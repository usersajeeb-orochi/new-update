# nab_sync_ui.py — "🔄 Sync" dialog: status, sync now, change history.
import os
import time
import threading
import customtkinter as ctk
from tkinter import Listbox, END, messagebox

from nab_constants import (C_BG, C_SURFACE, C_ACCENT, C_BORDER, C_TEXT_MAIN,
                           C_TEXT_DIM, F_HEADER, F_BTN)
import nab_ui_scale
import nab_settings_sync as S


def _status_text(app):
    mgr = getattr(app, "_sync", None)
    last = getattr(mgr, "last", {}) or {}
    if not last.get("time"):
        return "● Waiting for the first sync…", C_ACCENT
    if last.get("no_drive"):
        return ("● This build has no Google key bundled, so settings stay on this PC only. "
                "Rebuild with the key next to BUILD.bat (Settings → Advanced shows the status)."), "#EF4444"
    ago = int(time.time() - last["time"])
    res = last.get("result")
    if res and res.get("offline"):
        return f"● Couldn't reach Google Drive ({ago}s ago). Using local settings; will retry.", "#EF4444"
    bits = []
    if res:
        if res["pulled"]: bits.append("received: " + ", ".join(res["pulled"]))
        if res["pushed"]: bits.append("sent: " + ", ".join(res["pushed"]))
        if res["conflicts"]: bits.append("⚠ conflicts (your copy saved): " + ", ".join(res["conflicts"]))
    return (f"● Synced {ago}s ago" + (" — " + "; ".join(bits) if bits else " — everything up to date")), \
        ("#F59E0B" if res and res["conflicts"] else "#22C55E")


def open_sync_dialog(app):
    from nab_telegram import PC_NAME

    win = ctk.CTkToplevel(app)
    win.title("Settings Sync")
    nab_ui_scale.fit(win, 600, 520, min_w=372, min_h=380, parent=app)
    win.configure(fg_color=C_BG)
    win.attributes("-topmost", True)
    ctk.CTkLabel(win, text="SETTINGS SYNC", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=(14, 0))
    ctk.CTkLabel(win, text=f"This PC: {PC_NAME}  ·  syncs through your Google Drive folder",
                 font=("Arial", 11), text_color=C_TEXT_DIM).pack()
    status = ctk.CTkLabel(win, text="", font=("Arial", 12), wraplength=540, justify="left")
    status.pack(padx=20, pady=8, anchor="w")

    ctk.CTkLabel(win, text="CHANGE HISTORY", font=F_BTN, text_color=C_TEXT_MAIN).pack(anchor="w", padx=20)
    top = ctk.CTkFrame(win, fg_color="transparent")
    top.pack(fill="x", padx=20, pady=(2, 0))
    ns_var = ctk.StringVar(value="app_settings")
    names = {"app_settings": "Settings & hotkeys", "url_mappings": "URL mappings", "sources": "Paper list",
             "categories": "Categories", "subscriptions": "Subscriptions", "paper_aliases": "Aliases",
             "pdf_maker": "PDF Maker"}
    ctk.CTkOptionMenu(top, variable=ns_var, values=list(names), fg_color="#1A1A1A", button_color=C_ACCENT,
                      width=170, command=lambda _: load_history()).pack(side="left")
    lst = Listbox(win, bg=C_SURFACE, fg="white", font=("Consolas", 10), selectbackground=C_ACCENT,
                  bd=0, highlightthickness=0, activestyle="none", height=9)
    lst.pack(fill="both", expand=True, padx=20, pady=6)

    def load_history():
        lst.delete(0, END)
        client = (getattr(app._sync, "last", {}) or {}).get("client")
        if not client:
            lst.insert(END, "No history yet — it appears after the first successful sync.")
            return
        lst.insert(END, "Loading…")

        def work():
            try:
                entries = client.get_config_history(ns_var.get(), 30)
            except Exception:
                entries = []

            def done():
                if not win.winfo_exists():
                    return
                lst.delete(0, END)
                if not entries:
                    lst.insert(END, "No changes recorded for this group yet.")
                for e in entries:
                    when = (e.get("at", "") or "")[:16].replace("T", " ")
                    lst.insert(END, f"{when}  {e.get('pc_name','?'):14.14} v{e.get('version','?'):<3} {e.get('summary','')}")
            win.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def refresh():
        if not win.winfo_exists():
            return
        t, col = _status_text(app)
        status.configure(text=t, text_color=col)
        load_history()

    def sync_now():
        status.configure(text="Syncing…", text_color=C_TEXT_DIM)
        app._sync.sync_now()
        win.after(4000, refresh)

    def open_log():
        try:
            if not os.path.exists(S.LOG_FILE):
                open(S.LOG_FILE, "a").close()
            os.startfile(S.LOG_FILE)
        except Exception as e:
            messagebox.showinfo("Sync log", f"{S.LOG_FILE}\n\n{e}", parent=win)

    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill="x", padx=20, pady=(0, 14))
    ctk.CTkButton(bar, text="🔄 SYNC NOW", fg_color=C_ACCENT, text_color="black", command=sync_now).pack(side="left", padx=3)
    ctk.CTkButton(bar, text="📜 LOCAL LOG", fg_color="#333", command=open_log).pack(side="left", padx=3)
    ctk.CTkButton(bar, text="↻ HISTORY", fg_color="#333", command=load_history).pack(side="left", padx=3)
    refresh()
    return win
