# ═══════════════════════════════════════════════════════════════════════════════
#  NAB NEWSPAPER TRACKER  v2.0  —  nab_tracker.py
#  Drop next to NAB.pyw. Integration instructions at bottom of this file.
# ═══════════════════════════════════════════════════════════════════════════════

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import json, os, datetime, threading, winreg, calendar
import logging
import requests

import nab_ui_scale
import nab_clip_scan
import nab_loading

# Google Sheets support via gspread + google-auth
# Install once:  pip install gspread google-auth
try:
    import gspread
    from google.oauth2.service_account import Credentials as _SACredentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

# ── NAB Theme ──────────────────────────────────────────────────────────────────
C_BG      = "#050505"
C_SURF    = "#111111"
C_SURF2   = "#1A1A1A"
C_ACCENT  = "#ff9500"
C_RED     = "#FF3131"
C_BORDER  = "#2A2A2A"
C_SUCCESS = "#10B981"
C_DANGER  = "#D32F2F"
C_BLUE    = "#1A6BAA"
C_DIM     = "#555555"

import nab_connections as _nc

# ── Registry ───────────────────────────────────────────────────────────────────
REG_PATH = r"Software\NAB\Tracker"

def _rget(key, default=""):
    try:
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        v, _ = winreg.QueryValueEx(hk, key); winreg.CloseKey(hk); return v
    except: return default

def _rset(key, value):
    try:
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(hk, key, 0, winreg.REG_SZ, str(value)); winreg.CloseKey(hk)
    except Exception as e: print(f"[Tracker] reg: {e}")

# ── Persistent data paths ───────────────────────────────────────────────────────
_DOC = os.path.join(os.path.expanduser("~"), "Documents")
LOG_FILE     = os.path.join(_DOC, "nab_tracker_log.json")
PAPERS_FILE  = os.path.join(_DOC, "nab_tracker_papers.json")

# ── Default paper list ─────────────────────────────────────────────────────────
DEFAULT_PAPERS = [
    "The Daily Star",    "TBS",                "Financial Express",
    "Daily Observer",    "Dhaka Tribune",       "New Age",
    "Daily Sun",         "New Nation",          "Asian Age",
    "Bangladesh Today",  "Times of Bangladesh", "Prothom Alo",
    "Samakal",           "Ittefaq",             "Jugantor",
    "Kaler Kantha",      "Janakantha",          "Naya Diganta",
    "Daily Inqilab",     "Bonik Barta",         "Bangladesh Pratidin",
    "Sangbad",           "Jaijaidin",           "Manabzamin",
    "Amader Shomoy",     "Ajker Patrika",       "Protidiner Bangladesh",
    "Shomoyer Alo",      "Pratidiner Sangbad",  "Desh Rupantor",
    "Kalbela",           "Rupali Bangladesh",   "Agamirsomoy",
    "Amardesh",          "Alokito Bangladesh",
]

DEFAULT_PRICES = {
    "The Daily Star":15.0,"TBS":12.0,"Financial Express":15.0,
    "Daily Observer":12.0,"Dhaka Tribune":12.0,"New Age":15.0,
    "Daily Sun":12.0,"New Nation":15.0,"Asian Age":10.0,
    "Bangladesh Today":10.0,"Times of Bangladesh":10.0,"Prothom Alo":12.0,
    "Samakal":12.0,"Ittefaq":8.0,"Jugantor":10.0,"Kaler Kantha":8.0,
    "Janakantha":9.0,"Naya Diganta":9.0,"Daily Inqilab":7.0,"Bonik Barta":7.0,
    "Bangladesh Pratidin":7.0,"Sangbad":5.0,"Jaijaidin":8.0,"Manabzamin":6.0,
    "Amader Shomoy":6.0,"Ajker Patrika":3.0,"Protidiner Bangladesh":5.0,
    "Shomoyer Alo":4.0,"Pratidiner Sangbad":4.0,"Desh Rupantor":4.0,
    "Kalbela":5.0,"Rupali Bangladesh":3.0,"Agamirsomoy":3.0,
    "Amardesh":10.0,"Alokito Bangladesh":4.0,
}

# ── Load / save paper list ─────────────────────────────────────────────────────
def load_papers():
    try:
        if os.path.exists(PAPERS_FILE):
            with open(PAPERS_FILE) as f: return json.load(f)
    except: pass
    return list(DEFAULT_PAPERS)

def save_papers(lst):
    with open(PAPERS_FILE, "w") as f: json.dump(lst, f, indent=2)

def load_prices():
    raw = _rget("prices")
    if raw:
        try: return json.loads(raw)
        except: pass
    return dict(DEFAULT_PRICES)

def save_prices(p): _rset("prices", json.dumps(p))

def load_cfg():
    return {
        "tg_token":      _rget("tg_token"),
        "tg_chat_id":    _rget("tg_chat_id"),
        "remind_hour":   _rget("remind_hour", "18"),
        # Built in (nab_connections); a value typed in the tracker's own
        # settings still wins for this PC.
        "gs_creds_path": (_rget("gs_creds_path") if os.path.isfile(_rget("gs_creds_path") or "")
                          else _nc.google_key_file()),
        "gs_sheet_id":   _rget("gs_sheet_id") or _nc.sheet_id(),
    }

def save_cfg(c):
    for k,v in c.items():
        # Don't freeze the built-in defaults into the registry — keeps future
        # app updates able to change them.
        if k == "gs_sheet_id" and v == _nc.BUILTIN_SHEET_ID: v = ""
        if k == "gs_creds_path" and v == _nc.google_key_file() and not _rget("gs_creds_path"): v = ""
        _rset(k,v)

# ── Log helpers ────────────────────────────────────────────────────────────────
def _load_log():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f: return json.load(f)
    except: pass
    return {}

def _save_log(log):
    try:
        with open(LOG_FILE,"w") as f: json.dump(log, f, indent=2)
    except Exception as e: print(f"[Tracker] log save: {e}")

def _log_entry(date_iso, status, received=None, missing=None, prices=None, total=0.0):
    log = _load_log()
    log[date_iso] = {
        "status": status,               # submitted | off_day | auto_missed
        "received": received or [],
        "missing":  missing  or [],
        "prices":   prices   or {},
        "total":    total,
        "updated":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_log(log)

def _get_month_stats(year, month):
    log = _load_log()
    prefix = f"{year:04d}-{month:02d}"
    total = 0.0; submitted = off = missed = 0
    for k, v in log.items():
        if not k.startswith(prefix): continue
        s = v.get("status","")
        if s == "submitted":   total += v.get("total",0); submitted += 1
        elif s == "off_day":   off += 1
        elif s == "auto_missed": missed += 1
    return total, submitted, off, missed

# ── Auto-backfill missed days on startup ───────────────────────────────────────
def backfill_missed_days():
    """Called on app start — silently marks any unrecorded past days as auto_missed."""
    log   = _load_log()
    today = datetime.date.today()
    if not log:
        # First ever run — there is no history to have "missed". The old code
        # stamped 30 auto_missed days here, which permanently skewed the
        # month counters on every freshly deployed PC.
        return
    earliest = min(log.keys())
    # look back up to 30 days
    for i in range(1, 31):
        d = today - datetime.timedelta(days=i)
        iso = d.isoformat()
        if iso < earliest:
            break   # before this PC started tracking — not a missed day
        if iso not in log:
            _log_entry(iso, "auto_missed")
        else:
            break   # stop at first recorded day (no gap)

# ── Google Sheets ───────────────────────────────────────────────────────────────
# Color hex values for cell backgrounds (used via gspread's userEnteredFormat)
_GS_GREEN  = {"red": 0.83, "green": 0.93, "blue": 0.85}   # received
_GS_RED    = {"red": 0.97, "green": 0.84, "blue": 0.85}   # missing
_GS_BLUE   = {"red": 0.82, "green": 0.89, "blue": 1.00}   # off day
_GS_ORANGE = {"red": 1.00, "green": 0.95, "blue": 0.80}   # auto missed
_GS_HEADER = {"red": 0.12, "green": 0.31, "blue": 0.47}   # header row

_GS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _gs_client(creds_path):
    """Return an authenticated gspread client using a service-account JSON file."""
    if not HAS_GSPREAD:
        raise RuntimeError(
            "gspread is not installed.\n"
            "Run:  pip install gspread google-auth"
        )
    creds = _SACredentials.from_service_account_file(creds_path, scopes=_GS_SCOPES)
    return gspread.authorize(creds)

def _get_or_create_worksheet(spreadsheet, month_label, papers):
    """Return the worksheet for this month, creating and formatting it if needed."""
    try:
        ws = spreadsheet.worksheet(month_label)
        return ws
    except gspread.WorksheetNotFound:
        pass

    # Create a new sheet tab for this month
    ws = spreadsheet.add_worksheet(
        title=month_label,
        rows=len(papers) + 10,
        cols=34,   # SL + Paper + days 1-31 + Total
    )

    # Build header rows
    day_headers = [f"{d:02d}" for d in range(1, 32)]
    header_row1 = [f"Daily Newspaper Received — {month_label}"] + [""] * 33
    header_row2 = ["SL.", "Paper"] + day_headers

    paper_rows = []
    for i, paper in enumerate(papers, 1):
        paper_rows.append([i, paper] + [""] * 32)

    all_rows = [header_row1, header_row2] + paper_rows
    ws.update(all_rows, value_input_option="USER_ENTERED")

    # Format: merge title row A1:AH1, bold header row
    fmt_requests = [
        # Merge title across all columns
        {"mergeCells": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 34},
            "mergeType": "MERGE_ALL"
        }},
        # Title cell style
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 34},
            "cell": {"userEnteredFormat": {
                "backgroundColor": _GS_HEADER,
                "textFormat": {"bold": True, "fontSize": 12,
                               "foregroundColor": {"red":1,"green":1,"blue":1}},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }},
        # Header row 2
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": 34},
            "cell": {"userEnteredFormat": {
                "backgroundColor": _GS_HEADER,
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red":1,"green":1,"blue":1}},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }},
        # Freeze first 2 rows only.
        # NOTE: frozenColumnCount is intentionally omitted here. The title row
        # (row 1) is merged across all 34 columns. Google Sheets raises APIError
        # [400] if you try to freeze a column boundary that bisects a merged
        # cell — which freezing at column 2 would do. Freezing rows only is
        # safe because the merge is horizontal (row-level), not vertical.
        {"updateSheetProperties": {
            "properties": {
                "sheetId": ws.id,
                "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 0}
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
        }},
        # Column widths: SL narrow, Paper wide, day columns narrow
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 40},
            "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 200},
            "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": 2, "endIndex": 34},
            "properties": {"pixelSize": 48},
            "fields": "pixelSize"
        }},
    ]
    spreadsheet.batch_update({"requests": fmt_requests})
    return ws

def gs_write_day(creds_path, sheet_id, date_obj, status, prices_today, received_set, missing_set, papers):
    """
    Write one day's data into the Google Sheet.
    Each month gets its own tab (e.g. "July 2026").
    Column = day number + 2 (col A = SL, col B = Paper, col C = day 1, ...).
    """
    client      = _gs_client(creds_path)
    spreadsheet = client.open_by_key(sheet_id)
    month_label = date_obj.strftime("%B %Y")
    ws          = _get_or_create_worksheet(spreadsheet, month_label, papers)
    day_col     = date_obj.day + 1   # 0-indexed: col 0=SL, col 1=Paper, col 2=day1...

    # Build batch cell updates and format requests
    cell_updates   = []  # for ws.update (values)
    format_requests = [] # for spreadsheet.batch_update (colors)

    for i, paper in enumerate(papers):
        row_0 = i + 2   # 0-indexed; rows 0=title, 1=header, 2+=papers

        if status == "off_day":
            val  = "OFF"
            color = _GS_BLUE
            bold  = True
        elif status == "auto_missed":
            val  = "?"
            color = _GS_ORANGE
            bold  = False
        elif paper in received_set:
            val  = prices_today.get(paper, DEFAULT_PRICES.get(paper, 0))
            color = _GS_GREEN
            bold  = False
        else:
            val  = "✗"
            color = _GS_RED
            bold  = True

        # gspread A1 notation for this cell: e.g. C3
        col_letter = gspread.utils.rowcol_to_a1(row_0 + 1, day_col + 1).rstrip("0123456789")
        a1 = f"{col_letter}{row_0 + 1}"
        cell_updates.append({"range": a1, "values": [[val]]})

        format_requests.append({"repeatCell": {
            "range": {
                "sheetId":          ws.id,
                "startRowIndex":    row_0,
                "endRowIndex":      row_0 + 1,
                "startColumnIndex": day_col,
                "endColumnIndex":   day_col + 1,
            },
            "cell": {"userEnteredFormat": {
                "backgroundColor":    color,
                "horizontalAlignment": "CENTER",
                "textFormat":         {"bold": bold, "fontSize": 9},
            }},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"
        }})

    # Write values in one batch call
    ws.batch_update(cell_updates, value_input_option="USER_ENTERED")
    # Apply formatting in one batch call
    if format_requests:
        spreadsheet.batch_update({"requests": format_requests})
# ── Telegram ───────────────────────────────────────────────────────────────────
def tg_send(token, chat_id, text):
    if not token or not chat_id: return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id":chat_id,"text":text,"parse_mode":"Markdown"},
                      timeout=8)
    except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN TRACKER WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class NewspaperTracker(ctk.CTkToplevel):

    def __init__(self, master=None):
        super().__init__(master)
        self.title("📰 NAB — Newspaper Tracker")
        # Was 980x740 with a hard minsize(900, 640). On a 1366x768 screen the
        # usable height is ~720, so the Submit Day button sat under the
        # taskbar AND the minsize prevented shrinking the window to reach it.
        nab_ui_scale.fit(self, 980, 740, min_w=760, min_h=520, parent=master)
        self.configure(fg_color=C_BG)
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))

        self.papers  = load_papers()
        self.prices  = load_prices()
        self.cfg     = load_cfg()
        self.checks  = {}        # paper → BooleanVar
        self.overrides = {}      # paper → StringVar
        self._price_labels = {}

        # Auto-detection from NAB's saved clips
        self._detected = {}          # canonical paper → clip count
        self._detected_unknown = {}  # raw filename name → clip count
        self._detect_token = 0       # guards against a slow scan landing
                                     # after the user has changed date

        # Current date being edited (default = today)
        self.editing_date = datetime.date.today()

        # Auto-backfill silently
        threading.Thread(target=backfill_missed_days, daemon=True).start()

        self._build_ui()
        self._load_date(self.editing_date)

    # ══════════════════════════════════════════════════════
    #  BUILD UI
    # ══════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Top header ──
        hdr = ctk.CTkFrame(self, fg_color="#0D0D0D", corner_radius=0, height=56)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="📰  Daily Newspaper Tracker",
                     font=ctk.CTkFont(family="Impact", size=20),
                     text_color=C_RED).pack(side="left", padx=20)

        # Date nav on the right
        nav = ctk.CTkFrame(hdr, fg_color="transparent")
        nav.pack(side="right", padx=12)

        ctk.CTkButton(nav, text="◀", width=32, height=28, fg_color=C_SURF2,
                      hover_color="#333", font=ctk.CTkFont(size=14),
                      command=self._prev_day).pack(side="left", padx=2)

        self._date_lbl = ctk.CTkLabel(nav, text="", width=180,
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       text_color="#DDD")
        self._date_lbl.pack(side="left", padx=4)

        ctk.CTkButton(nav, text="▶", width=32, height=28, fg_color=C_SURF2,
                      hover_color="#333", font=ctk.CTkFont(size=14),
                      command=self._next_day).pack(side="left", padx=2)

        ctk.CTkButton(nav, text="📅 Pick Date", width=100, height=28,
                      fg_color=C_BLUE, hover_color="#1E7FC0",
                      font=ctk.CTkFont(size=12),
                      command=self._pick_date).pack(side="left", padx=(8,2))

        ctk.CTkButton(nav, text="Today", width=70, height=28,
                      fg_color="#333", hover_color="#444",
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._load_date(datetime.date.today())).pack(side="left", padx=2)

        # ── Monthly counter bar ──
        self._mbar = ctk.CTkFrame(self, fg_color="#0A0A14", corner_radius=0, height=34)
        self._mbar.pack(fill="x"); self._mbar.pack_propagate(False)
        self._mlbl = ctk.CTkLabel(self._mbar, text="",
                                   font=ctk.CTkFont(size=12), text_color="#7FB3D3")
        self._mlbl.pack(side="left", padx=16)

        # ── Tabs ──
        tabs = ctk.CTkTabview(
            self, fg_color=C_BG,
            segmented_button_fg_color="#0D0D0D",
            segmented_button_selected_color=C_ACCENT,
            segmented_button_unselected_color="#0D0D0D",
            segmented_button_selected_hover_color="#cc7700",
            text_color="#CCC",
            command=self._on_tab_changed,
        )
        tabs.pack(fill="both", expand=True, padx=8, pady=(4,0))
        self._tabs = tabs

        tabs.add("✅  Daily Check")
        tabs.add("📊  Month View")
        tabs.add("🌐  Heatmap")
        tabs.add("📋  Paper List")
        tabs.add("💰  Prices")
        tabs.add("⚙️  Settings")

        self._tab_check   = tabs.tab("✅  Daily Check")
        self._tab_month   = tabs.tab("📊  Month View")
        self._tab_heatmap = tabs.tab("🌐  Heatmap")
        self._tab_papers  = tabs.tab("📋  Paper List")
        self._tab_prices  = tabs.tab("💰  Prices")
        self._tab_cfg     = tabs.tab("⚙️  Settings")

        self._build_checklist()
        self._build_month_view()
        self._build_heatmap_tab()
        self._build_paper_list()
        self._build_prices()
        self._build_settings()

        self._refresh_month_bar()

    def _on_tab_changed(self):
        """The Heatmap tab does a recursive scan of the whole archive to
        build its grid — on a big or networked archive that can take real
        time. It used to run 500ms after ANY Tracker window was created
        (including the hidden one built just to drive the end-of-session
        close dialog), which is why closing NAB used to pause while a tab
        nobody was looking at scanned in the background. Now it only scans
        the first time you actually open that tab."""
        try:
            if self._tabs.get() == "🌐  Heatmap" and not self._heatmap_loaded:
                self._heatmap_loaded = True
                self._refresh_heatmap()
        except Exception as e:
            logging.error(f"_on_tab_changed: {e}")

    # ══════════════════════════════════════════════════════
    #  DATE NAVIGATION
    # ══════════════════════════════════════════════════════
    def _prev_day(self):
        self._load_date(self.editing_date - datetime.timedelta(days=1))

    def _next_day(self):
        d = self.editing_date + datetime.timedelta(days=1)
        if d <= datetime.date.today():
            self._load_date(d)

    def _pick_date(self):
        """Simple date picker using entry dialog."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Pick Date"); nab_ui_scale.fit(dlg, 300, 170, parent=self)
        dlg.configure(fg_color=C_BG); dlg.grab_set()
        dlg.attributes("-topmost", True)

        ctk.CTkLabel(dlg, text="Enter date  (YYYY-MM-DD)",
                     font=ctk.CTkFont(size=13), text_color="#CCC").pack(pady=(20,8))
        e = ctk.CTkEntry(dlg, width=200, height=32, fg_color="#0A0A0A",
                          border_color="#333", text_color="#EEE",
                          placeholder_text=self.editing_date.isoformat())
        e.insert(0, self.editing_date.isoformat())
        e.pack()

        def confirm():
            try:
                d = datetime.date.fromisoformat(e.get().strip())
                if d <= datetime.date.today():
                    self._load_date(d); dlg.destroy()
            except: pass

        ctk.CTkButton(dlg, text="Go", width=120, height=34,
                      fg_color=C_ACCENT, hover_color="#cc7700",
                      command=confirm).pack(pady=14)
        e.bind("<Return>", lambda _: confirm())

    def _load_date(self, d: datetime.date):
        """Switch the checklist to show a specific date, pre-filling from log if exists."""
        self.editing_date = d
        is_today = (d == datetime.date.today())
        is_past  = (d < datetime.date.today())

        # Update date label
        label = d.strftime("%d %B %Y  (%A)")
        if is_today: label = "TODAY — " + label
        self._date_lbl.configure(text=label)

        # Load saved entry for that day if exists
        log   = _load_log()
        entry = log.get(d.isoformat(), {})
        saved_received = set(entry.get("received", []))
        saved_prices   = entry.get("prices", {})
        status         = entry.get("status", "")

        # Set checkboxes
        for paper in self.papers:
            if paper not in self.checks: continue
            if status in ("off_day", "auto_missed"):
                # Don't touch checkboxes for special statuses — show banner instead
                self.checks[paper].set(True)
            elif saved_received:
                self.checks[paper].set(paper in saved_received)
            else:
                # No entry yet. Start from nothing and let the clip scan below
                # tick what NAB actually saved — defaulting everything to
                # "received" meant a hurried Submit recorded papers that had
                # never arrived.
                self.checks[paper].set(False)

        # Pre-fill price overrides from saved
        for paper in self.papers:
            if paper not in self.overrides: continue
            saved_p = saved_prices.get(paper, "")
            default_p = self.prices.get(paper, 0)
            # Only show override if it differs from current default
            if saved_p and abs(float(saved_p) - default_p) > 0.001:
                self.overrides[paper].set(str(saved_p))
            else:
                self.overrides[paper].set("")

        # Status badge
        badge = ""
        if status == "off_day":      badge = "🏖  OFF DAY"
        elif status == "auto_missed": badge = "❓  NOT SUBMITTED"
        elif status == "submitted":   badge = "✅  SUBMITTED"
        self._day_status_lbl.configure(text=badge)

        # Disable/enable buttons
        state = "normal"
        self._submit_btn.configure(state=state)
        self._off_btn.configure(state=state)

        # No saved entry for this day → auto-tick from the clips on disk.
        self._detected, self._detected_unknown = {}, {}
        if not saved_received and status not in ("off_day", "submitted"):
            self._auto_detect_async(d)

        # Disable future nav
        self._update_summary()
        self._refresh_month_bar()

    # ══════════════════════════════════════════════════════
    #  AUTO-DETECT FROM NAB CLIPS
    # ══════════════════════════════════════════════════════
    def _auto_detect_async(self, d, announce=True):
        """Scan NAB's archive for clips saved on date d and tick the papers
        they belong to. Runs off the UI thread — base_root is often a network
        share, where a synchronous walk would freeze the window."""
        self._detect_token += 1
        token = self._detect_token
        try:
            self._status_lbl.configure(text="🔎 Scanning clips…", text_color="#888")
        except Exception:
            pass

        papers_snapshot = list(self.papers)

        def _work():
            try:
                matched, unknown = nab_clip_scan.papers_clipped_on(d, papers_snapshot)
            except Exception as e:
                logging.error(f"tracker auto-detect: {e}")
                matched, unknown = {}, {}
            try:
                self.after(0, lambda: self._apply_detection(
                    token, d, matched, unknown, announce))
            except Exception:
                pass    # window closed mid-scan

        threading.Thread(target=_work, daemon=True).start()

    def _apply_detection(self, token, d, matched, unknown, announce=True):
        # A slower scan for a date the user has since navigated away from
        # must not stomp on the checkboxes they're now looking at.
        if token != self._detect_token or self.editing_date != d:
            return
        try:
            self._detected = dict(matched)
            self._detected_unknown = dict(unknown)
            for paper, count in matched.items():
                if paper in self.checks:
                    self.checks[paper].set(True)
            self._update_summary()
            if announce:
                if matched:
                    clips = sum(matched.values())
                    msg = (f"🔎 Auto-ticked {len(matched)} paper(s) "
                           f"from {clips} clip(s) on disk")
                else:
                    msg = "🔎 No clips found on disk for this date"
                if unknown:
                    names = ", ".join(sorted(unknown)[:3])
                    more = f" +{len(unknown)-3}" if len(unknown) > 3 else ""
                    msg += f"  ·  unmatched: {names}{more}"
                self._status_lbl.configure(text=msg, text_color=C_BLUE)
        except Exception as e:
            logging.error(f"_apply_detection: {e}")

    def _manual_detect(self):
        self._auto_detect_async(self.editing_date)

    # ══════════════════════════════════════════════════════
    #  CHECKLIST TAB
    # ══════════════════════════════════════════════════════
    def _build_checklist(self):
        tab = self._tab_check
        tab.configure(fg_color=C_BG)

        # Top controls row
        top = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=8, height=44)
        top.pack(fill="x", pady=(4,4)); top.pack_propagate(False)

        ctk.CTkButton(top, text="✅ All Received", width=120, height=28,
                      fg_color="#1A4A1A", hover_color="#1E6B1E",
                      font=ctk.CTkFont(size=12),
                      command=self._check_all).pack(side="left", padx=8, pady=8)

        ctk.CTkButton(top, text="❌ Clear All", width=100, height=28,
                      fg_color="#4A1A1A", hover_color="#6B1E1E",
                      font=ctk.CTkFont(size=12),
                      command=self._uncheck_all).pack(side="left", padx=4)

        ctk.CTkButton(top, text="🔎 From Clips", width=110, height=28,
                      fg_color="#1A2A4A", hover_color="#24406B",
                      font=ctk.CTkFont(size=12),
                      command=self._manual_detect).pack(side="left", padx=4)

        self._day_status_lbl = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_ACCENT, width=200)
        self._day_status_lbl.pack(side="left", padx=16)

        self._summary_lbl = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=12), text_color="#AAA")
        self._summary_lbl.pack(side="right", padx=14)

        # Column headers
        chdr = ctk.CTkFrame(tab, fg_color=C_SURF2, corner_radius=4, height=26)
        chdr.pack(fill="x", pady=(0,1)); chdr.pack_propagate(False)
        for txt, w, anc in [("  ✓",40,"w"),("Newspaper",230,"w"),
                             ("Default ৳",110,"center"),("Override ৳",120,"center")]:
            ctk.CTkLabel(chdr, text=txt, width=w, anchor=anc,
                         font=ctk.CTkFont(size=11,weight="bold"),
                         text_color=C_DIM).pack(side="left", padx=2)

        # Scrollable list
        self._scroll_frame = ctk.CTkScrollableFrame(
            tab, fg_color=C_BG, scrollbar_button_color=C_ACCENT)
        self._scroll_frame.pack(fill="both", expand=True)
        self._build_paper_rows()

        # Bottom action bar
        bot = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=0, height=56)
        bot.pack(fill="x", pady=(4,0)); bot.pack_propagate(False)

        self._status_lbl = ctk.CTkLabel(
            bot, text="", font=ctk.CTkFont(size=12), text_color="#888")
        self._status_lbl.pack(side="left", padx=14)

        self._submit_btn = ctk.CTkButton(
            bot, text="📤  Submit Day", width=150, height=36,
            fg_color="#145A32", hover_color="#1E8449",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._submit)
        self._submit_btn.pack(side="right", padx=10, pady=10)

        self._off_btn = ctk.CTkButton(
            bot, text="🏖  Off Day", width=110, height=36,
            fg_color="#00254A", hover_color="#003366",
            font=ctk.CTkFont(size=12),
            command=self._mark_off_day)
        self._off_btn.pack(side="right", padx=4, pady=10)

    def _build_paper_rows(self):
        """Build (or rebuild) checklist rows from self.papers."""
        for w in self._scroll_frame.winfo_children():
            w.destroy()
        self.checks.clear(); self.overrides.clear(); self._price_labels.clear()

        for i, paper in enumerate(self.papers):
            bg = "#111111" if i % 2 == 0 else C_BG
            row = ctk.CTkFrame(self._scroll_frame, fg_color=bg, corner_radius=3, height=34)
            row.pack(fill="x", pady=1); row.pack_propagate(False)

            var = ctk.BooleanVar(value=True)
            self.checks[paper] = var
            ctk.CTkCheckBox(row, text="", variable=var, width=40,
                             checkbox_width=18, checkbox_height=18,
                             fg_color=C_ACCENT, hover_color="#cc7700",
                             border_color="#555",
                             command=self._update_summary).pack(side="left", padx=(8,0))

            ctk.CTkLabel(row, text=paper, width=230, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#DDD").pack(side="left", padx=4)

            lbl = ctk.CTkLabel(row, text=f"৳ {self.prices.get(paper, DEFAULT_PRICES.get(paper,0)):.2f}",
                                width=110, anchor="center",
                                font=ctk.CTkFont(size=12), text_color="#666")
            lbl.pack(side="left")
            self._price_labels[paper] = lbl

            ov = ctk.StringVar(value="")
            self.overrides[paper] = ov
            ctk.CTkEntry(row, textvariable=ov, width=100, height=24,
                          placeholder_text="Override",
                          fg_color="#0A0A0A", border_color="#333",
                          text_color="#EEE", font=ctk.CTkFont(size=11)).pack(side="left", padx=8)

    def _check_all(self):
        for v in self.checks.values(): v.set(True)
        self._update_summary()

    def _uncheck_all(self):
        for v in self.checks.values(): v.set(False)
        self._update_summary()

    def _eff_price(self, paper):
        ov = self.overrides.get(paper, ctk.StringVar()).get().strip()
        if ov:
            try: return float(ov)
            except: pass
        return self.prices.get(paper, DEFAULT_PRICES.get(paper, 0))

    def _update_summary(self):
        received = [p for p, v in self.checks.items() if v.get()]
        missing  = [p for p, v in self.checks.items() if not v.get()]
        total    = sum(self._eff_price(p) for p in received)
        self._summary_lbl.configure(
            text=f"✅ {len(received)}   ❌ {len(missing)}   |   ৳{total:.2f}")

    # ── Submit ─────────────────────────────────────────────
    def _submit(self, on_done=None):
        d          = self.editing_date
        day_str    = d.strftime("%d %B %Y")
        month_lbl  = d.strftime("%B %Y")
        received   = {p for p, v in self.checks.items() if v.get()}
        missing    = {p for p, v in self.checks.items() if not v.get()}
        prices_t   = {p: self._eff_price(p) for p in self.papers}
        total      = sum(prices_t[p] for p in received)

        is_past = (d < datetime.date.today())
        if is_past:
            if not messagebox.askyesno("Edit Past Day",
                f"You're editing a past date:\n{day_str}\n\nSave this entry?", parent=self):
                return

        self._status_lbl.configure(text="⏳ Saving...", text_color="#F0A500")
        self.update()

        def _do():
            errs = []
            creds = self.cfg.get("gs_creds_path", "").strip()
            sid   = self.cfg.get("gs_sheet_id",   "").strip()
            if creds and sid:
                try:
                    gs_write_day(creds, sid, d, "submitted", prices_t, received, missing, self.papers)
                except Exception as e:
                    errs.append(f"Google Sheets: {e}")
            else:
                errs.append("Google Sheets not configured — check Settings tab")

            _log_entry(d.isoformat(), "submitted", list(received), list(missing), prices_t, total)

            # Telegram
            tok = self.cfg.get("tg_token",""); cid = self.cfg.get("tg_chat_id","")
            if missing:
                miss_lines = "\n".join(f"  ❌ {p}" for p in sorted(missing))
                msg = (f"📰 *{day_str}*\n✅ {len(received)} received  ❌ {len(missing)} missing\n\n"
                       f"*Missing:*\n{miss_lines}\n\n💰 Today: *৳{total:.2f}*")
            else:
                msg = f"📰 *{day_str}*\n✅ All *{len(received)}* papers received!\n💰 *৳{total:.2f}*"
            tg_send(tok, cid, msg)

            mt, ms, mo, mm = _get_month_stats(d.year, d.month)
            tg_send(tok, cid, f"📅 *{month_lbl}:* ৳{mt:.2f} total  ({ms} days)")

            self.after(0, lambda: [
                self._status_lbl.configure(
                    text=f"✅ Saved! {len(missing)} missing — ৳{total:.2f}",
                    text_color=C_SUCCESS),
                self._day_status_lbl.configure(text="✅  SUBMITTED"),
                self._refresh_month_bar(),
                self._refresh_month_grid() if hasattr(self, '_month_cells') else None,
            ])
            if errs:
                self.after(0, lambda: self._status_lbl.configure(
                    text="⚠ " + " | ".join(errs), text_color=C_DANGER))

            # Lets the end-of-session dialog wait for the Sheets/Telegram
            # round-trip instead of closing NAB mid-write.
            if on_done:
                try:
                    self.after(0, lambda: on_done(errs))
                except Exception:
                    pass

        threading.Thread(target=_do, daemon=True).start()

    # ══════════════════════════════════════════════════════
    #  END-OF-SESSION CONFIRMATION  (called by NAB on close)
    # ══════════════════════════════════════════════════════
    def session_end_confirm(self, parent=None):
        """Modal end-of-day check, shown when NAB is closing.

        Papers with clips on disk for today are already ticked (nothing to
        confirm — the work is the evidence). Everything else is listed so the
        operator can say which of them actually arrived, then the day is
        submitted in one go.

        The dialog itself appears INSTANTLY — the archive scan that finds
        which papers were clipped runs on a background thread afterwards,
        with a loading overlay over the body until it's done. It used to
        scan first and only then show the dialog, which is what made closing
        NAB feel like it was hanging: nothing was on screen while a
        potentially slow (especially over a network share) folder walk ran.

        Returns:
          'submitted' — day written to the log / Sheet
          'skipped'   — nothing recorded, NAB may close
          'cancel'    — user backed out; NAB must stay open
        """
        d = datetime.date.today()

        # Already dealt with today? Don't nag.
        entry = _load_log().get(d.isoformat(), {})
        if entry.get("status") in ("submitted", "off_day"):
            return "skipped"

        if self.editing_date != d:
            self._load_date(d)

        # Mutable holder so the button callbacks (defined below, before the
        # scan finishes) see the real data once _populate_body fills it in.
        state = {"matched": {}, "unknown": {}, "detected": [], "rest": []}
        rest_vars = {}
        result = {"v": "cancel"}

        dlg = ctk.CTkToplevel(self)
        dlg.title("End of session — confirm today's papers")
        dlg.configure(fg_color=C_BG)
        nab_ui_scale.fit(dlg, 620, 640, min_w=430, min_h=380,
                         parent=parent or self)
        dlg.transient(parent or self)
        dlg.attributes("-topmost", True)

        # ── Header ──
        hdr = ctk.CTkFrame(dlg, fg_color="#0D0D0D", corner_radius=0, height=66)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📰  Before you close — today's papers",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=C_ACCENT).pack(anchor="w", padx=18, pady=(12, 0))
        ctk.CTkLabel(hdr, text=d.strftime("%d %B %Y  (%A)"),
                     font=ctk.CTkFont(size=12), text_color="#888"
                     ).pack(anchor="w", padx=18)

        body = ctk.CTkScrollableFrame(dlg, fg_color=C_BG,
                                      scrollbar_button_color=C_ACCENT)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body_overlay = nab_loading.LoadingOverlay(
            body, text="Scanning your clips…",
            sub_fg="#555")
        body_overlay.show(sub="Everything below fills in as soon as this finishes")

        # ── Footer ──
        foot = ctk.CTkFrame(dlg, fg_color=C_SURF, corner_radius=0, height=58)
        foot.pack(fill="x"); foot.pack_propagate(False)

        note = ctk.CTkLabel(foot, text="⏳ Scanning…", font=ctk.CTkFont(size=12),
                            text_color="#888")
        note.pack(side="left", padx=14)

        def _apply_to_checklist():
            for paper, var in self.checks.items():
                var.set(paper in state["matched"] or bool(
                    rest_vars.get(paper) and rest_vars[paper].get()))
            self._update_summary()

        def _tick_all_rest():
            for v in rest_vars.values():
                v.set(True)

        def _close(value):
            result["v"] = value
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        def _do_submit():
            _apply_to_checklist()
            for b in (btn_submit, btn_off, btn_skip, btn_all):
                b.configure(state="disabled")
            note.configure(text="⏳ Saving to log / Google Sheet…",
                           text_color="#F0A500")

            done = {"v": False}

            def _finished(errs=None):
                if done["v"]:
                    return
                done["v"] = True
                if errs:
                    note.configure(text="⚠ Saved locally, sync had errors",
                                   text_color=C_DANGER)
                _close("submitted")

            # Failsafe: never hold NAB's shutdown hostage to a hung network
            # call — the local log write in _submit has already happened by
            # then anyway.
            dlg.after(20000, lambda: _finished(["timeout"]))
            self._submit(on_done=_finished)

        def _do_off_day():
            self._mark_off_day()
            _close("submitted")

        btn_submit = ctk.CTkButton(foot, text="✅  Submit Day", width=140, height=34,
                                   fg_color="#145A32", hover_color="#1E8449",
                                   font=ctk.CTkFont(size=13, weight="bold"),
                                   state="disabled", command=_do_submit)
        btn_submit.pack(side="right", padx=(4, 12), pady=10)

        btn_skip = ctk.CTkButton(foot, text="⏭  Skip", width=80, height=34,
                                 fg_color="#333", hover_color="#444",
                                 font=ctk.CTkFont(size=12),
                                 command=lambda: _close("skipped"))
        btn_skip.pack(side="right", padx=4, pady=10)

        btn_off = ctk.CTkButton(foot, text="🏖  Off Day", width=100, height=34,
                                fg_color="#00254A", hover_color="#003366",
                                font=ctk.CTkFont(size=12),
                                state="disabled", command=_do_off_day)
        btn_off.pack(side="right", padx=4, pady=10)

        btn_all = ctk.CTkButton(foot, text="Tick all remaining", width=140, height=34,
                                fg_color="#1A2A4A", hover_color="#24406B",
                                font=ctk.CTkFont(size=12),
                                state="disabled", command=_tick_all_rest)
        btn_all.pack(side="left", padx=4, pady=10)

        # Closing the dialog with the X means "I'm not done yet" — NAB stays
        # open rather than silently discarding the day. Available immediately
        # (doesn't need the scan), same as Skip.
        dlg.protocol("WM_DELETE_WINDOW", lambda: _close("cancel"))

        def _map_unknown(raw, count):
            """Teach the matcher what an unrecognised filename spelling
            actually means. Saved via nab_clip_scan.save_alias, so every
            future scan — on this PC — auto-matches it without asking
            again."""
            if not self.papers:
                return
            popup = ctk.CTkToplevel(dlg)
            popup.title("Map to a paper")
            popup.configure(fg_color=C_BG)
            nab_ui_scale.fit(popup, 360, 220, parent=dlg)
            popup.attributes("-topmost", True)
            popup.grab_set()

            ctk.CTkLabel(popup, text=f'"{raw}" is actually:',
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#F9FAFB", wraplength=320
                         ).pack(pady=(16, 8), padx=16)

            pick_var = ctk.StringVar(value=self.papers[0])
            ctk.CTkOptionMenu(popup, variable=pick_var, values=self.papers,
                             fg_color="#222", button_color="#333",
                             width=280).pack(pady=6)

            ctk.CTkLabel(popup, text="Remembered from now on — this exact "
                                    "spelling auto-matches every future scan.",
                         font=ctk.CTkFont(size=10), text_color="#666",
                         wraplength=320).pack(pady=(4, 10))

            def _confirm_map():
                canonical = pick_var.get()
                if not canonical:
                    return
                nab_clip_scan.save_alias(raw, canonical)
                new_matched = dict(state["matched"])
                new_matched[canonical] = new_matched.get(canonical, 0) + count
                new_unknown = dict(state["unknown"])
                new_unknown.pop(raw, None)
                popup.destroy()
                _populate_body(new_matched, new_unknown)

            ctk.CTkButton(popup, text="✅ Save Mapping", fg_color=C_SUCCESS,
                         command=_confirm_map).pack(pady=6)

        def _populate_body(matched, unknown, scan_error=None, methods=None):
            if not dlg.winfo_exists():
                return   # operator already hit Skip/X while this was running
            body_overlay.hide()
            for w in body.winfo_children():
                w.destroy()

            state["matched"], state["unknown"] = dict(matched), dict(unknown)
            methods = methods or {}
            self._detected, self._detected_unknown = dict(matched), dict(unknown)
            state["detected"] = [p for p in self.papers if p in matched]
            state["rest"]     = [p for p in self.papers if p not in matched]
            detected, rest = state["detected"], state["rest"]

            if scan_error is not None:
                ctk.CTkLabel(body,
                             text=f"⚠  Couldn't scan the archive ({scan_error}) — "
                                  f"tick papers manually below.",
                             font=ctk.CTkFont(size=12), text_color=C_DANGER,
                             anchor="w", wraplength=520, justify="left"
                             ).pack(fill="x", pady=(4, 10))

            # ── Auto-entered ──
            clips = sum(matched.values())
            ctk.CTkLabel(body,
                         text=f"✅  Auto-entered from your clips  ({len(detected)} "
                              f"paper{'s' if len(detected) != 1 else ''}, {clips} clips)",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C_SUCCESS, anchor="w").pack(fill="x", pady=(4, 2))

            if detected:
                auto_box = ctk.CTkFrame(body, fg_color="#0B160B", corner_radius=6)
                auto_box.pack(fill="x", pady=(0, 10))
                for paper in detected:
                    row = ctk.CTkFrame(auto_box, fg_color="transparent")
                    row.pack(fill="x", padx=10, pady=1)
                    # Exact/alias/substring matches are shown plainly; a fuzzy
                    # match (closest spelling, not a real one on file) gets a
                    # "~" flag so it gets a second glance instead of blind
                    # trust — typos matching the WRONG similar paper are rare
                    # but not impossible.
                    is_fuzzy = methods.get(paper) == "fuzzy"
                    prefix = "~ " if is_fuzzy else ""
                    ctk.CTkLabel(row, text=f"✓  {prefix}{paper}", anchor="w",
                                 font=ctk.CTkFont(size=12),
                                 text_color="#F0C040" if is_fuzzy else "#CFE9CF"
                                 ).pack(side="left")
                    ctk.CTkLabel(row, text=f"{matched[paper]} clip"
                                           f"{'s' if matched[paper] != 1 else ''}",
                                 font=ctk.CTkFont(size=11), text_color="#4C7A4C"
                                 ).pack(side="right", padx=8)
            else:
                ctk.CTkLabel(body, text="   (no clips found on disk for today)",
                             font=ctk.CTkFont(size=12), text_color=C_DIM,
                             anchor="w").pack(fill="x", pady=(0, 10))

            # Raw names in filenames that match no paper in the list — surfaced
            # with a one-click way to teach the matcher what they mean, rather
            # than either dropped silently or left to nag forever. Usually
            # means the NAB source list and the tracker paper list have
            # drifted apart (a typo, an abbreviation, a paper renamed).
            if unknown:
                ctk.CTkLabel(body,
                             text="⚠  Clips whose paper name isn't in your list "
                                  "— map them so this stops happening:",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=C_ACCENT, anchor="w"
                             ).pack(fill="x", pady=(0, 2))
                unk_box = ctk.CTkFrame(body, fg_color="#1A1400", corner_radius=6)
                unk_box.pack(fill="x", pady=(0, 10))
                for raw_name, cnt in sorted(unknown.items()):
                    row = ctk.CTkFrame(unk_box, fg_color="transparent")
                    row.pack(fill="x", padx=8, pady=2)
                    ctk.CTkLabel(row, text=f"{raw_name}  ({cnt} clip"
                                           f"{'s' if cnt != 1 else ''})",
                                 font=ctk.CTkFont(size=11), text_color="#E0C080",
                                 anchor="w").pack(side="left", fill="x", expand=True)
                    ctk.CTkButton(row, text="🔗 Map", width=70, height=24,
                                 fg_color="#333", hover_color="#444",
                                 font=ctk.CTkFont(size=11),
                                 command=lambda r=raw_name, c=cnt: _map_unknown(r, c)
                                 ).pack(side="right")

            # ── The rest ──
            ctk.CTkLabel(body,
                         text=f"❔  Not clipped today — did these arrive?  "
                              f"({len(rest)})",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=C_ACCENT, anchor="w").pack(fill="x", pady=(4, 2))
            ctk.CTkLabel(body,
                         text="Tick the ones you received. Leave unticked to "
                              "record them as missing.",
                         font=ctk.CTkFont(size=11), text_color=C_DIM,
                         anchor="w").pack(fill="x", pady=(0, 4))

            rest_box = ctk.CTkFrame(body, fg_color=C_SURF, corner_radius=6)
            rest_box.pack(fill="x")
            for i, paper in enumerate(rest):
                var = ctk.BooleanVar(value=False)
                rest_vars[paper] = var
                row = ctk.CTkFrame(rest_box,
                                   fg_color="#141414" if i % 2 == 0 else "transparent",
                                   corner_radius=3)
                row.pack(fill="x", padx=6, pady=1)
                ctk.CTkCheckBox(row, text=paper, variable=var,
                                checkbox_width=18, checkbox_height=18,
                                fg_color=C_ACCENT, hover_color="#cc7700",
                                border_color="#555",
                                font=ctk.CTkFont(size=12)
                                ).pack(side="left", padx=8, pady=3)

            note.configure(text="", text_color="#888")
            for b in (btn_submit, btn_off, btn_all):
                b.configure(state="normal")

        def _scan_worker():
            try:
                matched, unknown, methods = nab_clip_scan.papers_clipped_on(
                    d, self.papers, return_methods=True)
                err = None
            except Exception as e:
                logging.error(f"session_end_confirm scan: {e}")
                matched, unknown, methods, err = {}, {}, {}, e
            try:
                dlg.after(0, lambda: _populate_body(matched, unknown, err, methods))
            except Exception:
                pass   # dialog closed before the scan finished

        threading.Thread(target=_scan_worker, daemon=True).start()

        # If a slow/unreachable network share hangs the scan, don't leave the
        # operator stuck looking at a spinner with every button disabled —
        # let them in to tick things manually after a reasonable wait.
        def _scan_timeout_guard():
            if dlg.winfo_exists() and btn_submit.cget("state") == "disabled":
                _populate_body({}, {}, "timed out after 15s")
        dlg.after(15000, _scan_timeout_guard)

        dlg.after(120, lambda: dlg.attributes("-topmost", False))
        dlg.grab_set()
        dlg.wait_window()
        return result["v"]

    # ── Off Day ────────────────────────────────────────────
    def _mark_off_day(self):
        d = self.editing_date
        day_str = d.strftime("%d %B %Y")
        is_past = (d < datetime.date.today())

        # Simple toggle — no annoying confirmation for today
        if is_past:
            if not messagebox.askyesno("Off Day", f"Mark {day_str} as Off Day?", parent=self):
                return

        self._status_lbl.configure(text="⏳ Saving...", text_color="#F0A500")
        self.update()

        def _do():
            errs = []
            creds = self.cfg.get("gs_creds_path", "").strip()
            sid   = self.cfg.get("gs_sheet_id",   "").strip()
            if creds and sid:
                try:
                    gs_write_day(creds, sid, d, "off_day", {}, set(), set(), self.papers)
                except Exception as e:
                    errs.append(f"Google Sheets: {e}")
            _log_entry(d.isoformat(), "off_day")
            tok = self.cfg.get("tg_token",""); cid = self.cfg.get("tg_chat_id","")
            tg_send(tok, cid, f"🏖 *Off Day — {day_str}*")

            self.after(0, lambda: [
                self._status_lbl.configure(text=f"🏖 Off day — {day_str}", text_color=C_BLUE),
                self._day_status_lbl.configure(text="🏖  OFF DAY"),
                self._refresh_month_bar(),
                self._refresh_month_grid() if hasattr(self, '_month_cells') else None,
            ])
        threading.Thread(target=_do, daemon=True).start()

    # ── Monthly counter bar ────────────────────────────────
    def _refresh_month_bar(self):
        d = self.editing_date
        total, sub, off, missed = _get_month_stats(d.year, d.month)
        self._mlbl.configure(
            text=(f"📅 {d.strftime('%B %Y')}  |  "
                  f"💰 ৳{total:.2f}  |  ✅ {sub} days  |  🏖 {off} off  |  ❓ {missed} missed"))

    # ══════════════════════════════════════════════════════
    #  MONTH VIEW TAB
    # ══════════════════════════════════════════════════════
    def _build_month_view(self):
        tab = self._tab_month
        tab.configure(fg_color=C_BG)

        top = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=8, height=44)
        top.pack(fill="x", pady=(4,8)); top.pack_propagate(False)

        ctk.CTkButton(top, text="◀", width=32, height=28, fg_color=C_SURF2,
                      command=self._month_prev).pack(side="left", padx=8, pady=8)
        self._month_nav_lbl = ctk.CTkLabel(top, text="", width=160,
                                            font=ctk.CTkFont(size=13,weight="bold"),
                                            text_color="#DDD")
        self._month_nav_lbl.pack(side="left", padx=4)
        ctk.CTkButton(top, text="▶", width=32, height=28, fg_color=C_SURF2,
                      command=self._month_next).pack(side="left", padx=2)

        ctk.CTkButton(top, text="↻ Refresh", width=90, height=28,
                      fg_color="#333", command=self._refresh_month_grid).pack(side="left", padx=12)

        # Legend
        legend = ctk.CTkFrame(top, fg_color="transparent")
        legend.pack(side="right", padx=10)
        for sym, col, txt in [("■","#2ECC71","Submitted"),("■","#3498DB","Off"),
                               ("■","#F39C12","Missed"),("■","#555","No data")]:
            ctk.CTkLabel(legend, text=f"{sym} {txt}", font=ctk.CTkFont(size=11),
                         text_color=col).pack(side="left", padx=6)

        # Grid area
        self._month_grid_frame = ctk.CTkScrollableFrame(
            tab, fg_color=C_BG, scrollbar_button_color=C_ACCENT)
        self._month_grid_frame.pack(fill="both", expand=True, padx=4)

        self._view_year  = datetime.date.today().year
        self._view_month = datetime.date.today().month
        self._month_cells = {}
        self._refresh_month_grid()

    def _month_prev(self):
        if self._view_month == 1: self._view_year -= 1; self._view_month = 12
        else: self._view_month -= 1
        self._refresh_month_grid()

    def _month_next(self):
        today = datetime.date.today()
        if (self._view_year, self._view_month) < (today.year, today.month):
            if self._view_month == 12: self._view_year += 1; self._view_month = 1
            else: self._view_month += 1
            self._refresh_month_grid()

    def _refresh_month_grid(self):
        for w in self._month_grid_frame.winfo_children(): w.destroy()
        self._month_cells.clear()

        y = self._view_year; m = self._view_month
        self._month_nav_lbl.configure(text=datetime.date(y,m,1).strftime("%B %Y"))

        log   = _load_log()
        today = datetime.date.today()
        _, days_in_month = calendar.monthrange(y, m)

        STATUS_COLOR = {
            "submitted":   "#1A5C2A",
            "off_day":     "#003366",
            "auto_missed": "#5C3A00",
        }
        STATUS_ICON = {
            "submitted": "✅", "off_day": "🏖", "auto_missed": "❓"
        }

        # Summary totals row
        total, sub, off, missed = _get_month_stats(y, m)
        summ = ctk.CTkFrame(self._month_grid_frame, fg_color=C_SURF2, corner_radius=8)
        summ.pack(fill="x", pady=(0,10), padx=4)
        ctk.CTkLabel(summ,
                     text=(f"  💰 Month Total: ৳{total:.2f}   ✅ {sub} submitted   "
                           f"🏖 {off} off   ❓ {missed} missed"),
                     font=ctk.CTkFont(size=13), text_color="#CCC").pack(pady=8)

        # Day cards (7 per row)
        row_frame = None
        for day in range(1, days_in_month + 1):
            if (day - 1) % 7 == 0:
                row_frame = ctk.CTkFrame(self._month_grid_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=2, padx=2)

            d   = datetime.date(y, m, day)
            iso = d.isoformat()
            entry  = log.get(iso, {})
            status = entry.get("status", "")
            is_future = d > today

            bg = STATUS_COLOR.get(status, "#1A1A1A") if not is_future else "#0D0D0D"
            icon = STATUS_ICON.get(status, "—") if not is_future else ""

            day_total = entry.get("total", 0) if status == "submitted" else 0
            n_missing = len(entry.get("missing", []))

            card = ctk.CTkFrame(row_frame, fg_color=bg, corner_radius=8,
                                width=118, height=76, border_width=1,
                                border_color="#333" if status else "#222")
            card.pack(side="left", padx=3, pady=2)
            card.pack_propagate(False)

            ctk.CTkLabel(card, text=f"{icon}  {day:02d}", anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#EEE" if not is_future else "#333").pack(anchor="w", padx=8, pady=(8,0))

            if status == "submitted":
                ctk.CTkLabel(card, text=f"৳{day_total:.0f}", anchor="w",
                             font=ctk.CTkFont(size=11), text_color="#2ECC71").pack(anchor="w", padx=8)
                if n_missing:
                    ctk.CTkLabel(card, text=f"{n_missing} missing", anchor="w",
                                 font=ctk.CTkFont(size=10), text_color="#E74C3C").pack(anchor="w", padx=8)
            elif status and not is_future:
                ctk.CTkLabel(card, text=status.replace("_"," ").title(), anchor="w",
                             font=ctk.CTkFont(size=10), text_color="#888").pack(anchor="w", padx=8)

            # Click to jump to that day in checklist
            if not is_future:
                def _jump(date=d):
                    self._load_date(date)
                    # Switch to checklist tab programmatically not easy in CTk, show info
                card.bind("<Button-1>", lambda e, date=d: self._load_date(date))
                for child in card.winfo_children():
                    child.bind("<Button-1>", lambda e, date=d: self._load_date(date))

    # ══════════════════════════════════════════════════════
    #  PAPER LIST (Editable)
    # ══════════════════════════════════════════════════════
    def _build_paper_list(self):
        tab = self._tab_papers
        tab.configure(fg_color=C_BG)

        top = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=8, height=48)
        top.pack(fill="x", pady=(4,6)); top.pack_propagate(False)

        ctk.CTkLabel(top, text="Edit newspaper list — changes apply to all future entries",
                     font=ctk.CTkFont(size=12), text_color="#888").pack(side="left", padx=14, pady=10)

        ctk.CTkButton(top, text="💾 Save List", width=110, height=32,
                      fg_color="#145A32", hover_color="#1E8449",
                      command=self._save_paper_list).pack(side="right", padx=10, pady=8)

        ctk.CTkButton(top, text="+ Add Paper", width=100, height=32,
                      fg_color=C_BLUE, hover_color="#1E7FC0",
                      command=self._add_paper).pack(side="right", padx=4, pady=8)

        # Two columns: list + controls
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4)

        # Left: scrollable list
        self._papers_scroll = ctk.CTkScrollableFrame(
            body, fg_color=C_BG, scrollbar_button_color=C_ACCENT, width=580)
        self._papers_scroll.pack(side="left", fill="both", expand=True)

        # Right: info panel
        info = ctk.CTkFrame(body, fg_color=C_SURF, corner_radius=10, width=200)
        info.pack(side="right", fill="y", padx=(8,4), pady=4)
        info.pack_propagate(False)
        ctk.CTkLabel(info, text="Tips", font=ctk.CTkFont(size=13,weight="bold"),
                     text_color=C_ACCENT).pack(pady=(14,4))
        tips = ("• Click ✕ to remove a paper\n"
                "• ▲▼ to reorder\n"
                "• Add paper with + button\n"
                "• Save changes after editing\n\n"
                "Changes won't affect\npast Excel entries.\n\n"
                "Prices are set in\nthe Prices tab.")
        ctk.CTkLabel(info, text=tips, font=ctk.CTkFont(size=11),
                     text_color="#888", justify="left").pack(padx=12, anchor="w")

        self._papers_status = ctk.CTkLabel(info, text="", font=ctk.CTkFont(size=11),
                                            text_color=C_SUCCESS)
        self._papers_status.pack(pady=10)

        self._refresh_paper_list_ui()

    def _refresh_paper_list_ui(self):
        for w in self._papers_scroll.winfo_children(): w.destroy()

        for i, paper in enumerate(self.papers):
            bg = "#111111" if i % 2 == 0 else C_BG
            row = ctk.CTkFrame(self._papers_scroll, fg_color=bg, corner_radius=3, height=34)
            row.pack(fill="x", pady=1); row.pack_propagate(False)

            ctk.CTkLabel(row, text=f"{i+1:02d}.", width=36, anchor="center",
                         font=ctk.CTkFont(size=11), text_color=C_DIM).pack(side="left")

            name_var = ctk.StringVar(value=paper)
            e = ctk.CTkEntry(row, textvariable=name_var, width=320, height=24,
                              fg_color="transparent", border_width=0,
                              text_color="#DDD", font=ctk.CTkFont(size=12))
            e.pack(side="left", padx=4)

            # Store reference to update on save
            def _on_change(var=name_var, idx=i):
                self.papers[idx] = var.get()
            name_var.trace_add("write", lambda *_, fn=_on_change: fn())

            ctk.CTkButton(row, text="▲", width=28, height=24, fg_color="#222",
                          hover_color="#333", font=ctk.CTkFont(size=11),
                          command=lambda i=i: self._move_paper(i, -1)).pack(side="right", padx=2)
            ctk.CTkButton(row, text="▼", width=28, height=24, fg_color="#222",
                          hover_color="#333", font=ctk.CTkFont(size=11),
                          command=lambda i=i: self._move_paper(i, 1)).pack(side="right", padx=2)
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          fg_color="#4A1A1A", hover_color="#6B1E1E",
                          font=ctk.CTkFont(size=11),
                          command=lambda p=paper: self._remove_paper(p)).pack(side="right", padx=(2,6))

    def _move_paper(self, idx, direction):
        new_idx = idx + direction
        if 0 <= new_idx < len(self.papers):
            self.papers[idx], self.papers[new_idx] = self.papers[new_idx], self.papers[idx]
            self._refresh_paper_list_ui()

    def _remove_paper(self, paper):
        if paper in self.papers:
            self.papers.remove(paper)
            self._refresh_paper_list_ui()

    def _add_paper(self):
        dlg = ctk.CTkToplevel(self); dlg.title("Add Paper")
        nab_ui_scale.fit(dlg, 320, 150, parent=self); dlg.configure(fg_color=C_BG); dlg.grab_set()
        dlg.attributes("-topmost", True)
        ctk.CTkLabel(dlg, text="Newspaper name:", text_color="#CCC").pack(pady=(16,4))
        e = ctk.CTkEntry(dlg, width=260, height=30, fg_color="#0A0A0A",
                          border_color="#333", text_color="#EEE")
        e.pack(); e.focus()
        def add():
            name = e.get().strip()
            if name and name not in self.papers:
                self.papers.append(name)
                self._refresh_paper_list_ui()
            dlg.destroy()
        ctk.CTkButton(dlg, text="Add", width=120, height=30, fg_color=C_ACCENT,
                      command=add).pack(pady=10)
        e.bind("<Return>", lambda _: add())

    def _save_paper_list(self):
        # Remove blanks
        self.papers = [p.strip() for p in self.papers if p.strip()]
        save_papers(self.papers)
        self._refresh_paper_list_ui()
        self._build_paper_rows()   # rebuild checklist
        self._load_date(self.editing_date)
        self._papers_status.configure(text="✅ Saved!")
        self.after(2500, lambda: self._papers_status.configure(text=""))

    # ══════════════════════════════════════════════════════
    #  PRICES TAB
    # ══════════════════════════════════════════════════════
    def _build_prices(self):
        tab = self._tab_prices
        tab.configure(fg_color=C_BG)

        ctk.CTkLabel(tab, text="Default price per newspaper (৳).  Use the Override column for one-day changes.",
                     font=ctk.CTkFont(size=12), text_color="#888").pack(anchor="w", padx=14, pady=(10,4))

        scroll = ctk.CTkScrollableFrame(tab, fg_color=C_BG, scrollbar_button_color=C_ACCENT)
        scroll.pack(fill="both", expand=True, padx=8)

        self._price_vars = {}
        for i, paper in enumerate(self.papers):
            bg = "#111111" if i % 2 == 0 else C_BG
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=3, height=32)
            row.pack(fill="x", pady=1); row.pack_propagate(False)
            ctk.CTkLabel(row, text=f"{i+1:02d}.  {paper}", width=300, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#CCC").pack(side="left", padx=10)
            var = ctk.StringVar(value=str(self.prices.get(paper, DEFAULT_PRICES.get(paper,0))))
            ctk.CTkEntry(row, textvariable=var, width=100, height=22,
                          fg_color="#0A0A0A", border_color="#333",
                          text_color="#EEE", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
            self._price_vars[paper] = var

        bot = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=0, height=50)
        bot.pack(fill="x"); bot.pack_propagate(False)
        self._price_status = ctk.CTkLabel(bot, text="", text_color=C_SUCCESS)
        self._price_status.pack(side="left", padx=14)
        ctk.CTkButton(bot, text="💾 Save Prices", width=140, height=34,
                      fg_color="#145A32", hover_color="#1E8449",
                      font=ctk.CTkFont(size=13,weight="bold"),
                      command=self._save_prices).pack(side="right", padx=12, pady=8)

    def _save_prices(self):
        for paper, var in self._price_vars.items():
            try: self.prices[paper] = float(var.get().strip())
            except: pass
        save_prices(self.prices)
        # Update labels in checklist
        for paper, lbl in self._price_labels.items():
            lbl.configure(text=f"৳ {self.prices.get(paper, DEFAULT_PRICES.get(paper,0)):.2f}")
        self._price_status.configure(text="✅ Saved!")
        self.after(2500, lambda: self._price_status.configure(text=""))

    # ══════════════════════════════════════════════════════
    #  SETTINGS TAB
    # ══════════════════════════════════════════════════════
    def _build_heatmap_tab(self):
        """Coverage heatmap: papers × categories, colour-coded by clip count."""
        frm = self._tab_heatmap
        # Controls row
        ctrl = ctk.CTkFrame(frm, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(ctrl, text="Month:", font=ctk.CTkFont(size=12),
                     text_color="#888").pack(side="left", padx=(0,4))

        self._hm_month_var = ctk.StringVar(
            value=datetime.datetime.now().strftime("%Y-%m"))
        month_entry = ctk.CTkEntry(ctrl, textvariable=self._hm_month_var,
                                    width=90, height=28, fg_color="#0A0A0A",
                                    border_color="#333", text_color="#EEE",
                                    font=ctk.CTkFont(size=11))
        month_entry.pack(side="left", padx=(0,8))

        ctk.CTkButton(ctrl, text="🔄 Refresh", width=90, height=28,
                      fg_color="#1A3A5A", hover_color="#1E4A7A",
                      font=ctk.CTkFont(size=11),
                      command=self._refresh_heatmap).pack(side="left")

        self._hm_status = ctk.CTkLabel(ctrl, text="", font=ctk.CTkFont(size=10),
                                        text_color="#555")
        self._hm_status.pack(side="left", padx=10)

        # Push to Sheets button
        ctk.CTkButton(ctrl, text="📤 Push to Sheet", width=120, height=28,
                      fg_color="#145A32", hover_color="#1E8449",
                      font=ctk.CTkFont(size=11),
                      command=self._push_heatmap_to_sheet).pack(side="right")

        # Scrollable grid area
        self._hm_scroll = ctk.CTkScrollableFrame(
            frm, fg_color="#0A0A0A", corner_radius=8)
        self._hm_scroll.pack(fill="both", expand=True, padx=10, pady=(0,8))

        self._hm_frame = ctk.CTkFrame(self._hm_scroll, fg_color="transparent")
        self._hm_frame.pack(fill="both", expand=True)

        # Colour legend
        leg = ctk.CTkFrame(frm, fg_color="transparent")
        leg.pack(fill="x", padx=10, pady=(0,6))
        for color, label in [
            ("#1A4A1A","1 clip"), ("#1E6B1E","2-3"), ("#22A822","4-5"),
            ("#33CC33","6+"), ("#1A1A1A","0 (missed)")]:
            f = ctk.CTkFrame(leg, fg_color=color, width=14, height=14,
                              corner_radius=3)
            f.pack(side="left", padx=(4,2))
            f.pack_propagate(False)
            ctk.CTkLabel(leg, text=label, font=ctk.CTkFont(size=9),
                         text_color="#666").pack(side="left", padx=(0,8))

        self._hm_data = None
        self._heatmap_loaded = False
        self._hm_overlay = nab_loading.LoadingOverlay(
            self._hm_scroll, text="Scanning your archive…")
        ctk.CTkLabel(self._hm_frame,
                     text="Open this tab to load the heatmap",
                     font=ctk.CTkFont(size=12), text_color="#444"
                     ).pack(pady=40)

    def _refresh_heatmap(self):
        """Kick off a heatmap rebuild. The actual folder walk runs on a
        background thread — on a large or networked archive that's real I/O,
        and running it on the main thread is what used to freeze the whole
        Tracker window (and, via the close-time dialog, briefly freeze NAB
        itself) while it walked every JPG ever saved."""
        month = self._hm_month_var.get().strip()
        try:
            mo = datetime.datetime.strptime(month, "%Y-%m")
        except Exception:
            self._hm_status.configure(
                text="Invalid month format (use YYYY-MM)", text_color="#EF5350")
            return
        month_suffix = mo.strftime("%m-%Y")

        self._hm_status.configure(text="Scanning…", text_color="#888")
        for w in self._hm_frame.winfo_children():
            w.destroy()
        self._hm_overlay.show(text=f"Scanning your archive for {month}…")

        base_root = nab_clip_scan.nab_base_root()
        threading.Thread(target=self._scan_heatmap_worker,
                         args=(base_root, month, month_suffix),
                         daemon=True).start()

    def _scan_heatmap_worker(self, base_root, month, month_suffix):
        """BACKGROUND THREAD — filesystem only, no widget access."""
        import glob, re
        from pathlib import Path
        try:
            paper_cat_counts = {}   # {(paper, category): count}
            papers, categories = set(), set()

            for jpg in glob.glob(os.path.join(base_root, "**", "*.jpg"),
                                 recursive=True):
                fname = os.path.basename(jpg)
                m = re.search(r"Date-(\d{2}-\d{2}-\d{4})", fname)
                if not m or not m.group(1).endswith(month_suffix):
                    continue
                paper = fname.split(",")[0].strip()
                rel   = os.path.relpath(jpg, base_root)
                parts = Path(rel).parts
                cat   = " / ".join(parts[3:-1]) if len(parts) > 4 else (
                        parts[3] if len(parts) == 4 else "Uncategorized")
                papers.add(paper)
                categories.add(cat)
                paper_cat_counts[(paper, cat)] = paper_cat_counts.get((paper, cat), 0) + 1

            data = {
                "paper_cat_counts": paper_cat_counts,
                "papers":     sorted(papers),
                "categories": sorted(categories),
                "month":      month,
            }
            self.after(0, lambda: self._render_heatmap(data, None))
        except Exception as e:
            logging.error(f"_scan_heatmap_worker: {e}")
            self.after(0, lambda err=e: self._render_heatmap(None, err))

    def _render_heatmap(self, data, error):
        """MAIN THREAD — builds the grid widgets from data already gathered
        by _scan_heatmap_worker. No I/O here, so this stays fast regardless
        of archive size."""
        try:
            if not self.winfo_exists():
                return   # Tracker closed while the scan was running
        except Exception:
            return
        self._hm_overlay.hide()

        if error is not None:
            self._hm_status.configure(text=f"Error: {error}", text_color="#EF5350")
            return

        self._hm_data = data
        papers     = data["papers"]
        categories = data["categories"]
        paper_cat_counts = data["paper_cat_counts"]
        month      = data["month"]

        if not papers:
            ctk.CTkLabel(self._hm_frame,
                text=f"No clips found for {month}",
                font=ctk.CTkFont(size=13), text_color="#444").pack(pady=40)
            self._hm_status.configure(text="No data", text_color="#555")
            return

        cats = sorted(categories)
        paps = sorted(papers)

        # Header row
        ctk.CTkLabel(self._hm_frame, text="Paper / Category",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color="#888", width=140, anchor="w").grid(
            row=0, column=0, padx=2, pady=2, sticky="w")
        for ci, cat in enumerate(cats):
            short = cat[-14:] if len(cat) > 14 else cat
            ctk.CTkLabel(self._hm_frame, text=short,
                         font=ctk.CTkFont(size=8), text_color="#666",
                         width=52, anchor="center").grid(
                row=0, column=ci+1, padx=1, pady=2)

        # Paper rows
        for pi, paper in enumerate(paps):
            short_paper = paper[:18] if len(paper) > 18 else paper
            ctk.CTkLabel(self._hm_frame, text=short_paper,
                         font=ctk.CTkFont(size=9), text_color="#CCC",
                         width=140, anchor="w").grid(
                row=pi+1, column=0, padx=2, pady=1, sticky="w")
            for ci, cat in enumerate(cats):
                count = paper_cat_counts.get((paper, cat), 0)
                if   count == 0: bg = "#111111"
                elif count == 1: bg = "#1A4A1A"
                elif count <= 3: bg = "#1E6B1E"
                elif count <= 5: bg = "#22A822"
                else:            bg = "#33CC33"
                cell = ctk.CTkFrame(
                    self._hm_frame, fg_color=bg,
                    width=50, height=22, corner_radius=4)
                cell.grid(row=pi+1, column=ci+1, padx=1, pady=1)
                cell.pack_propagate(False)
                txt = str(count) if count > 0 else ""
                ctk.CTkLabel(cell, text=txt,
                             font=ctk.CTkFont(size=8),
                             text_color="#EEE" if count > 0 else "#222"
                             ).pack(expand=True)

        total = sum(paper_cat_counts.values())
        self._hm_status.configure(
            text=f"{total} clips | {len(paps)} papers | {len(cats)} categories",
            text_color="#43A047")

    def _push_heatmap_to_sheet(self):
        """Push the current heatmap data as a new tab in Google Sheets."""
        if not self._hm_data:
            self._hm_status.configure(
                text="Load heatmap first", text_color="#EF5350")
            return
        creds = self.cfg.get("gs_creds_path", "").strip()
        sid   = self.cfg.get("gs_sheet_id",   "").strip()
        if not creds or not sid:
            self._hm_status.configure(
                text="Google Sheets not configured", text_color="#EF5350")
            return
        self._hm_status.configure(text="Pushing to Sheet…", text_color="#F59E0B")
        self.update_idletasks()

        def _do():
            try:
                import gspread
                from google.oauth2.service_account import Credentials
                scopes = ["https://www.googleapis.com/auth/spreadsheets",
                          "https://www.googleapis.com/auth/drive"]
                crd = Credentials.from_service_account_file(creds, scopes=scopes)
                gc  = gspread.authorize(crd)
                sh  = gc.open_by_key(sid)

                month     = self._hm_data["month"]
                tab_title = f"Heatmap {month}"
                paps = self._hm_data["papers"]
                cats = self._hm_data["categories"]
                pcc  = self._hm_data["paper_cat_counts"]

                # Delete existing tab if present
                try:
                    sh.del_worksheet(sh.worksheet(tab_title))
                except Exception:
                    pass

                ws = sh.add_worksheet(tab_title,
                                       rows=len(paps)+4, cols=len(cats)+3)
                rows = []
                rows.append([f"Coverage Heatmap — {month}"] + [""]*(len(cats)+1))
                rows.append(["Paper"] + cats + ["Total"])
                for paper in paps:
                    row = [paper]
                    total = 0
                    for cat in cats:
                        c = pcc.get((paper, cat), 0)
                        row.append(c if c > 0 else "")
                        total += c
                    row.append(total)
                    rows.append(row)
                ws.update(rows, value_input_option="USER_ENTERED")
                self.after(0, lambda: self._hm_status.configure(
                    text=f"✅ Pushed to Sheet: {tab_title}",
                    text_color="#43A047"))
            except Exception as e:
                self.after(0, lambda err=e: self._hm_status.configure(
                    text=f"❌ {err}", text_color="#EF5350"))
                logging.error(f"_push_heatmap_to_sheet: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def _build_settings(self):
        tab = self._tab_cfg
        tab.configure(fg_color=C_BG)

        frm = ctk.CTkFrame(tab, fg_color=C_SURF, corner_radius=10)
        frm.pack(fill="both", expand=True, padx=20, pady=16)

        def sec(t):
            ctk.CTkLabel(frm, text=t, font=ctk.CTkFont(size=13,weight="bold"),
                         text_color=C_ACCENT).pack(anchor="w", padx=20, pady=(16,4))

        def lbl_entry(label, width=440):
            ctk.CTkLabel(frm, text=label, text_color="#888").pack(anchor="w", padx=20)
            e = ctk.CTkEntry(frm, width=width, height=30, fg_color="#0A0A0A",
                              border_color="#333", text_color="#EEE")
            e.pack(anchor="w", padx=20, pady=(2,10)); return e

        sec("Telegram Bot (NAB local bot — same token)")
        self._e_token = lbl_entry("Bot Token")
        self._e_token.insert(0, self.cfg.get("tg_token",""))
        self._e_chat  = lbl_entry("Chat ID", 300)
        self._e_chat.insert(0, self.cfg.get("tg_chat_id",""))

        sec("Google Sheets")
        # ── Dependency check banner ──
        if not HAS_GSPREAD:
            ctk.CTkLabel(frm,
                text="⚠  gspread not installed.  Run:  pip install gspread google-auth",
                text_color=C_DANGER, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20, pady=(0,6))

        # Service-account JSON path
        ctk.CTkLabel(frm,
            text="Service Account JSON  (from Google Cloud Console → IAM → Service Accounts → Keys)",
            text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        crow = ctk.CTkFrame(frm, fg_color="transparent")
        crow.pack(anchor="w", padx=20, pady=(2,10))
        self._e_creds = ctk.CTkEntry(crow, width=360, height=30, fg_color="#0A0A0A",
                                      border_color="#333", text_color="#EEE",
                                      placeholder_text="C:\\path\\to\\service_account.json")
        self._e_creds.insert(0, self.cfg.get("gs_creds_path", ""))
        self._e_creds.pack(side="left")
        ctk.CTkButton(crow, text="Browse", width=80, height=30,
                      fg_color="#333", hover_color="#444",
                      command=self._browse_creds).pack(side="left", padx=8)

        # Spreadsheet ID
        ctk.CTkLabel(frm,
            text="Spreadsheet ID  (from the Sheet URL:  .../spreadsheets/d/  ←THIS PART→  /edit)",
            text_color="#888", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        self._e_sheet_id = ctk.CTkEntry(frm, width=440, height=30, fg_color="#0A0A0A",
                                         border_color="#333", text_color="#EEE",
                                         placeholder_text="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms")
        self._e_sheet_id.insert(0, self.cfg.get("gs_sheet_id", ""))
        self._e_sheet_id.pack(anchor="w", padx=20, pady=(2,6))

        # Test connection button
        ctk.CTkButton(frm, text="🔗 Test Connection", width=160, height=28,
                      fg_color="#1A3A5A", hover_color="#1E4A7A",
                      font=ctk.CTkFont(size=12),
                      command=self._test_gs_connection).pack(anchor="w", padx=20, pady=(0,12))

        sec("Reminder")
        ctk.CTkLabel(frm, text="Send Telegram reminder if no submission by hour (0-23, blank=off):",
                     text_color="#888").pack(anchor="w", padx=20)
        self._e_remind = ctk.CTkEntry(frm, width=80, height=30,
                                       fg_color="#0A0A0A", border_color="#333", text_color="#EEE")
        self._e_remind.insert(0, self.cfg.get("remind_hour",""))
        self._e_remind.pack(anchor="w", padx=20, pady=(2,10))

        self._cfg_status = ctk.CTkLabel(frm, text="", text_color=C_SUCCESS)
        self._cfg_status.pack(anchor="w", padx=20)
        ctk.CTkButton(frm, text="💾 Save Settings", width=160, height=36,
                      fg_color="#145A32", hover_color="#1E8449",
                      font=ctk.CTkFont(size=13,weight="bold"),
                      command=self._save_settings).pack(anchor="w", padx=20, pady=16)

        # Reset defaults button
        ctk.CTkButton(frm, text="↺ Reset paper list to default", width=200, height=30,
                      fg_color="#333", hover_color="#444", font=ctk.CTkFont(size=11),
                      command=self._reset_papers).pack(anchor="w", padx=20)

    def _browse_creds(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Select Service Account JSON file")
        if p:
            self._e_creds.delete(0, "end")
            self._e_creds.insert(0, p)

    def _test_gs_connection(self):
        creds = self._e_creds.get().strip()
        sid   = self._e_sheet_id.get().strip()
        if not creds or not sid:
            self._cfg_status.configure(
                text="⚠ Fill in both fields first", text_color=C_DANGER)
            return
        self._cfg_status.configure(text="⏳ Testing...", text_color="#F0A500")
        self.update()
        def _test():
            try:
                client = _gs_client(creds)
                sh = client.open_by_key(sid)
                name = sh.title
                self.after(0, lambda: self._cfg_status.configure(
                    text=f"✅ Connected to: \"{name}\"", text_color=C_SUCCESS))
            except Exception as e:
                self.after(0, lambda err=e: self._cfg_status.configure(
                    text=f"❌ {err}", text_color=C_DANGER))
        threading.Thread(target=_test, daemon=True).start()

    def _save_settings(self):
        self.cfg = {
            "tg_token":      self._e_token.get().strip(),
            "tg_chat_id":    self._e_chat.get().strip(),
            "remind_hour":   self._e_remind.get().strip(),
            "gs_creds_path": self._e_creds.get().strip(),
            "gs_sheet_id":   self._e_sheet_id.get().strip(),
        }
        save_cfg(self.cfg)
        self._cfg_status.configure(text="✅ Saved!")
        self.after(2500, lambda: self._cfg_status.configure(text=""))

    def _reset_papers(self):
        if messagebox.askyesno("Reset", "Reset paper list to factory default?", parent=self):
            self.papers = list(DEFAULT_PAPERS)
            save_papers(self.papers)
            self._refresh_paper_list_ui()
            self._build_paper_rows()
            self._load_date(self.editing_date)


# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEETS SETUP  (one-time, ~5 minutes)
# ══════════════════════════════════════════════════════════════════════════════
#
#  1. pip install gspread google-auth
#
#  2. Go to https://console.cloud.google.com
#     → New Project → Enable "Google Sheets API" + "Google Drive API"
#
#  3. IAM & Admin → Service Accounts → Create Service Account
#     → Keys tab → Add Key → JSON  →  save the downloaded .json file
#
#  4. Create a Google Sheet at https://sheets.google.com
#     Share it with the service account email (ends in @...iam.gserviceaccount.com)
#     Give it "Editor" permission
#
#  5. Copy the Spreadsheet ID from the URL:
#        https://docs.google.com/spreadsheets/d/ >>>THIS<<< /edit
#
#  6. In NAB Tracker → Settings tab:
#     • Service Account JSON → Browse to the .json file from step 3
#     • Spreadsheet ID → paste the ID from step 5
#     • Click "Test Connection" — should show the sheet name
#     • Save Settings
#
#  Each month auto-creates a new tab (e.g. "July 2026") with colour-coded
#  cells: green = received (shows price), red = missing, blue = off day.
#
# ══════════════════════════════════════════════════════════════════════════════
#  HOW TO INTEGRATE INTO NAB.pyw
# ══════════════════════════════════════════════════════════════════════════════
#
#  STEP 1 — Add import near top of NAB.pyw (after existing imports):
#      try:
#          from nab_tracker import NewspaperTracker
#          _HAS_TRACKER = True
#      except ImportError:
#          _HAS_TRACKER = False
#
#  STEP 2 — Auto-popup on login. In _finish_login(), at the very end add:
#      if _HAS_TRACKER:
#          self.after(1500, self._open_tracker)
#
#  STEP 3 — Add tracker method to NewsClipper class:
#      def _open_tracker(self):
#          if not hasattr(self, '_tracker') or not self._tracker.winfo_exists():
#              self._tracker = NewspaperTracker(self)
#          else:
#              self._tracker.lift()
#              self._tracker.focus_force()
#
#  STEP 4 — Add tracker button in setup_ui(), inside sub_btns section:
#      ctk.CTkButton(sub_btns, text="📰 Tracker", width=90, height=40,
#                    fg_color="#1A4A1A", hover_color="#1E6B1E",
#                    font=F_BTN, command=self._open_tracker).pack(side="left", padx=2)
#
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    root = ctk.CTk(); root.withdraw()
    app  = NewspaperTracker(root)
    app.mainloop()
