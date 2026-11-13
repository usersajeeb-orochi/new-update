# nab_remote.py - the PC's side of the cloud relay: signed calls, approval answers, live screen view, Riko questions.
#
# Telegram lets only ONE program read button taps for a token, so PCs never poll Telegram any more: the cloud bot reads
# the taps and the PC asks the cloud for them. All message sending still goes straight from the PC.
import hashlib
import hmac
import io
import json
import logging
import threading
import time
import urllib.parse as _up
import urllib.request as _rq

import nab_secrets


def cloud_url():
    try:
        import nab_connections
        return (nab_connections.cloud_url() or "").rstrip("/")
    except Exception:
        return ""


def sign_headers(pc):
    """HMAC of 'pc|timestamp' with the build's sign_key. The server checks it only when NAB_PC_SECRET is set there."""
    key = (nab_secrets.get("sign_key") or "").encode()
    ts = str(int(time.time()))
    return {"X-NAB-Ts": ts, "X-NAB-Sig": hmac.new(key, f"{pc}|{ts}".encode(), hashlib.sha256).hexdigest()} if key else {}


def available():
    return bool(cloud_url())


def get_decision(rid, pc):
    """-> (action, who) once somebody tapped the button for this request id, else None."""
    u = cloud_url()
    if not u:
        return None
    try:
        req = _rq.Request(f"{u}/pc/decision?" + _up.urlencode({"rid": rid, "pc": pc}), headers=sign_headers(pc))
        j = json.loads(_rq.urlopen(req, timeout=10).read().decode())
        return (j["d"], j.get("who") or "Someone") if j.get("d") else None
    except Exception as e:
        logging.error(f"get_decision: {e}")
        return None


# ---------------------------------------------------------------- live screen view
class Live:
    """One live view at a time. The picture is ONE Telegram message that is edited in place, so there is nothing to scroll."""
    ZOOMS = {"full": None, "tl": (0, 0, .5, .5), "tr": (.5, 0, 1, .5), "bl": (0, .5, .5, 1), "br": (.5, .5, 1, 1), "mid": (.25, .25, .75, .75)}

    def __init__(self, tg, pc):
        self.tg, self.pc = tg, pc          # tg = nab_telegram module
        self.on = False
        self.chat = ""
        self.mid = None
        self.every = 3.0
        self.zoom = "full"
        self.last = ""
        self.t = None
        self.app = None
        self.started = 0

    def keyboard(self):
        k = lambda label, a: {"text": label, "callback_data": f"nabL|{self.pc}|{a}"}
        return json.dumps({"inline_keyboard": [
            [k("Full", "z_full"), k("Top left", "z_tl"), k("Top right", "z_tr")],
            [k("Centre", "z_mid"), k("Bottom left", "z_bl"), k("Bottom right", "z_br")],
            [k("Faster", "faster"), k("Slower", "slower"), k("Snapshot", "snap")],
            [k("Pause NAB", "pause"), k("Resume NAB", "resume"), k("Lock screen", "lock")],
            [k("Stop live view", "stop")]]})

    def _frame(self):
        from PIL import ImageGrab
        im = ImageGrab.grab()
        box = self.ZOOMS.get(self.zoom)
        if box:
            w, h = im.size
            im = im.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))
        if im.width > 1600:
            im = im.resize((1600, int(im.height * 1600 / im.width)))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=62)
        return b.getvalue()

    def _caption(self):
        return f"{self.pc}  {time.strftime('%H:%M:%S')}  view: {self.zoom}  every {self.every:g}s"

    def _multipart(self, method, fields, photo):
        bd = "----NABLive"
        body = b""
        for k, v in fields.items():
            body += f'--{bd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body += f'--{bd}\r\nContent-Disposition: form-data; name="photo"; filename="s.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() + photo + f"\r\n--{bd}--\r\n".encode()
        req = _rq.Request(f"{self.tg.TG_API}/{method}", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
        return json.loads(_rq.urlopen(req, timeout=25, context=self.tg._SSL_CTX).read())

    def start(self, chat_id, app=None):
        if self.on:
            self.send_event("snap")
            return
        self.chat, self.app, self.on, self.started = str(chat_id), app, True, time.time()
        self.t = threading.Thread(target=self._loop, daemon=True, name="live-view")
        self.t.start()

    def stop(self, why="Live view stopped."):
        if not self.on:
            return
        self.on = False
        try:
            self.tg._tg_send(f"{why} ({self.pc})", chat_id=self.chat)
        except Exception:
            pass

    def send_event(self, ev):
        """A button under the picture was tapped (the cloud relays it as EVT|<name>)."""
        if ev.startswith("z_") and ev[2:] in self.ZOOMS:
            self.zoom, self.last = ev[2:], ""
        elif ev == "faster":
            self.every = max(1.5, self.every - 1)
        elif ev == "slower":
            self.every = min(15, self.every + 2)
        elif ev == "snap":
            self.last = ""
        elif ev == "stop":
            self.stop()
        elif ev in ("pause", "resume") and self.app:
            try:
                self.app.after(0, self.app._on_pause if ev == "pause" else self.app._on_resume)
                self.tg._tg_send(("Paused" if ev == "pause" else "Resumed") + f" NAB on {self.pc}.", chat_id=self.chat)
            except Exception as e:
                logging.error(f"live {ev}: {e}")
        elif ev == "lock":
            lock_screen()
            self.tg._tg_send(f"Screen of {self.pc} locked.", chat_id=self.chat)

    def _loop(self):
        fails = 0
        while self.on:
            try:
                if time.time() - self.started > 1800:                 # never left running by accident
                    self.stop("Live view ended after 30 minutes.")
                    break
                fr = self._frame()
                h = hashlib.md5(fr).hexdigest()
                if h != self.last:
                    self.last = h
                    if self.mid is None:
                        r = self._multipart("sendPhoto", {"chat_id": self.chat, "caption": self._caption(), "reply_markup": self.keyboard()}, fr)
                        self.mid = (r.get("result") or {}).get("message_id")
                    else:
                        media = json.dumps({"type": "photo", "media": "attach://photo", "caption": self._caption()})
                        self._multipart("editMessageMedia", {"chat_id": self.chat, "message_id": self.mid, "media": media, "reply_markup": self.keyboard()}, fr)
                fails = 0
            except Exception as e:
                fails += 1
                logging.error(f"live view: {self.tg._tg_error_detail(e)}")
                if fails >= 5:
                    self.stop("Live view stopped: Telegram would not take the picture.")
                    break
            end = time.time() + self.every
            while self.on and time.time() < end:
                time.sleep(.25)


def lock_screen():
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return True
    except Exception as e:
        logging.error(f"lock_screen: {e}")
        return False


# ---------------------------------------------------------------- Riko over Telegram
def ask_riko(tg, app, chat_id, question):
    """Answer a /ask question from the archive with the same assistant as the app. Runs in a thread; never raises."""
    def run():
        try:
            import nab_tools
            out = nab_tools.get("ai", app).brain.chat([], question)
            reply = out.get("reply") if isinstance(out, dict) else str(out)
            if isinstance(out, dict) and out.get("confirm"):
                reply = (reply or "") + "\n\nThis needs a button press in the app, so I did not run it from Telegram."
            tg._tg_send((reply or "Riko could not answer that right now.")[:3800], chat_id=chat_id)
        except Exception as e:
            logging.exception("ask_riko")
            tg._tg_send("Could not answer: " + str(e)[:200], chat_id=chat_id)
    threading.Thread(target=run, daemon=True, name="ask-riko").start()
