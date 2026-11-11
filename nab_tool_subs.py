# nab_tool_subs.py — paper subscription expiry dates (web). Same file as the classic nab_subscriptions.py:
# Documents\nab_subscription_expiry.json  {"Paper Name": "DD-MM-YYYY"}, warns WARN_DAYS_BEFORE days ahead.
import os
import json
import logging
import datetime

import nab_engine
from nab_text import strip_emoji_prefix

SUBS_FILE = os.path.join(nab_engine.DOC_DIR, "nab_subscription_expiry.json")
WARN_DAYS_BEFORE = 3


def load_expiries():
    try:
        with open(SUBS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_expiries(data):
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"save_expiries: {e}")
        return False


def _days(date_str):
    try:
        return (datetime.datetime.strptime(date_str, "%d-%m-%Y").date() - datetime.date.today()).days
    except Exception:
        return None


class Tool:
    def __init__(self, engine):
        self.e = engine

    def api_list(self, a):
        data = load_expiries()
        rows = []
        for raw in self.e.paper_list:
            p = strip_emoji_prefix(raw)
            ds = data.get(p, "")
            rows.append({"paper": p, "raw": raw, "date": ds, "iso": _iso(ds), "days": _days(ds) if ds else None})
        return {"ok": True, "rows": rows, "warn": WARN_DAYS_BEFORE}

    def api_set(self, a):
        data = load_expiries()
        p = strip_emoji_prefix(a["paper"])
        iso = (a.get("iso") or "").strip()
        if not iso:
            data.pop(p, None)
        else:
            try:
                data[p] = datetime.date.fromisoformat(iso).strftime("%d-%m-%Y")
            except ValueError:
                return {"ok": False, "error": "Bad date"}
        return {"ok": save_expiries(data)}

    def api_expiring(self, a):
        known = {strip_emoji_prefix(p) for p in self.e.paper_list}
        out = []
        for p, ds in load_expiries().items():
            if p not in known:
                continue
            d = _days(ds)
            if d is not None and d <= WARN_DAYS_BEFORE:
                out.append({"paper": p, "date": ds, "days": d})
        out.sort(key=lambda r: r["days"])
        return {"ok": True, "items": out}


def _iso(ds):
    try:
        return datetime.datetime.strptime(ds, "%d-%m-%Y").date().isoformat()
    except Exception:
        return ""
