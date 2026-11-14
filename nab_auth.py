# nab_auth.py — TelegramAuth class
import os
import sys
import json
import time
import shutil
import logging
import datetime
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})
from nab_telegram import *
import nab_telegram as _nab_telegram_mod
globals().update({k: v for k, v in vars(_nab_telegram_mod).items() if not k.startswith('__')})
from nab_update import *
import nab_update as _nab_update_mod
globals().update({k: v for k, v in vars(_nab_update_mod).items() if not k.startswith('__')})
from nab_access import *
import nab_access as _nab_access_mod
globals().update({k: v for k, v in vars(_nab_access_mod).items() if not k.startswith('__')})

class TelegramAuth:
    _session_start   = None
    _access_deadline = None
    _app_ref         = None
    _paused          = False
    _last_update_id  = None   # shared across auth + background listener

    # ─────────────────────────────────────────────────────────────────────
    # AUTH — local bot polls getUpdates directly (no cloud involvement)
    # The cloud bot uses a DIFFERENT token so there is ZERO 409 conflict.
    # ─────────────────────────────────────────────────────────────────────

    _sync_decisions = {}        # request id -> True / False (filled by the background listener)

    @staticmethod
    def request_sync_approval(summary, timeout=180):
        """Ask the admin on Telegram to approve UPLOADING settings changes to the shared
        Drive file. Returns True / False. Downloading never needs this."""
        import nab_remote
        rid = "s" + str(int(time.time() * 1000))[-9:]
        relay = nab_remote.available()
        TelegramAuth._sync_decisions.pop(rid, None)
        text = (f"🔄 <b>NAB settings sync — upload request</b>\n\n💻 PC: <code>{PC_NAME}</code>\n"
                f"📝 {summary}\n\n⏳ Auto-denied in {timeout}s.")
        yes, no = ((f"nabS|{rid}|ok", f"nabS|{rid}|no") if relay else (f"nab_sync_ok_{rid}", f"nab_sync_no_{rid}"))
        mid = _tg_send_callback_buttons(text, buttons=[("✅ Allow upload", yes), ("⛔ Deny", no)], chat_id=TG_CHAT_ID)
        if not mid:
            return None            # could not reach Telegram — caller retries later
        end = time.time() + timeout
        while time.time() < end:
            d = TelegramAuth._sync_decisions.pop(rid, None)
            if d is None and relay:
                r = nab_remote.get_decision(rid, PC_NAME)
                if r:
                    d = (r[0] == "ok")
            if d is not None:
                _tg_edit_message(TG_CHAT_ID, mid, text.split("\n\n⏳")[0] + ("\n\n✅ <b>Allowed</b>" if d else "\n\n⛔ <b>Denied</b>"))
                return d
            time.sleep(2 if relay else 1)
        _tg_edit_message(TG_CHAT_ID, mid, text.split("\n\n⏳")[0] + "\n\n⏰ <b>Timed out</b> — not uploaded")
        return False

    @staticmethod
    def request_access(mode="group", reason="", remember_until=None, remember_long=None):
        TelegramAuth._remember_until = None
        try:
            import getpass
            user = getpass.getuser()
        except Exception:
            user = "Unknown"

        now = datetime.datetime.now()

        # ── Blocked PC check ──
        blocked = _load_blocked_pcs()
        if PC_NAME in blocked:
            _tg_send(
                f"🚫 <b>Blocked PC attempted login</b>\n\n"
                f"💻 PC: <code>{PC_NAME}</code>\n"
                f"👤 User: <code>{user}</code>\n"
                f"🕐 Time: {now.strftime('%H:%M:%S')}\n\n"
                f"This PC was previously blocked.\n"
                f"Send /unblock {PC_NAME} to allow."
            )
            shot = _take_screenshot()
            if shot:
                _tg_send_photo(shot, f"Blocked PC attempt — {PC_NAME}")
            _log_access_attempt(PC_NAME, user, "blocked")
            return False

        # ── Allowed hours check ──
        if ALLOWED_HOURS is not None:
            start_h, end_h = ALLOWED_HOURS
            if not (start_h <= now.hour < end_h):
                _tg_send(
                    f"⏰ <b>Outside-hours login blocked</b>\n\n"
                    f"💻 PC: <code>{PC_NAME}</code>\n"
                    f"👤 User: <code>{user}</code>\n"
                    f"🕐 Time: {now.strftime('%H:%M:%S')}\n"
                    f"📅 Allowed: {start_h:02d}:00 – {end_h:02d}:00\n\nAuto-denied."
                )
                shot = _take_screenshot()
                if shot:
                    _tg_send_photo(shot, f"Screen at denied login — {PC_NAME}")
                _log_access_attempt(PC_NAME, user, "outside_hours")
                return False

        # ── With a cloud bot the cloud reads the button taps (one reader per token); without it this PC reads them itself ──
        import nab_remote, uuid as _uuid
        relay = nab_remote.available()
        rid = _uuid.uuid4().hex[:8]
        if not relay:
            _tg_drain_queue()
        TelegramAuth._last_update_id = None
        _cb = (lambda act: f"nabA|{rid}|{act}") if relay else (lambda act: f"nab_{act}_{PC_NAME}")

        # ── Targets: the request buttons go to the GROUP only. Everything
        # else in this function (confirmations, screenshots, blocked-PC
        # alerts, timeout notices) still goes to TG_CHAT_ID by default —
        # unaffected, since those _tg_send()/_tg_send_photo() calls below
        # don't reference `targets` at all.
        owner_only = (mode == "owner")
        targets = [TG_CHAT_ID] if (owner_only or not TG_GROUP_CHAT_ID) else [TG_GROUP_CHAT_ID]
        import html as _html
        reason = _html.escape((reason or "").strip()[:140])

        request_text = (
            f"🔐 <b>NAB Login Request</b>" + (" — <i>owner only</i>" if owner_only else "") + "\n\n"
            f"💻 PC: <code>{PC_NAME}</code>\n"
            f"👤 User: <code>{user}</code>\n"
            f"🕐 Time: {now.strftime('%H:%M:%S')}\n"
            + (f"📝 Reason: <i>{reason}</i>\n" if reason else "") + "\n"
            f"Tap a button below.\n"
            f"⏳ Auto-denied in {AUTH_TIMEOUT}s."
        )
        # Track (chat_id, message_id) for each sent request so we can edit
        # them in place once someone responds — whichever chat responds
        # first "wins" and the request is cleared from all of them.
        sent_msgs = {}
        for cid in targets:
            mid = _tg_send_callback_buttons(
                request_text,
                buttons=([
                    ("Allow",   _cb("allow")),
                    ("2 Hours", _cb("allow2")),
                    ("Remember today", _cb("today")),
                    ("Remember for days", _cb("week")),
                    ("Deny",    _cb("deny")),
                ] if owner_only else [
                    ("Allow",   _cb("allow")),
                    ("2 Hours", _cb("allow2")),
                    ("Remember today", _cb("today")),
                    ("Deny",    _cb("deny")),
                ]),
                chat_id=cid,
            )
            if mid:
                sent_msgs[cid] = mid

        def _clear_request_buttons(outcome_line):
            for cid, mid in sent_msgs.items():
                _tg_edit_message(cid, mid, request_text.split("\n\nTap")[0] + f"\n\n{outcome_line}")

        # ── Poll for response ──
        deadline       = time.time() + AUTH_TIMEOUT
        last_update_id = None

        while time.time() < deadline:
            remaining    = int(deadline - time.time())
            poll_timeout = min(remaining, 5)
            if poll_timeout <= 0:
                break
            events = []                                   # (text, responder)
            if relay:
                time.sleep(min(2, max(poll_timeout, 0)))
                d = nab_remote.get_decision(rid, PC_NAME)
                if d:
                    act, responder = d
                    text = {"allow": "allow", "allow2": "allow 2", "today": "today", "week": "week", "deny": "deny"}.get(act)
                    if text == "week" and not owner_only:
                        text = None
                    if text:
                        events.append((text, responder))
            else:
                data = _tg_get_updates(offset=last_update_id, timeout=poll_timeout)
                for update in data.get("result", []):
                    last_update_id = update["update_id"] + 1
                    TelegramAuth._last_update_id = last_update_id
                    cb = update.get("callback_query")
                    if cb:
                        cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                        if cb_chat_id not in targets:
                            continue
                        data_str  = cb.get("data", "")
                        responder = (cb.get("from", {}).get("first_name")
                                     or cb.get("from", {}).get("username") or "Someone")
                        _tg_answer_callback_query(cb["id"], text="Got it!")
                        if data_str == f"nab_deny_{PC_NAME}":
                            text = "deny"
                        elif data_str == f"nab_allow2_{PC_NAME}":
                            text = "allow 2"
                        elif data_str == f"nab_allow_{PC_NAME}":
                            text = "allow"
                        elif data_str == f"nab_today_{PC_NAME}":
                            text = "today"
                        elif data_str == f"nab_week_{PC_NAME}" and owner_only:
                            text = "week"
                        else:
                            continue
                    else:
                        # Plain-text fallback only from the admin's own DM, never from the group.
                        msg     = update.get("message", {})
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        text    = msg.get("text", "").strip().lower()
                        if chat_id != TG_CHAT_ID:
                            continue
                        responder = "Admin"
                    events.append((text, responder))
            for text, responder in events:
                if text == "deny":
                    _clear_request_buttons(f"⛔ <b>Denied</b> by {responder}")
                    _tg_send(f"⛔ Access <b>DENIED</b> to <code>{PC_NAME}</code>.")
                    shot = _take_screenshot()
                    if shot:
                        _tg_send_photo(shot, f"Screen at denied login — {PC_NAME}")
                    _log_access_attempt(PC_NAME, user, "denied")
                    denied_count = _get_denied_count(PC_NAME)
                    if denied_count >= 10:
                        blocked          = _load_blocked_pcs()
                        blocked[PC_NAME] = {
                            "user":       user,
                            "blocked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "deny_count": denied_count
                        }
                        _save_blocked_pcs(blocked)
                        _tg_send(
                            f"🔴 <b>PC AUTO-BLOCKED after 10 denials!</b>\n\n"
                            f"💻 PC: <code>{PC_NAME}</code>\n"
                            f"Send /unblock {PC_NAME} to allow again."
                        )
                        shot = _take_screenshot()
                        if shot:
                            _tg_send_photo(shot, f"Auto-blocked — {PC_NAME}")
                    return False

                elif text == "week" and remember_long:
                    TelegramAuth._remember_until = remember_long
                    until_s = datetime.datetime.fromtimestamp(remember_long).strftime("%d %b %H:%M")
                    _clear_request_buttons(f"✅ <b>Remembered</b> (until {until_s}) by {responder}")
                    _tg_send(f"✅ Access <b>GRANTED</b> to <code>{PC_NAME}</code> until <b>{until_s}</b> — it will not ask again before then.")
                    TelegramAuth._session_start   = time.time()
                    TelegramAuth._access_deadline = None
                    _log_access_attempt(PC_NAME, user, "granted_days")
                    return True

                elif text == "today" or text == "allow today":
                    TelegramAuth._remember_until = remember_until
                    until_s = datetime.datetime.fromtimestamp(remember_until).strftime("%H:%M") if remember_until else "?"
                    _clear_request_buttons(f"✅ <b>Approved for today</b> (until {until_s}) by {responder}")
                    _tg_send(f"✅ Access <b>GRANTED</b> to <code>{PC_NAME}</code> until <b>{until_s}</b> — it will not ask again before then.")
                    TelegramAuth._session_start   = time.time()
                    TelegramAuth._access_deadline = None
                    _log_access_attempt(PC_NAME, user, "granted_today")
                    return True

                elif text == "allow":
                    _clear_request_buttons(f"✅ <b>Approved (unlimited)</b> by {responder}")
                    _tg_send(f"✅ Access <b>GRANTED</b> to <code>{PC_NAME}</code> — unlimited.")
                    TelegramAuth._session_start   = time.time()
                    TelegramAuth._access_deadline = None
                    _log_access_attempt(PC_NAME, user, "granted_unlimited")
                    return True

                elif text.startswith("allow"):
                    try:
                        hours = float(text.split()[1])
                    except (ValueError, IndexError):
                        hours = 2.0
                    TelegramAuth._session_start   = time.time()
                    TelegramAuth._access_deadline = time.time() + hours * 3600
                    exp_str = datetime.datetime.fromtimestamp(
                        TelegramAuth._access_deadline).strftime("%H:%M:%S")
                    _clear_request_buttons(f"✅ <b>Approved ({hours}h)</b> by {responder}")
                    _tg_send(
                        f"✅ Access <b>GRANTED</b> to <code>{PC_NAME}</code>\n"
                        f"⏱ Expires at <b>{exp_str}</b> ({hours}h)"
                    )
                    _log_access_attempt(PC_NAME, user, f"granted_{hours}h")
                    return True

        # Timeout
        _clear_request_buttons("⏰ <b>Timed out</b> — auto-denied")
        _tg_send(f"⏰ Login from <code>{PC_NAME}</code> timed out — auto denied.")
        shot = _take_screenshot()
        if shot:
            _tg_send_photo(shot, f"Screen at timeout — {PC_NAME}")
        _log_access_attempt(PC_NAME, user, "timeout")
        return False

    # ─────────────────────────────────────────────────────────────────────
    # BACKGROUND LISTENER
    # Local bot: polls getUpdates for auth/control commands
    # Cloud bot: receives heartbeat POSTs, queues file/upload commands
    # Both run in the SAME background thread, interleaved every 10s
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def run_background_listener(app):
        TelegramAuth._app_ref  = app
        last_update_id         = TelegramAuth._last_update_id  # carry over from auth
        last_heartbeat_time    = 0
        try:                                       # drop commands sent while NAB was closed (an old /restart must not run again)
            _old = _tg_get_updates(offset=-1, timeout=0).get("result", [])
            if _old:
                last_update_id = _old[-1]["update_id"] + 1
                _tg_get_updates(offset=last_update_id, timeout=0)
        except Exception as _e:
            logging.error(f"flush old updates: {_e}")

        def _handle_local_command(text, msg):
            """Handle commands coming from the LOCAL NAB bot (auth/control only)."""
            tl = text.strip().lower()

            # ── /start deep links from auth buttons (already handled in auth, ignore here) ──
            if tl.startswith("/start"):
                return False

            # ── PAUSE / RESUME ──
            if tl in ["/pause", f"/pause {PC_NAME.lower()}"]:
                TelegramAuth._paused = True
                app.after(0, lambda: app._on_pause())
                _tg_send(f"⏸ NAB paused on <b>{PC_NAME}</b>.")

            elif tl in ["/resume", f"/resume {PC_NAME.lower()}"]:
                TelegramAuth._paused = False
                app.after(0, lambda: app._on_resume())
                _tg_send(f"▶️ NAB resumed on <b>{PC_NAME}</b>.")

            # ── LOCK / CLOSE ──
            elif tl in ["deny", "/close", f"/close {PC_NAME.lower()}"]:
                _tg_send(f"🔒 NAB closed remotely on <b>{PC_NAME}</b>.")
                app.after(0, lambda: [app.save_settings(), app.destroy(), sys.exit(0)])
                return True  # exit loop

            # ── SCREENSHOT ──
            elif tl in ["/screenshot", f"/screenshot {PC_NAME.lower()}"]:
                _tg_send(f"📸 Taking screenshot on <b>{PC_NAME}</b>...")
                shot = _take_screenshot()
                if shot:
                    _tg_send_photo(shot, f"NAB — {PC_NAME} — {datetime.datetime.now().strftime('%H:%M:%S')}")
                else:
                    _tg_send("❌ Screenshot failed.")

            # ── RESTART ──
            elif tl in ["/restart", f"/restart {PC_NAME.lower()}"]:
                _tg_send(f"🔄 Restarting NAB on <b>{PC_NAME}</b>...")
                try:                                   # mark /restart as read, or the new copy reads it again and restarts for ever
                    _tg_get_updates(offset=last_update_id, timeout=0)
                except Exception:
                    pass
                app.after(0, app.save_settings)
                time.sleep(1)
                os.execv(sys.executable, [sys.executable] + sys.argv)

            # ── STATUS ──
            elif tl in ["/health", f"/health {PC_NAME.lower()}"]:
                try:
                    import shutil as _sh, platform as _pf
                    du = _sh.disk_usage(os.path.expanduser("~"))
                    up = int(time.time() - TelegramAuth._session_start) if getattr(TelegramAuth, "_session_start", None) else 0
                    _tg_send(f"🩺 <b>{PC_NAME}</b>\nNAB v{APP_VERSION}\nUp for {up // 3600}h {up % 3600 // 60}m\nFree disk {du.free // 2**30} GB\nPython {_pf.python_version()}")
                except Exception as e:
                    _tg_send(f"Health check failed: {e}")

            elif tl in ["/log", f"/log {PC_NAME.lower()}"]:
                try:
                    import nab_engine_host as _H
                    lf = _H.LOG_FILE
                    data = open(lf, "rb").read()[-30000:] if os.path.isfile(lf) else b""
                    _tg_send(f"📄 Log of <b>{PC_NAME}</b> (last part):\n<pre>{data.decode('utf-8', 'replace')[-3500:].replace('<', '&lt;')}</pre>" if data else "No log yet.")
                except Exception as e:
                    _tg_send(f"Could not read the log: {e}")

            elif tl in ["/status", f"/status {PC_NAME.lower()}"]:
                app.after(0, lambda: app._send_tg_status())

            # ── PREVIEW ──
            elif tl in ["/preview", f"/preview {PC_NAME.lower()}"]:
                app.after(0, lambda: app._tg_send_preview())

            # ── REPORT ──
            elif tl in ["/report", f"/report {PC_NAME.lower()}"]:
                app.after(0, lambda: app._send_tg_report())

            # ── VERSION ──
            elif tl == "/version":
                _tg_send(f"📦 NAB v<b>{APP_VERSION}</b> on <b>{PC_NAME}</b>")

            # ── EXTEND SESSION ──
            elif tl.startswith("/extend"):
                parts = tl.split()
                try:
                    hours = float(parts[-1])
                    if TelegramAuth._access_deadline:
                        TelegramAuth._access_deadline += hours * 3600
                    else:
                        TelegramAuth._access_deadline = time.time() + hours * 3600
                    exp_str = datetime.datetime.fromtimestamp(
                        TelegramAuth._access_deadline).strftime("%H:%M:%S")
                    _tg_send(f"⏱ Session extended on <b>{PC_NAME}</b>. Expires: <b>{exp_str}</b>")
                except (ValueError, IndexError):
                    _tg_send("❓ Use: /extend 1 (hours)")

            # ── BLOCK / UNBLOCK ──
            elif tl == "/blocked":
                _send_blocked_pcs_list()

            elif tl.startswith("/unblock "):
                _unblock_pc(text.split(maxsplit=1)[1].strip())

            # ── BROADCAST POPUP ──
            elif tl.startswith("/broadcast"):
                rest = text[len("/broadcast"):].strip()
                app.after(0, lambda r=rest: app._handle_broadcast(r))

            # ── NAB UPDATE (send NAB.pyw / nab_tracker.py / surgical_tools.py via local bot) ──
            elif msg.get("document", {}).get("file_name", "").lower() in [
                "nab.pyw", "nab.py", "nab_tracker.py", "surgical_tools.py"
            ]:
                doc       = msg["document"]
                file_id   = doc["file_id"]
                fname     = doc["file_name"].lower()
                _tg_send(f"⬇️ Downloading <b>{doc['file_name']}</b> on <b>{PC_NAME}</b>...")
                try:
                    params    = _urllib_parse.urlencode({"file_id": file_id})
                    resp      = _urllib_req.urlopen(f"{TG_API}/getFile?{params}", context=_SSL_CTX, timeout=8)
                    file_path = json.loads(resp.read())["result"]["file_path"]
                    file_url  = f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{file_path}"
                    with _urllib_req.urlopen(file_url, context=_SSL_CTX, timeout=30) as r:
                        new_code = r.read()

                    # Validation per file type
                    valid = False
                    if fname in ["nab.pyw", "nab.py"]:
                        valid = b"NewsClipper" in new_code or b"customtkinter" in new_code
                    elif fname == "nab_tracker.py":
                        valid = b"NewspaperTracker" in new_code or b"nab_tracker" in new_code.lower()
                    elif fname == "surgical_tools.py":
                        valid = b"SurgicalWorkspace" in new_code

                    if valid:
                        # Target the folder the app was actually LAUNCHED from.
                        # __file__ here is nab_auth.py, and under PyInstaller
                        # that resolves inside sys._MEIPASS — a temp folder
                        # wiped on exit, so the "update" was written to a
                        # directory that no longer existed by the time NAB
                        # restarted. _current_exe() (nab_update.py) already
                        # solves this with sys.argv[0].
                        base_dir    = os.path.dirname(_current_exe())
                        target_file = os.path.join(base_dir, doc["file_name"])
                        shutil.copy2(target_file, target_file + ".backup") if os.path.exists(target_file) else None
                        with open(target_file, "wb") as f:
                            f.write(new_code)
                        _tg_send(f"✅ <b>{doc['file_name']}</b> updated on <b>{PC_NAME}</b>! Restarting...")
                        time.sleep(1)
                        os.execv(sys.executable, [sys.executable] + sys.argv)
                    else:
                        _tg_send(f"❌ Invalid file content. Update of <b>{doc['file_name']}</b> cancelled.")
                except Exception as e:
                    _tg_send(f"❌ Update failed: {e}")

            # ── DRIVE TEST ──
            elif tl in ["/drivetest", "drivetest"]:
                app.after(0, lambda: app._test_drive_connection())

            # ── STATS ──
            elif tl in ["/stats", f"/stats {PC_NAME.lower()}"]:
                app.after(0, lambda: app._send_stats())

            # ── LOG ──
            elif tl == "/log today":
                _send_log_today()

            # ── HELP ──
            elif tl in ["/start", "/help", "hello", "hi"]:
                _tg_send(
                    f"👋 <b>NAB Local Bot — {PC_NAME}</b> v{APP_VERSION}\n\n"
                    f"<b>🔐 Auth:</b>\n"
                    f"allow / allow 2 / deny\n\n"
                    f"<b>🖥️ Control:</b>\n"
                    f"/screenshot — grab screen\n"
                    f"/pause / /resume\n"
                    f"/restart — restart NAB\n"
                    f"/health — version, uptime, free disk\n"
                    f"/log — last part of the log\n"
                    f"/close — close NAB\n"
                    f"/extend 1 — extend session (hours)\n\n"
                    f"<b>📊 Info:</b>\n"
                    f"/status — session info\n"
                    f"/preview — canvas preview\n"
                    f"/report — activity report\n"
                    f"/stats — clip statistics\n"
                    f"/version — current version\n"
                    f"/log today — today's access log\n\n"
                    f"<b>🔒 Security:</b>\n"
                    f"/blocked — blocked PCs\n"
                    f"/unblock [pc] — unblock a PC\n\n"
                    f"<b>📁 Files & Uploads:</b>\n"
                    f"Use the <b>Cloud Bot</b> for uploads, Drive, and group commands."
                )

            return False

        def _handle_cloud_command(cmd):
            """Handle commands queued by the cloud bot (file/upload only)."""
            if cmd.startswith("EVT|"):                       # a button under the live picture
                live.send_event(cmd[4:].strip())
                return
            if cmd.startswith("CMD|"):
                cmd = cmd[4:]
            tl = cmd.strip().lower()

            simple = {"screenshot": "/screenshot", "pause": "/pause", "resume": "/resume", "restart": "/restart",
                      "health": "/health", "report": "/report", "status": "/status"}
            if tl in simple:
                _handle_local_command(simple[tl], {})
                return
            if tl.startswith("extend|"):
                try:
                    _handle_local_command(f"/extend {float(tl.split('|')[1]) / 60:g}", {})
                except ValueError:
                    pass
                return
            if tl.startswith("live|"):
                live.start(cmd.split("|", 1)[1].strip(), app)
                return
            if tl.startswith("ask|"):
                parts = cmd.split("|", 2)
                if len(parts) == 3:
                    nab_remote.ask_riko(_nab_telegram_mod, app, parts[1].strip(), parts[2])
                return
            if tl == "sessionend":
                app.lock_session("session ended from Telegram")
                _tg_send(f"🔒 Session ended on <b>{PC_NAME}</b>. NAB is locked and needs a new approval to open.")
                return
            if tl == "block_self":
                try:
                    import getpass
                    blocked = _load_blocked_pcs()
                    blocked[PC_NAME] = {"user": getpass.getuser(), "blocked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "deny_count": 0}
                    _save_blocked_pcs(blocked)
                except Exception as ex:
                    logging.error(f"block self: {ex}")
                app.lock_session("this PC was blocked")
                _tg_send(f"⛔ <b>{PC_NAME}</b> blocked and locked.")
                return
            if tl == "unblock_self":
                _unblock_pc(PC_NAME)
                return
            if tl.startswith("send_log"):
                _send_log_today()
                return
            if tl.startswith("broadcast_user|"):
                parts = cmd.split("|", 2)
                if len(parts) == 3:
                    who = parts[1].strip().lower()
                    import getpass
                    if who in ("all", "*", "", PC_NAME.lower(), getpass.getuser().lower()):
                        app.after(0, lambda r=parts[2]: app._handle_broadcast(r))
                return
            if tl == "lock":
                _tg_send(f"🔒 Screen of <b>{PC_NAME}</b> locked." if nab_remote.lock_screen() else "❌ Could not lock the screen.")
                return
            if tl == "daily":
                def _daily():
                    try:
                        import nab_archive, nab_daily_report
                        r = nab_daily_report.build_for_day(nab_archive.get(), datetime.date.today().isoformat())
                        try:
                            link = nab_daily_report.upload_to_drive(r.get("doc") or r["path"])
                        except Exception as ex:
                            link = "upload failed: " + str(ex)[:120]
                        _tg_send(f"📊 Daily analysis for <b>{PC_NAME}</b>: {r.get('n', 0)} clips.\n" + "\n".join("• " + t for t in r.get("insights", [])[:5]) + f"\n{link}")
                    except Exception as ex:
                        _tg_send(f"❌ Daily analysis failed: {str(ex)[:200]}")
                threading.Thread(target=_daily, daemon=True, name="daily-from-telegram").start()
                return

            if tl.startswith("upload_old|"):
                parts = cmd.split("|")
                if len(parts) >= 3:
                    cat, scope = parts[1], parts[2]
                    # * means all categories
                    app.after(0, lambda c=cat, s=scope: app._upload_old_files(c, s))

            elif tl.startswith("upload_dates|"):
                # UPLOAD_DATES|category|date1,date2,date3,...
                parts = cmd.split("|")
                if len(parts) >= 3:
                    cat   = parts[1]  # * = all categories
                    dates = parts[2].split(",")
                    app.after(0, lambda c=cat, d=dates: app._upload_date_list(c, d))

            elif tl == "scan_local":
                app.after(0, lambda: app._scan_and_report_local())

            elif tl.startswith("force_upload|"):
                parts = cmd.split("|")
                if len(parts) >= 3:
                    cat, date = parts[1], parts[2]
                    app.after(0, lambda c=cat, d=date: app._force_upload_category(c, d))

            elif tl.startswith("update_code|"):
                parts = cmd.split("|")
                if len(parts) >= 3:
                    file_url, filename = parts[1], parts[2]
                    try:
                        _tg_send(f"⬇️ Downloading update on <b>{PC_NAME}</b>: <code>{filename}</code>")
                        with _urllib_req.urlopen(file_url, context=_SSL_CTX, timeout=30) as r:
                            new_code = r.read()
                        if b"NewsClipper" in new_code or b"customtkinter" in new_code:
                            # Same __file__/_MEIPASS problem as above.
                            current_file = _current_exe()
                            shutil.copy2(current_file, current_file + ".backup")
                            with open(current_file, "wb") as f:
                                f.write(new_code)
                            _tg_send(f"✅ Updated on <b>{PC_NAME}</b>! Restarting...")
                            time.sleep(1)
                            os.execv(sys.executable, [sys.executable] + sys.argv)
                        else:
                            _tg_send("❌ Invalid update file. Cancelled.")
                    except Exception as e:
                        _tg_send(f"❌ Update failed on <b>{PC_NAME}</b>: {e}")

            elif tl.startswith("setdate|"):
                app.after(0, lambda d=cmd.split("|")[1]: app._remote_set_date(d))

            elif tl.startswith("setpaper|"):
                app.after(0, lambda p=cmd.split("|", 1)[1]: app._remote_set_paper(p))

            elif tl.startswith("note|"):
                app.after(0, lambda n=cmd.split("|", 1)[1]: app._set_pending_note(n))

            elif tl.startswith("setgoal|"):
                try:
                    app.after(0, lambda g=int(cmd.split("|")[1]): app._set_daily_goal(g))
                except ValueError:
                    pass

            elif tl == "skipauto":
                app.after(0, lambda: app._skip_auto_snatch())

            elif tl.startswith("send_category|"):
                cat = cmd.split("|", 1)[1]
                app.after(0, lambda c=cat: app._send_category_files(c))

        import nab_remote, threading
        relay = nab_remote.available()
        live = nab_remote.Live(_nab_telegram_mod, PC_NAME)

        # ── MAIN LOOP ──────────────────────────────────────────────────────
        while True:
            try:
                # ── Session expiry ──
                if TelegramAuth._access_deadline and time.time() > TelegramAuth._access_deadline:
                    _tg_send(f"⏰ Session expired on <b>{PC_NAME}</b> — closing NAB.")
                    app.after(0, lambda: [app.save_settings(), app.destroy(), sys.exit(0)])
                    return

                # ── 15-min expiry warning ──
                if TelegramAuth._access_deadline:
                    remaining = TelegramAuth._access_deadline - time.time()
                    if 890 < remaining < 910:
                        exp_str = datetime.datetime.fromtimestamp(
                            TelegramAuth._access_deadline).strftime("%H:%M:%S")
                        app.after(0, lambda e=exp_str: app._show_expiry_warning(e))

                # ── LOCAL BOT: poll getUpdates (30s long-poll). With a cloud bot this PC does NOT read Telegram:
                # the cloud bot is the one reader and hands commands over with the heartbeat below. ──
                data = {} if relay else _tg_get_updates(offset=last_update_id, timeout=30)
                for update in data.get("result", []):
                    last_update_id = update["update_id"] + 1
                    cbq = update.get("callback_query")
                    if cbq:
                        cd = cbq.get("data", "") or ""
                        cb_chat = str(cbq.get("message", {}).get("chat", {}).get("id", ""))
                        if cd.startswith("nab_sync_") and cb_chat in (TG_CHAT_ID, TG_GROUP_CHAT_ID):
                            _tg_answer_callback_query(cbq["id"], text="Got it!")
                            TelegramAuth._sync_decisions[cd.rsplit("_", 1)[1]] = cd.startswith("nab_sync_ok_")
                        continue
                    msg     = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text    = msg.get("text", "") or ""
                    if chat_id != TG_CHAT_ID:
                        # The group (TG_GROUP_CHAT_ID) is a known, expected
                        # source — it's just not privileged to run admin
                        # commands, and replying "Unauthorized" to every
                        # message anyone sends there is noisy and pointless.
                        # Silently ignore it. Still warn for a genuinely
                        # unknown/unexpected chat trying to talk to the bot.
                        if chat_id != TG_GROUP_CHAT_ID:
                            _tg_send("⛔ Unauthorized.", chat_id=chat_id)
                        continue
                    should_exit = _handle_local_command(text, msg)
                    if should_exit:
                        return

                # ── CLOUD BOT: heartbeat every 30s ──
                now = time.time()
                if relay:
                    time.sleep(1)
                if now - last_heartbeat_time >= (3 if relay else 30):
                    last_heartbeat_time = now
                    try:
                        cloud_commands = _cloud_heartbeat_post(APP_VERSION)
                        for cmd in cloud_commands:
                            _handle_cloud_command(cmd)
                    except Exception as e:
                        logging.error(f"cloud heartbeat: {e}")

            except Exception as e:
                logging.error(f"background_listener: {e}")
                time.sleep(5)

def _send_log_today():
    log = _load_access_log()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    today_entries = [e for e in log if e["time"].startswith(today)]
    if not today_entries:
        _tg_send(f"📋 No login attempts today on <b>{PC_NAME}</b>.")
        return
    lines = []
    for e in today_entries[-20:]:
        icon = "✅" if "granted" in e["result"] else "⛔"
        lines.append(f"{icon} {e['time'][11:]} — {e['pc']} ({e['user']}) — {e['result']}")
    _tg_send(f"📋 <b>Access Log Today</b>\n\n" + "\n".join(lines))



def _send_blocked_pcs_list():
    blocked = _load_blocked_pcs()
    if not blocked:
        _tg_send("✅ No blocked PCs.")
        return
    lines = []
    for pc, info in blocked.items():
        lines.append(f"🚫 <code>{pc}</code> — user: {info.get('user','?')} — blocked: {info.get('blocked_at','?')} — denials: {info.get('deny_count','?')}")
    _tg_send("🚫 <b>Blocked PCs:</b>\n\n" + "\n".join(lines) + "\n\nSend /unblock PC_NAME to unblock.")

def _unblock_pc(pc_name):
    blocked = _load_blocked_pcs()
    if pc_name in blocked:
        del blocked[pc_name]
        _save_blocked_pcs(blocked)
        _tg_send(f"✅ <b>{pc_name}</b> has been unblocked. They can now log in.")
    else:
        _tg_send(f"ℹ️ <b>{pc_name}</b> is not in the blocked list.")

# ─────────────────────────────────────────────
# DIALOGS
# ─────────────────────────────────────────────
