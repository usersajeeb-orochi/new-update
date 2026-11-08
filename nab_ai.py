# nab_ai.py — one small Groq client used by every NAB feature that needs AI.
#
#  * OpenAI-compatible HTTPS calls with urllib (no extra package)
#  * a LIST of API keys: when one is rate-limited (429) or refused (401/403) the next one is used,
#    the limited key rests for the time Groq asks for
#  * models are looked up from Groq's own /models list, so a retired model name never breaks the app
#  * everything fails soft: callers get  (None, "friendly reason")  and carry on without AI
#
# Settings live in  Documents\nab_ai.json  and are edited in Settings > AI.
import os
import re
import json
import time
import base64
import logging
import threading
import urllib.request
import urllib.error

import nab_engine

BASE = os.environ.get("NAB_AI_BASE") or "https://api.groq.com/openai/v1"
FILE = os.path.join(nab_engine.DOC_DIR, "nab_ai.json")
BRAIN = os.path.join(nab_engine.DOC_DIR, "nab_riko_brain.json")

# built-in free keys (can be replaced / extended in Settings > AI without an update)
DEFAULT_KEYS = [
    "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",
    "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",
    "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",
    "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",
]
DEFAULTS = {"enabled": True, "keys": [], "use_builtin": True, "text_model": "llama-3.3-70b-versatile",
            "fast_model": "llama-3.1-8b-instant", "vision_model": "", "whisper_model": "whisper-large-v3-turbo"}
VISION_HINTS = ("llama-4-scout", "llama-4-maverick", "vision", "-vl", "pixtral")


class AI:
    def __init__(self):
        self.lock = threading.RLock()
        self.cool = {}                 # key -> time it may be used again
        self.models = None
        self.models_t = 0
        self.cfg = self._load()
        self.last_error = ""

    # ------------------------------------------------------------ settings
    def _load(self):
        d = dict(DEFAULTS)
        try:
            with open(FILE, encoding="utf-8") as f:
                d.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except Exception:
            pass
        return d

    def save(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if k in DEFAULTS:
                    if k == "keys":
                        v = [x.strip() for x in (v if isinstance(v, list) else re.split(r"[\s,]+", str(v))) if x.strip()]
                    elif k in ("enabled", "use_builtin"):
                        v = bool(v)
                    self.cfg[k] = v
            try:
                tmp = FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.cfg, f)
                os.replace(tmp, FILE)
            except Exception as e:
                logging.error(f"ai save: {e}")
            if "vision_model" in kw or "text_model" in kw:
                self.models = None

    def keys(self):
        ks = list(self.cfg.get("keys") or [])
        if self.cfg.get("use_builtin", True):
            ks += [k for k in DEFAULT_KEYS if k not in ks]
        return ks

    def ready(self):
        return bool(self.cfg.get("enabled", True) and self.keys())

    # ------------------------------------------------------------ http
    def _request(self, path, body=None, raw=None, ctype="application/json", method=None, timeout=45):
        """Try every key until one answers.  Returns (json, "") or (None, reason)."""
        if not self.cfg.get("enabled", True):
            return None, "AI is switched off in Settings."
        keys = self.keys()
        if not keys:
            return None, "No API key set (Settings > AI)."
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        reason = ""
        for attempt in range(2):                       # second pass after the shortest rest
            now = time.time()
            order = sorted(keys, key=lambda k: self.cool.get(k, 0))
            usable = [k for k in order if self.cool.get(k, 0) <= now]
            if not usable:
                wait = min(self.cool.get(k, 0) for k in keys) - now
                if wait > 12 or attempt:
                    return None, f"All keys are busy (rate limit). Try again in {int(wait) + 1}s."
                time.sleep(max(wait, 0) + .2)
                usable = [k for k in order if self.cool.get(k, 0) <= time.time()]
            for k in usable:
                req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                             headers={"Authorization": "Bearer " + k, "Content-Type": ctype, "User-Agent": "NAB/3"})
                try:
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        return json.loads(r.read().decode("utf-8")), ""
                except urllib.error.HTTPError as e:
                    msg = ""
                    try:
                        msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
                    except Exception:
                        pass
                    if e.code == 429:
                        try:
                            ra = float(e.headers.get("retry-after") or 20)
                        except Exception:
                            ra = 20
                        self.cool[k] = time.time() + min(max(ra, 2), 300)
                        reason = "rate limit"
                        continue
                    if e.code in (401, 403):
                        self.cool[k] = time.time() + 3600
                        reason = "a key was refused"
                        continue
                    if e.code >= 500:
                        reason = f"Groq error {e.code}"
                        continue
                    return None, f"{msg or 'Request refused'} ({e.code})"
                except Exception as e:
                    reason = "no connection to Groq (" + str(e)[:60] + ")"
                    break
            if reason.startswith("no connection"):
                break
        self.last_error = reason or "failed"
        return None, self.last_error

    # ------------------------------------------------------------ models
    def model_ids(self):
        if self.models is not None and time.time() - self.models_t < 3600:
            return self.models
        j, why = self._request("/models", timeout=15)
        ids = [m["id"] for m in (j or {}).get("data", []) if m.get("id")]
        if ids:
            self.models, self.models_t = ids, time.time()
        return ids

    def vision_model(self):
        m = self.cfg.get("vision_model")
        if m:
            return m
        ids = self.model_ids()
        for h in VISION_HINTS:
            for i in ids:
                if h in i.lower():
                    return i
        return ""

    # ------------------------------------------------------------ chat
    def chat(self, messages, model=None, json_mode=False, max_tokens=700, temperature=0.4):
        """-> (text, "") or (None, reason)"""
        body = {"model": model or self.cfg["text_model"], "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        j, why = self._request("/chat/completions", body)
        if j is None and "model" in why.lower() and not model:      # retired model name -> pick another from /models
            ids = [i for i in self.model_ids() if any(t in i for t in ("llama-3.3", "gpt-oss", "llama-3.1"))]
            if ids:
                body["model"] = ids[0]
                j, why = self._request("/chat/completions", body)
        if j is None:
            return None, why
        try:
            return j["choices"][0]["message"]["content"].strip(), ""
        except Exception:
            return None, "unexpected answer"

    def ask_json(self, system, user, fast=True, max_tokens=500):
        txt, why = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             model=self.cfg["fast_model"] if fast else None, json_mode=True, max_tokens=max_tokens, temperature=0.1)
        if txt is None:
            return None, why
        try:
            return json.loads(txt), ""
        except Exception:
            m = re.search(r"\{.*\}", txt, re.S)
            try:
                return json.loads(m.group(0)), ""
            except Exception:
                return None, "answer was not valid JSON"

    def vision(self, image_bytes, prompt, mime="image/jpeg", max_tokens=400):
        vm = self.vision_model()
        if not vm:
            return None, "no vision model available on this Groq account"
        url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
        txt, why = self.chat([{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}],
                             model=vm, max_tokens=max_tokens, temperature=0.1)
        return txt, why

    def transcribe(self, path, lang=""):
        """Speech -> text with Groq Whisper (file up to ~25 MB)."""
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except Exception as e:
            return None, str(e)
        if len(blob) > 24 * 1024 * 1024:
            return None, "audio is larger than 25 MB"
        b = "----nab" + str(int(time.time() * 1000))
        parts = [("model", self.cfg["whisper_model"])] + ([("language", lang)] if lang else []) + [("response_format", "json")]
        body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in parts)
        body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(path)}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + blob + f"\r\n--{b}--\r\n".encode()
        j, why = self._request("/audio/transcriptions", raw=body, ctype=f"multipart/form-data; boundary={b}", timeout=120)
        return ((j or {}).get("text"), why) if j else (None, why)

    def status(self):
        return {"enabled": self.cfg.get("enabled", True), "keys": len(self.keys()), "use_builtin": self.cfg.get("use_builtin", True),
                "own_keys": len(self.cfg.get("keys") or []), "text_model": self.cfg["text_model"], "fast_model": self.cfg["fast_model"],
                "vision_model": self.cfg.get("vision_model") or "", "resting": sum(1 for k, t in self.cool.items() if t > time.time()),
                "last_error": self.last_error}


_ai = None
_lk = threading.Lock()


def get():
    global _ai
    with _lk:
        if _ai is None:
            _ai = AI()
        return _ai
