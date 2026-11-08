# nab_server.py — NABPreviewServer (WebSocket) + MiniOverlay
import json
import base64
import logging
import threading
import io
import asyncio
import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk
from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})

class NABPreviewServer:
    """Lightweight WebSocket server that broadcasts canvas previews."""

    THUMB_W = 300          # thumbnail width sent to extension (px)
    THUMB_Q = 60           # JPEG quality for thumbnails

    def __init__(self):
        self._clients    = set()
        self._loop       = None
        self._thread     = None
        self._last_frame = None   # bytes of the last JPEG thumbnail
        self._clip_count = 0
        self._running    = False
        self.tab_info    = {"url": "", "title": "", "ts": 0.0}

    def get_tab_info(self, max_age=8.0):
        """Latest {url,title} pushed by the Tab Reporter extension, or None
        if nothing arrived recently (extension not installed / browser idle)."""
        import time as _t
        ti = self.tab_info
        if ti.get("url") and _t.time() - ti.get("ts", 0) <= max_age:
            return dict(ti)
        return None

    @staticmethod
    def _origin_ok(websocket):
        """Only browser extensions (or non-browser clients, which send no
        Origin) may feed tab info — a random web page must not be able to
        steer paper detection."""
        try:
            hdrs = websocket.request.headers
            origin = hdrs.get("Origin", "") or ""
        except Exception:
            return True
        return (not origin) or origin.startswith(("chrome-extension://", "moz-extension://"))

    def _handle_inbound(self, websocket, raw):
        import json as _j, time as _t
        if isinstance(raw, (bytes, bytearray)) or not self._origin_ok(websocket):
            return
        try:
            m = _j.loads(raw)
        except Exception:
            return
        if isinstance(m, dict) and m.get("type") == "tab_info":
            url = str(m.get("url", ""))[:2000]
            if url.startswith(("http://", "https://")):
                self.tab_info = {"url": url, "title": str(m.get("title", ""))[:300],
                                 "ts": _t.time()}

    def start(self):
        if not HAS_WS:
            logging.warning("NABPreviewServer: websockets not installed — pip install websockets")
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="NAB-WS")
        self._thread.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            logging.error(f"NABPreviewServer: {e}")

    async def _serve(self):
        self._running = True
        async with _ws_lib.serve(self._handler, "127.0.0.1", NAB_WS_PORT,
                                  ping_interval=20, ping_timeout=10):
            logging.info(f"NABPreviewServer: listening on ws://127.0.0.1:{NAB_WS_PORT}")
            await asyncio.Future()   # run forever

    async def _handler(self, websocket):
        self._clients.add(websocket)
        logging.info(f"NABPreviewServer: client connected ({len(self._clients)} total)")
        try:
            # Send the current frame immediately on connect
            if self._last_frame:
                await self._send_frame(websocket, self._last_frame)
            async for raw in websocket:
                self._handle_inbound(websocket, raw)   # tab_info from Tab Reporter
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)

    async def _send_frame(self, ws, jpeg_bytes):
        b64 = base64.b64encode(jpeg_bytes).decode()
        msg = json.dumps({
            "type":        "canvas_update",
            "image_b64":   b64,
            "clip_count":  self._clip_count,
        })
        await ws.send(msg)

    def broadcast(self, pil_image, clip_count, last_action=""):
        """Called from the main Tkinter thread after every canvas update.
        Scales the image to a thumbnail and broadcasts to all connected clients."""
        if not self._clients or not self._loop:
            return
        try:
            thumb = pil_image.copy()
            ratio = self.THUMB_W / max(thumb.width, 1)
            th    = max(1, int(thumb.height * ratio))
            thumb = thumb.resize((self.THUMB_W, th), Image.Resampling.BILINEAR)
            buf   = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=self.THUMB_Q)
            jpeg_bytes = buf.getvalue()
        except Exception as e:
            logging.error(f"NABPreviewServer.broadcast: {e}")
            return

        self._last_frame = jpeg_bytes
        self._clip_count = clip_count

        msg = json.dumps({
            "type":        "canvas_update",
            "image_b64":   base64.b64encode(jpeg_bytes).decode(),
            "clip_count":  clip_count,
            "last_action": last_action,
        })

        async def _bcast():
            dead = set()
            for client in list(self._clients):
                try:
                    await client.send(msg)
                except Exception:
                    dead.add(client)
            self._clients -= dead

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_bcast(), self._loop)

# Global singleton — created before NewsClipper, shared via self.preview_server
_preview_server = NABPreviewServer()


# ── NAB Mini Overlay (shown when main window is minimized) ──────────────────
#
# No separate window to open. When the user minimizes NAB:
#   • A small always-on-top frameless overlay appears in the bottom-right corner
#   • It shows a live thumbnail of the current canvas
#   • Ctrl+S triggers process_final() → metadata popup → save, all without
#     restoring the full window
#   • Any other shortcut (Ctrl+Z, Ctrl+V …) also works through the overlay
#   • Restoring NAB hides the overlay automatically

class MiniOverlay(tk.Toplevel):
    """Frameless always-on-top mini canvas shown while NAB is minimised."""

    W         = 260          # overlay width  (px)
    H         = 320          # overlay height (px)
    MARGIN    = 18           # distance from screen edge
    REFRESH   = 600          # thumbnail refresh interval (ms)
    THUMB_Q   = 70

    def __init__(self, master):
        # CRITICAL: do NOT pass master to super().__init__().
        # If this Toplevel is a child of NAB (master), Windows automatically
        # minimises it together with NAB — so it never actually appears on
        # screen when NAB is iconified. Creating it with no parent makes it
        # a top-level independent window that survives NAB's minimise.
        super().__init__()
        self._master  = master
        self._tk_img  = None
        self._job     = None
        self._drag_ox = self._drag_oy = 0

        # ── Window chrome ───────────────────────────────────────────────────
        self.overrideredirect(True)          # no title bar
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.93)
        try:
            self.attributes("-toolwindow", True)   # keeps it off the taskbar (Win)
        except Exception:
            pass
        self.configure(bg="#0A0A0A")

        # Position: bottom-right of screen
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = sw - self.W - self.MARGIN
        y  = sh - self.H - self.MARGIN - 48   # above taskbar
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # ── UI ──────────────────────────────────────────────────────────────
        # Header bar (drag handle + label + restore + close buttons)
        hdr = tk.Frame(self, bg="#111111", height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="📰 NAB", bg="#111111", fg="#1E88E5",
                 font=("Consolas", 10, "bold")).pack(side="left", padx=8)

        tk.Button(hdr, text="✕", bg="#111111", fg="#555", relief="flat",
                  font=("Consolas", 9), cursor="hand2", bd=0,
                  activebackground="#222", activeforeground="#EF5350",
                  command=self._on_close).pack(side="right", padx=4)

        tk.Button(hdr, text="□", bg="#111111", fg="#888", relief="flat",
                  font=("Consolas", 9), cursor="hand2", bd=0,
                  activebackground="#222", activeforeground="#EEE",
                  command=self._restore_main).pack(side="right", padx=2)

        self._status_lbl = tk.Label(hdr, text="", bg="#111111", fg="#555",
                                     font=("Consolas", 8))
        self._status_lbl.pack(side="right", padx=6)

        # Canvas thumbnail
        self._cv = Canvas(self, bg="#1A1A1A", highlightthickness=0)
        self._cv.pack(fill="both", expand=True, padx=4, pady=4)

        # Footer — shortcut hints
        ftr = tk.Frame(self, bg="#0A0A0A", height=20)
        ftr.pack(fill="x")
        ftr.pack_propagate(False)
        tk.Label(ftr, text="Ctrl+S = Save   Ctrl+V = Paste",
                 bg="#0A0A0A", fg="#333", font=("Consolas", 8)).pack()

        # ── Dragging ────────────────────────────────────────────────────────
        hdr.bind("<ButtonPress-1>",   self._drag_start)
        hdr.bind("<B1-Motion>",       self._drag_move)

        # ── Keyboard shortcuts forwarded to main app ─────────────────────
        # Bind every shortcut key so they work while the overlay has focus
        self.bind("<Control-s>",      lambda e: self._fwd(master.process_final))
        self.bind("<Control-S>",      lambda e: self._fwd(master.process_final))
        self.bind("<Control-v>",      lambda e: self._fwd(master.paste_image))
        self.bind("<Control-V>",      lambda e: self._fwd(master.paste_image))
        self.bind("<Control-z>",      lambda e: self._fwd(master.undo))
        self.bind("<Control-Z>",      lambda e: self._fwd(master.undo))
        self.bind("<Control-y>",      lambda e: self._fwd(master.redo))
        self.bind("<Control-Y>",      lambda e: self._fwd(master.redo))
        # Click the thumbnail to restore
        self._cv.bind("<Double-Button-1>", lambda e: self._restore_main())

        self._refresh()
        self._keep_on_top()

    def _keep_on_top(self):
        """Re-assert always-on-top every 1s. Windows can reset this when
        other windows steal focus (e.g. full-screen apps, UAC dialogs)."""
        try:
            if self.winfo_exists():
                self.attributes("-topmost", True)
                self.lift()
                self.after(1000, self._keep_on_top)
        except Exception:
            pass

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _fwd(self, fn):
        """Forward a shortcut to the main app, restoring window if needed
        only for actions that require the full UI (like process_final which
        shows a dialog — dialogs need their parent window visible)."""
        try:
            # For process_final we must deiconify first so the dialog
            # has a visible parent to attach to.
            if fn == self._master.process_final:
                self._master.deiconify()
                self._master.lift()
                self._master.after(80, fn)
            else:
                fn()
        except Exception as e:
            logging.error(f"MiniOverlay._fwd: {e}")

    def _restore_main(self):
        self._master.deiconify()
        self._master.lift()
        self._master.focus_force()

    def _on_close(self):
        """Hide the overlay without restoring — user can still restore via taskbar."""
        self.withdraw()

    def _drag_start(self, e):
        self._drag_ox = e.x_root - self.winfo_x()
        self._drag_oy = e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    def _refresh(self):
        try:
            if not self.winfo_exists():
                return
            m = self._master
            cw = max(self._cv.winfo_width(),  self.W - 8)
            ch = max(self._cv.winfo_height(), self.H - 52)

            if not m.orig_images:
                self._cv.delete("all")
                self._cv.create_text(cw // 2, ch // 2,
                    text="Canvas empty\nPaste a clip to begin",
                    fill="#333", font=("Consolas", 9), justify="center")
                self._status_lbl.configure(text="0 clips")
            else:
                merged = m._get_stitched_clips(use_proxy=True)
                ratio  = min(cw / max(merged.width, 1), ch / max(merged.height, 1))
                tw     = max(1, int(merged.width  * ratio))
                th_    = max(1, int(merged.height * ratio))
                thumb  = merged.resize((tw, th_), Image.Resampling.BILINEAR)
                self._tk_img = ImageTk.PhotoImage(thumb)
                self._cv.delete("all")
                self._cv.create_image(cw // 2, ch // 2,
                                      image=self._tk_img, anchor="center")
                n = len(m.orig_images)
                self._status_lbl.configure(text=f"{n} clip{'s' if n!=1 else ''}")
        except Exception as e:
            logging.error(f"MiniOverlay._refresh: {e}")
        finally:
            if self.winfo_exists():
                self._job = self.after(self.REFRESH, self._refresh)

    def destroy(self):
        if self._job:
            try: self.after_cancel(self._job)
            except: pass
        super().destroy()


