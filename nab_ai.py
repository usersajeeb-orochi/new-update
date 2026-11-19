# nab_ai.py — one small AI client used by every NAB feature that needs AI.
#
#  1. the NAB cloud (Gemini, then OpenRouter free models). The keys live on the server, never on a PC.
#  2. Groq with your own keys from Settings > AI (a LIST: when one is rate-limited the next is used)
#  3. a Gemini key of your own / the anonymous Pollinations service (both opt-in)
#  * OpenAI-compatible HTTPS calls with urllib (no extra package)
#  * model names are looked up from the provider's own /models list, so a retired name never breaks the app
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
import urllib.parse
import urllib.request
import urllib.error

import nab_engine

BASE = os.environ.get("NAB_AI_BASE") or "https://api.groq.com/openai/v1"
FILE = os.path.join(nab_engine.DOC_DIR, "nab_ai.json")
BRAIN = os.path.join(nab_engine.DOC_DIR, "nab_riko_brain.json")

# Built-in keys are NOT in the source any more (a key in a public repo is found and revoked by the provider within hours).
# They come from the build secret NAB_SECRETS_JSON ("groq_keys": "gsk_..., gsk_...") and/or Settings > AI on each PC.
import nab_secrets
DEFAULT_KEYS = [k for k in re.split(r"[\s,]+", nab_secrets.get("groq_keys")) if k]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
POLLI_BASE = "https://text.pollinations.ai/openai"
DEFAULTS = {"enabled": True, "use_cloud": True, "keys": [], "use_builtin": True, "text_model": "openai/gpt-oss-120b",
            "fast_model": "openai/gpt-oss-20b", "vision_model": "",
            "alt_key": "", "alt_model": "gemini-flash-latest", "alt_free": False}
# Groq switched these off in 2026 (llama-3.3 / 3.1 on 16 Aug, Llama 4 Scout on 17 Jul): a saved setting that still names one is replaced.
RETIRED = {"llama-3.3-70b-versatile": "openai/gpt-oss-120b", "llama-3.1-8b-instant": "openai/gpt-oss-20b",
           "meta-llama/llama-4-scout-17b-16e-instruct": "", "meta-llama/llama-4-maverick-17b-128e-instruct": "", "qwen/qwen3-32b": "openai/gpt-oss-120b"}
VISION_HINTS = ("llama-4-scout", "llama-4-maverick", "vision", "-vl", "pixtral")


class AI:
    def __init__(self):
        self.lock = threading.RLock()
        self.cool = {}                 # key -> time it may be used again
        self.models = None
        self.models_t = 0
        self.cfg = self._load()
        self.last_error = ""
        self.last_used = ""
        self._cloud_off = 0

    # ------------------------------------------------------------ settings
    def _load(self):
        d = dict(DEFAULTS)
        try:
            with open(FILE, encoding="utf-8") as f:
                d.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except Exception:
            pass
        for k in ("text_model", "fast_model", "vision_model"):
            if d.get(k) in RETIRED:
                d[k] = RETIRED[d[k]] or (DEFAULTS[k] if k != "vision_model" else "")
        return d

    def save(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if k in DEFAULTS:
                    if k == "keys":
                        v = [x.strip() for x in (v if isinstance(v, list) else re.split(r"[\s,]+", str(v))) if x.strip()]
                    elif k in ("enabled", "use_builtin", "use_cloud", "alt_free"):
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
        return bool(self.cfg.get("enabled", True) and (self._cloud_on() or self.keys() or self.cfg.get("alt_key") or self.cfg.get("alt_free")))

    # ------------------------------------------------------------ the NAB cloud (Gemini / OpenRouter, keys stay on the server)
    def _cloud_on(self):
        if not self.cfg.get("use_cloud", True) or time.time() < self._cloud_off:
            return False
        try:
            import nab_remote
            return bool(nab_remote.cloud_url())
        except Exception:
            return False

    def _cloud_chat(self, kind, messages, json_mode, max_tokens, temperature):
        """-> (text, "") or (None, reason). After a 'no key / bad signature' answer the cloud is skipped for 5 minutes, after a network error for 1."""
        if not self._cloud_on():
            return None, "cloud AI is off"
        try:
            import nab_remote
            from nab_telegram import PC_NAME
            body = json.dumps({"kind": kind, "messages": messages, "json_mode": json_mode, "max_tokens": max_tokens, "temperature": temperature}).encode()
            req = urllib.request.Request(nab_remote.cloud_url() + "/ai/chat?pc=" + urllib.parse.quote(PC_NAME), data=body,
                                         headers=dict(nab_remote.sign_headers(PC_NAME), **{"Content-Type": "application/json", "User-Agent": "NAB/3"}))
            j = None
            for tmo in (35, 55):                         # a sleeping free server needs ~30 s to wake: one quiet retry before giving up
                try:
                    with urllib.request.urlopen(req, timeout=tmo) as r:
                        j = json.loads(r.read().decode("utf-8"))
                    break
                except urllib.error.HTTPError:
                    raise
                except Exception as ex:
                    if tmo == 55:
                        raise ex
                    time.sleep(1.5)
            if j.get("ok") and j.get("text"):
                self.last_used = f"{j.get('provider')} / {j.get('model')}"
                return j["text"].strip(), ""
            return None, j.get("error") or "cloud AI gave no answer"
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                pass
            if e.code in (403, 503):
                self._cloud_off = time.time() + 300
            return None, f"cloud AI: {msg or e.code}"
        except Exception as e:
            self._cloud_off = time.time() + 60
            return None, "cloud AI unreachable (" + str(e)[:50] + ")"

    # ------------------------------------------------------------ backup providers (free)
    def _alt_chat(self, messages, max_tokens, temperature, json_mode):
        """Second chance when Groq has no key or fails: a free Gemini key of your own, then (only if you allowed it) the anonymous Pollinations service.
        -> (text, "") or (None, reason)"""
        tries = []
        if self.cfg.get("alt_key"):
            tries.append((GEMINI_BASE, self.cfg["alt_key"], self.cfg.get("alt_model") or "gemini-flash-latest"))
        if self.cfg.get("alt_free"):
            tries.append((POLLI_BASE, "", "openai"))
        why = "no backup provider set"
        for base, key, model in tries:
            body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
            if json_mode and key:
                body["response_format"] = {"type": "json_object"}
            hdr = {"Content-Type": "application/json", "User-Agent": "NAB/3"}
            if key:
                hdr["Authorization"] = "Bearer " + key
            try:
                req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(), headers=hdr)
                with urllib.request.urlopen(req, timeout=40) as r:
                    return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip(), ""
            except urllib.error.HTTPError as e:
                why = f"backup provider refused ({e.code})"
            except Exception as e:
                why = "backup provider: " + str(e)[:60]
        return None, why

    # ------------------------------------------------------------ http
    def _request(self, path, body=None, method=None, timeout=45):
        """Try every key until one answers.  Returns (json, "") or (None, reason)."""
        if not self.cfg.get("enabled", True):
            return None, "AI is switched off in Settings."
        keys = self.keys()
        if not keys:
            return None, "No API key set (Settings > AI)."
        data = json.dumps(body).encode("utf-8") if body is not None else None
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
                                             headers={"Authorization": "Bearer " + k, "Content-Type": "application/json", "User-Agent": "NAB/3"})
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
    def chat(self, messages, model=None, json_mode=False, max_tokens=700, temperature=0.4, kind=None):
        """-> (text, "") or (None, reason). Order: NAB cloud, then Groq with your keys, then your own Gemini key / Pollinations."""
        if not self.cfg.get("enabled", True):
            return None, "AI is switched off in Settings."
        kind = kind or ("fast" if model and model == self.cfg["fast_model"] else "text")
        cloud_why = ""
        if self._cloud_on():
            txt, cloud_why = self._cloud_chat(kind, messages, json_mode, max_tokens, temperature)
            if txt:
                return txt, ""
        if not self.keys():
            alt, why2 = self._alt_chat(messages, max_tokens, temperature, json_mode)
            if alt is not None:
                return alt, ""
            return None, cloud_why or "No API key set (Settings > AI)."
        m = model or self.cfg["text_model"]
        body = {"model": m, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if m.startswith("openai/gpt-oss"):             # a reasoning model: keep its thinking short so the answer fits in max_tokens
            body["reasoning_effort"] = "low"
            body["max_tokens"] = max(max_tokens, 400)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        j, why = self._request("/chat/completions", body)
        if j is None and ("model" in why.lower() or "decommission" in why.lower()) and not model:      # retired model name -> pick another from /models
            ids = [i for i in self.model_ids() if any(t in i for t in ("gpt-oss-120b", "gpt-oss-20b", "qwen", "llama"))]
            if ids:
                body["model"] = ids[0]
                body.pop("reasoning_effort", None)
                j, why = self._request("/chat/completions", body)
        if j is not None:
            try:
                txt = (j["choices"][0]["message"].get("content") or "").strip()
                if txt:
                    self.last_used = "groq / " + body["model"]
                    return txt, ""
                why = "empty answer"
            except Exception:
                why = "unexpected answer"
        alt, why2 = self._alt_chat(messages, max_tokens, temperature, json_mode)
        return (alt, "") if alt is not None else (None, cloud_why or why)

    def ask_json(self, system, user, fast=True, max_tokens=500):
        txt, why = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             model=self.cfg["fast_model"] if fast else None, json_mode=True, max_tokens=max_tokens, temperature=0.1, kind="fast" if fast else "text")
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

    @staticmethod
    def _shrink(blob, mime):
        """A big screenshot is shrunk before it travels: faster, cheaper, and plenty for reading a newspaper name."""
        try:
            if len(blob) < 900_000:
                return blob, mime
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(blob))
            im.thumbnail((1800, 1800))
            out = io.BytesIO()
            im.convert("RGB").save(out, "JPEG", quality=82)
            return out.getvalue(), "image/jpeg"
        except Exception:
            return blob, mime

    def vision(self, image_bytes, prompt, mime="image/jpeg", max_tokens=400):
        image_bytes, mime = self._shrink(image_bytes, mime)
        url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
        msgs = [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": url}}]}]
        why = ""
        if self.cfg.get("enabled", True) and self._cloud_on():
            txt, why = self._cloud_chat("vision", msgs, False, max_tokens, 0.1)
            if txt:
                return txt, ""
        vm = self.vision_model() if self.keys() else ""
        if not vm:
            return None, why or "no vision model available (the NAB cloud and Groq both have none)"
        return self.chat(msgs, model=vm, max_tokens=max_tokens, temperature=0.1, kind="vision")

    def status(self):
        return {"enabled": self.cfg.get("enabled", True), "keys": len(self.keys()), "use_builtin": self.cfg.get("use_builtin", True),
                "own_keys": len(self.cfg.get("keys") or []), "text_model": self.cfg["text_model"], "fast_model": self.cfg["fast_model"],
                "vision_model": self.cfg.get("vision_model") or "", "resting": sum(1 for k, t in self.cool.items() if t > time.time()),
                "last_error": self.last_error, "cloud": self._cloud_on(), "use_cloud": self.cfg.get("use_cloud", True), "last_used": self.last_used, "alt_key": bool(self.cfg.get("alt_key")), "alt_model": self.cfg.get("alt_model", ""), "alt_free": bool(self.cfg.get("alt_free"))}


_ai = None
_lk = threading.Lock()


def get():
    global _ai
    with _lk:
        if _ai is None:
            _ai = AI()
        return _ai
