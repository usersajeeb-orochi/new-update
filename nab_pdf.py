# nab_pdf.py — PDF Maker (was PDF.py V31), integrated into NAB
#
# Launched as its own process via:  NAB.exe --pdf-bot
# (same pattern as --ocr-finder) because it owns a Tk root and a
# ProcessPoolExecutor, neither of which can live inside NAB's event loop.
#
# Changes from the standalone PDF.py:
#   • config moved out of CWD into ~/Documents/nab_pdf_config.json, and
#     merged with defaults so an old/partial config can't KeyError the app
#   • folder picker starts in NAB's own save folder for today
#   • sort_order now matches LONGEST name first — "Sangbad" no longer
#     swallows clips that belong to "Pratidiner Sangbad"
#   • failed pages are reported instead of silently skipped
#   • every window goes through nab_ui_scale.fit() so it fits small monitors
#   • winsound / os.startfile guarded for non-Windows
#   • "Save Folders" / "Update" in Settings now actually write to disk
#
import os
import re
import sys
import time
import json
import logging
import datetime as _dt
import multiprocessing
import concurrent.futures
import tkinter as tk
from tkinter import (filedialog, Button, Label, Frame, Toplevel, Text,
                     messagebox, Checkbutton, BooleanVar, Entry, Listbox,
                     Scale, IntVar, Canvas)
from tkinter.ttk import Progressbar, Style, Notebook
from PIL import Image, ImageTk

from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

try:
    import nab_ui_scale
except ImportError:                       # standalone use
    nab_ui_scale = None

try:
    from nab_clip_scan import nab_base_root
except ImportError:
    def nab_base_root():
        return os.path.join(os.path.expanduser("~"), "Documents", "Monitoring")

# ---------- COLORS ----------
COLOR_BG      = "#211900"
COLOR_CARD    = "#1E293B"
COLOR_ACCENT  = "#f2be2c"
COLOR_TEXT    = "#FFFFFF"
COLOR_WARN    = "#f59e0b"
COLOR_DANGER  = "#EF4444"
COLOR_SUCCESS = "#22C55E"

# ---------- CONFIG ----------
# Was "config.json" relative to the working directory — which, for an EXE
# launched from Explorer or from NAB, is wherever the user happened to be.
# Settings silently vanished or duplicated depending on how it was started.
CONFIG_FILE = os.path.join(os.path.expanduser("~"), "Documents",
                           "nab_pdf_config.json")

DEFAULT_CONFIG = {
    "sort_order": ["Daily Star", "TBS", "Financial Express", "Daily Observer",
                   "Dhaka Tribune", "New Age", "Daily Sun", "New Nation",
                   "Asian Age", "Bangladesh Today", "TOB", "Prothom Alo",
                   "Samakal", "Ittefaq", "Jugantor", "Kaler Kantha",
                   "Janakantha", "Naya Diganta", "Daily Inqilab", "Bonik Barta",
                   "Bangladesh Pratidin", "Sangbad", "Jaijaidin", "Manabzamin",
                   "Amader Shomoy", "Sharebiz", "Ajker Patrika",
                   "Protidiner Bangladesh", "Shomoyer Alo",
                   "Pratidiner Sangbad", "Desh Rupantor", "Kalbela",
                   "Rupali Bangladesh", "Khoborer Kagoj", "Amardesh",
                   "Alokito Bangladesh"],
    "custom_names": {
        "Bank":    "Bank news media monitoring report on {date}",
        "Economy": "Economy news media monitoring report on {date}",
        "Finance": "Finance news media monitoring report on {date}",
        "LPG":     "LPG news media monitoring report on {date}",
        "LNG":     "LNG news media monitoring report on {date}",
        "Power":   "Power news media monitoring report on {date}",
    },
    "combined_groups": {
        "Banking & Finance news media monitoring report on {date}":
            ["Bank", "Economy", "Finance"],
        "Power, Energy & Mineral news media monitoring report on {date}":
            ["LPG", "LNG", "Power"],
    },
    "categories_to_process": ["Beximco", "Mineral", "Pride Group", "United Group"],
    "generic_pattern": "{folder} news media monitoring report on {date}.pdf",
    "blacklist": ["Old_Data", "Temp", "Backup", "OutputPDF"],
    "group_only": ["Economy", "Finance", "LPG"],
    "auto_open": True,
    "play_sound": True,
    "compress_enabled": True,
    "smart_compression": True,
    "manual_quality": 65,
    "bg_image": "",
}


def load_config():
    """Load config, filling in anything the saved file is missing.

    The old version returned the raw JSON, so a config written by an earlier
    build (or a hand-edited one) would KeyError on CFG["sort_order"] the
    moment you pressed Start."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))     # deep copy
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update({k: v for k, v in saved.items() if v is not None})
    except Exception as e:
        logging.error(f"nab_pdf.load_config: {e}")
    return cfg


def save_config(new_config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"nab_pdf.save_config: {e}")
        return False


CFG = load_config()


# ---------- WORKER (runs in a separate process) ----------
def process_single_pdf_task(payload):
    jpg_files, output_pdf_path, comp_enabled, smart_mode, manual_qual = payload
    name = os.path.basename(output_pdf_path)

    if not jpg_files:
        return (False, f"⏭ Skipped (no images): {name}")

    SIZE_THRESHOLD = 400 * 1024
    failed = []

    try:
        page_w, page_h = A4
        c = pdf_canvas.Canvas(output_pdf_path, pagesize=A4)
        c.setTitle(os.path.splitext(name)[0])

        pages = 0
        for jpg in jpg_files:
            try:
                do_compress = False
                target_w, target_q = 1600, 65

                if comp_enabled:
                    if smart_mode:
                        if os.path.getsize(jpg) > SIZE_THRESHOLD:
                            do_compress = True
                    else:
                        do_compress = True
                        target_q = manual_qual
                        if manual_qual > 80:   target_w = 2500
                        elif manual_qual > 50: target_w = 1600
                        else:                  target_w = 1000

                if do_compress:
                    import io
                    with Image.open(jpg) as raw_img:
                        if raw_img.mode != "RGB":
                            raw_img = raw_img.convert("RGB")
                        w, h = raw_img.size
                        if w > target_w:
                            ratio = target_w / float(w)
                            raw_img = raw_img.resize(
                                (target_w, max(1, int(h * ratio))),
                                Image.Resampling.LANCZOS)
                        buf = io.BytesIO()
                        raw_img.save(buf, format="JPEG",
                                     quality=target_q, optimize=True)
                        buf.seek(0)
                        img_obj = ImageReader(buf)
                else:
                    img_obj = ImageReader(jpg)

                w_px, h_px = img_obj.getSize()
                scale = min(page_w / w_px, page_h / h_px, 1.0)
                draw_w, draw_h = w_px * scale, h_px * scale
                x = (page_w - draw_w) / 2
                y = (page_h - draw_h) / 2

                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
                c.drawImage(img_obj, x, y, draw_w, draw_h,
                            preserveAspectRatio=True, anchor="c")
                c.showPage()
                pages += 1
            except Exception as e:
                # The old code did `except: continue` — a corrupt or locked
                # JPEG vanished from the PDF with nothing reported, so you
                # only found out when someone noticed a missing clip.
                failed.append(f"{os.path.basename(jpg)} ({type(e).__name__})")

        if pages == 0:
            return (False, f"❌ {name}: every page failed "
                           f"({len(failed)} image(s))")

        c.save()
        if failed:
            shown = ", ".join(failed[:3])
            more = f" +{len(failed)-3} more" if len(failed) > 3 else ""
            return (True, f"⚠ {name} — {pages} page(s), SKIPPED: {shown}{more}")
        return (True, f"✅ {name} — {pages} page(s)")

    except Exception as e:
        return (False, f"❌ {name}: {type(e).__name__}: {e}")


# ---------- TASK BUILDER ----------
def detect_date(folder):
    m = re.search(r"\d{2}-\d{2}-\d{4}", folder)
    if not m:
        return folder
    try:
        return _dt.datetime.strptime(m.group(0), "%d-%m-%Y").strftime("%B %d, %Y")
    except Exception:
        return m.group(0)


def _make_sorter(sort_order):
    """Priority lookup that matches the LONGEST newspaper name first.

    The old version walked the list in priority order and took the first
    substring hit, so a file called "Pratidiner Sangbad, Page-1..." matched
    "Sangbad" (list position 21) instead of "Pratidiner Sangbad" (position
    29) — papers ended up in the wrong place in every combined PDF."""
    ranked = sorted(
        ((name.lower().replace("_", " ").replace("-", " "), i)
         for i, name in enumerate(sort_order) if name.strip()),
        key=lambda t: len(t[0]), reverse=True)

    def get_sort(path):
        base = os.path.basename(path).lower().replace("_", " ").replace("-", " ")
        for name, idx in ranked:
            if name in base:
                return (idx, os.path.basename(path).lower())
        return (999, os.path.basename(path).lower())
    return get_sort


def _images_in(folder):
    try:
        return [os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    except OSError:
        return []


def build_pdf_tasks(day_folder):
    global CFG
    CFG = load_config()

    date_str   = detect_date(os.path.basename(day_folder))
    output_dir = os.path.join(day_folder, "OutputPDF")

    comp_en  = CFG.get("compress_enabled", True)
    smart_m  = CFG.get("smart_compression", True)
    man_qual = CFG.get("manual_quality", 65)

    blacklist  = {b.lower() for b in CFG.get("blacklist", [])}
    group_only = {g.lower() for g in CFG.get("group_only", [])}
    get_sort   = _make_sorter(CFG.get("sort_order", []))

    tasks = []
    for category in CFG.get("categories_to_process", []):
        if category.lower() in blacklist:
            continue
        cat_path = os.path.join(day_folder, category)
        if not os.path.isdir(cat_path):
            continue

        # Loose images directly under the category
        jpgs = _images_in(cat_path)
        if jpgs:
            jpgs.sort(key=get_sort)
            tasks.append((jpgs, os.path.join(
                output_dir,
                f"{category} news media monitoring report on {date_str}.pdf"),
                comp_en, smart_m, man_qual))

        # Combined groups
        for pattern, groups in CFG.get("combined_groups", {}).items():
            c_jpgs = []
            for g in groups:
                if g.lower() in blacklist:
                    continue
                p = os.path.join(cat_path, g)
                if os.path.isdir(p):
                    c_jpgs.extend(_images_in(p))
            if c_jpgs:
                c_jpgs.sort(key=get_sort)
                try:
                    name = pattern.format(date=date_str)
                except (KeyError, IndexError):
                    # A group name containing stray {braces} used to crash
                    # the whole build before a single PDF was written.
                    name = pattern
                if not name.lower().endswith(".pdf"):
                    name += ".pdf"
                tasks.append((c_jpgs, os.path.join(output_dir, name),
                              comp_en, smart_m, man_qual))

        # One PDF per sub-folder
        try:
            subfolders = [d for d in os.listdir(cat_path)
                          if os.path.isdir(os.path.join(cat_path, d))
                          and d.lower() not in blacklist]
        except OSError:
            subfolders = []
        for sf in subfolders:
            if sf.lower() in group_only:
                continue
            jpgs = _images_in(os.path.join(cat_path, sf))
            if not jpgs:
                continue
            jpgs.sort(key=get_sort)
            pat = CFG.get("custom_names", {}).get(
                sf, CFG.get("generic_pattern", "{folder} {date}.pdf"))
            try:
                name = pat.format(folder=sf, date=date_str)
            except (KeyError, IndexError):
                name = f"{sf} {date_str}"
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            tasks.append((jpgs, os.path.join(output_dir, name),
                          comp_en, smart_m, man_qual))

    # Only create the output folder if there's actually something to write —
    # the old version left empty OutputPDF folders all over the archive.
    if tasks:
        os.makedirs(output_dir, exist_ok=True)
    return tasks


def list_pdf_items(day_folder, categories=None, include_hidden=False):
    """What the PDF maker would produce, one entry per PDF, with the folders behind it — used by "Send by mail" so a group
    can pick exactly which PDFs / folders it gets.  Mirrors build_pdf_tasks() (same names, same order); it creates nothing."""
    cfg = load_config()
    date_str = detect_date(os.path.basename(day_folder))
    output_dir = os.path.join(day_folder, "OutputPDF")
    comp_en, smart_m, man_qual = cfg.get("compress_enabled", True), cfg.get("smart_compression", True), cfg.get("manual_quality", 65)
    blacklist = {b.lower() for b in cfg.get("blacklist", [])}
    group_only = {g.lower() for g in cfg.get("group_only", [])}
    get_sort = _make_sorter(cfg.get("sort_order", []))
    if categories is None:
        try:
            categories = sorted(d for d in os.listdir(day_folder) if os.path.isdir(os.path.join(day_folder, d)))
        except OSError:
            categories = []
    items = []

    def add(cat, kind, label, folders, jpgs, name, recursive_dirs, hidden=False):
        jpgs = sorted(jpgs, key=get_sort)
        out = os.path.join(output_dir, name)
        short = re.sub(r"\s+", " ", name[:-4].replace(date_str, "")).strip()
        short = re.sub(r"\s+on$", "", short).strip()
        items.append({"key": "pdf|" + short, "legacy_key": f"{cat}|{kind}|{label}", "short": short, "category": cat, "kind": kind, "label": label or cat, "name": name, "out": out,
                      "folders": folders, "images": jpgs, "n": len(jpgs), "dirs": recursive_dirs, "hidden": hidden,
                      "task": (jpgs, out, comp_en, smart_m, man_qual)})

    for category in categories:
        if category.lower() in blacklist:
            continue
        cat_path = os.path.join(day_folder, category)
        if not os.path.isdir(cat_path):
            continue
        jpgs = _images_in(cat_path)
        if jpgs:
            add(category, "loose", "", [cat_path], jpgs, f"{category} news media monitoring report on {date_str}.pdf", [])
        for pattern, groups in cfg.get("combined_groups", {}).items():
            c_jpgs, dirs = [], []
            for g in groups:
                if g.lower() in blacklist:
                    continue
                p = os.path.join(cat_path, g)
                if os.path.isdir(p):
                    c_jpgs.extend(_images_in(p))
                    dirs.append(p)
            if c_jpgs:
                try:
                    name = pattern.format(date=date_str)
                except (KeyError, IndexError):
                    name = pattern
                if not name.lower().endswith(".pdf"):
                    name += ".pdf"
                add(category, "combined", pattern.split(" news media")[0], dirs, c_jpgs, name, dirs)
        try:
            subfolders = sorted(d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d)) and d.lower() not in blacklist)
        except OSError:
            subfolders = []
        for sf in subfolders:
            hidden = sf.lower() in group_only
            if hidden and not include_hidden:
                continue
            sp = os.path.join(cat_path, sf)
            sj = _images_in(sp)
            if not sj:
                continue
            pat = cfg.get("custom_names", {}).get(sf, cfg.get("generic_pattern", "{folder} {date}.pdf"))
            try:
                name = pat.format(folder=sf, date=date_str)
            except (KeyError, IndexError):
                name = f"{sf} {date_str}"
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            add(category, "sub", sf, [sp], sj, name, [sp], hidden)
    # the same PDF name coming from two categories would overwrite each other: keep them apart
    seen = {}
    for it in items:
        seen.setdefault(it["name"].lower(), []).append(it)
    for lst in seen.values():
        if len(lst) > 1:
            for it in lst:
                base = it["name"][:-4]
                it["name"] = f"{base} ({it['category']}).pdf"
                it["out"] = os.path.join(output_dir, it["name"])
                it["task"] = (it["task"][0], it["out"]) + tuple(it["task"][2:])
    return items


# ---------- CONTROLLER ----------
def start_processing(folder, logger_func, pbar, lbl, btn):
    import threading

    btn.config(state="disabled", bg=COLOR_CARD)

    if CFG.get("compress_enabled", True):
        mode_text = ("SMART MODE" if CFG.get("smart_compression", True)
                     else f"MANUAL: {CFG.get('manual_quality', 65)}%")
    else:
        mode_text = "RAW QUALITY (OFF)"

    logger_func(f"🚀 STARTED ({mode_text}): {folder}")
    # Scanning is now shown as its own step — it used to run on the main
    # thread BEFORE this function returned, which froze the whole PDF Maker
    # window (no progress bar, no log line, nothing) for however long it took
    # to walk every category/subfolder. That walk, and building the combined-
    # group file lists, now happens inside the same background thread as the
    # actual PDF rendering.
    lbl.config(text="🔎 Scanning folder…")

    def run_in_thread():
        start_time = time.time()
        completed = ok = 0
        try:
            tasks = build_pdf_tasks(folder)
        except Exception as e:
            lbl.after(0, lambda e=e: [
                logger_func(f"❌ Could not scan folder: {e}"),
                btn.config(state="normal", bg=COLOR_ACCENT)])
            return

        total = len(tasks)
        if total == 0:
            lbl.after(0, lambda: [
                logger_func("⚠️ No PDFs to create — check the folder, "
                           "Categories tab, and Blacklist."),
                btn.config(state="normal", bg=COLOR_ACCENT)])
            return

        lbl.after(0, lambda: lbl.config(text=f"Building {total} PDF(s)…"))
        try:
            # Cap workers: one process per core each holding a decompressed
            # broadsheet page is an easy way to swap a 4 GB newsroom PC.
            workers = max(1, min(4, (os.cpu_count() or 2)))
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
                futures = [ex.submit(process_single_pdf_task, t) for t in tasks]
                for future in concurrent.futures.as_completed(futures):
                    completed += 1
                    try:
                        success, msg = future.result()
                    except Exception as e:
                        success, msg = False, f"❌ Worker crashed: {e}"
                    if success:
                        ok += 1
                    lbl.after(0, lambda m=msg: logger_func(m))

                    def update_prog(c=completed):
                        pbar["maximum"] = total
                        pbar["value"] = c
                        lbl.config(text=f"Progress: {c}/{total}")
                    lbl.after(0, update_prog)
        except Exception as e:
            lbl.after(0, lambda e=e: logger_func(f"❌ Engine failed: {e}"))

        elapsed = time.time() - start_time

        def finish():
            lbl.config(text=f"✅ {ok}/{total} in {elapsed:.1f}s")
            logger_func(f"✨ FINISHED — {ok}/{total} PDFs in {elapsed:.1f}s")
            btn.config(state="normal", bg=COLOR_ACCENT)
            if CFG.get("play_sound", True) and sys.platform == "win32":
                try:
                    import winsound
                    winsound.MessageBeep()
                except Exception:
                    pass
            if CFG.get("auto_open", True) and ok:
                out_path = os.path.join(folder, "OutputPDF")
                if os.path.exists(out_path):
                    try:
                        if sys.platform == "win32":
                            os.startfile(out_path)   # type: ignore[attr-defined]
                        else:
                            import subprocess
                            subprocess.Popen(["xdg-open", out_path])
                    except Exception as e:
                        logging.error(f"nab_pdf auto_open: {e}")
        lbl.after(0, finish)

    threading.Thread(target=run_in_thread, daemon=True).start()


# ---------- UI ELEMENTS ----------
def _f(size, bold=True):
    """Font tuple scaled for this screen (raw tk widgets don't get CTk's
    widget scaling)."""
    if nab_ui_scale:
        size = nab_ui_scale.scaled_font(size)
    return ("Segoe UI", size, "bold" if bold else "normal")


def create_rounded_button(parent, text, command, bg_color, text_color="#FFFFFF"):
    return Button(parent, text=text, command=command, bg=bg_color, fg=text_color,
                  font=_f(10), relief="flat", activebackground=bg_color,
                  activeforeground=text_color, padx=12, pady=6, bd=0)


class ImageHUD(Canvas):
    def __init__(self, master):
        super().__init__(master, bg="#000000", highlightthickness=0)
        self.log_lines = []
        self.max_lines = 15
        self.w, self.h = 800, 500
        self.bg_path = CFG.get("bg_image", "")
        self.orig_img = None
        self.photo = None
        self._resize_job = None

        self.text_id = self.create_text(
            30, 30, anchor="nw",
            text="> SYSTEM INITIALIZED\n> AWAITING COMMAND...",
            fill="#00FF00", font=("Consolas", _f(11)[1], "bold"))

        self.load_image()
        self.bind("<Configure>", self.on_resize)

    def load_image(self):
        if self.bg_path and os.path.exists(self.bg_path):
            try:
                self.orig_img = Image.open(self.bg_path).convert("RGB")
            except Exception:
                self.orig_img = None
        else:
            self.orig_img = None
        self.redraw_bg()

    def set_bg(self, path):
        self.bg_path = path
        CFG["bg_image"] = path
        save_config(CFG)
        self.load_image()

    def on_resize(self, event):
        if event.width <= 1 or event.height <= 1:
            return
        self.w, self.h = event.width, event.height
        # Debounce: a LANCZOS resize of a full-size photo on every pixel of a
        # window drag made the whole UI unusable while resizing.
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(120, self.redraw_bg)

    def redraw_bg(self):
        self._resize_job = None
        if self.orig_img and self.w > 1 and self.h > 1:
            try:
                resized = self.orig_img.resize((self.w, self.h),
                                               Image.Resampling.BILINEAR)
                self.photo = ImageTk.PhotoImage(resized)
                self.delete("bg")
                self.create_image(0, 0, image=self.photo, anchor="nw", tags="bg")
                self.tag_lower("bg")
            except Exception as e:
                logging.error(f"ImageHUD.redraw_bg: {e}")
        else:
            self.delete("bg")

    def write_log(self, message):
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {message}")
        if len(self.log_lines) > self.max_lines:
            self.log_lines = self.log_lines[-self.max_lines:]
        self.itemconfig(self.text_id, text="\n".join(self.log_lines))
        self.tag_raise(self.text_id)


# ---------- SETTINGS UI ----------
def open_smart_settings(root):
    win = Toplevel(root)
    win.title("PDF Maker — Settings")
    win.configure(bg=COLOR_BG)
    if nab_ui_scale:
        nab_ui_scale.fit(win, 900, 750, min_w=620, min_h=420, parent=root)
    else:
        win.geometry("900x750")

    style = Style()
    style.theme_use("clam")
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=COLOR_CARD, foreground=COLOR_TEXT,
                    padding=[12, 6], font=_f(10))
    style.map("TNotebook.Tab", background=[("selected", COLOR_ACCENT)],
              foreground=[("selected", COLOR_BG)])
    notebook = Notebook(win)
    notebook.pack(fill="both", expand=True, padx=14, pady=14)

    # 1. CATEGORIES
    tab_cat = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_cat, text=" 📁 Categories ")
    frame_c = Frame(tab_cat, bg=COLOR_CARD); frame_c.pack(fill="both", expand=True, padx=12, pady=12)
    lb_cat = Listbox(frame_c, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False))
    lb_cat.pack(side="left", fill="both", expand=True)
    for c in CFG["categories_to_process"]:
        lb_cat.insert("end", c)

    def add_c():
        if e_c.get().strip():
            lb_cat.insert("end", e_c.get().strip()); e_c.delete(0, "end")

    def del_c():
        if lb_cat.curselection():
            lb_cat.delete(lb_cat.curselection())
    btn_c = Frame(tab_cat, bg=COLOR_CARD); btn_c.pack(fill="x", padx=12, pady=8)
    create_rounded_button(btn_c, "Add", add_c, COLOR_SUCCESS).pack(side="right", padx=4)
    create_rounded_button(btn_c, "Del", del_c, COLOR_DANGER).pack(side="right", padx=4)
    e_c = Entry(btn_c, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False),
                insertbackground="white"); e_c.pack(side="right", padx=8, fill="y")

    # 2. PRIORITY
    tab_prio = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_prio, text=" 📰 Priority ")
    frame_p = Frame(tab_prio, bg=COLOR_CARD); frame_p.pack(fill="both", expand=True, padx=12, pady=12)
    lb_prio = Listbox(frame_p, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False))
    lb_prio.pack(side="left", fill="both", expand=True)
    for item in CFG["sort_order"]:
        lb_prio.insert("end", item)

    def move(d):
        pos = lb_prio.curselection()
        if not pos:
            return
        pos = pos[0]; text = lb_prio.get(pos)
        if d == -1 and pos > 0:
            lb_prio.delete(pos); lb_prio.insert(pos - 1, text); lb_prio.selection_set(pos - 1)
        elif d == 1 and pos < lb_prio.size() - 1:
            lb_prio.delete(pos); lb_prio.insert(pos + 1, text); lb_prio.selection_set(pos + 1)

    def add_p():
        if e_p.get().strip():
            lb_prio.insert("end", e_p.get().strip()); e_p.delete(0, "end")

    def del_p():
        if lb_prio.curselection():
            lb_prio.delete(lb_prio.curselection())
    btn_p = Frame(tab_prio, bg=COLOR_CARD); btn_p.pack(fill="x", padx=12, pady=8)
    create_rounded_button(btn_p, "▲", lambda: move(-1), COLOR_BG).pack(side="left", padx=2)
    create_rounded_button(btn_p, "▼", lambda: move(1), COLOR_BG).pack(side="left", padx=2)
    create_rounded_button(btn_p, "Add", add_p, COLOR_SUCCESS).pack(side="right", padx=4)
    create_rounded_button(btn_p, "Del", del_p, COLOR_DANGER).pack(side="right", padx=4)
    e_p = Entry(btn_p, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False),
                insertbackground="white"); e_p.pack(side="right", padx=8, fill="y")

    # 3. GROUPS
    tab_grp = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_grp, text=" 📂 Groups ")
    frame_g = Frame(tab_grp, bg=COLOR_CARD); frame_g.pack(fill="both", expand=True, padx=12, pady=12)
    frame_gl = Frame(frame_g, bg=COLOR_CARD); frame_gl.pack(side="left", fill="both", expand=True, padx=4)
    Label(frame_gl, text="Group Name", bg=COLOR_CARD, fg=COLOR_ACCENT, font=_f(9)).pack(pady=4)
    lb_grps = Listbox(frame_gl, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False))
    lb_grps.pack(fill="both", expand=True)
    frame_gr = Frame(frame_g, bg=COLOR_CARD); frame_gr.pack(side="right", fill="both", expand=True, padx=4)
    Label(frame_gr, text="Folders (comma separated)", bg=COLOR_CARD,
          fg=COLOR_ACCENT, font=_f(9)).pack(pady=4)
    txt_grps = Text(frame_gr, bg=COLOR_BG, fg=COLOR_TEXT, height=8, bd=0,
                    font=("Consolas", _f(10)[1])); txt_grps.pack(fill="both", expand=True)
    for k in CFG["combined_groups"]:
        lb_grps.insert("end", k)

    def on_grp_sel(_e):
        if not lb_grps.curselection():
            return
        g = lb_grps.get(lb_grps.curselection())
        txt_grps.delete("1.0", "end")
        txt_grps.insert("end", ", ".join(CFG["combined_groups"].get(g, [])))
    lb_grps.bind("<<ListboxSelect>>", on_grp_sel)

    def save_grp():
        if not lb_grps.curselection():
            return
        g = lb_grps.get(lb_grps.curselection())
        CFG["combined_groups"][g] = [x.strip() for x in
                                     txt_grps.get("1.0", "end").split(",") if x.strip()]
        # The old version popped "Saved" but never wrote the file — the edit
        # was lost unless you also happened to press SAVE ALL afterwards.
        ok = save_config(CFG)
        messagebox.showinfo("Saved" if ok else "Error",
                            "Group updated." if ok else "Could not write config file.",
                            parent=win)

    def add_grp():
        def cfm():
            n = e_gn.get().strip()
            if n:
                CFG["combined_groups"].setdefault(n, [])
                lb_grps.insert("end", n); save_config(CFG); win_g.destroy()
        win_g = Toplevel(win); win_g.configure(bg=COLOR_BG)
        if nab_ui_scale:
            nab_ui_scale.fit(win_g, 400, 160, parent=win)
        else:
            win_g.geometry("400x160")
        Label(win_g, text="New Group Name:", bg=COLOR_BG, fg=COLOR_TEXT, font=_f(10, False)).pack(pady=10)
        e_gn = Entry(win_g, width=40); e_gn.pack()
        create_rounded_button(win_g, "Create", cfm, COLOR_SUCCESS).pack(pady=10)

    def del_grp():
        if lb_grps.curselection():
            g = lb_grps.get(lb_grps.curselection())
            CFG["combined_groups"].pop(g, None)
            lb_grps.delete(lb_grps.curselection()); txt_grps.delete("1.0", "end")
            save_config(CFG)
    btn_g = Frame(tab_grp, bg=COLOR_CARD); btn_g.pack(fill="x", padx=12, pady=8)
    create_rounded_button(btn_g, "💾 Save Folders", save_grp, COLOR_ACCENT, COLOR_BG).pack(side="right", padx=4)
    create_rounded_button(btn_g, "🗑 Delete", del_grp, COLOR_DANGER).pack(side="left", padx=4)
    create_rounded_button(btn_g, "➕ New Group", add_grp, COLOR_SUCCESS).pack(side="left", padx=4)

    # 4. MERGE ONLY
    tab_mrg = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_mrg, text=" 🔕 Merge Only ")
    frame_m = Frame(tab_mrg, bg=COLOR_CARD); frame_m.pack(fill="both", expand=True, padx=12, pady=12)
    lb_mrg = Listbox(frame_m, bg=COLOR_BG, fg=COLOR_WARN, bd=0, font=_f(10, False))
    lb_mrg.pack(side="left", fill="both", expand=True)
    Label(frame_m, text="Included in GROUPS but\nskipped as a single PDF.",
          bg=COLOR_CARD, fg=COLOR_TEXT, font=_f(9, False)).pack(side="right", padx=10)
    for g in CFG.get("group_only", []):
        lb_mrg.insert("end", g)

    def add_m():
        if e_m.get().strip():
            lb_mrg.insert("end", e_m.get().strip()); e_m.delete(0, "end")

    def del_m():
        if lb_mrg.curselection():
            lb_mrg.delete(lb_mrg.curselection())
    btn_m = Frame(tab_mrg, bg=COLOR_CARD); btn_m.pack(fill="x", padx=12, pady=8)
    create_rounded_button(btn_m, "Add", add_m, COLOR_WARN).pack(side="right", padx=4)
    create_rounded_button(btn_m, "Del", del_m, COLOR_SUCCESS).pack(side="right", padx=4)
    e_m = Entry(btn_m, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False),
                insertbackground="white"); e_m.pack(side="right", padx=8, fill="y")

    # 5. BLACKLIST
    tab_blk = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_blk, text=" 🚫 Ignore ")
    frame_b = Frame(tab_blk, bg=COLOR_CARD); frame_b.pack(fill="both", expand=True, padx=12, pady=12)
    lb_blk = Listbox(frame_b, bg=COLOR_BG, fg=COLOR_DANGER, bd=0, font=_f(10, False))
    lb_blk.pack(side="left", fill="both", expand=True)
    Label(frame_b, text="Completely ignored.\nNo group, no single.",
          bg=COLOR_CARD, fg=COLOR_TEXT, font=_f(9, False)).pack(side="right", padx=10)
    for b in CFG.get("blacklist", []):
        lb_blk.insert("end", b)

    def add_b():
        if e_b.get().strip():
            lb_blk.insert("end", e_b.get().strip()); e_b.delete(0, "end")

    def del_b():
        if lb_blk.curselection():
            lb_blk.delete(lb_blk.curselection())
    btn_b = Frame(tab_blk, bg=COLOR_CARD); btn_b.pack(fill="x", padx=12, pady=8)
    create_rounded_button(btn_b, "Block", add_b, COLOR_DANGER).pack(side="right", padx=4)
    create_rounded_button(btn_b, "Allow", del_b, COLOR_SUCCESS).pack(side="right", padx=4)
    e_b = Entry(btn_b, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False),
                insertbackground="white"); e_b.pack(side="right", padx=8, fill="y")

    # 6. FILE NAMING
    tab_files = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_files, text=" 📝 Renamer ")
    file_frame = Frame(tab_files, bg=COLOR_CARD); file_frame.pack(fill="both", expand=True, padx=12, pady=12)
    frame_fl = Frame(file_frame, bg=COLOR_CARD); frame_fl.pack(side="left", fill="both", expand=True, padx=(0, 4))
    Label(frame_fl, text="Original Folder", bg=COLOR_CARD, fg=COLOR_ACCENT, font=_f(9)).pack(pady=4)
    lb_files = Listbox(frame_fl, bg=COLOR_BG, fg=COLOR_TEXT, bd=0, font=_f(10, False))
    lb_files.pack(fill="both", expand=True)
    frame_fr = Frame(file_frame, bg=COLOR_CARD); frame_fr.pack(side="right", fill="both", expand=True, padx=(4, 0))
    Label(frame_fr, text="New Filename Pattern", bg=COLOR_CARD, fg=COLOR_ACCENT, font=_f(9)).pack(pady=4)
    entry_pattern = Entry(frame_fr, bg=COLOR_BG, fg=COLOR_TEXT, bd=0,
                          font=("Consolas", _f(10)[1]), insertbackground="white")
    entry_pattern.pack(fill="x", pady=4)
    Label(frame_fr, text="Use {date} and {folder} as placeholders",
          bg=COLOR_CARD, fg="#64748B", font=_f(8, False)).pack()
    for k in CFG["custom_names"]:
        lb_files.insert("end", k)

    def on_file_select(_e):
        if not lb_files.curselection():
            return
        key = lb_files.get(lb_files.curselection())
        entry_pattern.delete(0, "end")
        entry_pattern.insert(0, CFG["custom_names"].get(key, ""))
    lb_files.bind("<<ListboxSelect>>", on_file_select)

    def save_file_map():
        if lb_files.curselection():
            key = lb_files.get(lb_files.curselection())
            CFG["custom_names"][key] = entry_pattern.get()
            ok = save_config(CFG)
            messagebox.showinfo("Saved" if ok else "Error",
                                "Rule updated." if ok else "Could not write config file.",
                                parent=win)

    def add_file_map():
        def confirm_add():
            folder, pat = e_f.get().strip(), e_pp.get().strip()
            if folder and pat:
                CFG["custom_names"][folder] = pat
                lb_files.insert("end", folder); save_config(CFG); add_win.destroy()
        add_win = Toplevel(win); add_win.configure(bg=COLOR_BG)
        if nab_ui_scale:
            nab_ui_scale.fit(add_win, 400, 220, parent=win)
        else:
            add_win.geometry("400x220")
        Label(add_win, text="Folder Name:", bg=COLOR_BG, fg=COLOR_TEXT, font=_f(10, False)).pack(pady=(12, 0))
        e_f = Entry(add_win, width=40); e_f.pack(pady=4)
        Label(add_win, text="Filename Pattern:", bg=COLOR_BG, fg=COLOR_TEXT, font=_f(10, False)).pack()
        e_pp = Entry(add_win, width=40); e_pp.pack(pady=4)
        create_rounded_button(add_win, "Add Rule", confirm_add, COLOR_SUCCESS).pack(pady=10)

    def del_file_map():
        if lb_files.curselection():
            key = lb_files.get(lb_files.curselection())
            CFG["custom_names"].pop(key, None)
            lb_files.delete(lb_files.curselection()); entry_pattern.delete(0, "end")
            save_config(CFG)
    file_btns = Frame(tab_files, bg=COLOR_CARD); file_btns.pack(fill="x", padx=12, pady=8)
    create_rounded_button(file_btns, "💾 Update", save_file_map, COLOR_ACCENT, COLOR_BG).pack(side="right", padx=4)
    create_rounded_button(file_btns, "🗑 Delete", del_file_map, COLOR_DANGER).pack(side="left", padx=4)
    create_rounded_button(file_btns, "➕ Add", add_file_map, COLOR_SUCCESS).pack(side="left", padx=4)

    # 7. GENERAL
    tab_gen = Frame(notebook, bg=COLOR_CARD); notebook.add(tab_gen, text=" ⚙ General ")
    var_open    = BooleanVar(value=CFG.get("auto_open", True))
    var_sound   = BooleanVar(value=CFG.get("play_sound", True))
    var_comp_en = BooleanVar(value=CFG.get("compress_enabled", True))
    var_smart   = BooleanVar(value=CFG.get("smart_compression", True))

    Checkbutton(tab_gen, text="Auto open output folder", variable=var_open,
                bg=COLOR_CARD, fg=COLOR_TEXT, selectcolor=COLOR_BG,
                font=_f(11, False)).pack(anchor="w", padx=24, pady=(16, 8))
    Checkbutton(tab_gen, text="Play completion sound", variable=var_sound,
                bg=COLOR_CARD, fg=COLOR_TEXT, selectcolor=COLOR_BG,
                font=_f(11, False)).pack(anchor="w", padx=24, pady=8)
    Frame(tab_gen, bg=COLOR_ACCENT, height=2).pack(fill="x", padx=18, pady=12)
    Checkbutton(tab_gen, text="Enable compression", variable=var_comp_en,
                bg=COLOR_CARD, fg=COLOR_ACCENT, selectcolor=COLOR_BG,
                font=_f(12)).pack(anchor="w", padx=24, pady=(8, 4))
    Checkbutton(tab_gen, text="Smart mode (compress only files over 400 KB)",
                variable=var_smart, bg=COLOR_CARD, fg=COLOR_TEXT,
                selectcolor=COLOR_BG, font=_f(11, False)).pack(anchor="w", padx=42, pady=4)
    Label(tab_gen, text="Manual quality (used when Smart mode is off):",
          bg=COLOR_CARD, fg="#94A3B8", font=_f(10, False)).pack(anchor="w", padx=42, pady=(8, 0))
    qual_val = IntVar(value=CFG.get("manual_quality", 65))
    Scale(tab_gen, from_=10, to=95, orient="horizontal", variable=qual_val,
          length=340, bg=COLOR_CARD, fg=COLOR_TEXT,
          highlightthickness=0).pack(anchor="w", padx=42)

    def save_all():
        CFG["categories_to_process"] = list(lb_cat.get(0, "end"))
        CFG["sort_order"]            = list(lb_prio.get(0, "end"))
        CFG["group_only"]            = list(lb_mrg.get(0, "end"))
        CFG["blacklist"]             = list(lb_blk.get(0, "end"))
        CFG["auto_open"]             = var_open.get()
        CFG["play_sound"]            = var_sound.get()
        CFG["compress_enabled"]      = var_comp_en.get()
        CFG["smart_compression"]     = var_smart.get()
        CFG["manual_quality"]        = qual_val.get()
        if save_config(CFG):
            messagebox.showinfo("Saved", f"Settings written to:\n{CONFIG_FILE}", parent=win)
            win.destroy()
        else:
            messagebox.showerror("Error", "Could not write the config file.", parent=win)
    create_rounded_button(win, "SAVE ALL SETTINGS", save_all, COLOR_SUCCESS).pack(pady=14, ipadx=18)


# ---------- MAIN ----------
def _todays_folder():
    """NAB's folder for today, so the picker doesn't open in My Documents
    every single time."""
    try:
        base = nab_base_root()
        now = _dt.datetime.now()
        p = os.path.join(base, now.strftime("%Y"), now.strftime("%B"),
                         now.strftime("%d-%m-%Y"))
        if os.path.isdir(p):
            return p
        if os.path.isdir(base):
            return base
    except Exception:
        pass
    return os.path.expanduser("~")


def main():
    multiprocessing.freeze_support()
    try:
        if nab_ui_scale:
            nab_ui_scale.enable_dpi_awareness()

        root = tk.Tk()
        root.title("NAB — PDF Maker")
        root.configure(bg=COLOR_BG)
        if nab_ui_scale:
            nab_ui_scale.fit(root, 950, 800, min_w=620, min_h=460)
        else:
            root.geometry("950x800")

        head = Frame(root, bg=COLOR_BG); head.pack(fill="x", pady=(14, 6))
        Label(head, text="PDF MAKER", font=("Impact", _f(28)[1]),
              bg=COLOR_BG, fg=COLOR_ACCENT).pack()
        Label(head, text="• NAB •", font=("Impact", _f(10)[1]),
              bg=COLOR_BG, fg="#fff700").pack()

        cinema = ImageHUD(root)
        cinema.pack(fill="both", expand=True, padx=14, pady=8)

        style = Style(); style.theme_use("clam")
        style.configure("Horizontal.TProgressbar", troughcolor=COLOR_BG,
                        background=COLOR_ACCENT, thickness=6, borderwidth=0)
        pbar = Progressbar(root, orient="horizontal", mode="determinate",
                           style="Horizontal.TProgressbar")
        pbar.pack(fill="x", padx=14, pady=10)

        lbl = Label(root, text="AWAITING COMMAND", font=_f(10),
                    bg=COLOR_BG, fg="#64748B")
        lbl.pack(pady=(0, 6))

        def change_bg():
            path = filedialog.askopenfilename(
                filetypes=[("Image Files", "*.png *.jpg *.jpeg")])
            if path:
                cinema.set_bg(path)

        foot = Frame(root, bg=COLOR_BG); foot.pack(fill="x", pady=14, padx=18)
        btn_run = create_rounded_button(foot, "🚀 START ENGINE", lambda: None,
                                        COLOR_ACCENT, COLOR_BG)
        btn_run.pack(side="left", fill="x", expand=True, padx=4)
        create_rounded_button(foot, "🖼️ SET BG", change_bg, COLOR_CARD)\
            .pack(side="left", fill="x", expand=True, padx=4)
        create_rounded_button(foot, "⚙ SETTINGS", lambda: open_smart_settings(root),
                              COLOR_CARD).pack(side="right", fill="x", expand=True, padx=4)

        def start_logic():
            f = filedialog.askdirectory(title="Pick the day folder",
                                        initialdir=_todays_folder())
            if f:
                start_processing(f, cinema.write_log, pbar, lbl, btn_run)
        btn_run.config(command=start_logic)

        # --auto-folder <path>: launched from NAB's "📅 PDF for Today" button.
        # Skips the folder picker entirely and starts processing the moment
        # the window is up, instead of making the operator browse to the
        # same day folder they'd pick every single day anyway.
        auto_folder = None
        if "--auto-folder" in sys.argv:
            idx = sys.argv.index("--auto-folder")
            if idx + 1 < len(sys.argv):
                auto_folder = sys.argv[idx + 1]
        if auto_folder and os.path.isdir(auto_folder):
            root.after(300, lambda: start_processing(
                auto_folder, cinema.write_log, pbar, lbl, btn_run))
        elif auto_folder:
            cinema.write_log(f"❌ Folder not found: {auto_folder}")

        root.mainloop()
    except Exception as e:
        logging.error(f"nab_pdf.main: {e}")
        try:
            messagebox.showerror("PDF Maker failed to start", str(e))
        except Exception:
            print(f"CRITICAL UI ERROR: {e}")


if __name__ == "__main__":
    main()
