# nab_extras.py — v3.0.4 engine features, kept in one mixin so the core files stay readable.
#   per-paper defaults · page-from-ePaper hints · detection test · extension light · learn-this-paper
#   local settings backups · crash-safe draft · copy last saved · inch calibration · clean-up memory
#   first-run guide status · slow-PC detection · missed-save guard
import io
import os
import re
import sys
import json
import time
import shutil
import zipfile
import logging
import datetime
import threading

from PIL import Image

import nab_core
import nab_clipboard

_BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_PAGE_OK = re.compile(r"^(?:[A-Z]{1,2}\d{1,3}|\d{1,3}[A-Z]?)$")
_PAGE_PATTERNS = [
    re.compile(r"[?&#](?:page|pg|pageno|page_no|pagenumber|pagenum|p)=([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)(?:[&#]|$)", re.I),
    re.compile(r"/(?:page|pg|pages|p)[-_/ ]?([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)(?:[/?#._-]|$)", re.I),
    re.compile(r"(?:page|pg|পৃষ্ঠা|পাতা)[\s\-:#.]*([A-Za-z]{0,2}\d{1,3}[A-Za-z]?)", re.I),
]


def _local_dir():
    base = os.environ.get("LOCALAPPDATA")
    if base and os.path.isdir(base):
        return os.path.join(base, "NAB")
    from nab_engine import DOC_DIR
    return os.path.join(DOC_DIR, ".nab_local")


class ExtrasMixin:
    # ───────────────────────────── per-paper defaults ───────────────────────
    DEFAULT_PAPER_OPTS = {"autotrim": None, "clean": False, "out_width": 0, "target_kb": 0, "ppi": 0,
                          "page_regex": "", "cleanup": []}

    def _pd_all(self):
        return self.extra_settings.setdefault("paper_defaults", {})

    def paper_opts(self, paper=None):
        key = (paper or self.paper_clean or "").strip().lower()
        o = dict(self.DEFAULT_PAPER_OPTS)
        for k, v in self._pd_all().items():
            if k.lower() == key:
                o.update(v)
                break
        return o

    def paper_defaults_get(self):
        return {"ok": True, "papers": [re.sub(r"^[^\w]+", "", p, flags=re.U).strip() or p for p in self.paper_list],
                "defaults": self._pd_all(), "smart_trim": self.extra_settings.get("smart_trim", True)}

    def paper_defaults_set(self, paper, **kw):
        key = (paper or "").strip()
        if not key:
            return {"ok": False, "error": "No paper."}
        cur = dict(self._pd_all().get(key, {}))
        for k in ("autotrim", "clean"):
            if k in kw:
                cur[k] = None if kw[k] is None else bool(kw[k])
        for k in ("out_width", "target_kb"):
            if k in kw:
                cur[k] = max(0, int(kw[k] or 0))
        if "ppi" in kw:
            cur["ppi"] = max(0.0, float(kw["ppi"] or 0))
        if "page_regex" in kw:
            rx = (kw["page_regex"] or "").strip()
            if rx:
                try:
                    re.compile(rx)
                except re.error as e:
                    return {"ok": False, "error": f"Bad pattern: {e}"}
            cur["page_regex"] = rx
        self._pd_all()[key] = cur
        self.save_settings()
        self.hub.emit("settings_changed")
        return {"ok": True}

    # ───────────────────────────── paste: smart trim (instant) ──────────────
    def post_paste(self, layers_imgs):
        """Called right after clips were added. The layer is already on screen (instant paste);
        trim / clean run on a worker and swap the pixels in only if the layer was not touched."""
        po = self.paper_opts()
        do_trim = po["autotrim"] if po["autotrim"] is not None else self.extra_settings.get("smart_trim", True)
        do_clean = bool(po["clean"])
        if not (do_trim or do_clean) or self.auto_polish:
            return

        def work():
            for layer, orig in layers_imgs:
                try:
                    out = orig
                    if do_clean:
                        out = nab_core.cv_remove_lines(out)
                    if do_trim:
                        out = nab_core.auto_trim(out)
                    if out is orig or out.size == orig.size and out.tobytes() == orig.tobytes():
                        continue
                    with self.doc.lock:
                        if layer in self.doc.layers and layer.img is orig:
                            layer.set_img(out)
                            self.doc.touch()
                except Exception as e:
                    logging.error(f"post_paste: {e}")
            self._preview_cache = None
            self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
        threading.Thread(target=work, daemon=True, name="NAB-PostPaste").start()

    # ───────────────────────────── cleanup memory ───────────────────────────
    def cleanup_save(self, layer_id, shape):
        """Remember a rectangle (as fractions of the clip) to erase on this paper."""
        l = next((q for q in self.doc.layers if q.id == layer_id), None)
        if l is None or not shape:
            return {"ok": False, "error": "Select the area first."}
        x1, y1, x2, y2 = nab_core.shape_bbox(shape, l.img.size)
        w, h = l.img.size
        rect = {"x1": round(x1 / w, 4), "y1": round(y1 / h, 4), "x2": round(x2 / w, 4), "y2": round(y2 / h, 4)}
        key = self.paper_clean
        cur = dict(self._pd_all().get(key, {}))
        cur["cleanup"] = (cur.get("cleanup") or []) + [rect]
        self._pd_all()[key] = cur
        self.save_settings()
        return {"ok": True, "n": len(cur["cleanup"])}

    def cleanup_apply(self, layer_id):
        rects = self.paper_opts().get("cleanup") or []
        if not rects:
            return {"ok": False, "error": "Nothing remembered for this paper yet (select an area, then 'Remember clean-up')."}
        l = next((q for q in self.doc.layers if q.id == layer_id), None)
        if l is None:
            return {"ok": False, "error": "No clip."}
        w, h = l.img.size
        first = True
        for r in rects:
            shape = {"type": "rect", "x1": r["x1"] * w, "y1": r["y1"] * h, "x2": r["x2"] * w, "y2": r["y2"] * h}
            self.doc.op_erase(layer_id, shape)
        return self._after_edit()

    def cleanup_clear(self):
        key = self.paper_clean
        cur = dict(self._pd_all().get(key, {}))
        cur["cleanup"] = []
        self._pd_all()[key] = cur
        self.save_settings()
        return {"ok": True}

    # ───────────────────────────── inches / calibration ─────────────────────
    def calibrate(self, px, inches, paper=None):
        px, inches = float(px), float(inches)
        if px <= 0 or inches <= 0:
            return {"ok": False, "error": "Both numbers must be above 0."}
        ppi = round(px / inches, 3)
        return dict(self.paper_defaults_set(paper or self.paper_clean, ppi=ppi), ppi=ppi)

    def estimate_inches(self):
        ppi = float(self.paper_opts().get("ppi") or 0)
        if ppi <= 0:
            return {"ok": False, "calibrated": False}
        w, h = self.doc.stack_size()
        if not w or not h:
            return {"ok": False, "calibrated": True}

        def fmt(v):
            v = round(v * 2) / 2.0               # nearest half inch
            return str(int(v)) if v == int(v) else str(v)
        return {"ok": True, "calibrated": True, "ppi": ppi, "w": round(w / ppi, 2), "h": round(h / ppi, 2),
                "size": f"{fmt(w / ppi)}x{fmt(h / ppi)}"}

    # ───────────────────────────── page from the ePaper ─────────────────────
    def page_hint(self, title="", url=""):
        po = self.paper_opts()
        texts = [url or "", title or ""]
        pats = []
        if po.get("page_regex"):
            try:
                pats.append(re.compile(po["page_regex"], re.I))
            except re.error:
                pass
        pats += _PAGE_PATTERNS
        for rx in pats:
            for t in texts:
                m = rx.search((t or "").translate(_BN))
                if m:
                    v = (m.group(1) if m.groups() else m.group(0)).strip().upper()
                    if _PAGE_OK.match(v):
                        return v.lstrip("0") or "0" if v.isdigit() else v
        return ""

    # ───────────────────────────── detection test / extension light ─────────
    # ───────────────────────────── browser extension: one-click setup ───────
    def ext_source_dir(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(getattr(sys, "_MEIPASS", "") or "", "NAB_TabReporter"),
                  os.path.join(os.path.dirname(sys.executable), "NAB_TabReporter"),
                  os.path.join(here, "NAB_TabReporter")):
            if os.path.isfile(os.path.join(p, "manifest.json")):
                return p
        return ""

    def ext_install_dir(self):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "NAB", "extension")

    def ext_prepare(self):
        """Copy the bundled extension to a permanent folder (Chrome needs a stable path). Returns (dir, error)."""
        import shutil
        src, dst = self.ext_source_dir(), self.ext_install_dir()
        if not src:
            return dst, "The extension files are missing from this NAB copy."
        try:
            os.makedirs(dst, exist_ok=True)
            for n in os.listdir(src):
                p = os.path.join(src, n)
                if os.path.isfile(p):
                    shutil.copy2(p, os.path.join(dst, n))
            return dst, None
        except Exception as e:
            return dst, str(e)

    def ext_browsers(self):
        """Installed browsers that can load the extension: [{id, name, exe, url}] (Chrome first)."""
        out = []
        if not sys.platform.startswith("win"):
            return out
        pf, pf86, la = (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                        os.environ.get("LOCALAPPDATA", ""))
        cands = [("chrome", "Google Chrome", "chrome://extensions",
                  [os.path.join(b, "Google", "Chrome", "Application", "chrome.exe") for b in (pf, pf86, la) if b]),
                 ("edge", "Microsoft Edge", "edge://extensions",
                  [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe") for b in (pf86, pf, la) if b]),
                 ("brave", "Brave", "brave://extensions",
                  [os.path.join(b, "BraveSoftware", "Brave-Browser", "Application", "brave.exe") for b in (pf, pf86, la) if b])]
        for bid, name, url, paths in cands:
            exe = next((p for p in paths if os.path.isfile(p)), "")
            if exe:
                out.append({"id": bid, "name": name, "exe": exe, "url": url})
        return out

    def ext_setup_info(self):
        d, err = self.ext_prepare()
        return {"ok": not err, "error": err, "dir": d, "browsers": [{k: b[k] for k in ("id", "name", "url")} for b in self.ext_browsers()],
                "status": self.ext_status(), "version": self._ext_version()}

    def _ext_version(self):
        try:
            import json
            with open(os.path.join(self.ext_install_dir(), "manifest.json"), encoding="utf-8") as f:
                return json.load(f).get("version", "")
        except Exception:
            return ""

    def ext_open_browser(self, bid=None):
        """Open the chosen browser straight on its extensions page."""
        import subprocess
        d, err = self.ext_prepare()
        if err:
            return {"ok": False, "error": err}
        bs = self.ext_browsers()
        b = next((x for x in bs if x["id"] == bid), bs[0] if bs else None)
        if not b:
            return {"ok": False, "error": "No Chrome / Edge found. Open your browser, type chrome://extensions in the address bar."}
        try:
            subprocess.Popen([b["exe"], b["url"]], close_fds=True)
            return {"ok": True, "browser": b["name"], "dir": d}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ext_open_folder(self):
        d, err = self.ext_prepare()
        if err:
            return {"ok": False, "error": err}
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)           # noqa
            return {"ok": True, "dir": d}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    def ext_status(self):
        ts = self.tab_server
        if ts is None:
            return {"state": "off", "text": "Extension listener not running"}
        i = ts.info()
        age = i.get("last_msg_age")
        if i.get("clients", 0) > 0 and age is not None and age < 12:
            return {"state": "ok", "text": "Browser extension connected", "age": age}
        if i.get("clients", 0) > 0:
            return {"state": "idle", "text": "Extension connected but quiet — open a news tab", "age": age}
        return {"state": "off", "text": "Browser extension not connected — Settings → About → Setup guide"}

    def detect_test(self):
        import nab_clip_scan
        title = getattr(self, "_last_external_title", "") or ""
        ti = None
        try:
            ti = self.tab_server.get_tab_info() if self.tab_server else None
        except Exception:
            pass
        url = (ti or {}).get("url", "") or (self._tab_url[1] if self._tab_url else "")
        ctx = f"{title} {url}"
        paper, how, detail = nab_clip_scan.detect_paper(ctx, ctx, self.url_mappings, self.paper_list, allow_name_fallback=True)
        return {"ok": True, "title": title, "url": url, "ext": self.ext_status(),
                "paper": re.sub(r"^[^\w]+", "", paper or "", flags=re.U).strip(), "how": how or "", "detail": detail or "",
                "page": self.page_hint(title, url), "mapped": bool(paper)}

    def learn_paper(self, text, paper):
        """User answered the 'which paper is this?' prompt: remember the address part."""
        t = (text or "").strip().lower()
        if not t or paper not in self.paper_list:
            return {"ok": False, "error": "Pick a paper."}
        m = re.match(r"^(?:https?://)?([^/\s?#]+)", t)
        key = m.group(1) if m and "." in m.group(1) else t[:40]
        key = re.sub(r"^www\.", "", key)
        mp = dict(self.url_mappings)
        mp[key] = paper
        self.set_mappings(mp)
        self.set_paper(paper)
        return {"ok": True, "key": key}

    # ───────────────────────────── copy last saved / open folder ────────────
    def last_saved_file(self):
        for h in reversed(self.session_history):
            if os.path.exists(h.get("path", "")):
                return h["path"]
        return ""

    def copy_last_saved(self):
        p = self.last_saved_file()
        if not p:
            return {"ok": False, "error": "Nothing saved yet in this session."}
        try:
            ok = nab_clipboard.set_clipboard_image(Image.open(p).convert("RGB"))
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": bool(ok), "name": os.path.basename(p), **({} if ok else {"error": "Clipboard not available here."})}

    def open_last_folder(self):
        p = self.last_saved_file()
        folder = os.path.dirname(p) if p else self._dest_folder([])
        try:
            os.makedirs(folder, exist_ok=True)
            if sys.platform.startswith("win"):
                if p:
                    import subprocess
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
                else:
                    os.startfile(folder)      # noqa
            return {"ok": True, "folder": folder}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ───────────────────────────── settings backups ─────────────────────────
    def _backup_dir(self):
        from nab_engine import DOC_DIR
        return os.path.join(DOC_DIR, "NAB_Backups")

    def _backup_files(self):
        from nab_engine import UI_STATE_FILE
        from nab_engine import DOC_DIR
        extra = [os.path.join(DOC_DIR, "nab_wa.json"), os.path.join(os.path.expanduser("~"), "Documents", "nab_users.json")]
        return [self.settings_file, self.sources_file, self.mappings_file, self.config_file, UI_STATE_FILE] + extra

    def backup_now(self, why="manual"):
        try:
            d = self._backup_dir()
            os.makedirs(d, exist_ok=True)
            name = f"settings_{datetime.datetime.now():%Y%m%d_%H%M%S}_{re.sub(r'[^a-z0-9]+', '', why.lower())[:12]}.zip"
            with zipfile.ZipFile(os.path.join(d, name), "w", zipfile.ZIP_DEFLATED) as z:
                for f in self._backup_files():
                    if os.path.exists(f):
                        z.write(f, os.path.basename(f))
            zs = sorted(x for x in os.listdir(d) if x.startswith("settings_") and x.endswith(".zip"))
            for old in zs[:-30]:
                try:
                    os.remove(os.path.join(d, old))
                except OSError:
                    pass
            return {"ok": True, "name": name}
        except Exception as e:
            logging.error(f"backup: {e}")
            return {"ok": False, "error": str(e)}

    def backup_auto(self):
        """Once per day, and whenever the app version changed (update-safe settings)."""
        try:
            from nab_engine import UI_STATE_FILE   # noqa
            v = getattr(self, "app_version", "") or ""
            last = self.ui_state.get("backup_day"), self.ui_state.get("backup_ver")
            today = datetime.date.today().isoformat()
            if last[0] != today or last[1] != v:
                self.backup_now("update" if last[1] != v else "daily")
                self.ui_set(backup_day=today, backup_ver=v)
        except Exception as e:
            logging.error(f"backup_auto: {e}")

    def backup_list(self):
        d = self._backup_dir()
        out = []
        if os.path.isdir(d):
            for n in sorted(os.listdir(d), reverse=True):
                if n.startswith("settings_") and n.endswith(".zip"):
                    out.append({"name": n, "kb": os.path.getsize(os.path.join(d, n)) // 1024})
        return {"ok": True, "backups": out, "dir": d}

    def backup_restore(self, name):
        p = os.path.join(self._backup_dir(), os.path.basename(name or ""))
        if not os.path.isfile(p):
            return {"ok": False, "error": "Backup not found."}
        self.backup_now("beforerestore")
        try:
            with zipfile.ZipFile(p) as z:
                known = {os.path.basename(f): f for f in self._backup_files()}
                for n in z.namelist():
                    if n in known:
                        with open(known[n], "wb") as fh:
                            fh.write(z.read(n))
            self.load_settings()
            self.load_sources()
            self.load_categories()
            self.hub.emit("settings_changed")
            self.hub.emit("state_changed")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ───────────────────────────── crash-safe draft ─────────────────────────
    def _draft_dir(self):
        return os.path.join(_local_dir(), "draft")

    def draft_start(self):
        threading.Thread(target=self._draft_loop, daemon=True, name="NAB-Draft").start()

    def _draft_loop(self):
        sig = None
        quiet = 0
        d = self._draft_dir()
        while True:
            time.sleep(1.5)
            try:
                if not self.authorized or getattr(self, "_draft_pending", False):
                    continue
                with self.doc.lock:
                    layers = list(self.doc.layers)
                    cur = tuple((l.id, id(l.img)) for l in layers)
                if cur == sig:
                    continue
                quiet += 1
                if quiet < 2:                  # wait for ~3 s of calm before writing
                    continue
                quiet = 0
                sig = cur
                if not layers:
                    shutil.rmtree(d, ignore_errors=True)
                    continue
                os.makedirs(d, exist_ok=True)
                meta = []
                for l in layers:
                    fn = f"L{l.id}.png"
                    fp = os.path.join(d, fn)
                    if not os.path.exists(fp) or getattr(l, "_draft_id", None) != id(l.img):
                        l.img.save(fp, "PNG", compress_level=1)
                        try:
                            l._draft_id = id(l.img)
                        except Exception:
                            pass
                    meta.append({"file": fn, "name": l.name, "x": l.x, "y": l.y, "visible": l.visible, "align": l.align})
                for f in os.listdir(d):
                    if f.endswith(".png") and f not in {m["file"] for m in meta}:
                        os.remove(os.path.join(d, f))
                with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
                    json.dump({"saved": time.time(), "paper": self.paper, "layers": meta, "free": self.doc.free,
                               "cats": self.draft.get("cats", []), "line": self.draft.get("line", "")}, fh)
            except Exception as e:
                logging.error(f"draft: {e}")

    def draft_check(self):
        """Is there an unsaved clip from a previous run? (not offered when the app is already holding clips)"""
        mp = os.path.join(self._draft_dir(), "meta.json")
        try:
            if os.path.isfile(mp) and not self.doc.layers:
                m = json.load(open(mp, encoding="utf-8"))
                n = len(m.get("layers", []))
                if n:
                    self._draft_pending = True
                    return {"found": True, "n": n, "age": int(time.time() - m.get("saved", 0)), "paper": m.get("paper", "")}
        except Exception as e:
            logging.error(f"draft_check: {e}")
        return {"found": False}

    def draft_restore(self):
        d = self._draft_dir()
        try:
            m = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
            with self.doc.lock:
                for L in m["layers"]:
                    im = Image.open(os.path.join(d, L["file"])).convert("RGB")
                    lay = self.doc.add(im, L.get("name", "Clip"), checkpoint=False)
                    lay.visible = L.get("visible", True)
                    lay.x, lay.y = L.get("x", 0), L.get("y", 0)
            if m.get("paper") in self.paper_list:
                self.set_paper(m["paper"])
            self._preview_cache = None
            self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
            self._draft_pending = False
            return {"ok": True, "n": len(m["layers"]), "cats": m.get("cats", []), "line": m.get("line", "")}
        except Exception as e:
            self._draft_pending = False
            return {"ok": False, "error": str(e)}

    def draft_discard(self):
        shutil.rmtree(self._draft_dir(), ignore_errors=True)
        self._draft_pending = False
        return {"ok": True}

    # ───────────────────────────── slow-PC mode ─────────────────────────────
    def slow_pc(self):
        mode = self.extra_settings.get("slow_mode", "auto")
        if mode in ("on", "true", True):
            return True
        if mode in ("off", "false", False):
            return False
        try:
            cpus = os.cpu_count() or 2
            ram_gb = 8.0
            if sys.platform.startswith("win"):
                import ctypes

                class MS(ctypes.Structure):
                    _fields_ = [("l", ctypes.c_ulong), ("ml", ctypes.c_ulong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                                ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                                ("ae", ctypes.c_ulonglong)]
                ms = MS()
                ms.l = ctypes.sizeof(MS)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
                ram_gb = ms.tp / 1024 ** 3
            return cpus <= 4 or ram_gb < 6.5
        except Exception:
            return False

    # ───────────────────────────── first-run guide ──────────────────────────
    def firstrun_status(self):
        from nab_connections import summary as _sum
        steps = []
        # 1 save folder writable
        ok = True
        try:
            os.makedirs(self.base_root, exist_ok=True)
            t = os.path.join(self.base_root, ".w")
            open(t, "w").close()
            os.remove(t)
        except Exception:
            ok = False
        steps.append({"id": "folder", "ok": ok, "title": "Save folder", "path": self.base_root,
                      "why": "Clips are saved here, in Year / Month / Day folders.",
                      "fix": "Pick a folder you can write to."})
        # 2 logos
        have = sum(1 for p in self.paper_list if self.logo_path(re.sub(r"^[^\w]+", "", p, flags=re.U).strip()))
        steps.append({"id": "logos", "ok": have >= max(1, len(self.paper_list) // 2), "title": "Newspaper logos",
                      "detail": f"{have}/{len(self.paper_list)} found",
                      "why": "The logo is printed at the top of every clip.",
                      "fix": "Settings → Newspapers → Paste shot (Win+Shift+S, drag around the logo)."})
        # 3 extension
        e = self.ext_status()
        here = os.path.dirname(os.path.abspath(__file__))
        ext_dir = self.ext_install_dir()
        steps.append({"id": "ext", "ok": e["state"] == "ok", "title": "Browser extension", "detail": e["text"], "path": ext_dir,
                      "why": "It tells NAB which e-paper tab you are on, so the paper (and page) are picked automatically.",
                      "fix": "Click “Set up now” — NAB opens your browser and shows what to click."})
        # 4 webview2 (Windows 10 PCs may lack it)
        wv = True
        if sys.platform.startswith("win"):
            try:
                import winreg
                wv = False
                for hive, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
                                  (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
                                  (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}")):
                    try:
                        winreg.CloseKey(winreg.OpenKey(hive, sub))
                        wv = True
                        break
                    except OSError:
                        pass
            except Exception:
                wv = True
        steps.append({"id": "webview", "ok": wv, "title": "Edge WebView2 (Windows 10)", "detail": "installed" if wv else "not found",
                      "why": "NAB's window needs it. Windows 11 has it; some Windows 10 PCs do not.",
                      "fix": "Install 'Evergreen Bootstrapper' from microsoft.com/edge/webview2 (free, 2 minutes)."})
        # 5 drive key / upload
        c = _sum() if callable(_sum) else {}
        steps.append({"id": "upload", "ok": True, "title": "Google upload", "detail": "ON" if self.upload_enabled() else "OFF (clips stay on this PC)",
                      "why": "Uploading is optional and can be turned on later.", "fix": "Settings → Sync → Upload clips to Google."})
        # 6 mappings
        steps.append({"id": "rules", "ok": bool(self.url_mappings), "title": "Tab → paper rules", "detail": f"{len(self.url_mappings)} rules",
                      "why": "They link a web address to a newspaper.", "fix": "Settings → Tab → paper rules, or use the 'learn this paper' prompt."})
        done = bool(self.ui_state.get("firstrun_done"))
        return {"ok": True, "steps": steps, "done": done, "all_ok": all(s["ok"] for s in steps)}

    def firstrun_done(self):
        self.ui_set(firstrun_done=True)
        return {"ok": True}

    # ───────────────────────────── missed-save guard ────────────────────────
    def guard_tick(self):
        """Called by the ticker (every ~2 s): clips waiting unsaved while the user is elsewhere."""
        if not self.extra_settings.get("missed_guard", True) or not self.authorized:
            return
        n = len(self.doc.visible_layers())
        if n == 0:
            self._guard_since = None
            self._guard_fired = False
            return
        rev = self.doc.rev
        if getattr(self, "_guard_rev", None) != rev:
            self._guard_rev, self._guard_since, self._guard_fired = rev, time.time(), False
            return
        wait = int(self.extra_settings.get("missed_guard_s", 45) or 45)
        if self._guard_since and not self._guard_fired and time.time() - self._guard_since >= wait:
            self._guard_fired = True
            self.hub.emit("missed_save", n=n, secs=wait)
            try:
                import nab_winutil as W
                W.flash_window(W.find_window("News Automation Pro"))
            except Exception:
                pass
