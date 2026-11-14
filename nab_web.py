# nab_web.py — the local web server the UI windows talk to.
#
#   GET  /                 main window page          GET /overlay   overlay page
#   GET  /s/<file>         static UI files           GET /events    live events (SSE)
#   POST /api/<name>       JSON call into the engine
#   GET  /img/<id>.jpg     last rendered previews    GET /thumb?p=  saved-file thumbnails
#
# Listens on 127.0.0.1 only, random port.  Every request needs the per-run token
# (header X-NAB-Token or ?t=) and a localhost Host header, so another web page
# or another PC cannot drive NAB.
import os, shutil
import io
import json
import time
import hmac
import queue
import secrets
import logging
import mimetypes
mimetypes.add_type("image/webp", ".webp")
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PIL import Image

import nab_core
import nab_engine
from nab_engine import parse_line_json, resource_path

UI_DIR = None


def mascot_user_dir():
    """Editable character folder (Documents\\NAB Mascot). Pictures are copied in once; your own edits are never overwritten.
    When a new app version ships a new picture set (VERSION.txt), the old folder is kept as a backup and the new set is copied in."""
    d = os.path.join(os.path.expanduser("~"), "Documents", "NAB Mascot")
    try:
        src = os.path.join(ui_dir(), "mascot", "sajeeb")
        sj = os.path.join(d, "sajeeb")
        os.makedirs(sj, exist_ok=True)

        def ver(folder):
            try:
                with open(os.path.join(folder, "VERSION.txt"), "r") as fh:
                    return fh.read().strip()
            except Exception:
                return ""
        if ver(sj) != ver(src):
            old = [f for f in os.listdir(sj)]
            if old:
                bk = os.path.join(d, "backup_" + time.strftime("%Y%m%d_%H%M%S"))
                os.makedirs(bk, exist_ok=True)
                for f in old:
                    shutil.move(os.path.join(sj, f), os.path.join(bk, f))
                for f in ("sajeeb_poses.json", "READ ME FIRST.txt"):
                    if os.path.exists(os.path.join(d, f)):
                        shutil.move(os.path.join(d, f), os.path.join(bk, f))
        for f in os.listdir(src):
            t = os.path.join(sj, f)
            if not os.path.exists(t):
                shutil.copy2(os.path.join(src, f), t)
        cfg = os.path.join(d, "sajeeb_poses.json")
        if not os.path.exists(cfg):
            import json as _j
            with open(os.path.join(ui_dir(), "mascot", "skins.json"), "r", encoding="utf-8") as fh:
                ent = _j.load(fh).get("sajeeb")
            with open(cfg, "w", encoding="utf-8") as fh:
                _j.dump(ent, fh, indent=1)
        rd = os.path.join(d, "READ ME FIRST.txt")
        if not os.path.exists(rd):
            with open(os.path.join(src, "README.txt"), "r", encoding="utf-8") as a, open(rd, "w", encoding="utf-8") as b:
                b.write("Replace the pictures in the folder 'sajeeb' with yours (same file names), then restart NAB.\n"
                        "Pose list, frame lists and animation speeds are in sajeeb_poses.json.\n\n" + a.read())
    except Exception as e:
        logging.error(f"mascot folder: {e}")
    return d


def ui_dir():
    global UI_DIR
    if UI_DIR is None:
        UI_DIR = resource_path("nab_ui")
        if not os.path.isdir(UI_DIR):
            UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nab_ui")
    return UI_DIR


# endpoints usable before the Telegram approval has been granted
OPEN_API = {"state_min", "login_begin", "login_precheck", "ping", "acct_login", "acct_google_begin", "acct_google_poll", "acct_google_cfg"}


class _Img:
    """Tiny LRU of rendered previews (id -> jpeg bytes)."""

    def __init__(self, n=6):
        self.n, self.d, self.lock = n, OrderedDict(), threading.Lock()

    def put(self, key, data):
        with self.lock:
            self.d[key] = data
            self.d.move_to_end(key)
            while len(self.d) > self.n:
                self.d.popitem(last=False)

    def get(self, key):
        with self.lock:
            return self.d.get(key)


class Api:
    """JSON methods. Each takes the decoded request body (dict) and returns JSON-able."""

    def __getattr__(self, name):
        # tool calls: "<tool>_<method>" -> nab_tools.get(tool).api_<method>(args)
        if name.startswith("_") or "_" not in name:
            raise AttributeError(name)
        tool, meth = name.split("_", 1)
        import nab_tools
        if tool not in nab_tools.TOOLS:
            raise AttributeError(name)
        fn = getattr(nab_tools.get(tool, self.e), "api_" + meth, None)
        if fn is None:
            raise AttributeError(name)
        return fn

    def __init__(self, eng, server):
        self.e, self.srv = eng, server
        self.thumbs = _Img(120)

    # ---- state / preview ----------------------------------------------------
    def state_min(self, a):
        e = self.e
        try:
            import nab_engine_host
            if not nab_engine_host.LOGIN_REQUIRED and not e.authorized:     # login switched off: open at once, no gate screen
                e.authorized = True
                e._start_session_touch()
                e.after_login()
        except Exception as ex:
            logging.error(f"open without login: {ex}")
        return {"authorized": e.authorized, "ui": e.ui_state, "version": _ver(),
                "login": e.hub._last.get("login")}

    def ping(self, a):
        return {"ok": True, "t": time.time()}

    def state(self, a):
        return self.e.get_state()

    def login_precheck(self, a):
        return self.e.login_precheck()


    def selfcheck(self, a):
        import nab_health
        return nab_health.run_all(self.e)

    # ---- accounts (see nab_accounts.py) ----
    def acct_status(self, a):
        import nab_accounts
        r = nab_accounts.status()
        r["owner_pc"] = self.e.acct_is_owner_pc()
        return r

    def acct_login(self, a):
        return self.e.acct_login(a.get("name", ""), a.get("password", ""))

    def acct_google_begin(self, a):
        import nab_google
        return nab_google.begin()

    def acct_google_poll(self, a):
        return self.e.acct_google_poll()

    def acct_google_cfg(self, a):
        import nab_google
        c = nab_google.config()
        if "client_id" in a and self.e.authorized and self.e.acct_can_manage():
            nab_google.save_config(a.get("client_id"), a.get("client_secret") if a.get("client_secret") else None)
            c = nab_google.config()
        return {"ok": True, "configured": bool(c["client_id"]), "client_id": c["client_id"] if self.e.acct_can_manage() else "", "has_secret": bool(c["client_secret"])}

    def acct_block(self, a):
        import nab_accounts
        return nab_accounts.block_email(a.get("email", ""), bool(a.get("blocked", True)), actor_ok=self.e.acct_can_manage())

    def acct_email(self, a):
        import nab_accounts
        r = nab_accounts.set_email(a.get("name", ""), a.get("email", ""), actor_ok=self.e.acct_can_manage())
        return r

    def acct_logout(self, a):
        import nab_accounts
        return nab_accounts.logout()

    def acct_list(self, a):
        import nab_accounts
        return {"ok": True, "users": nab_accounts.list_users(), "owner_pc": self.e.acct_is_owner_pc()}

    def acct_add(self, a):
        import nab_accounts
        r = nab_accounts.add_user(a.get("name", ""), a.get("password", ""), a.get("role", "staff"), a.get("display", ""), actor_ok=self.e.acct_can_manage())
        if r.get("ok"):
            self.e.sync_now()
        return r

    def acct_role(self, a):
        import nab_accounts
        r = nab_accounts.set_role(a.get("name", ""), a.get("role", ""), actor_ok=self.e.acct_can_manage())
        if r.get("ok"):
            self.e.sync_now()
        return r

    def acct_disable(self, a):
        import nab_accounts
        r = nab_accounts.set_disabled(a.get("name", ""), bool(a.get("disabled", True)), actor_ok=self.e.acct_can_manage())
        if r.get("ok"):
            self.e.sync_now()
        return r

    def acct_delete(self, a):
        import nab_accounts
        r = nab_accounts.delete_user(a.get("name", ""), actor_ok=self.e.acct_can_manage())
        if r.get("ok"):
            self.e.sync_now()
        return r

    def acct_reset(self, a):
        import nab_accounts
        r = nab_accounts.reset_password(a.get("name", ""), a.get("password", ""), actor_ok=self.e.acct_can_manage())
        if r.get("ok"):
            self.e.sync_now()
        return r

    def acct_change_pw(self, a):
        import nab_accounts
        r = nab_accounts.change_own_password(a.get("old", ""), a.get("new", ""))
        if r.get("ok"):
            self.e.sync_now()
        return r

    def audit_tail(self, a):
        import nab_accounts
        return {"ok": True, "rows": nab_accounts.audit_tail(int(a.get("n", 200) or 200), a.get("user", ""), a.get("action", ""))}

    def login_begin(self, a):
        if not getattr(self.e, "_login_started", False):
            self.e._login_started = True
            self.e.begin_login(mode=a.get("mode", "group"), reason=a.get("reason", ""), auto=bool(a.get("auto")))
        return {"ok": True}

    def preview(self, a):
        pr = self.e.render_preview(a.get("h", 1000), a.get("page", ""), a.get("cols", ""),
                                   a.get("header", None), force=bool(a.get("force")))
        key = f"{pr['rev']}-{abs(hash(pr['key'])) % 10**9}"
        self.srv.imgs.put(key, pr["jpeg"])
        return {"img": f"/img/{key}.jpg", "w": pr["w"], "h": pr["h"], "k": pr["k"], "header_h": pr["header_h"],
                "layout": pr["layout"], "free": pr.get("free", False), "rev": pr["rev"], "full_w": pr["full_w"], "full_h": pr["full_h"],
                "empty": pr["empty"]}

    def layers(self, a):
        d = self.e.doc
        return {"layers": d.info(), "free": d.free, "canvas": list(d.canvas_size()), "rev": d.rev, "undo": d.history_depth()[0], "redo": d.history_depth()[1]}

    def detect_log(self, a):
        return self.e.detect_log_get()

    # ---- v3.0.4 extras -------------------------------------------------------
    def paper_defaults(self, a):
        return self.e.paper_defaults_get()

    def paper_defaults_set(self, a):
        a = dict(a)
        return self.e.paper_defaults_set(a.pop("paper"), **a)

    def cleanup_save(self, a):
        return self.e.cleanup_save(a["layer"], a.get("shape"))

    def cleanup_apply(self, a):
        return self.e.cleanup_apply(a["layer"])

    def cleanup_clear(self, a):
        return self.e.cleanup_clear()

    def calibrate(self, a):
        return self.e.calibrate(a["px"], a["inches"], a.get("paper"))

    def inches(self, a):
        return self.e.estimate_inches()

    def detect_test(self, a):
        return self.e.detect_test()

    def learn_paper(self, a):
        return self.e.learn_paper(a.get("text", ""), a.get("paper", ""))

    def ext_setup_info(self, a):
        return self.e.ext_setup_info()

    def ext_open_browser(self, a):
        return self.e.ext_open_browser(a.get("browser"))

    def ext_open_folder(self, a):
        return self.e.ext_open_folder()

    def ext_status(self, a):
        return self.e.ext_status()

    def copy_last_saved(self, a):
        return self.e.copy_last_saved()

    def open_last_folder(self, a):
        return self.e.open_last_folder()

    def backups(self, a):
        return self.e.backup_list()

    def backup_now(self, a):
        return self.e.backup_now("manual")

    def backup_restore(self, a):
        return self.e.backup_restore(a.get("name", ""))

    def draft_check(self, a):
        return self.e.draft_check()

    def draft_restore(self, a):
        return self.e.draft_restore()

    def draft_discard(self, a):
        return self.e.draft_discard()

    def firstrun(self, a):
        return self.e.firstrun_status()

    def firstrun_done(self, a):
        return self.e.firstrun_done()

    def estimate(self, a):
        return self.e.estimate_save(a.get("page", ""), a.get("cols", ""))

    def meta_parse(self, a):
        return parse_line_json(a.get("line", ""))

    # ---- clips --------------------------------------------------------------
    def paste(self, a):
        added = self.e.paste_clipboard()
        return {"ok": bool(added), "n": len(added), "layers": self.e.doc.info(), "rev": self.e.doc.rev}

    def paste_data(self, a):
        """Images dropped on the window (base64 data URLs)."""
        import base64
        imgs = []
        for d in a.get("images", []):
            try:
                raw = d.split(",", 1)[1] if "," in d else d
                imgs.append(Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB"))
            except Exception:
                continue
        added = self.e.add_images(imgs)
        return {"ok": bool(added), "n": len(added), "rev": self.e.doc.rev}

    def edit(self, a):
        a = dict(a)
        return self.e.edit(a.pop("op"), a.pop("layer"), a.pop("shape", None), **a)

    def filter(self, a):
        a = dict(a)
        return self.e.filter(a.pop("name"), a.pop("layer", None), **a)

    def wand(self, a):
        return self.e.wand(a["layer"], a["x"], a["y"], a.get("tol", 24))

    def layer(self, a):
        a = dict(a)
        return self.e.layer_cmd(a.pop("cmd"), a.pop("layer", None), **a)

    def suggest_crop(self, a):
        return self.e.suggest_crop()

    # ---- saving -------------------------------------------------------------
    def save(self, a):
        import nab_accounts
        if not nab_accounts.can("save"):
            return {"ok": False, "error": "Your account can only view. Ask the owner for a staff account to save clips."}
        r = self.e.save(a.get("cats", []), a.get("line", ""))
        if isinstance(r, dict) and r.get("ok"):
            nab_accounts.audit("save", f"{', '.join(a.get('cats', []))} | {a.get('line', '')} | {getattr(self.e, 'paper', '')}")
        return r

    def undo_save(self, a):
        return self.e.undo_save()

    # ---- settings -----------------------------------------------------------
    def set_options(self, a):
        return self.e.set_options(**a)

    def set_paper(self, a):
        return {"ok": self.e.user_chose_paper(a["paper"])["ok"]}

    def set_date(self, a):
        return self.e.set_date(a["date"])

    def set_quick_saves(self, a):
        return self.e.set_quick_saves(a["map"])

    def set_hotkeys(self, a):
        return self.e.set_hotkeys(a["map"])

    def set_mappings(self, a):
        return self.e.set_mappings(a["map"])

    def get_mappings(self, a):
        return {"map": self.e.url_mappings}

    def explain(self, a):
        return {"text": self.e.explain_detection(a.get("text", ""))}

    def set_categories(self, a):
        self.e.save_categories(a["cats"])
        self.e.hub.emit("state_changed")
        return {"ok": True}

    def paper_add(self, a):
        ok, why = self.e.paper_add(a.get("name", ""))
        if ok:
            self.e.hub.emit("state_changed")
        return {"ok": ok, "error": why}

    def paper_rename(self, a):
        ok, why = self.e.paper_rename(a.get("old", ""), a.get("new", ""))
        if ok:
            self.e.hub.emit("state_changed")
        return {"ok": ok, "error": why}

    def paper_remove(self, a):
        ok, why = self.e.paper_remove(a.get("name", ""))
        if ok:
            self.e.hub.emit("state_changed")
        return {"ok": ok, "error": why}

    def set_papers(self, a):
        self.e.save_sources(a["papers"])
        self.e.hub.emit("state_changed")
        return {"ok": True}

    def set_draft(self, a):
        return self.e.set_draft(a.get("cats"), a.get("line"), a.get("src", ""), a.get("f"))

    def ui_set(self, a):
        self.e.ui_set(**a)
        return {"ok": True}

    def learn_remember(self, a):
        return self.e.learn_remember(a["fragment"], a["paper"])

    def learn_decline(self, a):
        return self.e.learn_decline(a["fragment"])

    def lock_tab(self, a):
        return self.e.lock_tab()

    def clear_tab_locks(self, a):
        return self.e.clear_tab_locks()

    # ---- recent / files -----------------------------------------------------
    def recent(self, a):
        return {"items": self.e.recent(a.get("limit", 60))}

    def retag(self, a):
        return self.e.retag(a["i"], a.get("paper"), a.get("page"), a.get("pos"), a.get("size"))

    def delete_saved(self, a):
        return self.e.delete_saved(a["i"])

    def discard(self, a):
        return self.e.discard_clips(bool(a.get("all")))

    def reopen(self, a):
        r = self.e.load_image_from_path(a["path"])
        return dict(r, ok=True) if r else {"ok": False}

    def reveal(self, a):
        return self.e.reveal(a.get("path"))

    def logo_upload(self, a):
        import base64
        from nab_text import strip_emoji_prefix
        d = a.get("data", "")
        raw = base64.b64decode(d.split(",", 1)[1] if "," in d else d)
        try:
            self.e.logo_save(strip_emoji_prefix(a["paper"]), raw)
        except Exception as ex:
            return {"ok": False, "error": f"Not a usable image: {ex}"}
        self.e.hub.emit("state_changed")
        return {"ok": True}

    def logo_from_clipboard(self, a):
        """Logo from a screenshot on the clipboard (Win+Shift+S)."""
        import io
        from nab_text import strip_emoji_prefix
        try:
            import nab_clipboard
            imgs = nab_clipboard.grab_images() or []
        except Exception as ex:
            return {"ok": False, "error": f"Clipboard unavailable: {ex}"}
        if not imgs:
            return {"ok": False, "error": "No image on the clipboard. Press Win+Shift+S, drag around the logo, then try again."}
        try:
            from PIL import Image, ImageChops
            im = imgs[0]
            if not hasattr(im, "convert"):
                im = Image.open(io.BytesIO(im))
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, im.getpixel((0, 0)))
            bb = ImageChops.difference(im, bg).getbbox()
            if bb:
                im = im.crop(bb)
            buf = io.BytesIO(); im.save(buf, "PNG")
            self.e.logo_save(strip_emoji_prefix(a["paper"]), buf.getvalue())
        except Exception as ex:
            return {"ok": False, "error": f"Could not save: {ex}"}
        self.e.hub.emit("state_changed")
        return {"ok": True}

    def logo_remove(self, a):
        from nab_text import strip_emoji_prefix
        self.e.logo_delete(strip_emoji_prefix(a["paper"]))
        self.e.hub.emit("state_changed")
        return {"ok": True}

    def logos(self, a):
        """Which papers have a logo file (for the dropdown)."""
        out = {}
        for p in self.e.paper_list:
            from nab_text import strip_emoji_prefix
            out[p] = bool(self.e.logo_path(strip_emoji_prefix(p)))
        return {"logos": out, "dirs": self.e.logo_dirs(), "found": sum(1 for v in out.values() if v), "total": len(out)}

    # ---- upload / sync / update / tools / connections ----------------------
    def upload_now(self, a):
        return self.e.upload_now()

    def upload_days(self, a):
        return self.e.upload_days()

    def upload_dates(self, a):
        return self.e.upload_dates(a.get("dates"), a.get("category", "*"))

    def schedule_upload(self, a):
        return self.e.schedule_upload_next_session()

    def drive_test(self, a):
        return self.e.drive_test()

    def sync_now(self, a):
        return self.e.sync_now()

    def sync_role(self, a):
        import nab_accounts
        if not nab_accounts.can("manage"):
            return {"ok": False, "error": "Only an owner account can change the sync role."}
        return self.e.sync_set_role(a.get("role"), a.get("id"))

    def sync_history(self, a):
        return {"items": self.e.sync_history()}

    def apply_update(self, a):
        return self.e.apply_update()

    def launch_tool(self, a):
        return self.e.launch_tool(a["name"])

    def pdf_today(self, a):
        return self.e.pdf_today()

    def mail_load(self, a):
        return self.e.mail_load()

    def mail_items(self, a):
        return self.e.mail_items()

    def titlebar(self, a):
        """Match the native window title bar to the current theme background colour."""
        import re
        bg = str(a.get("bg", ""))
        if not re.match(r"^#[0-9a-fA-F]{6}$", bg):
            return {"ok": False}
        try:
            import nab_winutil as W
            try:
                from nab_main import TITLE
            except Exception:
                TITLE = "News Automation Pro"
            hw = W.MAIN_HWND or W.find_window(TITLE)
            ok = bool(W.theme_titlebar(hw, bg))
            logging.info(f"titlebar {bg} hwnd={hw} ok={ok}")
            return {"ok": ok}
        except Exception as e:
            logging.error(f"titlebar: {e}")
            return {"ok": False}

    def mascot_folder(self, a):
        d = mascot_user_dir()
        if a.get("open"):
            try:
                os.startfile(d)
            except Exception as e:
                logging.error(f"open mascot folder: {e}")
        return {"ok": True, "path": d}

    def tg_open(self, a):
        """Open the Telegram group (or the bot chat for owner mode) in the browser / Telegram app."""
        import webbrowser, urllib.request, urllib.parse, json as _j
        try:
            import nab_telegram as T
            url = ""
            if a.get("mode") == "owner":
                try:
                    r = _j.load(urllib.request.urlopen("https://api.telegram.org/bot%s/getMe" % T.TG_BOT_TOKEN, timeout=6))
                    u = (r.get("result") or {}).get("username")
                    if u:
                        url = "https://t.me/" + u
                except Exception as e:
                    logging.error(f"tg getMe: {e}")
            else:
                url = getattr(T, "TG_GROUP_LINK", "") or ""
                if not url:
                    gid = str(T.TG_GROUP_CHAT_ID)
                    if gid.startswith("-100"):
                        url = "https://t.me/c/" + gid[4:] + "/1"
            if not url:
                url = "https://web.telegram.org/"
            if urllib.parse.urlparse(url).hostname not in ("t.me", "web.telegram.org"):
                return {"ok": False}
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            logging.error(f"tg_open: {e}")
            return {"ok": False}

    def mail_defaults(self, a):
        return self.e.mail_defaults()

    def mail_save(self, a):
        return self.e.mail_save(a.get("cfg") or {})

    def mail_password(self, a):
        return self.e.mail_password(a.get("pw") or "")

    def mail_test_conn(self, a):
        return self.e.mail_test_conn(a.get("cfg"))

    def mail_prepare(self, a):
        return self.e.mail_prepare(a.get("make_pdfs"), a.get("ids"))

    def mail_send(self, a):
        return self.e.mail_send(a.get("ids"), a.get("test"))

    def connections_get(self, a):
        return self.e.connections_get()

    def connections_set(self, a):
        return self.e.connections_set(a.get("values"), a.get("reset", False))

    def close_summary(self, a):
        return self.e.close_summary()

    def quit(self, a):
        """Close flow finished in the UI: upload choice + exit."""
        choice = a.get("upload", "skip")
        if choice == "now":
            self.e.upload_now()
            time.sleep(1.5)
        elif choice == "later":
            self.e.schedule_upload_next_session()
        threading.Thread(target=self.srv.on_quit, daemon=True).start()
        return {"ok": True}

    def window(self, a):
        """UI → native window actions (minimize, toggle overlay, etc.)."""
        h = self.srv.window_handler
        if h:
            return h(a.get("action"), a)
        return {"ok": False}


def _ver():
    try:
        from nab_constants import APP_VERSION
        return APP_VERSION
    except Exception:
        return ""


class NabServer:
    def __init__(self, engine, host="127.0.0.1", port=0):
        self.engine = engine
        self.token = secrets.token_urlsafe(24)
        self.imgs = _Img(8)
        self.api = Api(engine, self)
        self.window_handler = None
        self.on_quit = lambda: os._exit(0)
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "NAB"

            def log_message(self, *a):
                pass

            # -- helpers
            def _host_ok(self):
                host = (self.headers.get("Host") or "").split(":")[0].lower()
                return host in ("127.0.0.1", "localhost")

            def _auth(self, qs):
                t = self.headers.get("X-NAB-Token") or (qs.get("t") or [""])[0]
                return hmac.compare_digest(t, srv.token)

            def _send(self, code, body=b"", ctype="application/json", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:
                    pass

            def _json(self, obj, code=200):
                self._send(code, json.dumps(obj, default=str).encode("utf-8"))

            # -- GET
            def do_GET(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._host_ok():
                    return self._send(403, b"bad host", "text/plain")
                p = u.path
                try:
                    if p in ("/", "/index.html", "/overlay", "/pet"):
                        # page itself: token is handed over in the URL the window is opened with
                        if not self._auth(qs):
                            return self._send(403, b"forbidden", "text/plain")
                        name = {"/overlay": "overlay.html", "/pet": "pet.html"}.get(p, "index.html")
                        with open(os.path.join(ui_dir(), name), "rb") as f:
                            html = f.read().replace(b"__NAB_TOKEN__", srv.token.encode())
                        return self._send(200, html, "text/html; charset=utf-8")
                    if p.startswith("/s/mascot/"):
                        ud, r2 = mascot_user_dir(), os.path.normpath(p[10:]).lstrip("/\\")
                        if r2 == "skins.json":                       # bundled list, with the Sajeeb entry replaced by the user's own copy
                            import json as _j
                            with open(os.path.join(ui_dir(), "mascot", "skins.json"), "r", encoding="utf-8") as fh:
                                j = _j.load(fh)
                            try:
                                with open(os.path.join(ud, "sajeeb_poses.json"), "r", encoding="utf-8") as fh:
                                    j["sajeeb"] = _j.load(fh)
                            except Exception as e:
                                logging.error(f"sajeeb_poses.json: {e}")
                            return self._send(200, _j.dumps(j).encode(), "application/json", {"Cache-Control": "no-cache"})
                        uf = os.path.join(ud, r2)
                        if r2.startswith("sajeeb" + os.sep) and os.path.abspath(uf).startswith(os.path.abspath(ud)) and os.path.isfile(uf):
                            with open(uf, "rb") as f:
                                data = f.read()
                            return self._send(200, data, mimetypes.guess_type(uf)[0] or "application/octet-stream", {"Cache-Control": "no-cache"})
                    if p.startswith("/s/"):
                        rel = os.path.normpath(p[3:]).lstrip("/\\")
                        full = os.path.join(ui_dir(), rel)
                        if not os.path.abspath(full).startswith(os.path.abspath(ui_dir())) or not os.path.isfile(full):
                            return self._send(404, b"", "text/plain")
                        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                        if full.endswith(".js"):
                            ctype = "text/javascript; charset=utf-8"
                        with open(full, "rb") as f:
                            data = f.read()
                        return self._send(200, data, ctype, {"Cache-Control": "no-cache"})
                    if not self._auth(qs):
                        return self._send(403, b"forbidden", "text/plain")
                    if p.startswith("/img/"):
                        key = p[5:].rsplit(".", 1)[0]
                        data = srv.imgs.get(key)
                        if data is None:
                            return self._send(404, b"", "text/plain")
                        return self._send(200, data, "image/jpeg", {"Cache-Control": "max-age=60"})
                    if p == "/thumb":
                        return self._thumb((qs.get("p") or [""])[0], int((qs.get("w") or ["200"])[0]))
                    if p == "/lthumb":
                        return self._lthumb(int((qs.get("id") or ["0"])[0]), int((qs.get("w") or ["96"])[0]))
                    if p == "/logo":
                        return self._logo((qs.get("n") or [""])[0])
                    if p == "/events":
                        return self._events()
                    return self._send(404, b"", "text/plain")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as e:
                    logging.exception("GET")
                    self._json({"ok": False, "error": str(e)}, 500)

            def _thumb(self, path, w):
                eng = srv.engine
                ap = os.path.abspath(path)
                root = os.path.abspath(eng.base_root)
                if not ap.startswith(root) or not os.path.isfile(ap):
                    return self._send(404, b"", "text/plain")
                key = f"{ap}|{os.path.getmtime(ap)}|{w}"
                data = srv.api.thumbs.get(key)
                if data is None:
                    im = Image.open(ap)
                    im.draft("RGB", (w * 2, w * 4))
                    im = im.convert("RGB")
                    im.thumbnail((w, w * 3))
                    data = nab_core.jpeg_bytes(im, 70)
                    srv.api.thumbs.put(key, data)
                self._send(200, data, "image/jpeg", {"Cache-Control": "max-age=300"})

            def _lthumb(self, lid, w):
                doc = srv.engine.doc
                try:
                    l = doc.get(lid)
                except KeyError:     # layer was removed while the thumbnail was loading → blank pixel, no broken icon
                    import base64
                    return self._send(200, base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"), "image/gif", {"Cache-Control": "no-store"})
                key = f"L{lid}|{id(l.img)}|{w}"
                data = srv.api.thumbs.get(key)
                if data is None:
                    im = l.img.copy()
                    im.thumbnail((w * 2, w * 2))
                    data = nab_core.jpeg_bytes(im, 70)
                    srv.api.thumbs.put(key, data)
                self._send(200, data, "image/jpeg", {"Cache-Control": "no-store"})

            def _logo(self, name):
                from nab_text import strip_emoji_prefix
                eng = srv.engine
                im = eng.get_logo(strip_emoji_prefix(name), small=True)
                if im is None:
                    return self._send(404, b"", "text/plain")
                t = im.copy()
                t.thumbnail((160, 60))
                buf = io.BytesIO()
                t.save(buf, "PNG")
                self._send(200, buf.getvalue(), "image/png", {"Cache-Control": "max-age=600"})

            def _events(self):
                q = srv.engine.hub.subscribe()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    self.wfile.write(b": hi\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            ev = q.get(timeout=15)
                            self.wfile.write(b"data: " + json.dumps(ev, default=str).encode("utf-8") + b"\n\n")
                        except queue.Empty:
                            self.wfile.write(b": ka\n\n")
                        self.wfile.flush()
                except Exception:
                    pass
                finally:
                    srv.engine.hub.unsubscribe(q)
                    srv.client_gone()
                self.close_connection = True

            # -- POST
            def do_POST(self):
                u = urlparse(self.path)
                qs = parse_qs(u.query)
                if not self._host_ok() or not self._auth(qs):
                    return self._send(403, b"forbidden", "text/plain")
                if not u.path.startswith("/api/"):
                    return self._send(404, b"", "text/plain")
                name = u.path[5:]
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(n) if n else b"{}"
                    args = json.loads(raw.decode("utf-8") or "{}")
                    fn = getattr(srv.api, name, None)
                    if not fn or name.startswith("_"):
                        return self._json({"ok": False, "error": f"no such call {name}"}, 404)
                    if name not in OPEN_API and not srv.engine.authorized:
                        return self._json({"ok": False, "error": "not authorised"}, 401)
                    self._json(fn(args))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as e:
                    logging.exception(f"api {name}")
                    self._json({"ok": False, "error": str(e)}, 500)

        self.httpd = ThreadingHTTPServer((host, port), H)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._clients = 0
        self._lock = threading.Lock()

    def client_gone(self):
        pass

    def url(self, page=""):
        return f"http://127.0.0.1:{self.port}/{page}?t={self.token}"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="NAB-Web").start()
        return self
