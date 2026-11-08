# nab_tool_pdf.py — PDF Maker inside the web UI (replaces the separate Tk window).
# Logic is the same as nab_pdf.py (longest-name-first sort, combined groups, per-subfolder PDFs, smart compression)
# but runs in a thread pool inside NAB (no second Tk root, no process pool — those can't live inside the frozen EXE).
import os
import re
import io
import sys
import json
import time
import logging
import threading
import datetime as _dt
import concurrent.futures

import nab_engine

CONFIG_FILE = os.path.join(nab_engine.DOC_DIR, "nab_pdf_config.json")

DEFAULT_CONFIG = {
    "sort_order": ["Daily Star", "TBS", "Financial Express", "Daily Observer", "Dhaka Tribune", "New Age", "Daily Sun",
                   "New Nation", "Asian Age", "Bangladesh Today", "TOB", "Prothom Alo", "Samakal", "Ittefaq", "Jugantor",
                   "Kaler Kantha", "Janakantha", "Naya Diganta", "Daily Inqilab", "Bonik Barta", "Bangladesh Pratidin",
                   "Sangbad", "Jaijaidin", "Manabzamin", "Amader Shomoy", "Sharebiz", "Ajker Patrika",
                   "Protidiner Bangladesh", "Shomoyer Alo", "Pratidiner Sangbad", "Desh Rupantor", "Kalbela",
                   "Rupali Bangladesh", "Khoborer Kagoj", "Amardesh", "Alokito Bangladesh"],
    "custom_names": {
        "Bank": "Bank news media monitoring report on {date}",
        "Economy": "Economy news media monitoring report on {date}",
        "Finance": "Finance news media monitoring report on {date}",
        "LPG": "LPG news media monitoring report on {date}",
        "LNG": "LNG news media monitoring report on {date}",
        "Power": "Power news media monitoring report on {date}",
    },
    "combined_groups": {
        "Banking & Finance news media monitoring report on {date}": ["Bank", "Economy", "Finance"],
        "Power, Energy & Mineral news media monitoring report on {date}": ["LPG", "LNG", "Power"],
    },
    "categories_to_process": ["Beximco", "Mineral", "Pride Group", "United Group"],
    "generic_pattern": "{folder} news media monitoring report on {date}.pdf",
    "blacklist": ["Old_Data", "Temp", "Backup", "OutputPDF"],
    "group_only": ["Economy", "Finance", "LPG"],
    "auto_open": True,
    "compress_enabled": True,
    "smart_compression": True,
    "manual_quality": 65,
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                cfg.update({k: v for k, v in saved.items() if v is not None})
    except Exception as e:
        logging.error(f"nab_tool_pdf.load_config: {e}")
    return cfg


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"nab_tool_pdf.save_config: {e}")
        return False


def detect_date(folder):
    m = re.search(r"\d{2}-\d{2}-\d{4}", folder)
    if not m:
        return folder
    try:
        return _dt.datetime.strptime(m.group(0), "%d-%m-%Y").strftime("%B %d, %Y")
    except Exception:
        return m.group(0)


def make_sorter(sort_order):
    ranked = sorted(((n.lower().replace("_", " ").replace("-", " "), i) for i, n in enumerate(sort_order) if n.strip()),
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
        return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    except OSError:
        return []


def build_tasks(day_folder, cfg):
    date_str = detect_date(os.path.basename(os.path.normpath(day_folder)))
    out_dir = os.path.join(day_folder, "OutputPDF")
    comp = cfg.get("compress_enabled", True)
    smart = cfg.get("smart_compression", True)
    qual = int(cfg.get("manual_quality", 65) or 65)
    black = {b.lower() for b in cfg.get("blacklist", [])}
    gonly = {g.lower() for g in cfg.get("group_only", [])}
    key = make_sorter(cfg.get("sort_order", []))
    tasks = []
    for cat in cfg.get("categories_to_process", []):
        if cat.lower() in black:
            continue
        cp = os.path.join(day_folder, cat)
        if not os.path.isdir(cp):
            continue
        j = _images_in(cp)
        if j:
            j.sort(key=key)
            tasks.append((j, os.path.join(out_dir, f"{cat} news media monitoring report on {date_str}.pdf"), comp, smart, qual))
        for pattern, groups in cfg.get("combined_groups", {}).items():
            cj = []
            for g in groups:
                if g.lower() in black:
                    continue
                p = os.path.join(cp, g)
                if os.path.isdir(p):
                    cj.extend(_images_in(p))
            if cj:
                cj.sort(key=key)
                try:
                    name = pattern.format(date=date_str)
                except (KeyError, IndexError, ValueError):
                    name = pattern
                if not name.lower().endswith(".pdf"):
                    name += ".pdf"
                tasks.append((cj, os.path.join(out_dir, name), comp, smart, qual))
        try:
            subs = sorted(d for d in os.listdir(cp) if os.path.isdir(os.path.join(cp, d)) and d.lower() not in black)
        except OSError:
            subs = []
        for sf in subs:
            if sf.lower() in gonly:
                continue
            j = _images_in(os.path.join(cp, sf))
            if not j:
                continue
            j.sort(key=key)
            pat = cfg.get("custom_names", {}).get(sf, cfg.get("generic_pattern", "{folder} {date}.pdf"))
            try:
                name = pat.format(folder=sf, date=date_str)
            except (KeyError, IndexError, ValueError):
                name = f"{sf} {date_str}"
            if not name.lower().endswith(".pdf"):
                name += ".pdf"
            tasks.append((j, os.path.join(out_dir, name), comp, smart, qual))
    if tasks:
        os.makedirs(out_dir, exist_ok=True)
    return tasks


def render_pdf(task):
    from PIL import Image
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    files, out, comp, smart, qual = task
    name = os.path.basename(out)
    if not files:
        return False, f"Skipped (no images): {name}", 0
    failed = []
    try:
        pw, ph = A4
        c = pdf_canvas.Canvas(out, pagesize=A4)
        c.setTitle(os.path.splitext(name)[0])
        pages = 0
        for jpg in files:
            try:
                do, tw, tq = False, 1600, 65
                if comp:
                    if smart:
                        do = os.path.getsize(jpg) > 400 * 1024
                    else:
                        do, tq = True, qual
                        tw = 2500 if qual > 80 else (1600 if qual > 50 else 1000)
                if do:
                    with Image.open(jpg) as im:
                        im = im.convert("RGB") if im.mode != "RGB" else im
                        w, h = im.size
                        if w > tw:
                            im = im.resize((tw, max(1, int(h * tw / float(w)))), Image.Resampling.LANCZOS)
                        buf = io.BytesIO()
                        im.save(buf, format="JPEG", quality=tq, optimize=True)
                        buf.seek(0)
                        obj = ImageReader(buf)
                else:
                    obj = ImageReader(jpg)
                wpx, hpx = obj.getSize()
                sc = min(pw / wpx, ph / hpx, 1.0)
                dw, dh = wpx * sc, hpx * sc
                c.setFillColorRGB(1, 1, 1)
                c.rect(0, 0, pw, ph, fill=1, stroke=0)
                c.drawImage(obj, (pw - dw) / 2, (ph - dh) / 2, dw, dh, preserveAspectRatio=True, anchor="c")
                c.showPage()
                pages += 1
            except Exception as e:
                failed.append(f"{os.path.basename(jpg)} ({type(e).__name__})")
        if pages == 0:
            return False, f"{name}: every page failed ({len(failed)} image(s))", 0
        c.save()
        if failed:
            more = f" +{len(failed) - 3} more" if len(failed) > 3 else ""
            return True, f"{name} — {pages} page(s), SKIPPED: {', '.join(failed[:3])}{more}", pages, "warn"
        return True, f"{name} — {pages} page(s)", pages
    except Exception as e:
        return False, f"{name}: {type(e).__name__}: {e}", 0


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.running = False
        self.lock = threading.Lock()

    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="pdf", **kw)

    def _day_path(self, d):
        return os.path.join(self.e.base_root, d.strftime("%Y"), d.strftime("%B"), d.strftime("%d-%m-%Y"))

    def api_days(self, a):
        """Day folders that exist in the archive, newest first (last ~45), with how many images each has."""
        out, seen = [], set()
        today = _dt.date.today()
        for i in range(0, 45):
            d = today - _dt.timedelta(days=i)
            p = self._day_path(d)
            if os.path.isdir(p):
                out.append({"path": p, "label": d.strftime("%a %d %b %Y"), "date": d.isoformat(), "pdf": os.path.isdir(os.path.join(p, "OutputPDF"))})
                seen.add(p)
        return {"ok": True, "days": out, "today": self._day_path(today), "base": self.e.base_root}

    def api_preview(self, a):
        p = (a.get("path") or "").strip().strip('"')
        if not os.path.isdir(p):
            return {"ok": False, "error": "That folder doesn't exist."}
        try:
            tasks = build_tasks_dry(p, load_config())
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "items": tasks}

    def api_config(self, a):
        return {"ok": True, "cfg": load_config(), "defaults": DEFAULT_CONFIG}

    def api_config_save(self, a):
        cfg = load_config()
        new = a.get("cfg") or {}
        for k in DEFAULT_CONFIG:
            if k in new:
                cfg[k] = new[k]
        if not isinstance(cfg.get("manual_quality"), int):
            try:
                cfg["manual_quality"] = max(10, min(100, int(cfg["manual_quality"])))
            except Exception:
                cfg["manual_quality"] = 65
        return {"ok": save_config(cfg)}

    def api_config_reset(self, a):
        return {"ok": save_config(DEFAULT_CONFIG), "cfg": DEFAULT_CONFIG}

    def api_start(self, a):
        p = (a.get("path") or "").strip().strip('"')
        if not os.path.isdir(p):
            return {"ok": False, "error": "That folder doesn't exist."}
        with self.lock:
            if self.running:
                return {"ok": False, "error": "A PDF job is already running."}
            self.running = True
        threading.Thread(target=self._work, args=(p,), daemon=True, name="NAB-PDF").start()
        return {"ok": True}

    def _work(self, folder):
        t0 = time.time()
        ok = done = 0
        try:
            cfg = load_config()
            self._emit(ev="scan", text="Scanning folder…")
            tasks = build_tasks(folder, cfg)
            total = len(tasks)
            if not total:
                self._emit(ev="done", ok=0, total=0, msg="No PDFs to create — check the folder, Categories and Blacklist in Settings.")
                return
            self._emit(ev="begin", total=total)
            workers = max(1, min(4, (os.cpu_count() or 2)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(render_pdf, t) for t in tasks]
                for f in concurrent.futures.as_completed(futs):
                    done += 1
                    try:
                        r = f.result()
                    except Exception as e:
                        r = (False, f"Worker crashed: {e}", 0)
                    good, msg = r[0], r[1]
                    lvl = "warn" if (len(r) > 3 and r[3] == "warn") else ("ok" if good else "bad")
                    if good:
                        ok += 1
                    self._emit(ev="item", n=done, total=total, ok=good, level=lvl, msg=msg)
            out = os.path.join(folder, "OutputPDF")
            self._emit(ev="done", ok=ok, total=total, secs=round(time.time() - t0, 1), out=out)
            if cfg.get("auto_open", True) and ok and os.path.isdir(out):
                self.e.reveal(out)
        except Exception as e:
            logging.exception("pdf job")
            self._emit(ev="done", ok=ok, total=0, msg=f"Failed: {e}")
        finally:
            self.running = False

    def api_open(self, a):
        return self.e.reveal(a.get("path"))


def build_tasks_dry(folder, cfg):
    """Preview: what would be made, without writing anything."""
    date_str = detect_date(os.path.basename(os.path.normpath(folder)))
    out = []
    import tempfile
    # build_tasks creates OutputPDF only when there are tasks; do the same walk without that side effect
    black = {b.lower() for b in cfg.get("blacklist", [])}
    gonly = {g.lower() for g in cfg.get("group_only", [])}
    for cat in cfg.get("categories_to_process", []):
        if cat.lower() in black:
            continue
        cp = os.path.join(folder, cat)
        if not os.path.isdir(cp):
            continue
        n = len(_images_in(cp))
        if n:
            out.append({"name": f"{cat} news media monitoring report on {date_str}.pdf", "pages": n})
        for pattern, groups in cfg.get("combined_groups", {}).items():
            n = sum(len(_images_in(os.path.join(cp, g))) for g in groups if g.lower() not in black and os.path.isdir(os.path.join(cp, g)))
            if n:
                try:
                    nm = pattern.format(date=date_str)
                except (KeyError, IndexError, ValueError):
                    nm = pattern
                out.append({"name": nm if nm.lower().endswith(".pdf") else nm + ".pdf", "pages": n})
        try:
            subs = sorted(d for d in os.listdir(cp) if os.path.isdir(os.path.join(cp, d)) and d.lower() not in black)
        except OSError:
            subs = []
        for sf in subs:
            if sf.lower() in gonly:
                continue
            n = len(_images_in(os.path.join(cp, sf)))
            if n:
                pat = cfg.get("custom_names", {}).get(sf, cfg.get("generic_pattern", "{folder} {date}.pdf"))
                try:
                    nm = pat.format(folder=sf, date=date_str)
                except (KeyError, IndexError, ValueError):
                    nm = f"{sf} {date_str}"
                out.append({"name": nm if nm.lower().endswith(".pdf") else nm + ".pdf", "pages": n})
    return out
