"""
Image OCR Finder
-----------------
A small Tkinter desktop app that indexes images in one or more folders,
extracts any text found inside them using OCR (Tesseract), and lets you
search that text by keyword to quickly locate the image files again.

REQUIREMENTS (install once):
    pip install pytesseract pillow

You also need the actual Tesseract-OCR engine installed on your machine
(pytesseract is just a Python wrapper around it):
    Windows: https://github.com/UB-Mannheim/tesseract/wiki  (installer)
             default install path is usually:
             C:\\Program Files\\Tesseract-OCR\\tesseract.exe
             During install, tick "Bengali" under Additional language data
             so the eng+ben OCR mode works on Bengali newspaper text.
    Linux:   sudo apt install tesseract-ocr tesseract-ocr-ben
    After installing, set TESSERACT_CMD below if it isn't auto-detected.

USAGE:
    python image_ocr_finder.py

    1. Click "Add Folder" to pick a folder to index (subfolders included).
    2. Pick an OCR language from the dropdown (default eng+ben — covers
       English and Bengali newspaper clippings in one pass).
    3. Click "Rebuild / Update Index" to OCR any new or changed images.
       (Already-indexed, unchanged files are skipped on later runs;
       switching OCR language re-OCRs everything on the next run.)
    4. Type keyword(s), separated by commas. By default any one keyword
       matching is enough — tick "Match ALL keywords" to require every
       one to appear in the same image.
    5. Click Search, then "Copy Results To Folder..." to copy the
       matches (or just your selected rows) into a destination folder.
    6. Double-click a result to open the file, or right-click to reveal
       it in the file manager.

The index (folder list + extracted text per file) is cached to
"image_ocr_index.json" next to this script, so you don't have to
re-OCR everything every time you open the app.
"""

import os
import sys
import re
import json
import time
import queue
import threading
import concurrent.futures
# Windows are sized through nab_ui_scale.fit() instead of hardcoded
# pixels — see nab_ui_scale.py for why (small monitors / DPI).
import nab_ui_scale
import subprocess
import shutil
import calendar
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageOps, ImageTk, ImageDraw
import pytesseract

# ---------------------------------------------------------------------------
# Theme — modern "bubble" palette + a real rounded-corner button widget
# ---------------------------------------------------------------------------

class Palette:
    BG = "#F3F2FA"          # app background — soft lavender-gray
    CARD = "#FFFFFF"        # toolbar/panel background
    BORDER = "#E7E4F5"
    TEXT = "#211F35"
    TEXT_MUTED = "#7A7791"
    PRIMARY = "#6C5CE7"       # vivid indigo — main actions
    PRIMARY_HOVER = "#5A48E0"
    PRIMARY_PRESS = "#4C3AD1"
    ACCENT = "#00C2A8"        # teal — secondary accent (trend/search highlights)
    ACCENT_HOVER = "#00AB93"
    BUBBLE = "#EDEBFC"        # soft lavender — secondary/neutral bubble buttons
    BUBBLE_HOVER = "#E1DCFA"
    BUBBLE_PRESS = "#D3CBF7"
    DANGER = "#FF5C7C"        # Stop button
    DANGER_HOVER = "#F03F63"
    DISABLED = "#E4E3EE"
    DISABLED_TEXT = "#ADAABF"
    HIGHLIGHT = "#FFE066"     # matched-text highlight color
    FONT = ("Segoe UI", 10)
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_HEADER = ("Segoe UI", 13, "bold")


class RoundedButton(tk.Canvas):
    """A real pill/bubble-shaped button (rounded corners aren't possible
    with stock ttk widgets — this draws one on a Canvas instead)."""

    def __init__(self, parent, text, command=None, *, bg=None, fg="#FFFFFF",
                 hover_bg=None, press_bg=None, font=None, padx=16, pady=8,
                 radius=16, parent_bg=None):
        bg = bg or Palette.PRIMARY
        hover_bg = hover_bg or bg
        press_bg = press_bg or bg
        font = font or Palette.FONT

        probe = tk.Label(parent, text=text, font=font)
        probe.update_idletasks()
        text_w = max(probe.winfo_reqwidth(), 10)
        text_h = max(probe.winfo_reqheight(), 10)
        probe.destroy()

        width = text_w + 2 * padx
        height = text_h + 2 * pady
        resolved_bg = parent_bg
        if resolved_bg is None:
            try:
                resolved_bg = parent.cget("bg")
            except Exception:
                resolved_bg = Palette.CARD

        super().__init__(parent, width=width, height=height, highlightthickness=0,
                          bd=0, bg=resolved_bg)

        self._text, self._font = text, font
        self._bg, self._hover_bg, self._press_bg = bg, hover_bg, press_bg
        self._fg = fg
        self._btn_w, self._btn_h, self._radius = width, height, radius
        self._command = command
        self._enabled = True

        self._draw("normal")
        self.bind("<Enter>", lambda e: self._enabled and self._draw("hover"))
        self.bind("<Leave>", lambda e: self._enabled and self._draw("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._enabled and self._draw("press"))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, **kw)

    def _draw(self, state):
        self.delete("all")
        if not self._enabled:
            fill, fg = Palette.DISABLED, Palette.DISABLED_TEXT
        elif state == "press":
            fill, fg = self._press_bg, self._fg
        elif state == "hover":
            fill, fg = self._hover_bg, self._fg
        else:
            fill, fg = self._bg, self._fg
        self._round_rect(1, 1, self._btn_w - 1, self._btn_h - 1, self._radius, fill=fill, outline="")
        self.create_text(self._btn_w / 2, self._btn_h / 2, text=self._text, fill=fg, font=self._font)
        self.configure(cursor="hand2" if self._enabled else "arrow")

    def _on_release(self, _event):
        if self._enabled:
            self._draw("hover")
            if self._command:
                self._command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        self._draw("normal")



# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    # Running bundled inside a frozen EXE (e.g. NAB.exe): __file__ would
    # resolve into PyInstaller's temporary _MEIxxxx extraction folder,
    # which is recreated fresh and deleted on every run — using it here
    # would silently lose the OCR index/tags cache every single launch.
    # Use the real EXE's folder instead so the cache actually persists.
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(SCRIPT_DIR, "image_ocr_index.json")
TAGS_FILE = os.path.join(SCRIPT_DIR, "image_ocr_tags.json")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}
DATE_PATTERN = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

# If Tesseract isn't on PATH, uncomment and fix this for your machine:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

WINDOWS_DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.name == "nt" and os.path.exists(WINDOWS_DEFAULT_TESSERACT):
    pytesseract.pytesseract.tesseract_cmd = WINDOWS_DEFAULT_TESSERACT

# OCR language(s). Tesseract language codes, joined with "+" to run multiple
# scripts in one pass. "eng+ben" covers English + Bengali newspaper text.
# Requires the matching traineddata file(s) to be installed
# (Windows installer lets you tick extra languages; Linux: apt install
# tesseract-ocr-ben). Changed value only takes effect on the next
# "Rebuild / Update Index" run.
OCR_LANGUAGES = ["eng", "ben", "eng+ben"]
DEFAULT_OCR_LANGUAGE = "eng+ben"

# How many images to OCR at once. Each OCR call shells out to a separate
# tesseract.exe process, so this genuinely runs in parallel across CPU
# cores (not limited by Python's GIL). Capped at 8 to avoid saturating
# disk I/O / memory on a typical machine; lower it if your PC struggles.
# How many images to OCR at once, using separate PROCESSES (not threads).
# Image preprocessing (resize/contrast) is CPU-bound Python code that would
# otherwise be serialized by the GIL even across threads; real processes
# let that work — and the tesseract.exe subprocess each one launches — run
# truly in parallel across all your CPU cores.
OCR_WORKERS = max(1, min(16, os.cpu_count() or 4))

# Bump this whenever the cached record format changes, to force existing
# index entries to be re-OCR'd even though the underlying image file
# hasn't changed (e.g. we started storing word bounding boxes).
CACHE_FORMAT_VERSION = "v2"


def check_tesseract_available():
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _normalize(text):
    """Lowercase, collapse all whitespace/newlines to single spaces, and
    drop punctuation OCR commonly mangles, so search isn't defeated by
    line breaks or stray symbols."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)  # drop punctuation
    text = re.sub(r"\s+", " ", text).strip()  # collapse whitespace/newlines
    return text


def _extract_date_from_path(path):
    """Return a datetime for the last DD-MM-YYYY found in the path (NAB's
    day-folder and filename both use this), or None if no date is present."""
    matches = DATE_PATTERN.findall(path)
    if not matches:
        return None
    day, month, year = matches[-1]  # rightmost match = deepest folder/filename
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Index (load/save + build)
# ---------------------------------------------------------------------------

def load_index():
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"folders": [], "files": {}}


def save_index(index):
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_FILE)


def load_tags():
    """User-defined {tag_name: [trigger_keyword, ...]} dictionary used to
    auto-tag clippings by topic/entity (e.g. "Telecom": ["Grameenphone",
    "Robi", "BTRC"]). Empty by default — you build your own taxonomy via
    Manage Tags."""
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_tags(tags):
    tmp = TAGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TAGS_FILE)


def compute_tags_for_text(text, tag_dict):
    """Which tag(s) apply to this OCR'd text, based on a simple
    case-insensitive substring check against each tag's trigger keywords."""
    if not text or not tag_dict:
        return []
    haystack = text.lower()
    hits = []
    for tag_name, keywords in tag_dict.items():
        for kw in keywords:
            kw = (kw or "").strip().lower()
            if kw and kw in haystack:
                hits.append(tag_name)
                break
    return hits


def _levenshtein(a, b):
    """Edit distance between two strings. Small/pure-Python but fine at
    word length (a handful of characters) which is all we ever call it on."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _fuzzy_word_hit(word, target):
    """True if `word` is close enough to `target` to count as an OCR typo
    of it (e.g. 'Grarneenphone' vs 'Grameenphone'). Tolerance scales with
    word length so short words still need a near-exact match."""
    if not word or not target:
        return False
    if len(word) < 3 or len(target) < 3:
        return word == target  # too short for fuzzy matching to be meaningful
    dist = _levenshtein(word, target)
    tolerance = 1 if len(target) <= 5 else (2 if len(target) <= 9 else 3)
    return dist <= tolerance


def iter_image_files(folders):
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for root, _dirs, files in os.walk(folder):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTS:
                    yield os.path.join(root, name)


def _preprocess_for_ocr(img):
    """Grayscale + upscale + autocontrast. Newspaper clippings are often
    small/low-contrast scans/screenshots; this alone fixes a lot of
    misreads without needing OpenCV. Returns (processed_img, scale) where
    scale = processed_size / original_size, needed to map OCR word boxes
    back onto the original, unmodified image later."""
    img = img.convert("L")  # grayscale
    w, h = img.size
    scale = 1.0
    # Tesseract does much better on text that's reasonably large.
    if max(w, h) < 2000:
        scale = 2000 / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    img = ImageOps.autocontrast(img)
    return img, scale


def _words_from_data(data):
    """Turn pytesseract's image_to_data dict into (text, words) where
    words is a list of {text, left, top, width, height} for every
    recognized word with actual content."""
    words = []
    lines_out = []  # list of list-of-word-text, grouped by (block, par, line)
    current_key = None
    current_line = []
    n = len(data.get("text", []))
    for i in range(n):
        raw = data["text"][i]
        word_text = raw.strip() if raw else ""
        try:
            conf = float(data["conf"][i])
        except (ValueError, KeyError, IndexError):
            conf = -1
        if not word_text or conf < 0:
            continue
        words.append({
            "text": word_text,
            "left": data["left"][i],
            "top": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
        })
        key = (data.get("block_num", [0] * n)[i], data.get("par_num", [0] * n)[i], data.get("line_num", [0] * n)[i])
        if key != current_key:
            if current_line:
                lines_out.append(current_line)
            current_line = [word_text]
            current_key = key
        else:
            current_line.append(word_text)
    if current_line:
        lines_out.append(current_line)
    text = "\n".join(" ".join(line) for line in lines_out)
    return text, words


def ocr_file(path, lang=DEFAULT_OCR_LANGUAGE, thorough=False):
    """Returns (text, words, scale). words/scale are used to draw highlight
    boxes on the original image later; text/positions are in the
    *preprocessed* (possibly upscaled) image's coordinate space — divide
    by scale to map back to the original file's pixel coordinates.

    By default only ONE Tesseract pass runs (psm 6 — "single uniform
    block", which is what a single newspaper clipping/article almost
    always is). This is the single biggest lever on scan speed: a second
    full pass at psm 3 used to run automatically whenever the first
    pass found 20 characters or fewer, which is a low bar most real
    clippings clear anyway, but any image that DIDN'T clear it silently
    paid for two full OCR passes. Pass thorough=True (wired to the
    "Thorough OCR" checkbox) to re-enable that second pass for tricky
    multi-column layouts."""
    try:
        with Image.open(path) as raw:
            img, scale = _preprocess_for_ocr(raw)
    except Exception as e:
        return f"[OCR ERROR opening file: {e}]", [], 1.0

    psm_attempts = ("6", "3") if thorough else ("6",)
    best_text, best_words = "", []
    for psm in psm_attempts:
        try:
            # oem 1 = LSTM-only. oem 3 ("default/combined") can silently
            # also run Tesseract's older legacy engine on some installs
            # (notably Windows installers that bundle full/combined
            # trained data rather than the "fast" LSTM-only data), roughly
            # doubling per-image cost for no accuracy benefit on printed
            # newspaper text. Pinning oem 1 guarantees only the fast path runs.
            config = f"--oem 1 --psm {psm}"
            data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
            text, words = _words_from_data(data)
        except Exception as e:
            return f"[OCR ERROR: {e}]", [], 1.0
        if len(text.strip()) > len(best_text.strip()):
            best_text, best_words = text, words
        if not thorough and len(best_text.strip()) > 20:
            break  # fast mode: good enough, don't bother with a second pass

    return best_text, best_words, scale



# ---------------------------------------------------------------------------
# Background indexing worker
# ---------------------------------------------------------------------------

class IndexWorker(threading.Thread):
    """Runs in a background thread so the GUI never freezes."""

    def __init__(self, index, progress_queue, lang=DEFAULT_OCR_LANGUAGE, thorough=False, workers=None):
        super().__init__(daemon=True)
        self.index = index
        self.q = progress_queue
        self.lang = lang
        self.thorough = thorough
        self.workers = workers or OCR_WORKERS
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            self._run()
        except Exception as e:
            import traceback
            self.q.put(("error", str(e), traceback.format_exc()))

    def _run(self):
        folders = self.index["folders"]
        files_meta = self.index["files"]

        if not check_tesseract_available():
            self.q.put(("error",
                        "Tesseract OCR engine not found (pytesseract.get_tesseract_version() failed).",
                        "Install Tesseract-OCR and/or set pytesseract.pytesseract.tesseract_cmd "
                        "to its .exe path near the top of this script."))
            return

        all_paths = list(iter_image_files(folders))
        total = len(all_paths)
        self.q.put(("total", total))

        if total == 0:
            self.q.put(("error",
                        "No image files found in the selected folder(s).",
                        f"Folders checked: {folders}\n"
                        f"Recognized extensions: {sorted(IMAGE_EXTS)}\n"
                        "Check the folder actually contains files with one of these "
                        "extensions (case-insensitive) and isn't empty/wrong path."))
            return

        # Drop entries for files that no longer exist.
        existing = set(all_paths)
        for old_path in list(files_meta.keys()):
            if old_path not in existing:
                del files_meta[old_path]

        done = 0
        ocr_error_count = 0
        pending = []  # (path, sig) still needing OCR
        for path in all_paths:
            if self._stop_event.is_set():
                break
            try:
                stat = os.stat(path)
                mode_tag = "thorough" if self.thorough else "fast"
                sig = f"{stat.st_size}-{int(stat.st_mtime)}-{self.lang}-{mode_tag}-{CACHE_FORMAT_VERSION}"
            except OSError:
                continue

            cached = files_meta.get(path)
            if cached and cached.get("sig") == sig:
                done += 1
                self.q.put(("progress", done, total, path, False))
                continue
            pending.append((path, sig))

        ocr_start = time.time()
        if pending and not self._stop_event.is_set():
            workers = max(1, min(64, self.workers))
            self.q.put(("workers", workers, len(pending)))
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(ocr_file, path, self.lang, self.thorough): (path, sig)
                    for path, sig in pending
                }
                for future in concurrent.futures.as_completed(future_map):
                    path, sig = future_map[future]
                    try:
                        text, words, scale = future.result()
                    except Exception as e:
                        text, words, scale = f"[OCR ERROR: {e}]", [], 1.0
                    if text.startswith("[OCR ERROR"):
                        ocr_error_count += 1
                    files_meta[path] = {"sig": sig, "text": text, "words": words, "scale": scale}
                    done += 1
                    self.q.put(("progress", done, total, path, True))

                    if self._stop_event.is_set():
                        # Let already-running OCR calls finish (they're
                        # separate processes we can't cleanly interrupt),
                        # but drop everything still waiting in the pool.
                        for f in future_map:
                            f.cancel()
                        break
        ocr_elapsed = time.time() - ocr_start

        self.q.put(("done", done, total, ocr_error_count, ocr_elapsed, len(pending)))


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ImageOCRFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image OCR Finder [build 2026-07-23a]")
        nab_ui_scale.fit(self.root, 980, 920, min_w=607, min_h=570)

        self.index = load_index()
        self.tags = load_tags()
        self.progress_queue = queue.Queue()
        self.worker = None
        self._result_keywords = {}
        self._last_whole_word = False
        self._last_case_sensitive = False
        self._last_fuzzy = False

        self._setup_style()
        self._build_ui()
        self._refresh_folder_list()
        self._poll_queue()

        if not check_tesseract_available():
            messagebox.showwarning(
                "Tesseract not found",
                "The Tesseract OCR engine wasn't found on this system.\n\n"
                "Install it (see the top of image_ocr_finder.py for a link), "
                "then set TESSERACT_CMD in the script if needed, and restart.",
            )

    # -- UI construction ----------------------------------------------------

    def _setup_style(self):
        P = Palette
        self.root.configure(bg=P.BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=P.BG, foreground=P.TEXT, font=P.FONT)
        style.configure("TFrame", background=P.BG)
        style.configure("Card.TFrame", background=P.CARD)
        style.configure("TLabel", background=P.BG, foreground=P.TEXT, font=P.FONT)
        style.configure("Card.TLabel", background=P.CARD, foreground=P.TEXT, font=P.FONT)
        style.configure("Muted.TLabel", background=P.BG, foreground=P.TEXT_MUTED, font=P.FONT)
        style.configure("CardMuted.TLabel", background=P.CARD, foreground=P.TEXT_MUTED, font=P.FONT)
        style.configure("Header.TLabel", background=P.BG, foreground=P.TEXT, font=P.FONT_HEADER)

        style.configure("TCheckbutton", background=P.CARD, foreground=P.TEXT, font=P.FONT)
        style.map("TCheckbutton", background=[("active", P.CARD)])
        style.configure("TRadiobutton", background=P.CARD, foreground=P.TEXT, font=P.FONT)

        style.configure("TEntry", fieldbackground="#FFFFFF", foreground=P.TEXT,
                         bordercolor=P.BORDER, lightcolor=P.BORDER, darkcolor=P.BORDER,
                         padding=6, relief="flat")
        style.map("TEntry", bordercolor=[("focus", P.PRIMARY)])
        style.configure("TCombobox", fieldbackground="#FFFFFF", foreground=P.TEXT,
                         bordercolor=P.BORDER, arrowcolor=P.PRIMARY, padding=4)
        style.configure("TSpinbox", fieldbackground="#FFFFFF", foreground=P.TEXT,
                         bordercolor=P.BORDER, arrowcolor=P.PRIMARY, padding=4)

        style.configure("TProgressbar", background=P.PRIMARY, troughcolor=P.BUBBLE,
                         bordercolor=P.BUBBLE, lightcolor=P.PRIMARY, darkcolor=P.PRIMARY)

        style.configure("Vertical.TScrollbar", background=P.BUBBLE, troughcolor=P.BG,
                         bordercolor=P.BG, arrowcolor=P.PRIMARY)
        style.configure("Horizontal.TScrollbar", background=P.BUBBLE, troughcolor=P.BG,
                         bordercolor=P.BG, arrowcolor=P.PRIMARY)

        style.configure("Treeview", background="#FFFFFF", fieldbackground="#FFFFFF",
                         foreground=P.TEXT, font=P.FONT, borderwidth=0, rowheight=30)
        style.configure("Thumbs.Treeview", rowheight=68, background="#FFFFFF",
                         fieldbackground="#FFFFFF", foreground=P.TEXT, font=P.FONT, borderwidth=0)
        style.configure("Treeview.Heading", background=P.BUBBLE, foreground=P.TEXT,
                         font=P.FONT_BOLD, relief="flat", borderwidth=0)
        style.map("Treeview.Heading", background=[("active", P.BUBBLE_HOVER)])
        style.map(
            "Thumbs.Treeview",
            background=[("selected", P.PRIMARY)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.map(
            "Treeview",
            background=[("selected", P.PRIMARY)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # drop default border box

        style.configure("TLabelframe", background=P.CARD, bordercolor=P.BORDER, relief="flat")
        style.configure("TLabelframe.Label", background=P.CARD, foreground=P.TEXT, font=P.FONT_BOLD)

    def _card(self, parent, **pack_opts):
        """A flat 'card' panel — the closest stock Tk gets to the soft
        rounded panels of a modern bubble UI without a full custom canvas
        background for every single frame."""
        outer = tk.Frame(parent, bg=Palette.BG)
        outer.pack(side=tk.TOP, fill=tk.X, **pack_opts)
        card = tk.Frame(outer, bg=Palette.CARD, highlightbackground=Palette.BORDER,
                         highlightthickness=1, bd=0)
        card.pack(fill=tk.X, padx=10, pady=4, ipady=6)
        return card

    def _build_ui(self):
        P = Palette
        top = self._card(self.root, pady=(10, 0))

        def tbtn(parent, text, command, kind="bubble", **pad):
            colors = {
                "primary": dict(bg=P.PRIMARY, hover_bg=P.PRIMARY_HOVER, press_bg=P.PRIMARY_PRESS, fg="#FFFFFF"),
                "accent": dict(bg=P.ACCENT, hover_bg=P.ACCENT_HOVER, press_bg=P.ACCENT_HOVER, fg="#FFFFFF"),
                "danger": dict(bg=P.DANGER, hover_bg=P.DANGER_HOVER, press_bg=P.DANGER_HOVER, fg="#FFFFFF"),
                "bubble": dict(bg=P.BUBBLE, hover_bg=P.BUBBLE_HOVER, press_bg=P.BUBBLE_PRESS, fg=P.TEXT),
            }[kind]
            b = RoundedButton(parent, text, command, parent_bg=P.CARD, **colors)
            b.pack(side=tk.LEFT, **pad)
            return b

        tbtn(top, "Add Folder", self.add_folder, "bubble", padx=(10, 4))
        tbtn(top, "Add Date Range...", self.add_date_range_folders, "bubble", padx=4)
        tbtn(top, "Remove Folder", self.remove_folder, "bubble", padx=4)
        tbtn(top, "Rebuild / Update Index", self.start_indexing, "primary", padx=4)
        tbtn(top, "Stop", self.stop_indexing, "danger", padx=4)
        tbtn(top, "Show Index...", self.show_index, "bubble", padx=4)

        ttk.Label(top, text="OCR language:", style="Card.TLabel").pack(side=tk.LEFT, padx=(14, 0))
        self.lang_var = tk.StringVar(value=DEFAULT_OCR_LANGUAGE)
        lang_combo = ttk.Combobox(
            top, textvariable=self.lang_var, values=OCR_LANGUAGES, width=8, state="readonly"
        )
        lang_combo.pack(side=tk.LEFT, padx=(4, 10))

        self.folder_list = tk.Listbox(
            top, height=3, width=50, selectmode=tk.EXTENDED,
            bg="#FFFFFF", fg=P.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=P.BORDER, highlightcolor=P.PRIMARY,
            selectbackground=P.PRIMARY, selectforeground="#FFFFFF",
        )
        self.folder_list.pack(side=tk.LEFT, padx=(4, 10), fill=tk.X, expand=True)

        top2 = self._card(self.root)

        ttk.Label(top2, text="OCR workers:", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self.workers_var = tk.IntVar(value=OCR_WORKERS)
        ttk.Spinbox(
            top2, from_=1, to=64, textvariable=self.workers_var, width=4
        ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Label(
            top2, text=f"(detected {os.cpu_count() or '?'} CPU cores — raise this if Task Manager "
                        f"shows spare capacity while indexing)",
            style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(6, 0))

        self.thorough_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top2, text="Thorough OCR (try 2 layouts per image — slower, helps multi-column pages)",
            variable=self.thorough_var,
        ).pack(side=tk.LEFT, padx=(18, 0))

        tbtn(top2, "Manage Tags...", self.manage_tags, "bubble", padx=(18, 4))
        tbtn(top2, "Find Duplicates...", self.find_duplicates, "bubble", padx=4)

        search_frame = self._card(self.root)

        ttk.Label(search_frame, text="Keyword(s):", style="Card.TLabel").pack(side=tk.LEFT, padx=(10, 0))
        self.search_var = tk.StringVar()
        entry = tk.Entry(
            search_frame, textvariable=self.search_var, font=P.FONT, relief="flat",
            highlightthickness=1, highlightbackground=P.BORDER, highlightcolor=P.PRIMARY,
            bg="#FFFFFF", fg=P.TEXT, insertbackground=P.TEXT,
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, ipady=4)
        entry.bind("<Return>", lambda e: self.search())
        tbtn(search_frame, "Search", self.search, "primary", padx=4)
        tbtn(search_frame, "Show Trend...", self.show_trend, "accent", padx=4)
        tbtn(search_frame, "Copy Results To Folder...", self.copy_results, "bubble", padx=(4, 10))

        hint = ttk.Label(
            self.root,
            text="Tip: separate multiple keywords with commas — matches images containing ANY of them "
                 "(tick 'Match ALL keywords' below to require every one in the same image).",
            padding=(14, 4),
            style="Muted.TLabel",
        )
        hint.pack(side=tk.TOP, fill=tk.X)

        filters_frame = self._card(self.root, pady=(0, 4))

        self.whole_word_var = tk.BooleanVar(value=False)
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.folder_scope_var = tk.BooleanVar(value=False)
        self.match_all_var = tk.BooleanVar(value=False)
        self.fuzzy_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(filters_frame, text="Whole word", variable=self.whole_word_var).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Checkbutton(filters_frame, text="Case sensitive", variable=self.case_sensitive_var).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Checkbutton(
            filters_frame, text="Match ALL keywords (AND)", variable=self.match_all_var
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Checkbutton(
            filters_frame, text="Fuzzy (tolerate OCR typos)", variable=self.fuzzy_var
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Checkbutton(
            filters_frame, text="Only selected folder(s) above", variable=self.folder_scope_var
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(filters_frame, text="Date from:", style="Card.TLabel").pack(side=tk.LEFT, padx=(16, 0))
        self.date_from_var = tk.StringVar()
        ttk.Entry(filters_frame, textvariable=self.date_from_var, width=12).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(filters_frame, text="to:", style="Card.TLabel").pack(side=tk.LEFT, padx=(8, 0))
        self.date_to_var = tk.StringVar()
        ttk.Entry(filters_frame, textvariable=self.date_to_var, width=12).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(filters_frame, text="(DD-MM-YYYY, optional)", style="CardMuted.TLabel").pack(
            side=tk.LEFT, padx=(6, 10)
        )

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self.root, textvariable=self.status_var, padding=(14, 4), style="Muted.TLabel").pack(
            side=tk.TOP, fill=tk.X
        )

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))

        preview_frame = ttk.LabelFrame(self.root, text="Preview — why this image matched (select a result below)")
        preview_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))

        preview_inner = tk.Frame(preview_frame, bg=P.CARD)
        preview_inner.pack(fill=tk.BOTH, expand=True)

        self.preview_text = tk.Text(
            preview_inner, height=6, wrap="word", state=tk.DISABLED,
            font=("Segoe UI", 10), bg="#FFFFFF", fg=P.TEXT, relief="flat",
            highlightthickness=1, highlightbackground=P.BORDER,
        )
        preview_scroll = ttk.Scrollbar(preview_inner, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(1, 0), pady=1)
        preview_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.preview_text.tag_configure("hl", background=P.HIGHLIGHT, foreground="#000000")

        columns = ("file", "path", "tags", "snippet")
        self.tree = ttk.Treeview(
            self.root, columns=columns, show="tree headings", style="Thumbs.Treeview"
        )
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=68, stretch=False, anchor="center")
        self.tree.heading("file", text="File")
        self.tree.heading("path", text="Folder")
        self.tree.heading("tags", text="Tags")
        self.tree.heading("snippet", text="Matched text")
        self.tree.column("file", width=170)
        self.tree.column("path", width=220)
        self.tree.column("tags", width=110)
        self.tree.column("snippet", width=380)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.tree.tag_configure("odd", background="#FAF9FF")
        self.tree.tag_configure("even", background="#FFFFFF")

        self._thumb_refs = []  # keep PhotoImage refs alive; cleared each search

        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_result_select)

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Open file", command=self.open_selected)
        self.context_menu.add_command(label="Show in file manager", command=self.reveal_selected)

    # -- Folder management ---------------------------------------------------

    def _refresh_folder_list(self):
        self.folder_list.delete(0, tk.END)
        for f in self.index["folders"]:
            self.folder_list.insert(tk.END, f)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder to index")
        if folder and folder not in self.index["folders"]:
            self.index["folders"].append(folder)
            save_index(self.index)
            self._refresh_folder_list()

    def remove_folder(self):
        sel = self.folder_list.curselection()
        if not sel:
            return
        folder = self.folder_list.get(sel[0])
        self.index["folders"].remove(folder)
        save_index(self.index)
        self._refresh_folder_list()

    def add_date_range_folders(self):
        """Add every day-folder between two dates, assuming NAB's layout:
        <root>/<YYYY>/<Month name>/<DD-MM-YYYY>/  (e.g. .../2026/July/21-07-2026)
        """
        root_folder = filedialog.askdirectory(
            title="Select the root 'Monitoring' folder (the one containing year folders)"
        )
        if not root_folder:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Date Range")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="From (DD-MM-YYYY):").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        from_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=from_var, width=15).grid(row=0, column=1, padx=8, pady=8)

        ttk.Label(dialog, text="To (DD-MM-YYYY):").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        to_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=to_var, width=15).grid(row=1, column=1, padx=8, pady=8)

        today_str = datetime.now().strftime("%d-%m-%Y")
        from_var.set(today_str)
        to_var.set(today_str)

        result = {}

        def on_add():
            try:
                start = datetime.strptime(from_var.get().strip(), "%d-%m-%Y")
                end = datetime.strptime(to_var.get().strip(), "%d-%m-%Y")
            except ValueError:
                messagebox.showerror("Invalid date", "Please use DD-MM-YYYY, e.g. 21-07-2026.", parent=dialog)
                return
            if end < start:
                start, end = end, start
            result["start"] = start
            result["end"] = end
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text="Add", command=on_add).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

        self.root.wait_window(dialog)

        if "start" not in result:
            return

        start, end = result["start"], result["end"]
        added, missing = [], []
        current = start
        while current <= end:
            year = str(current.year)
            month_name = calendar.month_name[current.month]  # e.g. "July"
            day_folder = current.strftime("%d-%m-%Y")
            candidate = os.path.join(root_folder, year, month_name, day_folder)
            if os.path.isdir(candidate):
                if candidate not in self.index["folders"]:
                    self.index["folders"].append(candidate)
                added.append(candidate)
            else:
                missing.append(candidate)
            current += timedelta(days=1)

        save_index(self.index)
        self._refresh_folder_list()

        msg = f"Added {len(added)} date folder(s)."
        if missing:
            msg += f"\n\n{len(missing)} date(s) had no matching folder, e.g.:\n" + "\n".join(missing[:5])
        messagebox.showinfo("Date range added", msg)

    # -- Indexing -------------------------------------------------------------

    def start_indexing(self):
        if not self.index["folders"]:
            messagebox.showinfo("No folders", "Add at least one folder first.")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "Indexing is already running.")
            return
        self.progress["value"] = 0
        self.status_var.set("Scanning...")
        self.worker = IndexWorker(
            self.index, self.progress_queue,
            lang=self.lang_var.get(),
            thorough=self.thorough_var.get(),
            workers=self.workers_var.get(),
        )
        self.worker.start()

    def stop_indexing(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            self.status_var.set("Stopping...")

    def _poll_queue(self):
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                kind = msg[0]
                if kind == "total":
                    self.progress["maximum"] = max(msg[1], 1)
                elif kind == "workers":
                    _, workers, n_pending = msg
                    self.status_var.set(f"Indexing {n_pending} image(s) using {workers} parallel OCR worker(s)...")
                elif kind == "progress":
                    _, done, total, path, was_ocrd = msg
                    self.progress["value"] = done
                    action = "OCR'd" if was_ocrd else "unchanged"
                    self.status_var.set(f"[{done}/{total}] {action}: {os.path.basename(path)}")
                elif kind == "done":
                    _, done, total, ocr_errors, ocr_elapsed, n_ocrd = msg
                    rate = f", {n_ocrd} OCR'd in {ocr_elapsed:.1f}s ({n_ocrd / ocr_elapsed:.2f} img/s)" if ocr_elapsed > 0 and n_ocrd else ""
                    if ocr_errors:
                        self.status_var.set(
                            f"Index updated. {done}/{total} files scanned{rate}, "
                            f"{ocr_errors} failed OCR (see file's matched text)."
                        )
                    else:
                        self.status_var.set(f"Index updated. {done}/{total} files scanned{rate}.")
                    save_index(self.index)
                elif kind == "error":
                    _, summary, detail = msg
                    self.status_var.set(f"Indexing stopped: {summary}")
                    messagebox.showerror("Indexing problem", f"{summary}\n\n{detail}")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    # -- Search -----------------------------------------------------------

    def search(self):
        try:
            self._do_search()
        except Exception as e:
            import traceback
            self.status_var.set(f"Search failed: {e}")
            messagebox.showerror(
                "Search error",
                f"Something went wrong while searching:\n\n{e}\n\n{traceback.format_exc()}",
            )

    def _do_search(self):
        raw = self.search_var.get().strip()
        self.status_var.set("Searching...")
        self.root.update_idletasks()
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._thumb_refs.clear()

        if not raw:
            return

        keywords = [k.strip() for k in raw.split(",") if k.strip()]
        if not keywords:
            return

        whole_word = self.whole_word_var.get()
        case_sensitive = self.case_sensitive_var.get()
        match_all = self.match_all_var.get()

        # -- date filter --
        date_from = date_to = None
        try:
            if self.date_from_var.get().strip():
                date_from = datetime.strptime(self.date_from_var.get().strip(), "%d-%m-%Y")
            if self.date_to_var.get().strip():
                date_to = datetime.strptime(self.date_to_var.get().strip(), "%d-%m-%Y")
        except ValueError:
            messagebox.showerror("Invalid date", "Date filters must be DD-MM-YYYY, e.g. 21-07-2026.")
            return
        if date_from and date_to and date_to < date_from:
            date_from, date_to = date_to, date_from

        # -- folder scope filter --
        allowed_folders = None
        scope_note = ""
        if self.folder_scope_var.get():
            sel = [self.folder_list.get(i) for i in self.folder_list.curselection()]
            if sel:
                allowed_folders = tuple(sel)
                scope_note = f" in {len(sel)} selected folder(s)"
            else:
                # Nothing actually highlighted in the list above — rather than
                # silently finding nothing, fall back to searching everything
                # and say so, instead of dead-ending the search.
                scope_note = " (no folder was highlighted above, so searched all folders)"

        def prep_kw(kw):
            return kw if case_sensitive else _normalize(kw)

        prepped_keywords = [(prep_kw(kw), kw) for kw in keywords]
        # for whole-word we need a regex per keyword
        word_patterns = None
        if whole_word:
            word_patterns = [
                (re.compile(r"\b" + re.escape(norm_kw) + r"\b", 0 if case_sensitive else re.IGNORECASE), kw)
                for norm_kw, kw in prepped_keywords
            ]

        results = []
        for path, meta in self.index["files"].items():
            if allowed_folders and not path.startswith(allowed_folders):
                continue

            if date_from or date_to:
                file_date = _extract_date_from_path(path)
                if file_date is None:
                    continue
                if date_from and file_date < date_from:
                    continue
                if date_to and file_date > date_to:
                    continue

            text = meta.get("text", "") or ""
            haystack = text if case_sensitive else _normalize(text)
            flat_haystack = haystack.replace(" ", "")

            # Collect every keyword that matches this file (not just the
            # first), so ALL-mode can check the full set and ANY-mode still
            # gets a sensible "first match" snippet.
            matched = []  # list of (keyword, approximate)

            if whole_word:
                for pattern, kw in word_patterns:
                    if pattern.search(haystack):
                        matched.append((kw, False))
                        continue
                    # Strict word-boundary matching has no tolerance for OCR
                    # splitting a MULTI-WORD phrase across a line break (e.g.
                    # "Grameen phone"). Only fall back for phrases (keywords
                    # containing a space) — for a single token like "GP",
                    # flattening would let it falsely match inside unrelated
                    # words like "GPU", so single tokens never use this path.
                    norm_kw = next(nk for nk, k in prepped_keywords if k == kw)
                    if " " not in norm_kw:
                        continue
                    flat_kw = norm_kw.replace(" ", "")
                    if flat_kw and flat_kw in flat_haystack:
                        matched.append((kw, True))
            else:
                for norm_kw, kw in prepped_keywords:
                    if not norm_kw:
                        continue
                    if norm_kw in haystack:
                        matched.append((kw, False))
                    elif " " in norm_kw and norm_kw.replace(" ", "") in flat_haystack:
                        matched.append((kw, True))

            matched_keywords = {kw for kw, _ in matched}

            if self.fuzzy_var.get():
                words = meta.get("words", [])
                if words:
                    still_missing = [kw for kw in keywords if kw not in matched_keywords]
                    for kw in still_missing:
                        if self._fuzzy_keyword_in_words(words, kw, case_sensitive):
                            matched.append((kw, "fuzzy"))
                            matched_keywords.add(kw)

            is_match = (
                matched_keywords == set(keywords) if match_all else len(matched) > 0
            )

            if is_match and matched:
                first_kw, tag = matched[0]
                snippet = self._make_snippet(text, first_kw)
                if match_all and len(matched) > 1:
                    snippet = f"[{', '.join(sorted(matched_keywords))}] " + snippet
                if tag == "fuzzy":
                    snippet += "  [fuzzy match]"
                elif tag is True:
                    snippet += "  [approximate match]"
                results.append((path, snippet, sorted(matched_keywords)))

        results.sort(key=lambda r: r[0])

        self._result_keywords = {path: kws for path, _snippet, kws in results}
        self._last_whole_word = whole_word
        self._last_case_sensitive = case_sensitive
        self._last_fuzzy = self.fuzzy_var.get()
        self._clear_preview()

        make_thumbs = len(results) <= 300
        for i, (path, snippet, _kws) in enumerate(results):
            thumb = self._make_thumbnail(path) if make_thumbs else None
            if thumb is not None:
                self._thumb_refs.append(thumb)
            file_tags = compute_tags_for_text(self.index["files"].get(path, {}).get("text", ""), self.tags)
            stripe = "even" if i % 2 == 0 else "odd"
            self.tree.insert(
                "", tk.END,
                image=thumb if thumb is not None else "",
                values=(os.path.basename(path), os.path.dirname(path), ", ".join(file_tags), snippet),
                tags=(path, stripe),
            )

        joiner = " AND " if match_all else " OR "
        kw_desc = joiner.join(f"'{k}'" for k in keywords)
        note = "" if make_thumbs else " (thumbnails skipped — too many results)"
        self.status_var.set(
            f"Found {len(results)} image(s) matching {kw_desc}{note}"
            f"{scope_note} (searched {len(self.index['files'])} indexed image(s))."
        )

    @staticmethod
    def _make_thumbnail(path, size=(64, 64)):
        try:
            img = Image.open(path)
            img.thumbnail(size)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    @staticmethod
    def _make_snippet(text, keyword, context=40):
        lower = text.lower()
        idx = lower.find(keyword.lower())
        if idx == -1:
            return text[:80].replace("\n", " ")
        start = max(0, idx - context)
        end = min(len(text), idx + len(keyword) + context)
        snippet = text[start:end].replace("\n", " ")
        return ("..." if start > 0 else "") + snippet + ("..." if end < len(text) else "")

    @staticmethod
    def _build_highlight_pattern(keyword, whole_word, case_sensitive):
        """Regex that finds a keyword inside the RAW (non-normalized) OCR
        text for on-screen highlighting. Words are joined with \\s* so a
        multi-word keyword still lights up even if OCR inserted/dropped a
        space or line break inside it (matching the same tolerance the
        search itself uses for split phrases)."""
        parts = [p for p in keyword.strip().split() if p]
        if not parts:
            return None
        pattern = r"\s*".join(re.escape(p) for p in parts)
        if whole_word:
            pattern = r"\b" + pattern + r"\b"
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            return re.compile(pattern, flags)
        except re.error:
            return None

    def _clear_preview(self):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.config(state=tk.DISABLED)

    def _on_result_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            self._clear_preview()
            return
        tags = self.tree.item(sel[0], "tags")
        if not tags:
            self._clear_preview()
            return
        path = tags[0]
        meta = self.index["files"].get(path)
        text = (meta.get("text", "") if meta else "") or ""
        keywords = self._result_keywords.get(path, [])

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, text if text.strip() else "(OCR found no text on this image)")

        for kw in keywords:
            pattern = self._build_highlight_pattern(kw, self._last_whole_word, self._last_case_sensitive)
            hit_any = False
            if pattern is not None:
                for m in pattern.finditer(text):
                    if m.start() == m.end():
                        continue
                    hit_any = True
                    start_idx = f"1.0+{m.start()}c"
                    end_idx = f"1.0+{m.end()}c"
                    self.preview_text.tag_add("hl", start_idx, end_idx)

            if not hit_any and self._last_fuzzy:
                # The exact keyword never appears verbatim — it was a fuzzy
                # (typo-tolerant) match — so find which actual OCR'd word(s)
                # triggered it and highlight those instead.
                words = (meta.get("words", []) if meta else [])
                fuzzy_words = self._fuzzy_hit_word_texts(words, kw, self._last_case_sensitive)
                for w_text in fuzzy_words:
                    lit_pattern = re.compile(re.escape(w_text), 0 if self._last_case_sensitive else re.IGNORECASE)
                    for m in lit_pattern.finditer(text):
                        start_idx = f"1.0+{m.start()}c"
                        end_idx = f"1.0+{m.end()}c"
                        self.preview_text.tag_add("hl", start_idx, end_idx)

        self.preview_text.config(state=tk.DISABLED)

    @staticmethod
    def _clean_word(w, case_sensitive):
        w = w if case_sensitive else w.lower()
        return re.sub(r"[^\w]", "", w, flags=re.UNICODE)

    @classmethod
    def _fuzzy_hit_word_texts(cls, words, keyword, case_sensitive):
        """Like _fuzzy_keyword_in_words, but returns the literal OCR'd
        text of the matching word(s) instead of just True/False — used to
        highlight the actual (possibly misspelled) text in the preview."""
        parts = [p for p in keyword.strip().split() if p]
        if not parts or not words:
            return []
        target_parts = [cls._clean_word(p, case_sensitive) for p in parts]
        cleaned = [cls._clean_word(w["text"], case_sensitive) for w in words]
        n = len(words)
        hits = []
        i = 0
        while i <= n - len(target_parts):
            if all(_fuzzy_word_hit(cleaned[i + j], t) for j, t in enumerate(target_parts)):
                hits.extend(words[i + j]["text"] for j in range(len(target_parts)))
            i += 1
        return hits

    @classmethod
    def _fuzzy_keyword_in_words(cls, words, keyword, case_sensitive):
        """True if `keyword` (single- or multi-word) fuzzy-matches a
        consecutive run of this image's OCR'd words, tolerating typical
        OCR typos (substitution/insertion/deletion of a character or two)."""
        parts = [p for p in keyword.strip().split() if p]
        if not parts or not words:
            return False
        target_parts = [cls._clean_word(p, case_sensitive) for p in parts]
        cleaned = [cls._clean_word(w["text"], case_sensitive) for w in words]
        n = len(words)
        i = 0
        while i <= n - len(target_parts):
            if all(_fuzzy_word_hit(cleaned[i + j], t) for j, t in enumerate(target_parts)):
                return True
            i += 1
        return False

    @classmethod
    def _find_matching_word_boxes(cls, words, keyword, whole_word, case_sensitive, fuzzy=False):
        """Returns a list of (left, top, width, height) boxes — in the
        preprocessed-image coordinate space OCR produced them in — for
        every place `keyword` was found among this image's OCR'd words.
        Handles both a phrase split across several OCR words ("Grameen
        Phone") and the same phrase OCR'd as one run-together word
        ("Grameenphone")."""
        parts = [p for p in keyword.strip().split() if p]
        if not parts or not words:
            return []
        target_parts = [cls._clean_word(p, case_sensitive) for p in parts]
        flattened_target = "".join(target_parts)
        cleaned = [cls._clean_word(w["text"], case_sensitive) for w in words]
        n = len(words)
        boxes = []

        if len(parts) == 1:
            t = target_parts[0]
            for i, ct in enumerate(cleaned):
                if not ct:
                    continue
                hit = (ct == t) if whole_word else (t in ct)
                if not hit and fuzzy:
                    hit = _fuzzy_word_hit(ct, t)
                if hit:
                    w = words[i]
                    boxes.append((w["left"], w["top"], w["width"], w["height"]))
        else:
            i = 0
            while i <= n - len(target_parts):
                ok = True
                for j, t in enumerate(target_parts):
                    ct = cleaned[i + j]
                    exact_ok = (ct == t) if whole_word else (t in ct)
                    if not exact_ok and fuzzy:
                        exact_ok = _fuzzy_word_hit(ct, t)
                    if not exact_ok:
                        ok = False
                        break
                if ok:
                    group = words[i:i + len(target_parts)]
                    l = min(w["left"] for w in group)
                    t_ = min(w["top"] for w in group)
                    r = max(w["left"] + w["width"] for w in group)
                    b = max(w["top"] + w["height"] for w in group)
                    boxes.append((l, t_, r - l, b - t_))
                    i += len(target_parts)
                else:
                    i += 1
            # Also catch the phrase run together as a single OCR word.
            for i, ct in enumerate(cleaned):
                if not ct:
                    continue
                hit = (ct == flattened_target) if whole_word else (flattened_target in ct)
                if hit:
                    w = words[i]
                    boxes.append((w["left"], w["top"], w["width"], w["height"]))

        return boxes

    @staticmethod
    def _save_highlighted_copy(src_path, dst_path, boxes, scale):
        """Save a copy of src_path with red boxes drawn around each
        (left, top, width, height) box. Boxes are in preprocessed-image
        coordinates; scale maps them back to the original image's pixels."""
        with Image.open(src_path) as im:
            im = im.convert("RGB")
            draw = ImageDraw.Draw(im)
            scale = scale or 1.0
            pad = max(2, int(round(4 / scale)))
            line_w = max(2, int(round(4 / scale)))
            for (l, t, w, h) in boxes:
                ol, ot, ow, oh = l / scale, t / scale, w / scale, h / scale
                draw.rectangle(
                    [ol - pad, ot - pad, ol + ow + pad, ot + oh + pad],
                    outline=(255, 0, 0),
                    width=line_w,
                )
            im.save(dst_path)

    @classmethod
    def _quick_match_keywords(cls, meta, keywords, whole_word, case_sensitive, match_all, fuzzy):
        """Standalone version of the search-matching rules (same semantics
        as _do_search) for features that need to test a file against
        keywords outside of a live search — e.g. trend tracking scanning
        the whole index regardless of the current date/folder filters.
        Returns the set of matched keywords, or an empty set for no match."""
        text = meta.get("text", "") or ""

        def prep_kw(kw):
            return kw if case_sensitive else _normalize(kw)

        haystack = text if case_sensitive else _normalize(text)
        flat_haystack = haystack.replace(" ", "")
        matched_keywords = set()

        for kw in keywords:
            norm_kw = prep_kw(kw)
            if not norm_kw:
                continue
            hit = False
            if whole_word:
                pattern = re.compile(r"\b" + re.escape(norm_kw) + r"\b", 0 if case_sensitive else re.IGNORECASE)
                if pattern.search(haystack):
                    hit = True
                elif " " in norm_kw and norm_kw.replace(" ", "") in flat_haystack:
                    hit = True
            else:
                if norm_kw in haystack:
                    hit = True
                elif " " in norm_kw and norm_kw.replace(" ", "") in flat_haystack:
                    hit = True
            if not hit and fuzzy:
                words = meta.get("words", [])
                if words and cls._fuzzy_keyword_in_words(words, kw, case_sensitive):
                    hit = True
            if hit:
                matched_keywords.add(kw)

        if match_all and matched_keywords != set(keywords):
            return set()
        return matched_keywords

    def show_trend(self):
        """Show how often the current keyword(s) appear over time, across
        the WHOLE index (ignoring the date-range/folder filters above —
        that's the point, to see the full history)."""
        raw = self.search_var.get().strip()
        keywords = [k.strip() for k in raw.split(",") if k.strip()]
        if not keywords:
            messagebox.showinfo("No keywords", "Type keyword(s) to search first, then click Trend.")
            return

        whole_word = self.whole_word_var.get()
        case_sensitive = self.case_sensitive_var.get()
        match_all = self.match_all_var.get()
        fuzzy = self.fuzzy_var.get()

        counts_by_month = {}
        undated = 0
        matched_files = 0
        for path, meta in self.index["files"].items():
            matched = self._quick_match_keywords(meta, keywords, whole_word, case_sensitive, match_all, fuzzy)
            if not matched:
                continue
            matched_files += 1
            file_date = _extract_date_from_path(path)
            if file_date is None:
                undated += 1
                continue
            key = (file_date.year, file_date.month)
            counts_by_month[key] = counts_by_month.get(key, 0) + 1

        if matched_files == 0:
            messagebox.showinfo("No matches", "No indexed images matched those keyword(s).")
            return

        self._show_trend_window(keywords, counts_by_month, matched_files, undated)

    def _show_trend_window(self, keywords, counts_by_month, matched_files, undated):
        win = tk.Toplevel(self.root)
        win.title(f"Trend: {', '.join(keywords)}")
        nab_ui_scale.fit(win, 640, 420, min_w=396, min_h=260, parent=self.root)

        kw_desc = ", ".join(f"'{k}'" for k in keywords)
        header = f"{matched_files} matching image(s) total for {kw_desc}"
        if undated:
            header += f"  ({undated} had no detectable date and aren't shown on the chart)"
        ttk.Label(win, text=header, wraplength=600, padding=8).pack(side=tk.TOP, fill=tk.X)

        canvas = tk.Canvas(win, background="white", height=300)
        canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        months = sorted(counts_by_month.keys())
        if not months:
            canvas.create_text(300, 140, text="(no dated matches to chart)")
            return

        counts = [counts_by_month[m] for m in months]
        max_count = max(counts) or 1
        labels = [f"{y}-{mo:02d}" for (y, mo) in months]

        def redraw(_event=None):
            canvas.delete("all")
            w = canvas.winfo_width() or 640
            h = canvas.winfo_height() or 300
            pad_left, pad_bottom, pad_top = 40, 40, 20
            n = len(months)
            bar_area_w = w - pad_left - 10
            bar_w = max(4, bar_area_w / n * 0.7)
            gap = bar_area_w / n
            plot_h = h - pad_bottom - pad_top

            # y-axis gridlines
            for frac in (0, 0.5, 1.0):
                y = pad_top + plot_h * (1 - frac)
                canvas.create_line(pad_left, y, w - 5, y, fill="#e0e0e0")
                canvas.create_text(pad_left - 6, y, text=str(int(max_count * frac)), anchor="e", font=("Segoe UI", 8))

            for i, (label, count) in enumerate(zip(labels, counts)):
                x_center = pad_left + gap * i + gap / 2
                bar_h = plot_h * (count / max_count)
                x0 = x_center - bar_w / 2
                x1 = x_center + bar_w / 2
                y0 = pad_top + plot_h - bar_h
                y1 = pad_top + plot_h
                canvas.create_rectangle(x0, y0, x1, y1, fill="#4a90d9", outline="")
                canvas.create_text(x_center, y0 - 8, text=str(count), font=("Segoe UI", 8))
                rot_label = label if n <= 12 else label[2:]  # tighten labels if crowded
                canvas.create_text(x_center, pad_top + plot_h + 12, text=rot_label, font=("Segoe UI", 8), angle=45 if n > 8 else 0)

        canvas.bind("<Configure>", redraw)
        win.after(50, redraw)

    def manage_tags(self):
        """Dialog to create/edit/delete auto-tag rules: a tag name plus a
        list of trigger keywords. Any indexed image whose OCR text
        contains one of a tag's keywords gets tagged with it automatically
        (shown in the Tags column and in Show Index)."""
        win = tk.Toplevel(self.root)
        win.title("Manage Tags")
        nab_ui_scale.fit(win, 520, 420, min_w=322, min_h=260, parent=self.root)
        win.transient(self.root)

        ttk.Label(
            win, text="Each tag applies automatically to any image whose OCR text "
                      "contains one of its keywords.",
            wraplength=490, padding=8,
        ).pack(side=tk.TOP, fill=tk.X)

        list_frame = ttk.Frame(win)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8)

        tag_list = tk.Listbox(list_frame, height=10)
        tag_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tag_list.yview)
        tag_list.configure(yscrollcommand=tag_scroll.set)
        tag_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tag_scroll.pack(side=tk.LEFT, fill=tk.Y)

        form = ttk.Frame(win, padding=8)
        form.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(form, text="Tag name:").grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar()
        ttk.Entry(form, textvariable=name_var, width=40).grid(row=0, column=1, sticky="we", padx=(6, 0))

        ttk.Label(form, text="Keywords (comma-separated):").grid(row=1, column=0, sticky="w", pady=(6, 0))
        kw_var = tk.StringVar()
        ttk.Entry(form, textvariable=kw_var, width=40).grid(row=1, column=1, sticky="we", padx=(6, 0), pady=(6, 0))
        form.columnconfigure(1, weight=1)

        def refresh_list():
            tag_list.delete(0, tk.END)
            for tag_name in sorted(self.tags.keys()):
                kws = ", ".join(self.tags[tag_name])
                tag_list.insert(tk.END, f"{tag_name}  —  {kws}")

        def on_select(_event=None):
            sel = tag_list.curselection()
            if not sel:
                return
            tag_name = sorted(self.tags.keys())[sel[0]]
            name_var.set(tag_name)
            kw_var.set(", ".join(self.tags[tag_name]))

        tag_list.bind("<<ListboxSelect>>", on_select)

        def do_save_tag():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Missing name", "Give the tag a name.", parent=win)
                return
            kws = [k.strip() for k in kw_var.get().split(",") if k.strip()]
            if not kws:
                messagebox.showwarning("Missing keywords", "Add at least one trigger keyword.", parent=win)
                return
            self.tags[name] = kws
            save_tags(self.tags)
            refresh_list()
            name_var.set("")
            kw_var.set("")

        def do_delete_tag():
            sel = tag_list.curselection()
            if not sel:
                messagebox.showinfo("Nothing selected", "Select a tag in the list to delete.", parent=win)
                return
            tag_name = sorted(self.tags.keys())[sel[0]]
            if messagebox.askyesno("Delete tag", f"Delete the tag '{tag_name}'?", parent=win):
                del self.tags[tag_name]
                save_tags(self.tags)
                refresh_list()
                name_var.set("")
                kw_var.set("")

        btn_row = ttk.Frame(win, padding=(8, 0, 8, 8))
        btn_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(btn_row, text="Add / Update", command=do_save_tag).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Delete Selected", command=do_delete_tag).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_row, text="Close", command=win.destroy).pack(side=tk.RIGHT)

        refresh_list()

    def find_duplicates(self):
        """Scan the index for near-duplicate articles (same story run in
        multiple papers, or the same clipping filed twice) using a cheap
        word-overlap (Jaccard) similarity on the OCR'd text — no external
        dependencies needed."""
        items = [
            (path, meta.get("text", "") or "")
            for path, meta in self.index["files"].items()
        ]
        items = [(p, t) for p, t in items if len(t.strip()) >= 30]  # skip near-empty OCR results
        if len(items) < 2:
            messagebox.showinfo("Not enough data", "Need at least 2 indexed images with real OCR text to compare.")
            return

        win = tk.Toplevel(self.root)
        win.title("Finding duplicates...")
        ttk.Label(win, text=f"Comparing {len(items)} indexed images...", padding=16).pack()
        win.update()

        word_sets = [set(re.findall(r"\w+", t.lower())) for _p, t in items]
        n = len(items)
        threshold = 0.55
        parent = list(range(n))  # union-find to group transitively-similar articles

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            wi = word_sets[i]
            if len(wi) < 5:
                continue
            for j in range(i + 1, n):
                wj = word_sets[j]
                if len(wj) < 5:
                    continue
                inter = len(wi & wj)
                if inter == 0:
                    continue
                union_size = len(wi | wj)
                similarity = inter / union_size if union_size else 0
                if similarity >= threshold:
                    union(i, j)

        groups = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)
        dup_groups = [idxs for idxs in groups.values() if len(idxs) > 1]

        win.destroy()

        if not dup_groups:
            messagebox.showinfo("No duplicates found", f"Compared {n} images — no near-duplicate groups found.")
            return

        self._show_duplicates_window(items, dup_groups)

    def _show_duplicates_window(self, items, dup_groups):
        win = tk.Toplevel(self.root)
        win.title(f"Possible duplicates — {len(dup_groups)} group(s)")
        nab_ui_scale.fit(win, 760, 480, min_w=471, min_h=297, parent=self.root)

        ttk.Label(
            win, text=f"{len(dup_groups)} group(s) of likely-duplicate articles found "
                      f"(similar wording — e.g. the same wire story run in multiple papers).",
            wraplength=740, padding=8,
        ).pack(side=tk.TOP, fill=tk.X)

        tree = ttk.Treeview(win, columns=("file", "folder"), show="tree headings")
        tree.heading("#0", text="Group")
        tree.heading("file", text="File")
        tree.heading("folder", text="Folder")
        tree.column("#0", width=90)
        tree.column("file", width=220)
        tree.column("folder", width=380)
        tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        dup_groups = sorted(dup_groups, key=len, reverse=True)
        for gi, idxs in enumerate(dup_groups, 1):
            group_node = tree.insert("", tk.END, text=f"Group {gi} ({len(idxs)})", open=True)
            for idx in idxs:
                path, _text = items[idx]
                tree.insert(
                    group_node, tk.END,
                    values=(os.path.basename(path), os.path.dirname(path)),
                    tags=(path,),
                )

        def open_dup(_event=None):
            sel = tree.selection()
            if not sel:
                return
            tags = tree.item(sel[0], "tags")
            if not tags:
                return
            path = tags[0]
            if os.path.exists(path):
                self._open_path(path)

        tree.bind("<Double-1>", open_dup)

    def copy_results(self):
        """Ask what to copy (all results vs just the selected rows, and
        plain copies vs highlighted copies with matched words boxed) then
        do it."""
        all_rows = self.tree.get_children()
        if not all_rows:
            messagebox.showinfo("Nothing to copy", "Run a search first, then copy the results.")
            return
        selected_rows = self.tree.selection()

        win = tk.Toplevel(self.root)
        win.title("Copy results")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        pad = {"padx": 12, "pady": 6}
        scope_var = tk.StringVar(value="selected" if selected_rows else "all")
        ttk.Label(win, text="Which images?").grid(row=0, column=0, sticky="w", **pad)
        ttk.Radiobutton(
            win, text=f"Selected rows only ({len(selected_rows)})",
            variable=scope_var, value="selected", state=(tk.NORMAL if selected_rows else tk.DISABLED),
        ).grid(row=1, column=0, sticky="w", padx=24)
        ttk.Radiobutton(
            win, text=f"All results ({len(all_rows)})",
            variable=scope_var, value="all",
        ).grid(row=2, column=0, sticky="w", padx=24)

        ttk.Separator(win, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=12, pady=6)

        ttk.Label(win, text="Copy which version(s)?").grid(row=4, column=0, sticky="w", **pad)
        include_original = tk.BooleanVar(value=True)
        include_highlighted = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            win, text="Original images (unmodified)", variable=include_original
        ).grid(row=5, column=0, sticky="w", padx=24)
        ttk.Checkbutton(
            win, text="Highlighted copies (red box around matched word(s))",
            variable=include_highlighted,
        ).grid(row=6, column=0, sticky="w", padx=24)
        ttk.Label(
            win, text="(If both are ticked, they\'re saved into separate\n\'original\' / \'highlighted\' subfolders.)",
            foreground="#666666",
        ).grid(row=7, column=0, sticky="w", padx=24, pady=(0, 6))

        btn_row = ttk.Frame(win)
        btn_row.grid(row=8, column=0, sticky="e", padx=12, pady=(6, 12))

        def do_cancel():
            win.destroy()

        def do_copy():
            if not include_original.get() and not include_highlighted.get():
                messagebox.showwarning("Nothing selected", "Tick at least one of Original / Highlighted.", parent=win)
                return
            rows = selected_rows if scope_var.get() == "selected" else all_rows
            win.destroy()
            self._do_copy_results(rows, include_original.get(), include_highlighted.get())

        ttk.Button(btn_row, text="Cancel", command=do_cancel).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Copy", command=do_copy).pack(side=tk.RIGHT)

    def _do_copy_results(self, rows, include_original, include_highlighted):
        dest = filedialog.askdirectory(title="Choose a destination folder for the copies")
        if not dest:
            return

        both = include_original and include_highlighted
        orig_dir = os.path.join(dest, "original") if both else dest
        hl_dir = os.path.join(dest, "highlighted") if both else dest
        if include_original:
            os.makedirs(orig_dir, exist_ok=True)
        if include_highlighted:
            os.makedirs(hl_dir, exist_ok=True)

        def unique_dest(folder, filename):
            dst = os.path.join(folder, filename)
            if not os.path.exists(dst):
                return dst
            base, ext = os.path.splitext(filename)
            n = 1
            while os.path.exists(dst):
                dst = os.path.join(folder, f"{base}_{n}{ext}")
                n += 1
            return dst

        copied_orig, copied_hl, skipped, errors = 0, 0, 0, []
        for row in rows:
            values = self.tree.item(row, "values")
            filename, folder = values[0], values[1]
            src = os.path.join(folder, filename)
            if not os.path.exists(src):
                skipped += 1
                continue

            if include_original:
                try:
                    shutil.copy2(src, unique_dest(orig_dir, filename))
                    copied_orig += 1
                except Exception as e:
                    errors.append(f"{filename}: {e}")

            if include_highlighted:
                try:
                    meta = self.index["files"].get(src, {})
                    words = meta.get("words", [])
                    scale = meta.get("scale", 1.0) or 1.0
                    keywords = self._result_keywords.get(src, [])
                    boxes = []
                    for kw in keywords:
                        boxes.extend(self._find_matching_word_boxes(
                            words, kw, self._last_whole_word, self._last_case_sensitive, self._last_fuzzy
                        ))
                    dst = unique_dest(hl_dir, filename)
                    if boxes:
                        self._save_highlighted_copy(src, dst, boxes, scale)
                    else:
                        # No word-level box found (e.g. old cache entry, or
                        # an approximate match) — still give them a copy
                        # rather than silently skipping it.
                        shutil.copy2(src, dst)
                    copied_hl += 1
                except Exception as e:
                    errors.append(f"{filename} (highlighted): {e}")

        msg_parts = []
        if include_original:
            msg_parts.append(f"{copied_orig} original file(s) -> {orig_dir}")
        if include_highlighted:
            msg_parts.append(f"{copied_hl} highlighted file(s) -> {hl_dir}")
        msg = "Copy complete:\n" + "\n".join(msg_parts)
        if skipped:
            msg += f"\n\n{skipped} file(s) no longer existed and were skipped."
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        messagebox.showinfo("Copy complete", msg)

    def show_index(self):
        win = tk.Toplevel(self.root)
        win.title("What's currently indexed")
        nab_ui_scale.fit(win, 820, 480, min_w=508, min_h=297, parent=self.root)

        # -- Folder summary --
        ttk.Label(win, text="Folders being searched (recursively):", font=("", 10, "bold")).pack(
            anchor="w", padx=8, pady=(8, 2)
        )
        folder_box = tk.Text(win, height=6, wrap="none")
        folder_box.pack(fill=tk.X, padx=8)

        if not self.index["folders"]:
            folder_box.insert("end", "(no folders added yet)\n")
        for folder in self.index["folders"]:
            on_disk = len(list(iter_image_files([folder]))) if os.path.isdir(folder) else 0
            exists = "OK" if os.path.isdir(folder) else "MISSING"
            folder_box.insert("end", f"[{exists}] {folder}  —  {on_disk} image file(s) found on disk\n")
        folder_box.config(state="disabled")

        # -- Per-file index --
        ttk.Label(
            win,
            text=f"Indexed files ({len(self.index['files'])} total). "
                 f"'Text chars' near 0 usually means OCR found nothing on that image:",
            font=("", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(10, 2))

        columns = ("file", "folder", "chars", "preview")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.heading("file", text="File")
        tree.heading("folder", text="Folder")
        tree.heading("chars", text="Text chars")
        tree.heading("preview", text="OCR preview")
        tree.column("file", width=160)
        tree.column("folder", width=220)
        tree.column("chars", width=70, anchor="center")
        tree.column("preview", width=320)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        for path, meta in sorted(self.index["files"].items()):
            text = meta.get("text", "") or ""
            preview = text.strip().replace("\n", " ")[:80]
            tree.insert("", tk.END, values=(
                os.path.basename(path), os.path.dirname(path), len(text.strip()), preview
            ))

    # -- Opening files ------------------------------------------------------

    def _selected_path(self):
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        folder, filename = values[1], values[0]
        return os.path.join(folder, filename)

    def _open_path(self, path):
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    def open_selected(self):
        path = self._selected_path()
        if not path or not os.path.exists(path):
            return
        self._open_path(path)

    def reveal_selected(self):
        path = self._selected_path()
        if not path or not os.path.exists(path):
            return
        if os.name == "nt":
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", path])
        else:
            subprocess.run(["xdg-open", os.path.dirname(path)])

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.context_menu.post(event.x_root, event.y_root)


def main():
    root = tk.Tk()
    app = ImageOCRFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # required for ProcessPoolExecutor in a PyInstaller .exe
    main()
