# nab_accounts.py - named user accounts for NAB (free, no server).
#
# Users live in one JSON file (Documents\nab_users.json). The owner PC uploads it with the other settings and every
# other PC downloads it, so an account made once works on every PC.  Passwords are never stored: only a salted scrypt
# hash.  Roles:  owner (everything), staff (clip, save, send, tracker, mail), viewer (look only, cannot save or send).
# Accounts are an EXTRA way to unlock NAB.  The Telegram approval still works, and it is also the way back in if the
# only owner forgets the password.  Every important action is written to an audit log (Documents\nab_audit.jsonl).
import os
import re
import json
import time
import hmac
import base64
import hashlib
import logging
import threading

DOC = os.path.join(os.path.expanduser("~"), "Documents")
USERS_FILE = os.path.join(DOC, "nab_users.json")
AUDIT_FILE = os.path.join(DOC, "nab_audit.jsonl")
ROLES = ("owner", "staff", "viewer")
MIN_PW = 6
_lock = threading.RLock()
_current = {"name": "", "role": "", "display": ""}
_fails = {}            # name -> (count, locked_until)
PC = [""]


def init(pc_name=""):
    PC[0] = pc_name or ""


# ------------------------------------------------------------------ storage
def _load():
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("users"), dict):
            return d
    except Exception:
        pass
    return {"v": 1, "users": {}}


def _save(d):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, USERS_FILE)


def _key(name):
    return re.sub(r"\s+", " ", str(name or "")).strip().lower()


def _hash(pw, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return base64.b64encode(salt).decode(), base64.b64encode(h).decode()


def _check(pw, salt_b64, hash_b64):
    try:
        _s, h = _hash(pw, base64.b64decode(salt_b64))
        return hmac.compare_digest(h, hash_b64)
    except Exception:
        return False


# ------------------------------------------------------------------ audit
def audit(action, detail="", user=None):
    """Append one line to the audit log. Never raises."""
    try:
        who = user if user is not None else (_current["name"] or ("pc:" + PC[0] if PC[0] else "pc"))
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "user": who, "pc": PC[0], "action": action, "detail": str(detail)[:300]}
        with _lock:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
            try:
                if os.path.getsize(AUDIT_FILE) > 1_500_000:
                    os.replace(AUDIT_FILE, AUDIT_FILE + ".old")
            except OSError:
                pass
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"audit: {e}")


def audit_tail(n=200, user="", action=""):
    out = []
    try:
        with open(AUDIT_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-4000:]
        for ln in reversed(lines):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if user and _key(r.get("user")) != _key(user):
                continue
            if action and action not in r.get("action", ""):
                continue
            out.append(r)
            if len(out) >= n:
                break
    except Exception:
        pass
    return out


# ------------------------------------------------------------------ queries
def has_users():
    return bool(_load()["users"])


def current():
    return dict(_current)


def can(permission):
    """permission: 'save' | 'send' | 'manage'. No account signed in (Telegram login) = full access, exactly as before
    accounts existed. staff: save and send. viewer: look only. owner: everything."""
    role = _current["role"]
    if not role:
        return True
    if role == "owner":
        return True
    if role == "staff":
        return permission in ("save", "send")
    return False


def status():
    d = _load()
    return {"has_users": bool(d["users"]), "current": current(), "count": len(d["users"])}


def list_users():
    d = _load()
    return [{"name": k, "display": v.get("display") or k, "role": v.get("role", "staff"), "disabled": bool(v.get("disabled")),
             "email": v.get("email", ""), "created": v.get("created", ""), "last_login": v.get("last_login", ""), "must_change": bool(v.get("must_change"))}
            for k, v in sorted(d["users"].items())]


# ------------------------------------------------------------------ sign in / out
def login(name, password):
    k = _key(name)
    now = time.time()
    c, until = _fails.get(k, (0, 0))
    if until > now:
        return {"ok": False, "error": f"Too many wrong passwords. Try again in {int(until - now) + 1} s."}
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u or u.get("disabled") or not _check(str(password or ""), u.get("salt", ""), u.get("hash", "")):
            c += 1
            _fails[k] = (c, now + min(300, 5 * 2 ** max(0, c - 3)) if c >= 3 else 0)
            audit("login_failed", k, user=k or "?")
            return {"ok": False, "error": "Wrong name or password."}
        _fails.pop(k, None)
        u["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            _save(d)
        except Exception:
            pass
        _current.update({"name": k, "role": u.get("role", "staff"), "display": u.get("display") or k})
    audit("login", "account")
    return {"ok": True, "user": current(), "must_change": bool(u.get("must_change"))}


def login_google(email, name=""):
    """Any Google email may join. A first sign-in creates a viewer account (promote it in Settings); a switched-off or blocked email is refused."""
    email = str(email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "Google did not give an email."}
    with _lock:
        d = _load()
        hit = [(k, u) for k, u in d["users"].items() if str(u.get("email", "")).strip().lower() == email]
        if hit and hit[0][1].get("disabled"):
            audit("login_failed", "google blocked " + email, user=email)
            return {"ok": False, "error": "This Google account is blocked in NAB."}
        if hit:
            k, u = hit[0]
        else:
            k = _key(email)
            u = d["users"][k] = {"role": "viewer", "display": (name or email.split("@")[0])[:40], "email": email, "google": True,
                                 "created": time.strftime("%Y-%m-%d %H:%M:%S"), "disabled": False, "must_change": False}
            audit("account_add", f"{k} (viewer, joined with Google)", user=k)
        u["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            _save(d)
        except Exception:
            pass
        _current.update({"name": k, "role": u.get("role", "staff"), "display": u.get("display") or k})
    audit("login", "google")
    return {"ok": True, "user": current(), "must_change": False}


def block_email(email, blocked=True, actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    email = str(email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return {"ok": False, "error": "That does not look like an email address."}
    with _lock:
        d = _load()
        hit = [u for u in d["users"].values() if str(u.get("email", "")).lower() == email]
        if hit:
            for u in hit:
                u["disabled"] = bool(blocked)
        elif blocked:
            d["users"][_key(email)] = {"role": "viewer", "display": email, "email": email, "google": True, "disabled": True,
                                       "created": time.strftime("%Y-%m-%d %H:%M:%S"), "must_change": False}
        _save(d)
    audit("account_block" if blocked else "account_unblock", email)
    return {"ok": True}


def set_email(name, email, actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    k, email = _key(name), str(email or "").strip().lower()
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return {"ok": False, "error": "That does not look like an email address."}
    with _lock:
        d = _load()
        if k not in d["users"]:
            return {"ok": False, "error": "No such person."}
        if email and any(kk != k and str(u.get("email", "")).lower() == email for kk, u in d["users"].items()):
            return {"ok": False, "error": "Another account already uses that email."}
        d["users"][k]["email"] = email
        _save(d)
    audit("account_email", f"{k} -> {email or 'none'}")
    return {"ok": True}


def logout():
    audit("logout")
    _current.update({"name": "", "role": "", "display": ""})
    return {"ok": True}


# ------------------------------------------------------------------ management (owner PC only; the caller checks that)
def _need_owner(actor_ok):
    if not actor_ok:
        return {"ok": False, "error": "Only the owner can manage accounts, on the owner PC."}
    return None


def add_user(name, password, role="staff", display="", actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    k = _key(name)
    if not re.fullmatch(r"[\w .\-]{2,32}", k):
        return {"ok": False, "error": "Use 2-32 letters, numbers, spaces, dots or dashes for the name."}
    if len(str(password or "")) < MIN_PW:
        return {"ok": False, "error": f"The password needs at least {MIN_PW} characters."}
    if role not in ROLES:
        return {"ok": False, "error": "Unknown role."}
    with _lock:
        d = _load()
        if k in d["users"]:
            return {"ok": False, "error": "That name already exists."}
        first = not d["users"]
        salt, h = _hash(str(password))
        d["users"][k] = {"salt": salt, "hash": h, "role": "owner" if first else role, "display": (display or name).strip()[:40],
                         "created": time.strftime("%Y-%m-%d %H:%M:%S"), "disabled": False, "must_change": False}
        _save(d)
    audit("account_add", f"{k} ({'owner' if first else role})")
    return {"ok": True}


def _owners(d):
    return [k for k, v in d["users"].items() if v.get("role") == "owner" and not v.get("disabled")]


def set_role(name, role, actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    k = _key(name)
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u or role not in ROLES:
            return {"ok": False, "error": "Account or role not found."}
        if u.get("role") == "owner" and role != "owner" and _owners(d) == [k]:
            return {"ok": False, "error": "Keep at least one owner."}
        u["role"] = role
        _save(d)
    audit("account_role", f"{k} -> {role}")
    return {"ok": True}


def set_disabled(name, disabled, actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    k = _key(name)
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u:
            return {"ok": False, "error": "Account not found."}
        if disabled and u.get("role") == "owner" and _owners(d) == [k]:
            return {"ok": False, "error": "Keep at least one active owner."}
        u["disabled"] = bool(disabled)
        _save(d)
    audit("account_disable" if disabled else "account_enable", k)
    return {"ok": True}


def delete_user(name, actor_ok=False):
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    k = _key(name)
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u:
            return {"ok": False, "error": "Account not found."}
        if u.get("role") == "owner" and _owners(d) == [k]:
            return {"ok": False, "error": "Keep at least one owner."}
        del d["users"][k]
        _save(d)
    audit("account_delete", k)
    return {"ok": True}


def reset_password(name, new_password, actor_ok=False):
    """Owner sets a temporary password; the person must change it at next sign-in."""
    bad = _need_owner(actor_ok)
    if bad:
        return bad
    if len(str(new_password or "")) < MIN_PW:
        return {"ok": False, "error": f"The password needs at least {MIN_PW} characters."}
    k = _key(name)
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u:
            return {"ok": False, "error": "Account not found."}
        u["salt"], u["hash"] = _hash(str(new_password))
        u["must_change"] = True
        _save(d)
    _fails.pop(k, None)
    audit("account_reset", k)
    return {"ok": True}


def change_own_password(old, new):
    k = _current["name"]
    if not k:
        return {"ok": False, "error": "Sign in with your account first."}
    if len(str(new or "")) < MIN_PW:
        return {"ok": False, "error": f"The password needs at least {MIN_PW} characters."}
    with _lock:
        d = _load()
        u = d["users"].get(k)
        if not u or not _check(str(old or ""), u.get("salt", ""), u.get("hash", "")):
            return {"ok": False, "error": "The current password is wrong."}
        u["salt"], u["hash"] = _hash(str(new))
        u["must_change"] = False
        _save(d)
    audit("password_changed")
    return {"ok": True}
