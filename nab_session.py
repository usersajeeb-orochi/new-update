# nab_session.py — "remember me for today" and "quick re-login" (per PC, never synced).
# The file is signed so a hand-edited copy is ignored; this is tamper-evidence, not a vault.
import os, json, time, hmac, hashlib, logging

_dir = [None]
PC = [""]


def init(folder, pc_name):
    _dir[0] = folder
    PC[0] = pc_name or ""


def _path():
    return os.path.join(_dir[0] or os.path.expanduser("~"), "nab_session.json")


def _sig(d):
    body = json.dumps({k: d.get(k) for k in ("pc", "last_active", "deadline", "remember_until")}, sort_keys=True)
    return hmac.new(("NAB-session-v1|" + PC[0]).encode(), body.encode(), hashlib.sha256).hexdigest()


def load():
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("pc") != PC[0] or not hmac.compare_digest(str(d.get("sig", "")), _sig(d)):
            return {}
        return d
    except Exception:
        return {}


def save(d):
    try:
        d["pc"] = PC[0]
        d["sig"] = _sig(d)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _path())
    except Exception as e:
        logging.error(f"session save: {e}")


def touch(deadline=None):
    """Called every ~30 s while the session is authorised."""
    d = load()
    d["last_active"] = time.time()
    d["deadline"] = deadline
    save(d)


def remember(until_ts):
    d = load()
    d["remember_until"] = float(until_ts)
    save(d)


def clear():
    try:
        os.remove(_path())
    except Exception:
        pass


def check(grace_min):
    """Returns ('remember'|'regrace', info) when this PC may start without asking, else (None, '')."""
    d = load()
    now = time.time()
    if d.get("remember_until") and now < float(d["remember_until"]):
        return "remember", d
    gm = float(grace_min or 0)
    if gm > 0 and d.get("last_active") and 0 <= now - float(d["last_active"]) <= gm * 60:
        dl = d.get("deadline")
        if dl is None or now < float(dl):
            return "regrace", d
    return None, d
