# nab_engine.py — NAB's brain without a window.
#
# Holds everything the old NewsClipper class held (settings, categories, papers,
# the clip document, saving, history) but with no Tk. The web UI talks to it
# through nab_web.py; background duties (clipboard watcher, Telegram, Drive,
# updates, sync) live in nab_engine_host.py which is mixed in below.
import os
import re
import io
import sys
import json
import time
import queue
import logging
import threading
import datetime
import concurrent.futures

from PIL import Image

import nab_core
import nab_meta
import nab_recent
import nab_connections
import nab_clipboard
from nab_text import strip_emoji_prefix

DOC_DIR = os.environ.get("NAB_DOC_DIR") or os.path.join(os.path.expanduser("~"), "Documents")
UI_STATE_FILE = os.path.join(DOC_DIR, "nab_ui_state.json")        # per-PC, never synced
LOGO_FOLDER_NAME = "Logos"
NO_HEADER_CATS = ("Telecom", "Pride Group")                       # same rule as before

DEFAULT_QUICK_SAVES = {
    "1": "Beximco/Bank", "2": "Mineral/Power", "3": "Pride Group", "4": "Telecom/Industry", "5": "BAT",
    "6": "Beximco/Loan", "7": "Mineral/LNG", "8": "Mineral/LPG", "9": "Beximco/Capital Market",
    "Ctrl+1": "Beximco/Economy", "Ctrl+2": "Beximco/Finance", "Ctrl+3": "Telecom/TT", "Ctrl+4": "Telecom/GP",
    "Ctrl+5": "Telecom/Robi", "Ctrl+6": "Telecom/BL", "Ctrl+7": "Beximco/Pharma Industry",
    "Ctrl+8": "United Group/UIU", "Ctrl+9": "Beximco/Mr.Salman F Rahman",
}

DEFAULT_HOTKEYS = {
    "paste": "<Control-v>", "undo": "<Control-z>", "redo": "<Control-y>",
    "delete": "<Delete>", "generate": "<Control-s>", "trim": "<Control-t>",
    "clean": "<Control-l>", "pad": "<Control-e>", "open": "<Control-o>",
    "move_up": "<Control-Up>", "move_down": "<Control-Down>", "swap": "<Control-Left>",
    "tool_crop": "c", "tool_erase": "e", "tool_highlight": "h", "tool_redact": "r",
    "discard": "<Control-Delete>",
}

DEFAULT_CATS = {
    "BAT": [],
    "Beximco": ["Bank", "Beximco Group", "Capital Market", "Ceramics", "DTH",
                "Economy", "Finance", "Loan", "Pharma Industry", "Mr.Salman F Rahman", "NOAB"],
    "Mineral": ["LNG", "LPG", "Power"],
    "Pride Group": [],
    "Telecom": ["GP", "Robi", "BL", "TT", "Industry"],
    "United Group": ["United Finance", "United Healthcare", "United Power", "United Group", "UIU"],
    "Xiaomi": [],
}

DEFAULT_PAPERS = [
    "⭐ Daily Star", "📊 TBS", "💹 Financial Express", "👁️ Daily Observer",
    "🇧🇩 Dhaka Tribune", "📰 New Age", "☀️ Daily Sun", "🌍 New Nation",
    "🏛️ Asian Age", "🇧🇩 Bangladesh Today", "📜 TOB", "🌅 Prothom Alo",
    "🕒 Samakal", "🗳️ Ittefaq", "🏹 Jugantor", "🗣️ Kaler Kantha",
    "🏛️ Janakantha", "🕌 Naya Diganta", "🖋️ Daily Inqilab", "💼 Bonik Barta",
    "🇧🇩 Bangladesh Pratidin", "📰 Sangbad", "📅 Jaijaidin", "👤 Manabzamin",
    "⏰ Amader Shomoy", "📈 Sharebiz", "📅 Ajker Patrika",
    "🇧🇩 Protidiner Bangladesh", "💡 Shomoyer Alo", "🗞️ Pratidiner Sangbad",
    "🏙️ Desh Rupantor", "🔔 Kalbela", "🇧🇩 Rupali Bangladesh",
    "📖 Khoborer Kagoj", "📰 Amardesh", "💡 Alokito Bangladesh"]

DEFAULT_URLS = {
    "prothom alo": "🌅 Prothom Alo", "prothomalo": "🌅 Prothom Alo",
    "daily star": "⭐ Daily Star", "thedailystar": "⭐ Daily Star",
    "tbs": "📊 TBS", "financial express": "💹 Financial Express",
    "observer": "👁️ Daily Observer", "dhaka tribune": "🇧🇩 Dhaka Tribune",
    "new age": "📰 New Age", "daily sun": "☀️ Daily Sun",
    "samakal": "🕒 Samakal", "ittefaq": "🗳️ Ittefaq",
    "jugantor": "🏹 Jugantor", "kaler kantho": "🗣️ Kaler Kantha",
    "janakantha": "🏛️ Janakantha", "naya diganta": "🕌 Naya Diganta",
    "inqilab": "🖋️ Daily Inqilab", "bonik barta": "💼 Bonik Barta",
    "bangladesh pratidin": "🇧🇩 Bangladesh Pratidin", "kalbela": "🔔 Kalbela",
    "epaper.thedailystar.net": "⭐ Daily Star", "epaper.tbsnews.net": "📊 TBS",
    "epaper.prothomalo.com": "🌅 Prothom Alo", "epaper.samakal.com": "🕒 Samakal",
    "epaper.ittefaq.com.bd": "🗳️ Ittefaq", "epaper.jugantor.com": "🏹 Jugantor",
    "epaper.kalerkantho.com": "🗣️ Kaler Kantha", "epaper.kalbela.com": "🔔 Kalbela",
}


def _is_frozen():
    return getattr(sys, "frozen", False)


def exe_dir():
    return os.path.dirname(sys.executable) if _is_frozen() else os.path.abspath(".")


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None) or os.path.abspath(".")
    return os.path.join(base, rel)


def _read_json(path, default=None):
    """Reads a settings file. If it is damaged the last good copy (.bak) is used, and the damaged file is kept as .bad - never silently replaced by defaults."""
    for p, tag in ((path, ""), (path + ".bak", " (backup)")):
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if tag:
                    logging.warning(f"read {path}: using the backup copy")
                return d
        except Exception as e:
            logging.error(f"read {p}: {e}")
            if not tag:
                try:
                    import shutil
                    shutil.copy2(p, path + ".bad")
                except Exception:
                    pass
    return default


def _backup_file(path):
    """Before a settings file is rewritten: keep the previous version as .bak, plus one dated copy per day (last 7 days)."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 3:
            return
        import shutil
        shutil.copy2(path, path + ".bak")
        day = time.strftime("%Y%m%d")
        dated = f"{path}.{day}.bak"
        if not os.path.exists(dated):
            shutil.copy2(path, dated)
            base = os.path.basename(path) + "."
            folder = os.path.dirname(path)
            old = sorted(f for f in os.listdir(folder) if f.startswith(base) and f.endswith(".bak") and f != os.path.basename(path) + ".bak")
            for f in old[:-7]:
                try:
                    os.remove(os.path.join(folder, f))
                except Exception:
                    pass
    except Exception as e:
        logging.error(f"backup {path}: {e}")


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    _backup_file(path)
    os.replace(tmp, path)


def _safe_name(s):
    return re.sub(r'[\\/:*?"<>|]+', "", str(s)).strip()


# ─────────────────────────────────────────────────────────────────────────────
class Hub:
    """Event fan-out to every connected UI window (SSE)."""

    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()
        self._last = {}

    def subscribe(self):
        q = queue.Queue(maxsize=400)
        with self._lock:
            self._subs.append(q)
            replay = list(self._last.values())
        for ev in replay:                 # late joiners (overlay) get current status
            q.put(ev)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def emit(self, type_, sticky=False, **data):
        ev = {"type": type_, "t": time.time(), **data}
        with self._lock:
            if sticky:
                self._last[type_] = ev
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(ev)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(ev)
                except Exception:
                    pass
        return ev


class _Var:
    """Tiny stand-in for the Tk variables/widgets borrowed code still talks to."""

    def __init__(self, getter, setter=None):
        self._g, self._s = getter, setter

    def get(self):
        return self._g()

    def set(self, v):
        if self._s:
            self._s(v)

    def configure(self, **kw):
        pass


class _StatusShim:
    def __init__(self, eng):
        self._eng = eng
        self._text = "READY"

    def configure(self, text=None, text_color=None, **kw):
        if text is not None:
            self._text = text
            self._eng.hub.emit("status", sticky=True, text=text, color=text_color or "")

    def cget(self, key):
        return self._text if key == "text" else ""


# ─────────────────────────────────────────────────────────────────────────────
class EngineBase:
    PROXY_HEIGHT = 1440

    def __init__(self):
        self.hub = Hub()
        self.lock = threading.RLock()
        self.doc = nab_core.Document()

        # ---- paths (same files as the classic app → both stay compatible) ----
        os.makedirs(DOC_DIR, exist_ok=True)
        self.config_file = os.path.join(DOC_DIR, "news_clipper_cats.json")
        self.settings_file = os.path.join(DOC_DIR, "news_clipper_settings.json")
        self.sources_file = os.path.join(DOC_DIR, "news_clipper_sources.json")
        self.mappings_file = os.path.join(DOC_DIR, "news_clipper_mappings.json")
        self.logo_dir = os.path.join(exe_dir(), LOGO_FOLDER_NAME)
        try:
            os.makedirs(self.logo_dir, exist_ok=True)
        except Exception:
            pass
        self.logo_dir_bundled = resource_path(LOGO_FOLDER_NAME)
        self.base_root = os.path.join(DOC_DIR, "Monitoring")

        # ---- settings (same schema as before) ----
        self.logo_scale = 0.8
        self.text_scale = 1.0
        self.quality = 40
        self.hd_mode = False
        self.auto_snatch = False
        self.auto_polish = False
        self.quick_saves = dict(DEFAULT_QUICK_SAVES)
        self.universal_hotkeys = dict(DEFAULT_HOTKEYS)
        self.extra_settings = {
            "min_file_size_kb": 20, "max_file_size_kb": 5000, "batch_save_enabled": False,
            "autosave_enabled": False, "autosave_interval": 300,
            "daily_report_enabled": False, "daily_report_hour": 18,
            "smart_fit": True, "fit_target_kb": 500, "fit_big_kb": 780, "upload_enabled": False, "slow_mode": "auto",
            "missed_guard": True, "missed_guard_s": 45, "ov_opacity": 100, "ov_snap": True,
        }
        self.daily_goal = 0
        self.daily_goal_notified = False
        self.last_active_date = ""
        self.current_streak = 0
        self.group_chat_id = ""
        self.url_mappings = {}
        self.paper_list = []
        self.categories = {}

        # ---- session state ----
        self.paper = ""                      # selected label (with emoji)
        self.current_date = datetime.datetime.now()
        self.show_header = True
        self.last_page = ""                  # remembered between clips
        self.last_pos = ""
        self.last_size = ""
        self.last_saved_path = ""
        self.session_history = []
        self._last_save = None               # for "Undo save"
        self._logo_cache = {}
        self._preview_cache = None
        self._preview_lock = threading.Lock()
        self._reg_lock = threading.Lock()
        self._reg = None
        self._uploaded = set()
        self.ui_state = _read_json(UI_STATE_FILE, {}) or {}

        # ---- shims for code borrowed from the old Tk class ----
        self.status_label = _StatusShim(self)
        self.paper_combo = _Var(lambda: self.paper, self._set_paper_quiet)
        self.paper_var = self.paper_combo
        self.show_text_var = _Var(lambda: self.show_header, lambda v: setattr(self, "show_header", bool(v)))
        self.hd_mode_var = _Var(lambda: self.hd_mode, lambda v: setattr(self, "hd_mode", bool(v)))
        self.auto_snatch_var = _Var(lambda: self.auto_snatch, lambda v: setattr(self, "auto_snatch", bool(v)))

        self.load_settings()
        self.load_sources()
        self.load_categories()

    # ---- the few Tk-isms borrowed code expects ---------------------------------
    def after(self, ms, fn=None, *args):
        if fn is None:
            return None
        if ms <= 0:
            threading.Thread(target=fn, args=args, daemon=True).start()
            return None
        t = threading.Timer(ms / 1000.0, fn, args=args)
        t.daemon = True
        t.start()
        return t

    def update_idletasks(self):
        pass

    @property
    def orig_images(self):
        return [l.img for l in self.doc.layers]

    def status(self, text, color="", ms=0):
        self.hub.emit("status", sticky=True, text=text, color=color)
        if ms:
            self.after(ms, lambda t=text: self._status_idle_if(t))

    def _status_idle_if(self, text):
        if self.status_label._text == text:
            self.status_label.configure(text="READY")

    def toast(self, text, kind="info", ms=3500, **extra):
        self.hub.emit("toast", text=text, kind=kind, ms=ms, **extra)

    # ───────────────────────────── settings I/O ─────────────────────────────
    def load_settings(self):
        user_urls = (_read_json(self.mappings_file, {}) or {}).get("url_mappings", {})
        self.url_mappings = dict(DEFAULT_URLS)
        self.url_mappings.update(user_urls)
        data = _read_json(self.settings_file)
        self.universal_hotkeys = dict(DEFAULT_HOTKEYS)
        if not isinstance(data, dict):
            return
        self.logo_scale = float(data.get("logo_scale", 0.8))
        self.text_scale = float(data.get("text_scale", 1.0))
        self.quality = float(data.get("quality", 40))
        self.hd_mode = bool(data.get("hd_mode", False))
        self.auto_snatch = bool(data.get("auto_snatch", False))
        self.auto_polish = bool(data.get("auto_polish", False))
        self.quick_saves = data.get("quick_saves") or dict(DEFAULT_QUICK_SAVES)
        hk = data.get("hotkeys")
        if isinstance(hk, dict):
            self.universal_hotkeys.update(hk)
        self.extra_settings.update(data.get("extra_settings", {}) or {})
        self.daily_goal = data.get("daily_goal", 0) or 0
        self.last_active_date = data.get("last_active_date", "")
        self.current_streak = data.get("current_streak", 0)
        self.group_chat_id = data.get("group_chat_id", "")
        root = data.get("base_root", "")
        if root and os.path.exists(root):
            self.base_root = root

    def save_settings(self):
        try:
            _write_json(self.settings_file, {
                "logo_scale": self.logo_scale, "text_scale": self.text_scale,
                "quality": self.quality, "hd_mode": self.hd_mode,
                "auto_snatch": self.auto_snatch, "auto_polish": self.auto_polish,
                "quick_saves": self.quick_saves, "hotkeys": self.universal_hotkeys,
                "base_root": self.base_root, "extra_settings": self.extra_settings,
                "daily_goal": self.daily_goal, "last_active_date": self.last_active_date,
                "current_streak": self.current_streak, "group_chat_id": self.group_chat_id,
            })
        except Exception as e:
            logging.error(f"save_settings: {e}")
        try:
            _write_json(self.mappings_file, {"url_mappings": self.url_mappings})
        except Exception as e:
            logging.error(f"save mappings: {e}")

    def load_sources(self):
        data = _read_json(self.sources_file)
        if isinstance(data, list) and data:
            self.paper_list = list(data)
        elif getattr(self, "paper_list", None):
            pass                                            # unreadable file: keep what is already loaded, never fall back to the default list
        else:
            self.paper_list = list(DEFAULT_PAPERS)
        if self.paper not in self.paper_list:
            self.paper = self.paper_list[0] if self.paper_list else ""

    def save_sources(self, new_list=None):
        if new_list is not None:
            if not new_list:
                logging.error("save_sources: refused to save an empty paper list")
                return
            self.paper_list = list(new_list)
            if self.paper not in self.paper_list:
                self.paper = self.paper_list[0] if self.paper_list else ""
        try:
            _write_json(self.sources_file, self.paper_list)
        except Exception as e:
            logging.error(f"save_sources: {e}")

    def load_categories(self):
        data = _read_json(self.config_file)
        if isinstance(data, dict) and data:
            self.categories = {str(k): list(v) for k, v in data.items()}
        else:
            self.categories = {k: list(v) for k, v in DEFAULT_CATS.items()}

    def save_categories(self, cats=None):
        if cats is not None:
            self.categories = {str(k): [str(s) for s in v] for k, v in cats.items()}
        try:
            _write_json(self.config_file, self.categories)
        except Exception as e:
            logging.error(f"save_categories: {e}")

    def category_paths(self):
        out = []
        for p, subs in self.categories.items():
            out.append(p)
            out.extend(f"{p}/{s}" for s in subs)
        return out

    # ── per-PC UI state (window size, overlay place, language …) ───────────
    def ui_get(self, key, default=None):
        return self.ui_state.get(key, default)

    def ui_set(self, **kw):
        self.ui_state.update(kw)
        if any(k.startswith("mascot") for k in kw):
            try: self.hub.emit("settings_changed")
            except Exception: pass
        try:
            _write_json(UI_STATE_FILE, self.ui_state)
        except Exception as e:
            logging.error(f"ui_set: {e}")

    # ───────────────────────────── paper & logo ─────────────────────────────
    @property
    def paper_clean(self):
        return strip_emoji_prefix(self.paper) if self.paper else ""

    def _set_paper_quiet(self, label):
        if label in self.paper_list:
            self.paper = label

    def set_paper(self, label):
        with self.lock:
            if label not in self.paper_list:
                m = [p for p in self.paper_list if strip_emoji_prefix(p).lower() == strip_emoji_prefix(label).lower()]
                if not m:
                    return False
                label = m[0]
            self.paper = label
            self._preview_cache = None
            self.hub.emit("paper", paper=label, clean=strip_emoji_prefix(label))
            return True

    def paper_add(self, name):
        name = (name or "").strip()
        if not name:
            return False, "Type the paper name."
        with self.lock:
            if any(strip_emoji_prefix(p).lower() == strip_emoji_prefix(name).lower() for p in self.paper_list):
                return False, "That paper is already in the list."
            self.paper_list.append(name)
            self.save_sources()
        return True, ""

    def paper_rename(self, old, new):
        new = (new or "").strip()
        with self.lock:
            if old not in self.paper_list or not new:
                return False, "Paper not found."
            if new != old and any(p != old and strip_emoji_prefix(p).lower() == strip_emoji_prefix(new).lower() for p in self.paper_list):
                return False, "Another paper already has that name."
            self.paper_list[self.paper_list.index(old)] = new
            if self.paper == old:
                self.paper = new
            oc, nc = strip_emoji_prefix(old), strip_emoji_prefix(new)
            if oc != nc:                                         # the logo file follows the new name
                lp = self.logo_path(oc)
                if lp and not self.logo_path(nc):
                    try:
                        import shutil
                        shutil.copy2(lp, os.path.join(self.logo_dirs()[0], nc + os.path.splitext(lp)[1]))
                        self.reload_logos()
                    except Exception as e:
                        logging.error(f"logo rename: {e}")
            self.save_sources()
        return True, ""

    def paper_remove(self, name):
        with self.lock:
            if name not in self.paper_list or len(self.paper_list) < 2:
                return False, "Keep at least one paper."
            self.paper_list.remove(name)
            if self.paper == name:
                self.paper = self.paper_list[0]
            self.save_sources()
        return True, ""

    def logo_dirs(self):
        user = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB", "Logos")
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logos")
        out, seen = [], set()
        for d in (user, self.logo_dir, self.logo_dir_bundled, here, os.path.join(DOC_DIR, "Logos")):
            k = os.path.normcase(os.path.abspath(d))
            if k not in seen:
                seen.add(k)
                out.append(d)
        return out

    def logo_path(self, paper_clean):
        want = (paper_clean or "").strip()
        if not want:
            return ""
        low = want.lower()
        for d in self.logo_dirs():
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                p = os.path.join(d, want + ext)
                if os.path.exists(p):
                    return p
            try:   # case / spacing tolerant match
                for f in os.listdir(d):
                    base, ext = os.path.splitext(f)
                    if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") and base.strip().lower() == low:
                        return os.path.join(d, f)
            except Exception:
                pass
        return ""

    def logo_save(self, paper_clean, png_bytes):
        """Store a logo for a paper (user folder, always writable) and refresh caches."""
        import io as _io
        im = Image.open(_io.BytesIO(png_bytes))
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        d = self.logo_dirs()[0]
        os.makedirs(d, exist_ok=True)
        im.save(os.path.join(d, f"{paper_clean}.png"), "PNG")
        self.reload_logos()
        return True

    def logo_delete(self, paper_clean):
        d = self.logo_dirs()[0]
        p = os.path.join(d, f"{paper_clean}.png")
        if os.path.exists(p):
            os.remove(p)
        self.reload_logos()
        return True

    def get_logo(self, paper_clean, small=False):
        """Cached logo PIL. `small` = capped to 900 px wide for previews (some
        logos are 5000+ px wide and would make every preview slow)."""
        key = (paper_clean, small)
        if key in self._logo_cache:
            return self._logo_cache[key]
        p = self.logo_path(paper_clean)
        img = None
        if p:
            try:
                img = Image.open(p)
                img.load()
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                if small and img.width > 900:
                    img = img.resize((900, max(1, int(img.height * 900 / img.width))), Image.Resampling.LANCZOS)
            except Exception as e:
                logging.error(f"logo {p}: {e}")
                img = None
        self._logo_cache[key] = img
        return img

    def reload_logos(self):
        self._logo_cache.clear()
        self._preview_cache = None

    # ───────────────────────────── metadata / header ─────────────────────────
    def header_text(self, page, cols):
        return f"Page-{page}, Pos-{cols}, Date-{self.current_date.strftime('%d-%m-%Y')}"

    def header_allowed(self, cat_parts):
        return not any(x in NO_HEADER_CATS for x in cat_parts)

    # ───────────────────────────── clips ─────────────────────────────────────
    def add_images(self, imgs, name="Clip", polish=None):
        """Add pasted images as layers. Auto polish (setting) = trim+clean+pad."""
        if not imgs:
            return []
        do_polish = self.auto_polish if polish is None else polish
        added = []
        with self.doc.lock:
            self.doc.checkpoint()
            for im in imgs:
                im = im.convert("RGB")
                if do_polish:
                    try:
                        im = nab_core.polish(im)
                    except Exception as e:
                        logging.error(f"polish: {e}")
                added.append(self.doc.add(im, name, checkpoint=False))
        try:
            self.post_paste([(l, l.img) for l in added])
        except Exception as ex:
            logging.error(f"post_paste: {ex}")
        self._preview_cache = None
        n = len(self.doc.layers)
        self.hub.emit("clips", n=n, rev=self.doc.rev)
        self.status(f"PASTED! ({n} clip{'s' if n != 1 else ''})", "#F59E0B", 2000)
        return added

    def paste_clipboard(self):
        imgs = nab_clipboard.grab_images()
        if not imgs:
            self.status("CLIPBOARD EMPTY", "#D32F2F", 2000)
            return []
        return self.add_images(imgs)

    # ---- header registry: remembers how tall the logo/header band of each saved clip is,
    #      so reopening a clip can cut it off and leave only the news (no manual erasing) ----
    def _reg_file(self):
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB", "clip_registry.json")

    def _reg_get(self):
        if getattr(self, "_reg", None) is None:
            try:
                with open(self._reg_file(), "r", encoding="utf-8") as fh:
                    self._reg = json.load(fh)
            except Exception:
                self._reg = {}
        return self._reg

    def _reg_put(self, items):
        with self._reg_lock:
            reg = self._reg_get()
            for path, top, bottom in items:
                reg[os.path.normcase(os.path.abspath(path))] = [round(top, 5), round(bottom, 5)]
            if len(reg) > 4000:
                for k in list(reg)[:len(reg) - 3000]:
                    reg.pop(k, None)
            try:
                os.makedirs(os.path.dirname(self._reg_file()), exist_ok=True)
                tmp = self._reg_file() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(reg, fh)
                os.replace(tmp, self._reg_file())
            except Exception as e:
                logging.debug(f"registry: {e}")

    def _reg_move(self, old, new):
        with self._reg_lock:
            reg = self._reg_get()
            v = reg.pop(os.path.normcase(os.path.abspath(old)), None)
            if v:
                reg[os.path.normcase(os.path.abspath(new))] = v

    def _header_fracs(self, width, height, show_header, paper):
        """Fallback when a file isn't in the registry: rebuild the band height the way compose() does."""
        logo = self.get_logo(paper, small=False)
        if logo is not None and logo.width:
            tw = max(1, int(width * self.logo_scale))
            lh = max(1, int(logo.height * (tw / logo.width)))
        else:
            lh = 40
        fs = max(12, int((width * 0.03) * self.text_scale))
        hh = (lh + fs + 25) if show_header else (lh + 15)
        return hh / float(height), 10 / float(height)

    def _category_of(self, path):
        """Category parts from the folder layout  base/YYYY/Month/dd-mm-YYYY/<category...>/file."""
        try:
            rel = os.path.relpath(os.path.dirname(path), self.base_root).replace("\\", "/").split("/")
            return [x for x in rel[3:] if x and x != "."]
        except Exception:
            return []

    def load_image_from_path(self, path):
        """Reopen a saved clip for editing: the baked-in logo/header band is cut away (the app
        re-draws the current one), and paper / page / position / size / category are put back
        in the metadata boxes."""
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            self.toast(f"Can't open: {e}", "error")
            return False
        parts = nab_recent.parse_clip_name(path) or {}
        cat_parts = self._category_of(path)
        trimmed = False
        try:
            reg = self._reg_get().get(os.path.normcase(os.path.abspath(path)))
            if reg:
                top, bot = reg
            else:
                paper = strip_emoji_prefix(parts.get("paper") or "") or self.paper_clean
                top, bot = self._header_fracs(img.width, img.height, self.header_allowed(cat_parts) if cat_parts else True, paper)
            y0, y1 = int(round(top * img.height)), img.height - int(round(bot * img.height))
            if 0 < y0 < y1 - 30 and y0 < img.height * 0.6:
                img = img.crop((0, y0, img.width, y1))
                trimmed = True
        except Exception as e:
            logging.debug(f"header trim: {e}")
        if parts.get("paper"):
            self.set_paper(parts["paper"])
        with self.doc.lock:
            self.doc.clear()
            self.doc.add(img, os.path.basename(path)[:40], checkpoint=False)
        self._preview_cache = None
        self.show_header = True
        cat = "/".join(cat_parts)
        cats = [cat] if cat and self._cat_exists(cat) else []
        pos = parts.get("pos", "")
        self.last_page = parts.get("page", "") or self.last_page
        f = {"page": parts.get("page", ""), "cols": pos, "size": parts.get("size", "")}
        self.set_draft(cats, " ".join(x for x in f.values() if x), "engine", f)
        self.hub.emit("clips", n=1, rev=self.doc.rev)
        self.status("EDIT MODE", "#F59E0B", 2000)
        return {"trimmed": trimmed}

    def _cat_exists(self, cat):
        top, _, sub = cat.partition("/")
        return top in self.categories and (not sub or sub in self.categories.get(top, []))

    def discard_clips(self, everything=False):
        """Throw away an accidentally grabbed clip at once (the last one, or all).
        Undoable with Ctrl+Z."""
        with self.doc.lock:
            if not self.doc.layers:
                return {"ok": False, "error": "No clip to delete."}
            if everything or len(self.doc.layers) == 1:
                n = len(self.doc.layers)
                self.doc.clear()
            else:
                n = 1
                self.doc.delete(self.doc.layers[-1].id)
            left = len(self.doc.layers)
        self._preview_cache = None
        self.hub.emit("clips", n=left, rev=self.doc.rev)
        self.status("CLIP DELETED", "#F59E0B", 1500)
        return {"ok": True, "removed": n, "left": left}

    def delete_from_history(self, index):
        try:
            del self.session_history[index]
        except Exception:
            pass

    # ───────────────────────────── preview ───────────────────────────────────
    def render_preview(self, target_h, page="", cols="", show_header=None, force=False):
        """JPEG bytes + layout meta for the UI.  target_h = wanted pixel height of
        the page (UI passes display height × zoom × devicePixelRatio)."""
        with self._preview_lock:
            doc = self.doc
            with doc.lock:
                rev = doc.rev
                vis = doc.visible_layers()
                full_w, full_h = doc.stack_size()
            paper = self.paper_clean
            sh = self.show_header if show_header is None else bool(show_header)
            htxt = self.header_text(page or self.last_page, cols or self.last_pos)
            # page height at k=1 (approx) to choose a scale
            logo_small = self.get_logo(paper, small=True)
            est_full_h = full_h + 160
            target_h = max(200, min(int(target_h or 1000), 4200))
            k = min(1.0, target_h / float(max(est_full_h, 1)))
            k = max(k, 0.05)
            k = round(k, 3)
            key = (rev, paper, sh, htxt, k, round(self.logo_scale, 3), round(self.text_scale, 3),
                   self.logo_path(paper))
            c = self._preview_cache
            if c and c["key"] == key and not force:
                return c
            with doc.lock:                       # hold the document lock only long enough to copy the layer list;
                frozen = doc.frozen_copy()       # the heavy resize/paste work then runs without blocking other calls
                for fl, l in zip(frozen.layers, [x for x in doc.layers if x.visible]):
                    fl.id = l.id
            canvas, hh, pw = frozen.compose(k, logo_small, self.logo_scale, self.text_scale, sh, htxt)
            layout = frozen.layout(k, hh, pw)
            jpg = nab_core.jpeg_bytes(canvas, 80 if k < 0.6 else 86)
            out = {"key": key, "jpeg": jpg, "w": canvas.width, "h": canvas.height, "k": k,
                   "header_h": hh, "layout": layout, "rev": rev, "full_w": full_w, "full_h": full_h, "free": doc.free,
                   "empty": not vis}
            self._preview_cache = out
            return out

    # ───────────────────────────── saving ────────────────────────────────────
    def _quality(self):
        return 95 if self.hd_mode else int(self.quality)

    def _dest_folder(self, parts):
        d = self.current_date
        return os.path.join(self.base_root, d.strftime("%Y"), d.strftime("%B"),
                            d.strftime("%d-%m-%Y"), *parts)

    def _unique_name(self, folder, paper, page, cols, size, date_s):
        """Same filename as always; if it already exists, _2, _3 … goes at the very end (after the date)
        (the old app asked, then did exactly this)."""
        n = 1
        while True:
            tail = "" if n == 1 else f"_{n}"
            fname = f"{_safe_name(paper)}, Page-{page}, Pos-{cols}, S-{size}, Date-{date_s}{tail}.jpg"
            if not os.path.exists(os.path.join(folder, fname)):
                return fname, cols, n > 1
            n += 1
            if n > 99:
                return fname, cols, True

    def save(self, categories, line):
        """Save the current clips into one or more categories.  Returns at once:
        the document is cleared immediately (so the next clip can be pasted) and
        the heavy work finishes on a worker thread; `saved` / `save_failed`
        events report back."""
        meta = nab_meta.parse(line)
        if not meta["ok"]:
            return {"ok": False, "error": (meta["errors"] or ["Enter page, columns and size, e.g.  B1 1-3 4x6"])[0],
                    "meta": _meta_json(meta)}
        cats = [c for c in categories if c]
        if not cats:
            return {"ok": False, "error": "Pick a category first (quick-save key or click one)."}
        with self.doc.lock:
            layers = [l for l in self.doc.layers if l.visible]
            if not layers:
                return {"ok": False, "error": "Nothing to save — paste a clip first."}
            snapshot = self.doc._snap()
            ctx = {
                "paper": self.paper_clean, "q": self._quality(), "logo_scale": self.logo_scale,
                "text_scale": self.text_scale, "show_header": self.show_header,
                "date": self.current_date, "page": meta["page"], "cols": meta["cols"], "size": meta["size"],
                "hd": self.hd_mode,
            }
            # compose from copies of the layer references so edits made after the
            # click can't leak into this save
            frozen = self.doc.frozen_copy()
            po = self.paper_opts()
            ctx["out_w"] = int(po.get("out_width") or self.extra_settings.get("out_width", 0) or 0)
            ctx["target_kb"] = int(po.get("target_kb") or self.extra_settings.get("fit_target_kb", 500) or 500)
            self.doc.clear()
            del self.doc._undo[:-5]
        self.last_page, self.last_pos, self.last_size = meta["page"], "", meta["size"]
        self.last_meta = {"page": meta["page"], "cols": meta["cols"], "size": meta["size"]}
        self.show_header = True
        self.set_draft([], f"{meta['page']} {meta['size']}", "engine",
                       {"page": meta["page"], "cols": "", "size": meta["size"]})
        if len(cats) > 1:
            self.hd_mode = False
        self._preview_cache = None
        self.hub.emit("clips", n=0, rev=self.doc.rev)
        self.status("SAVING…", "#F59E0B")
        sid = int(time.time() * 1000)
        threading.Thread(target=self._save_worker, args=(sid, frozen, cats, ctx, snapshot),
                         daemon=True, name="NAB-Save").start()
        return {"ok": True, "id": sid, "meta": _meta_json(meta)}

    def _save_worker(self, sid, frozen, cats, ctx, snapshot):
        saved, failed = [], []
        date = ctx["date"]
        date_s = date.strftime("%d-%m-%Y")
        paper = ctx["paper"]
        logo_full = self.get_logo(paper, small=False)
        if logo_full is None and paper:
            self.toast(f"⚠ No logo for {paper.upper()}", "warn", 4500)
        pages = {}            # header flag → composed canvas (cached per save)

        def canvas_for(sh):
            if sh not in pages:
                htxt = f"Page-{ctx['page']}, Pos-{ctx['cols']}, Date-{date_s}"
                cv, hh_, _pw = frozen.compose(1.0, logo_full, ctx["logo_scale"], ctx["text_scale"], sh, htxt)
                hh_of[sh] = (hh_, 10)
                ow = ctx.get("out_w") or 0
                if ow and 200 <= ow != cv.width:
                    cv = cv.resize((ow, max(1, int(round(cv.height * ow / float(cv.width))))), Image.Resampling.LANCZOS)
                pages[sh] = cv
            return pages[sh]

        enc = {}
        hh_of = {}

        def encoded_for(sh, canvas):
            if sh not in enc:
                if self.extra_settings.get("smart_fit", True) and not ctx["hd"]:
                    tk = int(ctx.get("target_kb") or self.extra_settings.get("fit_target_kb", 500) or 500)
                    bk = int(self.extra_settings.get("fit_big_kb", 780) or 780)
                    enc[sh] = nab_core.fit_jpeg(canvas, target_kb=tk, big_target_kb=max(bk, tk))
                else:
                    buf = io.BytesIO()
                    canvas.save(buf, "JPEG", quality=ctx["q"], optimize=True, subsampling=0)
                    enc[sh] = (buf.getvalue(), {"q": ctx["q"], "kb": len(buf.getvalue()) // 1024, "scaled": 1.0})
            return enc[sh]

        def one(cat):
            parts = cat.split("/")
            sh = ctx["show_header"] and self.header_allowed(parts)
            canvas = canvas_for(sh)
            folder = self._dest_folder(parts)
            os.makedirs(folder, exist_ok=True)
            fname, pos, dup = self._unique_name(folder, paper, ctx["page"], ctx["cols"], ctx["size"], date_s)
            path = os.path.join(folder, fname)
            data, info = encoded_for(sh, canvas)
            with open(path, "wb") as fh:
                fh.write(data)
            self._check_file_size(path)
            hh_, bt_ = hh_of.get(sh, (0, 10))
            self._reg_put([(path, hh_ / float(canvas.height), bt_ / float(canvas.height))])
            return {"path": path, "category": cat, "time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "dup": dup, "pos": pos, "name": fname,
                    "kb": int(len(data) / 1024), "q": info.get("q"), "scaled": info.get("scaled", 1.0)}

        # compose both header variants once, up-front, single-threaded (PIL canvas
        # objects are shared read-only by the per-category savers)
        try:
            for sh in {ctx["show_header"] and self.header_allowed(c.split("/")) for c in cats}:
                encoded_for(sh, canvas_for(sh))
        except Exception as e:
            logging.error(f"save compose: {e}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(cats))) as ex:
            futs = {ex.submit(one, c): c for c in cats}
            for f in concurrent.futures.as_completed(futs):
                try:
                    saved.append(f.result())
                except Exception as e:
                    logging.error(f"save {futs[f]}: {e}")
                    failed.append({"category": futs[f], "error": str(e)})
        frozen = None
        pages.clear()
        enc.clear()
        if saved:
            self.last_saved_path = os.path.dirname(saved[-1]["path"])
            self.last_active_date = datetime.datetime.now().strftime("%Y-%m-%d")
            for s in saved:
                self.session_history.append({"path": s["path"], "category": s["category"], "time": s["time"]})
            try:                                                   # optional auto-send to WhatsApp (off unless switched on)
                import nab_tool_wa
                if nab_tool_wa.auto_enabled():
                    import nab_tools
                    nab_tools.get("wa", self).auto_saved(saved)
            except Exception as e:
                logging.error(f"wa auto: {e}")
            threading.Thread(target=self._archive_saved, args=(list(saved),), daemon=True, name="NAB-Archive").start()
            self._last_save = {"id": sid, "files": [s["path"] for s in saved], "snapshot": snapshot}
            # memory: the undo window is short — let go of the heavy copies afterwards
            def _release(sid_=sid):
                if self._last_save and self._last_save.get("id") == sid_:
                    self._last_save = None
                import gc
                gc.collect()
            t = threading.Timer(180, _release)
            t.daemon = True
            t.start()
            try:
                self._check_goal()
            except Exception:
                pass
            self.status("COMPLETED!", "#10B981", 1800)
            self.hub.emit("saved", id=sid, files=saved, failed=failed, n=len(saved),
                          page=ctx["page"], cols=ctx["cols"], size=ctx["size"])
            self.hub.emit("recent_changed")
        if failed and not saved:
            # nothing written: give the clips back so no work is lost
            with self.doc.lock:
                self.doc._restore(snapshot)
                self.doc.touch()
            self._preview_cache = None
            self.status("SAVE FAILED", "#D32F2F", 3000)
            self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
            self.hub.emit("save_failed", id=sid, failed=failed)
        elif failed:
            self.hub.emit("save_partial", id=sid, failed=failed)

    def _archive_saved(self, saved):
        """Add the new clips to the archive and warn if one looks like a clip that is already saved."""
        try:
            import nab_archive
            import nab_accounts
            arch = nab_archive.get()
            who = nab_accounts.current()["name"] or ""
            same_save = [s["path"] for s in saved]
            for s in saved:
                arch.upsert(s["path"], self.base_root, user=who)
            for s in saved[:1]:
                d = arch.dup_of(s["path"], exclude=same_save)
                if d:
                    self.hub.emit("dup_warning", name=s["name"], other=d["name"], other_path=d["path"], date=d.get("date", ""))
        except Exception as e:
            logging.error(f"archive on save: {e}")

    def undo_save(self):
        """Toast 'Undo': delete what was just saved and bring the clips back."""
        ls = self._last_save
        if not ls:
            return {"ok": False, "error": "Nothing to undo."}
        removed = 0
        for p in ls["files"]:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    removed += 1
                try:
                    import nab_archive
                    nab_archive.get().remove(p)
                except Exception:
                    pass
            except Exception as e:
                logging.error(f"undo_save remove {p}: {e}")
        self.session_history = [h for h in self.session_history if h.get("path") not in set(ls["files"])]
        with self.doc.lock:
            have = list(self.doc.layers)
            self.doc._restore(ls["snapshot"])
            self.doc.layers = self.doc.layers + [l for l in have if all(l.id != x.id for x in self.doc.layers)]
            self.doc.touch()
        self._last_save = None
        self._preview_cache = None
        self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
        self.hub.emit("recent_changed")
        self.status("SAVE UNDONE", "#F59E0B", 1800)
        return {"ok": True, "removed": removed}

    # file size / goal (same behaviour as before, toast instead of a modal box)
    def _check_file_size(self, path):
        try:
            size_kb = os.path.getsize(path) / 1024
            lo = self.extra_settings.get("min_file_size_kb", 20)
            hi = self.extra_settings.get("max_file_size_kb", 5000)
            if size_kb < lo:
                self.toast(f"⚠ File is only {size_kb:.0f} KB (limit {lo} KB) — check the clip", "warn", 6000)
            elif size_kb > hi:
                self.toast(f"⚠ File is {size_kb:.0f} KB (limit {hi} KB) — consider lower quality", "warn", 6000)
        except Exception:
            pass

    # ───────────────────────────── recent saves ──────────────────────────────
    def recent(self, limit=60):
        out = []
        for i in range(len(self.session_history) - 1, -1, -1):
            h = self.session_history[i]
            p = h.get("path", "")
            if not os.path.exists(p):
                continue
            parts = nab_recent.parse_clip_name(p) or {}
            out.append({"i": i, "path": p, "category": h.get("category", ""), "time": h.get("time", ""),
                        "name": os.path.basename(p), **{k: parts.get(k, "") for k in ("paper", "page", "pos", "size")}})
            if len(out) >= limit:
                break
        return out

    def retag(self, index, paper=None, page=None, pos=None, size=None):
        try:
            h = self.session_history[int(index)]
        except Exception:
            return {"ok": False, "error": "Not found."}
        new_path, err = nab_recent.retag_file(h["path"], paper=strip_emoji_prefix(paper) if paper else None,
                                              page=page, pos=pos, size=size)
        if err:
            return {"ok": False, "error": err}
        self._reg_move(h["path"], new_path)
        h["path"] = new_path
        self.hub.emit("recent_changed")
        return {"ok": True, "path": new_path}

    def delete_saved(self, index):
        try:
            h = self.session_history[int(index)]
        except Exception:
            return {"ok": False, "error": "Not found."}
        try:
            os.remove(h["path"])
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self.delete_from_history(int(index))
        self.hub.emit("recent_changed")
        return {"ok": True}


def _meta_json(m):
    return {"page": m["page"], "cols": m["cols"], "size": m["size"], "ok": m["ok"],
            "errors": m["errors"], "missing": m.get("missing", []),
            "tokens": [{"t": t, "kind": k, "ok": ok, "msg": msg} for t, k, ok, msg in m["tokens"]]}


def parse_line_json(line):
    return _meta_json(nab_meta.parse(line))
