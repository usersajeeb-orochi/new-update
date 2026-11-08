# nab_app.py — NewsClipper main application class
import os
import sys
import json
import time
import shutil
import logging
import subprocess
import re
import datetime
import concurrent.futures
import customtkinter as ctk
from tkinter import ttk, simpledialog, Menu, messagebox, Canvas, filedialog
from PIL import (Image, ImageDraw, ImageFont, ImageGrab, ImageTk, ImageChops,
                  ImageOps, ImageEnhance, ImageFilter)

from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})
from nab_telegram import *
import nab_telegram as _nab_telegram_mod
globals().update({k: v for k, v in vars(_nab_telegram_mod).items() if not k.startswith('__')})
from nab_update import *
import nab_update as _nab_update_mod
globals().update({k: v for k, v in vars(_nab_update_mod).items() if not k.startswith('__')})
from nab_access import *
import nab_access as _nab_access_mod
globals().update({k: v for k, v in vars(_nab_access_mod).items() if not k.startswith('__')})
from nab_auth import *
import nab_auth as _nab_auth_mod
globals().update({k: v for k, v in vars(_nab_auth_mod).items() if not k.startswith('__')})
from nab_dialogs import *
import nab_dialogs as _nab_dialogs_mod
globals().update({k: v for k, v in vars(_nab_dialogs_mod).items() if not k.startswith('__')})
from nab_server import *
import nab_server as _nab_server_mod
globals().update({k: v for k, v in vars(_nab_server_mod).items() if not k.startswith('__')})
from nab_bubble import *
import nab_bubble as _nab_bubble_mod
globals().update({k: v for k, v in vars(_nab_bubble_mod).items() if not k.startswith('__')})

# Imported explicitly (NOT via the star + globals().update pattern) so that
# removing an import from some other module can't silently break these.
import nab_ui_scale
import nab_clip_scan
import nab_connections
import nab_tabreader, nab_learn, nab_recent, nab_settings_sync, nab_sync_ui
import nab_batch
import nab_batch_ui
import nab_subscriptions

# ── Windows clipboard helper — handles DIB format from Snipping Tool ─────────
def _grab_clipboard_windows():
    """Grab image from Windows clipboard. Handles standard PNG/BMP, DIB
    (Device Independent Bitmap) format used by Snipping Tool & Print Screen,
    AND file-reference copies — some apps (e.g. Windows Photos' Copy button
    on a viewed file) put a file path on the clipboard instead of actual
    pixel data, the same as copying a file in Explorer. Falls back to a
    Windows DIB read if none of that works."""
    # Try PIL first — works for most cases
    try:
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            return img
        if isinstance(img, list):
            # File-reference copy (Photos app, Explorer, etc.) — open the
            # first path that's an actual image file on disk.
            for f in img:
                if os.path.isfile(f):
                    try:
                        return Image.open(f).convert("RGB")
                    except Exception:
                        continue
    except Exception:
        pass

    # Windows DIB fallback using ctypes
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes
        import struct

        CF_DIB  = 8
        CF_DIBV4 = 17
        GMEM_MOVEABLE = 0x0002

        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32

        if not u32.OpenClipboard(None):
            return None
        try:
            # Try CF_DIBV4 first, then CF_DIB
            h = u32.GetClipboardData(CF_DIBV4) or u32.GetClipboardData(CF_DIB)
            if not h:
                return None
            ptr  = k32.GlobalLock(h)
            size = k32.GlobalSize(h)
            if not ptr or not size:
                return None
            data = (ctypes.c_char * size).from_address(ptr)[:]
            k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()

        # Parse BITMAPINFOHEADER
        if len(data) < 40:
            return None
        # BITMAPINFOHEADER: biSize is unsigned, but biWidth AND biHeight are
        # both SIGNED. This used to read height as unsigned ('<IiI'), so a
        # top-down DIB (negative height — what several capture tools emit)
        # came through as ~4.29 billion, abs() did nothing, and PIL choked on
        # the resulting BMP.
        bih_size, width, height = struct.unpack_from('<Iii', data, 0)[:3]
        top_down = height < 0
        height = abs(height)

        # For a BI_BITFIELDS BITMAPINFOHEADER (bpp 16 or 32) three DWORD
        # colour masks sit between the header and the pixels. Skipping them
        # doesn't raise — it just shifts the image by 12 bytes, which is
        # worse, because the paste looks subtly corrupt instead of failing.
        extra = 0
        if bih_size == 40 and len(data) >= 40:
            bpp, compression = struct.unpack_from('<HI', data, 14)
            if compression == 3 and bpp in (16, 32):   # BI_BITFIELDS
                extra = 12
        # Write as BMP file in memory
        import io as _io
        bmp_buf = _io.BytesIO()
        # BMP file header (14 bytes) + DIB data
        pixel_offset = 14 + bih_size + extra
        file_size    = 14 + len(data)
        bmp_buf.write(b'BM')
        bmp_buf.write(struct.pack('<I', file_size))
        bmp_buf.write(bytes(4))
        bmp_buf.write(struct.pack('<I', pixel_offset))
        bmp_buf.write(data)
        bmp_buf.seek(0)
        return Image.open(bmp_buf).convert("RGB")
    except Exception as e:
        logging.error(f"_grab_clipboard_windows DIB: {e}")
        return None
# ── End clipboard helper ──────────────────────────────────────────────────────

class NewsClipper(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("Dark")
        # Shrink every CustomTkinter widget to suit this machine's screen
        # BEFORE building the UI — after setup_ui() the widgets already
        # exist at the old size. On a 1920x1080 PC this is a no-op (1.0).
        self._ui_scale = nab_ui_scale.apply_ctk_scaling(ctk, self)
        self.title("News Automation Pro v2.0 — made by Sajeeb")
        # Was a flat 1400x950, which is taller than the usable area of a
        # 1366x768 screen — the bottom toolbar (Paste/Trim/Surgical) and the
        # GENERATE button ended up under the taskbar with no way to reach
        # them. fit() clamps to the real work area and maximises when the
        # requested size doesn't fit.
        nab_ui_scale.fit(self, 1400, 950, min_w=900, min_h=560,
                         maximize_if_tight=True)
        self.configure(fg_color=C_BG)
        try: self.iconbitmap(resource_path("app_icon.ico"))
        except: pass

        # When running as a PyInstaller EXE, os.getcwd() points to wherever
        # the user launched the EXE from — not where the bundled Logos are.
        # resource_path() resolves to sys._MEIPASS (bundled) or "." (script).
        # We use TWO logo dirs:
        #   self.logo_dir       — writable folder next to the EXE/script
        #                         (user can add logos here, persists across updates)
        #   self.logo_dir_bundled — read-only bundled logos inside the EXE
        #                           (fallback when logo not found in writable dir)
        if getattr(sys, 'frozen', False):
            # Running as EXE — writable dir is next to the EXE
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.abspath(".")
        self.logo_dir = os.path.join(exe_dir, LOGO_FOLDER_NAME)
        if not os.path.exists(self.logo_dir):
            os.makedirs(self.logo_dir, exist_ok=True)
        self.logo_dir_bundled = resource_path(LOGO_FOLDER_NAME)
        self.bg_file = os.path.join(exe_dir, BG_FILE_NAME)
        self.raw_bg_image = None

        global DOC_DIR
        DOC_DIR = os.path.join(os.path.expanduser("~"), "Documents")
        self.base_root = os.path.join(DOC_DIR, "Monitoring")
        self.config_file = os.path.join(DOC_DIR, "news_clipper_cats.json")
        self.settings_file = os.path.join(DOC_DIR, "news_clipper_settings.json")
        self.sources_file = os.path.join(DOC_DIR, "news_clipper_sources.json")
        self.mappings_file = os.path.join(DOC_DIR, "news_clipper_mappings.json")

        self.orig_images = []
        self.proxy_images = []
        self.session_history = []
        self.undo_stack = []
        self.redo_stack = []

        self.quick_saves = {}
        self.url_mappings = {}
        # (hwnd, tab-title key) -> paper. Explicit 📍 locks only; session-
        # only (window handles aren't valid across launches).
        self._tab_locks = {}
        self._tab_url = (None, "")
        self._learn = nab_learn.LearnTracker()
        self._learn_declined = set()
        self._last_external_hwnd = None
        self._last_external_title = ""
        self._detect_dirty = False
        self.workspace_instance = None
        self._current_binds = []

        # Feature settings
        self.extra_settings = {
            "min_file_size_kb": 20,
            "max_file_size_kb": 5000,
            "batch_save_enabled": False,
            "autosave_enabled": False,
            "autosave_interval": 300,
            "daily_report_enabled": False,
            "daily_report_hour": 18,
        }

        # Feature 35: Daily goal
        self.daily_goal = 0
        self.daily_goal_notified = False

        # Feature 36: Pending note from Telegram

        # Group mode: set this to your Telegram group chat ID to allow limited commands from group
        self.group_chat_id = ""  # e.g. "-100123456789" — set via /setgroup command or edit here

        # Feature 38: Streak tracking
        self.last_active_date = ""

        # Autosave timer
        self._autosave_job = None
        self._daily_report_sent_hour = -1

        self.action_map = {
            "paste": lambda e=None: self.paste_image(),
            "undo": self.undo,
            "redo": self.redo,
            "delete": lambda e=None: self.smart_delete(),
            "generate": lambda e=None: self.process_final(),
            "trim": lambda e=None: self.auto_trim(),
            "clean": lambda e=None: self.remove_straight_lines(),
            "pad": lambda e=None: self.add_whitespace(),
            "open": lambda e=None: self.open_last_folder(),
            "move_up": lambda e=None: self.move_clip_up(),
            "move_down": lambda e=None: self.move_clip_down(),
            "swap": lambda e=None: self.swap_last_two(),
            "tool_crop": lambda e=None: self.handle_tool_key("crop"),
            "tool_erase": lambda e=None: self.handle_tool_key("erase"),
            "tool_highlight": lambda e=None: self.handle_tool_key("highlight"),
            "tool_redact": lambda e=None: self.handle_tool_key("redact")
        }

        self.PROXY_HEIGHT = 1440
        self.paper_list = []
        self.last_page = "1"
        self.last_pos = ""
        self.last_size = "1x1"
        self.last_saved_path = ""
        self.current_date = datetime.datetime.now()
        self.last_canvas_size = (0, 0)
        self.bg_image_ref = None
        self.cached_full_img = None

        self._preview_job = None
        self._bg_job = None
        self.last_clipboard_hash = None
        self.last_context = ""

        self.user_zoom = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.rect_start = None
        self.rect_id = None
        self.display_image = None
        self.fit_scale = 1.0
        self.header_offset = 0
        self.img_draw_x = 0
        self.img_draw_y = 0
        self.current_render_scale = 1.0

        self.space_pressed = False
        self.ctrl_pressed = False
        self.is_scrubby_zooming = False
        self.is_panning = False
        self.is_selecting = False

        # ── Move tool ──────────────────────────────────────────────────────────
        # clip_offsets[i] = [dx, dy] nudge in image-space pixels per clip.
        # Default [0,0] = centred vertical stack (unchanged from original).
        self.clip_rects         = []    # populated by _rebuild_default_offsets
        self.moving_clip_idx   = None
        self.move_drag_start   = None
        self.move_drag_orig    = None

        if os.path.exists(self.bg_file):
            try: self.raw_bg_image = Image.open(self.bg_file).convert("RGBA")
            except: pass

        self.setup_ui()
        self.setup_login_overlay()
        self.load_settings()
        self.setup_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

        global _nab_app_ref
        _nab_app_ref = self
        # Clean up leftover .old file from previous update
        if _is_frozen():
            _old = _current_exe() + ".old"
            if os.path.exists(_old):
                try: os.remove(_old)
                except Exception: pass
        # Start GitHub version check loop (runs every 5 min in background)
        self.after(3000, self._github_version_check_loop)
        threading.Thread(target=self.background_monitor, daemon=True).start()
        self.after(500, lambda: self.focus_force())
        self.after(10000, self._background_ticker)
        # Connections (Drive folder, Cloud URL, Sheet, Google key, Telegram) are
        # built in — see nab_connections.py. Overrides: Settings → Advanced.

        # ── WebSocket preview server ───────────────────────────────────────
        self.preview_server = _preview_server
        self.preview_server.start()

        # ── Settings sync (no-op until this PC is connected to the server) ──
        self._sync = nab_settings_sync.SyncManager(self, self._on_synced)
        self._sync.start()

        # Start local REST API server
        if HAS_API:
            try:
                _start_api_server()
            except Exception as e:
                logging.error(f"NAB API start: {e}")

        # ── Mini overlay — shown on minimize, hidden on restore/Alt+Tab ──────
        self._mini_overlay  = None
        self._was_iconic    = False
        # Poll window state every 300ms — more reliable than <Unmap>/<Map>
        # on Windows where those events fire for child widgets too.
        self.after(500, self._poll_window_state)

    # ── PAUSE / RESUME (Feature 23) ──
    def _on_pause(self):
        self.status_label.configure(text="⏸ PAUSED BY ADMIN", text_color="#888")
        self._pause_overlay = ctk.CTkFrame(self, fg_color="#000000CC")
        self._pause_overlay.place(relwidth=1, relheight=1)
        ctk.CTkLabel(self._pause_overlay, text="⏸  APP PAUSED\nSend /resume to continue",
                     font=("Consolas", 20, "bold"), text_color="#888").place(relx=0.5, rely=0.5, anchor="center")

    def _on_resume(self):
        if hasattr(self, '_pause_overlay'):
            self._pause_overlay.destroy()
        self.status_label.configure(text="READY", text_color=C_TEXT_DIM)

    # ── SESSION EXPIRY WARNING (Feature 31) ──
    def _show_expiry_warning(self, exp_str):
        self.status_label.configure(
            text=f"⚠️ Session expires at {exp_str} — 15 min left!",
            text_color="#FF9500"
        )
        messagebox.showwarning("Session Expiring",
                               f"Your timed session expires at {exp_str}\n(15 minutes remaining)")

    # ── BACKGROUND TICKER (daily report, autosave, streak, goal) ──
    def _background_ticker(self):
        now = datetime.datetime.now()

        # Feature 26: Daily report
        if (self.extra_settings.get("daily_report_enabled") and
                now.hour == self.extra_settings.get("daily_report_hour", 18) and
                self._daily_report_sent_hour != now.hour):
            self._daily_report_sent_hour = now.hour
            threading.Thread(target=self._send_tg_report, daemon=True).start()

        # Feature 15: Autosave
        if self.extra_settings.get("autosave_enabled"):
            interval = self.extra_settings.get("autosave_interval", 300)
            if not hasattr(self, '_last_autosave'):
                self._last_autosave = time.time()
            if time.time() - self._last_autosave >= interval:
                self._last_autosave = time.time()
                if self.orig_images:
                    selections = self.cat_tree.selection()
                    if selections:
                        self.status_label.configure(text="AUTO-SAVING...", text_color="#888")
                        # BUG FIX: build save_ctx here (main thread) — see process_final
                        # for why this can no longer be read inside the worker thread.
                        # strip_emoji_prefix (nab_constants.py) removes the
                        # display emoji ("📰 New Age" -> "New Age") without
                        # touching a name that never had one. See its docstring
                        # for why the old .split(" ", 1)[-1] broke "New Age".
                        save_ctx = {
                            "paper": strip_emoji_prefix(self.paper_combo.get()),
                            "save_q": 95 if self.hd_mode_var.get() else int(self.quality_slider.get()),
                            "logo_scale": self.logo_slider.get(),
                            "text_scale": self.text_slider.get(),
                            "show_header": self.show_text_var.get(),
                        }
                        threading.Thread(target=self.save_in_background, args=(selections, save_ctx), daemon=True).start()

        # Feature 38: Streak tracker
        today_str = now.strftime("%Y-%m-%d")
        if self.last_active_date and self.last_active_date != today_str and getattr(self, "_streak_day", "") != today_str:
            self._streak_day = today_str                      # once per day (it used to repeat every minute)
            yesterday = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            if self.last_active_date == yesterday:
                streak = getattr(self, 'current_streak', 0) + 1
                self.current_streak = streak
                if streak > 1:
                    threading.Thread(target=lambda s=streak: _tg_send(
                        f"🔥 <b>Streak: {s} days in a row!</b>\n💻 {PC_NAME}"
                    ), daemon=True).start()
            else:
                days_missed = (datetime.datetime.strptime(today_str, "%Y-%m-%d") -
                               datetime.datetime.strptime(self.last_active_date, "%Y-%m-%d")).days
                if days_missed > 1:
                    threading.Thread(target=lambda d=days_missed: _tg_send(
                        f"😴 <b>Streak broken!</b> {d} days with no clips on <b>{PC_NAME}</b>."
                    ), daemon=True).start()
                self.current_streak = 0

        self.after(60000, self._background_ticker)  # check every minute

    # ── REMOTE CONTROLS from Telegram ──
    def _remote_set_date(self, date_str):
        try:
            new_date = datetime.datetime.strptime(date_str, "%d-%m-%Y")
            self.current_date = new_date
            self.date_btn.configure(text=f"📅 {self.current_date.strftime('%Y-%m-%d')}")
            self.force_update_preview()
            _tg_send(f"📅 Date set to <b>{date_str}</b> on {PC_NAME}.")
        except ValueError:
            _tg_send("❌ Invalid date format. Use DD-MM-YYYY.")

    def _remote_set_paper(self, paper_name):
        matches = [p for p in self.paper_list if paper_name.lower() in p.lower()]
        if matches:
            self.paper_combo.set(matches[0])
            self.force_update_preview()
            _tg_send(f"📰 Paper set to <b>{matches[0]}</b> on {PC_NAME}.")
        else:
            _tg_send(f"❌ No newspaper matching '{paper_name}' found on {PC_NAME}.")

    def _set_daily_goal(self, goal):
        self.daily_goal = goal
        self.daily_goal_notified = False
        today_count = sum(1 for h in self.session_history
                          if h.get("time", "").split(":")[0].isdigit())
        _tg_send(f"🎯 Daily goal set to <b>{goal} clips</b> on {PC_NAME}.\nCurrent count: {today_count}.")

    def _skip_auto_snatch(self):
        if hasattr(self, 'auto_snatch_var'):
            old = self.auto_snatch_var.get()
            if old:
                self.auto_snatch_var.set(False)
                self.status_label.configure(text="Auto-snatch paused 60s", text_color="#888")
                _tg_send(f"⏸ Auto-snatch paused 60s on {PC_NAME}.")
                self.after(60000, lambda: [self.auto_snatch_var.set(True),
                                           self.status_label.configure(text="READY", text_color=C_TEXT_DIM)])
            else:
                _tg_send(f"ℹ️ Auto-snatch is already off on {PC_NAME}.")
        else:
            _tg_send(f"ℹ️ Auto-snatch not available on {PC_NAME}.")

    # Feature 45: Broadcast handler
    def _handle_broadcast(self, rest):
        parts = rest.split(maxsplit=1)
        if not parts:
            return
        if parts[0].lower() == "all" and len(parts) >= 2:
            msg = parts[1]
            self._show_broadcast_popup(msg)
            _tg_send(f"📣 Broadcast sent to all PCs: <i>{msg}</i>")
        elif parts[0].startswith("@") and len(parts) >= 2:
            username = parts[0]
            msg = parts[1]
            # Send to specific user via Telegram (just notifies back)
            _tg_send(f"📣 Broadcast to {username}: <i>{msg}</i>\n(Note: Direct user messaging requires user chat_id setup)")
        else:
            # Show popup on this PC only
            msg = rest
            self._show_broadcast_popup(msg)

    def _show_broadcast_popup(self, msg):
        top = ctk.CTkToplevel(self)
        top.title("📣 Admin Message")
        nab_ui_scale.fit(top, 400, 180, parent=self)
        top.configure(fg_color=C_SURFACE)
        top.attributes('-topmost', True)
        ctk.CTkLabel(top, text="📣 ADMIN BROADCAST", font=("Impact", 18), text_color=C_ACCENT).pack(pady=15)
        ctk.CTkLabel(top, text=msg, font=("Segoe UI", 13), text_color="white", wraplength=360).pack(padx=20)
        ctk.CTkButton(top, text="OK", fg_color=C_ACCENT, command=top.destroy,
                      height=40, width=100).pack(pady=15)
        top.after(30000, lambda: top.destroy() if top.winfo_exists() else None)

    def _send_pcs_info(self):
        elapsed = int(time.time() - TelegramAuth._session_start) if TelegramAuth._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        saves = len(self.session_history)
        _tg_send(
            f"🖥 <b>Active PC Info</b>\n\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"💾 Saves: {saves}\n"
            f"📰 Current paper: {self.paper_combo.get()}"
        )

    def _tg_send_preview(self):
        if not self.orig_images:
            _tg_send(f"📭 Canvas is empty on {PC_NAME}.")
            return
        try:
            import io
            canvas, _ = self.create_full_page(use_proxy=True, force_header_state=self.show_text_var.get())
            thumb = canvas.copy()
            thumb.thumbnail((800, 1200))
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=70)
            _tg_send_photo(buf.getvalue(), f"Canvas preview — {PC_NAME}")
        except Exception as e:
            _tg_send(f"❌ Preview failed: {e}")

    def _send_tg_report(self):
        from collections import Counter
        saves = len(self.session_history)
        cats = Counter(h.get("category", "?") for h in self.session_history)
        papers = Counter(
            os.path.basename(h.get("path", "")).split(",")[0]
            for h in self.session_history
        )
        elapsed = int(time.time() - TelegramAuth._session_start) if TelegramAuth._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        deadline_str = (
            datetime.datetime.fromtimestamp(TelegramAuth._access_deadline).strftime("%H:%M:%S")
            if TelegramAuth._access_deadline else "Unlimited"
        )
        cat_lines = "\n".join(f"  • {c}: {n}" for c, n in cats.most_common(5)) or "  None"
        paper_lines = "\n".join(f"  • {p}: {n}" for p, n in papers.most_common(5)) or "  None"
        goal_line = ""
        if self.daily_goal > 0:
            pct = min(100, int(saves / self.daily_goal * 100))
            goal_line = f"\n🎯 Goal: {saves}/{self.daily_goal} ({pct}%)"
        _tg_send(
            f"📊 <b>NAB Activity Report</b>\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"⏱ Expires: {deadline_str}\n"
            f"💾 Total saves: <b>{saves}</b>{goal_line}\n\n"
            f"📁 By category:\n{cat_lines}\n\n"
            f"📰 By newspaper:\n{paper_lines}"
        )

    def _send_tg_status(self):
        elapsed = int(time.time() - TelegramAuth._session_start) if TelegramAuth._session_start else 0
        hrs, rem = divmod(elapsed, 3600)
        mins = rem // 60
        deadline_str = (
            datetime.datetime.fromtimestamp(TelegramAuth._access_deadline).strftime("%H:%M:%S")
            if TelegramAuth._access_deadline else "Unlimited"
        )
        _tg_send(
            f"🟢 NAB running on <b>{PC_NAME}</b>\n"
            f"🕐 Session: {hrs}h {mins}m\n"
            f"⏱ Access expires: {deadline_str}\n"
            f"📰 Paper: {self.paper_combo.get()}\n"
            f"📅 Date: {self.current_date.strftime('%d-%m-%Y')}"
        )

    def _send_last_file(self):
        if not self.session_history:
            _tg_send(f"📭 No files saved this session on {PC_NAME}.")
            return
        last = self.session_history[-1]
        path = last.get("path", "")
        if os.path.exists(path):
            try:
                import io
                img = Image.open(path)
                img.thumbnail((800, 1200))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                _tg_send_photo(buf.getvalue(), f"Last file — {os.path.basename(path)}\n{last.get('category','?')} — {last.get('time','?')}")
            except Exception as e:
                _tg_send(f"❌ Could not send file: {e}")
        else:
            _tg_send(f"❌ File not found: {path}")

    def _send_files_today(self):
        today = self.current_date.strftime("%Y-%m-%d")
        today_files = [h for h in self.session_history if today in h.get("path", "") or today in h.get("time", "")]
        if not today_files:
            _tg_send(f"📭 No files saved today on {PC_NAME}.")
            return
        lines = [f"• [{h['time']}] {h['category']} → {os.path.basename(h['path'])}" for h in today_files[-20:]]
        _tg_send(f"📁 <b>Today's saves on {PC_NAME} ({len(today_files)} total):</b>\n\n" + "\n".join(lines))

    def _delete_last_file(self):
        if not self.session_history:
            _tg_send(f"📭 No files to delete on {PC_NAME}.")
            return
        last = self.session_history[-1]
        path = last.get("path", "")
        try:
            if os.path.exists(path):
                os.remove(path)
                self.session_history.pop()
                _tg_send(f"🗑️ Deleted: <code>{os.path.basename(path)}</code> on {PC_NAME}.")
            else:
                _tg_send(f"❌ File not found on {PC_NAME}.")
        except Exception as e:
            _tg_send(f"❌ Delete failed: {e}")

    def _send_last_n_files(self, n):
        recent = self.session_history[-n:]
        if not recent:
            _tg_send(f"📭 No files available on {PC_NAME}.")
            return
        sent = 0
        for h in recent:
            path = h.get("path", "")
            if os.path.exists(path):
                try:
                    import io
                    img = Image.open(path)
                    img.thumbnail((800, 1200))
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    _tg_send_document(buf.getvalue(), os.path.basename(path),
                                      f"{h.get('category','?')} — {h.get('time','?')}")
                    sent += 1
                    time.sleep(0.5)
                except Exception:
                    pass
        _tg_send(f"✅ Sent {sent}/{len(recent)} files from {PC_NAME}.")

    def _scan_category_files_on_disk(self, cat_query, date_filter=None):
        """
        Scan base_root on disk for files matching a category name and optional date.
        Folder structure: base_root/YYYY/Month/DD-MM-YYYY/Category[/SubCategory]/files
        date_filter: string like '02-02-2023' (DD-MM-YYYY) or None for all dates.
        Returns list of (full_path, category_path, date_str).
        """
        results = []
        if not os.path.exists(self.base_root):
            return results
        try:
            for year_d in os.scandir(self.base_root):
                if not year_d.is_dir(): continue
                for month_d in os.scandir(year_d.path):
                    if not month_d.is_dir(): continue
                    for date_d in os.scandir(month_d.path):
                        if not date_d.is_dir(): continue
                        date_str = date_d.name  # e.g. "02-02-2023"
                        # If date filter provided, skip non-matching dates
                        if date_filter and date_filter != date_str:
                            continue
                        # Walk all subdirs under this date folder
                        for root, dirs, files in os.walk(date_d.path):
                            rel = os.path.relpath(root, date_d.path)
                            # rel is like "Category" or "Category/SubCategory" or "."
                            cat_path = rel if rel != "." else ""
                            if cat_query.lower() in cat_path.lower() or cat_query.lower() in root.lower():
                                for f in files:
                                    if f.lower().endswith((".jpg", ".jpeg", ".png")):
                                        results.append((os.path.join(root, f), cat_path or date_str, date_str))
        except Exception as e:
            logging.error(f"_scan_category_files_on_disk: {e}")
        results.sort(key=lambda x: x[2])
        return results

    def _list_all_categories_on_disk(self):
        """Return a set of all category paths found on disk."""
        cats = set()
        if not os.path.exists(self.base_root):
            return cats
        try:
            for year_d in os.scandir(self.base_root):
                if not year_d.is_dir(): continue
                for month_d in os.scandir(year_d.path):
                    if not month_d.is_dir(): continue
                    for date_d in os.scandir(month_d.path):
                        if not date_d.is_dir(): continue
                        for root, dirs, files in os.walk(date_d.path):
                            has_imgs = any(f.lower().endswith((".jpg",".jpeg",".png")) for f in files)
                            if has_imgs:
                                rel = os.path.relpath(root, date_d.path)
                                cats.add(rel if rel != "." else "(root)")
        except Exception as e:
            logging.error(f"_list_all_categories_on_disk: {e}")
        return cats

    def _send_category_files(self, raw_arg):
        """
        Handles: /send CategoryName [DD-MM-YYYY]
        Scans disk so it works across sessions and after restarts.
        """
        import io as _io

        # Parse optional date at end: /send Economy 02-02-2023
        date_filter = None
        cat = raw_arg.strip()
        parts = cat.rsplit(" ", 1)
        if len(parts) == 2:
            maybe_date = parts[1].strip()
            import re as _re
            if _re.match(r"^\d{2}-\d{2}-\d{4}$", maybe_date):
                date_filter = maybe_date
                cat = parts[0].strip()

        _tg_send(
            f"🔍 Searching for <b>{cat}</b>"
            + (f" on <b>{date_filter}</b>" if date_filter else " (all dates)")
            + f" on <b>{PC_NAME}</b>..."
        )

        # First try disk scan
        found = self._scan_category_files_on_disk(cat, date_filter)

        # Also merge any in-memory session history matches (current session)
        session_paths = set(h.get("path", "") for h in self.session_history
                            if cat.lower() in h.get("category", "").lower())
        if date_filter:
            session_paths = {p for p in session_paths if date_filter in p}
        # Add session files not already in disk results
        disk_paths = {r[0] for r in found}
        for sp in sorted(session_paths):
            if sp not in disk_paths and os.path.exists(sp):
                rel = os.path.relpath(os.path.dirname(sp), self.base_root)
                found.append((sp, rel, date_filter or "session"))

        if not found:
            # Suggest similar categories
            all_cats = self._list_all_categories_on_disk()
            similar = [c for c in all_cats if any(w in c.lower() for w in cat.lower().split())]
            tip = ""
            if similar:
                tip = "\n\n💡 Similar categories found:\n" + "\n".join(f"  • {c}" for c in sorted(similar)[:8])
            _tg_send(
                f"📭 No files found for category <b>'{cat}'</b>"
                + (f" on date <b>{date_filter}</b>" if date_filter else "")
                + f" on <b>{PC_NAME}</b>.{tip}"
                + "\n\nSend /categories to see all available categories."
            )
            return

        # Group by date for summary
        by_date = {}
        for path, cat_path, date_str in found:
            by_date.setdefault(date_str, []).append((path, cat_path))

        summary_lines = []
        total = len(found)
        for ds, files in sorted(by_date.items()):
            summary_lines.append(f"📅 <b>{ds}</b>: {len(files)} file(s)")

        _tg_send(
            f"📁 <b>Found {total} file(s) for '{cat}' on {PC_NAME}</b>\n\n"
            + "\n".join(summary_lines)
            + "\n\nSending now..."
        )

        sent = 0
        limit = 20  # max files to send in one command
        for path, cat_path, date_str in found[:limit]:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((900, 1400))
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    caption = f"📂 {cat_path}\n📅 {date_str}\n📄 {os.path.basename(path)}"
                    _tg_send_document(buf.getvalue(), os.path.basename(path), caption)
                    sent += 1
                    time.sleep(0.4)
                except Exception as ex:
                    logging.error(f"_send_category_files send: {ex}")

        if total > limit:
            _tg_send(
                f"✅ Sent {sent}/{total} files from <b>'{cat}'</b> on {PC_NAME}.\n"
                f"⚠️ Only first {limit} shown. Use a date filter to narrow down:\n"
                f"<code>/send {cat} DD-MM-YYYY</code>"
            )
        else:
            _tg_send(f"✅ Sent {sent}/{total} files from <b>'{cat}'</b> on {PC_NAME}.")

    def _send_categories_list(self, chat_id=None):
        """Send a list of all categories found on disk."""
        cats = self._list_all_categories_on_disk()
        if not cats:
            _tg_send(f"📭 No categories found on disk for <b>{PC_NAME}</b>.\nBase folder: <code>{self.base_root}</code>", chat_id=chat_id)
            return
        sorted_cats = sorted(cats)
        lines = [f"  • {c}" for c in sorted_cats[:50]]
        suffix = f"\n...and {len(sorted_cats)-50} more." if len(sorted_cats) > 50 else ""
        _tg_send(
            f"📂 <b>Categories on {PC_NAME}</b> ({len(sorted_cats)} total):\n\n"
            + "\n".join(lines) + suffix
            + "\n\n<i>Use: /send CategoryName [DD-MM-YYYY]</i>",
            chat_id=chat_id
        )

    def _send_category_files_to(self, raw_arg, chat_id):
        """Like _send_category_files but sends to a specific chat_id (for group support)."""
        import io as _io
        import re as _re

        date_filter = None
        cat = raw_arg.strip()
        parts = cat.rsplit(" ", 1)
        if len(parts) == 2:
            maybe_date = parts[1].strip()
            if _re.match(r"^\d{2}-\d{2}-\d{4}$", maybe_date):
                date_filter = maybe_date
                cat = parts[0].strip()

        found = self._scan_category_files_on_disk(cat, date_filter)
        # Also add session files
        for h in self.session_history:
            if cat.lower() in h.get("category", "").lower():
                sp = h.get("path", "")
                if date_filter and date_filter not in sp:
                    continue
                if sp not in {r[0] for r in found} and os.path.exists(sp):
                    found.append((sp, h.get("category", ""), date_filter or "session"))

        if not found:
            all_cats = self._list_all_categories_on_disk()
            similar = [c for c in all_cats if any(w in c.lower() for w in cat.lower().split())]
            tip = ("\n💡 Similar: " + ", ".join(sorted(similar)[:5])) if similar else ""
            _tg_send(f"📭 No files found for <b>'{cat}'</b>" + (f" on {date_filter}" if date_filter else "") + f".{tip}", chat_id=chat_id)
            return

        by_date = {}
        for path, cat_path, date_str in found:
            by_date.setdefault(date_str, []).append((path, cat_path))
        summary = "\n".join(f"📅 <b>{ds}</b>: {len(fs)} file(s)" for ds, fs in sorted(by_date.items()))
        _tg_send(f"📁 <b>{len(found)} file(s) for '{cat}'</b>\n{summary}\nSending...", chat_id=chat_id)

        sent = 0
        for path, cat_path, date_str in found[:20]:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((900, 1400))
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    caption = f"📂 {cat_path}\n📅 {date_str}\n📄 {os.path.basename(path)}"
                    _tg_send_document(buf.getvalue(), os.path.basename(path), caption, chat_id=chat_id)
                    sent += 1
                    time.sleep(0.4)
                except Exception as ex:
                    logging.error(f"_send_category_files_to: {ex}")
        _tg_send(f"✅ Sent {sent}/{len(found)} files.", chat_id=chat_id)

    def _send_stats(self):
        from collections import Counter
        if not self.session_history:
            _tg_send(f"📊 No stats yet on {PC_NAME}.")
            return
        papers = Counter(os.path.basename(h.get("path", "")).split(",")[0] for h in self.session_history)
        cats = Counter(h.get("category", "?") for h in self.session_history)
        paper_lines = "\n".join(f"  {i+1}. {p}: {n}" for i, (p, n) in enumerate(papers.most_common(8)))
        cat_lines = "\n".join(f"  {i+1}. {c}: {n}" for i, (c, n) in enumerate(cats.most_common(8)))
        _tg_send(
            f"📈 <b>NAB Stats — {PC_NAME}</b>\n\n"
            f"<b>Top Newspapers:</b>\n{paper_lines}\n\n"
            f"<b>Top Categories:</b>\n{cat_lines}\n\n"
            f"Total clips this session: <b>{len(self.session_history)}</b>"
        )

    # ── CLOUD UPLOAD METHODS ──────────────────────────────────────────────────

    # ── UNIVERSAL FILE SCANNER ────────────────────────────────────────────
    # Finds all files under base_root regardless of folder structure.
    # Works with any nesting: YYYY/MM/DD, YYYY/MonthName/DD, YYYY/DD, etc.
    # Also handles any drive letter (C, D, E, F...) since base_root is stored
    # in settings and can point anywhere.

    _DATE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")  # DD-MM-YYYY

    def _scan_all_files(self, date_filter=None):
        """
        Recursively scan base_root for all saved files.
        Returns list of (date_str, category, file_path, file_name)

        date_filter: None = all, or a set of 'DD-MM-YYYY' strings
        Uses a recursive walk — works with ANY folder structure depth.
        """
        results = []
        base    = self.base_root
        if not base or not os.path.exists(base):
            return results

        def _walk(path, found_date=None, found_cat=None):
            try:
                entries = list(os.scandir(path))
            except PermissionError:
                return

            for entry in entries:
                if entry.name.startswith(".") or entry.name.startswith("__"):
                    continue

                if entry.is_file():
                    # Only collect if we have both date and category context
                    if found_date and found_cat:
                        if date_filter is None or found_date in date_filter:
                            results.append((found_date, found_cat, entry.path, entry.name))
                    continue

                if not entry.is_dir():
                    continue

                name = entry.name

                # Is this a date folder? DD-MM-YYYY
                if self._DATE_PATTERN.match(name):
                    _walk(entry.path, found_date=name, found_cat=None)

                # Already have a date — this must be a category folder
                elif found_date and not found_cat:
                    _walk(entry.path, found_date=found_date, found_cat=name)

                # Already have both — could be a subcategory, keep category as top-level
                elif found_date and found_cat:
                    _walk(entry.path, found_date=found_date, found_cat=found_cat)

                # No date yet — keep walking (year, month, custom folder, any depth)
                else:
                    _walk(entry.path, found_date=None, found_cat=None)

        _walk(base)
        return results

    def _get_gdrive_service(self):
        """Get Google Drive service using service account credentials."""
        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account

            creds_file = nab_connections.google_key_file()
            if not creds_file:
                logging.error("Google key not found (not bundled in this build).")
                return None

            creds = service_account.Credentials.from_service_account_file(
                creds_file, scopes=["https://www.googleapis.com/auth/drive"]
            )
            return build("drive", "v3", credentials=creds, cache_discovery=False)
        except Exception as e:
            logging.error(f"_get_gdrive_service: {e}")
            return None

    def _drive_get_or_create_folder(self, service, parent_id, name):
        """Get or create a folder in Google Drive — supports both personal and Shared Drive."""
        if not parent_id:
            return None
        try:
            safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
            q         = f"name='{safe_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            result    = service.files().list(
                q=q, fields="files(id,name)", pageSize=1,
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            files = result.get("files", [])
            if files:
                return files[0]["id"]
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            f    = service.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
            return f["id"]
        except Exception as e:
            logging.error(f"_drive_get_or_create_folder '{name}': {e}")
            return None

    def _drive_file_exists(self, service, parent_id, filename):
        """Check if a file already exists in a Drive folder."""
        if not parent_id:
            return False
        try:
            safe_name = filename.replace("\\", "\\\\").replace("'", "\\'")
            q         = f"name='{safe_name}' and '{parent_id}' in parents and trashed=false"
            result    = service.files().list(
                q=q, fields="files(id)", pageSize=1,
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute()
            return len(result.get("files", [])) > 0
        except Exception as e:
            logging.error(f"_drive_file_exists '{filename}': {e}")
            return False

    def _drive_upload_file(self, service, parent_id, file_path, filename):
        """Upload a single file to Google Drive folder."""
        if not parent_id:
            raise ValueError(f"parent_id is None for {filename}")
        from googleapiclient.http import MediaFileUpload
        import mimetypes
        mime, _ = mimetypes.guess_type(file_path)
        mime     = mime or "image/jpeg"
        meta     = {"name": filename, "parents": [parent_id]}
        media    = MediaFileUpload(file_path, mimetype=mime, resumable=False)
        service.files().create(
            body=meta, media_body=media, fields="id",
            supportsAllDrives=True
        ).execute()
        return True

    def _test_drive_connection(self):
        """Test Drive connection and send diagnostic info via Telegram."""
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service:
                _tg_send(f"❌ Drive test on <b>{PC_NAME}</b>: No service (check creds file)")
                return
            if not root_id:
                _tg_send(f"❌ Drive test on <b>{PC_NAME}</b>: No root folder ID")
                return
            # Try to list files in root folder
            result = service.files().list(
                q=f"'{root_id}' in parents and trashed=false",
                fields="files(id,name)", pageSize=5
            ).execute()
            files = result.get("files", [])
            # Try to create a test folder
            meta   = {"name": "_NAB_TEST_", "mimeType": "application/vnd.google-apps.folder", "parents": [root_id]}
            folder = service.files().create(body=meta, fields="id,name").execute()
            # Delete it immediately
            service.files().delete(fileId=folder["id"]).execute()
            _tg_send(
                f"✅ <b>Drive connection OK — {PC_NAME}</b>\n\n"
                f"Root folder ID: <code>{root_id}</code>\n"
                f"Existing items in root: <b>{len(files)}</b>\n"
                f"Write access: ✅ confirmed\n\n"
                f"Drive is ready for uploads."
            )
        except Exception as e:
            _tg_send(
                f"❌ <b>Drive test FAILED — {PC_NAME}</b>\n\n"
                f"Error: <code>{e}</code>\n\n"
                f"Root ID: <code>{self._drive_get_root_id()}</code>"
            )

    def _drive_get_root_id(self):
        """Drive root folder ID — built in (override: Settings → Advanced)."""
        return nab_connections.drive_folder_id()

    def _upload_date_list(self, category, dates):
        """Upload all files for a list of specific dates. category='*' means all."""
        import threading
        threading.Thread(target=self._upload_date_list_thread, args=(category, dates), daemon=True).start()

    def _upload_date_list_thread(self, category, dates):
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service or not root_id:
                missing = []
                if not service: missing.append("Google key (not bundled in this build)")
                if not root_id: missing.append("Drive root folder ID")
                _tg_send(
                    f"❌ <b>Drive not configured on {PC_NAME}</b>\n\n"
                    f"Missing: {', '.join(missing)}\n\n"
                    f"Rebuild NAB with the Google key next to BUILD.bat (see Settings → Advanced)."
                )
                return

            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found: <code>{base}</code>")
                return

            date_set  = set(dates)
            to_upload = self._scan_all_files(date_filter=date_set if date_set != {"all"} else None)
            if category != "*":
                to_upload = [(d, c, fp, fn) for d, c, fp, fn in to_upload if c == category]

            total     = len(to_upload)
            uploaded  = 0
            skipped   = 0

            if total == 0:
                _tg_send(f"📭 No files found on <b>{PC_NAME}</b> for the requested dates.")
                return

            cat_label = category if category != "*" else "all categories"
            _tg_send(
                f"📤 <b>Starting Upload — {PC_NAME}</b>\n"
                f"📁 {cat_label} | 📅 {len(dates)} date(s)\n"
                f"Files: <b>{total}</b>"
            )

            for date_str, cat, fpath, fname in to_upload:
                try:
                    year_id = self._drive_get_or_create_folder(service, root_id, date_str[:4] if len(date_str) > 6 else "Unknown")
                    date_id = self._drive_get_or_create_folder(service, year_id, date_str)
                    cat_id  = self._drive_get_or_create_folder(service, date_id, cat)
                    if self._drive_file_exists(service, cat_id, fname):
                        skipped += 1
                    else:
                        if self._drive_upload_file(service, cat_id, fpath, fname):
                            uploaded += 1
                        else:
                            skipped += 1
                except Exception as e:
                    logging.error(f"upload {fname}: {e}")
                    skipped += 1

            _tg_send(
                f"✅ <b>Upload Complete — {PC_NAME}</b>\n\n"
                f"📁 {cat_label}\n"
                f"📅 {len(dates)} date(s)\n"
                f"📤 Uploaded: <b>{uploaded}</b>\n"
                f"⏭ Skipped (already on Drive): <b>{skipped}</b>\n"
                f"📊 Total: <b>{total}</b>"
            )
        except Exception as e:
            logging.error(f"_upload_date_list_thread: {e}")
            _tg_send(f"❌ Upload error on <b>{PC_NAME}</b>: {e}")

    def _upload_old_files(self, category, scope):
        """Upload files by scope with a live progress window."""
        import threading
        # Show progress window on main thread
        self.after(0, lambda: self._start_upload_with_progress(category, scope))

    def _start_upload_with_progress(self, category, scope):
        """Create progress window then start upload thread."""
        import threading
        import tkinter as tk

        win = ctk.CTkToplevel(self)
        win.title("Uploading to Drive")
        nab_ui_scale.fit(win, 480, 280, parent=self)
        win.lift()
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="📤 Uploading to Google Drive",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(18, 4))

        cat_label = category if category != "*" else "All Categories"
        ctk.CTkLabel(win, text=f"Scope: {scope}  |  Category: {cat_label}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack()

        status_var  = tk.StringVar(value="Scanning files...")
        file_var    = tk.StringVar(value="")
        status_lbl  = ctk.CTkLabel(win, textvariable=status_var, font=ctk.CTkFont(size=12))
        status_lbl.pack(pady=(14, 2))

        file_lbl = ctk.CTkLabel(win, textvariable=file_var, font=ctk.CTkFont(size=10),
                                text_color="gray", wraplength=440)
        file_lbl.pack()

        progress_bar = ctk.CTkProgressBar(win, width=420, height=18)
        progress_bar.set(0)
        progress_bar.pack(pady=(12, 4))

        count_var = tk.StringVar(value="0 / 0")
        ctk.CTkLabel(win, textvariable=count_var, font=ctk.CTkFont(size=11)).pack()

        cancel_flag = [False]
        def cancel():
            cancel_flag[0] = True
            status_var.set("Cancelling...")

        cancel_btn = ctk.CTkButton(win, text="Cancel", width=100,
                                   fg_color="#555", command=cancel)
        cancel_btn.pack(pady=(10, 0))

        def _upload_thread():
            try:
                service = self._get_gdrive_service()
                root_id = self._drive_get_root_id()
                if not service or not root_id:
                    win.after(0, lambda: status_var.set("❌ Drive not configured!"))
                    win.after(2000, win.destroy)
                    _tg_send(f"❌ Drive not configured on <b>{PC_NAME}</b>.")
                    return

                all_files = self._scan_all_files()
                if category != "*":
                    all_files = [(d,c,fp,fn) for d,c,fp,fn in all_files if c == category]

                to_upload = []
                for date_str, cat, fpath, fname in all_files:
                    if scope.lower() == "all":
                        to_upload.append((date_str, cat, fpath, fname))
                        continue
                    try:
                        dt = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                        if len(scope) == 10 and scope.count("-") == 2:
                            if date_str == scope: to_upload.append((date_str, cat, fpath, fname))
                        elif len(scope) == 7:
                            if dt.strftime("%Y-%m") == scope: to_upload.append((date_str, cat, fpath, fname))
                        elif len(scope) == 4:
                            if dt.strftime("%Y") == scope: to_upload.append((date_str, cat, fpath, fname))
                    except Exception:
                        pass

                total    = len(to_upload)
                uploaded = 0
                skipped  = 0
                errors   = 0

                if total == 0:
                    win.after(0, lambda: status_var.set("📭 No files found."))
                    win.after(2000, win.destroy)
                    _tg_send(f"📭 No files found on <b>{PC_NAME}</b> for <b>{cat_label}</b> / <b>{scope}</b>.")
                    return

                win.after(0, lambda t=total: count_var.set(f"0 / {t}"))
                _tg_send(f"📤 <b>Upload started — {PC_NAME}</b>\nCategory: <b>{cat_label}</b> | Scope: <b>{scope}</b>\nFiles: <b>{total}</b>")

                for i, (date_str, cat, fpath, fname) in enumerate(to_upload):
                    if cancel_flag[0]:
                        break
                    # Update UI
                    pct = i / total
                    win.after(0, lambda p=pct: progress_bar.set(p))
                    win.after(0, lambda f=fname: file_var.set(f"↑ {f}"))
                    win.after(0, lambda i=i, t=total, u=uploaded, s=skipped, e=errors:
                              [status_var.set(f"Uploading... {int(i/t*100)}%"),
                               count_var.set(f"{i} / {t}  |  ✅{u}  ⏭{s}  ❌{e}")])
                    try:
                        try:
                            year = datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y")
                        except Exception:
                            year = "Unknown"
                        year_id = self._drive_get_or_create_folder(service, root_id, year)
                        if not year_id:
                            if errors == 0:
                                _tg_send(f"🔍 Debug: year_id is None for year='{year}', root_id='{root_id}'")
                            errors += 1; continue
                        date_id = self._drive_get_or_create_folder(service, year_id, date_str)
                        if not date_id:
                            if errors == 0:
                                _tg_send(f"🔍 Debug: date_id is None for date='{date_str}', year_id='{year_id}'")
                            errors += 1; continue
                        cat_id = self._drive_get_or_create_folder(service, date_id, cat)
                        if not cat_id:
                            if errors == 0:
                                _tg_send(f"🔍 Debug: cat_id is None for cat='{cat}', date_id='{date_id}'")
                            errors += 1; continue
                        if self._drive_file_exists(service, cat_id, fname):
                            skipped += 1
                        else:
                            try:
                                self._drive_upload_file(service, cat_id, fpath, fname)
                                uploaded += 1
                            except Exception as ue:
                                if errors == 0:
                                    _tg_send(f"🔍 Upload error:\nFile: <code>{fname}</code>\nError: <code>{ue}</code>")
                                errors += 1
                    except Exception as e:
                        if errors == 0:
                            _tg_send(f"🔍 Debug first error:\nFile: <code>{fname}</code>\nError: <code>{e}</code>")
                        logging.error(f"upload {fname}: {e}")
                        errors += 1

                # Done
                win.after(0, lambda: progress_bar.set(1.0))
                win.after(0, lambda: status_var.set("✅ Upload Complete!"))
                win.after(0, lambda: file_var.set(""))
                win.after(0, lambda: count_var.set(f"{total} / {total}  |  ✅{uploaded}  ⏭{skipped}  ❌{errors}"))
                win.after(0, lambda: cancel_btn.configure(text="Close", command=win.destroy))

                _tg_send(
                    f"✅ <b>Upload Complete — {PC_NAME}</b>\n\n"
                    f"📁 {cat_label} | Scope: <b>{scope}</b>\n"
                    f"📤 Uploaded: <b>{uploaded}</b>\n"
                    f"⏭ Skipped: <b>{skipped}</b>\n"
                    f"❌ Errors: <b>{errors}</b>\n"
                    f"📊 Total: <b>{total}</b>"
                )
            except Exception as e:
                logging.error(f"upload thread: {e}")
                win.after(0, lambda err=str(e): status_var.set(f"❌ Error: {err}"))
                _tg_send(f"❌ Upload error on <b>{PC_NAME}</b>: {e}")

        threading.Thread(target=_upload_thread, daemon=True).start()

    def _upload_old_files_thread(self, category, scope):
        try:
            service = self._get_gdrive_service()
            root_id = self._drive_get_root_id()
            if not service or not root_id:
                missing = []
                if not service: missing.append("Google key (not bundled in this build)")
                if not root_id: missing.append("Drive root folder ID")
                _tg_send(
                    f"❌ <b>Drive not configured on {PC_NAME}</b>\n\n"
                    f"Missing: {', '.join(missing)}\n\n"
                    f"Rebuild NAB with the Google key next to BUILD.bat (see Settings → Advanced)."
                )
                return

            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found on <b>{PC_NAME}</b>: <code>{base}</code>")
                return

            # Use universal scanner — works with any folder structure/drive
            all_files = self._scan_all_files()
            if category != "*":
                all_files = [(d, c, fp, fn) for d, c, fp, fn in all_files if c == category]

            # Filter by scope
            to_upload = []
            for date_str, cat, fpath, fname in all_files:
                if scope.lower() == "all":
                    to_upload.append((date_str, cat, fpath, fname))
                    continue
                try:
                    dt = datetime.datetime.strptime(date_str, "%d-%m-%Y")
                    if len(scope) == 10 and scope.count("-") == 2:
                        if date_str == scope: to_upload.append((date_str, cat, fpath, fname))
                    elif len(scope) == 7:  # YYYY-MM
                        if dt.strftime("%Y-%m") == scope: to_upload.append((date_str, cat, fpath, fname))
                    elif len(scope) == 4:  # YYYY
                        if dt.strftime("%Y") == scope: to_upload.append((date_str, cat, fpath, fname))
                except Exception:
                    pass

            total    = len(to_upload)
            uploaded = 0
            skipped  = 0
            errors   = 0

            if total == 0:
                _tg_send(f"📭 No files found for <b>{category}</b> / <b>{scope}</b> on <b>{PC_NAME}</b>.")
                return

            _tg_send(f"📤 Starting upload on <b>{PC_NAME}</b>\nCategory: <b>{category}</b> | Scope: <b>{scope}</b>\nFiles: <b>{total}</b>")

            for date_str, cat, fpath, fname in to_upload:
                try:
                    try:
                        year = datetime.datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y")
                    except Exception:
                        year = "Unknown"
                    year_id = self._drive_get_or_create_folder(service, root_id, year)
                    date_id = self._drive_get_or_create_folder(service, year_id, date_str)
                    cat_id  = self._drive_get_or_create_folder(service, date_id, cat)
                    if not cat_id:
                        errors += 1
                        continue
                    if self._drive_file_exists(service, cat_id, fname):
                        skipped += 1
                    else:
                        if self._drive_upload_file(service, cat_id, fpath, fname):
                            uploaded += 1
                        else:
                            errors += 1
                except Exception as e:
                    logging.error(f"upload file {fname}: {e}")
                    errors += 1

            _tg_send(
                f"✅ <b>Upload Complete — {PC_NAME}</b>\n\n"
                f"Category: <b>{category}</b> | Scope: <b>{scope}</b>\n"
                f"📤 Uploaded: <b>{uploaded}</b>\n"
                f"⏭ Skipped (already on Drive): <b>{skipped}</b>\n"
                f"❌ Errors: <b>{errors}</b>\n"
                f"📊 Total: <b>{total}</b>"
            )
        except Exception as e:
            logging.error(f"_upload_old_files_thread: {e}")
            _tg_send(f"❌ Upload error on <b>{PC_NAME}</b>: {e}")

    def _force_upload_category(self, category, date_str):
        """Force upload a specific category+date — triggered by cloud bot pending_req ping."""
        import threading
        threading.Thread(target=self._upload_old_files_thread, args=(category, date_str), daemon=True).start()

    def _scan_and_report_local(self):
        """Scan local disk and report what's available vs what's on Drive."""
        import threading
        threading.Thread(target=self._scan_and_report_local_thread, daemon=True).start()

    def _scan_and_report_local_thread(self):
        try:
            base = self.base_root
            if not os.path.exists(base):
                _tg_send(f"❌ Base folder not found on <b>{PC_NAME}</b>: <code>{base}</code>")
                return

            # Count files per category
            cat_counts = {}
            date_counts = {}
            total_files = 0

            all_files = self._scan_all_files()
            for date_str, cat, fpath, fname in all_files:
                cat_counts[cat]      = cat_counts.get(cat, 0) + 1
                date_counts[date_str] = date_counts.get(date_str, 0) + 1
                total_files          += 1

            if not cat_counts:
                _tg_send(f"📭 No files found on disk for <b>{PC_NAME}</b>.")
                return

            cat_lines  = "\n".join(f"  • <b>{c}</b>: {n} files" for c, n in sorted(cat_counts.items()))
            date_sample = "\n".join(f"  • {d}: {n}" for d, n in sorted(date_counts.items(), reverse=True)[:10])

            _tg_send(
                f"🔍 <b>Local Scan — {PC_NAME}</b>\n\n"
                f"📁 Base: <code>{base}</code>\n"
                f"📊 Total files: <b>{total_files}</b>\n\n"
                f"<b>By Category:</b>\n{cat_lines}\n\n"
                f"<b>Recent Dates (last 10):</b>\n{date_sample}\n\n"
                f"Use <code>/uploadold [Category] all</code> to upload any category."
            )
        except Exception as e:
            logging.error(f"_scan_and_report_local_thread: {e}")
            _tg_send(f"❌ Scan error on <b>{PC_NAME}</b>: {e}")

    # ── FEATURE 29: IN-APP DUPLICATE DETECTION ──
    def _check_duplicate(self, folder_path, fname):
        """
        Returns True ONLY if an identical file (same name = same paper/page/pos/size)
        already exists. Files with the same page but different size or position are
        NOT duplicates — they are allowed to save without any warning.
        """
        try:
            full_path = os.path.join(folder_path, fname)
            if os.path.exists(full_path):
                return True  # exact same filename = true duplicate
        except Exception:
            pass
        return False

    # ── FEATURE 32: FILE SIZE CHECK ──
    def _check_file_size(self, path):
        try:
            size_kb = os.path.getsize(path) / 1024
            min_kb = self.extra_settings.get("min_file_size_kb", 20)
            max_kb = self.extra_settings.get("max_file_size_kb", 5000)
            if size_kb < min_kb:
                self.after(0, lambda s=size_kb: self._show_size_warning(s, min_kb, "too small"))
            elif size_kb > max_kb:
                self.after(0, lambda s=size_kb: self._show_size_warning(s, max_kb, "too large"))
        except Exception:
            pass

    def _show_size_warning(self, size_kb, limit_kb, direction):
        self.status_label.configure(
            text=f"⚠️ File size {size_kb:.0f}KB is {direction}! (limit: {limit_kb}KB)",
            text_color=C_DANGER
        )
        messagebox.showwarning("File Size Warning",
                               f"The saved file is {size_kb:.0f}KB which seems {direction}.\n"
                               f"Limit: {limit_kb}KB\n\nCheck if the image is correct.")
        self.after(4000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    # ── FEATURE 35: GOAL CHECK ──
    def _check_goal(self):
        if self.daily_goal > 0 and not self.daily_goal_notified:
            count = len(self.session_history)
            if count >= self.daily_goal:
                self.daily_goal_notified = True
                self.status_label.configure(text=f"🎯 Goal reached! {count}/{self.daily_goal} clips!", text_color=C_SUCCESS)
                threading.Thread(target=lambda: _tg_send(
                    f"🎯 <b>Daily goal reached on {PC_NAME}!</b>\n"
                    f"Saved {count}/{self.daily_goal} clips. Great work!"
                ), daemon=True).start()

    # ── OPEN BROADCAST DIALOG ──
    def open_broadcast_dialog(self):
        BroadcastDialog(self, self._process_broadcast_dialog)

    def _process_broadcast_dialog(self, target, msg, custom):
        if target == "This PC":
            self._show_broadcast_popup(msg)
        elif target == "All PCs":
            self._show_broadcast_popup(msg)
            threading.Thread(target=lambda: _tg_send(
                f"📣 <b>Broadcast (All PCs):</b> {msg}"
            ), daemon=True).start()
        elif target == "Telegram Chat":
            threading.Thread(target=lambda: _tg_send(f"📣 {msg}"), daemon=True).start()
        elif target == "@custom_username":
            threading.Thread(target=lambda: _tg_send(
                f"📣 <b>Broadcast to {custom}:</b> {msg}\n(Note: Requires their chat_id configured)"
            ), daemon=True).start()

    def save_state(self):
        if len(self.undo_stack) > 15: self.undo_stack.pop(0)
        c_stack = [compress_img(img) for img in self.orig_images]
        self.undo_stack.append(c_stack)
        if len(self.redo_stack) > 15: self.redo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self, event=None):
        if self.undo_stack:
            self.redo_stack.append([compress_img(img) for img in self.orig_images])
            c_stack = self.undo_stack.pop()
            self.orig_images = [decompress_img(c) for c in c_stack]
            self.proxy_images = [self.create_proxy(i) for i in self.orig_images]
            self._clear_selection()
            self.force_update_preview()

    def redo(self, event=None):
        if self.redo_stack:
            self.undo_stack.append([compress_img(img) for img in self.orig_images])
            c_stack = self.redo_stack.pop()
            self.orig_images = [decompress_img(c) for c in c_stack]
            self.proxy_images = [self.create_proxy(i) for i in self.orig_images]
            self._clear_selection()
            self.force_update_preview()

    def background_monitor(self):
        """Clipboard / active-tab watcher. Runs forever on a thread.

        DETECTION IS EVENT-DRIVEN, not continuous. It re-evaluates only
        when something actually happened: the page/clipboard text changed,
        a NEW image/text was copied, the active tab changed, or the URL
        mappings were edited. An earlier version re-applied a remembered
        paper on every 0.5s tick, which kept overriding the dropdown and —
        because a window handle identifies the whole browser window, not
        one tab — let a single accidental 📍 press pin every tab."""
        last_tab_key = None
        last_seq = None
        while True:
            time.sleep(0.5)
            context = ""          # title + source URL (+ copied text): mapping input
            signal_text = ""      # title + source URL only: name-match input
            title = ""
            hwnd = None
            has_image = False
            seq = None
            clip_src_url = ""
            if HAS_WIN32:
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    t = win32gui.GetWindowText(hwnd)
                    if "News Automation" not in t and "Surgical Workspace" not in t:
                        title = t
                        context += title + " "
                        signal_text += title + " "
                        # Remembered for the 📍 button — by the time the
                        # operator clicks back into NAB, NAB itself is the
                        # foreground window.
                        self._last_external_hwnd = hwnd
                        self._last_external_title = title
                except Exception:
                    pass
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        try:
                            seq = win32clipboard.GetClipboardSequenceNumber()
                        except Exception:
                            seq = None
                        for fmt in (win32clipboard.CF_DIB, win32clipboard.CF_BITMAP,
                                    getattr(win32clipboard, "CF_DIBV5", 17)):
                            if win32clipboard.IsClipboardFormatAvailable(fmt):
                                has_image = True
                                break
                        html_fmt = win32clipboard.RegisterClipboardFormat("HTML Format")
                        if win32clipboard.IsClipboardFormatAvailable(html_fmt):
                            data = win32clipboard.GetClipboardData(html_fmt)
                            if isinstance(data, bytes):
                                data = data.decode('utf-8', errors='ignore')
                            for line in data.splitlines():
                                if line.startswith("SourceURL:"):
                                    u = line.split(":", 1)[1].strip()
                                    clip_src_url = u
                                    context += u + " "
                                    signal_text += u + " "
                                    break
                        elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                            context += win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) + " "
                    finally:
                        win32clipboard.CloseClipboard()
                except Exception:
                    try: win32clipboard.CloseClipboard()
                    except Exception: pass

            # ---- what just happened? ----
            clip_event = False
            if seq is not None:
                if last_seq is None:
                    last_seq = seq               # first look — not an event
                elif seq != last_seq:
                    last_seq, clip_event = seq, True
            tab_key = None
            if title:
                # digits/punctuation dropped so "Page 3 - X" and "Page 4 - X"
                # count as the same tab; (hwnd, title) — NOT hwnd alone.
                tab_key = (hwnd, re.sub(r"[\W\d_]+", "", title.lower()))
            tab_changed = bool(tab_key and tab_key != last_tab_key)
            if tab_key:
                last_tab_key = tab_key

            # ---- real tab URL (extension first, address-bar read second) ----
            # Refreshed only on events: UI Automation costs tens of ms, and
            # between events the cached URL for this tab is reused so the
            # context stays stable (no flapping re-detection every tick).
            if tab_key and nab_tabreader.looks_like_browser(title):
                if tab_changed or clip_event:
                    url = ""
                    try:
                        ti = self.preview_server.get_tab_info()
                    except Exception:
                        ti = None
                    if ti:
                        url = ti["url"]
                    elif HAS_WIN32:
                        url = nab_tabreader.read_address_bar(hwnd)
                    self._tab_url = (tab_key, url)
                tab_url = self._tab_url[1] if self._tab_url[0] == tab_key else ""
                if tab_url:
                    context += tab_url + " "
                    signal_text += tab_url + " "
            else:
                tab_url = ""
            context_changed = bool(context.strip() and context != self.last_context)

            if context_changed or clip_event or tab_changed:
                self.last_context = context
                lock_paper = self._tab_locks.get(tab_key) if (tab_key and (tab_changed or clip_event)) else None
                paper, how, detail = nab_clip_scan.detect_paper(
                    context, signal_text, self.url_mappings, self.paper_list,
                    lock_paper=lock_paper,
                    allow_name_fallback=bool(clip_event and has_image))
                if (clip_event and has_image) or tab_changed:
                    self._learn.note_event(time.time(), title, tab_url or clip_src_url, paper)
                if paper:
                    if self.paper_combo.get() != paper:
                        label = {"mapping": f"'{detail}'", "lock": "locked tab",
                                 "name": "paper name"}.get(how, how)
                        self.after(0, lambda p=paper, l=label: self._apply_detected_paper(p, l))
                elif clip_event and has_image:
                    # A copy just happened and nothing matched. Say what was
                    # seen, so a mapping can be written for exactly that.
                    seen = (title or "(no window title)")[:34]
                    self.after(0, lambda t=seen: self._flash_detect(
                        f"⚠ NO PAPER MATCH — tab: {t}", "#EF4444", 3500))

            if not hasattr(self, 'auto_snatch_var') or not self.auto_snatch_var.get(): continue
            try:
                img = _grab_clipboard_windows()
                if isinstance(img, Image.Image):
                    t = img.copy(); t.thumbnail((32, 32))
                    img_hash = hash(t.tobytes())
                    if img_hash != self.last_clipboard_hash:
                        self.last_clipboard_hash = img_hash
                        if self.workspace_instance and self.workspace_instance.winfo_exists():
                            self.after(0, lambda i=img: self.workspace_instance.paste_to_workspace(i))
                        else:
                            self.after(0, lambda i=img: self.paste_image(provided_img=i))
            except Exception:
                pass

    def _on_synced(self, namespaces):
        """Tk thread: another PC's changes were just written to disk — load
        them into the running app so they take effect now and aren't
        overwritten by this PC's stale in-memory copy on the next save."""
        try:
            ns = set(namespaces)
            if ns & {"app_settings", "url_mappings"}:
                self.load_settings()
                self.setup_shortcuts()
                self.last_context = ""
            if "sources" in ns:
                cur = self.paper_var.get()
                self.load_sources()
                if cur in self.paper_list:
                    self.paper_combo.set(cur)
            if "categories" in ns:
                self.load_categories()
            names = {"app_settings": "settings", "url_mappings": "mappings", "sources": "papers",
                     "categories": "categories", "subscriptions": "subscriptions",
                     "paper_aliases": "aliases", "pdf_maker": "PDF Maker"}
            self._flash_detect("🔄 Synced: " + ", ".join(names.get(n, n) for n in namespaces),
                               "#22C55E", 3500)
        except Exception as e:
            logging.error(f"_on_synced: {e}")

    def open_sync(self):
        nab_sync_ui.open_sync_dialog(self)

    def _on_user_paper_choice(self):
        """The operator picked a paper by hand. If detection saw a tab a
        moment ago and disagreed (or found nothing), offer to remember it."""
        try:
            sug = self._learn.on_user_choice(time.time(), self.paper_var.get(), self.url_mappings)
            if sug and sug["fragment"] not in self._learn_declined:
                self._learn.ctx = None          # one prompt per event
                self._show_learn_prompt(sug)
        except Exception as e:
            logging.error(f"_on_user_paper_choice: {e}")

    def _show_learn_prompt(self, sug):
        win = ctk.CTkToplevel(self)
        win.title("Remember this?")
        win.configure(fg_color=C_BG)
        win.attributes("-topmost", True)
        nab_ui_scale.fit(win, 440, 210, min_w=300, min_h=190, parent=self)
        was = strip_emoji_prefix(sug["replaces"]) if sug["replaces"] else "nothing"
        ctk.CTkLabel(win, text=f"Detection picked {was}.\nAlways choose {strip_emoji_prefix(sug['paper'])} for tabs containing:",
                     font=("Arial", 12), text_color=C_TEXT_MAIN, justify="left").pack(padx=16, pady=(14, 6), anchor="w")
        e = ctk.CTkEntry(win, fg_color="#000", border_color=C_BORDER)
        e.insert(0, sug["fragment"])
        e.pack(fill="x", padx=16)
        info = ctk.CTkLabel(win, text=(sug["url"] or sug["title"])[:70], font=("Consolas", 9), text_color=C_TEXT_DIM)
        info.pack(padx=16, pady=(2, 8), anchor="w")
        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))

        def remember():
            frag = e.get().strip().lower()
            if frag and nab_learn.fragment_is_safe(frag, self.url_mappings):
                m = dict(self.url_mappings)
                m[frag] = sug["paper"]
                self.save_url_mappings(m)
                self._flash_detect(f"✔ Learned: '{frag}' → {strip_emoji_prefix(sug['paper'])}", "#22C55E", 3000)
            win.destroy()

        def decline():
            self._learn_declined.add(sug["fragment"])
            win.destroy()
        ctk.CTkButton(row, text="✔ REMEMBER", fg_color=C_ACCENT, text_color="black", command=remember).pack(side="left", expand=True, fill="x", padx=3)
        ctk.CTkButton(row, text="NOT THIS ONE", fg_color="#333", command=decline).pack(side="left", expand=True, fill="x", padx=3)
        win.after(20000, lambda: win.winfo_exists() and win.destroy())

    def _apply_detected_paper(self, paper, how_label):
        """Main-thread: select the detected paper and say why."""
        try:
            self.paper_combo.set(paper)
            self.force_update_preview()
        except Exception as e:
            logging.error(f"_apply_detected_paper: {e}")
        self._flash_detect(f"📍 {strip_emoji_prefix(paper)}  ({how_label})", "#22C55E", 2200)

    def _flash_detect(self, text, color, ms):
        """Brief status-bubble message — never replaces a real in-progress
        status (PROCESSING..., SAVING...), only an idle READY."""
        try:
            cur = self.status_label.cget("text")
            if cur not in ("READY", ""):
                return
            self.status_label.configure(text=text, text_color=color)
            self.after(ms, lambda: self.status_label.cget("text") == text and
                       self.status_label.configure(text="READY", text_color=C_TEXT_DIM))
        except Exception:
            pass

    def _auto_select_from_url(self):
        """Feature 13: Auto-select category when URL maps to a paper"""
        pass  # category auto-selection is context-dependent; paper auto-select already works above

    def _lock_window_to_paper(self):
        """📍 — for epaper sites whose tab title is just generic "ePaper"
        text and whose copies carry no usable source URL. Locks the TAB
        you were last on (not the whole browser window) to the paper
        currently selected, so switching to it or copying from it selects
        that paper again. Press again on the same tab to UNLOCK. Right-click
        the button to clear every lock. A real URL/title mapping match always
        wins over a lock, so a mistaken lock can't block genuine detection."""
        hwnd = getattr(self, '_last_external_hwnd', None)
        title = getattr(self, '_last_external_title', "")
        paper = self.paper_var.get()
        if not hwnd or not title:
            messagebox.showinfo(
                "Nothing to lock",
                "Click the epaper's browser tab, copy one image from it, "
                "then come back and press 📍.")
            return
        if not paper:
            messagebox.showwarning("No paper selected", "Pick a paper first.")
            return
        key = (hwnd, re.sub(r"[\W\d_]+", "", title.lower()))
        clean = strip_emoji_prefix(paper)
        if self._tab_locks.get(key) == paper:
            del self._tab_locks[key]
            self._flash_detect(f"📍 UNLOCKED: {title[:28]}", "#F59E0B", 2500)
            return
        self._tab_locks[key] = paper
        self._flash_detect(f"📍 LOCKED '{title[:22]}' → {clean}", "#22C55E", 3000)

    def _clear_tab_locks(self):
        n = len(self._tab_locks)
        self._tab_locks.clear()
        self._flash_detect(f"📍 CLEARED {n} LOCK{'S' if n != 1 else ''}", "#F59E0B", 2500)

    def setup_login_overlay(self):
        self.login_frame = ctk.CTkFrame(self, fg_color=C_BG)
        self.login_frame.place(relwidth=1, relheight=1)

        center_box = ctk.CTkFrame(self.login_frame, width=420, height=300,
                                   fg_color=C_SURFACE, corner_radius=20,
                                   border_color="#1E4A8A", border_width=1)
        center_box.place(relx=0.5, rely=0.5, anchor="center")
        center_box.pack_propagate(False)

        ctk.CTkLabel(center_box, text="🔐  AUTHORIZATION REQUIRED",
                     font=("Consolas", 15, "bold"), text_color="#00D4FF").pack(pady=(30, 5))
        ctk.CTkLabel(center_box, text="A login request has been sent to your phone.",
                     font=("Segoe UI", 11), text_color="#888").pack()

        self._auth_status = ctk.CTkLabel(center_box, text="⏳ Waiting for approval...",
                                          font=("Consolas", 13, "bold"), text_color="#FF9500")
        self._auth_status.pack(pady=15)

        self._auth_timer = ctk.CTkLabel(center_box, text=f"Auto-denied in {AUTH_TIMEOUT}s",
                                         font=("Consolas", 11), text_color="#555")
        self._auth_timer.pack()

        ctk.CTkLabel(center_box, text="Reply  allow  or  deny  on Telegram",
                     font=("Consolas", 11), text_color="#444").pack(pady=(10, 0))

        self._auth_result = None
        self._auth_countdown = AUTH_TIMEOUT
        threading.Thread(target=self._run_2fa, daemon=True).start()
        self._tick_auth_timer()

    def _tick_auth_timer(self):
        if not hasattr(self, 'login_frame') or not self.login_frame.winfo_exists():
            return
        if self._auth_result is not None:
            return
        self._auth_countdown -= 1
        try:
            self._auth_timer.configure(text=f"Auto-denied in {max(0, self._auth_countdown)}s")
        except Exception:
            pass
        if self._auth_countdown > 0:
            self.after(1000, self._tick_auth_timer)

    def _run_2fa(self):
        result = TelegramAuth.request_access()
        self._auth_result = result
        self.after(0, lambda: self._on_auth_result(result))

    def _on_auth_result(self, granted):
        if granted:
            try:
                self._auth_status.configure(text="✅ Access Granted!", text_color="#00FF88")
            except Exception:
                pass
            self.after(800, self._finish_login)
        else:
            try:
                self._auth_status.configure(text="⛔ Access Denied.", text_color="#FF4444")
            except Exception:
                pass
            self.after(2000, lambda: [self.destroy(), sys.exit(0)])

    def _finish_login(self):
        try:
            self.login_frame.destroy()
        except Exception:
            pass
        # FIX 16: Send login alert with active newspaper + category
        paper = self.paper_combo.get() if hasattr(self, 'paper_combo') else "?"
        threading.Thread(target=lambda: _tg_send(
            f"✅ <b>NAB Session Started</b>\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"📰 Active paper: {paper}\n"
            f"📅 Date: {self.current_date.strftime('%d-%m-%Y')}"
        ), daemon=True).start()

        threading.Thread(
            target=TelegramAuth.run_background_listener,
            args=(self,), daemon=True
        ).start()

        # Check if a upload was scheduled from last session
        self.after(3000, self._check_pending_upload)

        # Check for an interrupted batch session (sealed clips from a crash)
        self.after(1500, lambda: nab_batch_ui.check_resume_on_launch(self))

        # Subscription expiry reminder — once at startup, then re-checked
        # every few hours in case NAB stays open for days and a paper
        # crosses into the warning window while it's running.
        self.after(4000, lambda: nab_subscriptions.check_and_remind(self))
        nab_subscriptions.schedule_periodic_check(self)

        # Tracker no longer auto-opens at startup — it was popping the full
        # window (calendar, heatmap, month view) open on every single launch,
        # which had nothing to do with anything the operator was doing yet.
        # It's still reachable any time via the 📰 Tracker button, and the
        # end-of-day confirmation in on_app_close() is the only place it
        # shows up uninvited now.

    def _open_tracker(self):
        if not hasattr(self, '_tracker_win') or not self._tracker_win.winfo_exists():
            self._tracker_win = NewspaperTracker(self)
        else:
            # _tracker_session_prompt() withdraws this same window when it
            # only needs the small end-of-session dialog. If the operator
            # then cancelled the close, the window still exists but is
            # hidden — deiconify() is required here or a later click on this
            # button would lift()/focus() a window nobody can see.
            self._tracker_win.deiconify()
            self._tracker_win.lift()
            self._tracker_win.focus_force()

    def check_login(self): pass
    def reset_pass_entry(self): pass

    def setup_shortcuts(self):
        if hasattr(self, '_current_binds'):
            for key in self._current_binds:
                try: self.unbind_all(key)
                except: pass
        self._current_binds = []
        for action, key in self.universal_hotkeys.items():
            if key and key not in ["None", "Unbound"] and action in self.action_map:
                try:
                    self.bind_all(key, self.action_map[action])
                    self._current_binds.append(key)
                except: pass
        self.bind_all('<KeyPress>', self.on_key_press)
        self.bind_all('<KeyRelease>', self.on_key_release)

    def open_universal_hotkeys(self):
        UniversalHotkeyDialog(self, self.universal_hotkeys, self.save_universal_hotkeys)

    def save_universal_hotkeys(self, new_map):
        self.universal_hotkeys.update(new_map)
        self.save_settings()
        self.setup_shortcuts()
        messagebox.showinfo("Success", "Universal Hotkeys Updated.")

    def handle_tool_key(self, action):
        fw = self.focus_get()
        if isinstance(fw, (tk.Entry, ttk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)): return
        if self.rect_id:
            self._apply_box_action(action)

    def on_key_press(self, event):
        keysym = event.keysym
        if keysym == 'space':
            self.space_pressed = True
            self.update_cursor()
        elif keysym in ('Control_L', 'Control_R'):
            self.ctrl_pressed = True
            self.update_cursor()
        fw = self.focus_get()
        if isinstance(fw, (tk.Entry, ttk.Entry, tk.Text, ctk.CTkEntry, ctk.CTkTextbox)): return
        ctrl_key = ("Ctrl+" + keysym) if self.ctrl_pressed else keysym
        if ctrl_key in self.quick_saves:
            self.execute_quick_save(self.quick_saves[ctrl_key])
        elif keysym in self.quick_saves and not self.ctrl_pressed:
            self.execute_quick_save(self.quick_saves[keysym])

    def on_key_release(self, event):
        if event.keysym == 'space': self.space_pressed = False
        if event.keysym in ('Control_L', 'Control_R'): self.ctrl_pressed = False
        self.update_cursor()

    def update_cursor(self):
        if self.ctrl_pressed and self.space_pressed: self.preview_canvas.configure(cursor="sizing")
        elif self.space_pressed: self.preview_canvas.configure(cursor="fleur")
        else: self.preview_canvas.configure(cursor="crosshair")

    def smart_delete(self):
        if self.rect_id: self._apply_box_action("erase")
        else: self.undo()

    def setup_ui(self):
        # Everything that used to be parented straight to `self` (the root
        # window) now lives inside the "Clip" tab of a CTkTabview, with a
        # sibling "Batch" tab for batch processing. The root window itself
        # now just holds this one tabview, filling the whole space.
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.main_tabs = ctk.CTkTabview(
            self, fg_color=C_BG,
            segmented_button_fg_color="#0D0D14",
            segmented_button_selected_color=C_ACCENT,
            segmented_button_unselected_color="#0D0D14",
            segmented_button_selected_hover_color=C_ACCENT_HOVER,
            text_color="#CCC",
        )
        self.main_tabs.grid(row=0, column=0, sticky="nsew")
        tab_clip = self.main_tabs.add("✂️ Clip")
        tab_batch = self.main_tabs.add("📦 Batch")

        tab_clip.grid_columnconfigure(0, weight=3, minsize=320)
        tab_clip.grid_columnconfigure(1, weight=7)
        tab_clip.grid_rowconfigure(0, weight=1)
        self.left_panel = ctk.CTkFrame(tab_clip, fg_color=C_SURFACE, corner_radius=0)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(fill="x")
        ctk.CTkLabel(title_frame, text="NEWS AUTOMATION", font=F_HEADER, text_color=C_TEXT_MAIN).pack(side="left")
        ctk.CTkButton(title_frame, text="⚙️", width=30, height=30, fg_color="#1A1A1A", hover_color="#333",
                      font=F_BTN, command=self.open_global_settings).pack(side="right")
        ctk.CTkButton(title_frame, text="⌨️", width=30, height=30, fg_color="#1A1A1A", hover_color="#333",
                      font=F_BTN, command=self.open_universal_hotkeys).pack(side="right", padx=5)
        ctk.CTkButton(title_frame, text="📣", width=30, height=30, fg_color="#1A1A1A", hover_color="#333",
                      font=F_BTN, command=self.open_broadcast_dialog).pack(side="right", padx=2)

        txt = f"📅 {self.current_date.strftime('%Y-%m-%d')}"
        self.date_btn = ctk.CTkButton(header, text=txt, command=self.open_calendar, font=("Consolas", 12),
                                       fg_color="#222", hover_color="#333", width=120)
        self.date_btn.pack(anchor="w", pady=(5, 0))

        src_box = ctk.CTkFrame(self.left_panel, fg_color="#000", corner_radius=10, border_color=C_BORDER, border_width=1)
        src_box.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(src_box, text="SOURCE", font=F_SUBHEAD, text_color=C_TEXT_DIM).pack(padx=10, pady=(10, 0), anchor="w")
        src_row = ctk.CTkFrame(src_box, fg_color="transparent")
        src_row.pack(fill="x", padx=5, pady=5)
        # Bound to a real StringVar (rather than CTkOptionMenu's own internal
        # value) specifically so the Batch tab's own paper dropdown — a
        # separate widget, since it lives in a different tab — can share the
        # exact same selection without any extra sync code.
        self.paper_var = ctk.StringVar()
        self.paper_combo = ctk.CTkOptionMenu(src_row, height=35, corner_radius=8, font=F_BODY, fg_color="#1A1A1A",
                                              button_color=C_ACCENT, button_hover_color=C_ACCENT_HOVER,
                                              variable=self.paper_var,
                                              command=lambda _: (self.force_update_preview(),
                                                                 self._on_user_paper_choice()))
        self.paper_combo.pack(side="left", fill="x", expand=True, padx=(5, 5))
        lock_btn = ctk.CTkButton(src_row, text="📍", width=30, height=35, fg_color="#1A1A1A",
                                 hover_color="#333", font=F_BTN, command=self._lock_window_to_paper)
        lock_btn.pack(side="right", padx=(0, 5))
        lock_btn.bind("<Button-3>", lambda e: self._clear_tab_locks())
        ctk.CTkButton(src_row, text="🔗", width=30, height=35, fg_color="#1A1A1A", hover_color="#333",
                      font=F_BTN, command=self.open_url_mapping).pack(side="right", padx=(0, 5))
        ctk.CTkButton(src_row, text="✏️", width=30, height=35, fg_color="#1A1A1A", hover_color="#333",
                      font=F_BTN, command=self.open_source_manager).pack(side="right", padx=(0, 5))
        self.load_sources()

        cat_box = ctk.CTkFrame(self.left_panel, fg_color="#000", corner_radius=10, border_color=C_BORDER, border_width=1)
        cat_box.pack(fill="both", expand=True, padx=20, pady=5)

        cat_header = ctk.CTkFrame(cat_box, fg_color="transparent")
        cat_header.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(cat_header, text="DESTINATION", font=F_SUBHEAD, text_color=C_TEXT_DIM).pack(side="left")

        # Feature 14: Batch mode indicator
        self.batch_mode_label = ctk.CTkLabel(cat_header, text="", font=("Segoe UI", 9), text_color=C_ACCENT)
        self.batch_mode_label.pack(side="left", padx=5)

        self.cat_settings_btn = ctk.CTkButton(cat_header, text="⚙️", width=30, height=30, fg_color="#1A1A1A",
                                               hover_color="#333", font=F_BTN, command=self.show_cat_settings)
        self.cat_settings_btn.pack(side="right", padx=(5, 0))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#000", foreground="#DDD", fieldbackground="#000",
                        rowheight=22, font=F_BODY, borderwidth=0)
        style.map('Treeview', background=[('selected', C_ACCENT)])
        self.cat_tree = ttk.Treeview(cat_box, show="tree", style="Treeview", selectmode="extended")
        self.cat_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.cat_tree.bind("<<TreeviewSelect>>", self.on_cat_change)
        self.cat_tree.bind("<Button-3>", self.show_context_menu)
        self.load_categories()

        ctrl_box = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        ctrl_box.pack(fill="x", padx=10, pady=10)
        sw_row = ctk.CTkFrame(ctrl_box, fg_color="transparent")
        sw_row.pack(fill="x", pady=5)

        self.show_text_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(sw_row, text="Header", font=F_BODY, variable=self.show_text_var,
                      command=self.force_update_preview, progress_color=C_ACCENT).pack(side="left", padx=3)

        self.auto_snatch_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(sw_row, text="Auto Snatch", font=F_BODY, variable=self.auto_snatch_var,
                      progress_color="#1E88E5").pack(side="left", padx=3)

        self.auto_polish_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(sw_row, text="Auto Polish", font=F_BODY, variable=self.auto_polish_var,
                      progress_color="#8E24AA", command=self.on_auto_polish_toggle).pack(side="left", padx=3)

        self.hd_mode_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(sw_row, text="Force HD", font=F_BODY, variable=self.hd_mode_var,
                      progress_color="#D32F2F").pack(side="right", padx=3)

        def add_sl(parent, txt, v_min, v_max, init):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=2)
            ctk.CTkLabel(r, text=txt, font=F_SUBHEAD, width=60, anchor="w", text_color=C_TEXT_DIM).pack(side="left")
            s = ctk.CTkSlider(r, from_=v_min, to=v_max, number_of_steps=50, button_color="white",
                              progress_color=C_ACCENT, command=lambda x: self.force_update_preview())
            s.set(init)
            s.pack(side="left", fill="x", expand=True, padx=5)
            return s

        self.quality_slider = add_sl(ctrl_box, "Quality", 10, 100, 40)
        self.logo_slider = add_sl(ctrl_box, "Logo", 0.1, 2.0, 0.8)
        self.text_slider = add_sl(ctrl_box, "Text", 0.5, 2.0, 1.0)

        btn_box = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(0, 20))

        gen_row = ctk.CTkFrame(btn_box, fg_color="transparent")
        gen_row.pack(fill="x", pady=(0, 10))

        self.save_btn = ctk.CTkButton(gen_row, text="⚡  GENERATE", height=50, corner_radius=12,
                                       fg_color=C_ACCENT, font=F_HEADER, command=self.process_final)
        self.save_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(gen_row, text="⚙️", width=50, height=50, corner_radius=25, fg_color="#1A1A1A",
                      hover_color="#333", font=F_BTN, command=self.open_quicksave_settings).pack(side="right")

        sub_btns = ctk.CTkFrame(btn_box, fg_color="transparent")
        sub_btns.pack(fill="x")
        ctk.CTkButton(sub_btns, text="🎨 BG", width=60, height=40, fg_color="#333",
                      font=F_BTN, command=self.set_background).pack(side="left", padx=(0, 2))
        ctk.CTkButton(sub_btns, text="📜 History", width=90, height=40, fg_color="#222",
                      font=F_BTN, command=self.open_history).pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(sub_btns, text="📂 Open", width=90, height=40, fg_color="#222",
                      font=F_BTN, command=self.open_last_folder).pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(sub_btns, text="🗑️", width=50, height=40, fg_color="#222",
                      hover_color="#C62828", font=F_BTN, command=self.clear_all).pack(side="left", padx=2)
        ctk.CTkButton(sub_btns, text="📰 Tracker", width=90, height=40,
                      fg_color="#1A4A1A", hover_color="#1E6B1E",
                      font=F_BTN, command=self._open_tracker).pack(side="left", fill="x", expand=True, padx=2)
        ctk.CTkButton(sub_btns, text="🔍 Search", width=80, height=40,
                      fg_color="#1A1A3A", hover_color="#252550",
                      font=F_BTN, command=self.open_ocr_search).pack(side="left", padx=2)
        ctk.CTkButton(sub_btns, text="📄 PDF", width=70, height=40,
                      fg_color="#4A2A00", hover_color="#6B3D00",
                      font=F_BTN, command=self.open_pdf_bot).pack(side="left", padx=2)
        ctk.CTkButton(sub_btns, text="🔄", width=40, height=40,
                      fg_color="#1A3A3A", hover_color="#245050",
                      font=F_BTN, command=self.open_sync).pack(side="left", padx=2)
        ctk.CTkButton(sub_btns, text="📅 PDF for Today", width=110, height=40,
                      fg_color="#4A2A00", hover_color="#6B3D00",
                      font=F_BTN, command=self.open_pdf_bot_today).pack(side="left", padx=2)


        self.right_container = ctk.CTkFrame(tab_clip, fg_color=C_BG)
        self.right_container.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.toolbar = ctk.CTkFrame(self.right_container, height=56, fg_color="#0D0D14",
                                    corner_radius=14, border_width=1, border_color="#1E1E2E")
        self.toolbar.pack(fill="x", side="bottom", pady=10, padx=20)

        t_frame_1 = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        t_frame_1.pack(side="left", padx=5, pady=8)
        def t_btn(txt, cmd, col="#16161E", parent=t_frame_1, width=55):
            ctk.CTkButton(parent, text=txt, width=width, height=32, corner_radius=8,
                          fg_color=col, font=("Segoe UI", 10, "bold"),
                          hover_color="#1E1E2E", border_width=1, border_color="#2D2D3A",
                          command=cmd).pack(side="left", padx=2)

        t_btn("⌅ Paste", self.paste_image, C_ACCENT)
        t_btn("Trim", self.auto_trim)
        t_btn("Clean", self.remove_straight_lines)
        t_btn("Levels", self.open_levels_dialog)
        t_btn("Crisp", self.apply_sharpen)
        t_btn("2x UP", self.upscale_clips)
        t_btn("Pad", self.add_whitespace)
        t_btn("✂ Surgical", self.open_surgical_workspace, col="#1D4ED8")

        ctk.CTkLabel(t_frame_1, text="|", text_color="#444").pack(side="left", padx=3)
        t_btn("Up", self.move_clip_up, width=40)
        t_btn("Down", self.move_clip_down, width=40)
        t_btn("Merge", self.merge_side_by_side)

        self.action_frame = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        self.action_frame.pack(side="right", padx=5, pady=8)

        t_btn("⟳", self.redo, parent=self.action_frame, width=35)
        t_btn("⟲", self.undo, parent=self.action_frame, width=35)
        ctk.CTkLabel(self.action_frame, text="|", text_color="#444").pack(side="right", padx=5)

        self.redact_btn = ctk.CTkButton(self.action_frame, text="Redact", width=65, height=34, corner_radius=17,
                                         fg_color="#000000", text_color="white", font=F_BTN,
                                         command=lambda: self._apply_box_action("redact"))
        self.redact_btn.pack(side="right", padx=3)

        self.hl_btn = ctk.CTkButton(self.action_frame, text="Highlight", width=75, height=34, corner_radius=17,
                                     fg_color="#FBC02D", text_color="black", font=F_BTN,
                                     command=lambda: self._apply_box_action("highlight"))
        self.hl_btn.pack(side="right", padx=3)

        self.cut_btn = ctk.CTkButton(self.action_frame, text="Erase", width=60, height=34, corner_radius=17,
                                      fg_color="#D32F2F", font=F_BTN, command=lambda: self._apply_box_action("erase"))
        self.cut_btn.pack(side="right", padx=3)

        self.crop_btn = ctk.CTkButton(self.action_frame, text="Crop", width=60, height=34, corner_radius=17,
                                       fg_color=C_ACCENT, text_color="black", font=F_BTN,
                                       command=lambda: self._apply_box_action("crop"))
        self.crop_btn.pack(side="right", padx=3)
        self.canvas_frame = ctk.CTkFrame(self.right_container, fg_color="#08080E",
                                          corner_radius=12, border_width=1,
                                          border_color="#1A1A2E")
        self.canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.preview_canvas = Canvas(self.canvas_frame, bg="#000", highlightthickness=0,
                                     borderwidth=0, cursor="crosshair")
        self.preview_canvas.pack(fill="both", expand=True, padx=2, pady=2)
        self.preview_canvas.bind("<Configure>", self.on_canvas_resize)

        # ── Bubble notification (top-right corner of canvas) ─────────────────
        self._bubble_job    = None
        self._bubble_frame  = ctk.CTkFrame(
            self.canvas_frame,
            fg_color="#111827", corner_radius=12,
            border_width=1, border_color="#1F2937")
        self._bubble_frame.place(relx=0.99, rely=0.02, anchor="ne")
        self._bubble_frame.place_forget()   # hidden by default

        bubble_inner = ctk.CTkFrame(self._bubble_frame, fg_color="transparent")
        bubble_inner.pack(padx=10, pady=7)

        self._bubble_dot = ctk.CTkLabel(
            bubble_inner, text="●", font=("Consolas", 9),
            text_color="#6B7280", width=12)
        self._bubble_dot.pack(side="left", padx=(0, 6))

        self._bubble_text = ctk.CTkLabel(
            bubble_inner, text="READY",
            font=("Consolas", 11, "bold"), text_color="#9CA3AF")
        self._bubble_text.pack(side="left")

        self._bubble_bar = ctk.CTkProgressBar(
            self._bubble_frame, height=3, width=160,
            corner_radius=2, fg_color="#1F2937",
            progress_color="#3B82F6")
        self._bubble_bar.pack(fill="x", padx=10, pady=(0, 8))
        self._bubble_bar.set(0)
        self._bubble_bar.pack_forget()

        # Compat: self.status_label points to a proxy that updates the bubble
        self.status_label = _BubbleStatusProxy(self)

        # Batch tab is built last — it reads self.cat_tree, self.paper_var,
        # self.logo_slider etc., all of which exist by this point in setup_ui
        # but didn't when tab_batch was first created above.
        nab_batch_ui.build_batch_tab(self, tab_batch)

        # Feature 28: Live clip counter
        self.clip_counter_label = ctk.CTkLabel(self.canvas_frame, text="📎 0 clips",
                                                text_color="#444", font=("Consolas", 11), bg_color="#000")
        self.clip_counter_label.place(relx=0.02, rely=0.98, anchor="sw")

        self.preview_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.preview_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.preview_canvas.bind("<MouseWheel>", self.on_zoom)

        self.menu = Menu(self, tearoff=0)
        self.menu.add_command(label="Add Root Category", command=self.add_root_category)
        self.menu.add_command(label="Add Sub-category", command=self.add_sub_category)
        self.menu.add_command(label="Rename", command=self.rename_category)
        self.menu.add_separator()
        self.menu.add_command(label="Delete", command=self.delete_category, foreground="red")

        self.update_canvas_bg()

    def _update_clip_counter(self):
        count = len(self.session_history)
        goal_txt = f"/{self.daily_goal}" if self.daily_goal > 0 else ""
        self.clip_counter_label.configure(text=f"📎 {count}{goal_txt} clips", text_color="#666")

    def on_auto_polish_toggle(self):
        # BUG FIX: this is the "Auto Polish" feature. The background thread
        # previously had NO exception handling. If a single clip failed
        # inside _cv_auto_trim/_cv_remove_lines/_pad_image (malformed image,
        # OOM on a huge canvas, a degenerate contour, etc.) the whole
        # thread_target() died silently: finalize() never ran, orig_images
        # was never updated, and the status label was left stuck on
        # "POLISHING..." forever with no error shown — looking exactly like
        # the feature "not working." Each clip is now processed individually
        # with its own try/except so one bad image can't take down the rest,
        # and failures are reported to the user instead of hanging silently.
        if self.auto_polish_var.get() and self.orig_images:
            if getattr(self, '_polish_running', False):
                return  # re-entrancy guard: ignore rapid double-toggle
            self._polish_running = True
            self.save_state()
            self.status_label.configure(text="POLISHING...", text_color=C_ACCENT)
            self.update_idletasks()

            # FIX 2: Run polish in background thread properly
            def run_polish():
                new_origs = []
                failures = 0
                for img in self.orig_images:
                    try:
                        out = self._cv_auto_trim(img)
                        out = self._cv_remove_lines(out)
                        out = self._pad_image(out)
                        new_origs.append(out)
                    except Exception as e:
                        logging.error(f"on_auto_polish_toggle: {e}")
                        failures += 1
                        new_origs.append(img)  # keep original clip on failure
                return new_origs, failures

            def finalize(res, failures):
                self._polish_running = False
                self.orig_images = res
                self.proxy_images = [self.create_proxy(i) for i in self.orig_images]
                self.force_update_preview()
                if failures:
                    self.status_label.configure(
                        text=f"⚠️ Polished with {failures} failure(s)", text_color=C_DANGER)
                    messagebox.showwarning(
                        "Auto Polish — Partial Failure",
                        f"{failures} of {len(self.orig_images)} clip(s) could not be polished "
                        f"and were left unchanged.\nCheck nab_errors.log for details."
                    )
                else:
                    self.status_label.configure(text="POLISHED!", text_color=C_SUCCESS)
                self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

            def thread_target():
                try:
                    result, failures = run_polish()
                except Exception as e:
                    # Safety net in case something outside the per-clip loop throws
                    logging.error(f"on_auto_polish_toggle thread_target: {e}")
                    self.after(0, lambda e=e: [
                        setattr(self, '_polish_running', False),
                        self.status_label.configure(text="POLISH FAILED", text_color=C_DANGER),
                        messagebox.showerror("Auto Polish Failed", f"{e}\nCheck nab_errors.log for details."),
                    ])
                    return
                self.after(0, lambda: finalize(result, failures))

            threading.Thread(target=thread_target, daemon=True).start()

    def open_surgical_workspace(self):
        if not self.orig_images:
            if not getattr(self, 'workspace_instance', None) or not self.workspace_instance.winfo_exists():
                self.workspace_instance = SurgicalWorkspace(self, self.handle_surgical_commit)
            self.workspace_instance.lift()
            return
        self.save_state()
        img_to_edit = self.orig_images.pop()
        self.proxy_images.pop()
        # Keep clip_rects in sync when removing an image
        if self.clip_rects:
            self.clip_rects.pop()
        self.force_update_preview()
        if not getattr(self, 'workspace_instance', None) or not self.workspace_instance.winfo_exists():
            self.workspace_instance = SurgicalWorkspace(self, self.handle_surgical_commit)
        self.workspace_instance.paste_to_workspace(img_to_edit)
        self.workspace_instance.lift()

    def handle_surgical_commit(self, cropped_img):
        self.save_state()
        self.orig_images.append(cropped_img)
        self.proxy_images.append(self.create_proxy(cropped_img))
        # Add a correctly-sized clip_rect for the new cropped image.
        # Position it below all existing clips (same as default stack).
        self._ensure_offsets_synced()
        y = max((r['y'] + r['h'] for r in self.clip_rects), default=0)
        self.clip_rects.append({
            'x': 0, 'y': y,
            'w': cropped_img.width, 'h': cropped_img.height
        })
        self.force_update_preview()

    def open_global_settings(self):
        GlobalSettingsDialog(self, self.base_root, self.save_global_settings,
                             self.extra_settings, self.save_extra_settings)

    def save_global_settings(self, new_dir):
        self.base_root = new_dir
        self.save_settings()
        messagebox.showinfo("Success", "Global Settings Updated.")

    def save_extra_settings(self, extra):
        self.extra_settings.update(extra)
        self.save_settings()

    def open_quicksave_settings(self):
        cats = self.get_all_category_paths()
        QuickSaveSettingsDialog(self, self.quick_saves, cats, self.save_quicksave_settings)

    def get_all_category_paths(self):
        cats = []
        for p in self.cat_tree.get_children(""):
            p_text = self.cat_tree.item(p)['text']
            cats.append(p_text)
            for c in self.cat_tree.get_children(p):
                cats.append(f"{p_text}/{self.cat_tree.item(c)['text']}")
        return cats

    def save_quicksave_settings(self, new_map):
        self.quick_saves = new_map
        self.save_settings()
        self.setup_shortcuts()

    def open_url_mapping(self):
        MappingDialog(self, "Source URL/Title Mapping",
                      "Map browser titles or URLs to Newspaper sources.\nExample: 'daily star' -> '⭐ Daily Star'",
                      "Title/URL Fragment", "Newspaper", self.url_mappings, self.paper_list, self.save_url_mappings,
                      tester=lambda text, d: nab_clip_scan.explain_detection(text, d, self.paper_list))

    def save_url_mappings(self, new_map):
        self.url_mappings = new_map
        self.save_settings()
        # Force re-evaluation on the next monitor tick. Detection only
        # re-runs when the page text changes, so without this an edited
        # mapping did nothing until you happened to navigate somewhere.
        self.last_context = ""
        self._tab_locks.clear()   # a fresh mapping set starts from a clean slate

    def execute_quick_save(self, cat_path):
        if not cat_path or not self.orig_images: return
        # When a batch session is active, category hotkeys seal to the
        # batch instead of opening the metadata dialog — metadata is
        # entered later, all at once, in Review. Same hotkeys you already
        # know, different destination while batching.
        if getattr(self, '_batch_session', None):
            nab_batch_ui.seal_current_clip_with_category(self, cat_path)
            return
        # Ensure NAB is visible before showing dialog (handles Ctrl+S from mini overlay)
        if self.state() == 'iconic':
            self.deiconify()
            self.lift()
            self.update_idletasks()
        dialog = MultiInputDialog(self, self.last_page, self.last_pos, self.last_size)
        self.wait_window(dialog)
        if not dialog.result: return
        self.last_page, self.last_pos, self.last_size = dialog.result

        self.status_label.configure(text="QUICK SAVING...", text_color=C_ACCENT)
        parts = cat_path.split("/")
        force_header = False if any(x in ["Telecom", "Pride Group"] for x in parts) else True
        save_q = 95 if self.hd_mode_var.get() else int(self.quality_slider.get())
        canvas, _ = self.create_full_page(use_proxy=False, force_header_state=force_header)
        fd = os.path.join(self.base_root, self.current_date.strftime("%Y"),
                          self.current_date.strftime("%B"), self.current_date.strftime("%d-%m-%Y"), *parts)
        if not os.path.exists(fd): os.makedirs(fd, exist_ok=True)
        paper = strip_emoji_prefix(self.paper_combo.get())
        fname = f"{paper}, Page-{self.last_page}, Pos-{self.last_pos}, S-{self.last_size}, Date-{self.current_date.strftime('%d-%m-%Y')}.jpg"
        full_path = os.path.join(fd, fname)

        # Feature 29: Check duplicate before saving
        if self._check_duplicate(fd, fname):
            answer = messagebox.askyesno("Duplicate Detected",
                                          f"This exact file already exists:\n{fname}\n\nSave with a new name?")
            if not answer:
                self.status_label.configure(text="SAVE CANCELLED (DUPLICATE)", text_color=C_DANGER)
                return
            # Re-open metadata dialog for new name
            dialog2 = MultiInputDialog(self, self.last_page, f"{self.last_pos}_2", self.last_size)
            self.wait_window(dialog2)
            if dialog2.result:
                self.last_page, self.last_pos, self.last_size = dialog2.result
                fname = f"{paper}, Page-{self.last_page}, Pos-{self.last_pos}, S-{self.last_size}, Date-{self.current_date.strftime('%d-%m-%Y')}.jpg"
                full_path = os.path.join(fd, fname)

        def save_and_finish():
            canvas.save(full_path, "JPEG", quality=save_q, optimize=True, subsampling=0)
            self._check_file_size(full_path)
            self.after(0, lambda: self.finish_quick_save(full_path, cat_path))

        threading.Thread(target=save_and_finish, daemon=True).start()

    def finish_quick_save(self, path, cat):
        self.session_history.append({"path": path, "category": cat,
                                     "time": datetime.datetime.now().strftime("%H:%M:%S")})
        # BUG FIX: quick-save (hotkey single-category save) never updated
        # last_saved_path, so "Open Folder" only worked after a batch save
        # via the main Generate button. It now works consistently everywhere.
        self.last_saved_path = os.path.dirname(path)
        self.last_active_date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.status_label.configure(text="COMPLETED!", text_color=C_SUCCESS)
        self._update_clip_counter()
        self._check_goal()
        self.clear_all()
        self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    def show_cat_settings(self):
        x = self.cat_settings_btn.winfo_rootx()
        y = self.cat_settings_btn.winfo_rooty() + self.cat_settings_btn.winfo_height()
        self.menu.post(x, y)

    def _clear_selection(self):
        self.preview_canvas.delete("tool_rect")
        self.rect_id = None

    def set_background(self):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if p:
            try:
                shutil.copy(p, self.bg_file)
                self.raw_bg_image = Image.open(self.bg_file).convert("RGBA")
                self.update_canvas_bg()
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}")

    def on_canvas_resize(self, event):
        if abs(event.width - getattr(self, 'last_canvas_width', 0)) > 50 or \
           abs(event.height - getattr(self, 'last_canvas_height', 0)) > 50:
            self.last_canvas_width = event.width
            self.last_canvas_height = event.height
            if getattr(self, '_bg_job', None):
                self.after_cancel(self._bg_job)
            self._bg_job = self.after(50, self.update_canvas_bg)
            self.force_update_preview()

    def update_canvas_bg(self):
        if self.raw_bg_image:
            w = self.preview_canvas.winfo_width()
            h = self.preview_canvas.winfo_height()
            if w > 10 and h > 10:
                self.bg_image_ref = create_dimmed_bg(self.raw_bg_image, w, h)
                self.preview_canvas.delete("bg_layer")
                if self.bg_image_ref:
                    self.preview_canvas.create_image(0, 0, image=self.bg_image_ref, anchor="nw", tags="bg_layer")
                    self.preview_canvas.tag_lower("bg_layer")
        self.preview_canvas.delete("placeholder_text")
        if not self.orig_images:
            w = self.preview_canvas.winfo_width()
            h = self.preview_canvas.winfo_height()
            self.preview_canvas.create_text(w // 2, h // 2, text="PASTE (Ctrl+V)", fill="#555",
                                            font=("Arial", 20, "bold"), tags="placeholder_text")

    def reset_view(self):
        self.user_zoom = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0

    def open_calendar(self):
        top = ctk.CTkToplevel(self)
        top.title("Select Date")
        nab_ui_scale.fit(top, 300, 300, parent=self)
        top.configure(fg_color=C_BG)
        top.attributes('-topmost', True)
        if HAS_CALENDAR:
            cal = Calendar(top, selectmode='day', year=self.current_date.year,
                           month=self.current_date.month, day=self.current_date.day, date_pattern='dd-mm-yyyy')
            cal.pack(pady=20, fill="both", expand=True, padx=10)
            def set_date():
                self.current_date = datetime.datetime.strptime(cal.get_date(), '%d-%m-%Y')
                self.date_btn.configure(text=f"📅 {self.current_date.strftime('%Y-%m-%d')}")
                self.force_update_preview()
                top.destroy()
            ctk.CTkButton(top, text="Confirm Date", command=set_date, fg_color=C_ACCENT, height=40).pack(pady=10, padx=20, fill="x")
        else:
            ctk.CTkLabel(top, text="Enter Date (DD-MM-YYYY)", text_color="white").pack(pady=10)
            e = ctk.CTkEntry(top, placeholder_text="DD-MM-YYYY")
            e.insert(0, self.current_date.strftime('%d-%m-%Y'))
            e.pack(pady=5, padx=20)
            def manual_set():
                try:
                    self.current_date = datetime.datetime.strptime(e.get(), '%d-%m-%Y')
                    self.date_btn.configure(text=f"📅 {self.current_date.strftime('%Y-%m-%d')}")
                    self.force_update_preview()
                    top.destroy()
                except: messagebox.showerror("Error", "Invalid Date Format")
            ctk.CTkButton(top, text="Set Date", command=manual_set, fg_color=C_ACCENT).pack(pady=10)

    def load_sources(self):
        default = ["⭐ Daily Star", "📊 TBS", "💹 Financial Express", "👁️ Daily Observer",
                   "🇧🇩 Dhaka Tribune", "📰 New Age", "☀️ Daily Sun", "🌍 New Nation",
                   "🏛️ Asian Age", "🇧🇩 Bangladesh Today", "📜 TOB", "🌅 Prothom Alo",
                   "🕒 Samakal", "🗳️ Ittefaq", "🏹 Jugantor", "🗣️ Kaler Kantha",
                   "🏛️ Janakantha", "🕌 Naya Diganta", "🖋️ Daily Inqilab", "💼 Bonik Barta",
                   "🇧🇩 Bangladesh Pratidin", "📰 Sangbad", "📅 Jaijaidin", "👤 Manabzamin",
                   "⏰ Amader Shomoy", "📈 Sharebiz", "📅 Ajker Patrika",
                   "🇧🇩 Protidiner Bangladesh", "💡 Shomoyer Alo", "🗞️ Pratidiner Sangbad",
                   "🏙️ Desh Rupantor", "🔔 Kalbela", "🇧🇩 Rupali Bangladesh",
                   "📖 Khoborer Kagoj", "📰 Amardesh", "💡 Alokito Bangladesh"]
        if os.path.exists(self.sources_file):
            try:
                with open(self.sources_file, 'r') as f:
                    self.paper_list = json.load(f)
            except: self.paper_list = default
        else: self.paper_list = default
        self.paper_combo.configure(values=self.paper_list)
        if self.paper_list: self.paper_combo.set(self.paper_list[0])

    def save_sources(self, new_list=None):
        if new_list is not None:
            self.paper_list = new_list
            self.paper_combo.configure(values=self.paper_list)
            if self.paper_list: self.paper_combo.set(self.paper_list[0])
        try:
            with open(self.sources_file, 'w') as f:
                json.dump(self.paper_list, f)
        except: pass

    def auto_select_category_from_path(self, cat_path):
        parts = cat_path.split("/")
        root_nodes = self.cat_tree.get_children("")
        for node in root_nodes:
            if self.cat_tree.item(node)['text'] == parts[0]:
                if len(parts) == 1:
                    self.cat_tree.selection_set(node)
                    return
                for child in self.cat_tree.get_children(node):
                    if self.cat_tree.item(child)['text'] == parts[1]:
                        self.cat_tree.selection_set(child)
                        self.cat_tree.see(child)
                        return

    def on_cat_change(self, e):
        sel = self.cat_tree.selection()
        if not sel: return
        txt = self.cat_tree.item(sel[0])['text']
        prnt = self.cat_tree.item(self.cat_tree.parent(sel[0]))['text'] if self.cat_tree.parent(sel[0]) else ""
        if any(x in ["Telecom", "Pride Group"] for x in [txt, prnt]):
            self.show_text_var.set(False)
        else:
            self.show_text_var.set(True)
        # Feature 14: Show batch mode hint
        if self.extra_settings.get("batch_save_enabled") and len(self.cat_tree.selection()) > 1:
            self.batch_mode_label.configure(text=f"[BATCH: {len(self.cat_tree.selection())}]")
        else:
            self.batch_mode_label.configure(text="")
        self.force_update_preview()

    def load_categories(self):
        default_cats = {
            "BAT": [],
            "Beximco": ["Bank", "Beximco Group", "Capital Market", "Ceramics", "DTH",
                        "Economy", "Finance", "Loan", "Pharma Industry", "Mr.Salman F Rahman", "NOAB"],
            "Mineral": ["LNG", "LPG", "Power"],
            "Pride Group": [],
            "Telecom": ["GP", "Robi", "BL", "TT", "Industry"],
            "United Group": ["United Finance", "United Healthcare", "United Power", "United Group", "UIU"],
            "Xiaomi": []
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    default_cats = json.load(f)
            except: pass
        for item in self.cat_tree.get_children(): self.cat_tree.delete(item)
        colors = ["#1A237E", "#283593", "#303F9F", "#3949AB", "#3F51B5"]
        i = 0
        for p, subs in default_cats.items():
            color = colors[i % len(colors)]
            tag_name = f"root_{i}"
            self.cat_tree.tag_configure(tag_name, background=color, foreground="white")
            node = self.cat_tree.insert("", "end", text=p, open=True, tags=(tag_name,))
            for s in subs: self.cat_tree.insert(node, "end", text=s)
            i += 1

    def _rebuild_default_offsets(self):
        """Rebuild clip_rects from scratch as a centered vertical stack,
        matching _get_stitched_clips()'s layout. Called after any operation
        that changes the clip list wholesale (paste, reorder, upscale) where
        prior positions are no longer meaningful."""
        self.clip_rects = []
        if not self.orig_images:
            return
        mw = max(img.width for img in self.orig_images)
        y = 0
        for img in self.orig_images:
            self.clip_rects.append({
                'x': (mw - img.width) // 2,
                'y': y,
                'w': img.width,
                'h': img.height,
            })
            y += img.height

    def _ensure_offsets_synced(self):
        """Make sure clip_rects has exactly one entry per orig_image without
        discarding entries that are already correct. Appends default-position
        entries for any images missing one; trims extras."""
        if len(self.clip_rects) > len(self.orig_images):
            self.clip_rects = self.clip_rects[:len(self.orig_images)]
            return
        if len(self.clip_rects) == len(self.orig_images):
            return
        mw = max((img.width for img in self.orig_images), default=0)
        y = max((r['y'] + r['h'] for r in self.clip_rects), default=0)
        for img in self.orig_images[len(self.clip_rects):]:
            self.clip_rects.append({
                'x': max(0, (mw - img.width) // 2), 'y': y,
                'w': img.width, 'h': img.height,
            })
            y += img.height

    def _sync_clip_rects_to_images(self):
        """After any crop/trim/resize operation, make sure clip_rects w/h
        match the actual pixel dimensions of each orig_image.
        This prevents stretched rendering when an image shrinks after a crop
        but clip_rects still holds the old larger dimensions."""
        if not self.orig_images:
            return
        self._ensure_offsets_synced()
        changed = False
        for i, img in enumerate(self.orig_images):
            r = self.clip_rects[i]
            if r['w'] != img.width or r['h'] != img.height:
                # Preserve position, update size to actual image size
                r['w'] = img.width
                r['h'] = img.height
                changed = True
        return changed

    def force_update_preview(self):
        # Always sync clip_rects dimensions to actual image sizes before
        # rendering — catches any crop/trim/pad that changed image dimensions
        self._sync_clip_rects_to_images()
        self.cached_full_img = None
        if getattr(self, '_preview_job', None):
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(15, self._render_and_broadcast)

    def _render_and_broadcast(self):
        """Render the preview then broadcast the updated canvas to the
        Chrome extension (via WebSocket) and refresh the mini-window."""
        self.render_preview()
        # Broadcast to Chrome extension
        try:
            if self.orig_images and getattr(self, 'preview_server', None):
                merged = self._get_stitched_clips(use_proxy=True)
                self.preview_server.broadcast(
                    merged,
                    clip_count=len(self.orig_images),
                    last_action=getattr(self, '_last_broadcast_action', ''),
                )
                self._last_broadcast_action = ''
        except Exception as e:
            logging.error(f"_render_and_broadcast: {e}")

    def on_zoom(self, event):
        if not self.display_image: return
        zoom_factor = 1.15 if event.delta > 0 else 1 / 1.15
        new_zoom = self.user_zoom * zoom_factor
        if new_zoom < 0.1 or new_zoom > 10.0: return
        c_w = self.preview_canvas.winfo_width()
        c_h = self.preview_canvas.winfo_height()
        mouse_offset_x = event.x - (c_w // 2) - self.pan_offset_x
        mouse_offset_y = event.y - (c_h // 2) - self.pan_offset_y
        self._clear_selection()
        self.user_zoom = new_zoom
        self.pan_offset_x -= mouse_offset_x * (zoom_factor - 1)
        self.pan_offset_y -= mouse_offset_y * (zoom_factor - 1)
        self.update_canvas_render_only()

    def process_final(self):
        if not self.orig_images: messagebox.showwarning("ERR", "EMPTY"); return
        selections = self.cat_tree.selection()
        if not selections: messagebox.showwarning("ERR", "SELECT CATEGORY"); return
        # Ensure NAB is visible before showing dialog (handles Ctrl+S from mini overlay)
        if self.state() == 'iconic':
            self.deiconify()
            self.lift()
            self.update_idletasks()
        dialog = MultiInputDialog(self, self.last_page, self.last_pos, self.last_size)
        self.wait_window(dialog)
        if not dialog.result: return
        self.last_page, self.last_pos, self.last_size = dialog.result
        self.status_label.configure(text="PARALLEL SAVING...", text_color=C_ACCENT)
        # BUG FIX: snapshot every bit of Tkinter/CTk widget state HERE, on the
        # main thread, before handing off to background worker threads.
        # _save_single_category used to call self.create_full_page() (which
        # reads self.paper_combo.get(), self.logo_slider.get(),
        # self.text_slider.get(), self.show_text_var.get()) from inside a
        # ThreadPoolExecutor worker. Tkinter/Tcl is NOT thread-safe — reading
        # widget state off the main thread is a classic source of intermittent
        # crashes, blank/corrupted canvases, or saves that silently fail. When
        # a save silently failed, last_saved_path was never updated, which is
        # exactly why "Open Folder" looked broken — there was nothing to open.
        save_ctx = {
            "paper": strip_emoji_prefix(self.paper_combo.get()),
            "save_q": 95 if self.hd_mode_var.get() else int(self.quality_slider.get()),
            "logo_scale": self.logo_slider.get(),
            "text_scale": self.text_slider.get(),
            "show_header": self.show_text_var.get(),
        }
        threading.Thread(target=self.save_in_background, args=(selections, save_ctx), daemon=True).start()

    def _save_single_category(self, sel, save_ctx):
        itm = self.cat_tree.item(sel)['text']
        prnt_node = self.cat_tree.parent(sel)
        prnt = self.cat_tree.item(prnt_node)['text'] if prnt_node else ""
        parts = [prnt, itm] if prnt else [itm]
        force_header = False if any(x in ["Telecom", "Pride Group"] for x in [itm, prnt]) else True
        if not force_header:
            show_header = False
        else:
            show_header = save_ctx["show_header"]

        # BUG FIX: create_full_page_threadsafe takes plain values captured on
        # the main thread instead of reading live CTk widgets here.
        canvas, _ = self.create_full_page_threadsafe(
            use_proxy=False,
            show_header=show_header,
            paper=save_ctx["paper"],
            logo_scale=save_ctx["logo_scale"],
            text_scale=save_ctx["text_scale"],
        )
        fd = os.path.join(self.base_root, self.current_date.strftime("%Y"),
                          self.current_date.strftime("%B"), self.current_date.strftime("%d-%m-%Y"), *parts)
        if not os.path.exists(fd): os.makedirs(fd, exist_ok=True)

        paper = save_ctx["paper"]
        fname = f"{paper}, Page-{self.last_page}, Pos-{self.last_pos}, S-{self.last_size}, Date-{self.current_date.strftime('%d-%m-%Y')}.jpg"
        full_path = os.path.join(fd, fname)

        canvas.save(full_path, "JPEG", quality=save_ctx["save_q"], optimize=True, subsampling=0, qtables="web_high")
        self._check_file_size(full_path)
        return {"path": full_path, "category": "/".join(parts),
                "time": datetime.datetime.now().strftime("%H:%M:%S")}, fd

    def save_in_background(self, selections, save_ctx):
        saved_files_info = []
        last_dir = ""
        failures = 0
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self._save_single_category, sel, save_ctx) for sel in selections]
            for future in concurrent.futures.as_completed(futures):
                try:
                    info, d = future.result()
                    saved_files_info.append(info)
                    last_dir = d
                except Exception as e:
                    failures += 1
                    logging.error(f"save_in_background: {e}")
        self.last_saved_path = last_dir
        # BUG FIX: surface failures to the user instead of failing silently.
        # Previously, if every single category save threw an exception,
        # last_saved_path stayed "" and finish_saving() ran anyway showing
        # "COMPLETED!" — the user had no idea nothing was actually saved.
        if failures and not saved_files_info:
            self.after(0, lambda: messagebox.showerror(
                "Save Failed",
                f"All {failures} categor{'y' if failures == 1 else 'ies'} failed to save.\n"
                f"Check nab_errors.log for details."
            ))
            self.after(0, lambda: self.status_label.configure(text="SAVE FAILED", text_color=C_DANGER))
            return
        if failures:
            self.after(0, lambda: messagebox.showwarning(
                "Partial Save",
                f"{failures} of {len(selections)} categories failed to save.\n"
                f"Check nab_errors.log for details."
            ))
        self.after(0, lambda: self.finish_saving(saved_files_info))

    def finish_saving(self, saved_files):
        self.session_history.extend(saved_files)
        self.last_active_date = datetime.datetime.now().strftime("%Y-%m-%d")
        self.status_label.configure(text="COMPLETED!", text_color=C_SUCCESS)
        self.last_pos = ""
        self.hd_mode_var.set(False)
        self.show_text_var.set(True)
        self._update_clip_counter()
        self._check_goal()
        self.clear_all()
        self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    def _get_stitched_clips(self, use_proxy=False):
        """Stack all clips into one centered vertical strip (white background).
        This is the pre-header, pre-logo 'raw' merged image."""
        source_list = self.proxy_images if use_proxy else self.orig_images
        if not source_list:
            return Image.new('RGB', (100, 100), 'white')
        ws, hs = zip(*(i.size for i in source_list))
        mw, total_h = max(ws), sum(hs)
        merged = Image.new('RGB', (mw, total_h), (255, 255, 255))
        y = 0
        for img in source_list:
            merged.paste(img, ((mw - img.size[0]) // 2, y))
            y += img.size[1]
        return merged

    def _build_full_page(self, use_proxy, show_header, paper, logo_scale, text_scale,
                         warn_missing_logo=False):
        """Shared page-compositing logic: stitched clips + paper logo + header
        text. Takes plain values only (no live widget reads) so it's safe to
        call from a background thread. Returns (canvas, header_height).

        warn_missing_logo: only set True from an actual SAVE path (not the
        live preview, which calls this on nearly every keystroke/slider drag
        — warning there would just spam the status bubble). When set and no
        logo file matches `paper` in either folder, self._flag_missing_logo
        is scheduled on the main thread so the operator finds out at the
        moment it matters, instead of only noticing on a printed page."""
        merged = self._get_stitched_clips(use_proxy)
        final_mw = max(merged.width, 400)
        # Writable dir first (user-added/overridden logos persist across
        # updates there), fall back to the read-only logos bundled inside
        # the EXE itself.
        lp = os.path.join(self.logo_dir, f"{paper}.png")
        if not os.path.exists(lp):
            lp = os.path.join(self.logo_dir_bundled, f"{paper}.png")
            if warn_missing_logo and not os.path.exists(lp) and paper:
                self.after(0, lambda p=paper: self._flag_missing_logo(p))
        logo_img = None
        if os.path.exists(lp):
            try:
                temp_logo = Image.open(lp)
                tw = int(final_mw * logo_scale)
                th = int(temp_logo.height * (tw / temp_logo.width))
                logo_img = temp_logo.resize(
                    (tw, th),
                    Image.Resampling.BILINEAR if use_proxy else Image.Resampling.LANCZOS)
            except Exception:
                pass
        lh = logo_img.size[1] if logo_img else 40
        fs = max(12, int((final_mw * 0.03) * text_scale))
        hh = lh + fs + 25 if show_header else lh + 15
        canvas = Image.new('RGB', (final_mw, merged.height + hh + 10), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        if logo_img:
            canvas.paste(logo_img, ((final_mw - logo_img.size[0]) // 2, 10))
        if show_header:
            info = f"Page-{self.last_page}, Pos-{self.last_pos}, Date-{self.current_date.strftime('%d-%m-%Y')}"
            try:
                font = ImageFont.truetype("arialbd.ttf", fs)
            except Exception:
                font = ImageFont.load_default()
            tw = draw.textbbox((0, 0), info, font=font)[2]
            draw.text(((final_mw - tw) // 2, lh + 12), info, fill="black", font=font)
        canvas.paste(merged, ((final_mw - merged.width) // 2, hh))
        return canvas, hh

    def create_full_page(self, use_proxy=False, force_header_state=None):
        """Main-thread version — reads live CTk widget values directly.
        Do not call this from a background thread; use
        create_full_page_threadsafe() instead."""
        paper = strip_emoji_prefix(self.paper_combo.get())
        show_header = force_header_state if force_header_state is not None else self.show_text_var.get()
        return self._build_full_page(
            use_proxy=use_proxy,
            show_header=show_header,
            paper=paper,
            logo_scale=self.logo_slider.get(),
            text_scale=self.text_slider.get(),
            warn_missing_logo=not use_proxy,   # proxy calls are live preview
        )

    def create_full_page_threadsafe(self, use_proxy=False, show_header=None, paper=None,
                                     logo_scale=None, text_scale=None):
        """Background-thread-safe version — takes plain values captured on
        the main thread instead of reading live CTk widgets here."""
        return self._build_full_page(
            use_proxy=use_proxy,
            show_header=bool(show_header),
            paper=paper,
            logo_scale=logo_scale,
            text_scale=text_scale,
            warn_missing_logo=not use_proxy,
        )

    def _flag_missing_logo(self, paper):
        """Non-blocking warning shown in the status bubble when a save just
        went out with no logo for `paper` — doesn't stop the save (a missing
        logo isn't worth losing a clip over), just makes sure it's noticed
        immediately rather than discovered later on a printed page."""
        try:
            self.status_label.configure(
                text=f"⚠ NO LOGO FOR: {paper.upper()}", text_color="#F59E0B")
            self.after(3500, lambda: self.status_label.configure(
                text="READY", text_color=C_TEXT_DIM))
        except Exception as e:
            logging.error(f"_flag_missing_logo: {e}")

    def create_proxy(self, img):
        """Downscale for preview. Uses NEAREST for speed — quality doesn't
        matter here since this is display-only, never saved."""
        if img.height <= self.PROXY_HEIGHT:
            return img  # already small enough — no copy needed
        ratio = self.PROXY_HEIGHT / img.height
        nw    = max(1, int(img.width * ratio))
        # NEAREST is 3-4x faster than BILINEAR for proxy generation
        return img.resize((nw, self.PROXY_HEIGHT), Image.Resampling.NEAREST)

    def render_preview(self):
        if not self.proxy_images:
            self.update_canvas_bg()
            self.preview_canvas.delete("img")
            return
        if not self.cached_full_img:
            self.cached_full_img, self.header_offset = self.create_full_page(
                use_proxy=True, force_header_state=self.show_text_var.get())
        self._execute_canvas_render()

    def update_canvas_render_only(self):
        if getattr(self, '_render_job', None):
            self.after_cancel(self._render_job)
        self._render_job = self.after(15, self._execute_canvas_render)

    def _execute_canvas_render(self):
        if not self.cached_full_img: return
        c_w = self.preview_canvas.winfo_width()
        c_h = self.preview_canvas.winfo_height()
        if c_w < 10 or c_h < 10: return
        i_w, i_h = self.cached_full_img.size
        self.fit_scale = min(c_w / i_w, c_h / i_h)
        final_scale = self.fit_scale * self.user_zoom
        new_size = (max(1, int(i_w * final_scale)), max(1, int(i_h * final_scale)))
        resized = self.cached_full_img.resize(new_size, Image.Resampling.BILINEAR)
        self.display_image = ImageTk.PhotoImage(resized)
        draw_x = ((c_w - new_size[0]) // 2) + self.pan_offset_x
        draw_y = ((c_h - new_size[1]) // 2) + self.pan_offset_y
        self.img_draw_x = draw_x
        self.img_draw_y = draw_y
        self.current_render_scale = final_scale
        prev_key = getattr(self, '_last_render_key', None)
        curr_key = (new_size[0], new_size[1], draw_x, draw_y, id(self.cached_full_img))
        if prev_key != curr_key:
            resized = self.cached_full_img.resize(new_size, Image.Resampling.BILINEAR)
            self.display_image    = ImageTk.PhotoImage(resized)
            self._last_render_key = curr_key
        if self.preview_canvas.find_withtag("img"):
            self.preview_canvas.itemconfig("img", image=self.display_image)
            self.preview_canvas.coords("img", draw_x, draw_y)
        else:
            self.preview_canvas.create_image(draw_x, draw_y, image=self.display_image,
                                             anchor="nw", tags="img")
        if self.rect_id:
            self.preview_canvas.tag_raise("tool_rect")

    def _pan_canvas_image_only(self):
        if not self.cached_full_img or not self.display_image: return
        i_w, i_h = self.cached_full_img.size
        new_w = max(1, int(i_w * self.current_render_scale))
        new_h = max(1, int(i_h * self.current_render_scale))
        c_w = self.preview_canvas.winfo_width()
        c_h = self.preview_canvas.winfo_height()
        draw_x = ((c_w - new_w) // 2) + self.pan_offset_x
        draw_y = ((c_h - new_h) // 2) + self.pan_offset_y
        self.img_draw_x = draw_x
        self.img_draw_y = draw_y
        if self.preview_canvas.find_withtag("img"):
            self.preview_canvas.coords("img", draw_x, draw_y)

    # ── Free-transform layout helpers ─────────────────────────────────────────

    def _cv_remove_lines(self, img):
        """Smart border removal — two strategies:
        A) Strip uniform-colour edge borders (never cuts into text).
        B) Remove thin line contours at the image edge only."""
        if not HAS_CV: return img
        arr = np.array(img.convert("RGB"))
        h, w = arr.shape[:2]

        # Strategy A: uniform colour border strips
        max_strip = min(20, int(min(h, w) * 0.04))
        tol = 18
        top = bot = left = right = 0
        for i in range(max_strip):
            if arr[i].max(axis=0).max() - arr[i].min(axis=0).max() <= tol: top = i+1
            else: break
        for i in range(max_strip):
            if arr[h-1-i].max(axis=0).max() - arr[h-1-i].min(axis=0).max() <= tol: bot = i+1
            else: break
        for i in range(max_strip):
            col = arr[:, i]
            if col.max(axis=0).max() - col.min(axis=0).max() <= tol: left = i+1
            else: break
        for i in range(max_strip):
            col = arr[:, w-1-i]
            if col.max(axis=0).max() - col.min(axis=0).max() <= tol: right = i+1
            else: break
        if top or bot or left or right:
            arr = arr[top: h-bot if bot else h,
                      left: w-right if right else w]
            h, w = arr.shape[:2]

        # Strategy B: thin contour lines at image edge
        img_bgr = arr[:, :, ::-1].copy()
        gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        ex = max(6, int(w * 0.04))
        ey = max(6, int(h * 0.04))
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            is_h = cw > 60 and ch <= 10 and cw > ch * 10
            is_v = ch > 60 and cw <= 10 and ch > cw * 10
            if not (is_h or is_v): continue
            at_edge = (x <= ex or x+cw >= w-ex or
                       y <= ey or y+ch >= h-ey)
            if at_edge:
                cv2.rectangle(img_bgr,
                    (max(0,x-1), max(0,y-1)),
                    (min(w,x+cw+1), min(h,y+ch+1)),
                    (255,255,255), -1)
        return Image.fromarray(img_bgr[:, :, ::-1])

    def _cv_auto_trim(self, img):
        bg = Image.new(img.mode, img.size, img.getpixel((0, 0)))
        diff = ImageChops.difference(img, bg)
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bbox = diff.getbbox()
        if bbox:
            pad = 10
            x1, y1 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
            x2, y2 = min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad)
            return img.crop((x1, y1, x2, y2))
        return img

    def _pad_image(self, img):
        new_im = Image.new("RGB", (img.width + 30, img.height + 30), (255, 255, 255))
        new_im.paste(img, (15, 15))
        return new_im

    def apply_sharpen(self):
        if not self.orig_images: return
        self.save_state()
        processed = []
        for img in self.orig_images:
            img = ImageEnhance.Sharpness(img).enhance(2.0)
            img = ImageEnhance.Contrast(img).enhance(1.1)
            processed.append(img)
        self.orig_images = processed
        self.proxy_images = [self.create_proxy(i) for i in processed]
        self.force_update_preview()

    def _process_single_pasted_image(self, img, do_polish=False):
        # BUG FIX: wrap the polish step so a single problematic clip can't
        # raise out of executor.map() and silently abort the entire paste
        # batch (which left the status label stuck on "PROCESSING..." with
        # no feedback — the same failure mode that made Auto Polish look
        # broken). On failure we fall back to the unpolished image.
        if do_polish:
            try:
                img = self._cv_auto_trim(img)
                img = self._cv_remove_lines(img)
                img = self._pad_image(img)
            except Exception as e:
                logging.error(f"_process_single_pasted_image (auto-polish): {e}")
        proxy = self.create_proxy(img)
        return img, proxy

    def paste_image(self, provided_img=None):
        try:
            self.preview_canvas.focus_set()
            time.sleep(0.05)
            img_data = provided_img
            if img_data is None:
                for _ in range(3):
                    try:
                        img_data = _grab_clipboard_windows()
                        if img_data is None:
                            # _grab_clipboard_windows() already tried the DIB
                            # fallback; None here means either an empty
                            # clipboard or file-path content (handled below),
                            # not a transient failure — but retry briefly in
                            # case the clipboard is still being written to by
                            # the source app (e.g. Snipping Tool).
                            img_data = ImageGrab.grabclipboard()
                        break
                    except:
                        time.sleep(0.1)
                        img_data = None
                if img_data is None:
                    try:
                        txt = self.clipboard_get()
                        if os.path.exists(txt): img_data = [txt]
                        elif "\n" in txt:
                            lines = txt.splitlines()
                            if os.path.exists(lines[0].strip('"')):
                                img_data = [l.strip('"') for l in lines]
                    except: pass
            new_origs = []
            if isinstance(img_data, Image.Image):
                new_origs.append(img_data.convert("RGB"))
            elif isinstance(img_data, list):
                for f in img_data:
                    if os.path.isfile(f):
                        try: new_origs.append(ImageOps.exif_transpose(Image.open(f)).convert("RGB"))
                        except: pass
            if new_origs:
                self.save_state()
                if not self.orig_images: self.reset_view()
                self.status_label.configure(text="PROCESSING...", text_color=C_ACCENT)
                self.update_idletasks()
                do_polish = getattr(self, 'auto_polish_var', ctk.BooleanVar(value=False)).get()
                def run_parallel_cv():
                    try:
                        results = [self._process_single_pasted_image(i, do_polish) for i in new_origs]
                        p_origs   = [r[0] for r in results]
                        p_proxies = [r[1] for r in results]
                        self.after(0, lambda: self._finalize_paste(p_origs, p_proxies))
                    except Exception as e:
                        logging.error(f"run_parallel_cv: {e}")
                        self.after(0, lambda: self.status_label.configure(
                            text="PASTE FAILED", text_color=C_DANGER))
                threading.Thread(target=run_parallel_cv, daemon=True).start()
            else:
                if provided_img is None:
                    self.status_label.configure(text="CLIPBOARD EMPTY", text_color=C_DANGER)
        except Exception as e:
            logging.error(f"paste_image: {e}")
            self.status_label.configure(text="ERROR", text_color=C_DANGER)

    def _finalize_paste(self, p_origs, p_proxies):
        self.orig_images.extend(p_origs)
        self.proxy_images.extend(p_proxies)
        self._rebuild_default_offsets()
        n = len(self.orig_images)
        self.status_label.configure(text=f"PASTED! ({n} clip{'s' if n!=1 else ''})",
                                     text_color=C_ACCENT)
        self.notify_snatch(f"Clip added ({n} total)")
        self.force_update_preview()
        self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    def move_clip_up(self):
        if len(self.orig_images) < 2: return
        self.save_state()
        self.orig_images.insert(-1, self.orig_images.pop())
        self.proxy_images.insert(-1, self.proxy_images.pop())
        # Rebuild vertical-stack offsets after reorder
        self._rebuild_default_offsets()
        self.force_update_preview()

    def move_clip_down(self):
        if len(self.orig_images) < 2: return
        self.save_state()
        self.orig_images.append(self.orig_images.pop(-2))
        self.proxy_images.append(self.proxy_images.pop(-2))
        self._rebuild_default_offsets()
        self.force_update_preview()

    def open_levels_dialog(self):
        full = self.create_merged_clips()
        if not full: return
        def apply_callback(modified_img):
            self.save_state()
            self.orig_images = [modified_img]
            self.proxy_images = [self.create_proxy(modified_img)]
            self.force_update_preview()
        LevelsDialog(self, full, apply_callback)

    def upscale_clips(self):
        """2x LANCZOS upscale + unsharp mask for crisp output."""
        if not self.orig_images: return
        self.save_state()
        self.status_label.configure(text="UPSCALING…", text_color=C_ACCENT)
        self.update_idletasks()
        def _do():
            result = []
            for img in self.orig_images:
                up = img.resize((img.width*2, img.height*2), Image.Resampling.LANCZOS)
                up = up.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
                result.append(up)
            self.after(0, lambda r=result: self._finish_upscale(r))
        threading.Thread(target=_do, daemon=True).start()

    def _finish_upscale(self, upscaled):
        self.orig_images  = upscaled
        self.proxy_images = [self.create_proxy(img) for img in upscaled]
        self._rebuild_default_offsets()
        self.status_label.configure(text="UPSCALED 2x", text_color=C_SUCCESS)
        self.force_update_preview()
        self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    def remove_straight_lines(self):
        # BUG FIX: this is the "Clean Lines" feature. Previously, any exception
        # raised by _cv_remove_lines() on ANY single clip (e.g. an unusual
        # image, a malformed contour, an out-of-memory condition on a very
        # large canvas) propagated up unhandled. Because NAB.pyw runs as a
        # windowless .pyw app, there is no console to show that traceback —
        # the button just appeared to silently do nothing. Now failures are
        # caught, logged, and reported, and a clip that fails to clean is
        # left unmodified rather than aborting the whole batch.
        if not self.orig_images: return
        if not HAS_CV:
            messagebox.showerror("Dependency Missing", "Please run: pip install opencv-python numpy")
            return
        self.save_state()
        self.status_label.configure(text="CLEANING LINES...", text_color=C_ACCENT)
        self.update_idletasks()
        cleaned = []
        failures = 0
        for img in self.orig_images:
            try:
                cleaned.append(self._cv_remove_lines(img))
            except Exception as e:
                logging.error(f"remove_straight_lines: {e}")
                failures += 1
                cleaned.append(img)  # keep the original clip rather than dropping it
        self.orig_images = cleaned
        self.proxy_images = [self.create_proxy(img) for img in self.orig_images]
        self.force_update_preview()
        if failures:
            self.status_label.configure(
                text=f"⚠️ Clean Lines: {failures} clip(s) failed", text_color=C_DANGER)
            messagebox.showwarning(
                "Clean Lines — Partial Failure",
                f"{failures} of {len(self.orig_images)} clip(s) could not be cleaned "
                f"and were left unchanged.\nCheck nab_errors.log for details."
            )
        else:
            self.status_label.configure(text="LINES CLEANED", text_color=C_SUCCESS)
        self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))

    def auto_trim(self):
        if not self.orig_images: return
        self.save_state()
        trimmed = []
        failures = 0
        for img in self.orig_images:
            try:
                trimmed.append(self._cv_auto_trim(img))
            except Exception as e:
                logging.error(f"auto_trim: {e}")
                failures += 1
                trimmed.append(img)
        self.orig_images = trimmed
        self.proxy_images = [self.create_proxy(img) for img in self.orig_images]
        self.force_update_preview()
        if failures:
            messagebox.showwarning(
                "Auto Trim — Partial Failure",
                f"{failures} of {len(self.orig_images)} clip(s) could not be trimmed "
                f"and were left unchanged.\nCheck nab_errors.log for details."
            )

    def add_whitespace(self):
        if not self.orig_images: return
        self.save_state()
        padded = []
        failures = 0
        for img in self.orig_images:
            try:
                padded.append(self._pad_image(img))
            except Exception as e:
                logging.error(f"add_whitespace: {e}")
                failures += 1
                padded.append(img)
        self.orig_images = padded
        self.proxy_images = [self.create_proxy(img) for img in self.orig_images]
        self.force_update_preview()
        if failures:
            messagebox.showwarning(
                "Add Padding — Partial Failure",
                f"{failures} of {len(self.orig_images)} clip(s) could not be padded "
                f"and were left unchanged.\nCheck nab_errors.log for details."
            )

    def clear_all(self):
        self.save_state()
        self.orig_images = []
        self.proxy_images = []
        self.clip_rects = []
        self.reset_view()
        self.force_update_preview()

    def swap_last_two(self):
        if len(self.orig_images) < 2: return
        self.save_state()
        self.orig_images[-1], self.orig_images[-2] = self.orig_images[-2], self.orig_images[-1]
        self.proxy_images[-1], self.proxy_images[-2] = self.proxy_images[-2], self.proxy_images[-1]
        self.force_update_preview()

    def merge_side_by_side(self):
        if len(self.orig_images) < 2: return
        self.save_state()
        r, l = self.orig_images.pop(), self.orig_images.pop()
        new_im = Image.new('RGB', (l.width + r.width, max(l.height, r.height)), (255, 255, 255))
        new_im.paste(l, (0, 0))
        new_im.paste(r, (l.width, 0))
        self.orig_images.append(new_im)
        self.proxy_images.pop()
        self.proxy_images.pop()
        self.proxy_images.append(self.create_proxy(new_im))
        self.force_update_preview()

    # ── mouse motion (hover cursor update in move-tool mode) ────────────────
    def on_mouse_down(self, event):
        self.preview_canvas.focus_set()
        if self.ctrl_pressed and self.space_pressed:
            self._clear_selection()
            self.is_scrubby_zooming = True
            self.scrubby_start_x    = event.x
            self.scrubby_start_zoom = self.user_zoom
            return
        if self.space_pressed:
            self._clear_selection()
            self.is_panning  = True
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            return

        # Normal selection rect
        self.is_selecting = True
        self._clear_selection()
        self.rect_start = (event.x, event.y)
        self.rect_id    = self.preview_canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline=C_ACCENT, width=2, dash=(4, 4), tags="tool_rect")

    def on_mouse_drag(self, event):
        shift = bool(event.state & 0x0001)   # Shift key state

        if self.is_scrubby_zooming:
            delta_x    = event.x - self.scrubby_start_x
            new_zoom   = self.scrubby_start_zoom * (1.0 + delta_x * 0.005)
            if 0.1 <= new_zoom <= 10.0:
                self.user_zoom = new_zoom
                self.update_canvas_render_only()
            return

        if self.is_panning:
            self.pan_offset_x += event.x - self.pan_start_x
            self.pan_offset_y += event.y - self.pan_start_y
            self.pan_start_x   = event.x
            self.pan_start_y   = event.y
            self._pan_canvas_image_only()
            return


        if self.is_selecting and self.rect_start and self.rect_id:
            self.preview_canvas.coords(
                self.rect_id,
                self.rect_start[0], self.rect_start[1], event.x, event.y)

    def on_mouse_up(self, event):
        self.is_scrubby_zooming = False
        self.is_panning         = False


        if self.is_selecting and self.rect_id:
            self.is_selecting = False
            coords = self.preview_canvas.coords(self.rect_id)
            if not (coords and abs(coords[2]-coords[0]) > 5
                             and abs(coords[3]-coords[1]) > 5):
                self._clear_selection()

    def get_real_coords(self, cx, cy):
        return (cx - self.img_draw_x) / self.current_render_scale, \
               (cy - self.img_draw_y) / self.current_render_scale

    def create_merged_clips(self):
        if not self.orig_images: return None
        ws, hs = zip(*(i.size for i in self.orig_images))
        mw, total_h = max(ws), sum(hs)
        new_im = Image.new('RGB', (mw, total_h), (255, 255, 255))
        y = 0
        for img in self.orig_images:
            new_im.paste(img, ((mw - img.size[0]) // 2, y))
            y += img.size[1]
        return new_im

    def _apply_box_action(self, action_type):
        if not self.rect_id or not self.orig_images: return
        x1, y1, x2, y2 = self.preview_canvas.coords(self.rect_id)
        rx1, ry1 = self.get_real_coords(x1, y1)
        rx2, ry2 = self.get_real_coords(x2, y2)
        full = self.create_merged_clips()
        if not full: return
        p_ws, _ = zip(*(i.size for i in self.proxy_images))
        proxy_content_width = max(p_ws)
        ratio = full.width / proxy_content_width
        clip_y1 = (ry1 - self.header_offset) * ratio
        clip_y2 = (ry2 - self.header_offset) * ratio
        p_offset_x = (max(proxy_content_width, 400) - proxy_content_width) // 2
        clip_x1 = (rx1 - p_offset_x) * ratio
        clip_x2 = (rx2 - p_offset_x) * ratio
        cx1, cy1 = max(0, min(clip_x1, clip_x2)), max(0, min(clip_y1, clip_y2))
        cx2, cy2 = min(full.width, max(clip_x1, clip_x2)), min(full.height, max(clip_y1, clip_y2))
        if cx2 - cx1 < 5 or cy2 - cy1 < 5: return
        self.save_state()
        if action_type == "crop":
            res = full.crop((cx1, cy1, cx2, cy2))
        elif action_type == "erase":
            draw = ImageDraw.Draw(full)
            draw.rectangle([cx1, cy1, cx2, cy2], fill="white", outline="white")
            res = full
        elif action_type == "redact":
            draw = ImageDraw.Draw(full)
            draw.rectangle([cx1, cy1, cx2, cy2], fill="#000000", outline="#000000")
            res = full
        elif action_type == "highlight":
            overlay = Image.new('RGBA', full.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle([cx1, cy1, cx2, cy2], fill=(255, 235, 59, 100))
            res = Image.alpha_composite(full.convert("RGBA"), overlay).convert("RGB")
        else:
            res = full
        self.orig_images = [res]
        self.proxy_images = [self.create_proxy(res)]
        self._clear_selection()
        self.force_update_preview()

    def crop_to_selection(self): self._apply_box_action("crop")
    def apply_whiteout(self): self._apply_box_action("erase")
    def apply_redact(self): self._apply_box_action("redact")
    def apply_highlight(self): self._apply_box_action("highlight")

    def _tracker_session_prompt(self):
        """End-of-session newspaper confirmation.

        Papers that actually produced clips today are detected from disk and
        ticked automatically; the rest are listed so the operator can confirm
        which of them genuinely arrived before the day is submitted.

        Only the small confirmation dialog should be visible here — NOT the
        full Tracker window (calendar / heatmap / month view) that session_end_
        confirm() lives on. NewspaperTracker is a CTkToplevel, so simply
        constructing one shows it immediately; if we're creating it fresh just
        to drive this dialog, it's withdrawn straight away so only the small
        dialog appears. If the operator already had Tracker open themselves
        (via the 📰 button), that window is left exactly as they had it.

        Returns 'cancel' if the user backed out of closing NAB."""
        if not _HAS_TRACKER:
            return "skip"
        try:
            created_now = not (hasattr(self, '_tracker_win') and self._tracker_win.winfo_exists())
            if created_now:
                self._tracker_win = NewspaperTracker(self)
                self._tracker_win.withdraw()
                self.update_idletasks()
            return self._tracker_win.session_end_confirm(parent=self)
        except Exception as e:
            logging.error(f"_tracker_session_prompt: {e}")
            return "skip"

    def on_app_close(self):
        # Ask BEFORE anything is torn down — once destroy() runs there's no
        # Tk root left to show a dialog on. Guarded so a second close click
        # can't stack two prompts.
        if not getattr(self, '_tracker_prompt_done', False):
            self._tracker_prompt_done = True
            if self._tracker_session_prompt() == "cancel":
                self._tracker_prompt_done = False
                return

        notified = False
        try:
            # ── Session close notification ──
            if TelegramAuth._session_start:
                elapsed = int(time.time() - TelegramAuth._session_start)
                hrs, rem = divmod(elapsed, 3600)
                mins     = rem // 60
                saves    = len(self.session_history)
                threading.Thread(
                    target=_tg_send,
                    args=(
                        f"🔴 <b>NAB Closed</b>\n\n"
                        f"💻 PC: <code>{PC_NAME}</code>\n"
                        f"🕐 Session: {hrs}h {mins}m\n"
                        f"💾 Files saved: {saves}",
                    ),
                    daemon=True
                ).start()
                notified = True
        except Exception as e:
            logging.error(f"on_app_close: {e}")
        self.save_settings()
        try:
            self._sync.push_on_close(2.5)      # share this session's edits before exiting
        except Exception:
            pass
        # BUG FIX: sys.exit(0) right after starting that thread used to kill
        # it before the HTTP request had even connected — daemon threads die
        # with the process, so the "NAB Closed" message usually never
        # actually sent. A short, bounded wait here (NOT a blocking call —
        # this schedules the real shutdown and returns immediately) gives it
        # a real chance without noticeably slowing the close down.
        self.after(400 if notified else 0, lambda: [self.destroy(), sys.exit(0)])

    def _show_upload_prompt(self, saves):
        """Show end-of-session upload dialog."""
        import tkinter as tk

        dialog = ctk.CTkToplevel(self)
        dialog.title("Upload Today's Work?")
        nab_ui_scale.fit(dialog, 420, 220, parent=self)
        dialog.grab_set()
        dialog.focus_force()
        dialog.lift()

        today = self.current_date.strftime("%d-%m-%Y")

        ctk.CTkLabel(
            dialog,
            text=f"📁 Session complete — {saves} file(s) saved",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            dialog,
            text="Upload today's files to Google Drive now?",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(pady=(0, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20)

        def do_upload():
            dialog.destroy()
            _tg_send(f"📤 Auto-uploading today's files on <b>{PC_NAME}</b>...")
            threading.Thread(
                target=self._upload_date_list_thread,
                args=("*", [today]),
                daemon=True
            ).start()
            self.save_settings()
            # Give upload thread a moment to start, then close
            self.after(1500, lambda: [self.destroy(), sys.exit(0)])

        def do_schedule():
            dialog.destroy()
            # Schedule upload for next startup via settings flag
            self.extra_settings["pending_upload_date"] = today
            self.save_settings()
            _tg_send(
                f"⏰ <b>Upload scheduled for next NAB session on {PC_NAME}</b>\n"
                f"📅 Date: <b>{today}</b>\n"
                f"Will auto-upload when NAB starts next time."
            )
            self.destroy()
            sys.exit(0)

        def do_skip():
            dialog.destroy()
            self.save_settings()
            self.destroy()
            sys.exit(0)

        ctk.CTkButton(
            btn_frame, text="✅ Upload Now",
            fg_color="#2d7a2d", hover_color="#1f5c1f",
            command=do_upload, width=110
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame, text="⏰ Next Time",
            fg_color="#7a6b2d", hover_color="#5c5020",
            command=do_schedule, width=110
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_frame, text="⏭ Skip",
            fg_color="#555", hover_color="#333",
            command=do_skip, width=90
        ).pack(side="left", padx=4)

        # Auto-skip after 30 seconds
        countdown_label = ctk.CTkLabel(dialog, text="Auto-skipping in 30s...", text_color="gray", font=ctk.CTkFont(size=11))
        countdown_label.pack(pady=(12, 0))

        def countdown(n):
            if not dialog.winfo_exists():
                return
            if n <= 0:
                do_skip()
                return
            countdown_label.configure(text=f"Auto-skipping in {n}s...")
            dialog.after(1000, lambda: countdown(n - 1))

        countdown(30)

    def _check_pending_upload(self):
        """Called on startup — if a scheduled upload is pending, run it."""
        pending = self.extra_settings.get("pending_upload_date")
        if not pending:
            return
        # Clear it first
        self.extra_settings.pop("pending_upload_date", None)
        self.save_settings()
        # _tg_send is a plain urllib call with a 10s timeout — called directly
        # here it used to block NAB's startup for up to 10s if Telegram was
        # slow to respond, for a notification nobody needs to wait on.
        threading.Thread(
            target=_tg_send,
            args=(f"⏰ <b>Running scheduled upload on {PC_NAME}</b>\n📅 Date: <b>{pending}</b>",),
            daemon=True
        ).start()
        threading.Thread(
            target=self._upload_date_list_thread,
            args=("*", [pending]),
            daemon=True
        ).start()

    def save_categories_to_file(self):
        cats = {
            self.cat_tree.item(p)['text']: [self.cat_tree.item(c)['text'] for c in self.cat_tree.get_children(p)]
            for p in self.cat_tree.get_children("")
        }
        with open(self.config_file, 'w') as f:
            json.dump(cats, f)

    def load_settings(self):
        default_urls = {
            "prothom alo": "🌅 Prothom Alo", "prothomalo": "🌅 Prothom Alo",
            "daily star": "⭐ Daily Star", "thedailystar": "⭐ Daily Star",
            "tbs": "📊 TBS", "financial express": "💹 Financial Express",
            "observer": "👁️ Daily Observer", "dhaka tribune": "🇧🇩 Dhaka Tribune",
            "new age": "📰 New Age", "daily sun": "☀️ Daily Sun",
            "samakal": "🕒 Samakal", "ittefaq": "🗳️ Ittefaq",
            "jugantor": "🏹 Jugantor", "kaler kantho": "🗣️ Kaler Kantha",
            "janakantha": "🏛️ Janakantha", "naya diganta": "🕌 Naya Diganta",
            "inqilab": "🖋️ Daily Inqilab", "bonik barta": "💼 Bonik Barta",
            "bangladesh pratidin": "🇧🇩 Bangladesh Pratidin", "kalbela": "🔔 Kalbela",
            "epaper.thedailystar.net": "⭐ Daily Star", "epaper.tbsnews.net": "📊 TBS",
            "epaper.prothomalo.com": "🌅 Prothom Alo", "epaper.samakal.com": "🕒 Samakal",
            "epaper.ittefaq.com.bd": "🗳️ Ittefaq", "epaper.jugantor.com": "🏹 Jugantor",
            "epaper.kalerkantho.com": "🗣️ Kaler Kantha", "epaper.kalbela.com": "🔔 Kalbela",
        }

        user_urls = {}
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, 'r') as f:
                    maps = json.load(f)
                    user_urls = maps.get("url_mappings", {})
            except: pass

        self.url_mappings = default_urls.copy()
        self.url_mappings.update(user_urls)

        default_hotkeys_map = {
            "paste": "<Control-v>", "undo": "<Control-z>", "redo": "<Control-y>",
            "delete": "<Delete>", "generate": "<Control-s>", "trim": "<Control-t>",
            "clean": "<Control-l>", "pad": "<Control-e>", "open": "<Control-o>",
            "move_up": "<Control-Up>", "move_down": "<Control-Down>", "swap": "<Control-Left>",
            "tool_crop": "c", "tool_erase": "e", "tool_highlight": "h", "tool_redact": "r"
        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    self.logo_slider.set(data.get("logo_scale", 0.8))
                    self.text_slider.set(data.get("text_scale", 1.0))
                    self.quality_slider.set(data.get("quality", 40))  # FIX 5
                    self.hd_mode_var.set(data.get("hd_mode", False))
                    self.auto_snatch_var.set(data.get("auto_snatch", False))
                    self.auto_polish_var.set(data.get("auto_polish", False))
                    self.quick_saves = data.get("quick_saves", {})
                    self.universal_hotkeys = data.get("hotkeys", default_hotkeys_map)
                    self.extra_settings.update(data.get("extra_settings", {}))
                    self.daily_goal = data.get("daily_goal", 0)
                    self.last_active_date = data.get("last_active_date", "")
                    self.current_streak = data.get("current_streak", 0)
                    self.group_chat_id = data.get("group_chat_id", "")
                    saved_root = data.get("base_root", "")
                    if saved_root and os.path.exists(saved_root):
                        self.base_root = saved_root
            except:
                self.universal_hotkeys = default_hotkeys_map
        else:
            self.universal_hotkeys = default_hotkeys_map

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump({
                    "logo_scale": self.logo_slider.get(),
                    "text_scale": self.text_slider.get(),
                    "quality": self.quality_slider.get(),  # FIX 5
                    "hd_mode": self.hd_mode_var.get(),
                    "auto_snatch": getattr(self, 'auto_snatch_var', ctk.BooleanVar(value=False)).get(),
                    "auto_polish": getattr(self, 'auto_polish_var', ctk.BooleanVar(value=False)).get(),
                    "quick_saves": self.quick_saves,
                    "hotkeys": self.universal_hotkeys,
                    "base_root": self.base_root,
                    "extra_settings": self.extra_settings,
                    "daily_goal": self.daily_goal,
                    "last_active_date": self.last_active_date,
                    "current_streak": getattr(self, 'current_streak', 0),
                    "group_chat_id": getattr(self, 'group_chat_id', ''),
                }, f)
        except Exception as e:
            logging.error(f"save_settings: {e}")

        try:
            with open(self.mappings_file, 'w') as f:
                json.dump({"url_mappings": self.url_mappings}, f)
        except: pass

    def open_source_manager(self):
        SourceManagerDialog(self, self.paper_list, self.save_sources, self.logo_dir)

    def open_history(self):
        nab_recent.open_recent_saves(self)

    def delete_from_history(self, index):
        if 0 <= index < len(self.session_history):
            self.session_history.pop(index)

    def load_image_from_path(self, path):
        try:
            img = Image.open(path).convert("RGB")
            self.save_state()
            self.orig_images = [img]
            self.proxy_images = [self.create_proxy(img)]
            self.force_update_preview()
            self.status_label.configure(text="EDIT MODE", text_color=C_ACCENT)
        except Exception as e:
            messagebox.showerror("Err", str(e))

    def _poll_window_state(self):
        """Poll window state every 250 ms to detect minimize/restore.
        We use polling rather than <Unmap>/<Map> because those events fire
        for every child widget on Windows and are completely unreliable.

        The 200 ms delayed show is critical: when the user clicks the
        minimize button, Windows iconifies NAB and ALL its Toplevel children
        at the same time. If we call deiconify() immediately, the overlay
        gets re-minimised by the OS a few ms later. Waiting 200 ms lets the
        OS finish the minimize sequence before we bring the overlay up.
        MiniOverlay uses super().__init__() with NO master so it is an
        independent window — not a child — and therefore survives NAB's
        iconify once it is shown."""
        try:
            iconic = (self.state() == 'iconic')

            if iconic and not self._was_iconic:
                # NAB just minimised — re-lift overlay after OS finishes
                def _show_overlay():
                    try:
                        if not self._mini_overlay or                                 not self._mini_overlay.winfo_exists():
                            self._mini_overlay = MiniOverlay(self)
                        self._mini_overlay.deiconify()
                        self._mini_overlay.lift()
                        self._mini_overlay.attributes("-topmost", True)
                    except Exception as e:
                        logging.error(f"_show_overlay: {e}")
                self.after(220, _show_overlay)

            # Overlay is never hidden on restore — it stays visible always

            self._was_iconic = iconic
        except Exception:
            pass
        self.after(250, self._poll_window_state)

    def notify_snatch(self, action_text="Image snatched"):
        """Called after a successful clipboard snatch/paste — notifies
        the mini overlay and Chrome extension preview server."""
        self._last_broadcast_action = action_text

    # ── GitHub auto-update ────────────────────────────────────────────────────

    def _github_version_check_loop(self):
        """Check GitHub every 5 min. If newer version found, download silently
        in background while user keeps working. Lock screen appears when ready."""
        if not GITHUB_REPO:
            return
        def _loop():
            while True:
                try:
                    remote_ver, dl_url = _github_get_latest_release()
                    if remote_ver and dl_url and _ver(remote_ver) > _ver(APP_VERSION):
                        # Found newer version — download silently in background
                        self.after(0, self._show_download_status)
                        dest = _update_zip_path() if _is_frozen() else _current_exe() + ".new"
                        def _progress(pct):
                            self.after(0, lambda p=pct: self._update_download_status(p))
                        ok, err = _github_download_silently(dl_url, dest,
                                                             progress_cb=_progress)
                        if ok:
                            # Download complete — show lock screen
                            self.after(0, lambda v=remote_ver, d=dest:
                                       self._show_restart_lock(v, d))
                        else:
                            # Download failed — hide status, retry next cycle
                            self.after(0, self._hide_download_status)
                            logging.error("Silent download failed: " + str(err))
                        return
                except Exception as e:
                    logging.error("github_version_check: " + str(e))
                time.sleep(GITHUB_CHECK_INTERVAL)
        threading.Thread(target=_loop, daemon=True, name="NAB-UpdateCheck").start()

    def _show_download_status(self):
        """Show a small unobtrusive status bar at the bottom during download."""
        if getattr(self, '_dl_status_bar', None):
            try:
                if self._dl_status_bar.winfo_exists():
                    return
            except Exception:
                pass
        bar = ctk.CTkFrame(self, fg_color="#0A1520", height=28, corner_radius=0)
        bar.place(x=0, rely=1.0, y=-28, relwidth=1.0)
        bar.lift()
        self._dl_status_bar = bar
        self._dl_pct_lbl = ctk.CTkLabel(bar,
            text="⬇  Downloading update in background…  0%",
            font=ctk.CTkFont(size=10), text_color="#1E88E5")
        self._dl_pct_lbl.pack(side="left", padx=12, pady=4)

    def _update_download_status(self, pct):
        try:
            if self._dl_pct_lbl.winfo_exists():
                self._dl_pct_lbl.configure(
                    text="⬇  Downloading update in background…  " + str(pct) + "%")
        except Exception:
            pass

    def _hide_download_status(self):
        try:
            if self._dl_status_bar.winfo_exists():
                self._dl_status_bar.destroy()
        except Exception:
            pass

    def _show_restart_lock(self, remote_version, new_exe_path):
        """Full-screen lock screen — update is ready, must restart to apply."""
        self._hide_download_status()

        # Same pattern as Telegram auth — full-screen CTkFrame over main window
        gate = ctk.CTkFrame(self, fg_color="#060C14", corner_radius=0)
        gate.place(relwidth=1, relheight=1)
        gate.lift()
        self._update_gate_frame = gate
        def _keep_up():
            try:
                if gate.winfo_exists():
                    gate.lift()
                    self.after(800, _keep_up)
            except Exception:
                pass
        self.after(200, _keep_up)

        card = ctk.CTkFrame(gate, width=520, height=400,
                             fg_color=C_SURFACE, corner_radius=20,
                             border_color="#1E88E5", border_width=1)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Icon + title
        ctk.CTkLabel(card, text="✅",
                     font=("Segoe UI Emoji", 44),
                     text_color="#43A047").pack(pady=(28, 0))
        ctk.CTkLabel(card, text="Update Ready",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#EEE").pack(pady=(6, 2))

        # Version info box
        vbox = ctk.CTkFrame(card, fg_color="#0A1520", corner_radius=10)
        vbox.pack(padx=40, fill="x", pady=(10, 0))

        r1 = ctk.CTkFrame(vbox, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(10, 3))
        ctk.CTkLabel(r1, text="Installed",
                     font=ctk.CTkFont(size=11), text_color="#444",
                     width=100, anchor="w").pack(side="left")
        ctk.CTkLabel(r1, text="v" + APP_VERSION,
                     font=ctk.CTkFont(size=11), text_color="#555").pack(side="left")

        r2 = ctk.CTkFrame(vbox, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(r2, text="New version",
                     font=ctk.CTkFont(size=11), text_color="#444",
                     width=100, anchor="w").pack(side="left")
        ctk.CTkLabel(r2, text="v" + remote_version,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#43A047").pack(side="left")

        ctk.CTkLabel(card,
            text="The update has been downloaded and is ready to install.",
            font=ctk.CTkFont(size=11), text_color="#555",
            wraplength=440).pack(pady=(12, 0))

        status_lbl = ctk.CTkLabel(card, text="",
                                   font=ctk.CTkFont(size=11), text_color="#888")
        status_lbl.pack(pady=(8, 0))

        def _do_restart():
            # Check updater exists before doing anything
            updater = os.path.join(
                os.path.dirname(_current_exe()), "nab_updater.exe")
            if _is_frozen() and not os.path.exists(updater):
                status_lbl.configure(
                    text="❌ nab_updater.exe not found next to NAB.exe. "
                         "Download it from GitHub Releases and try again.",
                    text_color="#EF5350")
                return
            btn.configure(state="disabled", text="Restarting…")
            status_lbl.configure(
                text="✅ Launching updater… NAB will restart in a moment.",
                text_color="#1E88E5")
            self.update_idletasks()
            self.after(500, lambda: _apply_update_and_restart(
                _current_exe(), new_exe_path))

        btn = ctk.CTkButton(card,
            text="🔄  Restart & Update Now",
            height=48, corner_radius=24,
            fg_color="#1565C0", hover_color="#1976D2",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=_do_restart)
        btn.pack(padx=40, fill="x", pady=(14, 0))

        ctk.CTkLabel(card,
            text="You cannot use NAB until the update is applied.",
            font=ctk.CTkFont(size=10), text_color="#222").pack(pady=(8, 0))

        # Force focus to the gate so keyboard shortcuts don't work behind it



    def open_ocr_search(self):
        """Launch the bundled Image OCR Finder tool.
        It's a full Tkinter app with its own window and event loop, so it
        can't run inside NAB's own UI — instead this starts a second
        instance of this same EXE/script with --ocr-finder, which
        NAB_entry.pyw detects and dispatches to image_ocr_finder.main()
        instead of NAB's own UI."""
        if getattr(self, '_ocr_finder_proc', None) and self._ocr_finder_proc.poll() is None:
            # Already running. We can't force another process's window to
            # the front from here without extra OS-level plumbing, but we
            # can at least tell the user instead of silently doing nothing.
            self.status_label.configure(text="OCR FINDER ALREADY OPEN", text_color=C_ACCENT)
            self.after(2000, lambda: self.status_label.configure(text="READY", text_color=C_TEXT_DIM))
            return
        try:
            cmd = [_current_exe(), "--ocr-finder"] if _is_frozen() else \
                  [sys.executable, _current_exe(), "--ocr-finder"]
            self._ocr_finder_proc = subprocess.Popen(cmd, cwd=os.path.dirname(_current_exe()))
        except Exception as e:
            logging.error(f"open_ocr_search: {e}")
            messagebox.showerror("OCR Finder Failed to Launch", str(e))

    def open_pdf_bot(self):
        """Launch the bundled PDF Maker (nab_pdf.py).

        Same approach as open_ocr_search: PDF Maker has its own Tk root and
        drives a ProcessPoolExecutor, so it runs as a second instance of this
        same EXE/script with --pdf-bot, which NAB_entry.pyw dispatches."""
        if getattr(self, '_pdf_bot_proc', None) and self._pdf_bot_proc.poll() is None:
            self.status_label.configure(text="PDF MAKER ALREADY OPEN", text_color=C_ACCENT)
            self.after(2000, lambda: self.status_label.configure(
                text="READY", text_color=C_TEXT_DIM))
            return
        try:
            cmd = [_current_exe(), "--pdf-bot"] if _is_frozen() else \
                  [sys.executable, _current_exe(), "--pdf-bot"]
            self._pdf_bot_proc = subprocess.Popen(cmd, cwd=os.path.dirname(_current_exe()))
            self.status_label.configure(text="PDF MAKER OPENED", text_color=C_ACCENT)
            self.after(2000, lambda: self.status_label.configure(
                text="READY", text_color=C_TEXT_DIM))
        except Exception as e:
            logging.error(f"open_pdf_bot: {e}")
            messagebox.showerror("PDF Maker Failed to Launch", str(e))

    def open_pdf_bot_today(self):
        """One click: build every PDF for TODAY's folder, no folder picker.

        Launches the same PDF Maker process as open_pdf_bot(), but with
        --auto-folder pointing at today's save folder — nab_pdf.main() skips
        straight to processing instead of waiting at an empty window for the
        operator to browse to a folder they'd pick every single time anyway.
        """
        if getattr(self, '_pdf_bot_proc', None) and self._pdf_bot_proc.poll() is None:
            self.status_label.configure(text="PDF MAKER ALREADY OPEN", text_color=C_ACCENT)
            self.after(2000, lambda: self.status_label.configure(
                text="READY", text_color=C_TEXT_DIM))
            return
        today = self.current_date if hasattr(self, 'current_date') else datetime.datetime.now()
        folder = os.path.join(self.base_root, today.strftime("%Y"),
                              today.strftime("%B"), today.strftime("%d-%m-%Y"))
        if not os.path.isdir(folder):
            messagebox.showwarning(
                "No folder for today",
                f"Nothing has been saved today yet — this folder doesn't "
                f"exist:\n{folder}")
            return
        try:
            cmd = ([_current_exe(), "--pdf-bot", "--auto-folder", folder] if _is_frozen()
                  else [sys.executable, _current_exe(), "--pdf-bot", "--auto-folder", folder])
            self._pdf_bot_proc = subprocess.Popen(cmd, cwd=os.path.dirname(_current_exe()))
            self.status_label.configure(text="BUILDING TODAY'S PDFS...", text_color=C_ACCENT)
            self.after(2500, lambda: self.status_label.configure(
                text="READY", text_color=C_TEXT_DIM))
        except Exception as e:
            logging.error(f"open_pdf_bot_today: {e}")
            messagebox.showerror("PDF Maker Failed to Launch", str(e))

    def open_last_folder(self):
        # BUG FIX: previously this called open_folder() and gave zero feedback
        # if last_saved_path was empty (nothing saved yet this session) or if
        # the folder had since been deleted/moved — the button just appeared
        # to do nothing, which is exactly the "file opening is broken" symptom.
        if not self.last_saved_path:
            messagebox.showinfo(
                "Nothing to Open",
                "No folder has been saved to yet this session.\n"
                "Save a clip first, then use Open Folder."
            )
            return
        if not os.path.exists(self.last_saved_path):
            messagebox.showwarning(
                "Folder Not Found",
                f"The last saved folder no longer exists:\n{self.last_saved_path}"
            )
            return
        if not open_folder(self.last_saved_path):
            messagebox.showerror(
                "Could Not Open Folder",
                f"Failed to open:\n{self.last_saved_path}\n\nCheck nab_errors.log for details."
            )

    def add_root_category(self):
        n = simpledialog.askstring("New", "Name")
        if n:
            self.cat_tree.insert("", "end", text=n)
            self.save_categories_to_file()

    def add_sub_category(self):
        s = self.cat_tree.selection()
        if s:
            n = simpledialog.askstring("Sub", "Name")
            if n:
                self.cat_tree.insert(s[0], "end", text=n)
                self.cat_tree.item(s[0], open=True)
                self.save_categories_to_file()

    def rename_category(self):
        s = self.cat_tree.selection()
        if s:
            n = simpledialog.askstring("Rename", "Name", initialvalue=self.cat_tree.item(s[0])['text'])
            if n:
                self.cat_tree.item(s[0], text=n)
                self.save_categories_to_file()

    def delete_category(self):
        s = self.cat_tree.selection()
        if s and messagebox.askyesno("Delete", "Sure?"):
            self.cat_tree.delete(s[0])
            self.save_categories_to_file()

    def show_context_menu(self, event):
        item = self.cat_tree.identify_row(event.y)
        if item:
            self.cat_tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)