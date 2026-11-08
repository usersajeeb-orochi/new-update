# nab_subscriptions.py — paper subscription expiry dates + reminder popup.
#
# Storage: one small JSON file in Documents, {"Paper Name": "DD-MM-YYYY"}.
# Nothing here assumes every paper has a date set — papers with no expiry
# on file are simply never checked (not everything is a paid subscription).
#
import os
import json
import logging
import datetime
import customtkinter as ctk
from tkinter import messagebox

import nab_ui_scale
import nab_batch   # reusing its self-contained strip_emoji_prefix — see its
                    # docstring for why this isn't read off the app instance

try:
    from nab_constants import HAS_CALENDAR
    if HAS_CALENDAR:
        from tkcalendar import Calendar
except ImportError:
    HAS_CALENDAR = False

SUBS_FILE = os.path.join(os.path.expanduser("~"), "Documents",
                         "nab_subscription_expiry.json")
WARN_DAYS_BEFORE = 3


def load_expiries():
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logging.error(f"load_expiries: {e}")
    return {}


def save_expiries(data):
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"save_expiries: {e}")
        return False


def _parse(date_str):
    try:
        return datetime.datetime.strptime(date_str, "%d-%m-%Y").date()
    except Exception:
        return None


def _days_until(date_str):
    d = _parse(date_str)
    if d is None:
        return None
    return (d - datetime.date.today()).days


def expiring_soon(known_papers=None):
    """Papers whose expiry is today, already past, or within
    WARN_DAYS_BEFORE days — sorted soonest first. Returns
    [(paper, date_str, days_left), ...]. If known_papers is given, entries
    for papers no longer in the source list are skipped (renamed/removed
    papers shouldn't keep nagging forever)."""
    data = load_expiries()
    out = []
    for paper, date_str in data.items():
        if known_papers is not None and paper not in known_papers:
            continue
        days = _days_until(date_str)
        if days is not None and days <= WARN_DAYS_BEFORE:
            out.append((paper, date_str, days))
    out.sort(key=lambda t: t[2])
    return out


# ─────────────────────────────────────────────────────────────────────────
# STARTUP / PERIODIC CHECK
# ─────────────────────────────────────────────────────────────────────────
def _known_papers(app):
    """Subscription dates are keyed by the emoji-STRIPPED paper name (same
    form the archive and tracker use) — app.paper_list holds the display
    form with the emoji prefix still on it. Comparing the two directly
    would never match anything, silently filtering every subscription out."""
    papers = getattr(app, "paper_list", []) or []
    return {nab_batch.strip_emoji_prefix(p) for p in papers}


def check_and_remind(app):
    """Call at startup and periodically (app schedules the repeat — see
    schedule_periodic_check). Shows the modal reminder once per calendar
    day for whatever's currently expiring; renewing a paper (which updates
    its date) removes it from the list immediately, so it stops nagging
    about that one without silencing the feature entirely."""
    today_str = datetime.date.today().isoformat()
    if getattr(app, "_subs_last_shown_date", None) == today_str:
        return
    items = expiring_soon(known_papers=_known_papers(app))
    if not items:
        return
    app._subs_last_shown_date = today_str
    _show_reminder(app, items)


def schedule_periodic_check(app, interval_hours=6):
    """NAB can stay open for days — re-check periodically, not just at
    launch, so a paper that crosses into the 3-day window while NAB is
    already running still gets flagged the same day it should."""
    def _tick():
        check_and_remind(app)
        app.after(interval_hours * 3600 * 1000, _tick)
    app.after(interval_hours * 3600 * 1000, _tick)


def _show_reminder(app, items):
    win = ctk.CTkToplevel(app)
    win.title("Subscription expiry reminder")
    win.configure(fg_color="#08080E")
    nab_ui_scale.fit(win, 460, 440, min_w=320, min_h=300, parent=app)
    win.attributes("-topmost", True)
    win.grab_set()   # modal — has to be dealt with, not just clicked past

    ctk.CTkLabel(win, text="📅 Subscriptions needing attention",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#F59E0B").pack(pady=(18, 4), padx=16)
    ctk.CTkLabel(win, text="This stays open until you close it — just so "
                        "it's definitely seen, not missed.",
                font=ctk.CTkFont(size=11), text_color="#666",
                wraplength=400).pack(pady=(0, 10), padx=16)

    body = ctk.CTkScrollableFrame(win, fg_color="#0D0D14")
    body.pack(fill="both", expand=True, padx=16, pady=6)

    def _rebuild_rows():
        for w in body.winfo_children():
            w.destroy()
        current = expiring_soon(known_papers=_known_papers(app))
        if not current:
            ctk.CTkLabel(body, text="✅ All caught up.",
                        font=ctk.CTkFont(size=12), text_color="#22C55E"
                        ).pack(pady=20)
            return
        for paper, date_str, days in current:
            row = ctk.CTkFrame(body, fg_color="#1A1400" if days >= 0 else "#2A0A0A",
                               corner_radius=8)
            row.pack(fill="x", pady=4, padx=2)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=8)

            status = (f"expired {abs(days)} day{'s' if abs(days) != 1 else ''} ago"
                     if days < 0 else
                     ("expires today" if days == 0 else
                      f"expires in {days} day{'s' if days != 1 else ''}"))
            color = "#EF4444" if days <= 0 else "#F59E0B"
            ctk.CTkLabel(inner, text=f"{paper}", font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#EEE", anchor="w").pack(anchor="w")
            ctk.CTkLabel(inner, text=f"{status} ({date_str})",
                        font=ctk.CTkFont(size=11), text_color=color,
                        anchor="w").pack(anchor="w")

            ctk.CTkButton(inner, text="✅ Renewed — set new date", height=26,
                         fg_color="#22C55E", hover_color="#1ca34e",
                         font=ctk.CTkFont(size=10),
                         command=lambda p=paper: _pick_new_date(app, p, _rebuild_rows)
                         ).pack(anchor="e", pady=(4, 0))

    _rebuild_rows()

    ctk.CTkButton(win, text="Close", height=38, fg_color="#333",
                 command=win.destroy).pack(pady=14, padx=16, fill="x")


def _pick_new_date(app, paper, on_saved):
    top = ctk.CTkToplevel(app)
    top.title(f"New expiry — {paper}")
    nab_ui_scale.fit(top, 300, 320, parent=app)
    top.configure(fg_color="#08080E")
    top.attributes("-topmost", True)
    top.grab_set()

    ctk.CTkLabel(top, text=paper, font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#F59E0B").pack(pady=(14, 8))

    if HAS_CALENDAR:
        cal = Calendar(top, selectmode="day", date_pattern="dd-mm-yyyy")
        cal.pack(pady=4, padx=10, fill="both", expand=True)

        def _confirm():
            data = load_expiries()
            data[paper] = cal.get_date()
            save_expiries(data)
            top.destroy()
            on_saved()
        ctk.CTkButton(top, text="Save", command=_confirm, fg_color="#22C55E",
                     height=36).pack(pady=10, padx=16, fill="x")
    else:
        ctk.CTkLabel(top, text="Enter date (DD-MM-YYYY)", text_color="#AAA"
                    ).pack(pady=6)
        e = ctk.CTkEntry(top, placeholder_text="DD-MM-YYYY")
        e.pack(pady=4, padx=16, fill="x")

        def _confirm():
            if _parse(e.get().strip()) is None:
                messagebox.showerror("Invalid date", "Use DD-MM-YYYY.", parent=top)
                return
            data = load_expiries()
            data[paper] = e.get().strip()
            save_expiries(data)
            top.destroy()
            on_saved()
        ctk.CTkButton(top, text="Save", command=_confirm, fg_color="#22C55E",
                     height=36).pack(pady=10, padx=16, fill="x")


# ─────────────────────────────────────────────────────────────────────────
# MANAGE ALL SUBSCRIPTIONS (set initial dates, edit any time)
# ─────────────────────────────────────────────────────────────────────────
def open_subscription_manager(app):
    win = ctk.CTkToplevel(app)
    win.title("Manage Subscriptions")
    win.configure(fg_color="#08080E")
    nab_ui_scale.fit(win, 480, 560, min_w=320, min_h=360, parent=app)
    win.attributes("-topmost", True)
    win.grab_set()

    ctk.CTkLabel(win, text="📅 Subscription Expiry Dates",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="#F59E0B").pack(pady=(16, 4))
    ctk.CTkLabel(win, text=f"You'll get a reminder {WARN_DAYS_BEFORE} days "
                        f"before any of these run out.",
                font=ctk.CTkFont(size=11), text_color="#666").pack(pady=(0, 10))

    body = ctk.CTkScrollableFrame(win, fg_color="#0D0D14")
    body.pack(fill="both", expand=True, padx=16, pady=6)

    def _rebuild():
        for w in body.winfo_children():
            w.destroy()
        data = load_expiries()
        papers = getattr(app, "paper_list", []) or []
        for raw in papers:
            paper = nab_batch.strip_emoji_prefix(raw)
            row = ctk.CTkFrame(body, fg_color="#151520", corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=paper, font=ctk.CTkFont(size=12),
                        text_color="#CCC", anchor="w", width=180
                        ).pack(side="left", padx=8, pady=6)
            date_str = data.get(paper, "— not set —")
            ctk.CTkLabel(row, text=date_str, font=ctk.CTkFont(size=11),
                        text_color="#888" if paper in data else "#444"
                        ).pack(side="left", padx=4)
            ctk.CTkButton(row, text="Edit", width=50, height=24,
                         fg_color="#333", font=ctk.CTkFont(size=10),
                         command=lambda p=paper: _pick_new_date(app, p, _rebuild)
                         ).pack(side="right", padx=8)

    _rebuild()
    ctk.CTkButton(win, text="Close", height=36, fg_color="#333",
                 command=win.destroy).pack(pady=12, padx=16, fill="x")
