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
        return {"ok": True, "folders": self.idx["folders"], "lang": self.idx["lang"], "count": len(self.idx["files"]), "running": self.running, "tess_error": err}

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
                            self.idx["files"][p] = {"m": m, "s": s, "l": lang, "t": _norm(f.result())}
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

    def api_find(self, a):
        words = [_norm(w) for w in re.split(r"[,\n]", a.get("q") or "") if _norm(w)]
        if not words:
            return {"ok": False, "error": "Type a keyword."}
        all_ = bool(a.get("all"))
        d1, d2 = a.get("from") or "", a.get("to") or ""
        out = []
        for p, v in self.idx["files"].items():
            t = v.get("t", "")
            hits = [w for w in words if w in t]
            if not hits or (all_ and len(hits) < len(words)):
                continue
            dt = _date(p)
            if (d1 and dt and dt < d1) or (d2 and dt and dt > d2):
                continue
            i = t.find(hits[0]); sn = ("…" if i > 60 else "") + t[max(0, i - 60): i + 100] + "…"
            out.append({"path": p, "name": os.path.basename(p), "date": dt, "hits": hits, "snip": sn})
        out.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
        return {"ok": True, "results": out[:500], "total": len(out)}

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
