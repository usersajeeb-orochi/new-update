# nab_recent.py — Recent Saves panel: retag, reopen, delete, show in folder.
import os
import re
import logging
import subprocess

_NAME_RE = re.compile(
    r"^(?P<paper>.+?), Page-(?P<page>[^,]*), Pos-(?P<pos>[^,]*), S-(?P<size>[^,]*), "
    r"Date-(?P<date>[\d\-]+)(?P<dup>_\d+)?(?P<ext>\.\w+)$")


def parse_clip_name(path):
    """Filename -> dict(paper,page,pos,size,date,ext) or None."""
    m = _NAME_RE.match(os.path.basename(path or ""))
    return m.groupdict() if m else None


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "", str(s)).strip()


def build_name(parts, **changes):
    d = dict(parts)
    d.update({k: v for k, v in changes.items() if v is not None})
    return (f"{_safe(d['paper'])}, Page-{_safe(d['page'])}, Pos-{_safe(d['pos'])}, "
            f"S-{_safe(d['size'])}, Date-{d['date']}{d.get('dup') or ''}{d['ext']}")


def retag_file(path, paper=None, page=None, pos=None, size=None):
    """Rename a saved clip. Returns (new_path, error_or_None). Never overwrites."""
    parts = parse_clip_name(path)
    if not parts:
        return path, "File name isn't in the standard NAB format."
    if not os.path.exists(path):
        return path, "File no longer exists."
    new_name = build_name(parts, paper=paper, page=page, pos=pos, size=size)
    new_path = os.path.join(os.path.dirname(path), new_name)
    if os.path.normcase(new_path) == os.path.normcase(path):
        return path, None
    if os.path.exists(new_path):
        return path, "A file with that name already exists in this folder."
    try:
        os.rename(path, new_path)
    except Exception as e:
        logging.error(f"retag_file: {e}")
        return path, str(e)
    return new_path, None


def show_in_folder(path):
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception as e:
        logging.error(f"show_in_folder: {e}")


def open_recent_saves(app, limit=20):
    """Builds the dialog lazily so this module imports without Tk."""
    import customtkinter as ctk
    from tkinter import Listbox, END, messagebox
    from nab_constants import (C_BG, C_SURFACE, C_ACCENT, C_BORDER, C_TEXT_MAIN,
                               C_TEXT_DIM, F_HEADER, F_BTN, strip_emoji_prefix)
    import nab_ui_scale

    win = ctk.CTkToplevel(app)
    win.title("Recent Saves")
    nab_ui_scale.fit(win, 640, 560, min_w=372, min_h=403, parent=app)
    win.configure(fg_color=C_BG)
    win.attributes("-topmost", True)
    ctk.CTkLabel(win, text="RECENT SAVES", font=F_HEADER, text_color=C_TEXT_MAIN).pack(pady=(14, 2))
    ctk.CTkLabel(win, text="Fix a wrong paper / page / position without re-clipping.",
                 font=("Arial", 11), text_color=C_TEXT_DIM).pack()

    frame = ctk.CTkFrame(win, fg_color=C_SURFACE, corner_radius=12, border_width=1, border_color=C_BORDER)
    frame.pack(fill="both", expand=True, padx=16, pady=8)
    lst = Listbox(frame, bg=C_SURFACE, fg="white", font=("Consolas", 10), selectbackground=C_ACCENT,
                  selectforeground="black", bd=0, highlightthickness=0, activestyle="none")
    lst.pack(fill="both", expand=True, padx=8, pady=8)

    # edit row
    edit = ctk.CTkFrame(win, fg_color="transparent")
    edit.pack(fill="x", padx=16)
    fields = {}
    for key, label, w in (("paper", "Paper", 150), ("page", "Page", 50), ("pos", "Pos", 60), ("size", "Size", 60)):
        ctk.CTkLabel(edit, text=label, font=("Arial", 10), text_color=C_TEXT_DIM).pack(side="left", padx=(4, 2))
        e = ctk.CTkEntry(edit, width=w, fg_color="#000", border_color=C_BORDER)
        e.pack(side="left", padx=(0, 4))
        fields[key] = e
    status = ctk.CTkLabel(win, text="", font=("Arial", 11), text_color=C_TEXT_DIM)
    status.pack(pady=(4, 0))

    rows = []   # indexes into app.session_history, newest first

    def refresh(keep=None):
        lst.delete(0, END)
        rows.clear()
        hist = app.session_history
        for i in range(len(hist) - 1, -1, -1):
            h = hist[i]
            if len(rows) >= limit:
                break
            if not os.path.exists(h.get("path", "")):
                continue
            rows.append(i)
            lst.insert(END, f"[{h.get('time','')}] {h.get('category','?')[:26]:26} {os.path.basename(h['path'])}")
        if keep is not None and keep in rows:
            lst.selection_set(rows.index(keep))

    def current():
        sel = lst.curselection()
        return rows[sel[0]] if sel else None

    def on_select(_=None):
        i = current()
        if i is None:
            return
        parts = parse_clip_name(app.session_history[i]["path"]) or {}
        for k, e in fields.items():
            e.delete(0, END)
            e.insert(0, parts.get(k, ""))
        status.configure(text="", text_color=C_TEXT_DIM)

    lst.bind("<<ListboxSelect>>", on_select)

    def apply_retag():
        i = current()
        if i is None:
            return
        h = app.session_history[i]
        new_path, err = retag_file(h["path"],
                                   paper=strip_emoji_prefix(fields["paper"].get()),
                                   page=fields["page"].get(), pos=fields["pos"].get(),
                                   size=fields["size"].get())
        if err:
            status.configure(text=err, text_color="#EF4444")
            return
        h["path"] = new_path
        refresh(keep=i)
        status.configure(text="✔ Renamed. (The header baked into the image is unchanged — "
                              "use Reopen to re-render it.)", text_color="#22C55E")

    def reopen():
        i = current()
        if i is None:
            return
        app.load_image_from_path(app.session_history[i]["path"])
        win.destroy()

    def delete():
        i = current()
        if i is None:
            return
        p = app.session_history[i]["path"]
        if messagebox.askyesno("Delete", f"Delete this file?\n\n{os.path.basename(p)}", parent=win):
            try:
                os.remove(p)
            except Exception as e:
                status.configure(text=str(e), text_color="#EF4444")
                return
            app.delete_from_history(i)
            refresh()

    def reveal():
        i = current()
        if i is not None:
            show_in_folder(app.session_history[i]["path"])

    bar = ctk.CTkFrame(win, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=10)
    for text, cmd, col in (("✏ RETAG", apply_retag, C_ACCENT), ("↩ REOPEN", reopen, "#2A4A7A"),
                           ("📂 SHOW", reveal, "#333"), ("🗑 DELETE", delete, "#7A2020")):
        ctk.CTkButton(bar, text=text, height=38, fg_color=col, font=F_BTN,
                      text_color="black" if col == C_ACCENT else "white",
                      command=cmd).pack(side="left", fill="x", expand=True, padx=3)
    refresh()
    return win
