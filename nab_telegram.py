# nab_telegram.py — Telegram bot config + send/receive helpers
#
# The Telegram bot token is built in, as in earlier versions, so a fresh PC
# works with no setup. A per-PC registry value (HKCU\Software\NAB\TGToken)
# or the broker, when present, takes precedence — that lets you rotate the
# token later without rebuilding the EXE.
import os
import sys
import json
import ssl
import socket
import logging
import urllib.request as _urllib_req
import urllib.parse as _urllib_parse
from PIL import Image, ImageGrab

try:
    import nab_broker_client as _broker
except ImportError:
    _broker = None

REG_KEY = r"Software\NAB"


def _reg_get(name, default=""):
    """Read a value from Windows registry."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return val or default
    except Exception:
        return default


def _reg_set(name, value):
    """Write a value to Windows registry permanently."""
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logging.error(f"_reg_set {name}: {e}")
        return False


def _broker_enabled():
    # Settings sync uses the broker too, but that must NOT silently reroute
    # Telegram through it — Telegram stays direct (built-in token) unless this
    # PC is explicitly opted in with registry value BrokerTelegram=1.
    return (_broker is not None and _broker.broker_enabled()
            and _reg_get("BrokerTelegram", "") == "1")


_BUILTIN_BOT_TOKEN = "8737601809:AAFOcuApledbL4XwDMNt0AR2zjnTj7_EQV0"
TG_GROUP_LINK = _reg_get("TGGroupLink", "https://t.me/+cMLBGanlKVphNmQ1")
TG_BOT_TOKEN  = _reg_get("TGToken", "") or _BUILTIN_BOT_TOKEN
TG_CHAT_ID    = _reg_get("TGChatID", "7020459302")
TG_GROUP_CHAT_ID = _reg_get("TGGroupChatID", "-1004457803996")
TG_API        = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
AUTH_TIMEOUT  = 120
ALLOWED_HOURS = None
PC_NAME       = socket.gethostname()

# Real certificate verification — the previous unverified context accepted
# ANY certificate on this connection, which is also the connection that
# pushes executable update code to this PC (see nab_update.py). That was a
# leftover workaround for a PyInstaller certifi-path issue that NAB_CONTEXT.md
# shows was already fixed properly elsewhere (SSL_CERT_FILE at startup).
_SSL_CTX = ssl.create_default_context()

def _tg_error_detail(e):
    """Extract Telegram's actual error description from an HTTPError's
    response body (e.g. 'chat not found', 'bot was kicked from the group
    chat', 'have no rights to send a message') instead of just the generic
    HTTP status code, which alone doesn't say why a call failed."""
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read().decode('utf-8', errors='replace')
            return f"{e} — {body}"
        except Exception:
            return str(e)
    return str(e)

# ── LOW-LEVEL HELPERS ──────────────────────────────────────────────────────

def _tg_send(text, chat_id=None):
    if _broker_enabled():
        _broker.tg_send(text, chat_id)
        return
    try:
        cid    = chat_id or TG_CHAT_ID
        params = _urllib_parse.urlencode({"chat_id": cid, "text": text, "parse_mode": "HTML"})
        _urllib_req.urlopen(f"{TG_API}/sendMessage?{params}", context=_SSL_CTX, timeout=10)
    except Exception as e:
        logging.error(f"_tg_send: {_tg_error_detail(e)}")

def _tg_send_photo(img_bytes, caption="", chat_id=None):
    if _broker_enabled():
        _broker.tg_send_photo(img_bytes, caption, chat_id)
        return
    try:
        cid      = chat_id or TG_CHAT_ID
        boundary = "----NABBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{cid}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="screen.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = _urllib_req.Request(
            f"{TG_API}/sendPhoto", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        _urllib_req.urlopen(req, timeout=15, context=_SSL_CTX)
    except Exception as e:
        logging.error(f"_tg_send_photo: {_tg_error_detail(e)}")

def _tg_send_document(file_bytes, filename, caption="", chat_id=None):
    # NOT YET broker-routed — the server (nab_broker_server.py) has no
    # /v1/telegram/send_document endpoint yet. This still uses TG_BOT_TOKEN
    # directly, so on a broker-migrated PC (empty TG_BOT_TOKEN) this call
    # will simply fail rather than silently leaking anything — but it means
    # this one path isn't protected yet. Add the endpoint (same shape as
    # send_photo) before relying on this in a fully broker-only deployment.
    try:
        cid      = chat_id or TG_CHAT_ID
        boundary = "----NABDocBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{cid}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = _urllib_req.Request(
            f"{TG_API}/sendDocument", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        _urllib_req.urlopen(req, timeout=30, context=_SSL_CTX)
    except Exception as e:
        logging.error(f"_tg_send_document: {_tg_error_detail(e)}")

def _tg_get_updates(offset=None, timeout=30):
    if _broker_enabled():
        # The broker owns the real long-poll to Telegram centrally — this PC
        # just drains its own queue, which is cheap, so `offset` (a raw-
        # getUpdates concept) doesn't apply here.
        return {"result": _broker.tg_poll_updates()}
    try:
        params = {
            "timeout": timeout,
            # Explicit on every call — Telegram remembers whatever
            # allowed_updates list was last used (even from an unrelated
            # tool/test) and keeps silently applying it to future calls
            # that don't specify one. Without this, a stray earlier call
            # that restricted to "message" only would make every button
            # tap (callback_query) vanish with no visible error.
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        if offset is not None:
            params["offset"] = offset
        url  = f"{TG_API}/getUpdates?" + _urllib_parse.urlencode(params)
        resp = _urllib_req.urlopen(url, context=_SSL_CTX, timeout=timeout + 5)
        return json.loads(resp.read())
    except Exception as e:
        logging.error(f"_tg_get_updates: {_tg_error_detail(e)}")
        return {}

def _tg_drain_queue():
    """Drain all pending updates on startup so auth polling starts clean."""
    if _broker_enabled():
        _broker.tg_poll_updates()
        return
    try:
        au_param = _urllib_parse.urlencode({"allowed_updates": json.dumps(["message", "callback_query"])})
        resp    = _urllib_req.urlopen(f"{TG_API}/getUpdates?timeout=0&{au_param}", context=_SSL_CTX, timeout=8)
        results = json.loads(resp.read()).get("result", [])
        if results:
            last_id = results[-1]["update_id"]
            params  = _urllib_parse.urlencode({"offset": last_id + 1, "timeout": 0,
                                                "allowed_updates": json.dumps(["message", "callback_query"])})
            _urllib_req.urlopen(f"{TG_API}/getUpdates?{params}", context=_SSL_CTX, timeout=8)
    except Exception as e:
        logging.error(f"_tg_drain_queue: {_tg_error_detail(e)}")

def _take_screenshot():
    try:
        import io
        buf = io.BytesIO()
        ImageGrab.grab().save(buf, format="JPEG", quality=60)
        return buf.getvalue()
    except Exception:
        return None

def _tg_send_inline_buttons(text, buttons, chat_id=None):
    """Send a message with inline URL buttons. buttons = list of (label, url) tuples."""
    # NOT YET broker-routed — same caveat as _tg_send_document above.
    try:
        cid      = chat_id or TG_CHAT_ID
        keyboard = json.dumps({"inline_keyboard": [[{"text": l, "url": u} for l, u in buttons]]})
        params   = _urllib_parse.urlencode({
            "chat_id":      cid,
            "text":         text,
            "parse_mode":   "HTML",
            "reply_markup": keyboard
        })
        _urllib_req.urlopen(f"{TG_API}/sendMessage?{params}", context=_SSL_CTX, timeout=10)
    except Exception as e:
        logging.error(f"_tg_send_inline_buttons: {_tg_error_detail(e)}")
        _tg_send(text, chat_id=chat_id)  # fallback to plain text

def _tg_send_callback_buttons(text, buttons, chat_id=None):
    """Send a message with real inline callback buttons — buttons = list of
    (label, callback_data) tuples. Unlike URL deep-link buttons, these work
    correctly for ANY user who taps them (including in a group), because
    Telegram delivers a callback_query event straight to the bot rather than
    opening a separate DM with whoever tapped it.
    Returns the sent message_id (or None on failure) so the caller can edit
    the message later to show the outcome."""
    if _broker_enabled():
        return _broker.tg_send_callback_buttons(text, buttons, chat_id)
    try:
        cid      = chat_id or TG_CHAT_ID
        keyboard = json.dumps({"inline_keyboard": [[
            {"text": l, "callback_data": d} for l, d in buttons
        ]]})
        params   = _urllib_parse.urlencode({
            "chat_id":      cid,
            "text":         text,
            "parse_mode":   "HTML",
            "reply_markup": keyboard
        })
        resp = _urllib_req.urlopen(f"{TG_API}/sendMessage?{params}", context=_SSL_CTX, timeout=10)
        result = json.loads(resp.read())
        return result.get("result", {}).get("message_id")
    except Exception as e:
        logging.error(f"_tg_send_callback_buttons: {_tg_error_detail(e)}")
        _tg_send(text, chat_id=chat_id)  # fallback to plain text
        return None

def _tg_answer_callback_query(callback_query_id, text=""):
    """Acknowledge a button tap — stops the tapping user's client from
    showing an infinite loading spinner on the button, and can show a
    small toast popup."""
    if _broker_enabled():
        _broker.tg_answer_callback_query(callback_query_id, text)
        return
    try:
        params = _urllib_parse.urlencode({
            "callback_query_id": callback_query_id,
            "text": text,
        })
        _urllib_req.urlopen(f"{TG_API}/answerCallbackQuery?{params}", context=_SSL_CTX, timeout=10)
    except Exception as e:
        logging.error(f"_tg_answer_callback_query: {_tg_error_detail(e)}")

def _tg_edit_message(chat_id, message_id, text):
    """Edit an already-sent message — used to update the login-request
    message in place (e.g. to '✅ Approved by Alice') once someone acts on
    it, instead of leaving a stale button and posting a separate reply."""
    if _broker_enabled():
        _broker.tg_edit_message(chat_id, message_id, text)
        return
    try:
        params = _urllib_parse.urlencode({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        })
        _urllib_req.urlopen(f"{TG_API}/editMessageText?{params}", context=_SSL_CTX, timeout=10)
    except Exception as e:
        logging.error(f"_tg_edit_message: {_tg_error_detail(e)}")

# ── CLOUD BOT HEARTBEAT (file/upload commands only) ────────────────────────
# The NAB local bot owns getUpdates — the cloud bot uses a DIFFERENT token.
# NAB still sends heartbeats to the cloud bot's Flask server so the cloud bot
# knows which PCs are online and can queue file/upload commands for them.

# ─────────────────────────────────────────────
# PERSISTENT CONFIG — reads from registry first,
# falls back to env var. Clients never need to
# set environment variables manually.
# (_reg_get/_reg_set now defined at the top of this file, next to
# TG_BOT_TOKEN, since they're needed earlier than they used to be.)
# ─────────────────────────────────────────────

def _get_cloud_url():
    """Get cloud URL from registry, then env var, then empty."""
    import nab_connections
    return nab_connections.cloud_url()

# ─────────────────────────────────────────────────────────────────────────────
# GITHUB AUTO-UPDATE
# ─────────────────────────────────────────────────────────────────────────────
# How it works (3 steps):
#   1. GITHUB_REPO (nab_update.py) points at your GitHub repo.
#   2. Every GITHUB_CHECK_INTERVAL seconds, NAB calls the GitHub Releases
#      API (_github_get_latest_release in nab_update.py) and compares the
#      release tag against APP_VERSION (nab_constants.py).
#   3. If GitHub has a newer version → downloads the NAB.exe/nab_updater.exe
#      release assets → full-screen lock screen → restarts via nab_updater.exe.
#
# To push an update:
#   1. Bump APP_VERSION in nab_constants.py  (e.g. "2.0.0" → "2.1.0")
#   2. Run BUILD.bat → produces NAB.exe + nab_updater.exe
#   3. GitHub → Releases → Draft new release → tag it to match (e.g. v2.1.0)
#      → upload both NAB.exe and nab_updater.exe as release assets → Publish
#   4. Every running NAB will detect it within GITHUB_CHECK_INTERVAL.
# ─────────────────────────────────────────────────────────────────────────────

