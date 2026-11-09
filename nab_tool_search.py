# nab_tool_search.py — OCR search over saved clips, inside the web UI (compact port of image_ocr_finder.py).
# Own index: Documents\nab_ocr_index.json  {"folders":[...], "lang":"eng+ben", "files":{path:{m,s,t}}}
import os
import re
import json
import time
import logging
import threading
import concurrent.futures

import nab_engine
import nab_archive

INDEX_FILE = os.path.join(nab_engine.DOC_DIR, "nab_ocr_index.json")
EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
DATE_RX = re.compile(r"(\d{2})-(\d{2})-(\d{4})")
WIN_TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()


def _tess():
    try:
        import pytesseract
    except Exception:
        return None, "pytesseract is not installed in this build."
    if os.name == "nt" and os.path.exists(WIN_TESS):
        pytesseract.pytesseract.tesseract_cmd = WIN_TESS
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return None, "Tesseract OCR is not installed. Install it from github.com/UB-Mannheim/tesseract/wiki (tick Bengali), then reopen Search."
    return pytesseract, ""


def _ocr(path, lang):
    from PIL import Image, ImageOps
    import pytesseract
    with Image.open(path) as im:
        im = im.convert("L")
        w, h = im.size
        if max(w, h) < 2000:
            k = 2000 / max(w, h)
            im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
        im = ImageOps.autocontrast(im)
        return pytesseract.image_to_string(im, lang=lang, config="--oem 1 --psm 6")


def _date(path):
    m = DATE_RX.findall(path)
    if not m:
        return ""
    d, mo, y = m[-1]
    return f"{y}-{mo}-{d}"


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.Lock()
        self.running = False
        self.stop = False
        self.idx = self._load()
        if not self.idx["folders"]:
            self.idx["folders"] = [self.e.base_root]
        self.arch = nab_archive.get()
        self._scanning = False
        try:                                    # first run after the update: take the old OCR text over, no re-reading
            if self.arch.count() == 0 and self.idx["files"]:
                self.arch.scan(self.idx["folders"], self.e.base_root)
                n = self.arch.import_legacy_ocr(self.idx["files"])
                logging.info(f"archive: imported OCR text for {n} clips")
        except Exception as e:
            logging.error(f"archive import: {e}")

    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="search", **kw)

    def _load(self):
        try:
            with open(INDEX_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and "files" in d:
                d.setdefault("folders", []); d.setdefault("lang", "eng+ben")
                return d
        except Exception:
            pass
        return {"folders": [], "files": {}, "lang": "eng+ben"}

    def _save(self):
        try:
            tmp = INDEX_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.idx, f, ensure_ascii=False)
            os.replace(tmp, INDEX_FILE)
        except Exception as e:
            logging.error(f"ocr index save: {e}")

    def api_state(self, a):
        _t, err = _tess()
        return {"ok": True, "folders": self.idx["folders"], "lang": self.idx["lang"], "count": self.arch.count(), "ocr_count": len(self.idx["files"]),
                "running": self.running, "scanning": self._scanning, "tess_error": err, "fts": self.arch.fts}

    def api_folders(self, a):
        fs = [f.strip().strip('"') for f in (a.get("folders") or []) if f.strip()]
        self.idx["folders"] = fs
        self.idx["lang"] = a.get("lang") if a.get("lang") in ("eng", "ben", "eng+ben") else "eng+ben"
        self._save()
        return {"ok": True}

    def api_index(self, a):
        _t, err = _tess()
        if err:
            return {"ok": False, "error": err}
        with self.lock:
            if self.running:
                return {"ok": False, "error": "Already indexing."}
            self.running = True
            self.stop = False
        threading.Thread(target=self._work, daemon=True, name="NAB-OCR").start()
        return {"ok": True}

    def api_stop(self, a):
        self.stop = True
        return {"ok": True}

    def _work(self):
        lang = self.idx.get("lang", "eng+ben")
        try:
            todo, seen = [], set()
            for folder in self.idx["folders"]:
                for root, _d, files in os.walk(folder):
                    for n in files:
                        if os.path.splitext(n)[1].lower() in EXTS:
                            p = os.path.join(root, n)
                            seen.add(p)
                            try:
                                st = os.stat(p)
                            except OSError:
                                continue
                            old = self.idx["files"].get(p)
                            if not old or old.get("m") != int(st.st_mtime) or old.get("s") != st.st_size or old.get("l") != lang:
                                todo.append((p, int(st.st_mtime), st.st_size))
            for p in [p for p in self.idx["files"] if p not in seen and any(p.startswith(f) for f in self.idx["folders"])]:
                self.idx["files"].pop(p, None)
            total = len(todo)
            self._emit(ev="begin", total=total)
            done = 0
            workers = max(1, min(8, os.cpu_count() or 2))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {}
                it = iter(todo)
                def feed():
                    for t in it:
                        futs[ex.submit(_ocr, t[0], lang)] = t
                        if len(futs) >= workers * 2:
                            return
                feed()
                while futs:
                    d, _ = concurrent.futures.wait(list(futs), return_when=concurrent.futures.FIRST_COMPLETED)
                    for f in d:
                        p, m, s = futs.pop(f)
                        try:
                            txt = _norm(f.result())
                            self.idx["files"][p] = {"m": m, "s": s, "l": lang, "t": txt}
                            self.arch.upsert(p, self.e.base_root)
                            self.arch.set_ocr(p, txt)
                        except Exception as e:
                            self.idx["files"][p] = {"m": m, "s": s, "l": lang, "t": "", "err": str(e)[:80]}
                        done += 1
                        if done % 5 == 0 or done == total:
                            self._emit(ev="prog", n=done, total=total, name=os.path.basename(p))
                    if self.stop:
                        for f in futs:
                            f.cancel()
                        break
                    feed()
            self._save()
            self._emit(ev="done", n=done, total=total, stopped=self.stop, count=len(self.idx["files"]))
        except Exception as e:
            logging.exception("ocr index")
            self._emit(ev="done", n=0, total=0, error=str(e), count=len(self.idx["files"]))
        finally:
            self.running = False

    def _flt(self, a):
        return {k: (a.get(k) or "").strip() for k in ("paper", "cat", "page", "user", "date_from", "date_to")}

    def api_find(self, a):
        q = a.get("q") or ""
        flt = self._flt(a)
        if not q.strip() and not any(flt.values()):
            return {"ok": False, "error": "Type a keyword or pick a filter."}
        r = self.arch.search(q, bool(a.get("all")), 500, **flt)
        return {"ok": True, "results": r["rows"], "total": r["total"], "more": r["more"]}

    def api_scan(self, a):
        """Fast pass: read file names and folders, no OCR. Safe to run any time."""
        if self._scanning:
            return {"ok": True, "busy": True}
        self._scanning = True

        def work():
            try:
                def prog(n, t, name):
                    self._emit(ev="scan", n=n, total=t, name=name)
                r = self.arch.scan(self.idx["folders"], self.e.base_root, progress=prog)
                self._emit(ev="scan_done", **r)
            except Exception as ex:
                logging.exception("archive scan")
                self._emit(ev="scan_done", error=str(ex), total=self.arch.count())
            finally:
                self._scanning = False
        threading.Thread(target=work, daemon=True, name="NAB-Scan").start()
        return {"ok": True}

    def api_facets(self, a):
        return dict(self.arch.facets(), ok=True, saved=self.arch.saved_list())

    def api_dups(self, a):
        return {"ok": True, "groups": self.arch.duplicate_groups(int(a.get("dist", 2) or 2))}

    def api_saved_put(self, a):
        return {"ok": self.arch.saved_put(a.get("name"), a.get("query")), "saved": self.arch.saved_list()}

    def api_saved_delete(self, a):
        self.arch.saved_delete(a.get("name") or "")
        return {"ok": True, "saved": self.arch.saved_list()}

    def api_export(self, a):
        q = a.get("q") or ""
        r = self.arch.search(q, bool(a.get("all")), 20000, **self._flt(a))
        if not r["rows"]:
            return {"ok": False, "error": "Nothing to export."}
        folder = os.path.join(os.path.expanduser("~"), "Documents", "NAB Exports")
        p = self.arch.export(r["rows"], folder, "csv" if a.get("kind") == "csv" else "xlsx")
        try:
            import nab_accounts
            nab_accounts.audit("export", f"{len(r['rows'])} clips -> {os.path.basename(p)}")
        except Exception:
            pass
        return {"ok": True, "path": p, "n": len(r["rows"])}

    def api_delete_files(self, a):
        """Delete the given clip files (used by the duplicate screen). Only files that are in the archive."""
        n = 0
        for p in a.get("paths") or []:
            try:
                if self.arch.has(p) and os.path.isfile(p):          # only files the archive knows about
                    os.remove(p); self.arch.remove(p); n += 1
                    try:
                        import nab_accounts
                        nab_accounts.audit("delete_clip", os.path.basename(p))
                    except Exception:
                        pass
            except Exception as ex:
                logging.error(f"delete {p}: {ex}")
        return {"ok": True, "n": n}

    def api_open(self, a):
        p = a.get("path") or ""
        if not os.path.isfile(p):
            return {"ok": False, "error": "File not found."}
        try:
            if os.name == "nt":
                os.startfile(p)
            else:
                import subprocess; subprocess.Popen(["xdg-open", p])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def api_reveal(self, a):
        return self.e.reveal(os.path.dirname(a.get("path") or ""))

    def api_copy(self, a):
        import shutil
        dest = (a.get("dest") or "").strip().strip('"')
        if not dest:
            return {"ok": False, "error": "Enter a destination folder."}
        os.makedirs(dest, exist_ok=True)
        n = 0
        for p in a.get("paths") or []:
            if os.path.isfile(p):
                b, ext = os.path.splitext(os.path.basename(p)); t = os.path.join(dest, b + ext); k = 1
                while os.path.exists(t):
                    t = os.path.join(dest, f"{b} ({k}){ext}"); k += 1
                shutil.copy2(p, t); n += 1
        return {"ok": True, "n": n}
