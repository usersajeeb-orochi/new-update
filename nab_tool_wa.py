# nab_tool_wa.py — send saved clips to a WhatsApp chat or group (free, through WhatsApp Web).
#
# NAB keeps one browser profile that is logged in to WhatsApp Web (scan the QR code once).  Clips are sent through a
# single background worker, one after another, so the browser is never driven from two places at once.
# This is unofficial automation: keep volumes small (a few clips a day), ideally use a spare number.
# WhatsApp changes its page now and then - every step tries several selectors and, on a failure, keeps a screenshot
# (Documents\NAB_WhatsApp\last_error.png) so the cause can be seen.
import os
import re
import json
import time
import queue
import logging
import threading

import nab_engine

FILE = os.path.join(nab_engine.DOC_DIR, "nab_wa.json")
DBG = os.path.join(nab_engine.DOC_DIR, "NAB_WhatsApp")
DEFAULTS = {"chats": [], "default": "", "per_category": {}, "as_document": True, "caption": True, "auto": False, "show_window": False}
URL = os.environ.get("NAB_WA_URL") or "https://web.whatsapp.com/"


def load_cfg():
    d = json.loads(json.dumps(DEFAULTS))
    try:
        with open(FILE, encoding="utf-8") as f:
            d.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:
        pass
    return d


def auto_enabled():
    return bool(load_cfg().get("auto"))


def _profile():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB", "wa_profile")


def _marker():
    return os.path.join(_profile(), "nab_linked.flag")


def _is_linked():
    return os.path.isfile(_marker())


def _is_number(s):
    return bool(re.fullmatch(r"\+?[\d\s\-]{8,16}", s.strip()))


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.cfg = load_cfg()
        self.q = queue.Queue()
        self.worker = None
        self.status = "idle"          # idle | starting | login | ready | error
        self.msg = ""
        self.pending = 0
        self.lock = threading.Lock()
        self.want_login = False

    # ------------------------------------------------------------ helpers
    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="wa", **kw)

    def _set(self, status, msg=""):
        self.status, self.msg = status, msg
        self._emit(ev="status", status=status, msg=msg, pending=self.pending)

    def _save(self):
        try:
            tmp = FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False)
            os.replace(tmp, FILE)
        except Exception as e:
            logging.error(f"wa save: {e}")

    @staticmethod
    def deps():
        try:
            import playwright  # noqa: F401
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ api
    def api_state(self, a):
        return {"ok": True, "cfg": self.cfg, "status": self.status, "msg": self.msg, "linked": _is_linked(), "pending": self.pending, "deps": self.deps(),
                "categories": list(getattr(self.e, "categories", []) or [])}

    def api_settings(self, a):
        c = self.cfg
        if "chats" in a:
            c["chats"] = [x.strip() for x in (a["chats"] if isinstance(a["chats"], list) else re.split(r"[\n,]+", str(a["chats"]))) if x.strip()]
        for k in ("default",):
            if k in a:
                c[k] = str(a[k]).strip()
        for k in ("as_document", "caption", "auto", "show_window"):
            if k in a:
                c[k] = bool(a[k])
        if "per_category" in a and isinstance(a["per_category"], dict):
            c["per_category"] = {k: v for k, v in a["per_category"].items() if v}
        self._save()
        return self.api_state({})

    def api_login(self, a):
        """Open WhatsApp Web in a visible window so the QR code can be scanned."""
        if not self.deps():
            return {"ok": False, "error": "Playwright is not installed (pip install playwright)."}
        self.want_login = True
        self.q.put(("login", None))
        self._ensure_worker()
        return {"ok": True}

    def api_logout(self, a):
        self.q.put(("logout", None))
        self._ensure_worker()
        return {"ok": True}

    def _resolve(self, path, category=""):
        c = self.cfg
        return (c["per_category"].get(category) or c["default"] or "").strip()

    def api_send(self, a):
        paths = [p for p in (a.get("paths") or ([a["path"]] if a.get("path") else [])) if p and os.path.isfile(p)]
        if not paths:
            return {"ok": False, "error": "File not found."}
        chat = (a.get("chat") or self._resolve(paths[0], a.get("category", ""))).strip()
        if not chat:
            return {"ok": False, "error": "Choose a chat or group first (WhatsApp setup)."}
        if not self.deps():
            return {"ok": False, "error": "Playwright is not installed (pip install playwright)."}
        self._enqueue(paths, chat, a.get("caption"))
        return {"ok": True, "chat": chat, "n": len(paths)}

    def api_send_recent(self, a):
        try:
            h = self.e.session_history[int(a["i"])]
        except Exception:
            return {"ok": False, "error": "Clip not found."}
        return self.api_send({"path": h["path"], "category": h.get("category", ""), "chat": a.get("chat", "")})

    def auto_saved(self, saved):
        """Called after NAB saves clips: send them when 'auto' is on and the category has a chat."""
        if not self.cfg.get("auto") or not self.deps():
            return
        for s in saved:
            chat = self._resolve(s["path"], s.get("category", ""))
            if chat:
                self._enqueue([s["path"]], chat, None)

    # ------------------------------------------------------------ queue + worker
    def _enqueue(self, paths, chat, caption):
        with self.lock:
            self.pending += 1
        self.q.put(("send", (paths, chat, caption)))
        self._ensure_worker()
        self._emit(ev="status", status=self.status, msg=self.msg, pending=self.pending)

    def _ensure_worker(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()

    def _run(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            self._set("error", "Playwright is missing: " + str(e)[:80])
            return
        ctx = page = None
        visible = False
        try:
            with sync_playwright() as p:
                while True:
                    try:
                        kind, data = self.q.get(timeout=1800)
                    except queue.Empty:                                  # idle 30 min: close the browser to save memory
                        break
                    if kind == "logout":
                        try:
                            if ctx:
                                ctx.close()
                        except Exception:
                            pass
                        ctx = page = None
                        import shutil
                        shutil.rmtree(_profile(), ignore_errors=True)
                        self._set("idle", "Logged out.")
                        continue
                    want_visible = kind == "login" or bool(self.cfg.get("show_window"))
                    if ctx is not None and visible != want_visible and kind == "login":
                        try:
                            ctx.close()
                        except Exception:
                            pass
                        ctx = page = None
                    if ctx is None:
                        try:
                            ctx, page = self._open(p, want_visible)
                            visible = want_visible
                        except Exception as e:
                            self._fail(kind, data, "Could not start the browser: " + str(e)[:120])
                            continue
                    try:
                        if kind == "login":
                            self._wait_login(page, 300)
                            page.wait_for_timeout(8000)                          # let WhatsApp write its session to the profile
                            try:
                                os.makedirs(_profile(), exist_ok=True)
                                open(_marker(), "w").write(str(time.time()))
                            except Exception:
                                pass
                            if not self.cfg.get("show_window"):                  # carry on hidden: the saved profile keeps you linked
                                ctx.close(); ctx = page = None
                        else:
                            try:
                                self._send(page, *data)
                            except Exception as e1:
                                if "closed" not in str(e1).lower():
                                    raise
                                logging.info("WhatsApp browser was closed during the send - reopening and retrying once")
                                ctx = page = None
                                self._set("starting", "Browser closed - reopening…")
                                ctx, page = self._open(p, want_visible)
                                visible = want_visible
                                self._send(page, *data)
                    except Exception as e:
                        self._fail(kind, data, str(e)[:160], page)
                        if "closed" in str(e).lower():
                            ctx = page = None
        finally:
            try:
                if ctx:
                    ctx.close()
            except Exception:
                pass
            if self.status not in ("error", "idle"):
                self._set("idle", "")

    def _open(self, p, visible):
        self._set("starting", "Starting browser…")
        prof = _profile()
        os.makedirs(prof, exist_ok=True)
        last = None
        for ch in ("chrome", "msedge", None):
            try:
                kw = dict(user_data_dir=prof, headless=not visible, viewport={"width": 1280, "height": 860},
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"], ignore_default_args=["--enable-automation"],
                          user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                if ch:
                    kw["channel"] = ch
                ctx = p.chromium.launch_persistent_context(**kw)
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                return ctx, page
            except Exception as e:
                last = e
        raise RuntimeError(last)

    # ------------------------------------------------------------ page logic
    SEARCH = ['div[contenteditable="true"][data-tab="3"]', 'div[role="textbox"][aria-label*="Search"]', 'div[contenteditable="true"][aria-label*="Search"]']
    READY = '#pane-side, div[aria-label="Chat list"], div[data-testid="chat-list"]'

    def _logged_in(self, page):
        try:
            return page.locator(self.READY).first.is_visible()
        except Exception:
            return False

    def _wait_login(self, page, secs):
        self._set("login", "Scan the QR code with WhatsApp on your phone: Linked devices > Link a device.")
        end = time.time() + secs
        while time.time() < end:
            if self._logged_in(page):
                self._set("ready", "WhatsApp is linked.")
                return
            page.wait_for_timeout(1000)
        raise RuntimeError("The QR code was not scanned in time. Press Link WhatsApp again.")

    def _ensure_ready(self, page):
        if not self._logged_in(page):
            try:
                page.wait_for_selector(self.READY, timeout=45000)
            except Exception:
                try:
                    os.remove(_marker())
                except Exception:
                    pass
                raise RuntimeError("WhatsApp is not linked (or the link expired). Settings > WhatsApp > Link WhatsApp.")
        self._set("ready", "")

    def _open_chat(self, page, chat):
        if _is_number(chat):                                           # a phone number: your own number or a person
            num = re.sub(r"\D", "", chat)
            page.goto(f"{URL}send?phone={num}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('footer div[contenteditable="true"]', timeout=45000)
            return
        box = None
        for s in self.SEARCH:
            loc = page.locator(s).first
            try:
                loc.wait_for(state="visible", timeout=6000)
                box = loc
                break
            except Exception:
                continue
        if box is None:
            raise RuntimeError("Could not find WhatsApp's search box (the page may have changed).")
        box.click()
        page.keyboard.press("Control+A"); page.keyboard.press("Delete")
        page.keyboard.type(chat, delay=25)
        page.wait_for_timeout(1200)
        hit = page.locator(f'#pane-side span[title="{chat}"]').first
        if hit.count() == 0:
            hit = page.locator(f'#pane-side span[title*="{chat}" i]').first
        if hit.count() == 0:
            raise RuntimeError(f'No chat or group named "{chat}" found. Check the spelling in WhatsApp setup.')
        hit.click()
        page.wait_for_selector('footer div[contenteditable="true"]', timeout=20000)

    def _send(self, page, paths, chat, caption):
        try:
            self._ensure_ready(page)
            self._open_chat(page, chat)
            doc = bool(self.cfg.get("as_document", True))
            page.locator('footer span[data-icon="plus"], footer span[data-icon="clip"], footer span[data-icon="attach-menu-plus"], footer button[aria-label*="Attach"], footer div[title*="Attach"]').first.click(timeout=15000)
            page.wait_for_timeout(700)
            files = page.locator('input[type="file"]')
            inp = None
            n = files.count()
            for i in range(n):                                           # document input has no image/video restriction
                acc = (files.nth(i).get_attribute("accept") or "")
                if doc and ("image" not in acc and "video" not in acc):
                    inp = files.nth(i); break
                if not doc and "image" in acc:
                    inp = files.nth(i); break
            if inp is None:
                inp = files.first
            inp.set_input_files(paths)
            SENDSEL = 'span[data-icon="send"], span[data-icon="wds-ic-send-filled"], div[aria-label="Send"], button[aria-label="Send"], [role="button"][aria-label="Send"]'
            page.wait_for_selector(SENDSEL, timeout=45000)
            page.wait_for_timeout(800)
            if caption is None and self.cfg.get("caption", True):
                caption = os.path.splitext(os.path.basename(paths[0]))[0] if len(paths) == 1 else ""
            if caption:
                cap = page.locator('div[contenteditable="true"][aria-label*="caption" i], div[contenteditable="true"][data-tab="10"], div[role="dialog"] div[contenteditable="true"]').first
                try:
                    cap.click(timeout=3000); page.keyboard.type(caption[:300], delay=5)
                except Exception:
                    pass
            clicked = False
            for _ in range(3):
                try:
                    page.locator(SENDSEL).last.click(timeout=5000)
                    clicked = True
                    break
                except Exception:
                    page.wait_for_timeout(700)
            if not clicked:
                page.keyboard.press("Enter")                              # fall back to Enter when the button cannot be clicked
            try:
                page.wait_for_selector(SENDSEL, state="detached", timeout=20000)   # the preview closes once the file is sent
            except Exception:
                page.keyboard.press("Enter")
                page.wait_for_selector(SENDSEL, state="detached", timeout=15000)
            page.wait_for_timeout(2000)
            try:
                page.wait_for_selector('span[data-icon="msg-time"]', state="detached", timeout=90000)   # clock icon disappears when uploaded
            except Exception:
                pass
            with self.lock:
                self.pending = max(0, self.pending - 1)
            self._emit(ev="sent", chat=chat, name=os.path.basename(paths[0]), n=len(paths), pending=self.pending)
        except Exception:
            raise

    def _fail(self, kind, data, why, page=None):
        if page is not None:
            try:
                os.makedirs(DBG, exist_ok=True)
                page.screenshot(path=os.path.join(DBG, "last_error.png"))
            except Exception:
                pass
        if kind == "send":
            with self.lock:
                self.pending = max(0, self.pending - 1)
            self._emit(ev="fail", chat=data[1], name=os.path.basename(data[0][0]), error=why, pending=self.pending)
        self._set("error" if kind == "login" else self.status if self.status != "starting" else "error", why)
