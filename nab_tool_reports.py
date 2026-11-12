# nab_tool_reports.py - Reports screen: build a report now, manage templates and scheduled jobs.
import os
import threading

import nab_reports
import nab_schedule


class Tool:
    def __init__(self, engine):
        self.e = engine

    def _arch(self):
        import nab_archive
        return nab_archive.get()

    def api_state(self, a):
        arch = self._arch()
        try:
            f = arch.facets()
        except Exception:
            f = {}
        return {"ok": True, "templates": nab_reports.load_templates(), "papers": f.get("papers", []), "cats": f.get("cats", []), "users": f.get("users", []),
                "jobs": nab_schedule.jobs(), "log": nab_schedule.log_tail(30), "wa_chat": ""}

    def api_run(self, a):
        try:
            r = nab_reports.run_report(self._arch(), a or {}, user=getattr(self.e, "current_user", "") or "")
        except Exception as ex:
            return {"ok": False, "error": str(ex)[:200]}
        if r.get("ok"):
            try:
                import nab_accounts
                nab_accounts.audit("report", f'{r.get("n")} clips -> {os.path.basename(r.get("path", ""))}')
            except Exception:
                pass
        return r

    def api_open(self, a):
        p = a.get("path") or nab_reports.OUT_DIR
        try:
            os.startfile(p)
        except Exception:
            pass
        return {"ok": True}

    def api_template_save(self, a):
        ts = nab_reports.load_templates()
        t = a.get("template") or {}
        name = (t.get("name") or "").strip().lower()
        ts = [x for x in ts if x["name"].lower() != name] + [t]
        return {"ok": True, "templates": nab_reports.save_templates(ts)}

    def api_template_delete(self, a):
        ts = [x for x in nab_reports.load_templates() if x["name"].lower() != (a.get("name") or "").lower()]
        return {"ok": True, "templates": nab_reports.save_templates(ts)}

    def api_job_save(self, a):
        return {"ok": True, "job": nab_schedule.save_job(a.get("job") or {}), "jobs": nab_schedule.jobs()}

    def api_job_delete(self, a):
        nab_schedule.delete_job(a.get("id", ""))
        return {"ok": True, "jobs": nab_schedule.jobs()}

    def api_job_run(self, a):
        r = nab_schedule.get(self.e)
        threading.Thread(target=lambda: (r.run_now(a.get("id", "")), self.e.hub.emit("tool", tool="reports", ev="job_done")), daemon=True).start()
        return {"ok": True}

    def api_daily_now(self, a):
        """Build today's (or the chosen day's) analysis workbook now; upload=True also puts it on the shared Drive."""
        import datetime
        import nab_daily_report
        day = str(a.get("day") or datetime.date.today().isoformat())
        try:
            r = nab_daily_report.build_for_day(self._arch(), day)
            if a.get("upload"):
                try:
                    r["link"] = nab_daily_report.upload_to_drive(r.get("doc") or r["path"])
                except Exception as ex:
                    r["upload_error"] = str(ex)[:140]
            return r
        except Exception as ex:
            return {"ok": False, "error": str(ex)[:200]}
