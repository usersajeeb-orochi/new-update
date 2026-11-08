# nab_tool_tracker.py — Newspaper Tracker as a web tool (no Tk). Same data as the classic nab_tracker.py:
# registry HKCU\Software\NAB\Tracker (prices, Telegram, Sheet), Documents\nab_tracker_log.json / nab_tracker_papers.json,
# same Google-Sheet layout (one tab per month, one column per day).
import os
import json
import logging
import calendar
import datetime
import threading
import time

import requests

import nab_clip_scan
import nab_connections as _nc
import nab_engine

try:
    import gspread
    from google.oauth2.service_account import Credentials as _SACredentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

try:
    import winreg
except ImportError:           # tests / non-Windows: keep the same keys in a JSON file
    winreg = None

REG_PATH = r"Software\NAB\Tracker"
_DOC = nab_engine.DOC_DIR
_FALLBACK = os.path.join(_DOC, "nab_tracker_reg.json")


def _rget(key, default=""):
    if winreg is None:
        try:
            with open(_FALLBACK, encoding="utf-8") as f:
                return json.load(f).get(key, default)
        except Exception:
            return default
    try:
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        v, _ = winreg.QueryValueEx(hk, key)
        winreg.CloseKey(hk)
        return v
    except Exception:
        return default


def _rset(key, value):
    if winreg is None:
        try:
            d = {}
            if os.path.exists(_FALLBACK):
                with open(_FALLBACK, encoding="utf-8") as f:
                    d = json.load(f)
            d[key] = str(value)
            with open(_FALLBACK, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except Exception as e:
            logging.error(f"tracker reg: {e}")
        return
    try:
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        hk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(hk, key, 0, winreg.REG_SZ, str(value))
        winreg.CloseKey(hk)
    except Exception as e:
        logging.error(f"tracker reg: {e}")


LOG_FILE = os.path.join(_DOC, "nab_tracker_log.json")
PAPERS_FILE = os.path.join(_DOC, "nab_tracker_papers.json")

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
            with open(PAPERS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return list(DEFAULT_PAPERS)


def save_papers(lst):
    with open(PAPERS_FILE, "w", encoding="utf-8") as f:
        json.dump(lst, f, indent=2, ensure_ascii=False)


def load_prices():
    raw = _rget("prices")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return dict(DEFAULT_PRICES)


def save_prices(p):
    _rset("prices", json.dumps(p))


def load_cfg():
    return {
        "tg_token": _rget("tg_token"),
        "tg_chat_id": _rget("tg_chat_id"),
        "remind_hour": _rget("remind_hour", "18"),
        "gs_creds_path": (_rget("gs_creds_path") if os.path.isfile(_rget("gs_creds_path") or "")
                          else _nc.google_key_file()),
        "gs_sheet_id": _rget("gs_sheet_id") or _nc.sheet_id(),
    }


def save_cfg(c):
    for k, v in c.items():
        if k == "gs_sheet_id" and v == _nc.BUILTIN_SHEET_ID:
            v = ""
        if k == "gs_creds_path" and v == _nc.google_key_file() and not _rget("gs_creds_path"):
            v = ""
        _rset(k, v)


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

# ── Auto-backfill missed days ──────────────────────────────────────────────────
def backfill_missed_days():
    log = _load_log()
    today = datetime.date.today()
    if not log:
        return
    earliest = min(log.keys())
    for i in range(1, 31):
        iso = (today - datetime.timedelta(days=i)).isoformat()
        if iso < earliest:
            break
        if iso not in log:
            _log_entry(iso, "auto_missed")
        else:
            break


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

    # Rows are found by paper NAME in column B, so PCs with differently ordered paper lists never overwrite each other's rows.
    try:
        names = [str(x).strip() for x in ws.col_values(2)]
    except Exception:
        names = []
    row_of = {}
    for idx, nm in enumerate(names):
        if idx >= 2 and nm and nm not in row_of:
            row_of[nm] = idx                      # 0-indexed row
    next_row = max(len(names), 2)
    new_rows = []
    for paper in papers:
        if paper not in row_of:
            row_of[paper] = next_row
            new_rows.append([next_row - 1, paper])
            next_row += 1
    if new_rows:
        try:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        except Exception as ex:
            logging.error(f"sheet append papers: {ex}")

    for i, paper in enumerate(papers):
        row_0 = row_of[paper]

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
# ── Pull from the Google Sheet (so every PC shows what the other PCs entered) ─────────────────────────────
def _num(v):
    t = str(v).strip().replace("\u09f3", "").replace(",", "").replace("Tk", "").strip()
    try:
        return float(t)
    except Exception:
        return None


_NOT_PAPER = None


def is_paper_name(nm):
    """True for a real newspaper name; False for blanks, numbers and the totals / notes people write under the list."""
    import re
    global _NOT_PAPER
    if _NOT_PAPER is None:
        _NOT_PAPER = re.compile(r"^(total|extra|grand|sum|sub\s*total|net|balance|bill|payment|paid|due|remarks?|note)\b", re.I)
    nm = str(nm or "").strip()
    if not nm or _num(nm) is not None or _NOT_PAPER.match(nm):
        return False
    return any(ch.isalpha() for ch in nm)


def parse_month_values(rows, year, month):
    """rows = worksheet values. Returns ({iso: entry}, [paper names in sheet order])."""
    out, papers = {}, []
    if len(rows) < 3:
        return out, papers
    plist = []
    for r in rows[2:]:
        nm = str(r[1]).strip() if len(r) > 1 else ""
        if is_paper_name(nm):
            plist.append((nm, r))
            papers.append(nm)
        elif plist:
            break                      # first total / note / blank row under the list: the paper list is over
    nd = calendar.monthrange(year, month)[1]
    for day in range(1, nd + 1):
        col = day + 1
        rec, miss, prices, off, auto = [], [], {}, 0, 0
        for nm, r in plist:
            v = str(r[col]).strip() if len(r) > col else ""
            if not v:
                continue
            if v.upper() == "OFF":
                off += 1
            elif v == "?":
                auto += 1
            elif v in ("\u2717", "\u2718", "x", "X"):
                miss.append(nm)
            else:
                n = _num(v)
                if n is not None:
                    rec.append(nm)
                    prices[nm] = n
        iso = datetime.date(year, month, day).isoformat()
        if off:
            out[iso] = {"status": "off_day", "received": [], "missing": [], "prices": {}, "total": 0.0}
        elif rec or miss:
            out[iso] = {"status": "submitted", "received": rec, "missing": miss, "prices": prices, "total": round(sum(prices.values()), 2)}
        elif auto:
            out[iso] = {"status": "auto_missed", "received": [], "missing": [], "prices": {}, "total": 0.0}
    return out, papers


def merge_sheet_days(log, days):
    """Fill gaps and 'not submitted' days from the sheet. A day already submitted here is never overwritten
    (reported as a difference instead). Returns (changed_dates, differing_dates)."""
    changed, differ = [], []
    today = datetime.date.today().isoformat()
    for iso, ent in sorted(days.items()):
        if iso > today:
            continue
        cur = log.get(iso)
        if cur is None or (cur.get("status") == "auto_missed" and ent["status"] != "auto_missed"):
            e = dict(ent)
            e["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            e["src"] = "sheet"
            log[iso] = e
            changed.append(iso)
        elif cur.get("status") == "submitted" and ent["status"] == "submitted" and set(cur.get("received", [])) != set(ent["received"]):
            differ.append(iso)
    return changed, differ


# ── Telegram ───────────────────────────────────────────────────────────────────
def tg_send(token, chat_id, text):
    if not token or not chat_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=8)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Web API
# ══════════════════════════════════════════════════════════════════════════════
def _d(iso):
    return datetime.date.fromisoformat(iso) if iso else datetime.date.today()


class Tool:
    def __init__(self, engine):
        self.e = engine
        self._bf = False
        self._pull_lock = threading.Lock()
        self._last_pull = 0.0

    # ---- helpers
    def _base(self):
        return self.e.base_root

    def _cfg(self):
        c = load_cfg()
        return c

    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="tracker", **kw)

    # ---- sheet -> this PC
    def _pull(self, months_back=2):
        c = self._cfg()
        creds, sid = (c["gs_creds_path"] or "").strip(), (c["gs_sheet_id"] or "").strip()
        if not creds or not sid:
            return {"ok": False, "error": "Google Sheets is not configured - check Settings."}
        if not self._pull_lock.acquire(blocking=False):
            return {"ok": True, "busy": True, "changed": []}
        try:
            sp = _gs_client(creds).open_by_key(sid)
            titles = {w.title.strip(): w for w in sp.worksheets()}
            today = datetime.date.today()
            log = _load_log()
            for k in [k for k, v in log.items() if isinstance(v, dict) and v.get("src") == "sheet"]:
                del log[k]            # rebuilt below from the sheet, so anything wrongly pulled earlier disappears
            changed, differ, sheet_papers = [], [], []
            y, m = today.year, today.month
            for _i in range(months_back + 1):
                label = datetime.date(y, m, 1).strftime("%B %Y")
                ws = titles.get(label)
                if ws is not None:
                    days, plist = parse_month_values(ws.get_all_values(), y, m)
                    ch, df = merge_sheet_days(log, days)
                    changed += ch
                    differ += df
                    for nm in plist:
                        if nm not in sheet_papers:
                            sheet_papers.append(nm)
                m -= 1
                if m == 0:
                    y, m = y - 1, 12
            _save_log(log)
            have = load_papers()
            clean = [p for p in have if is_paper_name(p)]
            if len(clean) != len(have):
                save_papers(clean)    # drop numbers / "Total" rows that an earlier sync had added by mistake
                have = clean
            add = [p for p in sheet_papers if p not in have]
            if add:
                save_papers(have + add)
            self._last_pull = time.time()
            return {"ok": True, "changed": sorted(changed), "differ": sorted(differ), "papers_added": add}
        except Exception as ex:
            logging.error(f"tracker pull: {ex}")
            return {"ok": False, "error": str(ex)[:300]}
        finally:
            self._pull_lock.release()

    def _pull_bg(self, months_back=2, manual=False):
        def work():
            r = self._pull(months_back)
            if r.get("busy"):
                return
            self._emit(stage="pulled", manual=manual, **{k: v for k, v in r.items() if k != "busy"})
        threading.Thread(target=work, daemon=True, name="NAB-TrackerPull").start()

    def api_sync(self, a):
        """Pull the last few months from the Google Sheet (button)."""
        self._pull_bg(int(a.get("months", 2)), manual=True)
        return {"ok": True}

    def api_open_sheet(self, a):
        import re, webbrowser
        sid = (self._cfg().get("gs_sheet_id") or "").strip()
        if not re.match(r"^[A-Za-z0-9_-]{20,}$", sid):
            return {"ok": False, "error": "No Google Sheet is set - check Settings."}
        try:
            webbrowser.open("https://docs.google.com/spreadsheets/d/" + sid + "/edit")
            return {"ok": True}
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

    # ---- load everything the screen needs
    def api_load(self, a):
        if time.time() - self._last_pull > 120:
            self._last_pull = time.time()
            self._pull_bg(2)
        if not self._bf:
            self._bf = True
            try:
                backfill_missed_days()
            except Exception as ex:
                logging.error(f"backfill: {ex}")
        c = self._cfg()
        return {"ok": True, "papers": load_papers(), "prices": load_prices(),
                "cfg": {"tg_chat_id": c["tg_chat_id"], "remind_hour": c["remind_hour"], "gs_sheet_id": c["gs_sheet_id"],
                        "gs_creds_path": c["gs_creds_path"], "has_token": bool(c["tg_token"]),
                        "has_key": bool(c["gs_creds_path"] and os.path.isfile(c["gs_creds_path"]))},
                "today": datetime.date.today().isoformat()}

    def api_day(self, a):
        d = _d(a.get("date"))
        e = _load_log().get(d.isoformat(), {})
        mt, ms, mo, mm = _get_month_stats(d.year, d.month)
        return {"ok": True, "entry": e, "month": {"total": mt, "submitted": ms, "off": mo, "missed": mm}}

    def api_scan(self, a):
        """Which papers have clips saved on that date (matched to the tracker's paper list)."""
        d = _d(a.get("date"))
        papers = a.get("papers") or load_papers()
        try:
            matched, unknown, methods = nab_clip_scan.papers_clipped_on(d, papers, base_root=self._base(), return_methods=True)
            return {"ok": True, "matched": matched, "unknown": unknown, "methods": methods}
        except Exception as ex:
            logging.error(f"tracker scan: {ex}")
            return {"ok": False, "error": str(ex), "matched": {}, "unknown": {}}

    def api_alias(self, a):
        ok = nab_clip_scan.save_alias(a["raw"], a["paper"])
        return {"ok": bool(ok)}

    # ---- submit / off day
    def _push(self, d, status, papers, prices_t, received, missing, total, wait):
        errs = []
        c = self._cfg()
        day_str = d.strftime("%d %B %Y")

        def work():
            creds, sid = (c["gs_creds_path"] or "").strip(), (c["gs_sheet_id"] or "").strip()
            if creds and sid:
                try:
                    gs_write_day(creds, sid, d, status, prices_t, set(received), set(missing), papers)
                except Exception as ex:
                    errs.append(f"Google Sheets: {ex}")
            else:
                errs.append("Google Sheets not configured — check Settings")
            tok, cid = c["tg_token"], c["tg_chat_id"]
            if status == "off_day":
                tg_send(tok, cid, f"🏖 *Off Day — {day_str}*")
            else:
                if missing:
                    lines = "\n".join(f"  ❌ {p}" for p in sorted(missing))
                    msg = (f"📰 *{day_str}*\n✅ {len(received)} received  ❌ {len(missing)} missing\n\n"
                           f"*Missing:*\n{lines}\n\n💰 Today: *৳{total:.2f}*")
                else:
                    msg = f"📰 *{day_str}*\n✅ All *{len(received)}* papers received!\n💰 *৳{total:.2f}*"
                tg_send(tok, cid, msg)
                mt, ms, mo, mm = _get_month_stats(d.year, d.month)
                tg_send(tok, cid, f"📅 *{d.strftime('%B %Y')}:* ৳{mt:.2f} total  ({ms} days)")
            self._emit(stage="synced", date=d.isoformat(), errors=errs)

        t = threading.Thread(target=work, daemon=True, name="NAB-TrackerSync")
        t.start()
        if wait:
            t.join(20)
        return errs

    def api_submit(self, a):
        d = _d(a.get("date"))
        papers = a.get("papers") or load_papers()
        received = [p for p in papers if p in set(a.get("received", []))]
        missing = [p for p in papers if p not in set(received)]
        prices = load_prices()
        ov = a.get("overrides") or {}
        prices_t = {}
        for p in papers:
            v = ov.get(p)
            try:
                prices_t[p] = float(v) if v not in (None, "") else float(prices.get(p, DEFAULT_PRICES.get(p, 0)))
            except Exception:
                prices_t[p] = float(prices.get(p, DEFAULT_PRICES.get(p, 0)))
        total = sum(prices_t[p] for p in received)
        _log_entry(d.isoformat(), "submitted", received, missing, prices_t, total)
        errs = self._push(d, "submitted", papers, prices_t, received, missing, total, bool(a.get("wait")))
        mt, ms, mo, mm = _get_month_stats(d.year, d.month)
        return {"ok": True, "total": total, "received": len(received), "missing": len(missing), "errors": errs,
                "month": {"total": mt, "submitted": ms, "off": mo, "missed": mm}}

    def api_off(self, a):
        d = _d(a.get("date"))
        _log_entry(d.isoformat(), "off_day")
        errs = self._push(d, "off_day", load_papers(), {}, [], [], 0.0, bool(a.get("wait")))
        return {"ok": True, "errors": errs}

    # ---- month calendar + heatmap
    def api_month(self, a):
        y, m = int(a["year"]), int(a["month"])
        log = _load_log()
        days = {}
        for k, v in log.items():
            if k.startswith(f"{y:04d}-{m:02d}"):
                days[k] = {"status": v.get("status", ""), "total": v.get("total", 0), "missing": len(v.get("missing", []))}
        mt, ms, mo, mm = _get_month_stats(y, m)
        return {"ok": True, "days": days, "ndays": calendar.monthrange(y, m)[1],
                "first_weekday": calendar.monthrange(y, m)[0],
                "stats": {"total": mt, "submitted": ms, "off": mo, "missed": mm}}

    def api_heatmap(self, a):
        import re
        from pathlib import Path
        month = a.get("month") or datetime.datetime.now().strftime("%Y-%m")
        try:
            mo = datetime.datetime.strptime(month, "%Y-%m")
        except Exception:
            return {"ok": False, "error": "Month must be YYYY-MM"}
        suffix = mo.strftime("%m-%Y")
        base = self._base()
        counts, papers, cats = {}, set(), set()
        pat = re.compile(r"Date-(\d{2}-\d{2}-\d{4})")
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                m = pat.search(fn)
                if not m or not m.group(1).endswith(suffix):
                    continue
                paper = fn.split(",")[0].strip()
                parts = Path(os.path.relpath(os.path.join(root, fn), base)).parts
                cat = " / ".join(parts[3:-1]) if len(parts) > 4 else (parts[3] if len(parts) == 4 else "Uncategorized")
                papers.add(paper)
                cats.add(cat)
                counts[(paper, cat)] = counts.get((paper, cat), 0) + 1
        self._hm = {"month": month, "papers": sorted(papers), "cats": sorted(cats), "counts": counts}
        return {"ok": True, "month": month, "papers": self._hm["papers"], "cats": self._hm["cats"],
                "cells": [[p, c, n] for (p, c), n in counts.items()]}

    def api_heatmap_push(self, a):
        hm = getattr(self, "_hm", None)
        if not hm:
            return {"ok": False, "error": "Load the heatmap first"}
        c = self._cfg()
        creds, sid = (c["gs_creds_path"] or "").strip(), (c["gs_sheet_id"] or "").strip()
        if not creds or not sid:
            return {"ok": False, "error": "Google Sheets not configured"}

        def work():
            try:
                sh = _gs_client(creds).open_by_key(sid)
                title = f"Heatmap {hm['month']}"
                try:
                    sh.del_worksheet(sh.worksheet(title))
                except Exception:
                    pass
                ws = sh.add_worksheet(title, rows=len(hm["papers"]) + 4, cols=len(hm["cats"]) + 3)
                rows = [[f"Coverage Heatmap — {hm['month']}"] + [""] * (len(hm["cats"]) + 1), ["Paper"] + hm["cats"] + ["Total"]]
                for p in hm["papers"]:
                    row, tot = [p], 0
                    for ct in hm["cats"]:
                        n = hm["counts"].get((p, ct), 0)
                        row.append(n if n else "")
                        tot += n
                    rows.append(row + [tot])
                ws.update(rows, value_input_option="USER_ENTERED")
                self._emit(stage="heatmap_pushed", ok=True, title=title)
            except Exception as ex:
                logging.error(f"heatmap push: {ex}")
                self._emit(stage="heatmap_pushed", ok=False, error=str(ex))
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    # ---- papers / prices / settings
    def api_papers_save(self, a):
        lst = [str(p).strip() for p in a.get("papers", []) if str(p).strip()]
        save_papers(lst)
        return {"ok": True}

    def api_papers_reset(self, a):
        save_papers(list(DEFAULT_PAPERS))
        return {"ok": True, "papers": list(DEFAULT_PAPERS)}

    def api_prices_save(self, a):
        pr = load_prices()
        for k, v in (a.get("prices") or {}).items():
            try:
                pr[k] = float(v)
            except Exception:
                pass
        save_prices(pr)
        return {"ok": True}

    def api_settings_save(self, a):
        c = self._cfg()
        for k in ("tg_chat_id", "remind_hour", "gs_sheet_id", "gs_creds_path"):
            if k in a:
                c[k] = str(a[k]).strip()
        if a.get("tg_token"):
            c["tg_token"] = str(a["tg_token"]).strip()
        save_cfg(c)
        return {"ok": True}

    def api_test_sheet(self, a):
        c = self._cfg()
        try:
            cl = _gs_client(c["gs_creds_path"])
            sh = cl.open_by_key(c["gs_sheet_id"])
            return {"ok": True, "title": sh.title}
        except Exception as ex:
            return {"ok": False, "error": str(ex)[:300]}

    # ---- end-of-day prompt
    def api_end_check(self, a):
        d = datetime.date.today()
        e = _load_log().get(d.isoformat(), {})
        if e.get("status") in ("submitted", "off_day"):
            return {"ok": True, "skip": True}
        papers = load_papers()
        r = self.api_scan({"date": d.isoformat(), "papers": papers})
        return {"ok": True, "skip": False, "papers": papers, "date": d.isoformat(), "matched": r.get("matched", {}),
                "unknown": r.get("unknown", {}), "prices": load_prices()}

    # ---- reminder (Telegram "no submission by hour")
    def reminder_due(self):
        try:
            h = int(self._cfg()["remind_hour"])
        except Exception:
            return False
        now = datetime.datetime.now()
        e = _load_log().get(now.date().isoformat(), {})
        return now.hour >= h and e.get("status") not in ("submitted", "off_day")
