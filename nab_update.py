# nab_update.py — GitHub auto-update system
import os
import sys
import json
import time
import logging
import subprocess
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
from nab_constants import *
import nab_constants as _nab_constants_mod
globals().update({k: v for k, v in vars(_nab_constants_mod).items() if not k.startswith('__')})
from nab_telegram import *
import nab_telegram as _nab_telegram_mod
globals().update({k: v for k, v in vars(_nab_telegram_mod).items() if not k.startswith('__')})

GITHUB_REPO          = "usersajeeb-orochi/new-update"
GITHUB_TOKEN         = ""      # leave empty for public repos
GITHUB_CHECK_INTERVAL = 300    # seconds between checks (5 min)

_nab_app_ref = None

def _ver(v):
    try: return tuple(int(x) for x in str(v).strip().split("."))
    except: return (0,)

def _is_frozen():
    return getattr(sys, "frozen", False)

def _current_exe():
    if _is_frozen():
        return sys.executable
    # NOTE: __file__ here would resolve to this module's own path
    # (nab_update.py), not the actual entry script — use sys.argv[0],
    # which reflects however the app was actually launched (NAB_entry.pyw).
    return os.path.abspath(sys.argv[0])

def _github_headers():
    h = {"User-Agent": "NAB/" + APP_VERSION, "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = "Bearer " + GITHUB_TOKEN
    return h

def _github_get_latest_release():
    """Fetch latest GitHub release. Returns (version_str, download_url) or (None, None)."""
    if not GITHUB_REPO:
        return None, None
    try:
        url  = "https://api.github.com/repos/" + GITHUB_REPO + "/releases/latest"
        req  = _urllib_req.Request(url, headers=_github_headers())
        resp = _urllib_req.urlopen(req, context=_SSL_CTX, timeout=10)
        data = json.loads(resp.read().decode())
        tag  = data.get("tag_name", "").lstrip("v")
        want = "NAB_win.zip" if _is_frozen() else "NAB_entry.pyw"
        dl_url = None
        for asset in data.get("assets", []):
            if asset["name"].lower() == want.lower():
                dl_url = asset["browser_download_url"]
                break
        if not dl_url and not _is_frozen():
            for asset in data.get("assets", []):
                if asset["name"].lower().endswith(".pyw"):
                    dl_url = asset["browser_download_url"]
                    break
        return tag, dl_url
    except Exception as e:
        logging.error("_github_get_latest_release: " + str(e))
        return None, None

def _github_download_silently(download_url, dest_path, progress_cb=None):
    """Download new EXE to dest_path. Called in background thread.
    Returns (True, None) on success or (False, error_str) on failure."""
    try:
        req  = _urllib_req.Request(download_url, headers=_github_headers())
        resp = _urllib_req.urlopen(req, context=_SSL_CTX, timeout=120)
        total    = int(resp.headers.get("Content-Length", 0))
        chunks   = []
        received = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
            if progress_cb and total:
                progress_cb(int(received / total * 100))
        new_bytes = b"".join(chunks)
        if len(new_bytes) < 10000:
            raise ValueError("Downloaded file too small (" + str(len(new_bytes)) + " bytes)")
        with open(dest_path, "wb") as f:
            f.write(new_bytes)
        return True, None
    except Exception as e:
        logging.error("_github_download_silently: " + str(e))
        return False, str(e)

def _app_dir():
    return os.path.dirname(_current_exe())

def _update_zip_path():
    """Where the downloaded update package is kept (inside the install folder)."""
    d = os.path.join(_app_dir(), "_update")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "NAB_win.zip")

def _extract_update(zip_path):
    """Unpack the package next to the app and return the folder that holds NAB.exe."""
    import zipfile, shutil
    out = os.path.join(os.path.dirname(zip_path), "new")
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None:
            raise ValueError("update package is damaged")
        z.extractall(out)
    root = out
    if not os.path.exists(os.path.join(root, "NAB.exe")):
        subs = [x for x in os.listdir(out) if os.path.isdir(os.path.join(out, x))]
        if len(subs) == 1 and os.path.exists(os.path.join(out, subs[0], "NAB.exe")):
            root = os.path.join(out, subs[0])
    if not os.path.exists(os.path.join(root, "NAB.exe")) or not os.path.isdir(os.path.join(root, "_internal")):
        raise ValueError("update package is incomplete (NAB.exe / _internal missing)")
    return root

def _apply_update_and_restart(current_exe, new_path):
    """Unpack the downloaded package, then start a copy of nab_updater.exe (from the
    temp folder, so it can replace itself too) and exit. The helper waits for NAB to
    close, swaps the files, and reopens NAB. Needed because Windows locks running files."""
    import shutil, tempfile
    app_dir = os.path.dirname(current_exe)
    try:
        if str(new_path).lower().endswith(".zip"):
            new_dir = _extract_update(new_path)
        else:
            new_dir = new_path            # legacy single-file update
        src = os.path.join(app_dir, "nab_updater.exe")
        if not os.path.exists(src):
            logging.error("nab_updater.exe not found at: " + src)
            return False
        run = os.path.join(tempfile.gettempdir(), "NAB_updater_run.exe")
        shutil.copy2(src, run)
        pid = str(os.getpid())
        subprocess.Popen([run, app_dir if os.path.isdir(new_dir) else current_exe, new_dir, pid])
        time.sleep(0.3)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        logging.error("_apply_update_and_restart: " + str(e))
        return False


def _cloud_heartbeat_post(app_version):
    """POST heartbeat to cloud bot (kept for Telegram bot commands)."""
    cloud_url = _get_cloud_url()
    if not cloud_url:
        return []
    try:
        data = _urllib_parse.urlencode({"pc": PC_NAME, "version": app_version}).encode()
        req  = _urllib_req.Request(f"{cloud_url}/heartbeat", data=data, method="POST")
        resp = _urllib_req.urlopen(req, context=_SSL_CTX, timeout=10)
        return json.loads(resp.read().decode()).get("commands", [])
    except Exception as e:
        logging.error(f"_cloud_heartbeat_post: {e}")
        return []

# ─────────────────────────────────────────────
# ACCESS LOG & BLOCKED PC MANAGEMENT
# ─────────────────────────────────────────────
