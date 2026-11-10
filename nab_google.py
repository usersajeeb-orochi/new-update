# nab_google.py - "Sign in with Google" for the NAB desktop app (free; Google's installed-app flow with PKCE).
#
# NAB opens the normal browser at Google's sign-in page.  Google sends the browser back to a tiny one-shot web server
# on 127.0.0.1, NAB swaps the code for an ID token, asks Google to confirm the token, and gets a verified email.
# The email is then matched to a NAB account (Settings > Accounts > Google email).  No password is typed in NAB.
# Needs a free "Desktop app" OAuth client from Google Cloud Console (Settings > Connections > Google sign-in).
import os
import json
import time
import base64
import socket
import hashlib
import secrets
import logging
import threading
import webbrowser
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

DOC = os.path.join(os.path.expanduser("~"), "Documents")
CFG = os.path.join(DOC, "nab_google.json")
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
INFO = "https://oauth2.googleapis.com/tokeninfo"
WAIT = 180
BUILTIN = {"client_id": "", "client_secret": ""}      # fill in once, or set it in Settings
_state = {"s": "idle", "email": "", "name": "", "error": "", "ts": 0}
_lock = threading.Lock()


def config():
    d = dict(BUILTIN)
    try:
        with open(CFG, encoding="utf-8") as f:
            j = json.load(f)
        for k in d:
            if str(j.get(k) or "").strip():
                d[k] = str(j[k]).strip()
    except Exception:
        pass
    return d


def save_config(client_id, client_secret=None):
    """client_secret=None keeps the saved secret."""
    old = config()
    os.makedirs(DOC, exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump({"client_id": (client_id or "").strip(), "client_secret": old["client_secret"] if client_secret is None else (client_secret or "").strip()}, f)


def configured():
    return bool(config()["client_id"])


def _pkce():
    v = secrets.token_urlsafe(64)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def verify_id_token(idt, client_id, http=None):
    """Ask Google to validate the token. -> (email, "") or ("", reason)"""
    try:
        import requests
        r = (http or requests).get(INFO, params={"id_token": idt}, timeout=15)
        j = r.json()
    except Exception as e:
        return "", "Could not reach Google: " + str(e)[:80]
    if j.get("aud") != client_id:
        return "", "Google answered for a different app."
    if str(j.get("email_verified")).lower() != "true" or not j.get("email"):
        return "", "That Google email is not verified."
    _state["name"] = str(j.get("name") or "")[:40]
    return str(j["email"]).strip().lower(), ""


def begin():
    """Start one sign-in. The browser opens; poll() reports the result."""
    cfg = config()
    if not cfg["client_id"]:
        return {"ok": False, "error": "Google sign-in is not set up yet. Add the client ID in Settings > Accounts > Google sign-in."}
    with _lock:
        if _state["s"] == "wait" and time.time() - _state["ts"] < WAIT:
            return {"ok": True, "again": True}
        _state.update(s="wait", email="", error="", ts=time.time())
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    srv_box = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q and "error" not in q:
                self.send_response(404)
                self.end_headers()
                return
            ok = q.get("state", [""])[0] == state and "code" in q
            body = ("<html><body style='font-family:sans-serif;padding:40px'><h2>" + ("Signed in. You can close this tab and return to NAB." if ok else "Sign-in was not completed.") + "</h2></body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            srv_box["q"] = q if ok else {"error": [q.get("error", ["cancelled"])[0]]}
            srv_box["done"] = True

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    redirect = f"http://127.0.0.1:{port}"
    try:
        httpd = HTTPServer(("127.0.0.1", port), H)
    except Exception as e:
        _state.update(s="error", error="Could not open a local port: " + str(e)[:60])
        return {"ok": False, "error": _state["error"]}

    def run():
        try:
            httpd.timeout = 1
            end = time.time() + WAIT
            while not srv_box.get("done") and time.time() < end:
                httpd.handle_request()
            q = srv_box.get("q")
            if not q:
                return _fail("Sign-in timed out. Try again.")
            if "error" in q:
                return _fail("Google sign-in was cancelled.")
            import requests
            r = requests.post(TOKEN, data={"code": q["code"][0], "client_id": cfg["client_id"], "client_secret": cfg["client_secret"], "redirect_uri": redirect,
                                           "grant_type": "authorization_code", "code_verifier": verifier}, timeout=20)
            j = r.json()
            if "id_token" not in j:
                return _fail("Google refused the sign-in: " + str(j.get("error_description") or j.get("error") or "unknown")[:80])
            email, why = verify_id_token(j["id_token"], cfg["client_id"])
            if not email:
                return _fail(why)
            _state.update(s="ok", email=email, error="")
        except Exception as e:
            logging.error(f"google signin: {e}")
            _fail("Google sign-in failed: " + str(e)[:80])
        finally:
            try:
                httpd.server_close()
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()
    url = AUTH + "?" + urllib.parse.urlencode({"client_id": cfg["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": "openid email",
                                               "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"})
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return {"ok": True, "url": url}


def _fail(msg):
    _state.update(s="error", error=msg)


def poll(consume=True):
    with _lock:
        r = {"state": _state["s"], "email": _state["email"], "name": _state["name"], "error": _state["error"]}
        if consume and _state["s"] in ("ok", "error"):
            _state.update(s="idle", email="", name="", error="")
    return r
