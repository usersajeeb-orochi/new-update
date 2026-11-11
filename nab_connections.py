# nab_connections.py — every connection NAB needs, built in.
#
# Nobody has to configure anything on a PC. The values below are the defaults;
# Settings → Advanced → Connections can override them for one PC, and
# "Reset to built-in" removes the override again.
#
# Overrides live in HKCU\Software\NAB (same key the app already uses).
import os
import sys
import logging

REG_KEY = r"Software\NAB"

# ── Built-in defaults ─────────────────────────────────────────────────────────
BUILTIN_CLOUD_URL = "https://nab-cloud-bot.onrender.com"
BUILTIN_DRIVE_FOLDER_ID = "1P_yDdQrOoTnWwueOMdqfwst2v2uFRyd2"
BUILTIN_SHEET_ID = "1wuFSBKyw0vIDlWshuMEY8yG8ijdZWxFWs44NtJk0jyo"

# The Google service-account key is bundled into the EXE by BUILD.bat.
# Either file name works; BUILD.bat adds whichever one sits next to it.
BUNDLED_KEY_NAMES = ("nab-bot-498413-3ae32f0a2eec.json", "nab_gdrive_creds.json")

# override name -> registry value
_REG = {
    "cloud_url": "CloudURL",
    "drive_folder_id": "DriveFolderID",
    "sheet_id": "gs_sheet_id",
    "google_key_path": "GoogleKeyPath",
    "telegram_token": "TGToken",
}


# The Tracker keeps its Sheet ID in its own registry subkey; share that value
# so the Tracker window and Advanced always agree.
_SUBKEY = {"gs_sheet_id": r"Software\NAB\Tracker"}


def _reg_read(name):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY.get(name, REG_KEY))
        try:
            v, _ = winreg.QueryValueEx(k, name)
        finally:
            winreg.CloseKey(k)
        return (v or "").strip()
    except Exception:
        return ""


def _reg_write(name, value):
    try:
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SUBKEY.get(name, REG_KEY))
        try:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(k)
        return True
    except Exception as e:
        logging.error(f"nab_connections reg write {name}: {e}")
        return False


def _reg_delete(name):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SUBKEY.get(name, REG_KEY), 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(k, name)
        finally:
            winreg.CloseKey(k)
    except Exception:
        pass


def override(which):
    """The per-PC override for 'which', or '' when this PC uses the built-in."""
    return _reg_read(_REG[which])


def set_override(which, value):
    """Store an override. An empty value, or a value equal to the built-in
    default, removes the override so future app updates can change the default."""
    value = (value or "").strip()
    if which == "cloud_url":
        value = value.rstrip("/")
    if not value or value == _builtin(which):
        _reg_delete(_REG[which])
        return True
    return _reg_write(_REG[which], value)


def reset_all():
    for name in _REG.values():
        _reg_delete(name)


def _builtin(which):
    return {
        "cloud_url": BUILTIN_CLOUD_URL,
        "drive_folder_id": BUILTIN_DRIVE_FOLDER_ID,
        "sheet_id": BUILTIN_SHEET_ID,
    }.get(which, "")


# ── Effective values ──────────────────────────────────────────────────────────
def cloud_url():
    return (override("cloud_url") or os.environ.get("NAB_CLOUD_URL", "")
            or BUILTIN_CLOUD_URL).rstrip("/")


def drive_folder_id():
    return override("drive_folder_id") or BUILTIN_DRIVE_FOLDER_ID


def sheet_id():
    return override("sheet_id") or BUILTIN_SHEET_ID


def _bundle_dirs():
    dirs = []
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        dirs.append(mp)
    dirs.append(os.path.dirname(os.path.abspath(__file__)))
    return dirs


def bundled_key():
    """Path of the Google key packed inside this EXE (or next to the source)."""
    for d in _bundle_dirs():
        for n in BUNDLED_KEY_NAMES:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return ""


def google_key_file():
    """Google service-account key: per-PC override → bundled → legacy locations."""
    p = override("google_key_path")
    if p and os.path.isfile(p):
        return p
    p = bundled_key()
    if p:
        return p
    home = os.path.expanduser("~")
    legacy = [
        os.path.join(home, "Documents", "nab_gdrive_creds.json"),
        os.path.join(home, "Documents", "Automation", "nab_gdrive_creds.json"),
        os.path.join(home, "nab_gdrive_creds.json"),
        os.path.join(os.getcwd(), "nab_gdrive_creds.json"),
    ]
    for p in legacy:
        if os.path.isfile(p):
            return p
    return ""


def summary():
    """Plain-text status lines for the Advanced dialog."""
    key = google_key_file()
    return {
        "key_ok": bool(key),
        "key_source": ("custom file" if override("google_key_path") and key == override("google_key_path")
                       else "built into NAB" if key and key == bundled_key()
                       else "found on this PC" if key else "missing"),
        "customized": [k for k in _REG if override(k)],
    }
