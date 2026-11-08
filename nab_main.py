# nab_main.py — NAB 3 launcher: engine + local web server + native window (pywebview), overlay, global switch hotkey.
import os
import sys
import time
import logging
import threading
import subprocess

import nab_winutil as W

TITLE = "News Automation Pro"
OVERLAY_TITLE = "NAB Overlay"


def _warm_imports():
    def go():
        try:
            import nab_constants  # noqa: F401
            import nab_telegram  # noqa: F401
            import nab_auth  # noqa: F401
            import numpy, cv2, nab_core, nab_extras  # noqa: F401  (first paste / trim is then instant)
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()


def build():
    from nab_engine_host import Engine
    from nab_web import NabServer
    engine = Engine()
    srv = NabServer(engine).start()
    return engine, srv


class Shell:
    """Native-window glue shared by the pywebview and msedge modes."""

    def __init__(self, engine=None, srv=None):
        self.e, self.srv = engine, srv
        self.main = None
        self.ov = None
        self.ov_visible = False
        self.ov_small = False
        self.stop = threading.Event()
        self.quitting = False
        self._ov_lock = threading.RLock()
        if srv:
            self.attach(engine, srv)

    def attach(self, engine, srv):
        self.e, self.srv = engine, srv
        srv.on_quit = self.quit
        srv.window_handler = self.handle

    # ---- quitting
    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.stop.set()
        for t_ in (TITLE, OVERLAY_TITLE):                   # the windows vanish at once; the rest of the shutdown happens unseen
            try:
                W.show_window(W.find_window(t_), False)
            except Exception:
                pass

        def work():
            try:
                if self.e:
                    self.e.shutdown()
            except Exception as e:
                logging.error(f"shutdown: {e}")
        th = threading.Thread(target=work, daemon=True, name="NAB-Shutdown")
        th.start()
        th.join(4.0)                                        # never hang on a slow network call
        os._exit(0)

    # ---- window actions (from the page)
    def handle(self, action, a):
        try:
            if action == "overlay":
                h_ = W.find_window(OVERLAY_TITLE) if W.IS_WIN else 0
                self.set_overlay(not (W.is_visible(h_) if h_ else self.ov_visible))
            elif action == "overlay_size":
                self.ov_small = bool(a.get("small"))
                if self.ov:
                    sz = self.e.ui_get("overlay_size") or [300, 440]
                    self.ov_set_size(int(sz[0]), 190 if self.ov_small else int(sz[1]))
            elif action == "overlay_resize":
                w = max(240, min(900, int(a.get("w", 300)))); hh = max(150, min(1200, int(a.get("h", 440))))
                self._ov_js_t = time.time()
                self.ov_set_size(w, hh)
                if a.get("final"):
                    self.e.ui_set(overlay_size=[w, hh])
            elif action == "ov_js":
                self._ov_js_t = time.time()
            elif action == "overlay_hide":
                if a.get("off"):
                    self.e.ui_set(overlay_auto=False)
                self.set_overlay(False)
            elif action == "ov_track":
                threading.Thread(target=self.ov_track, args=(a.get("mode"),), daemon=True).start()
            elif action == "restore":
                self.restore_main()
            elif action == "fullscreen":
                if self.main:
                    self.main.toggle_fullscreen()
            elif action == "minimize":
                if self.main:
                    self.main.minimize()
            return {"ok": True}
        except Exception as e:
            logging.error(f"window {action}: {e}")
            return {"ok": False, "error": str(e)}

    def ov_set_size(self, w, hh):
        """Resize the overlay to w x hh (CSS px): native SetWindowPos first, pywebview as the fallback."""
        try:
            if W.IS_WIN:
                h = W.find_window(OVERLAY_TITLE)
                rc = W.window_rect(h) if h else None
                if rc:
                    sc = W.dpi_scale(h)
                    if W.move_resize(h, rc[0], rc[1], int(w * sc), int(hh * sc)):
                        return
        except Exception as ex:
            logging.error(f"ov_set_size native: {ex}")
        try:
            if self.ov:
                self.ov.resize(int(w), int(hh))
        except Exception as ex:
            logging.error(f"ov_set_size: {ex}")

    def ov_track(self, mode):
        """Native drag / resize of the frameless overlay while the left button is held (page can't do it reliably)."""
        if not W.IS_WIN or getattr(self, "_ov_tracking", False):
            return
        h = W.find_window(OVERLAY_TITLE)
        rc = W.window_rect(h) if h else None
        if not rc:
            return
        self._ov_tracking = True
        logging.info(f"overlay: track {mode}")
        try:
            sx, sy = W.cursor_pos()
            x0, y0, w0, h0 = rc[0], rc[1], rc[2] - rc[0], rc[3] - rc[1]
            sc = W.dpi_scale(h)
            mw, mh = int(240 * sc), int(150 * sc)
            nw, nh = w0, h0
            while W.lbutton_down():
                cx, cy = W.cursor_pos()
                if mode == "resize":
                    nw, nh = max(mw, w0 + cx - sx), max(mh, h0 + cy - sy)
                    W.move_resize(h, x0, y0, nw, nh)
                else:
                    W.move_resize(h, x0 + cx - sx, y0 + cy - sy, w0, h0)
                time.sleep(0.012)
            if mode == "resize":
                self.e.ui_set(overlay_size=[int(nw / sc), int(nh / sc)])
            else:
                r2 = W.window_rect(h)
                if r2:
                    self.e.ui_set(overlay_pos=[r2[0], r2[1]])
        except Exception as ex:
            logging.error(f"ov_track: {ex}")
        finally:
            self._ov_tracking = False

    def ov_hit_loop(self):
        """Page-independent overlay move/resize: when the left button goes down on the overlay's header strip
        (move) or bottom-right corner (resize), track the cursor natively until release."""
        was_down = False
        logging.info("overlay: corner watcher running")
        while not self.stop.is_set():
            time.sleep(0.02 if self.ov_visible else 0.3)
            try:
                if not self.ov_visible or not W.IS_WIN:
                    was_down = False
                    continue
                down = W.lbutton_down()
                if down and not was_down and not getattr(self, "_ov_tracking", False):
                    h = W.find_window(OVERLAY_TITLE)
                    rc = W.window_rect(h) if h else None
                    if rc:
                        cx, cy = W.cursor_pos()
                        sc = W.dpi_scale(h)
                        if rc[0] <= cx <= rc[2] and rc[1] <= cy <= rc[3]:
                            lx, ly, rx, ry = cx - rc[0], cy - rc[1], rc[2] - cx, rc[3] - cy
                            if rx <= 26 * sc and ry <= 26 * sc:
                                t0 = time.time()
                                time.sleep(0.15)
                                if getattr(self, "_ov_js_t", 0) < t0 and W.lbutton_down():
                                    logging.info(f"overlay: corner press at {rx},{ry} -> native resize")
                                    self.ov_track("resize")
                was_down = W.lbutton_down()
            except Exception as ex:
                logging.error(f"ov_hit_loop: {ex}")
                time.sleep(0.5)

    def pet_loop(self):
        """Experimental desktop pet: a small transparent always-on-top window that walks along the bottom of the screen
        while NAB is not in front. Only covers its own footprint, so it cannot block clicks elsewhere."""
        import random
        PW, PH = 150, 210
        win, x, d, pause, until = None, 200.0, 1, 0, 0
        logging.info("pet: loop running")
        while not self.stop.is_set():
            time.sleep(0.05)
            try:
                want = W.IS_WIN and bool(self.e.ui_get("mascot_pet", False)) and bool(self.e.ui_get("mascot", True)) and not self.e.slow_pc() and self.e.authorized
                h = W.find_window(TITLE)
                if want and h:
                    want = (W.is_iconic(h) or W.foreground() != h) and not self.ov_visible
                if not want:
                    if win is not None:
                        try: win.hide()
                        except Exception: pass
                        win = "hidden" if win else None
                    time.sleep(0.4)
                    continue
                if win is None or win == "hidden":
                    if win is None:
                        import webview
                        try:
                            win = webview.create_window("NAB Pet", self.srv.url("pet"), width=PW, height=PH, frameless=True, on_top=True,
                                                        resizable=False, transparent=True, easy_drag=False)
                        except TypeError:
                            win = webview.create_window("NAB Pet", self.srv.url("pet"), width=PW, height=PH, frameless=True, on_top=True, resizable=False)
                        self._pet = win
                        time.sleep(2.0)
                        try: win.evaluate_js("window.petSkin&&petSkin(%r);window.petName&&petName(%r)" % (("blue" if str(self.e.ui_get("mascot_skin", "auto")) in ("auto", "") else str(self.e.ui_get("mascot_skin"))) if self.e.ui_get("mascot_who", "sajeeb") == "riko" else "sajeeb", str(self.e.ui_get("mascot_char", "")) or ("Riko" if self.e.ui_get("mascot_who", "sajeeb") == "riko" else "Sajeeb")))
                        except Exception: pass
                    else:
                        try: win.show()
                        except Exception: pass
                        win = self._pet
                hw = W.find_window("NAB Pet")
                if not hw:
                    continue
                l, t, r, b = W.work_area()
                now = time.time()
                if now >= until:
                    pause = random.random() < 0.45
                    until = now + (random.uniform(3, 8) if pause else random.uniform(4, 12))
                    if not pause and random.random() < 0.5:
                        d = -d
                    try: win.evaluate_js("petSet(%r,%s)" % ("sit" if pause else "walk", "true" if d > 0 else "false"))
                    except Exception: pass
                if not pause:
                    x += d * 2.0
                    if x < l:
                        x, d = l, 1
                    if x > r - PW:
                        x, d = r - PW, -1
                W.place_topmost(hw, int(x), int(b - PH))
            except Exception as ex:
                logging.error(f"pet_loop: {ex}")
                time.sleep(1.0)

    def restore_main(self):
        h = W.find_window(TITLE)
        if h:
            W.activate(h)
        elif self.main:
            self.main.restore()
        self.set_overlay(False)

    def _ov_create(self, hidden=False):
        import webview
        try:
            OV_W, OV_H = [int(x) for x in (self.e.ui_get("overlay_size") or [300, 440])]
        except Exception:
            OV_W, OV_H = 300, 440
        try:
            self.ov = webview.create_window(OVERLAY_TITLE, self.srv.url("overlay"), width=OV_W, height=OV_H, frameless=True,
                                            on_top=True, resizable=True, background_color="#0b0d12", easy_drag=True, hidden=hidden)
        except TypeError:   # very old pywebview without `hidden`
            self.ov = webview.create_window(OVERLAY_TITLE, self.srv.url("overlay"), width=OV_W, height=OV_H, frameless=True,
                                            on_top=True, resizable=True, background_color="#0b0d12", easy_drag=True)
        logging.info("overlay window created (hidden=%s)" % hidden)
        try:
            self.ov.events.closed += lambda: setattr(self, "ov", None) or setattr(self, "ov_visible", False)
        except Exception:
            pass
        return self.ov

    def _ov_place(self):
        """After the overlay window exists: topmost + tool window + remembered / bottom-right position."""
        for _ in range(25):
            h = W.find_window(OVERLAY_TITLE)
            if h:
                break
            time.sleep(0.2)
        else:
            return
        rc = W.window_rect(h) or (0, 0, 300, 440)
        w, hh = rc[2] - rc[0], rc[3] - rc[1]
        pos = self.e.ui_get("overlay_pos")
        sw, sh = W.screen_size()
        x, y = (pos if (pos and 0 <= pos[0] < sw - 40 and 0 <= pos[1] < sh - 40) else (sw - w - 24, sh - hh - 70))
        W.place_topmost(h, x, y)
        self._ov_alpha_applied = None
        self._ov_apply_alpha(h)

    def _ov_apply_alpha(self, h=None):
        try:
            pct = int(self.e.extra_settings.get("ov_opacity", 100) or 100)
            if pct != getattr(self, "_ov_alpha_applied", None):
                h = h or W.find_window(OVERLAY_TITLE)
                if h and W.set_alpha(h, pct):
                    self._ov_alpha_applied = pct
        except Exception as ex:
            logging.error(f"overlay alpha: {ex}")

    def snap_loop(self):
        """Overlay: apply opacity changes, and when you let go of the window near a screen edge
        pull it flush to that edge (like a docked panel)."""
        import ctypes
        last = None
        while not self.stop.is_set():
            time.sleep(0.35)
            try:
                if not self.ov_visible:
                    last = None
                    continue
                h = W.find_window(OVERLAY_TITLE)
                if not h:
                    continue
                self._ov_apply_alpha(h)
                if not self.e.extra_settings.get("ov_snap", True) or not W.IS_WIN:
                    continue
                if ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000:      # still dragging
                    last = None
                    continue
                rc = W.window_rect(h)
                if not rc or rc == last:
                    continue
                last = rc
                L, T, R, B = W.work_area()
                x, y, w, hh = rc[0], rc[1], rc[2] - rc[0], rc[3] - rc[1]
                nx, ny, SN = x, y, 28
                if abs(x - L) <= SN: nx = L
                elif abs(R - (x + w)) <= SN: nx = R - w
                if abs(y - T) <= SN: ny = T
                elif abs(B - (y + hh)) <= SN: ny = B - hh
                if (nx, ny) != (x, y):
                    W.place_topmost(h, nx, ny)
                    last = None
            except Exception:
                pass

    def set_overlay(self, show):
        """Show / hide the mini overlay. Hiding is a native Win32 call (instant, cannot fail or hang);
        pywebview is only used to create the window the first time."""
        with self._ov_lock:
            h = W.find_window(OVERLAY_TITLE) if W.IS_WIN else 0
            real = W.is_visible(h) if h else self.ov_visible
            if show == real and show == self.ov_visible:
                return
            try:
                if show:
                    logging.info("overlay: show")
                    if h and W.show_window(h, True):
                        pass
                    elif self.ov is None:
                        self._ov_create()
                    else:
                        try:
                            self.ov.show()
                        except Exception as e:
                            logging.error(f"overlay show failed, recreating: {e}")
                            self._ov_create()
                    self.ov_visible = True
                    threading.Thread(target=self._ov_place, daemon=True).start()
                else:
                    rc = W.window_rect(h) if h else None
                    if rc:
                        try:
                            self.e.ui_set(overlay_pos=[rc[0], rc[1]])
                        except Exception:
                            pass
                    self.ov_visible = False                     # state first, so no loop acts on a half-closed overlay
                    if not (h and W.show_window(h, False)):
                        threading.Thread(target=self._ov_hide_fallback, daemon=True).start()
            except Exception as e:
                logging.exception(f"overlay: {e}")

    def _ov_hide_fallback(self):
        try:
            self.ov.hide()
        except Exception:
            try:
                self.ov.destroy()
            except Exception:
                pass
            self.ov = None

    # ---- background helpers
    def minimize_watch(self):
        while not self.stop.is_set():
            time.sleep(0.4)
            try:
                if not self.e.ui_get("overlay_auto", True):
                    continue
                h = W.find_window(TITLE)
                if not h:
                    continue
                if W.is_iconic(h) and self.e.authorized:
                    self.set_overlay(True)
                elif self.ov_visible and not W.is_iconic(h) and W.is_visible(h):
                    self.set_overlay(False)
            except Exception:
                pass

    def hotkey_loop(self):
        spec = self.e.ui_get("switch_hotkey", "Ctrl+Alt+N")
        W.run_hotkey(spec, self.switch, self.stop)

    def switch(self):
        """Toggle: browser -> NAB, NAB -> the window we came from."""
        h = W.find_window(TITLE)
        if not h:
            return
        fg = W.foreground()
        if fg == h:
            prev = getattr(self.e, "_last_external_hwnd", None)
            if prev:
                W.activate(prev)
        else:
            W.activate(h)
            self.set_overlay(False)

    def start_background(self):
        threading.Thread(target=self.minimize_watch, daemon=True, name="NAB-MinWatch").start()
        threading.Thread(target=self.snap_loop, daemon=True, name="NAB-OvSnap").start()
        threading.Thread(target=self.ov_hit_loop, daemon=True, name="NAB-OvHit").start()
        if W.IS_WIN:
            threading.Thread(target=self.hotkey_loop, daemon=True, name="NAB-Hotkey").start()


SPLASH = """<!doctype html><html><head><meta charset="utf-8"><title>News Automation Pro</title><style>
html,body{margin:0;height:100%;background:#0b0d12;color:#c9cde4;font:14px 'Segoe UI',system-ui,sans-serif;overflow:hidden}
.top{height:54px;display:flex;align-items:center;gap:12px;padding:0 18px;border-bottom:1px solid #1f2336}
.dot{width:12px;height:12px;border-radius:50%;background:#6c6cf0}.b{font-weight:700;color:#f3f4fa}
.sk{background:linear-gradient(90deg,#161a29 0%,#222740 50%,#161a29 100%);background-size:200% 100%;animation:sh 1.3s linear infinite;border-radius:10px}
@keyframes sh{to{background-position:-200% 0}}
.wrap{display:flex;height:calc(100% - 55px)}.rail{width:70px;border-right:1px solid #1f2336;display:flex;flex-direction:column;align-items:center;gap:20px;padding-top:20px}
.rail .sk{width:36px;height:36px;border-radius:12px}.col{width:250px;border-right:1px solid #1f2336;padding:16px;display:flex;flex-direction:column;gap:12px}
.main{flex:1;padding:16px;display:flex;flex-direction:column;gap:14px}.side{width:280px;border-left:1px solid #1f2336;padding:16px;display:flex;flex-direction:column;gap:12px}
.msg{position:fixed;left:0;right:0;bottom:34px;text-align:center;color:#8f93ac}.msg b{color:#c9cde4;font-weight:600;background:#0b0d12;padding:6px 16px;border-radius:999px;border:1px solid #1f2336}
</style></head><body>
<div class="top"><span class="dot"></span><span class="b">NAB</span><div class="sk" style="width:150px;height:28px;border-radius:999px"></div><div class="sk" style="width:130px;height:28px;border-radius:999px"></div></div>
<div class="wrap"><div class="rail"><div class="sk"></div><div class="sk"></div><div class="sk"></div><div class="sk"></div><div class="sk"></div></div>
<div class="col"><div class="sk" style="height:90px"></div><div class="sk" style="height:22px;width:60%"></div><div class="sk" style="height:34px"></div><div class="sk" style="height:34px"></div><div class="sk" style="height:34px"></div><div class="sk" style="height:34px"></div></div>
<div class="main"><div class="sk" style="height:40px;width:55%"></div><div class="sk" style="flex:1"></div></div>
<div class="side"><div class="sk" style="height:120px"></div><div class="sk" style="height:170px"></div><div class="sk" style="height:100px"></div></div></div>
<div class="msg"><b id="m">Starting NAB…</b></div>
<script>var t0=Date.now();setInterval(function(){var s=Math.round((Date.now()-t0)/1000),m=document.getElementById('m');
m.textContent=s<8?'Starting NAB…':s<25?'Loading your settings and tools…':'Still loading… the first start after an update can take a little longer ('+s+' s)';},500);</script>
</body></html>"""


def _boot_engine(sh, ready):
    """Heavy part of the start-up (imports, engine, local server). Runs while the window already shows its skeleton."""
    t0 = time.time()
    try:
        engine, srv = build()
        sh.attach(engine, srv)
        logging.info("startup: engine + server ready in %.1fs" % (time.time() - t0))
        ready.set()
    except Exception as e:
        logging.exception(f"startup failed: {e}")
        sh.boot_error = str(e)
        ready.set()


def _early_ui(key, default):
    """Reads one per-PC UI setting before the engine exists (the window is created first, for a fast start)."""
    try:
        import json
        base = os.environ.get("NAB_DOC_DIR") or os.path.join(os.path.expanduser("~"), "Documents")
        with open(os.path.join(base, "nab_ui_state.json"), encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


def _intro_page():
    """The start-up page: the intro animation itself, so the window shows it from its very first frame. None = intro switched off."""
    try:
        if not _early_ui("intro", True):
            return None
        import nab_web
        with open(os.path.join(nab_web.ui_dir(), "intro.html"), encoding="utf-8") as f:
            html = f.read()
        import json as _j
        inject = ("<script>window.NAB_THEME=%s;window.NAB_SOUND=%s;window.NAB_HOLD=true;</script>"
                  % (_j.dumps(_early_ui("theme", "dark")), "true" if _early_ui("intro_sound", True) else "false"))
        return html.replace("</head>", inject + "</head>", 1)
    except Exception as e:
        logging.error(f"intro page: {e}")
        return None


def run_webview():
    import webview
    # let the start-up animation play its sound without a click first (WebView2 normally waits for a key press)
    flag = "--autoplay-policy=no-user-gesture-required"
    cur = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    if flag not in cur:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (cur + " " + flag).strip()
    sh = Shell()
    sh.boot_error = ""
    sw, sc = W.screen_size()
    w = min(1440, max(1000, int(sw * 0.92))) if W.IS_WIN else 1366
    h = min(900, max(620, int(sc * 0.9))) if W.IS_WIN else 820
    maxi = bool(_early_ui("start_full", True)) and W.IS_WIN     # normal maximised window, never borderless full screen
    intro_html = _intro_page()
    sh.main = webview.create_window(TITLE, html=intro_html or SPLASH, width=w, height=h, min_size=(900, 560), background_color="#0b0c13")
    try:   # the overlay is created up-front (hidden) with a blank page; it gets its real address once the server is up
        sh.ov = webview.create_window(OVERLAY_TITLE, html="<body style='background:#0b0d12'>", width=300, height=440, frameless=True,
                                      on_top=True, resizable=True, background_color="#0b0d12", easy_drag=True, hidden=True)
        try:
            sh.ov.events.closed += lambda: setattr(sh, "ov", None) or setattr(sh, "ov_visible", False)
        except Exception:
            pass
    except Exception as e:
        logging.error(f"overlay pre-create failed: {e}")
        sh.ov = None

    ready = threading.Event()
    last_close = [0.0]

    def closing():
        if sh.quitting:
            return True
        if not ready.is_set() or sh.e is None:             # still starting: just leave
            sh.quit()
            return True
        now = time.time()
        # page not connected (crashed/blank) or the user insists (second click within 6 s) → quit for real
        if not sh.e.hub._subs or now - last_close[0] < 6:
            sh.quit()
            return True
        last_close[0] = now
        sh.e.hub.emit("close_request")
        return False  # the page runs the upload-choice flow, then calls api('quit')
    sh.main.events.closing += closing

    def _signal_launcher():
        # tells NAB_Launcher.exe that the real window is up so it can close its splash
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.OpenEventW.restype = ctypes.c_void_p
            h = k.OpenEventW(0x0002, False, "Local\\NAB_Splash_Ready")
            if h:
                k.SetEvent(ctypes.c_void_p(h)); k.CloseHandle(ctypes.c_void_p(h))
        except Exception:
            pass
    def _on_shown():
        _signal_launcher()
        if maxi:
            try:
                sh.main.maximize()
            except Exception as e:
                logging.error(f"maximize: {e}")
        if intro_html:                                      # the launcher screen holds ~0.7 s, then fades: begin the animation right after
            def _go():
                for _ in range(40):
                    try:
                        sh.main.evaluate_js("window.NABSTART && window.NABSTART()")
                        break
                    except Exception:
                        time.sleep(.2)
            threading.Timer(1.0, _go).start()
        try:   # remember the real window handle (title-bar colour follows the theme; see nab_winutil.theme_titlebar)
            W.MAIN_HWND = int(sh.main.native.Handle.ToInt64())
            W.theme_titlebar(W.MAIN_HWND, "#0b0c13")
        except Exception as e:
            logging.error(f"main hwnd: {e}")
    try:
        sh.main.events.shown += _on_shown
    except Exception:
        pass

    def boot():
        try:
            import pyi_splash; pyi_splash.close()
        except Exception:
            pass
        _signal_launcher()
        threading.Thread(target=_boot_engine, args=(sh, ready), daemon=True, name="NAB-Boot").start()
        ready.wait()
        if not sh.boot_error:                         # tells the updater that the new version really started
            try:
                with open(os.path.join(os.path.dirname(sys.executable), "update_ok.flag"), "w") as _f:
                    _f.write(str(time.time()))
            except Exception:
                pass
        if sh.boot_error:
            try:
                sh.main.load_html("<body style='background:#0b0d12;color:#f87171;font:15px Segoe UI;padding:40px'><h2>NAB could not start</h2><pre>%s</pre>"
                                  "<p style='color:#8f93ac'>Details are in NAB's log file (Documents\\NAB or the app folder).</p>" % sh.boot_error.replace("<", "&lt;"))
            except Exception:
                pass
            return
        try:
            if intro_html:                                  # the intro page stays; the app loads beneath it in a frame (no blank gap, no restart)
                import json as _j
                u = _j.dumps(sh.srv.url(""))
                for _ in range(60):
                    try:
                        if sh.main.evaluate_js("window.NABGO && window.NABGO(%s)" % u):
                            break
                    except Exception:
                        pass
                    time.sleep(.25)
                else:
                    sh.main.load_url(sh.srv.url(""))
            else:
                sh.main.load_url(sh.srv.url(""))
        except Exception as e:
            logging.error(f"load main page: {e}")
        if sh.ov:
            try:
                sh.ov.load_url(sh.srv.url("overlay"))
            except Exception as e:
                logging.error(f"load overlay page: {e}")
        sh.start_background()

    webview.start(boot, gui="edgechromium" if W.IS_WIN else None, private_mode=False,
                  storage_path=os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NAB", "webview"))
    # window closed without the page's quit flow (should not happen) → exit cleanly
    sh.quit()


def _find_edge():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return None


def run_edge(engine, srv):
    edge = _find_edge()
    if not edge:
        raise RuntimeError("no Edge")
    sh = Shell(engine, srv)
    prof = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NAB", "edge")
    subprocess.Popen([edge, f"--app={srv.url('')}", f"--user-data-dir={prof}", "--window-size=1366,820",
                      "--no-first-run", "--disable-features=Translate"])
    sh.start_background()
    seen, gone = False, None
    while True:  # page closed (SSE gone for a while) → quit
        time.sleep(1.0)
        n = len(engine.hub._subs)
        if n:
            seen, gone = True, None
        elif seen:
            gone = gone or time.time()
            if time.time() - gone > 10:
                sh.quit()


def run_classic():
    import nab_classic
    nab_classic.run()


def run_tool(name):
    """Tk tools that still live in their own process: tracker / subscriptions / tracker-end."""
    import nab_ui_scale
    nab_ui_scale.enable_dpi_awareness()
    import customtkinter as ctk
    root = ctk.CTk()
    root.withdraw()
    code = 0
    if name == "tracker":
        import nab_tracker
        win = nab_tracker.NewspaperTracker(root)
        win.protocol("WM_DELETE_WINDOW", root.destroy)
        win.bind("<Destroy>", lambda e: root.after(50, root.destroy) if e.widget is win else None)
        root.mainloop()
    elif name == "subscriptions":
        import nab_subscriptions
        root.paper_list = _papers()
        nab_subscriptions.open_subscription_manager(root)
        for w in root.winfo_children():
            if w.winfo_class() == "Toplevel":
                w.bind("<Destroy>", lambda e, w=w: root.after(50, root.destroy) if e.widget is w else None)
        root.mainloop()
    elif name == "tracker-end":
        import nab_tracker
        win = nab_tracker.NewspaperTracker(root)
        win.withdraw()
        res = win.session_end_confirm(parent=root)
        code = 2 if res == "cancel" else 0
        try:
            root.destroy()
        except Exception:
            pass
    sys.exit(code)


def _papers():
    try:
        import json
        import nab_engine
        with open(os.path.join(nab_engine.DOC_DIR, "news_clipper_sources.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _setup_logging():
    try:
        import nab_engine_host
        from logging.handlers import RotatingFileHandler
        try:                                          # keep the previous run's log so a crash can still be read
            lf = nab_engine_host.LOG_FILE
            if os.path.isfile(lf) and os.path.getsize(lf) > 0:
                prev = lf.replace(".txt", ".prev.txt")
                try:
                    os.replace(lf, prev)
                except Exception:
                    pass
        except Exception:
            pass
        h = RotatingFileHandler(nab_engine_host.LOG_FILE, maxBytes=400_000, backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(h)
        logging.info("---- NAB start ----")
        sys.excepthook = lambda t, v, tb: logging.error("uncaught", exc_info=(t, v, tb))
        threading.excepthook = lambda a: logging.error("thread crash in %s" % (a.thread.name if a.thread else "?"), exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    except Exception:
        pass


def main():
    _setup_logging()
    _warm_imports()
    mode = os.environ.get("NAB_WINDOW", "")
    errs = []
    if mode != "edge":
        try:
            import webview  # noqa: F401
            return run_webview()
        except Exception as e:
            logging.error(f"pywebview failed: {e}")
            errs.append(e)
    try:
        engine, srv = build()
        return run_edge(engine, srv)
    except Exception as e:
        logging.error(f"edge mode failed: {e}")
        errs.append(e)
    raise RuntimeError("no web window available: " + "; ".join(map(str, errs)))
