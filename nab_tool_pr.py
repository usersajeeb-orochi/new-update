# nab_tool_pr.py — PR Value Calculator (the old PR_Value_Calculator.xlsx, now inside NAB).
#
#   Print  : column-inch x ad rate (per page type, colour / B&W) x PR multiplier
#   Online : width px x height px x rate (per site) x PR multiplier
#   TV     : seconds x rate per second x PR multiplier
#
# What is new compared with the spreadsheet:
#   * rates are looked up automatically (fuzzy media-name match) — no more typing the ad value by hand
#   * Print rows can be imported straight from the clips NAB saved (paper / page / position / size come
#     from the file names), same-paper-same-page-type rows are added together
#   * Online rows can be imported from the Screenshot Bot (width / height come from the real image)
#   * everything is saved, totals are live, and "Export" writes an .xlsx with real formulas in the
#     original three-sheet layout
import os
import re
import json
import time
import shutil
import logging
import threading
import datetime

import difflib
import base64

import nab_engine
import nab_ai

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RATES = os.path.join(HERE, "pr_rates_default.json")
RATES_FILE = os.path.join(nab_engine.DOC_DIR, "nab_pr_rates.json")
DATA_FILE = os.path.join(nab_engine.DOC_DIR, "nab_pr_sheet.json")
IMG = {".jpg", ".jpeg", ".png", ".webp"}
PAGE_TYPES = ["Front Page", "2nd Page", "3rd Page", "5th Page", "7th Page", "9th Page", "Inner Page", "Sports Page",
              "Before Back Page", "Back Page", "Business Front", "Business Inner", "Business Back"]


def _key(s):
    s = (s or "").lower().strip()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"^the\s+", "", s)
    s = s.split("/")[0]
    s = re.sub(r"\.(com|net|org|info|tv|news|co|bd|com\.bd|net\.bd)(\.bd)?$", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _num(v, d=0.0):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return d


def guess_page_type(page, total_pages=0):
    """B1 -> Business Front, 1 -> Front Page, 3 -> 3rd Page ... anything else Inner Page.  Always editable."""
    p = (page or "").strip().upper()
    if not p:
        return "Inner Page"
    m = re.match(r"^([A-Z]?)\s*(\d+)$", p)
    if not m:
        return "Inner Page"
    sec, n = m.group(1), int(m.group(2))
    if sec == "B":
        return "Business Front" if n == 1 else "Business Inner"
    if sec == "S":
        return "Sports Page"
    if n == 1:
        return "Front Page"
    if total_pages and n == total_pages:
        return "Back Page"
    if total_pages and n == total_pages - 1:
        return "Before Back Page"
    return {2: "2nd Page", 3: "3rd Page", 5: "5th Page", 7: "7th Page", 9: "9th Page"}.get(n, "Inner Page")


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.RLock()
        self.rates = self._load_rates()
        self.data = self._load_data()

    # ------------------------------------------------------------------ storage
    def _load_rates(self):
        for p in (RATES_FILE, DEFAULT_RATES):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                d.setdefault("multiplier", 3.5)
                for k in ("print", "online", "tv"):
                    d.setdefault(k, [])
                return d
            except Exception:
                continue
        return {"multiplier": 3.5, "print": [], "online": [], "tv": []}

    def _save_rates(self):
        self._write(RATES_FILE, self.rates)

    def _load_data(self):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                d = json.load(f)
            for k in ("print", "online", "tv"):
                d.setdefault(k, [])
            return d
        except Exception:
            return {"print": [], "online": [], "tv": []}

    def _save_data(self):
        self._write(DATA_FILE, self.data)

    @staticmethod
    def _write(path, obj):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception as e:
            logging.error(f"pr save {path}: {e}")

    # ------------------------------------------------------------------ rate lookup
    def _find(self, kind, name):
        """Best match in the rate table for a media name / domain.  Returns the table row or None."""
        k = _key(name)
        if not k:
            return None
        rows = self.rates.get(kind, [])
        best, score = None, 0
        for r in rows:
            rk = _key(r["name"])
            if not rk:
                continue
            if rk == k:
                return r
            s = 0
            if rk in k or k in rk:
                s = min(len(rk), len(k)) / float(max(len(rk), len(k)))
                if len(rk) >= 5 and rk in k:                  # a file name like "Prothom Alo - tower news" contains the media name
                    s = max(s, 0.6 + min(len(rk), 20) / 100.0)
            if s > score and s >= 0.6:
                best, score = r, s
        return best

    def print_rate(self, media, page_type, colour=True):
        r = self._find("print", media)
        if not r:
            return None, None
        pt = r["rates"].get(page_type) or r["rates"].get("Inner Page") or {}
        v = pt.get("c" if colour else "b")
        if v is None:
            v = pt.get("b" if colour else "c")
        return v, r["name"]

    def api_lookup(self, a):
        kind = a.get("kind")
        if kind == "print":
            v, name = self.print_rate(a.get("media"), a.get("page_type") or "Inner Page", a.get("colour", True))
            return {"ok": v is not None, "rate": v, "match": name}
        r = self._find(kind, a.get("media"))
        if not r:
            return {"ok": False}
        return {"ok": True, "rate": r.get("rate"), "tier": r.get("tier"), "match": r["name"]}

    # ------------------------------------------------------------------ state
    def _row_value(self, kind, r):
        m = _num(self.rates.get("multiplier"), 3.5)
        if kind == "print":
            return _num(r.get("colinch")) * _num(r.get("ad")) * m
        if kind == "online":
            return _num(r.get("w")) * _num(r.get("h")) * _num(r.get("rate")) * m
        return _num(r.get("secs")) * _num(r.get("rate")) * m

    def _totals(self):
        t = {k: round(sum(self._row_value(k, r) for r in self.data[k]), 2) for k in ("print", "online", "tv")}
        t["all"] = round(sum(t.values()), 2)
        return t

    def api_state(self, a):
        with self.lock:
            return {"ok": True, "data": self.data, "multiplier": self.rates.get("multiplier", 3.5),
                    "totals": self._totals(), "page_types": PAGE_TYPES,
                    "pubs": [p["name"] for p in self.rates["print"]], "sites": [o["name"] for o in self.rates["online"]],
                    "tvs": [t["name"] for t in self.rates["tv"]], "date": self.e.current_date.strftime("%Y-%m-%d"),
                    "tool_ready": True}

    def api_save(self, a):
        """The UI sends the three row lists whenever the user edits; the server keeps and totals them."""
        with self.lock:
            for k in ("print", "online", "tv"):
                if isinstance(a.get(k), list):
                    self.data[k] = [r for r in a[k] if isinstance(r, dict)][:5000]
            if a.get("multiplier") is not None:
                m = _num(a.get("multiplier"), 3.5)
                if m > 0:
                    self.rates["multiplier"] = m
                    self._save_rates()
            self._save_data()
            return {"ok": True, "totals": self._totals()}

    def api_clear(self, a):
        with self.lock:
            for k in (a.get("kinds") or ["print", "online", "tv"]):
                if k in self.data:
                    self.data[k] = []
            self._save_data()
            return {"ok": True, "totals": self._totals()}

    def api_rate_set(self, a):
        """Edit one rate in the table (kept in Documents\\nab_pr_rates.json, the shipped table is never touched)."""
        with self.lock:
            kind, name = a.get("kind"), (a.get("name") or "").strip()
            if not name:
                return {"ok": False, "error": "Enter a name."}
            if kind == "print":
                row = next((r for r in self.rates["print"] if r["name"].lower() == name.lower()), None)
                if not row:
                    row = {"name": name, "group": a.get("group") or "Added", "rates": {}}
                    self.rates["print"].append(row)
                pt = a.get("page_type") or "Inner Page"
                row["rates"].setdefault(pt, {})["c" if a.get("colour", True) else "b"] = _num(a.get("rate"))
            elif kind in ("online", "tv"):
                row = next((r for r in self.rates[kind] if r["name"].lower() == name.lower()), None)
                if not row:
                    row = {"name": name}
                    if kind == "online":
                        row["tier"] = int(_num(a.get("tier"), 3))
                    self.rates[kind].append(row)
                row["rate"] = _num(a.get("rate"))
                if kind == "online" and a.get("tier") is not None:
                    row["tier"] = int(_num(a.get("tier"), 3))
            else:
                return {"ok": False, "error": "Unknown table."}
            self._save_rates()
            return {"ok": True}

    def api_rates_reset(self, a):
        with self.lock:
            try:
                if os.path.exists(RATES_FILE):
                    os.remove(RATES_FILE)
            except Exception:
                pass
            m = self.rates.get("multiplier", 3.5)
            self.rates = self._load_rates()
            self.rates["multiplier"] = m
            return {"ok": True}

    # ------------------------------------------------------------------ imports
    def _day_folder(self, date):
        return os.path.join(self.e.base_root, date.strftime("%Y"), date.strftime("%B"), date.strftime("%d-%m-%Y"))

    def _dates(self, a):
        try:
            d1 = datetime.datetime.strptime(a.get("from") or a.get("date") or "", "%Y-%m-%d").date()
        except Exception:
            d1 = self.e.current_date
        try:
            d2 = datetime.datetime.strptime(a.get("to") or "", "%Y-%m-%d").date()
        except Exception:
            d2 = d1
        if d2 < d1:
            d1, d2 = d2, d1
        out = []
        while d1 <= d2 and len(out) < 62:
            out.append(d1)
            d1 += datetime.timedelta(days=1)
        return out

    def api_import_print(self, a):
        """Saved clips -> Print rows.  Paper / page / position / size come from the file names."""
        import nab_recent
        colour = bool(a.get("colour", True))
        group = bool(a.get("group", True))
        total_pages = int(_num(a.get("total_pages"), 0))
        found = {}                       # (paper, page, size, date) -> {folder: count}
        n_files = 0
        for d in self._dates(a):
            root = self._day_folder(d)
            if not os.path.isdir(root):
                continue
            for dp, _dn, fns in os.walk(root):
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() not in IMG:
                        continue
                    p = nab_recent.parse_clip_name(fn)
                    if not p:
                        continue
                    n_files += 1
                    key = (p["paper"], p["page"], p["pos"], p["size"], p["date"])
                    found.setdefault(key, {}).setdefault(dp, 0)
                    found[key][dp] += 1
        rows, miss = [], 0
        for (paper, page, pos, size, date), folders in found.items():
            cnt = max(folders.values())          # same clip saved into several categories counts once
            m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*$", size or "")
            if not m:
                continue
            ci = float(m.group(1)) * float(m.group(2)) * cnt
            pt = guess_page_type(page, total_pages)
            ad, match = self.print_rate(paper, pt, colour)
            if ad is None:
                miss += 1
            rows.append({"media": paper, "tier": "", "page": page, "page_type": pt, "colour": colour, "colinch": round(ci, 2),
                         "ad": ad if ad is not None else 0, "note": "" if ad is not None else "no rate found", "n": cnt, "date": date})
        if group:
            g = {}
            for r in rows:
                k = (r["media"], r["page_type"])
                if k in g:
                    g[k]["colinch"] = round(g[k]["colinch"] + r["colinch"], 2)
                    g[k]["n"] += r["n"]
                    g[k]["page"] = ""
                else:
                    g[k] = dict(r)
            rows = list(g.values())
        rows.sort(key=lambda r: (r["media"].lower(), r["page_type"]))
        with self.lock:
            if a.get("replace", True):
                self.data["print"] = [r for r in self.data["print"] if not r.get("auto")]
            for r in rows:
                r["auto"] = True
            self.data["print"].extend(rows)
            self._save_data()
            return {"ok": True, "added": len(rows), "files": n_files, "no_rate": miss, "data": self.data, "totals": self._totals()}

    def api_import_online(self, a):
        """Screenshot-bot manifest(s) -> Online rows (real pixel width / height)."""
        folder = a.get("folder") or ""
        manifests = []
        if folder and os.path.isfile(folder):
            manifests = [folder]
        else:
            roots = [folder] if folder else [self.e.extra_settings.get("shot_dir") or os.path.join(nab_engine.DOC_DIR, "NAB_Screenshots")]
            for root in roots:
                for dp, _dn, fns in os.walk(root):
                    manifests += [os.path.join(dp, f) for f in fns if f == "shots.json"]
        rows, seen = [], set()
        for mp in manifests:
            try:
                with open(mp, encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                continue
            for it in items:
                if it.get("fail") or not it.get("w"):
                    continue
                u = it.get("url", "")
                if u in seen:
                    continue
                seen.add(u)
                site = it.get("site") or ""
                r = self._find("online", u) or self._find("online", site)
                rows.append({"media": r["name"] if r else (site or _key(u)), "date": (it.get("ts") or "")[:10], "tier": r.get("tier") if r else "",
                             "w": it["w"], "h": it["h"], "rate": r.get("rate") if r else 0, "url": u, "auto": True,
                             "note": "" if r else "no rate found"})
        with self.lock:
            if a.get("replace", True):
                self.data["online"] = [r for r in self.data["online"] if not r.get("auto")]
            self.data["online"].extend(rows)
            self._save_data()
            return {"ok": True, "added": len(rows), "no_rate": sum(1 for r in rows if not r["rate"]), "data": self.data, "totals": self._totals()}


    # ------------------------------------------------------------------ upload + measure (+ AI)
    def _candidates(self, kind, text, n=40):
        names = [r["name"] for r in self.rates.get(kind, [])]
        keys = {_key(x): x for x in names}
        k = _key(text)
        out = [keys[m] for m in difflib.get_close_matches(k, list(keys), n=n, cutoff=0.3)] if k else []
        for kk, nm in keys.items():
            if k and (k in kk or kk in k) and nm not in out:
                out.append(nm)
        return out[:n] or names[:n]

    def _thumb_bytes(self, b64):
        try:
            return base64.b64decode(b64.split(",")[-1])
        except Exception:
            return None

    def _ai_identify(self, kind, hint, thumb=None):
        """Name the media (and the page for print) from the file name and, if there is one, a picture of the item.
        Returns {"media","page","how"} with media = an exact name from the rate table, or "" when unsure."""
        ai = nab_ai.get()
        if not ai.ready():
            return {}
        cands = self._candidates(kind, hint or "")
        seen = ""
        img = self._thumb_bytes(thumb) if thumb else None
        if img and ai.vision_model():
            txt, why = ai.vision(img, "This is a newspaper clipping, website screenshot or TV frame from Bangladesh. Read the publication / website / channel name "
                                 "that is printed or shown (logo, header, URL bar) and the page number or label if any. "
                                 'Reply ONLY JSON: {"name": "...", "page": "...", "section": "..."} using empty strings when not visible.')
            if txt:
                seen = txt[:300]
        j, why = ai.ask_json(
            "You map messy media names to the exact name in a rate table. Reply ONLY JSON "
            '{"media": "<exact name from the list or empty string>", "page": "<page label like 1, 5, B1 or empty>", "section": "<front|back|inner|sports|business|empty>"}. '
            "Never invent a name that is not in the list.",
            f"Table names: {json.dumps(cands, ensure_ascii=False)}\nFile name / hint: {hint}\nWhat was read from the picture: {seen or 'nothing'}", fast=True, max_tokens=120)
        if not j:
            return {}
        m = (j.get("media") or "").strip()
        if m and m.lower() not in {c.lower() for c in cands}:
            m = ""
        return {"media": m, "page": str(j.get("page") or "").strip().upper(), "section": (j.get("section") or "").lower(), "how": "AI"}

    def api_analyze(self, a):
        """The screen reads each uploaded file's pixel size / video length itself and sends only that plus a small thumbnail."""
        import nab_recent
        kind = a.get("kind")
        items = a.get("items") or []
        colour = bool(a.get("colour", True))
        col_w = _num(a.get("col_width"), 0) or _num(self.e.extra_settings.get("pr_col_width"), 0) or 1.8
        ppi = 0.0
        try:
            ppi = float(self.e.paper_opts().get("ppi") or 0)
        except Exception:
            pass
        rows, ai_used = [], 0
        for it in items[:200]:
            name = os.path.splitext(str(it.get("name") or ""))[0]
            w, h, secs = int(_num(it.get("w"))), int(_num(it.get("h"))), _num(it.get("secs"))
            thumb = it.get("thumb")
            hint = re.sub(r"[_\-]+", " ", name)
            if kind == "print":
                p = nab_recent.parse_clip_name(str(it.get("name") or ""))
                media, page, note, est, ident = "", "", "", False, {}
                m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*$", (p or {}).get("size", ""))
                if p and m:
                    media, page = p["paper"], p["page"]
                    cols, inch = float(m.group(1)), float(m.group(2))
                    note = "exact, from the file name"
                else:
                    ident = self._ai_identify("print", hint, thumb)
                    ai_used += bool(ident)
                    media, page = ident.get("media") or hint, ident.get("page") or ""
                    if ppi <= 0 or not w or not h:
                        cols = inch = 0
                        note = "set inches: calibrate once in the Clip screen (Calibrate inches)"
                    else:
                        wi, inch = w / ppi, h / ppi
                        cols = max(1, round(wi / col_w))
                        inch = round(inch * 2) / 2.0
                        note, est = f"estimate: {cols} col x {inch:g} in (column {col_w:g} in)", True
                pt = guess_page_type(page, _num(a.get("total_pages"), 0)) if page else "Inner Page"
                if not p or not m:
                    sec = ident.get("section") or ""
                    pt = {"front": "Front Page", "back": "Back Page", "sports": "Sports Page", "business": "Business Inner"}.get(sec, pt) if not page else pt
                ad, match = self.print_rate(media, pt, colour)
                rows.append({"media": match or media, "page": page, "page_type": pt, "colour": colour, "colinch": round(cols * inch, 2), "ad": ad or 0,
                             "note": note if ad else (note + "; no rate found").strip("; "), "src": it.get("name"), "auto": True, "est": est})
            elif kind == "online":
                r = self._find("online", hint)
                if not r:
                    ident = self._ai_identify("online", hint, thumb)
                    ai_used += bool(ident)
                    r = self._find("online", ident.get("media") or "")
                rows.append({"media": r["name"] if r else hint, "date": time.strftime("%Y-%m-%d"), "tier": r.get("tier") if r else "", "w": w, "h": h,
                             "rate": r.get("rate") if r else 0, "note": "" if r else "no rate found", "src": it.get("name"), "auto": True})
            else:
                r = self._find("tv", hint)
                if not r:
                    ident = self._ai_identify("tv", hint, thumb)
                    ai_used += bool(ident)
                    r = self._find("tv", ident.get("media") or "")
                rows.append({"media": r["name"] if r else hint, "date": time.strftime("%Y-%m-%d"), "peak": "", "secs": round(secs, 1),
                             "rate": r.get("rate") if r else 0, "note": "" if r else "no rate found", "src": it.get("name"), "auto": True})
        with self.lock:
            self.data[kind].extend(rows)
            self._save_data()
            return {"ok": True, "added": len(rows), "ai": ai_used, "data": self.data, "totals": self._totals(), "ai_ready": nab_ai.get().ready()}

    def api_report(self, a):
        """Plain-language summary paragraph of the current numbers (AI), for the report / email."""
        ai = nab_ai.get()
        with self.lock:
            t = self._totals()
            top = sorted(([k, r.get("media"), self._row_value(k, r)] for k in ("print", "online", "tv") for r in self.data[k]), key=lambda x: -x[2])[:8]
        if not ai.ready():
            return {"ok": False, "error": "AI is off or has no key."}
        txt, why = ai.chat([{"role": "system", "content": "You write short, factual PR-value summaries for a media-monitoring report in English. 3-4 sentences. Amounts are Bangladeshi Taka."},
                            {"role": "user", "content": f"Totals: {json.dumps(t)}. Biggest items (medium, media, value): {json.dumps(top, ensure_ascii=False)}. Client/topic: {a.get('topic') or 'the client'}."}], max_tokens=260)
        return {"ok": txt is not None, "text": txt, "error": why}

    # ------------------------------------------------------------------ export
    def api_export(self, a):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except Exception:
            return {"ok": False, "error": "openpyxl is not installed (pip install openpyxl)."}
        with self.lock:
            data = json.loads(json.dumps(self.data))
            mult = _num(self.rates.get("multiplier"), 3.5)
        wb = openpyxl.Workbook()
        head_fill = PatternFill("solid", fgColor="1F2A44")
        head_font = Font(bold=True, color="FFFFFF")
        thin = Side(style="thin", color="D0D5DD")
        box = Border(left=thin, right=thin, top=thin, bottom=thin)

        def sheet(ws, headers, rows, widths, money_cols, total_col):
            ws.append(headers)
            for c in ws[1]:
                c.fill, c.font, c.alignment = head_fill, head_font, Alignment(horizontal="center", vertical="center", wrap_text=True)
            for r in rows:
                ws.append(r)
            last = ws.max_row
            ws.append([None] * len(headers))
            tr = ws.max_row
            ws.cell(tr, 1, "Total").font = Font(bold=True)
            ws.cell(tr, total_col, f"=SUM({get_column_letter(total_col)}2:{get_column_letter(total_col)}{max(last, 2)})").font = Font(bold=True)
            for ci, w in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(ci)].width = w
            for row in ws.iter_rows(min_row=1, max_row=tr):
                for c in row:
                    c.border = box
            for cc in money_cols:
                for r in range(2, tr + 1):
                    ws.cell(r, cc).number_format = "#,##0.00"
            ws.freeze_panes = "A2"

        ws = wb.active
        ws.title = "Print"
        rows = []
        for i, r in enumerate(data["print"], 1):
            n = i + 1
            rows.append([i, r.get("media"), r.get("tier") or None, r.get("page_type") or r.get("page"), _num(r.get("colinch")), _num(r.get("ad")),
                         mult, f"=(E{n}*F{n}*G{n})"])
        sheet(ws, ["SL No.", "Media Name", "Tier", "Page", "Col x Inch", "AD Value", "PR Valuation Rate", "PR Value"], rows,
              [8, 28, 7, 18, 13, 12, 18, 16], [5, 6, 8], 8)
        ws = wb.create_sheet("Online")
        rows = []
        for i, r in enumerate(data["online"], 1):
            n = i + 1
            rows.append([i, r.get("media"), r.get("date"), r.get("tier") or None, _num(r.get("w")), _num(r.get("h")),
                         f"=E{n}*F{n}", _num(r.get("rate")), mult, f"=(G{n}*H{n}*I{n})"])
        sheet(ws, ["Sl No.", "Media Name", "Date", "Tier", "Width", "Height", "PXL Count", "Rate", "PR Valuation Rate", "Value"], rows,
              [8, 30, 12, 7, 10, 10, 14, 9, 18, 16], [7, 10], 10)
        ws = wb.create_sheet("TV")
        rows = []
        for i, r in enumerate(data["tv"], 1):
            n = i + 1
            rows.append([r.get("media"), r.get("date"), r.get("peak"), _num(r.get("secs")), _num(r.get("rate")), mult, f"=D{n}*E{n}*F{n}"])
        sheet(ws, ["Media Name", "Date", "Peak/Off Peak", "Duration (Second)", "Rate", "PR Valuation Rate", "PR Value"], rows,
              [24, 12, 14, 18, 10, 18, 16], [7], 7)
        ws = wb.create_sheet("Summary")
        ws.append(["Medium", "PR Value"])
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
        ws.append(["Print", "=Print!H%d" % (len(data["print"]) + 2)])
        ws.append(["Online", "=Online!J%d" % (len(data["online"]) + 2)])
        ws.append(["TV", "=TV!G%d" % (len(data["tv"]) + 2)])
        ws.append(["Grand total", "=SUM(B2:B4)"])
        ws["A5"].font = ws["B5"].font = Font(bold=True)
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 20
        for r in range(2, 6):
            ws.cell(r, 2).number_format = "#,##0.00"
        out = a.get("path") or os.path.join(nab_engine.DOC_DIR, f"PR_Value_{time.strftime('%d-%m-%Y_%H%M')}.xlsx")
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            wb.save(out)
        except Exception as e:
            return {"ok": False, "error": f"Could not write the file: {e}"}
        return {"ok": True, "path": out}

    def api_reveal(self, a):
        p = a.get("path")
        if p and os.path.exists(p):
            return self.e.reveal(os.path.dirname(p))
        return {"ok": False}
