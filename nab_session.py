# nab_session.py - "remember me" and "quick re-login", decided by the CLOUD.
#
# The cloud bot keeps every PC's approval (who approved, for how long, extended, closed, blocked). This module only asks
# it. The small signed file below is a cache for a short internet drop; it cannot grant anything on its own:
#   * with a cloud configured, a start is allowed only when the cloud says so, or when the cloud was reachable a few
#     minutes ago and said so (OFFLINE_OK);
#   * deleting or editing the file can never create or extend access.
# Without a cloud (a build with no cloud address) the old local behaviour is kept so such a build still works.
import os, json, time, hmac, hashlib, logging

_dir = [None]
PC = [""]

OFFLINE_OK = 10 * 60               # a cloud answer is trusted this long when the cloud cannot be reached
OFFLINE_LOCK = 30 * 60             # an open session locks after this long without any cloud answer
MAX_REMEMBER = 60 * 86400          # (no-cloud builds) a remembered approval never runs longer than this


def init(folder, pc_name):
    _dir[0] = folder
    PC[0] = pc_name or ""


def _path():
    return os.path.join(_dir[0] or os.path.expanduser("~"), "nab_session.json")


def _sig(d):
    import nab_secrets
    body = json.dumps({k: d.get(k) for k in ("pc", "last_active", "deadline", "remember_until", "saved", "cloud")}, sort_keys=True)
    return hmac.new(nab_secrets._key("session|" + PC[0], per_pc=True), body.encode(), hashlib.sha256).hexdigest()


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
        d["saved"] = d.get("saved") or time.time()
        d["sig"] = _sig(d)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, _path())
    except Exception as e:
        logging.error(f"session save: {e}")


def _cloud_on():
    try:
        import nab_remote
        return nab_remote.available()
    except Exception:
        return False


def _cache(kind, until=None):
    d = load()
    d["cloud"] = {"kind": kind, "at": time.time(), "until": until} if kind else None
    save(d)


def touch(deadline=None):
    """Called every ~30 s while open: keeps the offline cache fresh (and, without a cloud, the local grace window)."""
    d = load()
    d["last_active"] = time.time()
    d["deadline"] = deadline
    save(d)


def remember(until_ts):
    """After an approval. With a cloud the cloud already holds it; this only refreshes the short offline cache."""
    if _cloud_on():
        _cache("remember", min(float(until_ts), time.time() + MAX_REMEMBER))
        return
    d = load()
    d["remember_until"] = min(float(until_ts), time.time() + MAX_REMEMBER)
    d["saved"] = time.time()
    save(d)


def clear():
    try:
        os.remove(_path())
    except Exception:
        pass


def check(grace_min):
    """('remember'|'regrace', info) when this PC may start without asking, else (None, info)."""
    gm = max(0.0, min(float(grace_min or 0), 30.0))                 # quick re-login grace: at most 30 minutes
    if _cloud_on():
        import nab_remote
        r = nab_remote.session_state(PC[0], "start", gm)
        if r is not None:
            if r.get("state") == "ok" and r.get("kind") in ("remember", "regrace"):
                _cache(r["kind"], r.get("until"))
                return r["kind"], r
            _cache(None)
            return None, r
        c = (load().get("cloud") or {})                              # cloud unreachable: only a very recent cloud "yes" counts
        if c.get("kind") and 0 <= time.time() - float(c.get("at", 0)) <= OFFLINE_OK:
            return c["kind"], c
        return None, {}
    d = load()
    now = time.time()
    if d.get("remember_until") and now < float(d["remember_until"]) <= now + MAX_REMEMBER + 60:
        return "remember", d
    if gm > 0 and d.get("last_active") and 0 <= now - float(d["last_active"]) <= gm * 60:
        dl = d.get("deadline")
        if dl is None or now < float(dl):
            return "regrace", d
    return None, d


def heartbeat(enforce=True):
    """While open: ask the cloud. -> {"state": "ok", "deadline"} | {"state": "revoked", "why"} | {"state": "offline"} | {"state": "idle"}.
    enforce=False is for sessions opened with an account (no Telegram approval): only a block ends those."""
    if not _cloud_on():
        return {"state": "idle"}
    import nab_remote
    r = nab_remote.session_state(PC[0], "touch")
    if r is None:
        return {"state": "offline"}
    st = r.get("state")
    if st == "blocked":
        return {"state": "revoked", "why": "this PC was blocked"}
    if st == "ok":
        _cache("remember" if r.get("kind") == "remember" else "regrace", r.get("until"))
        return {"state": "ok", "deadline": r.get("deadline")}
    if enforce:
        return {"state": "revoked", "why": "the approval was closed or ran out on the server"}
    return {"state": "idle"}
