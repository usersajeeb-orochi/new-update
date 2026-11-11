# nab_secrets.py - build-time secrets + tamper-evident signing for the local files that decide who may use NAB.
#
# nab_secrets.json is made by the build from the GitHub secret NAB_SECRETS_JSON and packed into the EXE. It is never in the
# repository:  {"tg_token": "<Telegram bot token>", "sign_key": "<long random text>"}
# A file that does not carry a valid signature (hand-edited, copied from another PC, deleted and re-made) is not trusted.
# Honest limit: this stops editing files in Documents; someone who unpacks the EXE could still read the key.
import hashlib
import hmac
import json
import logging
import os
import sys

NAME = "nab_secrets.json"
_cache = {}


def _dirs():
    d = []
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        d.append(mp)
    d.append(os.path.dirname(os.path.abspath(__file__)))
    return d


def _load():
    if "d" in _cache:
        return _cache["d"]
    data = {}
    for d in _dirs():
        p = os.path.join(d, NAME)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f) or {}
                break
            except Exception as e:
                logging.error(f"nab_secrets: {e}")
    _cache["d"] = data if isinstance(data, dict) else {}
    return _cache["d"]


def get(name, default=""):
    return str(_load().get(name) or default)


def has_key():
    return bool(get("sign_key"))


def _machine():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0))
        try:
            return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        finally:
            winreg.CloseKey(k)
    except Exception:
        return ""


def _key(purpose, per_pc=False):
    base = get("sign_key") or "NAB-dev-key-not-for-release"          # a build without the secret is a development build
    return (base + "|" + purpose + ("|" + _machine() if per_pc else "")).encode()


def _body(obj):
    return json.dumps({k: v for k, v in obj.items() if k != "_sig"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign(obj, purpose, per_pc=False):
    out = dict(obj)
    out["_sig"] = hmac.new(_key(purpose, per_pc), _body(obj), hashlib.sha256).hexdigest()
    return out


def valid(obj, purpose, per_pc=False):
    if not isinstance(obj, dict) or not obj.get("_sig"):
        return False
    good = hmac.new(_key(purpose, per_pc), _body(obj), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(obj["_sig"]), good)


# ---- a copy in the registry, so deleting one file does not clear a block ----
def reg_get(name):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\NAB")
        try:
            return str(winreg.QueryValueEx(k, name)[0])
        finally:
            winreg.CloseKey(k)
    except Exception:
        return ""


def reg_set(name, value):
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\NAB")
        try:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(k)
        return True
    except Exception:
        return False
