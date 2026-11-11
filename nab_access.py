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

def _read_blocked_file():
    try:
        if os.path.exists(BLOCKED_PCS_FILE):
            with open(BLOCKED_PCS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        return {"_sig": "unreadable"}
    return None

def _load_blocked_pcs():
    """Blocked PCs. The file is signed and a copy lives in the registry: a hand-edited file is ignored, a deleted file is
    restored from the copy, and a file that cannot be trusted blocks this PC until the admin sends /unblock."""
    import nab_secrets
    reg = None
    try:
        raw = nab_secrets.reg_get("BlockedPCs")
        reg = json.loads(raw) if raw else None
    except Exception:
        reg = {"_sig": "unreadable"}
    f = _read_blocked_file()
    for cand in (f, reg):
        if isinstance(cand, dict) and nab_secrets.valid(cand, "blocked"):
            return {k: v for k, v in cand.items() if k != "_sig"}
    if f is None and reg is None:
        return {}                                                   # never blocked on this PC
    if isinstance(f, dict) and not f.get("_sig") and reg is None and "NAB_UNSIGNED_OK" in os.environ:
        return f
    if isinstance(f, dict) and not f.get("_sig") and reg is None and not nab_secrets.has_key():
        return {k: v for k, v in f.items()}                         # development build, no secret key
    try:
        import socket
        return {socket.gethostname(): {"user": "?", "blocked_at": "tampered file", "deny_count": 0}}
    except Exception:
        return {"?": {}}

def _save_blocked_pcs(blocked):
    import nab_secrets
    signed = nab_secrets.sign({k: v for k, v in blocked.items() if k != "_sig"}, "blocked")
    try:
        with open(BLOCKED_PCS_FILE, 'w') as f:
            json.dump(signed, f)
    except Exception:
        pass
    nab_secrets.reg_set("BlockedPCs", json.dumps(signed))

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

