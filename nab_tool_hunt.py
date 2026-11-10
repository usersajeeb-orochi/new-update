# nab_tool_hunt.py — News Hunter inside NAB: per-client keyword sets, Bangladesh-only filtering (from NewsBot),
# Groq checks, scheduler with Telegram / txt digests, and hand-off of found links to the Screenshot Bot.
import os
import re
import json
import time
import uuid
import logging
import threading
import datetime

import nab_engine
import nab_ai
from nhunt import engine as hx, output, bdfilter
from nhunt.store import Store

SET_FILE = os.path.join(nab_engine.DOC_DIR, "nab_hunt.json")
DB_FILE = os.path.join(nab_engine.DOC_DIR, "nab_hunter.db")
OUT_DIR = os.path.join(nab_engine.DOC_DIR, "NAB_Hunter")
SETTINGS = {"telegram": {"token": "", "chat_id": ""}, "brave_key": "", "blocklist": [], "allowlist": [], "feeds": [], "endpoints": {}}
CLIENT_KEYS = ("name", "any", "all", "none", "hours", "sources", "languages", "bd_only", "level", "topic", "brief", "every_minutes", "outputs", "enabled", "ai_check")


def _lines(v):
    if isinstance(v, str):
        v = v.replace(",\n", "\n").split("\n")
    return [x.strip() for x in (v or []) if str(x).strip()]


def _preset_edotco():
    kw = [l.strip() for l in bdfilter.KEYWORDS.splitlines() if l.strip() and not l.startswith("#")]
    return {"name": "Edotco / mobile towers (Bangladesh)", "any": kw, "all": [], "none": [], "hours": 24, "sources": ["gnews"], "languages": ["en", "bn"],
            "bd_only": True, "level": "Balanced", "topic": "tower", "brief": "Edotco Bangladesh and the mobile tower / telecom infrastructure industry in Bangladesh",
            "every_minutes": 0, "outputs": ["txt"], "enabled": True, "ai_check": True}


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.Lock()
        self.job = None            # {"name","log":[...],"done":bool,"result":..}
        self.sched = None
        self.d = self._load()
        self.db = None

    # ------------------------------------------------------------ storage
    def _load(self):
        d = {"settings": json.loads(json.dumps(SETTINGS)), "clients": {}}
        try:
            with open(SET_FILE, encoding="utf-8") as f:
                j = json.load(f)
            d["settings"].update(j.get("settings") or {})
            d["clients"] = j.get("clients") or {}
        except Exception:
            pass
        if not d["clients"]:
            d["clients"]["edotco"] = _preset_edotco()
        return d

    def _save(self):
        try:
            tmp = SET_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=1)
            os.replace(tmp, SET_FILE)
        except Exception as e:
            logging.error(f"hunt save: {e}")

    def store(self):
        if self.db is None:
            os.makedirs(OUT_DIR, exist_ok=True)
            self.db = Store(DB_FILE)
        return self.db

    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="hunt", **kw)

    def _ai(self):
        a = nab_ai.get()
        return a if a.ready() else None

    # ------------------------------------------------------------ api
    def api_state(self, a):
        st = self.store()
        s = json.loads(json.dumps(self.d["settings"]))
        tg = s.get("telegram") or {}
        return {"ok": True, "clients": self.d["clients"], "settings": s, "names": st.names(), "runs": st.last_runs(12), "auto": self.sched is not None,
                "job": self.job and {"name": self.job["name"], "done": self.job["done"]}, "ai": bool(self._ai()), "out": OUT_DIR, "tg": bool(tg.get("token") and tg.get("chat_id"))}

    def api_client_save(self, a):
        cid = a.get("id") or uuid.uuid4().hex[:8]
        c = dict(self.d["clients"].get(cid) or {})
        for k in CLIENT_KEYS:
            if k in a:
                v = a[k]
                if k in ("any", "all", "none"):
                    v = _lines(v)
                elif k in ("hours", "every_minutes"):
                    try:
                        v = float(v)
                    except Exception:
                        v = 24.0 if k == "hours" else 0.0
                elif k in ("bd_only", "enabled", "ai_check"):
                    v = bool(v)
                c[k] = v
        c.setdefault("name", "New client")
        c.setdefault("hours", 24); c.setdefault("sources", ["gnews"]); c.setdefault("languages", ["en", "bn"]); c.setdefault("outputs", ["txt"])
        c.setdefault("bd_only", True); c.setdefault("level", "Balanced"); c.setdefault("topic", "keywords"); c.setdefault("enabled", True)
        self.d["clients"][cid] = c
        self._save()
        return {"ok": True, "id": cid, "client": c}

    def api_client_delete(self, a):
        self.d["clients"].pop(a.get("id"), None)
        self._save()
        return {"ok": True}

    def api_preset(self, a):
        cid = "edotco"
        self.d["clients"][cid] = _preset_edotco()
        self._save()
        return {"ok": True, "id": cid}

    def api_settings(self, a):
        s = self.d["settings"]
        for k in ("brave_key",):
            if k in a:
                s[k] = str(a[k]).strip()
        for k in ("blocklist", "allowlist"):
            if k in a:
                s[k] = [x.lower() for x in _lines(a[k])]
        if "feeds" in a:
            s["feeds"] = [{"name": (l.split("|")[0] if "|" in l else l).strip(), "url": l.split("|")[-1].strip()} for l in _lines(a["feeds"])]
        if "telegram" in a:
            s["telegram"] = {"token": str((a["telegram"] or {}).get("token", "")).strip(), "chat_id": str((a["telegram"] or {}).get("chat_id", "")).strip()}
        self._save()
        return {"ok": True}

    def api_tgtest(self, a):
        n = output.send_telegram(self.d["settings"], "News Hunter test", [[{"title": "Telegram is connected", "link": "https://example.com", "source": "", "domain": "", "published": None}]], lambda m: None)
        return {"ok": bool(n)}

    # ------------------------------------------------------------ jobs
    def _start(self, name, fn):
        with self.lock:
            if self.job and not self.job["done"]:
                return None
            j = self.job = {"name": name, "done": False, "n": 0}
        def log(m):
            self._emit(ev="log", msg=m, at=time.strftime("%H:%M:%S"))
        def run():
            self._emit(ev="begin", name=name)
            res = {}
            try:
                res = fn(log) or {}
            except Exception as e:
                logging.exception("hunt job")
                log(f"Failed: {e}")
            j["done"] = True
            self._emit(ev="done", name=name, **res)
        threading.Thread(target=run, daemon=True).start()
        return j

    def _run_one(self, cid, log, quiet=False):
        c = self.d["clients"].get(cid)
        if not c:
            return {"new": 0}
        return hx.run_search(cid, c, self.d["settings"], self.store(), OUT_DIR, log, ai=self._ai())

    def api_run(self, a):
        ids = [i for i in (a.get("ids") or []) if i in self.d["clients"]]
        if not ids:
            return {"ok": False, "error": "Pick at least one client."}
        def go(log):
            tot = 0
            with_threads = []
            for cid in ids:
                r = self._run_one(cid, log)
                tot += r["new"]
            return {"new": tot, "ids": ids}
        j = self._start("Hunt", go)
        return {"ok": bool(j), "error": None if j else "A hunt is already running."}

    def api_similar(self, a):
        def go(log):
            s = self.d["settings"]
            cfg = {"sources": a.get("sources") or ["gnews", "gdelt"], "languages": a.get("languages") or ["en", "bn"]}
            r = hx.find_similar(a.get("headline", ""), a.get("body", ""), cfg, s, log, float(a.get("hours") or 72))
            log(f"{sum(len(g) for g in r['groups'])} links in {len(r['groups'])} stories")
            return {"groups": self._ser(r["groups"]), "keywords": r.get("keywords", []), "similar": True}
        j = self._start("Find similar", go)
        return {"ok": bool(j), "error": None if j else "A hunt is already running."}

    @staticmethod
    def _ser(groups):
        return [[{"title": i["title"], "link": i["link"], "source": i.get("source") or i.get("domain", ""), "domain": i.get("domain", ""),
                  "published": i["published"].isoformat() if i.get("published") else "", "sim": i.get("sim"), "label": i.get("label", ""),
                  "resolved": i.get("resolved", True), "score": i.get("score")} for i in g] for g in groups]

    def api_results(self, a):
        since = None
        if str(a.get("since")) in ("24", "168", "720"):
            since = (datetime.datetime.now() - datetime.timedelta(hours=int(a["since"]))).isoformat(timespec="seconds")
        rows = self.store().results(a.get("client") or None, since, a.get("text") or None, 1500)
        return {"ok": True, "rows": rows}

    def api_export(self, a):
        rows = self.store().results(a.get("client") or None, None, a.get("text") or None)
        os.makedirs(OUT_DIR, exist_ok=True)
        p = os.path.join(OUT_DIR, f"links_{time.strftime('%Y%m%d_%H%M%S')}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(r["link"] for r in rows) + "\n")
        return {"ok": True, "path": p, "n": len(rows)}

    def api_open(self, a):
        os.makedirs(OUT_DIR, exist_ok=True)
        try:
            os.startfile(OUT_DIR)
        except Exception:
            pass
        return {"ok": True, "path": OUT_DIR}

    def api_to_shots(self, a):
        links = [l for l in (a.get("links") or []) if str(l).startswith("http")]
        if not links:
            return {"ok": False, "error": "No links."}
        import nab_tools
        return nab_tools.get("shot", self.e).api_run({"text": "\n".join(links)})

    def resume_auto(self):
        """Hunter schedules survive a restart: if automatic runs were on, switch them on again."""
        if self.d["settings"].get("auto_on") and not self.sched:
            self.api_auto({"on": True, "_resume": True})

    def api_auto(self, a):
        on = bool(a.get("on"))
        if not a.get("_resume"):
            self.d["settings"]["auto_on"] = on
            self._save()
        if on and not self.sched:
            def one(cid, cfg):
                self._emit(ev="log", msg=f"Scheduled: {cfg.get('name', cid)}", at=time.strftime("%H:%M:%S"))
                r = self._run_one(cid, lambda m: self._emit(ev="log", msg=m, at=time.strftime("%H:%M:%S")))
                self._emit(ev="auto", cid=cid, new=r["new"])
            t = hx.Scheduler(lambda: self.d["clients"], one, self.store(), lambda m: self._emit(ev="log", msg=m, at=time.strftime("%H:%M:%S")))
            t.start(); self.sched = t
        elif not on and self.sched:
            self.sched.stop.set(); self.sched = None
        return {"ok": True, "auto": self.sched is not None}
