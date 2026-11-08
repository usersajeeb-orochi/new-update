# nab_mail_host.py — engine side of "Send by mail" (settings, prepare files, send, log).  Logic lives in nab_mailer.py.
import os, time, logging, threading, datetime
import nab_mailer as M


class MailMixin:
    _mail_busy = False
    _mail_plans = None

    def _mstore(self):
        return M.Store(os.path.dirname(self.settings_file))

    def _mail_date_s(self, cfg):
        try:
            return self.current_date.strftime(cfg["text"].get("date_format") or "%d-%m-%Y")
        except Exception:
            return self.current_date.strftime("%d-%m-%Y")

    def mail_load(self):
        st = self._mstore()
        cfg = st.load()
        day = self._dest_folder([])
        return {"ok": True, "cfg": cfg, "has_password": st.has_password(), "date": self._mail_date_s(cfg),
                "day_folder": day, "day_exists": os.path.isdir(day), "folders": M.day_categories(day),
                "log": st.log()[-60:][::-1], "busy": self._mail_busy, "authorized": self.authorized}

    def mail_items(self):
        try:
            d = M.list_items(self._dest_folder([]))
            return {"ok": True, "cats": d["cats"], "pdfs": d["pdfs"]}
        except Exception as e:
            logging.error(f"mail_items: {e}")
            return {"ok": False, "error": str(e), "cats": [], "pdfs": []}

    def mail_defaults(self):
        return {"ok": True, "groups": M.default_config()["groups"]}

    def mail_save(self, cfg):
        if not self.authorized:
            return {"ok": False, "error": "Sign in first."}
        try:
            clean = self._mstore().save(cfg)
            return {"ok": True, "cfg": clean}
        except Exception as e:
            logging.error(f"mail_save: {e}")
            return {"ok": False, "error": str(e)}

    def mail_password(self, pw):
        if not self.authorized:
            return {"ok": False, "error": "Sign in first."}
        self._mstore().set_password(pw or "")
        return {"ok": True, "has_password": self._mstore().has_password()}

    def mail_test_conn(self, cfg=None):
        st = self._mstore()
        c = M.clean_config(cfg) if cfg else st.load()
        return M.test_connection(c, st.get_password())

    # ---------- prepare ----------
    def mail_prepare(self, make_pdfs=False, ids=None):
        if not self.authorized:
            return {"ok": False, "error": "Sign in first."}
        if self._mail_busy:
            return {"ok": False, "error": "Busy. Wait for the current job."}
        self._mail_busy = True
        threading.Thread(target=self._mail_prepare_run, args=(bool(make_pdfs), ids), daemon=True, name="NAB-MailPrep").start()
        return {"ok": True}

    def _mail_prepare_run(self, make_pdfs, ids):
        try:
            cfg = self._mstore().load()
            day, date_s = self._dest_folder([]), self._mail_date_s(cfg)
            plans = {}
            self.hub.emit("mail_plan", stage="start")
            for g in cfg["groups"]:
                if not g["enabled"] or (ids and g["id"] not in ids):
                    continue
                self.hub.emit("mail_plan", stage="work", id=g["id"], name=g["name"])
                p = M.plan_group(g, cfg, day, date_s, make_pdfs=make_pdfs, logger=lambda m: self.hub.emit("mail_plan", stage="log", msg=m))
                plans[g["id"]] = p
                try:
                    p["hints"] = M.hints(g, p, self._mstore().log())
                except Exception as e:
                    logging.error(f"mail hints: {e}")
                    p["hints"] = []
                self.hub.emit("mail_plan", stage="group", plan={k: v for k, v in p.items() if k != "files"} | {"names": [os.path.basename(f) for f in p["files"]]})
            self._mail_plans = plans
            self.hub.emit("mail_plan", stage="done")
        except Exception as e:
            logging.error(f"mail prepare: {e}")
            self.hub.emit("mail_plan", stage="error", error=str(e))
        finally:
            self._mail_busy = False

    # ---------- send ----------
    def mail_send(self, ids=None, test=False):
        if not self.authorized:
            return {"ok": False, "error": "Sign in first."}
        if self._mail_busy:
            return {"ok": False, "error": "Busy. Wait for the current job."}
        st = self._mstore()
        cfg = st.load()
        errs = M.validate(cfg)
        if not st.has_password() and cfg["account"].get("kind") == "gmail":
            errs.append("Mail password / app password is not set.")
        if errs:
            return {"ok": False, "error": errs[0], "errors": errs}
        self._mail_busy = True
        threading.Thread(target=self._mail_send_run, args=(cfg, st, ids, bool(test)), daemon=True, name="NAB-MailSend").start()
        return {"ok": True}

    def _mail_drive_link(self, path):
        from googleapiclient.http import MediaFileUpload
        svc = self._get_gdrive_service()
        if not svc:
            raise RuntimeError("Drive not available")
        import nab_connections
        root = nab_connections.drive_folder_id()
        folder = self._drive_get_or_create_folder(svc, root, "Mail")
        sub = self._drive_get_or_create_folder(svc, folder, self.current_date.strftime("%d-%m-%Y")) if folder else None
        if not sub:
            raise RuntimeError("Drive folder not available")
        f = svc.files().create(body={"name": os.path.basename(path), "parents": [sub]}, media_body=MediaFileUpload(path, resumable=True),
                               fields="id,webViewLink", supportsAllDrives=True).execute()
        svc.permissions().create(fileId=f["id"], body={"type": "anyone", "role": "reader"}, supportsAllDrives=True).execute()
        return f.get("webViewLink") or ("https://drive.google.com/file/d/%s/view" % f["id"])

    def _mail_send_run(self, cfg, st, ids, test):
        pw = st.get_password()
        day, date_s = self._dest_folder([]), self._mail_date_s(cfg)
        today_key = self.current_date.strftime("%Y-%m-%d")
        sent_ok = set(e.get("group") for e in st.log() if e.get("day") == today_key and e.get("ok") and not e.get("test"))
        items = [g for g in cfg["groups"] if g["enabled"] and (not ids or g["id"] in ids)]
        status = {g["id"]: {"id": g["id"], "name": g["name"], "st": "wait", "msg": ""} for g in items}
        emit = lambda **k: self.hub.emit("mail_progress", items=list(status.values()), **k)
        emit(stage="start")
        n_ok = n_fail = 0
        try:
            for i, g in enumerate(items):
                s = status[g["id"]]
                if cfg["behaviour"].get("skip_sent") and not test and g["name"] in sent_ok:
                    s.update(st="skip", msg="Already sent today")
                    emit(stage="item")
                    continue
                s.update(st="run", msg="Preparing…")
                emit(stage="item")
                plan = (self._mail_plans or {}).get(g["id"])
                if not plan or any(not os.path.exists(f) for f in plan.get("files", [])):
                    plan = M.plan_group(g, cfg, day, date_s)
                if plan["status"] != "ready" and not g["send_empty"]:
                    s.update(st="skip", msg=plan.get("note") or "No files")
                    emit(stage="item")
                    continue
                s["msg"] = "Sending…"
                emit(stage="item")
                res = M.send_group(cfg, pw, g, plan, date_s, test_to=(cfg["account"]["email"] if test else None),
                                   drive_link=self._mail_drive_link,
                                   on_msg=lambda a, b, s=s: (s.update(msg=f"Sending part {a} of {b}…" if b > 1 else "Sending…"), emit(stage="item")))
                if res["ok"]:
                    n_ok += 1
                    s.update(st="ok", msg="Sent" + (f" ({res['total']} parts)" if res.get("total", 1) > 1 else ""))
                else:
                    n_fail += 1
                    s.update(st="fail", msg=res.get("error", "Failed")[:160])
                st.add_log({"t": int(time.time()), "day": today_key, "date": date_s, "group": g["name"], "ok": res["ok"], "test": test,
                            "parts": res.get("total", 1), "error": "" if res["ok"] else res.get("error", ""), "to": len(g["to"]) + len(g["cc"]), **M.log_facts(plan)})
                emit(stage="item")
                if i < len(items) - 1 and cfg["behaviour"]["wait_s"]:
                    time.sleep(cfg["behaviour"]["wait_s"])
            emit(stage="done", ok=n_ok, fail=n_fail, test=test)
            if cfg["behaviour"].get("telegram") and not test:
                try:
                    from nab_telegram import _tg_send, PC_NAME
                    _tg_send(f"📧 <b>Mail sent</b> from {PC_NAME}: {n_ok} group(s) OK, {n_fail} failed ({date_s}).")
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"mail send: {e}")
            emit(stage="error", error=str(e))
        finally:
            self._mail_busy = False
