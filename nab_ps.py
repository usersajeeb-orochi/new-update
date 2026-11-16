# nab_ps.py - "Photoshop mode" for the Clip canvas.
#   * no paper logo, no header line: the canvas is only your layers, which sit freely (move them anywhere)
#   * several documents at once (tabs): every screenshot the Screenshot Bot took can open on its own canvas
#   * Ctrl+S: the first time the real Windows "Save As" box (name + location + type); after that it saves in place
#     Ctrl+Shift+S: always the Save As box.   Ctrl+E: merge the layer down.   Ctrl+Shift+E: merge all visible layers.
import os
import json
import logging
import threading
import itertools

from PIL import Image

import nab_core
import nab_winutil

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
MAX_DOCS = 40
_ids = itertools.count(1)


def _stem(p):
    return os.path.splitext(os.path.basename(p))[0][:60]


class PSMixin:
    ps_on = False

    def _psd(self):
        d = self.__dict__.get("_ps_data")
        if d is None:
            d = self.__dict__["_ps_data"] = {"docs": [], "cur": -1, "n": 0, "dir": self._ps_load_dir(), "lock": threading.RLock()}
        return d

    # ---- last folder (remembered between runs) ----
    @staticmethod
    def _ps_file():
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB", "ps_state.json")

    def _ps_load_dir(self):
        try:
            with open(self._ps_file(), encoding="utf-8") as f:
                d = json.load(f).get("dir", "")
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
        return ""

    def _ps_remember_dir(self, d):
        self._psd()["dir"] = d
        try:
            os.makedirs(os.path.dirname(self._ps_file()), exist_ok=True)
            with open(self._ps_file(), "w", encoding="utf-8") as f:
                json.dump({"dir": d}, f)
        except Exception:
            pass

    # ---- documents ----
    def _ps_entry(self, doc, name, path=""):
        return {"id": next(_ids), "doc": doc, "name": name, "path": path, "saved_rev": doc.rev}

    def _ps_register_current(self):
        """Turning the mode on: whatever is on the canvas now becomes document 1."""
        P = self._psd()
        if P["docs"]:
            return
        self.brand = False                                    # Photoshop mode starts clean; the Logo toggle brings logo + header back
        self.doc.freeze()
        P["n"] += 1
        e = self._ps_entry(self.doc, "Untitled-%d" % P["n"])
        e["saved_rev"] = -1 if self.doc.layers else self.doc.rev
        P["docs"].append(e)
        P["cur"] = 0

    def _ps_refresh(self):
        self._preview_cache = None
        try:
            self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
            self.hub.emit("ps", on=self.ps_on)
        except Exception:
            pass

    def ps_state(self):
        P = self._psd()
        docs = []
        for i, e in enumerate(P["docs"]):
            d = e["doc"]
            try:
                w, h = d.canvas_size()
            except Exception:
                w = h = 0
            docs.append({"i": i, "id": e["id"], "name": e["name"], "path": e["path"], "dirty": d.rev != e["saved_rev"] and bool(d.layers),
                         "layers": len(d.layers), "w": w, "h": h})
        return {"ok": True, "on": self.ps_on, "brand": getattr(self, "brand", True), "cur": P["cur"], "docs": docs, "dir": P["dir"]}

    def brand_set(self, on):
        """The logo + header toggle: works the same in newspaper mode and in Photoshop mode."""
        self.brand = bool(on)
        self._ps_refresh()
        return self.ps_state()

    def ps_set(self, on):
        P = self._psd()
        with P["lock"]:
            on = bool(on)
            if on == self.ps_on:
                return self.ps_state()
            if on:
                self.ps_on = True
                self.brand = False                            # Photoshop mode starts clean; the toggle brings logo + header back
                self._ps_register_current()
            else:                                             # back to the normal newspaper flow with the document you are looking at
                self.ps_on = False
                self.brand = True
                keep = self.doc
                P["docs"], P["cur"] = [], -1
                keep.restack() if keep.free else None
            self._ps_refresh()
            return self.ps_state()

    def ps_new(self, w=1200, h=800, name=""):
        w, h = max(50, min(int(w or 1200), 8000)), max(50, min(int(h or 800), 8000))
        doc = nab_core.Document()
        doc.add(Image.new("RGB", (w, h), (255, 255, 255)), "Background", checkpoint=False)
        doc.freeze()
        return self._ps_add_doc(doc, name or "")

    def _ps_add_doc(self, doc, name, path=""):
        P = self._psd()
        with P["lock"]:
            if not self.ps_on:
                self.ps_on = True
                self._ps_register_current()
            if len(P["docs"]) >= MAX_DOCS:
                return {"ok": False, "error": "Too many canvases open (%d). Save and close some first." % MAX_DOCS}
            if not name:
                P["n"] += 1
                name = "Untitled-%d" % P["n"]
            P["docs"].append(self._ps_entry(doc, name, path))
            self._ps_switch_locked(len(P["docs"]) - 1)
        self._ps_refresh()
        return self.ps_state()

    def ps_open(self, paths):
        """Each image file becomes its own canvas (tab). Files that cannot be read are skipped and reported."""
        P = self._psd()
        opened, bad = [], []
        first = None
        for p in paths or []:
            p = str(p)
            if os.path.splitext(p)[1].lower() not in EXTS or not os.path.isfile(p):
                bad.append(os.path.basename(p))
                continue
            try:
                with Image.open(p) as im:
                    im.load()
                    img = im.convert("RGB")
            except Exception as ex:
                logging.error(f"ps_open {p}: {ex}")
                bad.append(os.path.basename(p))
                continue
            doc = nab_core.Document()
            doc.add(img, _stem(p), checkpoint=False)
            doc.freeze()
            with P["lock"]:
                if not self.ps_on:
                    self.ps_on = True
                    self._ps_register_current()
                if len(P["docs"]) >= MAX_DOCS:
                    bad.append(os.path.basename(p) + " (too many open)")
                    continue
                e = self._ps_entry(doc, _stem(p), "")           # not saved yet: Ctrl+S asks where to put the edited copy
                e["origin"] = p
                P["docs"].append(e)
                opened.append(_stem(p))
                if first is None:
                    first = len(P["docs"]) - 1
        if first is not None:
            with P["lock"]:
                # an empty untitled starter canvas is replaced by the first real image
                if len(P["docs"]) > len(opened) and not P["docs"][0]["doc"].layers and P["docs"][0]["name"].startswith("Untitled"):
                    P["docs"].pop(0)
                    first -= 1
                self._ps_switch_locked(max(0, first))
        self._ps_refresh()
        out = self.ps_state()
        out.update(opened=len(opened), skipped=bad)
        return out

    def ps_open_data(self, images, names=None):
        """Browser file picker / drag-drop: data-URL images, each on its own canvas."""
        import base64
        import io
        tmpl = []
        P = self._psd()
        first = None
        for n, d in enumerate(images or []):
            try:
                raw = base64.b64decode(str(d).split(",", 1)[-1])
                with Image.open(io.BytesIO(raw)) as im:
                    im.load()
                    img = im.convert("RGB")
            except Exception as ex:
                logging.error(f"ps_open_data: {ex}")
                continue
            doc = nab_core.Document()
            nm = ((names or [])[n] if names and n < len(names) else "") or "Image"
            nm = os.path.splitext(os.path.basename(str(nm)))[0][:60] or "Image"
            doc.add(img, nm, checkpoint=False)
            doc.freeze()
            with P["lock"]:
                if not self.ps_on:
                    self.ps_on = True
                    self._ps_register_current()
                if len(P["docs"]) >= MAX_DOCS:
                    break
                P["docs"].append(self._ps_entry(doc, nm))
                tmpl.append(nm)
                if first is None:
                    first = len(P["docs"]) - 1
        if first is not None:
            with P["lock"]:
                if len(P["docs"]) > len(tmpl) and not P["docs"][0]["doc"].layers and P["docs"][0]["name"].startswith("Untitled"):
                    P["docs"].pop(0)
                    first -= 1
                self._ps_switch_locked(max(0, first))
        self._ps_refresh()
        out = self.ps_state()
        out["opened"] = len(tmpl)
        return out

    def _ps_switch_locked(self, i):
        P = self._psd()
        if 0 <= i < len(P["docs"]):
            P["cur"] = i
            self.doc = P["docs"][i]["doc"]

    def ps_switch(self, i):
        P = self._psd()
        with P["lock"]:
            self._ps_switch_locked(int(i))
        self._ps_refresh()
        return self.ps_state()

    def ps_close(self, i):
        P = self._psd()
        with P["lock"]:
            i = int(i)
            if not (0 <= i < len(P["docs"])):
                return self.ps_state()
            P["docs"].pop(i)
            if not P["docs"]:
                doc = nab_core.Document()
                doc.freeze()
                P["n"] += 1
                P["docs"].append(self._ps_entry(doc, "Untitled-%d" % P["n"]))
                P["cur"] = 0
            elif P["cur"] >= i:
                P["cur"] = max(0, P["cur"] - (1 if P["cur"] >= i and P["cur"] > 0 else 0))
            self._ps_switch_locked(P["cur"])
        self._ps_refresh()
        return self.ps_state()

    # ---- saving ----
    def _ps_flat(self):
        with self.doc.lock:
            if not self.doc.visible_layers():
                return None
            fr = self.doc.frozen_copy()
        if getattr(self, "brand", True):
            htxt = self.header_text(self.last_page, self.last_pos)
            return fr.compose(1.0, self.get_logo(self.paper_clean, small=False), self.logo_scale, self.text_scale,
                              self.show_header, htxt)[0]
        return fr.stitched(1.0)

    def ps_save(self, save_as=False, path=None):
        """Ctrl+S / Ctrl+Shift+S. -> {"ok", "path"} or {"ok": False, "cancel": True}."""
        P = self._psd()
        if not self.ps_on:
            return {"ok": False, "error": "Photoshop mode is off."}
        img = self._ps_flat()
        if img is None:
            return {"ok": False, "error": "The canvas is empty."}
        e = P["docs"][P["cur"]] if 0 <= P["cur"] < len(P["docs"]) else None
        if e is None:
            return {"ok": False, "error": "No document."}
        target = path or ("" if save_as else e["path"])
        if not target:
            start = P["dir"] or (os.path.dirname(e.get("origin", "")) if e.get("origin") else "") or os.path.join(os.path.expanduser("~"), "Pictures")
            if not os.path.isdir(start):
                start = os.path.expanduser("~")
            name = (e["name"] or "Untitled") + (".png" if not e.get("origin", "").lower().endswith((".jpg", ".jpeg")) else ".jpg")
            target = nab_winutil.save_dialog("Save As", start, name)
            if target is None:                                   # no Windows dialog available: save next to the original / in Pictures
                target = os.path.join(start, name)
            if not target:
                return {"ok": False, "cancel": True}
        target = os.path.abspath(target)
        ext = os.path.splitext(target)[1].lower()
        if ext not in EXTS:
            target += ".png"
            ext = ".png"
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".tmp" + ext
            if ext in (".jpg", ".jpeg"):
                img.save(tmp, "JPEG", quality=95, subsampling=0, optimize=True)
            elif ext == ".webp":
                img.save(tmp, "WEBP", quality=95)
            elif ext == ".bmp":
                img.save(tmp, "BMP")
            else:
                img.save(tmp, "PNG", optimize=True)
            os.replace(tmp, target)
        except Exception as ex:
            logging.exception("ps_save")
            return {"ok": False, "error": "Could not save: %s" % ex}
        e["path"], e["name"] = target, os.path.splitext(os.path.basename(target))[0]
        e["saved_rev"] = e["doc"].rev
        self._ps_remember_dir(os.path.dirname(target))
        self._ps_refresh()
        return {"ok": True, "path": target, "name": os.path.basename(target), "kb": round(os.path.getsize(target) / 1024.0, 1)}

    # ---- scanner (Windows WIA dialog) ----
    def ps_scan(self):
        """Scan a paper: Windows' scan dialog (preview, DPI, colour) -> the result opens on its own canvas."""
        import time
        from PIL import Image as _I
        d = os.path.join(os.path.expanduser("~"), "Documents", "NAB_Scans")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            d = os.environ.get("TEMP") or os.path.expanduser("~")
        stamp = time.strftime("Scan-%d-%m-%Y_%H%M%S")
        raw, err = nab_winutil.scan_image(os.path.join(d, stamp + "_raw"))
        if err:
            return {"ok": False, "error": err}
        if not raw:
            return {"ok": False, "cancel": True}
        final = os.path.join(d, stamp + ".png")
        try:
            with _I.open(raw) as im:
                im.load()
                im.convert("RGB").save(final, "PNG")
            os.remove(raw)
        except Exception as ex:
            logging.error(f"ps_scan: {ex}")
            return {"ok": False, "error": "The scanned image could not be read."}
        r = self.ps_open([final])
        r["ok"] = bool(r.get("opened"))
        r["file"] = final
        return r
