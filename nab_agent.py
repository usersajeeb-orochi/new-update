# nab_agent.py - Riko as an agent: the model may call a few NAB tools, one step at a time.
#
# Protocol (works with any chat model, no native tool-calling needed): the model answers with ONE JSON object,
#   {"tool": "<name>", "args": {...}}   -> run a tool and show the result back, or
#   {"reply": "<text for the user>"}    -> finish.
# Read tools run at once. Tools that make something (a report) are never run by the model alone:
# they come back as a pending action and run only after the user presses Confirm.
import json
import re
import time
import uuid

MAX_STEPS = 4
PENDING_TTL = 600

READ_TOOLS = {
    "search_archive": 'Search saved clips. args: q (keywords), paper, cat, date_from, date_to (DD-MM-YYYY or YYYY-MM-DD). Returns count and up to 8 clips.',
    "list_filters": "List the papers and categories that exist in the archive. No args.",
    "self_check": "Run the health check (internet, Drive, Telegram, disk, backups...). No args.",
    "phone_queue": "List entries the colleague sent from the phone that are not yet taken. No args.",
    "daily_summary": "Today's numbers and written findings: clips, papers, top category, busiest hour, papers missing. args: day (YYYY-MM-DD, optional).",
    "scheduled_jobs": "List scheduled reports and their last result. No args.",
}
WRITE_TOOLS = {
    "make_report": 'Make a report file. args: range (today, yesterday, this_week, last_week, this_month, last_month), paper, cat, client, template. NEEDS CONFIRMATION.',
}


def _short(r):
    return {k: r.get(k, "") for k in ("name", "paper", "page", "pos", "size", "cat", "date", "user")}


class Agent:
    def __init__(self, engine, ai, brain):
        self.e, self.ai, self.brain = engine, ai, brain
        self.pending = {}

    # ---------------------------------------------------------------- tools
    def _arch(self):
        import nab_archive
        return nab_archive.get()

    def run_tool(self, name, args):
        args = args if isinstance(args, dict) else {}
        if name == "search_archive":
            flt = {k: str(args.get(k) or "").strip() for k in ("paper", "cat", "date_from", "date_to")}
            q = str(args.get("q") or "").strip()
            if not q and not any(flt.values()):
                return {"error": "give a keyword or a filter"}
            r = self._arch().search(q, False, 8, **flt)
            return {"total": r["total"], "more": r["more"], "clips": [_short(x) for x in r["rows"]]}
        if name == "list_filters":
            f = self._arch().facets()
            return {"papers": f.get("papers", [])[:60], "cats": f.get("cats", [])[:60]}
        if name == "self_check":
            import nab_health
            r = nab_health.run_all(self.e)
            return {"overall": r["overall"], "problems": [{"what": x["label"], "status": x["status"], "detail": x.get("detail", "")}
                                                          for x in r["rows"] if x["status"] != "ok"][:10]}
        if name == "phone_queue":
            import nab_tools
            r = nab_tools.get("phone", self.e).api_list({})
            if not r.get("ok"):
                return {"error": r.get("error", "unavailable")}
            return {"waiting": len(r["items"]), "items": [{k: i.get(k, "") for k in ("paper", "page", "position", "size", "cats", "user")} for i in r["items"][:8]]}
        if name == "daily_summary":
            import datetime
            import nab_daily_report as D
            day = str(args.get("day") or datetime.date.today().isoformat())[:10]
            d0 = D._day(day)
            rows = self._arch().search("", False, 50000, date_from=(d0 - datetime.timedelta(days=30)).isoformat(), date_to=day)["rows"]
            A = D.analyse(rows, day)
            return {"day": day, "clips": A["n"], "yesterday": A["n_prev"], "papers": len(A["by_paper"]),
                    "top_papers": sorted(A["by_paper"].items(), key=lambda x: -x[1])[:5], "top_categories": sorted(A["by_cat"].items(), key=lambda x: -x[1])[:5],
                    "findings": A["insights"][:6], "missing_papers": [m[0] for m in A["missing"]][:8]}
        if name == "scheduled_jobs":
            import nab_schedule
            return {"jobs": [{"name": j.get("name"), "time": j.get("time"), "on": j.get("on", True)} for j in nab_schedule.jobs()][:12]}
        return {"error": "unknown tool " + str(name)}

    def do_write(self, name, args):
        if name == "make_report":
            import nab_reports
            p = {k: str(args.get(k) or "") for k in ("range", "paper", "cat", "client", "template")}
            p["range"] = p["range"] or "today"
            r = nab_reports.run_report(self._arch(), p, user=getattr(self.e, "current_user", "") or "")
            if r.get("ok"):
                return {"ok": True, "text": f'Report ready: {r.get("n")} clips. Saved as {r.get("path", "")}', "path": r.get("path", "")}
            return {"ok": False, "text": r.get("error") or "The report could not be made."}
        return {"ok": False, "text": "Unknown action."}

    def confirm(self, pid, yes=True):
        self._gc()
        p = self.pending.pop(str(pid), None)
        if not p:
            return {"ok": False, "error": "That request expired. Ask me again."}
        if not yes:
            return {"ok": True, "reply": "Cancelled. I did not do it."}
        try:
            r = self.do_write(p["tool"], p["args"])
        except Exception as ex:
            return {"ok": False, "error": str(ex)[:160]}
        return {"ok": r["ok"], "reply": r["text"], "path": r.get("path", "")}

    def _gc(self):
        now = time.time()
        for k in [k for k, v in self.pending.items() if now - v["ts"] > PENDING_TTL]:
            self.pending.pop(k, None)

    # ---------------------------------------------------------------- loop
    def prompt(self):
        tl = "\n".join(f"- {k}: {v}" for k, v in {**READ_TOOLS, **WRITE_TOOLS}.items())
        return ("\n\n=== TOOLS ===\nYou can look things up or act by calling ONE tool at a time. Answer with a single JSON object and nothing else:\n"
                '{"tool":"name","args":{...}}  to call a tool, or  {"reply":"text for the user"}  when you can answer.\n'
                "Call a tool only when the user asks for data or an action; for how-to questions just reply. "
                "Never claim you did something unless a tool result says so. Never invent clips or numbers; use tool results only. "
                "A tool that makes a file only asks the user to confirm; tell the user to press Confirm.\n" + tl)

    def parse(self, txt):
        m = re.search(r"\{.*\}", txt or "", re.S)
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
            return j if isinstance(j, dict) else None
        except Exception:
            return None

    def run(self, history, text):
        msgs = [{"role": "system", "content": self.brain.system() + self.prompt()}]
        for h in (history or [])[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("text"):
                msgs.append({"role": h["role"], "content": str(h["text"])[:600]})
        msgs.append({"role": "user", "content": text[:1200]})
        for _ in range(MAX_STEPS):
            out, why = self.ai.chat(msgs, max_tokens=500, temperature=0.2, json_mode=True)
            if out is None:
                return {"ok": False, "error": why, "offline": True}
            j = self.parse(out)
            if not j:                       # model ignored the format: treat as plain reply
                return {"ok": True, "reply": re.sub(r"\s+", " ", out).strip()[:900]}
            if j.get("reply") is not None and not j.get("tool"):
                return {"ok": True, "reply": str(j["reply"]).strip()}
            name, args = str(j.get("tool") or ""), j.get("args") or {}
            if name in WRITE_TOOLS:
                self._gc()
                pid = uuid.uuid4().hex[:8]
                self.pending[pid] = {"tool": name, "args": args if isinstance(args, dict) else {}, "ts": time.time()}
                desc = ", ".join(f"{k}: {v}" for k, v in (args if isinstance(args, dict) else {}).items() if v) or "default settings"
                return {"ok": True, "reply": f"I can make this report ({desc}). Press Confirm to go ahead.", "confirm": {"id": pid, "label": "Make report", "detail": desc}}
            if name not in READ_TOOLS:
                msgs.append({"role": "assistant", "content": out})
                msgs.append({"role": "user", "content": "TOOL ERROR: no such tool. Reply with a JSON object."})
                continue
            try:
                res = self.run_tool(name, args)
            except Exception as ex:
                res = {"error": str(ex)[:120]}
            msgs.append({"role": "assistant", "content": out})
            msgs.append({"role": "user", "content": "TOOL RESULT (" + name + "): " + json.dumps(res, ensure_ascii=False)[:2500] +
                         "\nNow answer the user with a JSON reply, or call one more tool if needed."})
        return {"ok": True, "reply": "I could not finish that. Try asking in a simpler way."}
