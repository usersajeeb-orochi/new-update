# nab_dialogs.py — all popup dialog classes
import os
import customtkinter as ctk
from tkinter import Canvas, END, Listbox, filedialog, messagebox
from PIL import Image, ImageEnhance, ImageTk, ImageGrab
from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})
# Windows are sized through nab_ui_scale.fit() instead of hardcoded
# pixels — see nab_ui_scale.py for why (small monitors / DPI).
import nab_ui_scale
import nab_subscriptions


class GlobalSettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_root, save_callback, extra_settings=None, save_extra_callback=None):
        super().__init__(parent)
        self.title("Global Settings")
        nab_ui_scale.fit(self, 560, 620, min_w=347, min_h=384, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.save_callback = save_callback
        self.save_extra = save_extra_callback
        self.extra = extra_settings or {}

        ctk.CTkLabel(self, text="APP SETTINGS", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=15)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20)

        # Output dir
        f1 = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f1.pack(fill="x", pady=5)
        ctk.CTkLabel(f1, text="Output Directory:", font=F_BODY, text_color="white").pack(anchor="w", padx=15, pady=(10,0))
        dir_frame = ctk.CTkFrame(f1, fg_color="transparent")
        dir_frame.pack(fill="x", padx=15, pady=(5,15))
        self.dir_entry = ctk.CTkEntry(dir_frame, font=("Arial", 11), fg_color="#000", border_color=C_BORDER)
        self.dir_entry.insert(0, current_root)
        self.dir_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dir_frame, text="Browse", width=60, fg_color="#333", command=self.browse_dir).pack(side="right", padx=(5,0))

        # Feature 32: File size limits
        f2 = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f2.pack(fill="x", pady=5)
        ctk.CTkLabel(f2, text="File Size Alert Limits (KB)", font=F_BTN, text_color=C_ACCENT).pack(anchor="w", padx=15, pady=(10,0))
        size_row = ctk.CTkFrame(f2, fg_color="transparent")
        size_row.pack(fill="x", padx=15, pady=(5,10))
        ctk.CTkLabel(size_row, text="Min:", text_color="#aaa", font=F_TECH).pack(side="left")
        self.min_size_entry = ctk.CTkEntry(size_row, width=70, fg_color="#000", border_color=C_BORDER)
        self.min_size_entry.insert(0, str(self.extra.get("min_file_size_kb", 20)))
        self.min_size_entry.pack(side="left", padx=5)
        ctk.CTkLabel(size_row, text="Max:", text_color="#aaa", font=F_TECH).pack(side="left", padx=(10,0))
        self.max_size_entry = ctk.CTkEntry(size_row, width=70, fg_color="#000", border_color=C_BORDER)
        self.max_size_entry.insert(0, str(self.extra.get("max_file_size_kb", 5000)))
        self.max_size_entry.pack(side="left", padx=5)
        ctk.CTkLabel(f2, text="App will warn if saved file is outside this range.", font=("Segoe UI", 9), text_color="#555").pack(anchor="w", padx=15, pady=(0,10))

        # Feature 14: Batch save category mappings toggle
        f3 = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f3.pack(fill="x", pady=5)
        ctk.CTkLabel(f3, text="Batch Save Settings", font=F_BTN, text_color=C_ACCENT).pack(anchor="w", padx=15, pady=(10,0))
        self.batch_enabled_var = ctk.BooleanVar(value=self.extra.get("batch_save_enabled", False))
        ctk.CTkSwitch(f3, text="Enable Batch Save (save to multiple categories at once)",
                      variable=self.batch_enabled_var, font=F_TECH, progress_color=C_ACCENT).pack(anchor="w", padx=15, pady=5)
        ctk.CTkLabel(f3, text="When enabled, hold Ctrl and click multiple categories\nbefore hitting Generate.",
                     font=("Segoe UI", 9), text_color="#555", justify="left").pack(anchor="w", padx=15, pady=(0,10))

        # Feature 15: Auto-save interval
        f4 = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f4.pack(fill="x", pady=5)
        ctk.CTkLabel(f4, text="Scheduled Auto-Save", font=F_BTN, text_color=C_ACCENT).pack(anchor="w", padx=15, pady=(10,0))
        self.autosave_enabled_var = ctk.BooleanVar(value=self.extra.get("autosave_enabled", False))
        ctk.CTkSwitch(f4, text="Enable auto-save on interval",
                      variable=self.autosave_enabled_var, font=F_TECH, progress_color=C_ACCENT).pack(anchor="w", padx=15, pady=5)
        interval_row = ctk.CTkFrame(f4, fg_color="transparent")
        interval_row.pack(fill="x", padx=15, pady=(0,10))
        ctk.CTkLabel(interval_row, text="Interval (seconds):", text_color="#aaa", font=F_TECH).pack(side="left")
        self.autosave_interval_entry = ctk.CTkEntry(interval_row, width=70, fg_color="#000", border_color=C_BORDER)
        self.autosave_interval_entry.insert(0, str(self.extra.get("autosave_interval", 300)))
        self.autosave_interval_entry.pack(side="left", padx=5)

        # Feature 26: Daily summary time
        f5 = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f5.pack(fill="x", pady=5)
        ctk.CTkLabel(f5, text="Daily Auto-Report Time", font=F_BTN, text_color=C_ACCENT).pack(anchor="w", padx=15, pady=(10,0))
        self.daily_report_enabled_var = ctk.BooleanVar(value=self.extra.get("daily_report_enabled", False))
        ctk.CTkSwitch(f5, text="Send daily Telegram report automatically",
                      variable=self.daily_report_enabled_var, font=F_TECH, progress_color=C_ACCENT).pack(anchor="w", padx=15, pady=5)
        time_row = ctk.CTkFrame(f5, fg_color="transparent")
        time_row.pack(fill="x", padx=15, pady=(0,10))
        ctk.CTkLabel(time_row, text="Send at hour (0-23):", text_color="#aaa", font=F_TECH).pack(side="left")
        self.daily_report_hour_entry = ctk.CTkEntry(time_row, width=50, fg_color="#000", border_color=C_BORDER)
        self.daily_report_hour_entry.insert(0, str(self.extra.get("daily_report_hour", 18)))
        self.daily_report_hour_entry.pack(side="left", padx=5)

        # Advanced — hidden connections (everything works out of the box)
        ctk.CTkButton(scroll, text="🔧  Advanced…", height=34, font=F_BTN, fg_color="#1A1A1A",
                      hover_color="#333", border_width=1, border_color=C_BORDER,
                      command=lambda: AdvancedConnectionsDialog(self)).pack(fill="x", pady=(10, 5))

        ctk.CTkButton(self, text="SAVE", height=45, corner_radius=22, font=F_BTN,
                      fg_color=C_ACCENT, command=self.apply).pack(fill="x", padx=20, pady=15)

    def browse_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_entry.delete(0, END)
            self.dir_entry.insert(0, d)

    def apply(self):
        new_dir = self.dir_entry.get().strip()
        if new_dir and os.path.exists(new_dir):
            self.save_callback(new_dir)
            if self.save_extra:
                try:
                    extra = {
                        "min_file_size_kb": int(self.min_size_entry.get()),
                        "max_file_size_kb": int(self.max_size_entry.get()),
                        "batch_save_enabled": self.batch_enabled_var.get(),
                        "autosave_enabled": self.autosave_enabled_var.get(),
                        "autosave_interval": int(self.autosave_interval_entry.get()),
                        "daily_report_enabled": self.daily_report_enabled_var.get(),
                        "daily_report_hour": int(self.daily_report_hour_entry.get()),
                    }
                    self.save_extra(extra)
                except ValueError:
                    messagebox.showerror("Error", "Please enter valid numbers.", parent=self)
                    return
            self.destroy()
        else:
            messagebox.showerror("Error", "Invalid Directory", parent=self)


class AdvancedConnectionsDialog(ctk.CTkToplevel):
    """Settings → Advanced → Connections.  Everything is built in; this only
    exists to override a value on THIS PC. Empty box = use the built-in value."""

    _FIELDS = [
        ("drive_folder_id", "📁 Google Drive folder ID", "Where clips are uploaded and settings sync."),
        ("cloud_url",       "🌐 Cloud bot URL",          "Heartbeat / remote commands (Render)."),
        ("sheet_id",        "📊 Tracker Google Sheet ID", "The Tracker's spreadsheet."),
        ("telegram_token",  "✈️ Telegram bot token",      "Takes effect after restarting NAB."),
        ("google_key_path", "🔑 Google key file",         "Leave empty to use the key built into NAB."),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        import nab_connections as nc
        self.nc = nc
        self.title("Advanced — Connections")
        nab_ui_scale.fit(self, 560, 640, min_w=347, min_h=384, parent=parent)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.entries = {}

        ctk.CTkLabel(self, text="CONNECTIONS", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=(14, 2))
        self.info = ctk.CTkLabel(self, text="", font=F_TECH, text_color="#888", wraplength=500, justify="left")
        self.info.pack(padx=20, anchor="w")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=6)
        for key, title, hint in self._FIELDS:
            box = ctk.CTkFrame(scroll, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
            box.pack(fill="x", pady=4)
            ctk.CTkLabel(box, text=title, font=F_BTN, text_color=C_ACCENT).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(box, text=hint, font=("Segoe UI", 9), text_color="#666").pack(anchor="w", padx=12)
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(3, 10))
            e = ctk.CTkEntry(row, fg_color="#000", border_color=C_BORDER, font=("Consolas", 11),
                             show="•" if key == "telegram_token" else "")
            e.pack(side="left", fill="x", expand=True)
            if key == "google_key_path":
                ctk.CTkButton(row, text="Browse", width=60, fg_color="#333",
                              command=self._browse_key).pack(side="right", padx=(5, 0))
            self.entries[key] = e

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(4, 14))
        ctk.CTkButton(btns, text="Reset to built-in", height=40, font=F_BTN, fg_color="#444",
                      hover_color="#333", command=self.reset).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="SAVE", height=40, font=F_BTN, fg_color=C_ACCENT,
                      command=self.save).pack(side="left", fill="x", expand=True)
        self._load()

    def _load(self):
        nc = self.nc
        for key, e in self.entries.items():
            e.delete(0, END)
            e.configure(placeholder_text="(built-in)")
            v = nc.override(key)
            if v:
                e.insert(0, v)
        sm = nc.summary()
        self.info.configure(
            text=f"Using built-in values unless a box below is filled.   Google key: {sm['key_source']}."
                 + ("   ⚠ No Google key in this build — Drive/Sheets won't work." if not sm["key_ok"] else ""))

    def _browse_key(self):
        p = filedialog.askopenfilename(title="Google service-account key (.json)",
                                       filetypes=[("JSON", "*.json")], parent=self)
        if p:
            e = self.entries["google_key_path"]
            e.delete(0, END)
            e.insert(0, p)

    def save(self):
        nc = self.nc
        tg_changed = False
        for key, e in self.entries.items():
            v = e.get().strip()
            if key == "telegram_token" and v != nc.override(key):
                tg_changed = True
            nc.set_override(key, v)
        msg = "Saved."
        if tg_changed:
            msg += "\nRestart NAB for the new Telegram token to take effect."
        messagebox.showinfo("Connections", msg, parent=self)
        self._load()

    def reset(self):
        if messagebox.askyesno("Reset", "Remove all overrides and use the built-in connections on this PC?",
                               parent=self):
            self.nc.reset_all()
            self._load()
            messagebox.showinfo("Connections", "Reset. Restart NAB if you had changed the Telegram token.",
                                parent=self)


class UniversalHotkeyDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_hotkeys, save_callback):
        super().__init__(parent)
        self.title("Universal Hotkeys")
        nab_ui_scale.fit(self, 500, 700, min_w=310, min_h=434, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.save_callback = save_callback
        ctk.CTkLabel(self, text="UNIVERSAL HOTKEYS", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=10)
        ctk.CTkLabel(self, text="Click a button and press a new key combination.", font=("Arial", 10), text_color=C_TEXT_DIM).pack(pady=(0,10))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C_SURFACE)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=5)
        self.actions = {
            "paste": "Paste Image", "undo": "Undo", "redo": "Redo",
            "delete": "Delete / Erase Box", "generate": "Generate / Save",
            "trim": "Auto Trim", "clean": "Clean Lines", "pad": "Add Padding",
            "open": "Open Folder", "move_up": "Move Clip Up", "move_down": "Move Clip Down",
            "swap": "Swap Last Two", "tool_crop": "Crop Tool", "tool_erase": "Erase Tool",
            "tool_highlight": "Highlight Tool", "tool_redact": "Redact Tool"
        }
        self.slots = {}
        for action_key, display_name in self.actions.items():
            row = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=display_name, font=F_BODY, width=200, anchor="w").pack(side="left", padx=10)
            key_val = current_hotkeys.get(action_key, "Unbound")
            key_btn = ctk.CTkButton(row, text=key_val, width=150, fg_color="#333", font=("Consolas", 11, "bold"))
            key_btn.configure(command=lambda b=key_btn: self.listen_for_key(b))
            key_btn.pack(side="right", padx=10)
            self.slots[action_key] = key_btn
        ctk.CTkButton(self, text="SAVE ALL HOTKEYS", height=45, corner_radius=22, font=F_BTN,
                      fg_color=C_ACCENT, command=self.apply).pack(fill="x", padx=20, pady=20)
        self.listening_btn = None

    def listen_for_key(self, btn):
        if self.listening_btn:
            self.listening_btn.configure(text=self.listening_old_text)
            self.unbind('<KeyPress>')
        self.listening_btn = btn
        self.listening_old_text = btn.cget("text")
        btn.configure(text="Press a key...")
        self.bind('<KeyPress>', self.on_key_bound)
        self.focus_set()

    def on_key_bound(self, event):
        mods = []
        if event.state & 0x0004: mods.append("Control")
        if event.state & 0x0001: mods.append("Shift")
        if event.state & 0x00020000: mods.append("Alt")
        keysym = event.keysym
        if keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Caps_Lock'):
            return
        key_str = f"<{'-'.join(mods)}-{keysym}>" if mods else (keysym if len(keysym) == 1 else f"<{keysym}>")
        self.listening_btn.configure(text=key_str)
        self.unbind('<KeyPress>')
        self.listening_btn = None

    def apply(self):
        new_map = {}
        for action_key, key_btn in self.slots.items():
            key_val = key_btn.cget("text")
            if key_val and key_val not in ["Press a key...", "Unbound"]:
                new_map[action_key] = key_val
        self.save_callback(new_map)
        self.destroy()


class MappingDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, desc, col1_header, col2_header, current_dict, options_list, save_callback, tester=None, prefill=None):
        super().__init__(parent)
        self.title(title)
        nab_ui_scale.fit(self, 600, 650, min_w=372, min_h=403, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.save_callback = save_callback
        self.options_list = options_list
        ctk.CTkLabel(self, text=title, font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=(20, 5))
        ctk.CTkLabel(self, text=desc, font=("Arial", 11), text_color=C_TEXT_DIM).pack(pady=(0, 8))
        self.tester = tester
        if tester:
            tf = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=8)
            tf.pack(fill="x", padx=20, pady=(0, 6))
            trow = ctk.CTkFrame(tf, fg_color="transparent")
            trow.pack(fill="x", padx=8, pady=(8, 2))
            self.test_entry = ctk.CTkEntry(trow, placeholder_text="🧪 Test: paste a tab title or URL here…",
                                           fg_color="#000", border_color=C_BORDER)
            self.test_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkButton(trow, text="TEST", width=60, fg_color=C_ACCENT, text_color="black",
                          command=self.run_test).pack(side="left")
            self.test_entry.bind("<Return>", lambda e: self.run_test())
            self.test_result = ctk.CTkLabel(tf, text="Tests the rows below as they are now (even unsaved).",
                                            font=("Consolas", 10), text_color=C_TEXT_DIM,
                                            justify="left", anchor="w", wraplength=520)
            self.test_result.pack(fill="x", padx=10, pady=(0, 8))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C_SURFACE)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=5)
        headers = ctk.CTkFrame(self.scroll, fg_color="transparent")
        headers.pack(fill="x", pady=5)
        ctk.CTkLabel(headers, text=col1_header, font=F_BTN, width=250, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(headers, text=col2_header, font=F_BTN, width=250, anchor="w").pack(side="left", padx=5)
        self.rows = []
        for k, v in current_dict.items():
            self.add_row(k, v)
        if prefill:
            self.add_row(*prefill)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(btn_frame, text="+ ADD ROW", fg_color="#333",
                      command=lambda: self.add_row("", self.options_list[0] if self.options_list else "")).pack(side="left")
        ctk.CTkButton(btn_frame, text="SAVE MAPPINGS", fg_color=C_ACCENT, command=self.apply).pack(side="right")

    def _rows_dict(self):
        d = {}
        for row, e, var in self.rows:
            k = e.get().strip()
            if k:
                d[k] = var.get()
        return d

    def run_test(self):
        try:
            paper, lines = self.tester(self.test_entry.get(), self._rows_dict())
            self.test_result.configure(text="\n".join(lines),
                                       text_color="#22C55E" if paper else "#EF4444")
        except Exception as e:
            self.test_result.configure(text=f"Test failed: {e}", text_color="#EF4444")

    def add_row(self, k_val, v_val):
        row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row.pack(fill="x", pady=5)
        e = ctk.CTkEntry(row, width=250, fg_color="#000", border_color=C_BORDER)
        e.insert(0, k_val)
        e.pack(side="left", padx=5)
        var = ctk.StringVar(value=v_val)
        cb = ctk.CTkOptionMenu(row, variable=var, values=self.options_list, fg_color="#000",
                               button_color=C_ACCENT, width=200)
        cb.pack(side="left", padx=5)
        del_btn = ctk.CTkButton(row, text="X", width=30, fg_color="#C62828",
                                command=lambda r=row, d=(e, var): self.del_row(r, d))
        del_btn.pack(side="left", padx=5)
        self.rows.append((row, e, var))

    def del_row(self, row_frame, data_tuple):
        row_frame.destroy()
        self.rows = [r for r in self.rows if r[1] != data_tuple[0]]

    def apply(self):
        new_map = {}
        for row, e, var in self.rows:
            k = e.get().strip()
            v = var.get()
            if k: new_map[k] = v
        self.save_callback(new_map)
        self.destroy()


class QuickSaveSettingsDialog(ctk.CTkToplevel):
    """Quick-save keybinding dialog.
    Supports plain keys (1-9, a-z, F1-F12) AND Ctrl+key combos
    giving 20+ shortcut slots instead of just 9."""

    NUM_SLOTS = 20

    def __init__(self, parent, current_mappings, categories_list, save_callback):
        super().__init__(parent)
        self.title("Quick-Save Keybindings")
        nab_ui_scale.fit(self, 560, 680, min_w=347, min_h=421, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.save_callback = save_callback
        self.listening_btn = None
        self._ctrl_held    = False

        ctk.CTkLabel(self, text="QUICK-SAVE KEYBINDINGS",
                     font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=(14,2))
        ctk.CTkLabel(self,
            text="Click a key slot and press any key. Hold Ctrl while pressing for Ctrl+key combos.",
            font=("Arial", 10), text_color=C_TEXT_DIM, wraplength=500).pack(pady=(0,8))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C_SURFACE)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=4)
        self.slots = []

        keys_list = list(current_mappings.keys())
        cats_list = list(current_mappings.values())
        opts      = ["-- None --"] + categories_list

        for i in range(self.NUM_SLOTS):
            row = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row.pack(fill="x", pady=4)
            cat_val = cats_list[i] if i < len(cats_list) else "-- None --"
            key_val = keys_list[i] if i < len(keys_list) else "Click to Bind"
            cat_var = ctk.StringVar(value=cat_val)
            ctk.CTkOptionMenu(row, variable=cat_var, values=opts,
                               fg_color="#000", button_color=C_ACCENT,
                               button_hover_color=C_ACCENT_HOVER,
                               width=250).pack(side="left", padx=6)
            key_btn = ctk.CTkButton(row, text=key_val, width=170,
                                     fg_color="#222", font=F_BTN)
            key_btn.configure(command=lambda b=key_btn: self.listen_for_key(b))
            key_btn.pack(side="right", padx=6)
            self.slots.append((cat_var, key_btn))

        ctk.CTkButton(self, text="SAVE MAPPINGS", height=44,
                      corner_radius=22, font=F_BTN,
                      fg_color=C_ACCENT, command=self.apply
                      ).pack(fill="x", padx=16, pady=14)

    def listen_for_key(self, btn):
        if self.listening_btn:
            self.listening_btn.configure(text=self.listening_old_text, fg_color="#222")
            self.unbind('<KeyPress>')
            self.unbind('<KeyRelease>')
        self.listening_btn      = btn
        self.listening_old_text = btn.cget("text")
        btn.configure(text="Press key…", fg_color="#1565C0")
        self._ctrl_held = False
        self.bind('<KeyPress>',   self._on_key)
        self.bind('<KeyRelease>', self._on_rel)
        self.focus_set()

    def _on_rel(self, event):
        if event.keysym in ('Control_L', 'Control_R'):
            self._ctrl_held = False

    def _on_key(self, event):
        k = event.keysym
        if k in ('Control_L', 'Control_R'):
            self._ctrl_held = True
            return
        if k in ('Shift_L','Shift_R','Alt_L','Alt_R','Caps_Lock'): return
        display = ("Ctrl+" + k) if self._ctrl_held else k
        self.listening_btn.configure(text=display, fg_color="#145A32")
        self.unbind('<KeyPress>')
        self.unbind('<KeyRelease>')
        self.listening_btn = None
        self._ctrl_held    = False

    def apply(self):
        new_map = {}
        for cat_var, key_btn in self.slots:
            cat = cat_var.get()
            key = key_btn.cget("text")
            if cat != "-- None --" and key not in ["Click to Bind", "Press key…"]:
                new_map[key] = cat
        self.save_callback(new_map)
        self.destroy()


class LevelsDialog(ctk.CTkToplevel):
    def __init__(self, parent, stack_img, on_apply):
        super().__init__(parent)
        self.title("Live Levels Adjustment")
        nab_ui_scale.fit(self, 600, 700, min_w=372, min_h=434, parent=self.master)
        self.attributes('-topmost', True)
        self.orig_img = stack_img.copy()
        self.on_apply = on_apply
        self.result_img = self.orig_img.copy()
        self.preview_canvas = Canvas(self, bg="#000", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.preview_canvas.bind("<Configure>", self.update_preview)
        controls = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=15, border_width=1, border_color=C_BORDER)
        controls.pack(fill="x", padx=10, pady=(0, 10))
        self.b_var = ctk.DoubleVar(value=1.0)
        self.c_var = ctk.DoubleVar(value=1.0)
        ctk.CTkLabel(controls, text="Brightness", font=F_BODY, text_color="white").pack(anchor="w", padx=20, pady=(10, 0))
        ctk.CTkSlider(controls, variable=self.b_var, from_=0.2, to=2.5, button_color=C_ACCENT,
                      progress_color=C_ACCENT, command=self.update_preview).pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(controls, text="Contrast", font=F_BODY, text_color="white").pack(anchor="w", padx=20)
        ctk.CTkSlider(controls, variable=self.c_var, from_=0.2, to=3.0, button_color=C_ACCENT,
                      progress_color=C_ACCENT, command=self.update_preview).pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(self, text="APPLY", height=50, corner_radius=25, font=F_BTN,
                      fg_color=C_ACCENT, command=self.apply).pack(fill="x", padx=10, pady=(0, 10))

    def update_preview(self, *_):
        w, h = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        if w < 10 or h < 10: return
        if not hasattr(self, 'preview_orig'):
            ratio = min(w / self.orig_img.width, h / self.orig_img.height)
            self.preview_orig = self.orig_img.resize(
                (int(self.orig_img.width * ratio), int(self.orig_img.height * ratio)),
                Image.Resampling.BILINEAR)
        img = ImageEnhance.Brightness(self.preview_orig).enhance(self.b_var.get())
        img = ImageEnhance.Contrast(img).enhance(self.c_var.get())
        self.tk_img = ImageTk.PhotoImage(img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(w // 2, h // 2, image=self.tk_img, anchor="center")

    def apply(self):
        final_img = ImageEnhance.Brightness(self.orig_img).enhance(self.b_var.get())
        final_img = ImageEnhance.Contrast(final_img).enhance(self.c_var.get())
        self.on_apply(final_img)
        self.destroy()


class HistoryDialog(ctk.CTkToplevel):
    def __init__(self, parent, history_list, load_callback, delete_callback):
        super().__init__(parent)
        self.title("Session History")
        nab_ui_scale.fit(self, 500, 600, min_w=310, min_h=372, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        ctk.CTkLabel(self, text="RECENT SAVES", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=20)
        self.list_frame = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=15, border_width=1, border_color=C_BORDER)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        self.lst = Listbox(self.list_frame, bg=C_SURFACE, fg="white", font=("Consolas", 10),
                           selectbackground=C_ACCENT, selectforeground="white", bd=0, highlightthickness=0)
        self.lst.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.history = history_list
        self.load_callback = load_callback
        self.delete_callback = delete_callback
        self.refresh_list()
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btn_frame, text="RESTORE / EDIT", height=45, corner_radius=22, fg_color=C_ACCENT,
                      font=F_BTN, command=self.load_file).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(btn_frame, text="DELETE", height=45, corner_radius=22, fg_color="#333",
                      hover_color="#C62828", font=F_BTN, command=self.delete_file).pack(side="right", fill="x", expand=True, padx=5)

    def refresh_list(self):
        self.lst.delete(0, END)
        for item in reversed(self.history):
            self.lst.insert(END, f"[{item['time']}] {item['category']} -> {os.path.basename(item['path'])}")

    def load_file(self):
        sel = self.lst.curselection()
        if not sel: return
        real_index = len(self.history) - 1 - sel[0]
        self.load_callback(self.history[real_index]['path'])
        self.destroy()

    def delete_file(self):
        sel = self.lst.curselection()
        if not sel: return
        idx = len(self.history) - 1 - sel[0]
        if messagebox.askyesno("Delete", "Delete this file?"):
            try:
                if os.path.exists(self.history[idx]['path']): os.remove(self.history[idx]['path'])
                self.delete_callback(idx)
                self.refresh_list()
            except Exception as e:
                messagebox.showerror("Error", str(e))


class SourceManagerDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_list, save_callback, logo_dir):
        super().__init__(parent)
        self.title("Manage Sources")
        nab_ui_scale.fit(self, 450, 550, min_w=279, min_h=341, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.logo_dir = logo_dir
        ctk.CTkLabel(self, text="EDIT NEWSPAPERS", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=20)
        self.list_frame = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=15, border_width=1, border_color=C_BORDER)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        self.lst = Listbox(self.list_frame, bg=C_SURFACE, fg="white", font=("Arial", 11),
                           selectbackground=C_ACCENT, bd=0, highlightthickness=0)
        self.lst.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        for item in current_list: self.lst.insert(END, item)
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(ctrl, text="⬆", width=40, fg_color="#333", command=self.move_up).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="⬇", width=40, fg_color="#333", command=self.move_down).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="🖼 Change Logo", fg_color="#1A2A4A", hover_color="#24406B",
                     command=self.change_logo_for_selected).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="📅 Subscriptions", fg_color="#1A2A4A", hover_color="#24406B",
                     command=lambda: nab_subscriptions.open_subscription_manager(self.master)
                     ).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="Del", fg_color="#C62828", width=60, command=self.del_item).pack(side="right", padx=2)
        add_frame = ctk.CTkFrame(self, fg_color=C_SURFACE, border_color=C_BORDER, border_width=1)
        add_frame.pack(fill="x", padx=20, pady=10)
        self.new_name = ctk.CTkEntry(add_frame, placeholder_text="Name")
        self.new_name.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        logo_btns = ctk.CTkFrame(add_frame, fg_color="transparent")
        logo_btns.pack(side="right", padx=10, pady=10)
        ctk.CTkButton(logo_btns, text="📁 Browse", width=80, fg_color="#333",
                      command=self.add_item_with_logo).pack(side="left", padx=(0, 4))
        ctk.CTkButton(logo_btns, text="📸 Screenshot", width=100, fg_color="#333",
                      command=self.add_item_from_screenshot).pack(side="left")
        ctk.CTkButton(self, text="SAVE & CLOSE", height=45, corner_radius=22, fg_color=C_ACCENT, font=F_BTN,
                      command=lambda: [save_callback(list(self.lst.get(0, END))), self.destroy()]).pack(fill="x", padx=20, pady=(0, 20))

    def move_up(self):
        pos = self.lst.curselection()
        if not pos or pos[0] == 0: return
        t = self.lst.get(pos)
        self.lst.delete(pos)
        self.lst.insert(pos[0] - 1, t)
        self.lst.selection_set(pos[0] - 1)

    def move_down(self):
        pos = self.lst.curselection()
        if not pos or pos[0] == self.lst.size() - 1: return
        t = self.lst.get(pos)
        self.lst.delete(pos)
        self.lst.insert(pos[0] + 1, t)
        self.lst.selection_set(pos[0] + 1)

    def _insert_or_update(self, name):
        """BUG FIX: this used to unconditionally insert a new row, so typing
        an EXISTING paper's name here (to replace its logo) silently created
        a duplicate entry while the logo file underneath got overwritten
        correctly — the list and the Logos folder quietly fell out of sync.
        Now: if the name is already in the list, nothing new is inserted —
        only the logo file changes, which is what "change logo" is for."""
        existing = list(self.lst.get(0, END))
        if name in existing:
            return False   # already present — caller should say "updated"
        self.lst.insert(0, name)
        return True   # new entry — caller should say "added"

    def add_item_with_logo(self):
        name = self.new_name.get().strip()
        if not name: return
        file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if file_path:
            try:
                if not os.path.exists(self.logo_dir): os.makedirs(self.logo_dir)
                dest = os.path.join(self.logo_dir, f"{name}.png")
                Image.open(file_path).save(dest, "PNG")
                self._insert_or_update(name)
                self.new_name.delete(0, END)
            except Exception as e:
                messagebox.showerror("Error", str(e))
        elif messagebox.askyesno("No Logo", "Add without logo?"):
            self._insert_or_update(name)
            self.new_name.delete(0, END)

    def change_logo_for_selected(self):
        """🖼 Change Logo — operates on whichever paper is SELECTED in the
        list, not on retyped text. Typing a name to "update" a logo (the
        old only option) is one typo away from creating a stray duplicate
        instead of touching the paper you meant; selecting from the list
        can't have that problem."""
        sel = self.lst.curselection()
        if not sel:
            messagebox.showinfo("Pick a paper", "Select a paper in the list first.")
            return
        name = self.lst.get(sel[0])

        picker = ctk.CTkToplevel(self)
        picker.title(f"Change logo — {name}")
        picker.configure(fg_color=C_BG)
        nab_ui_scale.fit(picker, 360, 200, min_w=260, min_h=160, parent=self)
        picker.attributes('-topmost', True)
        picker.grab_set()

        ctk.CTkLabel(picker, text=f'New logo for "{name}"',
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT_MAIN, wraplength=320
                     ).pack(pady=(20, 4), padx=16)
        current = os.path.join(self.logo_dir, f"{name}.png")
        ctk.CTkLabel(picker,
                     text="Has a logo now" if os.path.exists(current) else "No logo set yet",
                     font=ctk.CTkFont(size=11),
                     text_color="#888" if os.path.exists(current) else "#F59E0B"
                     ).pack(pady=(0, 14))

        def _browse():
            picker.destroy()
            file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
            if file_path:
                try:
                    self._confirm_and_save_logo(name, Image.open(file_path).convert("RGB"))
                except Exception as e:
                    messagebox.showerror("Error", str(e))

        def _screenshot():
            picker.destroy()
            img = None
            try:
                for _ in range(3):
                    try:
                        img = ImageGrab.grabclipboard()
                        break
                    except Exception:
                        import time
                        time.sleep(0.1)
            except Exception as e:
                messagebox.showerror("Clipboard Error", str(e))
                return
            if isinstance(img, list):
                img = None
            if not isinstance(img, Image.Image):
                messagebox.showwarning(
                    "Nothing to paste",
                    "No image on the clipboard. Copy one first — Print "
                    "Screen, Win+Shift+S, or right-click an image and Copy.")
                return
            self._confirm_and_save_logo(name, img.convert("RGB"))

        btns = ctk.CTkFrame(picker, fg_color="transparent")
        btns.pack(pady=4)
        ctk.CTkButton(btns, text="📁 Browse", width=120, fg_color="#333",
                     command=_browse).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="📸 Screenshot", width=120, fg_color="#333",
                     command=_screenshot).pack(side="left", padx=6)

    def add_item_from_screenshot(self):
        """Grab whatever is on the clipboard right now (Print Screen, a
        Snipping Tool region, or Ctrl+C on an image anywhere) and use it as
        this paper's logo — same clipboard technique NAB already uses for
        pasting clips, so the workflow is: crop the logo out of the epaper
        or the paper's website with the Snipping Tool, then click this."""
        name = self.new_name.get().strip()
        if not name:
            messagebox.showwarning("Name required",
                                   "Type the paper's name first, then "
                                   "take your screenshot/copy the logo, "
                                   "then press 📸 Screenshot.")
            return
        try:
            img = None
            for _ in range(3):
                try:
                    img = ImageGrab.grabclipboard()
                    break
                except Exception:
                    import time
                    time.sleep(0.1)
        except Exception as e:
            messagebox.showerror("Clipboard Error", str(e))
            return

        if isinstance(img, list):   # a file path was copied, not an image
            img = None
        if not isinstance(img, Image.Image):
            messagebox.showwarning(
                "Nothing to paste",
                "No image found on the clipboard. Copy an image first — "
                "Print Screen, Win+Shift+S, or right-click an image and "
                "Copy — then try again.")
            return

        self._confirm_and_save_logo(name, img.convert("RGB"))

    def _confirm_and_save_logo(self, name, img):
        """Small preview so a bad screenshot (wrong window, wrong region)
        gets caught before it's saved as the paper's permanent logo."""
        prev = ctk.CTkToplevel(self)
        prev.title("Confirm Logo")
        prev.configure(fg_color=C_BG)
        nab_ui_scale.fit(prev, 360, 420, min_w=240, min_h=280, parent=self)
        prev.attributes('-topmost', True)
        prev.grab_set()

        ctk.CTkLabel(prev, text=f"Use this as the logo for \"{name}\"?",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=C_TEXT_MAIN, wraplength=320
                     ).pack(pady=(16, 8), padx=16)

        disp = img.copy()
        disp.thumbnail((300, 260), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(disp)
        pic_lbl = ctk.CTkLabel(prev, image=photo, text="")
        pic_lbl.image = photo   # keep a reference — CTkLabel doesn't hold one
        pic_lbl.pack(pady=6)

        btns = ctk.CTkFrame(prev, fg_color="transparent")
        btns.pack(pady=14)

        def _confirm():
            try:
                if not os.path.exists(self.logo_dir):
                    os.makedirs(self.logo_dir)
                dest = os.path.join(self.logo_dir, f"{name}.png")
                img.save(dest, "PNG")
                is_new = self._insert_or_update(name)
                self.new_name.delete(0, END)
                prev.destroy()
                if not is_new:
                    messagebox.showinfo("Logo updated", f'Logo updated for "{name}".')
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=prev)

        ctk.CTkButton(btns, text="✅ Use This", width=120, fg_color=C_SUCCESS,
                     command=_confirm).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="❌ Cancel", width=100, fg_color="#C62828",
                     command=prev.destroy).pack(side="left", padx=6)

    def del_item(self):
        p = self.lst.curselection()
        if p: self.lst.delete(p)


class MultiInputDialog(ctk.CTkToplevel):
    def __init__(self, parent, p_val, po_val, s_val):
        super().__init__(parent)
        self.title("Details")
        nab_ui_scale.fit(self, 350, 430, min_w=217, min_h=266, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.result = None
        ctk.CTkLabel(self, text="METADATA", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=20)
        f = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=15, border_width=1, border_color=C_BORDER)
        f.pack(fill="both", padx=25, pady=5)
        def mk_entry(ph, val):
            e = ctk.CTkEntry(f, placeholder_text=ph, font=F_BODY, height=40, corner_radius=10,
                             fg_color="#000", border_color=C_BORDER, text_color="white")
            e.insert(0, val)
            e.pack(pady=8, padx=15, fill="x")
            return e
        self.e1 = mk_entry("Page No.", p_val)
        self.e2 = mk_entry("Position", po_val)
        self.e3 = mk_entry("Size", s_val)
        # Note field removed — not used, and it was also getting drawn onto
        # every saved image's header text, which nobody wanted there either.
        ctk.CTkButton(self, text="COMMIT", height=50, corner_radius=25, fg_color=C_ACCENT,
                      font=F_BTN, command=self.on_confirm).pack(pady=15, padx=25, fill="x")
        self.bind("<Return>", lambda e: self.on_confirm())
        # Delay focus so the window is fully mapped before grabbing it.
        # Without the delay, focus_set() is ignored on Windows because
        # CTkToplevel hasn't finished rendering when __init__ returns.
        self.after(50, self._grab_focus)

    def _grab_focus(self):
        try:
            self.lift()
            self.focus_force()
            self.e1.focus_set()
            # Select all text in Page field so user can type immediately
            self.e1.select_range(0, 'end')
            self.e1.icursor('end')
        except Exception:
            pass

    def on_confirm(self):
        self.result = (self.e1.get(), self.e2.get(), self.e3.get())
        self.destroy()


class BroadcastDialog(ctk.CTkToplevel):
    """Feature 45: Select username for broadcast"""
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title("Broadcast Message")
        nab_ui_scale.fit(self, 420, 320, min_w=260, min_h=198, parent=self.master)
        self.configure(fg_color=C_BG)
        self.attributes('-topmost', True)
        self.callback = callback

        ctk.CTkLabel(self, text="BROADCAST", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=15)

        f = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=10, border_width=1, border_color=C_BORDER)
        f.pack(fill="both", expand=True, padx=20, pady=5)

        ctk.CTkLabel(f, text="Target:", font=F_BTN, text_color="#aaa").pack(anchor="w", padx=15, pady=(15,0))
        self.target_var = ctk.StringVar(value="This PC")
        opts = ["This PC", "All PCs", "Telegram Chat", "@custom_username"]
        self.target_menu = ctk.CTkOptionMenu(f, variable=self.target_var, values=opts,
                                              fg_color="#000", button_color=C_ACCENT)
        self.target_menu.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(f, text="Custom username (if selected above):", font=("Segoe UI", 9), text_color="#555").pack(anchor="w", padx=15)
        self.custom_username = ctk.CTkEntry(f, placeholder_text="@username or chat_id", fg_color="#000", border_color=C_BORDER)
        self.custom_username.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(f, text="Message:", font=F_BTN, text_color="#aaa").pack(anchor="w", padx=15, pady=(5,0))
        self.msg_entry = ctk.CTkEntry(f, placeholder_text="Type your message...", fg_color="#000", border_color=C_BORDER)
        self.msg_entry.pack(fill="x", padx=15, pady=(5,15))

        ctk.CTkButton(self, text="SEND", height=45, corner_radius=22, fg_color=C_ACCENT,
                      font=F_BTN, command=self.send).pack(fill="x", padx=20, pady=10)

    def send(self):
        target = self.target_var.get()
        msg = self.msg_entry.get().strip()
        custom = self.custom_username.get().strip()
        if msg:
            self.callback(target, msg, custom)
        self.destroy()

