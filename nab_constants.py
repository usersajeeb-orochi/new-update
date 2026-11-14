# nab_constants.py — all shared constants, colours, fonts, paths
import os
import sys
import logging
import platform
import subprocess
import zlib
import re
import traceback
from tkinter import messagebox
from PIL import Image, ImageOps, ImageTk

# WebSocket server — sends live canvas previews to the Chrome extension
try:
    import asyncio
    import websockets as _ws_lib
    HAS_WS = True
except ImportError:
    HAS_WS = False

# NAB REST API (external file — not part of this split; optional feature)
try:
    from nab_rest_api import start_api_server as _start_api_server
    HAS_API = True
except ImportError:
    HAS_API = False

def global_exception_hook(exctype, value, tb):
    with open("error_log.txt", "w") as f:
        traceback.print_exception(exctype, value, tb, file=f)

sys.excepthook = global_exception_hook
logging.basicConfig(
    filename=os.path.join(os.path.expanduser("~"), "Documents", "nab_errors.log"),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Surgical crop/edit workspace (external file — not part of this split)
try:
    from surgical_tools import SurgicalWorkspace
except ImportError:
    messagebox.showerror("Error", "surgical_tools.py is missing from the directory.")
    sys.exit(1)

# Newspaper tracker (external file — not part of this split; optional feature)
try:
    from nab_tracker import NewspaperTracker
    _HAS_TRACKER = True
except ImportError:
    _HAS_TRACKER = False

# --- OPTIONAL DEPENDENCIES ---
try:
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:
    HAS_CV = False

try:
    from tkcalendar import Calendar
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

try:
    import win32clipboard
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

APP_VERSION = "3.0.63"
LOGO_FOLDER_NAME = "Logos"
BG_FILE_NAME = "canvas_bg.png"
BG_OPACITY = 0.4
NAB_WS_PORT = 6789

# Emoji + symbol Unicode blocks covering every prefix used in the default
# source list (flags, weather symbols, dingbats, misc pictographs...), plus
# the variation-selector (\uFE0F) and ZWJ (\u200D) that often ride along
# with them, and trailing whitespace so the separating space is consumed too.
_EMOJI_PREFIX_RE = re.compile(
    r"^[\U0001F000-\U0001FFFF\u2190-\u2BFF\uFE0F\u200D\s]+"
)

# --- THEME ---
C_BG = "#08080E"
C_SURFACE = "#0D0D14"
C_ACCENT = "#F59E0B"
C_ACCENT_HOVER = "#D97706"
C_TEXT_MAIN = "#F9FAFB"
C_TEXT_DIM = "#6B7280"
C_BORDER = "#2A2A2A"
C_DANGER = "#D32F2F"
C_SUCCESS = "#10B981"

# --- TYPOGRAPHY ---
F_HEADER = ("Impact", 24)
F_SUBHEAD = ("Impact", 14)
F_BODY = ("Impact", 14)
F_BTN = ("Segoe UI", 11, "bold")
F_TECH = ("Segoe UI", 10)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def create_dimmed_bg(base_img, width, height):
    try:
        base = base_img.copy().convert("RGBA")
        base = ImageOps.fit(base, (width, height), method=Image.Resampling.BILINEAR)
        overlay_alpha = int(255 * (1 - BG_OPACITY))
        overlay = Image.new('RGBA', base.size, (0, 0, 0, overlay_alpha))
        blended = Image.alpha_composite(base, overlay)
        return ImageTk.PhotoImage(blended.convert("RGB"))
    except Exception:
        return None

def compress_img(img):
    return {"size": img.size, "mode": img.mode, "data": zlib.compress(img.tobytes(), level=1)}

def decompress_img(c_img):
    return Image.frombytes(c_img["mode"], c_img["size"], zlib.decompress(c_img["data"]))

# FIX 6: Cross-platform folder opener
def strip_emoji_prefix(name):
    """Paper names in the SOURCE dropdown are displayed as "EMOJI Name"
    for readability (e.g. "📰 New Age", from the default list in
    NewsClipper.load_sources). That emoji must never end up in a saved
    filename or a Logos/*.png lookup, so this strips a LEADING run of
    emoji/symbol characters (and any space right after them) and leaves
    everything else untouched.

    Used to be name.split(" ", 1)[-1], which assumed every single entry
    is exactly one space-separated emoji token followed by the name. That
    silently broke for any entry with NO emoji at all — which is exactly
    what you get from Source Manager -> "Upload Logo" (it inserts the
    plain typed name, no emoji prefix). "New Age" was read as an emoji
    token "New" plus a name "Age", so the file saved as "Age, Page-..."
    and the logo lookup went looking for a nonexistent "Age.png" instead
    of the "New Age.png" that was actually sitting in the Logos folder.

    This version only strips characters that are actually in Unicode's
    emoji/symbol ranges, so a manually-typed name with no emoji (like
    "New Age") is returned completely unchanged.
    """
    if not name:
        return name
    stripped = _EMOJI_PREFIX_RE.sub("", name, count=1)
    return stripped if stripped else name.strip()


def open_folder(path):
    """Open a folder in the OS file browser. Returns True on success, False otherwise."""
    if not path:
        logging.error("open_folder: empty path")
        return False
    if not os.path.exists(path):
        logging.error(f"open_folder: path does not exist: {path}")
        return False
    system = platform.system()
    try:
        if system == "Windows":
            # BUG FIX: os.startfile is the correct, locale-safe way to open a folder
            # in Explorer on Windows. The previous Popen(f'explorer "{path}"') approach
            # built a single shell-style command string, which is fragile with
            # unicode/foreign characters in paths (common here since paper and
            # category names are frequently Bengali/non-ASCII), and gave no
            # reliable way to detect failure.
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except AttributeError:
                # os.startfile only exists on Windows; guarded in case this code
                # path is ever hit on a non-Windows interpreter.
                subprocess.Popen(["explorer", path])
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        logging.error(f"open_folder: {e}")
        return False

# ─────────────────────────────────────────────
# TELEGRAM CONFIG
# ─────────────────────────────────────────────
# LOCAL BOT  — handles auth, lock, screenshot, pause/resume, restart
# CLOUD BOT  — handles file access, uploads, Drive, group (separate token)
# Both can run simultaneously with ZERO conflict because they use different tokens.
# ─────────────────────────────────────────────
