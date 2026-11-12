# nab_schedule.py - runs saved jobs at fixed times (reports, self-check alerts) and hands the results out:
# folder, Telegram, WhatsApp, e-mail.  Jobs live in Documents\nab_schedule.json.  A job that was missed because NAB was closed runs when NAB
# opens again if it is still inside its catch-up window; older misses are skipped and written to the log, never silently run at a strange hour.
import os
import re
import json
import time
import uuid
import logging
import threading
import datetime

DOC = os.path.join(os.path.expanduser("~"), "Documents")
FILE = os.path.join(DOC, "nab_schedule.json")
LOG = os.path.join(DOC, "nab_schedule_log.jsonl")
KINDS = ("report", "selfcheck", "daily")
DELIVER = ("folder", "telegram", "whatsapp", "mail", "drive")
_lock = threading.RLock()


def _read():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("jobs"), list):
            return d["jobs"]
    except Exception:
        pass
    return []


def _write(jobs):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "jobs": jobs}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, FILE)


def clean_job(j):
    o = {"id": re.sub(r"[^\w-]", "", str(j.get("id") or "")) or uuid.uuid4().hex[:8],
         "name": re.sub(r"\s+", " ", str(j.get("name") or "")).strip()[:60] or "Job",
         "kind": j.get("kind") if j.get("kind") in KINDS else "report", "enabled": bool(j.get("enabled", True))}
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(j.get("time") or "09:00").strip())
    h, mi = (int(m.group(1)), int(m.group(2))) if m else (9, 0)
    o["time"] = f"{min(h, 23):02d}:{min(mi, 59):02d}"
    o["days"] = sorted({int(d) for d in (j.get("days") or []) if str(d).isdigit() and 0 <= int(d) <= 6}) or [0, 1, 2, 3, 4, 5, 6]     # 0 = Monday
    o["catchup_h"] = max(0, min(23, int(j.get("catchup_h") or 6)))
    p = j.get("params") or {}
    o["params"] = {k: str(p.get(k) or "")[:120] for k in ("template", "cat", "paper", "range", "date_from", "date_to", "user", "client")}
    o["params"]["range"] = o["params"]["range"] or ("today" if o["kind"] == "daily" else "yesterday")
    o["deliver"] = [d for d in (j.get("deliver") or ["folder"]) if d in DELIVER] or ["folder"]
    o["chat"] = str(j.get("chat") or "")[:120]            # WhatsApp chat or group
    o["tg_chat"] = str(j.get("tg_chat") or "")[:60]       # empty = the NAB group
    o["mail_to"] = [x.strip() for x in str(j.get("mail_to") or "").replace(";", ",").split(",") if "@" in x][:10]
    o["last_day"] = str(j.get("last_day") or "")
    o["last_result"] = str(j.get("last_result") or "")[:200]
    return o


def jobs():
    return [clean_job(j) for j in _read()]


def save_job(j):
    with _lock:
        cur, c = _read(), clean_job(j)
        for i, x in enumerate(cur):
            if x.get("id") == c["id"]:
                c["last_day"], c["last_result"] = x.get("last_day", ""), x.get("last_result", "")
                cur[i] = c
                break
        else:
            cur.append(c)
        _write(cur)
    return c


def delete_job(jid):
    with _lock:
        _write([x for x in _read() if x.get("id") != jid])


def log(msg, **kw):
    try:
        os.makedirs(DOC, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "msg": msg, **kw}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_tail(n=60):
    try:
        with open(LOG, encoding="utf-8") as f:
            return [json.loads(x) for x in f.readlines()[-n:]][::-1]
    except Exception:
        return []


def due(job, now=None):
    """'run' | 'skip' | '' for one job at 'now'."""
    now = now or datetime.datetime.now()
    if not job["enabled"] or now.weekday() not in job["days"]:
        return ""
    key = now.strftime("%Y-%m-%d")
    if job["last_day"] == key:
        return ""
    h, m = map(int, job["time"].split(":"))
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if now < at:
        return ""
    return "run" if (now - at).total_seconds() <= job["catchup_h"] * 3600 + 120 else "skip"


class Runner:
    """Executes jobs. 'deliver' functions are injected so this file has no hard dependency on the UI engine."""

    def __init__(self, engine):
        self.e = engine
        self.stop = threading.Event()
        self.busy = False

    # -- delivery --
    def _tg_files(self, paths, caption, chat):
        import nab_telegram
        for p in paths:
            with open(p, "rb") as f:
                nab_telegram._tg_send_document(f.read(), os.path.basename(p), caption, chat or None)
            caption = ""

    def _wa(self, paths, chat, caption):
        import nab_tools
        r = nab_tools.get("wa", self.e).api_send({"paths": paths, "chat": chat, "caption": caption})
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "WhatsApp failed")

    def _mail(self, paths, to, subject, body):
        import smtplib
        import mimetypes
        from email.message import EmailMessage
        import nab_mailer as M
        st = self.e._mstore()
        cfg = st.load()
        msg = EmailMessage()
        msg["Subject"], msg["To"] = subject, ", ".join(to)
        msg["From"] = f'{cfg["account"].get("name") or "NAB"} <{cfg["account"]["email"]}>'
        msg.set_content(body)
        for p in paths:
            ct = mimetypes.guess_type(p)[0] or "application/octet-stream"
            with open(p, "rb") as f:
                msg.add_attachment(f.read(), maintype=ct.split("/")[0], subtype=ct.split("/")[1], filename=os.path.basename(p))
        s = M._connect(cfg, st.get_password())
        try:
            s.send_message(msg, from_addr=cfg["account"]["email"], to_addrs=to)
        finally:
            try:
                s.quit()
            except Exception:
                pass

    def deliver(self, job, paths, title):
        done, errs = [], []
        for d in job["deliver"]:
            try:
                if d == "folder":
                    done.append("folder")
                elif d == "drive":
                    import nab_daily_report
                    ups = [x for x in paths if x.lower().endswith(".docx")] or [x for x in paths if x.lower().endswith(".xlsx")]
                    for pth in ups:
                        nab_daily_report.upload_to_drive(pth)
                    done.append("Google Drive")
                elif d == "telegram":
                    self._tg_files(paths, title, job["tg_chat"]); done.append("Telegram")
                elif d == "whatsapp":
                    if not job["chat"]:
                        raise RuntimeError("no WhatsApp chat chosen")
                    self._wa(paths, job["chat"], title); done.append("WhatsApp")
                elif d == "mail":
                    if not job["mail_to"]:
                        raise RuntimeError("no e-mail address")
                    self._mail(paths, job["mail_to"], title, title + "\n\nSent by NAB."); done.append("mail")
            except Exception as ex:
                errs.append(f"{d}: {str(ex)[:80]}")
        return done, errs

    # -- one job --
    def run_job(self, job):
        if job["kind"] == "selfcheck":
            import nab_health
            res = nab_health.run_all(self.e)
            bad = [r for r in res.get("rows", []) if r.get("status") == nab_health.BAD]
            if bad:
                import nab_telegram
                nab_telegram._tg_send("NAB self-check found problems:\n" + "\n".join("- " + str(b.get("label") or b.get("id")) + ": " + str(b.get("detail") or b.get("msg") or "") for b in bad)[:3500], job["tg_chat"] or None)
            return {"ok": True, "msg": f"{len(bad)} problem(s)"}
        import nab_archive
        import nab_reports
        if job["kind"] == "daily":
            import nab_daily_report
            d1, _d2 = nab_reports.resolve_range(job["params"].get("range") or "today")
            r = nab_daily_report.build_for_day(nab_archive.get(), d1, client=job["params"].get("client", ""))
            paths = [r["path"]] + ([r["doc"]] if r.get("doc") else [])
            title = f'{job["name"]}: {r.get("n", 0)} clips on {d1}'
            done, errs = self.deliver(job, paths, title)
            return {"ok": not errs, "msg": title + (" | sent: " + ", ".join(done) if done else "") + ((" | failed: " + "; ".join(errs)) if errs else ""), "path": r["path"]}
        r = nab_reports.run_report(nab_archive.get(), job["params"], user="schedule")
        if not r.get("ok"):
            return {"ok": False, "msg": r.get("error") or "Report failed"}
        paths = [p for p in (r.get("path"), r.get("xlsx")) if p and os.path.isfile(p)]
        title = f'{job["name"]}: {r.get("n", 0)} clips'
        done, errs = self.deliver(job, paths, title)
        return {"ok": not errs, "msg": title + (" | sent: " + ", ".join(done) if done else "") + ((" | failed: " + "; ".join(errs)) if errs else ""), "path": r.get("path")}

    def run_now(self, jid, mark=False):
        job = next((j for j in jobs() if j["id"] == jid), None)
        if not job:
            return {"ok": False, "msg": "Job not found"}
        try:
            res = self.run_job(job)
        except Exception as ex:
            logging.exception("schedule job")
            res = {"ok": False, "msg": str(ex)[:150]}
        log(job["name"], ok=res["ok"], result=res["msg"])
        if mark:
            with _lock:
                cur = _read()
                for x in cur:
                    if x.get("id") == jid:
                        x["last_day"], x["last_result"] = time.strftime("%Y-%m-%d"), ("OK: " if res["ok"] else "Problem: ") + res["msg"]
                _write(cur)
        if not res["ok"]:
            try:
                import nab_telegram
                nab_telegram._tg_send(f'NAB scheduled job "{job["name"]}" had a problem: {res["msg"]}')
            except Exception:
                pass
        return res

    def tick(self):
        if self.busy:
            return
        self.busy = True
        try:
            now = datetime.datetime.now()
            for j in jobs():
                d = due(j, now)
                if d == "run":
                    self.run_now(j["id"], mark=True)
                elif d == "skip":
                    with _lock:
                        cur = _read()
                        for x in cur:
                            if x.get("id") == j["id"]:
                                x["last_day"], x["last_result"] = now.strftime("%Y-%m-%d"), "Skipped: NAB was closed at the scheduled time"
                        _write(cur)
                    log(j["name"], ok=False, result="skipped, NAB was closed at the scheduled time")
        finally:
            self.busy = False

    def loop(self):
        self.stop.wait(45)                    # let NAB finish starting
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                logging.exception("schedule tick")
            self.stop.wait(30)


_runner = None


def ensure_daily_job():
    """The daily Excel analysis (saved here and uploaded to the shared Drive) exists from the start; the owner can change or switch it off."""
    if not any(j.get("kind") == "daily" for j in jobs()):
        save_job({"name": "Daily news analysis", "kind": "daily", "time": "23:30", "catchup_h": 8,
                  "params": {"range": "today"}, "deliver": ["folder", "drive"]})


def start(engine):
    global _runner
    if _runner:
        return _runner
    try:
        ensure_daily_job()
    except Exception:
        logging.exception("daily job")
    _runner = Runner(engine)
    threading.Thread(target=_runner.loop, daemon=True, name="NAB-Schedule").start()
    return _runner


def get(engine=None):
    return _runner or (Runner(engine) if engine else None)
