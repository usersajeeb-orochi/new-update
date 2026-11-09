# nab_health.py - the Self-check screen: one list of green / amber / red lines for everything NAB depends on.
# Each check is small, has its own timeout, and never raises.  Run from Settings > Self-check or Telegram /health.
import os
import time
import shutil
import logging
import threading
import datetime
import email.utils

OK, WARN, BAD = "ok", "warn", "bad"


def _row(id_, label, status, detail="", fix=""):
    return {"id": id_, "label": label, "status": status, "detail": detail, "fix": fix}


def check_clock():
    try:
        import requests
        r = requests.head("https://www.google.com", timeout=5)
        srv = email.utils.parsedate_to_datetime(r.headers["Date"]).timestamp()
        drift = abs(time.time() - srv)
        if drift > 120:
            return _row("clock", "PC clock", BAD, f"Off by {int(drift)} s. Google refuses logins when the clock is wrong.", "Windows Settings > Time & language > Sync now.")
        return _row("clock", "PC clock", OK if drift < 30 else WARN, f"Off by about {int(drift)} s")
    except Exception as e:
        return _row("clock", "PC clock", WARN, "Could not compare with the internet time: " + str(e)[:60])


def check_internet():
    try:
        import requests
        t = time.time()
        requests.head("https://www.google.com", timeout=5)
        return _row("net", "Internet", OK, f"{int((time.time() - t) * 1000)} ms")
    except Exception as e:
        return _row("net", "Internet", BAD, "No connection: " + str(e)[:60], "Check the network cable or Wi-Fi.")


def check_updates():
    try:
        import nab_update
        r = nab_update._github_get_latest_release()
        if r:
            return _row("upd", "Update server (GitHub)", OK, "Reachable")
        return _row("upd", "Update server (GitHub)", WARN, "Reached GitHub but found no release")
    except Exception as e:
        return _row("upd", "Update server (GitHub)", WARN, "Not reachable right now: " + str(e)[:60])


def check_drive(e):
    try:
        s = e.sync_status()
        if not s.get("started"):
            return _row("drive", "Google Drive sync", WARN, "Sync has not started yet")
        if s.get("no_drive"):
            return _row("drive", "Google Drive sync", BAD, "No Drive key in this build", "Update to the newest NAB.")
        if s.get("offline"):
            return _row("drive", "Google Drive sync", BAD, "Drive refused or is not reachable. Last try: " + str(s.get("time") or "never"),
                        "If the log says invalid_grant, the Google key was disabled: make a new key and rebuild.")
        return _row("drive", "Google Drive sync", OK, "Last sync " + str(s.get("time") or ""))
    except Exception as ex:
        return _row("drive", "Google Drive sync", WARN, str(ex)[:80])


def check_telegram():
    try:
        import requests
        import nab_telegram
        r = requests.get(nab_telegram.TG_API + "/getMe", timeout=6).json()
        return _row("tg", "Telegram bot", OK if r.get("ok") else BAD, "Connected" if r.get("ok") else str(r.get("description", ""))[:80],
                    "" if r.get("ok") else "The bot token may be wrong or revoked.")
    except Exception as ex:
        return _row("tg", "Telegram bot", WARN, "Not reachable: " + str(ex)[:60])


def check_whatsapp(e):
    try:
        import nab_tools
        t = nab_tools.get("wa", e)
        st = t.api_queue({})
        if not t.deps():
            return _row("wa", "WhatsApp", WARN, "Playwright is not installed", "pip install playwright")
        if not st.get("linked"):
            return _row("wa", "WhatsApp", WARN, "Not linked yet", "Settings > WhatsApp > Link WhatsApp.")
        failed = [j for j in st.get("jobs", []) if j["state"] == "failed"]
        if failed:
            return _row("wa", "WhatsApp", WARN, f"{len(failed)} send(s) failed. Last problem: {st.get('last_error', '')[:70]}", "Open Settings > WhatsApp > Send queue and press Retry.")
        return _row("wa", "WhatsApp", OK, f"Linked. {st.get('pending', 0)} waiting.")
    except Exception as ex:
        return _row("wa", "WhatsApp", WARN, str(ex)[:80])


def check_disk(e):
    try:
        root = getattr(e, "base_root", os.path.expanduser("~"))
        os.makedirs(root, exist_ok=True)
        free = shutil.disk_usage(root).free / 1e9
        test = os.path.join(root, ".nab_write_test")
        with open(test, "w") as f:
            f.write("x")
        os.remove(test)
        st = OK if free > 2 else WARN if free > 0.5 else BAD
        return _row("disk", "Clip folder", st, f"{root} - {free:.1f} GB free, writable", "" if st == OK else "Free some disk space.")
    except Exception as ex:
        return _row("disk", "Clip folder", BAD, "Cannot write: " + str(ex)[:70], "Choose another folder in Settings.")


def check_tools():
    out = []
    try:
        import pytesseract
        ok = bool(shutil.which("tesseract")) or os.path.exists(getattr(pytesseract.pytesseract, "tesseract_cmd", "") or "")
        out.append(_row("ocr", "Tesseract OCR", OK if ok else WARN, "Found" if ok else "Not found; text reading is off", "" if ok else "Install Tesseract (free) if you need OCR."))
    except Exception:
        out.append(_row("ocr", "Tesseract OCR", WARN, "pytesseract not installed"))
    try:
        import playwright  # noqa: F401
        out.append(_row("pw", "Playwright (WhatsApp, Hunter, screenshots)", OK, "Installed"))
    except Exception:
        out.append(_row("pw", "Playwright (WhatsApp, Hunter, screenshots)", WARN, "Not installed", "pip install playwright"))
    return out


def check_backups(e):
    try:
        b = e.backup_list()["backups"]
        if not b:
            return _row("bk", "Settings backup", WARN, "No backup yet", "Settings > Backups > Back up now.")
        return _row("bk", "Settings backup", OK, f"{len(b)} backups, newest {b[0]['name']}")
    except Exception as ex:
        return _row("bk", "Settings backup", WARN, str(ex)[:70])


def check_accounts():
    try:
        import nab_accounts
        s = nab_accounts.status()
        if not s["has_users"]:
            return _row("acct", "Accounts", WARN, "No accounts yet; Telegram approval is the only way in", "Settings > Accounts > Add a person.")
        return _row("acct", "Accounts", OK, f"{s['count']} account(s)" + (", signed in as " + s["current"]["name"] if s["current"]["name"] else ""))
    except Exception as ex:
        return _row("acct", "Accounts", WARN, str(ex)[:70])


def run_all(e, timeout=12):
    """Run every check in parallel; a slow one is reported as 'timed out' instead of freezing the screen."""
    jobs = [("clock", check_clock), ("net", check_internet), ("upd", check_updates), ("tg", check_telegram),
            ("drive", lambda: check_drive(e)), ("wa", lambda: check_whatsapp(e)), ("disk", lambda: check_disk(e)),
            ("tools", check_tools), ("bk", lambda: check_backups(e)), ("acct", check_accounts)]
    results = {}

    def work(name, fn):
        try:
            r = fn()
            results[name] = r if isinstance(r, list) else [r]
        except Exception as ex:
            logging.error(f"selfcheck {name}: {ex}")
            results[name] = [_row(name, name, WARN, "Check failed: " + str(ex)[:60])]
    ths = [threading.Thread(target=work, args=j, daemon=True) for j in jobs]
    for t in ths:
        t.start()
    end = time.time() + timeout
    for t in ths:
        t.join(max(0.1, end - time.time()))
    rows = []
    for name, _fn in jobs:
        rows.extend(results.get(name) or [_row(name, name, WARN, "Timed out")])
    worst = BAD if any(r["status"] == BAD for r in rows) else WARN if any(r["status"] == WARN for r in rows) else OK
    return {"ok": True, "rows": rows, "overall": worst, "at": datetime.datetime.now().strftime("%H:%M:%S")}
