# nab_engine_host.py — Engine = EngineBase + Telegram/Drive ops + background duties.
import os
import re
import sys
import time
import base64
import logging
import threading
import datetime
import subprocess

from PIL import Image

import nab_core
import nab_meta
import nab_clipboard
import nab_connections
from nab_engine import (EngineBase, strip_emoji_prefix, parse_line_json, _meta_json,
                        DEFAULT_HOTKEYS, resource_path)
from nab_headless_ops import HeadlessOps

LOG_FILE = os.path.join(os.environ.get("NAB_DOC_DIR") or os.path.join(os.path.expanduser("~"), "Documents"), "nab_log.txt")
OWN_TITLES = ("News Automation", "NAB Overlay", "Surgical Workspace", "NAB —")


def _app_version():
    try:
        import nab_connections as _c  # noqa
        from nab_constants import APP_VERSION
        return APP_VERSION
    except Exception:
        try:
            m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nab_constants.py"), encoding="utf-8").read(), re.M)
            return m.group(1) if m else "?"
        except Exception:
            return "?"


from nab_extras import ExtrasMixin
from nab_mail_host import MailMixin


class Engine(MailMixin, ExtrasMixin, EngineBase, HeadlessOps):
    """Everything NAB does, window-less. One instance per process."""

    def __init__(self):
        EngineBase.__init__(self)
        self.authorized = False
        self.paused = False
        self.window_ctl = None           # set by nab_main: show/hide/focus/quit hooks
        self._tab_locks = {}
        self._tab_url = (None, "")
        self._learn = None
        self._learn_declined = set()
        self._last_external_hwnd = None
        self._last_external_title = ""
        self.last_context = ""
        self.last_clipboard_hash = None
        self._daily_report_sent_hour = -1
        self._last_autosave = time.time()
        self.draft = {"cats": [], "line": "", "f": {"page": "", "cols": "", "size": ""}}
        self.meta_rev = 0
        self.pending_note = ""
        self.tab_server = None
        import collections
        self._dlog = collections.deque(maxlen=40)
        self._sync = None
        self._started = False
        self._update = {"stage": "idle"}
        self._upload = {"running": False, "done": 0, "current": "", "last_error": ""}
        self._uploaded_file = os.path.join(os.path.dirname(self.settings_file), "nab_uploaded.json")
        self._load_uploaded()

    # ───────────────────────────── layer / edit API ─────────────────────────
    def _after_edit(self, extra=None):
        self._preview_cache = None
        self.hub.emit("clips", n=len(self.doc.layers), rev=self.doc.rev)
        out = {"ok": True, "rev": self.doc.rev, "layers": self.doc.info(),
               "undo": self.doc.history_depth()[0], "redo": self.doc.history_depth()[1]}
        if extra:
            out.update(extra)
        return out

    def _fail(self, msg):
        return {"ok": False, "error": msg, "rev": self.doc.rev}

    def edit(self, op, layer_id, shape=None, **kw):
        """Selection-based edits on one layer. shape is in LAYER pixels."""
        d = self.doc
        try:
            if op in ("crop", "erase", "redact", "highlight", "cut", "copy", "extract", "fill", "clone") and not shape:
                return self._fail("Make a selection first.")
            ok, extra = True, {}
            if op == "crop":
                ok = d.op_crop(layer_id, shape)
            elif op == "erase":
                ok = d.op_erase(layer_id, shape)
            elif op == "clone":
                ok = d.op_clone(layer_id, shape, float(kw.get("dx", 0)), float(kw.get("dy", 0)))
            elif op == "redact":
                ok = d.op_redact(layer_id, shape)
            elif op == "highlight":
                ok = d.op_highlight(layer_id, shape, tuple(kw.get("color", (255, 235, 59))), int(kw.get("alpha", 100)))
            elif op == "fill":
                ok = d.op_fill(layer_id, shape, tuple(kw.get("color", (255, 255, 255))))
            elif op == "cut":
                ok = d.op_cut(layer_id, shape)
            elif op == "copy":
                ok = d.op_copy(layer_id, shape)
                return {"ok": bool(ok), "rev": d.rev, "copied": bool(ok)}
            elif op == "extract":
                n = d.op_extract(layer_id, shape, cut=bool(kw.get("cut", True)))
                ok = n is not None
                extra = {"new_layer": n.id if n else None}
            elif op == "move":
                ok = d.op_move_selection(layer_id, shape, float(kw.get("dx", 0)), float(kw.get("dy", 0)),
                                         float(kw.get("scale", 1.0)), bool(kw.get("cut", True)))
            elif op == "stamp":
                png = kw.get("png", "")
                if "," in png:
                    png = png.split(",", 1)[1]
                import io as _io
                rgba = Image.open(_io.BytesIO(base64.b64decode(png)))
                ok = d.op_stamp(layer_id, kw.get("x", 0), kw.get("y", 0), rgba)
            elif op == "resize":
                ok = d.op_resize_layer(layer_id, kw.get("factor", 1.0))
            else:
                return self._fail(f"unknown edit {op!r}")
            if not ok:
                return self._fail("Selection too small.")
            return self._after_edit(extra)
        except KeyError:
            return self._fail("That layer no longer exists.")
        except Exception as e:
            logging.exception("edit")
            return self._fail(str(e))

    def filter(self, name, layer_id=None, **kw):
        """Whole-layer filters. layer_id None = every visible layer."""
        d = self.doc
        try:
            ids = [layer_id] if layer_id else [l.id for l in d.visible_layers()]
            if not ids:
                return self._fail("Nothing to edit.")
            extra = None
            if name == "deskew":
                src = next((q.img for q in d.layers if q.id == ids[0]), None)
                ang = nab_core.estimate_skew(src) if src is not None else None
                if ang is None or abs(ang) < 0.15:
                    return self._fail("No tilt found — the clip already looks straight.")
                kw["deg"] = ang
                extra = {"angle": ang}
            with d.lock:
                if len(ids) > 1:
                    d.checkpoint()
                    snap_depth = len(d._undo)
                for i in ids:
                    d.op_filter(i, name, **kw)
                if len(ids) > 1:
                    # collapse the per-layer checkpoints into one undo step
                    del d._undo[snap_depth:]
            return self._after_edit(extra)
        except Exception as e:
            logging.exception("filter")
            return self._fail(str(e))

    def wand(self, layer_id, x, y, tol=24):
        """Magic wand: flood-select the similar-colour region under (x, y) in LAYER pixels.
        Returns a polygon (layer px) the UI uses as a normal selection."""
        try:
            import numpy as np
            import cv2
            with self.doc.lock:
                l = self.doc.layer(layer_id) if hasattr(self.doc, "layer") else next(q for q in self.doc.layers if q.id == layer_id)
                arr = np.array(l.img.convert("RGB"))
            h, w = arr.shape[:2]
            x, y = int(max(0, min(w - 1, x))), int(max(0, min(h - 1, y)))
            k = min(1.0, 1400.0 / max(w, h))
            small = cv2.resize(arr, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA) if k < 1 else arr
            sh, sw = small.shape[:2]
            mask = np.zeros((sh + 2, sw + 2), np.uint8)
            t = int(max(0, min(120, tol)))
            cv2.floodFill(small.copy(), mask, (int(x * k), int(y * k)), (255, 255, 255), (t,) * 3, (t,) * 3,
                          4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8))
            m = mask[1:-1, 1:-1]
            cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cs:
                return {"ok": False, "error": "Nothing selected."}
            c = max(cs, key=cv2.contourArea)
            if cv2.contourArea(c) < 25:
                return {"ok": False, "error": "Region too small."}
            c = cv2.approxPolyDP(c, 1.2, True)
            pts = [[float(p[0][0]) / k, float(p[0][1]) / k] for p in c]
            return {"ok": True, "shape": {"type": "poly", "points": pts}, "layer": layer_id}
        except StopIteration:
            return {"ok": False, "error": "That layer no longer exists."}
        except Exception as e:
            logging.exception("wand")
            return {"ok": False, "error": str(e)}

    def layer_cmd(self, cmd, layer_id=None, **kw):
        d = self.doc
        try:
            extra = {}
            if cmd == "delete":
                d.delete(layer_id)
            elif cmd == "duplicate":
                extra["new_layer"] = d.duplicate(layer_id).id
            elif cmd == "visible":
                d.set_visible(layer_id, kw.get("visible", True))
            elif cmd == "rename":
                d.rename(layer_id, kw.get("name", ""))
            elif cmd == "align":
                d.set_align(layer_id, kw.get("align", "center"))
            elif cmd == "reorder":
                d.reorder(layer_id, kw.get("index", 0))
            elif cmd == "merge_down":
                d.merge_down(layer_id)
            elif cmd == "merge_visible":
                d.merge_visible()
            elif cmd == "merge_side":
                d.merge_side_by_side()
            elif cmd == "move_up":
                d.move_last(-1)
            elif cmd == "move_down":
                d.move_last(1)
            elif cmd == "swap":
                d.swap_last_two()
            elif cmd == "move":
                if not d.op_move_layer(layer_id, kw.get("dx", 0), kw.get("dy", 0)):
                    return self._fail("Nothing moved.")
            elif cmd == "resize":
                if not d.op_resize_to(layer_id, kw.get("w", 0), kw.get("h", 0), kw.get("dx", 0), kw.get("dy", 0)):
                    return self._fail("Can't resize to that size.")
            elif cmd == "scale":
                l = d.get(layer_id)
                f = float(kw.get("factor", 1.0))
                if not d.op_resize_to(layer_id, l.img.width * f, l.img.height * f):
                    return self._fail("Can't resize to that size.")
            elif cmd == "match_width":
                if not d.op_match_width():
                    return self._fail("Nothing to match (needs 2+ clips of different widths).")
            elif cmd == "restack":
                d.restack()
            elif cmd == "paste_internal":
                n = d.op_paste_clipboard()
                if n is None:
                    return self._fail("Nothing copied yet (select, then Ctrl+C).")
                extra["new_layer"] = n.id
            elif cmd == "clear":
                d.clear()
            elif cmd == "undo":
                if not d.undo():
                    return self._fail("Nothing to undo.")
            elif cmd == "redo":
                if not d.redo():
                    return self._fail("Nothing to redo.")
            else:
                return self._fail(f"unknown command {cmd!r}")
            return self._after_edit(extra)
        except KeyError:
            return self._fail("That layer no longer exists.")
        except Exception as e:
            logging.exception("layer_cmd")
            return self._fail(str(e))

    def estimate_save(self, page="", cols=""):
        """Size the saved JPEG would have right now (width/height/KB) — drives the live compress readout."""
        import io
        with self.doc.lock:
            if not self.doc.visible_layers():
                return {"ok": False, "error": "Nothing to measure."}
            d = self.doc.frozen_copy()
        htxt = self.header_text(page or self.last_page or "·", cols or "·")
        cv = d.compose(1.0, self.get_logo(self.paper_clean, small=False), self.logo_scale, self.text_scale,
                       self.show_header, htxt)[0]
        ow = int(self.extra_settings.get("out_width", 0) or 0)
        if ow and 200 <= ow != cv.width:
            cv = cv.resize((ow, max(1, int(round(cv.height * ow / float(cv.width))))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        cv.save(buf, "JPEG", quality=self._quality(), optimize=True, subsampling=0)
        return {"ok": True, "w": cv.width, "h": cv.height, "kb": round(len(buf.getvalue()) / 1024.0, 1)}

    def suggest_crop(self):
        """Auto-crop suggestion — only for a single news-item clip (one layer)."""
        with self.doc.lock:
            vis = self.doc.visible_layers()
            if len(vis) != 1 or not self.extra_settings.get("auto_crop_suggest", True):
                return {"rect": None}
            l = vis[0]
            rect = nab_core.suggest_crop(l.img)
            return {"rect": list(rect) if rect else None, "layer": l.id, "rev": self.doc.rev}

    # ───────────────────────────── state for the UI ─────────────────────────
    def get_state(self):
        d = self.doc
        qs = {}
        for k, v in (self.quick_saves or {}).items():
            qs[k] = v
        return {
            "version": _app_version(), "pc": _pc_name(),
            "authorized": self.authorized, "paused": self.paused,
            "paper": self.paper, "paper_clean": self.paper_clean, "papers": self.paper_list,
            "date": self.current_date.strftime("%Y-%m-%d"),
            "categories": self.categories, "quick_saves": qs,
            "layers": d.info(), "free": d.free, "canvas": list(d.canvas_size()), "rev": d.rev, "undo": d.history_depth()[0], "redo": d.history_depth()[1],
            "settings": {
                "logo_scale": self.logo_scale, "text_scale": self.text_scale, "quality": self.quality,
                "hd_mode": self.hd_mode, "out_width": self.extra_settings.get("out_width", 0), "auto_snatch": self.auto_snatch, "auto_polish": self.auto_polish,
                "show_header": self.show_header,
                "auto_crop_suggest": self.extra_settings.get("auto_crop_suggest", True),
                "auto_crop_apply": self.extra_settings.get("auto_crop_apply", True),
                "auto_upload": self.extra_settings.get("auto_upload", False),
                "upload_enabled": self.upload_enabled(), "smart_fit": self.extra_settings.get("smart_fit", True),
                "fit_target_kb": self.extra_settings.get("fit_target_kb", 500), "fit_big_kb": self.extra_settings.get("fit_big_kb", 780),
                "slow_mode": self.extra_settings.get("slow_mode", "auto"), "missed_guard": self.extra_settings.get("missed_guard", True),
                "missed_guard_s": self.extra_settings.get("missed_guard_s", 45), "ov_opacity": self.extra_settings.get("ov_opacity", 100),
                "ov_snap": self.extra_settings.get("ov_snap", True),
                "min_kb": self.extra_settings.get("min_file_size_kb", 20),
                "max_kb": self.extra_settings.get("max_file_size_kb", 5000),
                "autosave_enabled": self.extra_settings.get("autosave_enabled", False),
                "autosave_interval": self.extra_settings.get("autosave_interval", 300),
                "daily_report_enabled": self.extra_settings.get("daily_report_enabled", False),
                "daily_report_hour": self.extra_settings.get("daily_report_hour", 18),
                "daily_goal": self.daily_goal,
                "base_root": self.base_root,
            },
            "hotkeys": self.universal_hotkeys,
            "meta": {"page": self.last_page, "size": self.last_size},
            "draft_sync": {"cats": list(self.draft["cats"]), "line": self.draft["line"], "f": dict(self.draft["f"]), "rev": self.meta_rev},
            "saved_today": len(self.session_history),
            "pending_uploads": len(self.pending_uploads()),
            "upload": dict(self._upload),
            "update": dict(self._update),
            "ui": self.ui_state,
            "connections": nab_connections.summary(),
            "sync": self.sync_status(),
            "last_saved_path": self.last_saved_path,
            "ext": self.ext_status(), "slow": self.slow_pc(), "last_meta": dict(getattr(self, "last_meta", {}) or {}),
            "paper_opts": {k: self.paper_opts().get(k) for k in ("ppi", "autotrim", "clean", "cleanup")},
            "firstrun_done": bool(self.ui_state.get("firstrun_done")),
        }

    # ───────────────────────────── option setters ───────────────────────────
    def set_options(self, **kw):
        with self.lock:
            for k in ("logo_scale", "text_scale", "quality"):
                if k in kw:
                    setattr(self, k, float(kw[k]))
            for k in ("hd_mode", "auto_snatch", "auto_polish", "show_header"):
                if k in kw:
                    setattr(self, k, bool(kw[k]))
            ex = self.extra_settings
            for src, dst, cast in (("auto_crop_suggest", "auto_crop_suggest", bool), ("auto_crop_apply", "auto_crop_apply", bool), ("auto_upload", "auto_upload", bool),
                                   ("upload_enabled", "upload_enabled", bool), ("smart_fit", "smart_fit", bool),
                                   ("fit_target_kb", "fit_target_kb", int), ("fit_big_kb", "fit_big_kb", int),
                                   ("slow_mode", "slow_mode", str), ("smart_trim", "smart_trim", bool), ("sync_approval", "sync_approval", bool), ("missed_guard", "missed_guard", bool),
                                   ("missed_guard_s", "missed_guard_s", int), ("ov_opacity", "ov_opacity", int), ("ov_snap", "ov_snap", bool),
                                   ("min_kb", "min_file_size_kb", int), ("max_kb", "max_file_size_kb", int),
                                   ("autosave_enabled", "autosave_enabled", bool),
                                   ("autosave_interval", "autosave_interval", int),
                                   ("out_width", "out_width", int),
                                   ("daily_report_enabled", "daily_report_enabled", bool),
                                   ("daily_report_hour", "daily_report_hour", int)):
                if src in kw:
                    ex[dst] = cast(kw[src])
            if "daily_goal" in kw:
                self.daily_goal = int(kw["daily_goal"])
                self.daily_goal_notified = False
            if "base_root" in kw and kw["base_root"]:
                try:
                    os.makedirs(kw["base_root"], exist_ok=True)
                    self.base_root = kw["base_root"]
                except Exception as e:
                    return {"ok": False, "error": f"Can't use that folder: {e}"}
            self._preview_cache = None
        self.save_settings()
        return {"ok": True}

    def set_date(self, iso):
        try:
            self.current_date = datetime.datetime.strptime(iso, "%Y-%m-%d")
        except ValueError:
            try:
                self.current_date = datetime.datetime.strptime(iso, "%d-%m-%Y")
            except ValueError:
                return {"ok": False, "error": "Bad date"}
        self._preview_cache = None
        self.hub.emit("date", date=self.current_date.strftime("%Y-%m-%d"))
        return {"ok": True}

    def set_quick_saves(self, mapping):
        self.quick_saves = {str(k): str(v) for k, v in mapping.items() if v}
        self.save_settings()
        return {"ok": True}

    def set_hotkeys(self, mapping):
        self.universal_hotkeys.update({k: v for k, v in mapping.items() if k in DEFAULT_HOTKEYS})
        self.save_settings()
        return {"ok": True}

    def set_mappings(self, mapping):
        self.url_mappings = {str(k).strip().lower(): v for k, v in mapping.items() if k and v}
        self.last_context = ""
        self.save_settings()
        return {"ok": True}

    def explain_detection(self, text):
        import nab_clip_scan
        return nab_clip_scan.explain_detection(text, self.url_mappings, self.paper_list)

    def set_draft(self, cats, line, src="", f=None):
        """Single source of truth for the armed categories + Page/Position/Size line.
        Every window (app, overlay) pushes here and every other window gets a `meta`
        event, so both always show the same thing."""
        f = f if isinstance(f, dict) else {}
        new = {"cats": list(cats or []), "line": line or "",
               "f": {k: str(f.get(k, "")) for k in ("page", "cols", "size")}}
        if new == self.draft:
            return {"ok": True, "rev": self.meta_rev, "same": True}
        self.draft = new
        self.meta_rev += 1
        self.hub.emit("meta", cats=new["cats"], line=new["line"], f=new["f"], src=src or "", rev=self.meta_rev)
        return {"ok": True, "rev": self.meta_rev}

    # ───────────────────────────── detection helpers ────────────────────────
    def _apply_detected_paper(self, paper, how_label):
        self.set_paper(paper)
        self.hub.emit("detected", paper=paper, clean=strip_emoji_prefix(paper), how=how_label)

    def user_chose_paper(self, label):
        """Operator picked a paper by hand → maybe offer to remember the tab."""
        self.set_paper(label)
        try:
            sug = self._learn and self._learn.on_user_choice(time.time(), self.paper, self.url_mappings)
            if sug and sug["fragment"] not in self._learn_declined:
                self._learn.ctx = None
                self.hub.emit("learn", fragment=sug["fragment"], paper=sug["paper"],
                              clean=strip_emoji_prefix(sug["paper"]),
                              replaces=strip_emoji_prefix(sug["replaces"]) if sug.get("replaces") else "",
                              url=sug.get("url", ""), title=sug.get("title", ""))
        except Exception as e:
            logging.error(f"user_chose_paper: {e}")
        return {"ok": True}

    def learn_remember(self, fragment, paper):
        import nab_learn
        frag = (fragment or "").strip().lower()
        if frag and nab_learn.fragment_is_safe(frag, self.url_mappings):
            m = dict(self.url_mappings)
            m[frag] = paper
            self.set_mappings(m)
            self.toast(f"✔ Learned: '{frag}' → {strip_emoji_prefix(paper)}", "ok")
            return {"ok": True}
        return {"ok": False, "error": "That text is too generic to remember safely."}

    def learn_decline(self, fragment):
        self._learn_declined.add(fragment)
        return {"ok": True}

    def lock_tab(self):
        hwnd, title = self._last_external_hwnd, self._last_external_title
        if not hwnd or not title:
            return {"ok": False, "error": "Click the epaper's browser tab, copy one image from it, then come back and press 📍."}
        if not self.paper:
            return {"ok": False, "error": "Pick a paper first."}
        key = (hwnd, re.sub(r"[\W\d_]+", "", title.lower()))
        if self._tab_locks.get(key) == self.paper:
            del self._tab_locks[key]
            return {"ok": True, "msg": f"📍 Unlocked: {title[:28]}"}
        self._tab_locks[key] = self.paper
        return {"ok": True, "msg": f"📍 Locked '{title[:22]}' → {self.paper_clean}"}

    def clear_tab_locks(self):
        n = len(self._tab_locks)
        self._tab_locks.clear()
        return {"ok": True, "msg": f"📍 Cleared {n} lock{'s' if n != 1 else ''}"}

    # ───────────────────────────── clipboard monitor ────────────────────────
    def start_monitor(self):
        import nab_learn
        if self._learn is None:
            self._learn = nab_learn.LearnTracker()
        threading.Thread(target=self._monitor_super, daemon=True, name="NAB-Monitor").start()

    def _monitor_super(self):
        while True:
            try:
                self._monitor_loop()
            except BaseException:
                logging.exception("monitor crashed — restarting")
                time.sleep(2)

    def detect_log_get(self):
        return {"rows": list(self._dlog), "win32": nab_clipboard.HAS_WIN32 or nab_clipboard.IS_WIN,
                "tab_ext": bool(self.tab_server and self.tab_server.get_tab_info()),
                "tab_server": (self.tab_server.info() if self.tab_server else {"status": "not started (login first)"}),
                "log_file": LOG_FILE, "mon": getattr(self, "_mon", None),
                "paused": self.paused, "authorized": self.authorized}

    def _guarded(self, fn, seconds, default, *args):
        """Run a call that talks to other programs (reading a browser's address bar can hang for
        seconds) on a helper thread; give up after `seconds` so the clipboard monitor never freezes.
        While an earlier call is still hanging the next ones are skipped, not stacked."""
        if getattr(self, "_guard_busy", False):
            return default
        box = []

        def run():
            try:
                box.append(fn(*args))
            except Exception as e:
                logging.debug(f"guarded {getattr(fn, '__name__', fn)}: {e}")
            finally:
                self._guard_busy = False

        self._guard_busy = True
        t = threading.Thread(target=run, daemon=True, name="NAB-Guard")
        t.start()
        t.join(seconds)
        return box[0] if box else default

    def _monitor_loop(self):
        """Event-driven paper detection + auto-snatch.  Same logic as before, with
        one important speed-up: the clipboard image is only decoded when the
        clipboard actually CHANGED (the old loop decoded it every 0.5 s)."""
        import nab_tabreader
        import nab_clip_scan
        last_tab_key = None
        last_seq = None
        while True:
            time.sleep(0.5)
            try:
                if not self.authorized or self.paused:
                    continue
                hwnd, title = nab_clipboard.foreground()
                context = signal_text = ""
                if title and not any(t in title for t in OWN_TITLES):
                    context += title + " "
                    signal_text += title + " "
                    self._last_external_hwnd, self._last_external_title = hwnd, title
                else:
                    title = ""
                snap = nab_clipboard.snapshot()
                seq, has_image = snap["seq"], snap["has_image"]
                self._mon = {"t": time.time(), "title": (title or "")[:70], "seq": seq, "img": bool(has_image)}
                if title:
                    self.guard_tick()
                if snap["source_url"]:
                    context += snap["source_url"] + " "
                    signal_text += snap["source_url"] + " "
                elif snap["text"]:
                    context += snap["text"] + " "
                clip_event = False
                if seq is not None:
                    if last_seq is None:
                        last_seq = seq
                    elif seq != last_seq:
                        last_seq, clip_event = seq, True
                tab_key = (hwnd, re.sub(r"[\W\d_]+", "", title.lower())) if title else None
                tab_changed = bool(tab_key and tab_key != last_tab_key)
                if tab_key:
                    last_tab_key = tab_key
                tab_url = ""
                if tab_key and nab_tabreader.looks_like_browser(title):
                    if tab_changed or clip_event:
                        url = ""
                        try:
                            ti = self.tab_server.get_tab_info() if self.tab_server else None
                        except Exception:
                            ti = None
                        if ti:
                            url = ti["url"]
                        else:
                            url = self._guarded(nab_tabreader.read_address_bar, 1.5, "", hwnd)
                        self._tab_url = (tab_key, url)
                    tab_url = self._tab_url[1] if self._tab_url[0] == tab_key else ""
                    if tab_url:
                        context += tab_url + " "
                        signal_text += tab_url + " "
                context_changed = bool(context.strip() and context != self.last_context)
                if context_changed or clip_event or tab_changed:
                    self.last_context = context
                    lock_paper = self._tab_locks.get(tab_key) if (tab_key and (tab_changed or clip_event)) else None
                    paper, how, detail = nab_clip_scan.detect_paper(
                        context, signal_text, self.url_mappings, self.paper_list,
                        lock_paper=lock_paper, allow_name_fallback=bool(clip_event and has_image))
                    self._dlog.append({"t": time.strftime("%H:%M:%S"), "title": (title or "")[:70], "url": (tab_url or snap["source_url"] or "")[:90],
                                       "clip": bool(clip_event), "img": bool(has_image), "paper": strip_emoji_prefix(paper) if paper else "",
                                       "how": how or ""})
                    if (clip_event and has_image) or tab_changed:
                        self._learn.note_event(time.time(), title, tab_url or snap["source_url"], paper)
                    try:
                        ph = self.page_hint(title, tab_url or snap["source_url"] or "")
                        if ph and ph != getattr(self, "_page_hint", ""):
                            self._page_hint = ph
                            self.hub.emit("page_hint", page=ph)
                        elif not ph:
                            self._page_hint = ""
                    except Exception:
                        pass
                    if paper:
                        if self.paper != paper:
                            label = {"mapping": f"'{detail}'", "lock": "locked tab", "name": "paper name"}.get(how, how)
                            self._apply_detected_paper(paper, label)
                    elif clip_event and has_image:
                        self.hub.emit("detect_miss", tab=(title or "(no window title)")[:34],
                                      src=(tab_url or snap["source_url"] or "")[:120])
                if self.auto_snatch and clip_event and has_image:
                    imgs = nab_clipboard.grab_images()
                    if imgs:
                        h = nab_clipboard.thumb_hash(imgs[0])
                        if h != self.last_clipboard_hash:
                            self.last_clipboard_hash = h
                            self.add_images(imgs)
                            self.hub.emit("snatched", n=len(self.doc.layers))
            except Exception as e:
                logging.error(f"monitor: {e}")

    # ───────────────────────────── background ticker ────────────────────────
    def start_ticker(self):
        threading.Thread(target=self._ticker_loop, daemon=True, name="NAB-Ticker").start()

    def _ticker_loop(self):
        from nab_telegram import _tg_send, PC_NAME
        time.sleep(10)
        while True:
            try:
                now = datetime.datetime.now()
                ex = self.extra_settings
                if (ex.get("daily_report_enabled") and now.hour == ex.get("daily_report_hour", 18)
                        and self._daily_report_sent_hour != now.hour):
                    self._daily_report_sent_hour = now.hour
                    threading.Thread(target=self._send_tg_report, daemon=True).start()
                if ex.get("autosave_enabled") and time.time() - self._last_autosave >= ex.get("autosave_interval", 300):
                    self._last_autosave = time.time()
                    dr = self.draft
                    if self.doc.visible_layers() and dr["cats"] and nab_meta.parse(dr["line"])["ok"]:
                        self.status("AUTO-SAVING…", "#888")
                        self.save(dr["cats"], dr["line"])
                today = now.strftime("%Y-%m-%d")
                if self.last_active_date and self.last_active_date != today and self._streak_once(today):
                    yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                    if self.last_active_date == yesterday:
                        self.current_streak = getattr(self, "current_streak", 0) + 1
                        if self.current_streak > 1:
                            threading.Thread(target=lambda s=self.current_streak: _tg_send(
                                f"🔥 <b>Streak: {s} days in a row!</b>\n💻 {PC_NAME}"), daemon=True).start()
                    else:
                        missed = (datetime.datetime.strptime(today, "%Y-%m-%d")
                                  - datetime.datetime.strptime(self.last_active_date, "%Y-%m-%d")).days
                        if missed > 1:
                            threading.Thread(target=lambda d=missed: _tg_send(
                                f"😴 <b>Streak broken!</b> {d} days with no clips on <b>{PC_NAME}</b>."), daemon=True).start()
                        self.current_streak = 0
            except Exception as e:
                logging.error(f"ticker: {e}")
            time.sleep(60)

    def _streak_once(self, today):
        """True only the first time per calendar day (remembered on disk, so restarts do not repeat it). Was sent every minute before."""
        f = os.path.join(os.path.dirname(self.settings_file), "nab_streak_day.txt")
        try:
            if open(f, "r").read().strip() == today:
                return False
        except Exception:
            pass
        try:
            with open(f, "w") as fh:
                fh.write(today)
        except Exception:
            if getattr(self, "_streak_mem", "") == today:
                return False
            self._streak_mem = today
        return True

    # ───────────────────────────── Telegram remote controls ─────────────────
    def _on_pause(self):
        self.paused = True
        self.hub.emit("pause", paused=True, sticky=True)

    def _on_resume(self):
        self.paused = False
        self.hub.emit("pause", paused=False, sticky=True)

    def _remote_set_date(self, date_str):
        from nab_telegram import _tg_send, PC_NAME
        try:
            self.current_date = datetime.datetime.strptime(date_str, "%d-%m-%Y")
            self._preview_cache = None
            self.hub.emit("date", date=self.current_date.strftime("%Y-%m-%d"))
            _tg_send(f"📅 Date set to <b>{date_str}</b> on {PC_NAME}.")
        except ValueError:
            _tg_send("❌ Invalid date format. Use DD-MM-YYYY.")

    def _remote_set_paper(self, paper_name):
        from nab_telegram import _tg_send, PC_NAME
        matches = [p for p in self.paper_list if paper_name.lower() in p.lower()]
        if matches:
            self.set_paper(matches[0])
            _tg_send(f"📰 Paper set to <b>{matches[0]}</b> on {PC_NAME}.")
        else:
            _tg_send(f"❌ No newspaper matching '{paper_name}' found on {PC_NAME}.")

    def _set_pending_note(self, note):
        self.pending_note = note
        self.toast(f"📝 Note from admin: {note}", "info", 12000)

    def _skip_auto_snatch(self):
        from nab_telegram import _tg_send, PC_NAME
        if self.auto_snatch:
            self.auto_snatch = False
            self.save_settings()
            self.hub.emit("settings_changed")
            _tg_send(f"⏭ Auto-snatch turned <b>OFF</b> on {PC_NAME}.")

    def _handle_broadcast(self, rest):
        msg = (rest or "").strip()
        if msg:
            self.hub.emit("broadcast", text=msg)

    def _show_expiry_warning(self, exp_str):
        self.hub.emit("expiry", text=exp_str)

    def _tg_send_preview(self):
        from nab_telegram import _tg_send, _tg_send_photo, PC_NAME
        if not self.doc.visible_layers():
            _tg_send(f"📭 No clips on canvas on <b>{PC_NAME}</b>.")
            return
        try:
            pr = self.render_preview(900)
            _tg_send_photo(pr["jpeg"], f"🖼 Canvas preview — {PC_NAME}")
        except Exception as e:
            _tg_send(f"❌ Preview failed: {e}")

    def _upload_old_files(self, category, scope):
        threading.Thread(target=self._upload_old_files_thread, args=(category, scope), daemon=True).start()

    def destroy(self):
        self.hub.emit("quit")
        self.after(600, lambda: os._exit(0))

    # ───────────────────────────── uploads (queue) ──────────────────────────
    def _load_uploaded(self):
        import json
        try:
            if os.path.exists(self._uploaded_file):
                with open(self._uploaded_file, "r", encoding="utf-8") as f:
                    self._uploaded = set(json.load(f))
        except Exception:
            self._uploaded = set()

    def _mark_uploaded(self, path):
        import json
        self._uploaded.add(path)
        try:
            with open(self._uploaded_file, "w", encoding="utf-8") as f:
                json.dump(sorted(self._uploaded)[-5000:], f)
        except Exception:
            pass

    def upload_enabled(self):
        return bool(self.extra_settings.get("upload_enabled", False))

    def pending_uploads(self):
        if not self.upload_enabled():
            return []
        return [h["path"] for h in self.session_history
                if os.path.exists(h.get("path", "")) and h["path"] not in self._uploaded]

    def _drive_upload_file(self, service, parent_id, file_path, filename):   # wraps the original
        if not self.upload_enabled():
            raise RuntimeError("Google upload is turned off (Settings → Sync).")
        self._upload["current"] = filename
        res = HeadlessOps._drive_upload_file(self, service, parent_id, file_path, filename)
        self._upload["done"] += 1
        self._mark_uploaded(file_path)
        self.hub.emit("upload", **self._upload)
        return res

    def upload_now(self):
        """Upload today's saved files in the background (small queue indicator)."""
        if not self.upload_enabled():
            return {"ok": False, "error": "Google upload is turned off — turn it on in Settings → Sync."}
        if self._upload["running"]:
            return {"ok": False, "error": "Already uploading."}
        today = self.current_date.strftime("%d-%m-%Y")

        def run():
            self._upload.update(running=True, done=0, current="", last_error="")
            self.hub.emit("upload", **self._upload)
            try:
                self._upload_date_list_thread("*", [today])
            except Exception as e:
                self._upload["last_error"] = str(e)
                logging.error(f"upload_now: {e}")
            self._upload.update(running=False, current="")
            self.hub.emit("upload", **self._upload)
            self.hub.emit("state_changed")
        threading.Thread(target=run, daemon=True, name="NAB-Upload").start()
        return {"ok": True}

    def upload_days(self):
        """Day folders on disk (newest first) for the 'upload older days' picker."""
        import re
        out = set()
        try:
            for y in os.listdir(self.base_root):
                yp = os.path.join(self.base_root, y)
                if not os.path.isdir(yp): continue
                for m in os.listdir(yp):
                    mp = os.path.join(yp, m)
                    if not os.path.isdir(mp): continue
                    for d in os.listdir(mp):
                        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", d) and os.path.isdir(os.path.join(mp, d)):
                            out.add(d)
        except OSError:
            pass
        key = lambda s: (s[6:], s[3:5], s[:2])
        return {"ok": True, "days": sorted(out, key=key, reverse=True)}

    def upload_dates(self, dates, category="*"):
        if not self.upload_enabled():
            return {"ok": False, "error": "Google upload is turned off — turn it on in Settings → Sync."}
        if self._upload["running"]:
            return {"ok": False, "error": "Already uploading."}
        dates = [d for d in (dates or []) if d]
        if not dates:
            return {"ok": False, "error": "Pick at least one day."}

        def run():
            self._upload.update(running=True, done=0, current="", last_error="")
            self.hub.emit("upload", **self._upload)
            try:
                self._upload_date_list_thread(category or "*", dates)
            except Exception as e:
                self._upload["last_error"] = str(e)
            self._upload.update(running=False, current="")
            self.hub.emit("upload", **self._upload)
            self.hub.emit("state_changed")
        threading.Thread(target=run, daemon=True, name="NAB-Upload2").start()
        return {"ok": True}

    def schedule_upload_next_session(self):
        self.extra_settings["pending_upload_date"] = self.current_date.strftime("%d-%m-%Y")
        self.save_settings()
        return {"ok": True}

    def drive_test(self):
        svc = self._get_gdrive_service()
        root = self._drive_get_root_id()
        if not svc:
            return {"ok": False, "error": "Google key isn't bundled in this build."}
        try:
            svc.files().get(fileId=root, fields="id,name", supportsAllDrives=True).execute()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ───────────────────────────── sync ─────────────────────────────────────
    def start_sync(self):
        import nab_settings_sync
        self._sync = nab_settings_sync.SyncManager(self, self._on_synced)
        self._sync.start()

    def sync_now(self):
        if self._sync:
            self._sync.sync_now()
        return {"ok": True}

    def sync_status(self):
        s = getattr(self._sync, "last", None) or {}
        res = s.get("result") or {}
        return {"time": s.get("time"), "no_drive": s.get("no_drive", False), "offline": bool(res.get("offline")),
                "pulled": list(res.get("pulled", []) or []), "pushed": list(res.get("pushed", []) or []),
                "conflicts": list(res.get("conflicts", []) or []), "awaiting": list(res.get("awaiting", []) or []),
                "approval": bool(self.extra_settings.get("sync_approval", True)), "file": __import__("nab_settings_sync").drive_file_name(), "started": self._sync is not None,
                "role": __import__("nab_settings_sync").get_role(), "role_pending": bool(getattr(self, "_role_pending", False))}

    def sync_set_role(self, role=None, sid=None):
        """Followers download only. Becoming the owner (the only PC that uploads) needs a Telegram approval."""
        import nab_settings_sync as S
        if sid is not None:
            S.set_role(sid=sid)
        if role == "follower":
            S.set_role(role="follower")
        elif role == "owner" and S.get_role()["role"] != "owner":
            if getattr(self, "_role_pending", False):
                return {"ok": True, "pending": True}
            self._role_pending = True

            def work():
                try:
                    import nab_auth
                    ok = nab_auth.TelegramAuth.request_sync_approval("Make this PC the settings OWNER (the only PC that uploads)")
                    if ok:
                        S.set_role(role="owner")
                finally:
                    self._role_pending = False
                    self.hub.emit("state_changed")
            threading.Thread(target=work, daemon=True, name="NAB-RoleAsk").start()
            return {"ok": True, "pending": True}
        self.sync_now()
        self.hub.emit("state_changed")
        return {"ok": True}

    def sync_history(self, limit=60):
        try:
            c = (getattr(self._sync, "last", {}) or {}).get("client")
            if c is None:
                import nab_settings_sync as S
                c = S.make_drive_client(self)
            if c is None:
                return []
            out = []
            for ns in ("app_settings", "url_mappings", "sources", "categories", "subscriptions",
                       "paper_aliases", "pdf_maker"):
                out.extend(c.get_config_history(ns, 8))
            out.sort(key=lambda e: e.get("at", ""), reverse=True)
            return out[:limit]
        except Exception as e:
            logging.error(f"sync_history: {e}")
            return []

    def _on_synced(self, namespaces):
        try:
            ns = set(namespaces)
            if ns & {"app_settings", "url_mappings"}:
                self.load_settings()
                self.last_context = ""
            if "sources" in ns:
                cur = self.paper
                self.load_sources()
                if cur in self.paper_list:
                    self.paper = cur
            if "categories" in ns:
                self.load_categories()
            self._preview_cache = None
            self.hub.emit("synced", namespaces=list(namespaces))
            self.hub.emit("state_changed")
        except Exception as e:
            logging.error(f"_on_synced: {e}")

    # ───────────────────────────── updates ──────────────────────────────────
    def start_update_loop(self):
        threading.Thread(target=self._update_loop, daemon=True, name="NAB-UpdateCheck").start()

    def _update_loop(self):
        try:
            import nab_update as U
        except Exception as e:
            logging.error(f"update import: {e}")
            return
        if not getattr(U, "GITHUB_REPO", ""):
            return
        time.sleep(3)
        while True:
            try:
                remote_ver, dl_url = U._github_get_latest_release()
                if remote_ver and dl_url and U._ver(remote_ver) > U._ver(_app_version()):
                    self._update = {"stage": "downloading", "pct": 0, "version": remote_ver}
                    self.hub.emit("update", sticky=True, **self._update)
                    dest = U._update_zip_path() if U._is_frozen() else U._current_exe() + ".new"

                    def prog(p):
                        self._update = {"stage": "downloading", "pct": int(p), "version": remote_ver}
                        self.hub.emit("update", sticky=True, **self._update)
                    ok, err = U._github_download_silently(dl_url, dest, progress_cb=prog)
                    if ok:
                        self._update = {"stage": "ready", "version": remote_ver, "path": dest}
                        self.hub.emit("update", sticky=True, **self._update)
                        return
                    self._update = {"stage": "idle"}
                    self.hub.emit("update", sticky=True, **self._update)
                    logging.error("Silent download failed: " + str(err))
            except Exception as e:
                logging.error("github_version_check: " + str(e))
            time.sleep(getattr(U, "GITHUB_CHECK_INTERVAL", 300))

    def apply_update(self):
        try:
            import nab_update as U
            if self._update.get("stage") != "ready":
                return {"ok": False, "error": "No update is ready."}
            updater = os.path.join(os.path.dirname(U._current_exe()), "nab_updater.exe")
            if U._is_frozen() and not os.path.exists(updater):
                return {"ok": False, "error": "nab_updater.exe not found next to NAB.exe. Download it from GitHub Releases and try again."}
            if getattr(self, "_applying", False):
                return {"ok": True}
            self._applying = True
            threading.Thread(target=self._apply_worker, args=(updater,), daemon=True, name="NAB-Apply").start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _apply_worker(self, updater):
        """Unpack (with progress), start the helper, then really quit so the helper can swap the files."""
        import nab_update as U, zipfile, shutil, tempfile, subprocess
        ver = self._update.get("version", "")

        def emit(pct, msg, **k):
            self.hub.emit("update", sticky=True, stage="applying", version=ver, pct=pct, msg=msg, **k)
        try:
            path = self._update["path"]
            emit(2, "Checking the package")
            if str(path).lower().endswith(".zip"):
                out = os.path.join(os.path.dirname(path), "new")
                shutil.rmtree(out, ignore_errors=True)
                os.makedirs(out, exist_ok=True)
                with zipfile.ZipFile(path) as z:
                    infos = z.infolist()
                    total = sum(i.file_size for i in infos) or 1
                    done = 0
                    last = -1
                    for i in infos:
                        z.extract(i, out)
                        done += i.file_size
                        pc = 5 + int(done * 80 / total)
                        if pc != last:
                            last = pc
                            emit(pc, "Unpacking the new version")
                root = out
                if not os.path.exists(os.path.join(root, "NAB.exe")):
                    subs = [x for x in os.listdir(out) if os.path.isdir(os.path.join(out, x))]
                    if len(subs) == 1 and os.path.exists(os.path.join(out, subs[0], "NAB.exe")):
                        root = os.path.join(out, subs[0])
                if not os.path.exists(os.path.join(root, "NAB.exe")) or not os.path.isdir(os.path.join(root, "_internal")):
                    raise ValueError("update package is incomplete")
                new_dir = root
            else:
                new_dir = path
            emit(88, "Starting the installer")
            app_dir = os.path.dirname(U._current_exe())
            src = os.path.join(app_dir, "nab_updater.exe")
            run = os.path.join(tempfile.gettempdir(), "NAB_updater_run.exe")
            shutil.copy2(src, run)
            subprocess.Popen([run, app_dir if os.path.isdir(new_dir) else U._current_exe(), new_dir, str(os.getpid())])
            emit(96, "Restarting NAB")
            time.sleep(1.5)
            emit(100, "Restarting NAB")
            time.sleep(0.8)
            logging.info("update: quitting for the updater")
            os._exit(0)                                              # sys.exit here only ends this thread
        except Exception as e:
            logging.error(f"apply update: {e}")
            self._applying = False
            self.hub.emit("update", sticky=True, stage="apply_error", version=ver, error=str(e)[:200])

    # ───────────────────────────── login / session ──────────────────────────
    def _session_init(self):
        import nab_session
        from nab_telegram import PC_NAME
        nab_session.init(os.path.dirname(self.settings_file), PC_NAME)
        return nab_session

    def login_precheck(self):
        """What the lock screen should do: start silently (remembered / quick re-login) or ask which way to authorise."""
        out = {"auto": None, "mode": self.ui_get("auth_mode", ""), "grace": int(self.ui_get("auth_grace", 10)),
               "until": self.ui_get("auth_remember_until", "23:59")}
        try:
            import nab_access
            from nab_telegram import PC_NAME
            if PC_NAME in (nab_access._load_blocked_pcs() or {}):
                return out
            kind, d = self._session_init().check(out["grace"])
            out["auto"] = kind
        except Exception as e:
            logging.error(f"precheck: {e}")
        return out

    def _remember_ts(self):
        import datetime as _dt
        hhmm = str(self.ui_get("auth_remember_until", "23:59") or "23:59")
        try:
            h, m = [int(x) for x in hhmm.split(":")[:2]]
        except Exception:
            h, m = 23, 59
        now = _dt.datetime.now()
        t = now.replace(hour=min(23, max(0, h)), minute=min(59, max(0, m)), second=0, microsecond=0)
        if t <= now:
            t = now.replace(hour=23, minute=59, second=59, microsecond=0)
        return t.timestamp()

    def _remember_long_ts(self):
        import datetime as _dt
        try:
            days = max(2, min(60, int(self.ui_get("auth_remember_days", 7))))
        except Exception:
            days = 7
        t = (_dt.datetime.now() + _dt.timedelta(days=days - 1)).replace(hour=23, minute=59, second=0, microsecond=0)
        return t.timestamp()

    # ---- batch: work through a folder of page images one after another ----
    def batch_start(self, folder):
        folder = (folder or "").strip().strip('"')
        if not os.path.isdir(folder):
            return {"ok": False, "error": "That folder was not found."}
        exts = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")
        nat = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", t)]
        files = sorted([os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(exts)], key=lambda p: nat(os.path.basename(p)))
        if not files:
            return {"ok": False, "error": "No images in that folder."}
        self._batch = {"files": files, "i": 0, "folder": folder}
        return self.batch_next()

    def batch_next(self):
        b = getattr(self, "_batch", None)
        if not b:
            return {"ok": False, "error": "No batch is open."}
        while b["i"] < len(b["files"]):
            p = b["files"][b["i"]]
            b["i"] += 1
            try:
                with Image.open(p) as im:
                    im.load()
                    img = im.convert("RGB")
            except Exception as e:
                logging.error(f"batch open {p}: {e}")
                continue
            self.add_images([img], os.path.basename(p))
            left = len(b["files"]) - b["i"]
            if not left:
                self._batch = None
            return {"ok": True, "name": os.path.basename(p), "n": b["i"], "total": len(b["files"]), "left": left}
        self._batch = None
        return {"ok": True, "done": True, "left": 0}

    def batch_stop(self):
        self._batch = None
        return {"ok": True}

    # ---- accounts ----
    def acct_is_owner_pc(self):
        try:
            import nab_settings_sync as S
            return S.get_role()["role"] == "owner"
        except Exception:
            return False

    def acct_can_manage(self):
        """Only the owner PC creates or changes accounts (other PCs download them). On that PC: an owner account,
        or nobody signed in with an account (the Telegram-approved owner PC), or no accounts yet."""
        import nab_accounts
        if not self.acct_is_owner_pc():
            return False
        cur = nab_accounts.current()
        return (not cur["role"]) or cur["role"] == "owner"

    def _acct_precheck(self):
        import nab_accounts
        from nab_telegram import PC_NAME
        nab_accounts.init(PC_NAME)
        try:
            import nab_access
            if PC_NAME in (nab_access._load_blocked_pcs() or {}):
                return {"ok": False, "error": "This PC is blocked."}
        except Exception:
            pass
        return None

    def _acct_granted(self, r):
        if r.get("ok") and not self.authorized:
            self.authorized = True
            self._login_started = True
            self.hub.emit("login", sticky=True, stage="granted", how="account")
            self._start_session_touch()
            self.after_login()
        if r.get("ok"):
            self.hub.emit("state_changed")
        return r

    def acct_login(self, name, password):
        import nab_accounts
        bad = self._acct_precheck()
        if bad:
            return bad
        return self._acct_granted(nab_accounts.login(name, password))

    def acct_google_poll(self):
        import nab_google
        import nab_accounts
        p = nab_google.poll()
        if p["state"] == "ok":
            bad = self._acct_precheck()
            return bad or dict(self._acct_granted(nab_accounts.login_google(p["email"], p.get("name", ""))), state="done")
        return {"ok": p["state"] != "error", "state": p["state"], "error": p["error"]}

    def begin_login(self, mode="group", reason="", auto=False):
        def run():
            granted = False
            note = ""
            try:
                import nab_auth
                import nab_telegram
                sess = self._session_init()
                kind = None
                if auto:
                    kind, _d = sess.check(int(self.ui_get("auth_grace", 10)))
                if kind:
                    granted = True
                    note = kind
                    try:
                        from nab_telegram import _tg_send, PC_NAME
                        label = "remembered on this PC" if kind == "remember" else "reopened within the grace window"
                        threading.Thread(target=lambda: _tg_send(f"🔓 <b>NAB opened without a new request</b> ({label})\n💻 PC: <code>{PC_NAME}</code>"), daemon=True).start()
                    except Exception:
                        pass
                else:
                    md = "owner" if mode == "owner" else "group"
                    self.ui_set(auth_mode=md)
                    self.hub.emit("login", sticky=True, stage="waiting", timeout=nab_telegram.AUTH_TIMEOUT, mode=md)
                    granted = nab_auth.TelegramAuth.request_access(mode=md, reason=reason, remember_until=self._remember_ts(), remember_long=self._remember_long_ts())
                    if granted and getattr(nab_auth.TelegramAuth, "_remember_until", None):
                        sess.remember(nab_auth.TelegramAuth._remember_until)
            except Exception as e:
                logging.error(f"login: {e}")
                granted = False
            if granted:
                self.authorized = True
                self.hub.emit("login", sticky=True, stage="granted", how=note)
                self._start_session_touch()
                self.after_login()
            else:
                self.hub.emit("login", sticky=True, stage="denied")
                self.after(2200, self.destroy)
        threading.Thread(target=run, daemon=True, name="NAB-Login").start()

    def _start_session_touch(self):
        def loop():
            try:
                import nab_auth
                sess = self._session_init()
                while True:
                    sess.touch(getattr(nab_auth.TelegramAuth, "_access_deadline", None))
                    time.sleep(30)
            except Exception as e:
                logging.error(f"session touch: {e}")
        threading.Thread(target=loop, daemon=True, name="NAB-Session").start()

    def after_login(self):
        if self._started:
            return
        self._started = True
        from nab_telegram import _tg_send, PC_NAME
        threading.Thread(target=lambda: _tg_send(
            f"✅ <b>NAB Session Started</b>\n💻 PC: <code>{PC_NAME}</code>\n"
            f"📰 Active paper: {self.paper}\n📅 Date: {self.current_date.strftime('%d-%m-%Y')}"), daemon=True).start()
        import nab_auth
        threading.Thread(target=nab_auth.TelegramAuth.run_background_listener, args=(self,), daemon=True,
                         name="NAB-TGListener").start()
        try:
            import nab_tabserver
            self.tab_server = nab_tabserver.TabServer().start()
        except Exception as e:
            logging.error(f"tab server: {e}")
        try:
            self.app_version = _app_version()
        except Exception:
            self.app_version = ""
        try:
            if self.slow_pc():
                nab_core.MAX_UNDO = 10          # fewer undo snapshots = less memory on weak PCs
        except Exception:
            pass
        threading.Thread(target=self.backup_auto, daemon=True, name="NAB-Backup").start()
        if os.path.isdir(self.ext_install_dir()):       # keep the installed extension files in step with this version
            threading.Thread(target=self.ext_prepare, daemon=True, name="NAB-ExtSync").start()
        self.draft_start()
        self.hub.emit("draft", **self.draft_check())
        self.start_monitor()
        self.start_ticker()
        self.start_sync()
        try:
            import nab_schedule, nab_tools
            nab_schedule.start(self)
            nab_tools.get("hunt", self).resume_auto()
        except Exception as ex:
            logging.error(f"schedule start: {ex}")
        self.start_update_loop()
        self.after(3000, self._check_pending_upload)
        self.hub.emit("state_changed")

    # ───────────────────────────── closing ──────────────────────────────────
    def close_summary(self):
        return {"saves": len(self.session_history), "pending": len(self.pending_uploads()),
                "today": self.current_date.strftime("%d-%m-%Y")}

    def tracker_end_prompt(self):
        """End-of-day tracker prompt runs as its own process (it needs Tk). Exit code 2 = operator cancelled the close."""
        try:
            import nab_update as U
            exe = U._current_exe()
            cmd = ([exe] if U._is_frozen() else [sys.executable, exe]) + ["--tool", "tracker-end"]
            rc = subprocess.run(cmd, cwd=os.path.dirname(exe), timeout=900).returncode
            return "cancel" if rc == 2 else "ok"
        except Exception as e:
            logging.error(f"tracker_end_prompt: {e}")
            return "ok"

    def shutdown(self, upload=False):
        from nab_telegram import _tg_send, PC_NAME
        try:
            import nab_auth
            ta = nab_auth.TelegramAuth
            if ta._session_start:
                el = int(time.time() - ta._session_start)
                hrs, rem = divmod(el, 3600)
                threading.Thread(target=_tg_send, args=(
                    f"🔴 <b>NAB Closed</b>\n\n💻 PC: <code>{PC_NAME}</code>\n🕐 Session: {hrs}h {rem // 60}m\n"
                    f"💾 Files saved: {len(self.session_history)}",), daemon=True).start()
        except Exception as e:
            logging.error(f"shutdown: {e}")
        self.save_settings()
        try:
            if self._sync:
                self._sync.push_on_close(2.5)
        except Exception:
            pass
        time.sleep(0.1)

    # ───────────────────────────── tools (other windows) ────────────────────
    def launch_tool(self, name):
        flags = {"pdf": ["--pdf-bot"], "ocr": ["--ocr-finder"], "tracker": ["--tool", "tracker"],
                 "subscriptions": ["--tool", "subscriptions"], "batch": ["--classic"],
                 "classic": ["--classic"]}
        if name not in flags:
            return {"ok": False, "error": "unknown tool"}
        try:
            import nab_update as U
            exe = U._current_exe()
            cmd = ([exe] if U._is_frozen() else [sys.executable, exe]) + flags[name]
            if name == "pdf":
                folder = self._dest_folder([])
                if os.path.isdir(folder):
                    pass
            subprocess.Popen(cmd, cwd=os.path.dirname(exe))
            return {"ok": True}
        except Exception as e:
            logging.error(f"launch_tool {name}: {e}")
            return {"ok": False, "error": str(e)}

    def pdf_today(self):
        folder = self._dest_folder([])
        if not os.path.isdir(folder):
            return {"ok": False, "error": "Nothing has been saved today yet."}
        try:
            import nab_update as U
            exe = U._current_exe()
            cmd = ([exe] if U._is_frozen() else [sys.executable, exe]) + ["--pdf-bot", "--auto-folder", folder]
            subprocess.Popen(cmd, cwd=os.path.dirname(exe))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reveal(self, path=None):
        import nab_recent
        p = path or self.last_saved_path
        if not p:
            return {"ok": False, "error": "No folder saved to yet this session."}
        if os.path.isdir(p):
            try:
                if os.name == "nt":
                    os.startfile(p)
                else:
                    subprocess.Popen(["xdg-open", p])
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        nab_recent.show_in_folder(p)
        return {"ok": True}

    # ───────────────────────────── connections (Advanced) ───────────────────
    def connections_get(self):
        nc = nab_connections
        return {"overrides": {k: nc.override(k) for k in ("drive_folder_id", "cloud_url", "sheet_id",
                                                           "telegram_token", "google_key_path")},
                "builtin": {"drive_folder_id": nc.BUILTIN_DRIVE_FOLDER_ID, "cloud_url": nc.BUILTIN_CLOUD_URL,
                            "sheet_id": nc.BUILTIN_SHEET_ID},
                "summary": nc.summary()}

    def connections_set(self, values, reset=False):
        nc = nab_connections
        if reset:
            nc.reset_all()
            return {"ok": True, "restart": True}
        restart = False
        for k, v in (values or {}).items():
            if k in ("drive_folder_id", "cloud_url", "sheet_id", "telegram_token", "google_key_path"):
                if k == "telegram_token" and (v or "") != nc.override(k):
                    restart = True
                nc.set_override(k, v or "")
        return {"ok": True, "restart": restart}


def _pc_name():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "PC"
