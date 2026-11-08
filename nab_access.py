# nab_access.py — access log, blocked PCs, cloud heartbeat
import os
import json
import datetime

DOC_DIR = os.path.join(os.path.expanduser("~"), "Documents")
ACCESS_LOG_FILE = os.path.join(DOC_DIR, "nab_access_log.json")
BLOCKED_PCS_FILE = os.path.join(DOC_DIR, "nab_blocked_pcs.json")

def _load_access_log():
    try:
        if os.path.exists(ACCESS_LOG_FILE):
            with open(ACCESS_LOG_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_access_log(log):
    try:
        with open(ACCESS_LOG_FILE, 'w') as f:
            json.dump(log[-500:], f)  # keep last 500 entries
    except Exception:
        pass

def _load_blocked_pcs():
    try:
        if os.path.exists(BLOCKED_PCS_FILE):
            with open(BLOCKED_PCS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_blocked_pcs(blocked):
    try:
        with open(BLOCKED_PCS_FILE, 'w') as f:
            json.dump(blocked, f)
    except Exception:
        pass

def _log_access_attempt(pc, user, result):
    log = _load_access_log()
    entry = {
        "pc": pc,
        "user": user,
        "result": result,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    log.append(entry)
    _save_access_log(log)

def _get_denied_count(pc):
    log = _load_access_log()
    count = 0
    for entry in reversed(log):
        if entry["pc"] == pc:
            if entry["result"] == "denied":
                count += 1
            else:
                break
    return count

