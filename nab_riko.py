# nab_riko.py — the character's brain: knowledge of NAB, a chat with the AI, and self-learning notes.
#
# Learning is local and visible: short notes about how the user works ("saves Bank clips with key 3",
# "prefers Bangla replies") are kept in Documents\nab_riko_brain.json, shown in the right-click menu,
# and the user can delete any of them.  Nothing else is stored.
import os
import re
import json
import time
import threading

import nab_ai
import nab_engine

KNOW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "riko_knowledge.md")
MAX_NOTES = 120


class Brain:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.Lock()
        self.d = self._load()

    def _load(self):
        try:
            with open(nab_ai.BRAIN, encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("notes", [])
            d.setdefault("asked", {})
            return d
        except Exception:
            return {"notes": [], "asked": {}}

    def _save(self):
        try:
            tmp = nab_ai.BRAIN + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False)
            os.replace(tmp, nab_ai.BRAIN)
        except Exception:
            pass

    # ---- notes
    def notes(self):
        return list(self.d["notes"])

    def add_note(self, text, src="chat"):
        text = re.sub(r"\s+", " ", (text or "").strip())[:220]
        if len(text) < 4:
            return False
        with self.lock:
            low = text.lower()
            for n in self.d["notes"]:
                if n["t"].lower() == low:
                    n["n"] = n.get("n", 1) + 1
                    n["ts"] = time.time()
                    self._save()
                    return False
            self.d["notes"].append({"t": text, "src": src, "ts": time.time(), "n": 1})
            self.d["notes"] = sorted(self.d["notes"], key=lambda x: (x.get("n", 1), x["ts"]))[-MAX_NOTES:]
            self._save()
            return True

    def del_note(self, i):
        with self.lock:
            try:
                del self.d["notes"][int(i)]
                self._save()
                return True
            except Exception:
                return False

    def clear(self):
        with self.lock:
            self.d = {"notes": [], "asked": {}}
            self._save()

    # ---- prompt
    def knowledge(self):
        try:
            with open(KNOW, encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "NAB clips newspaper items and saves them by category."

    def context(self):
        """What is on screen right now (so 'why can't I save?' gets a real answer)."""
        e = self.e
        try:
            lay = len(e.doc.visible_layers())
        except Exception:
            lay = 0
        d = getattr(e, "draft", {}) or {}
        hk = getattr(e, "universal_hotkeys", {}) or {}
        try:
            ver = __import__("nab_constants").APP_VERSION
        except Exception:
            ver = ""
        return (f"App version {ver}. Current paper: {getattr(e, 'paper_clean', '') or 'none'}. "
                f"Clips on the canvas: {lay}. Armed categories: {', '.join(d.get('cats') or []) or 'none'}. Typed metadata: {d.get('line') or 'empty'}. "
                f"Saved today: {len(getattr(e, 'session_history', []))}. Hotkey overrides: " + ", ".join(f"{k}={v}" for k, v in hk.items() if k in ("discard", "paste", "generate")))

    def system(self, lang_hint=""):
        notes = sorted(self.d["notes"], key=lambda x: (-x.get("n", 1), -x["ts"]))[:25]
        mem = "\n".join("- " + n["t"] for n in notes) or "(nothing learned yet)"
        return ("You are Riko, the small animated guide living inside the NAB desktop app. You help newspaper-clipping operators use NAB. "
                "Be warm, short (1-4 sentences unless asked for steps), practical. Reply in the user's language (Bangla or English; match them). "
                "Use ONLY the app knowledge below; if something is not covered say you are not sure and suggest Ctrl+K or Settings. Never invent buttons or keys. "
                "Do not use emoji.\n\n=== APP KNOWLEDGE ===\n" + self.knowledge() + "\n=== CURRENT STATE ===\n" + self.context() +
                "\n=== THINGS YOU HAVE LEARNED ABOUT THIS USER ===\n" + mem + ("\n" + lang_hint if lang_hint else ""))

    # ---- chat
    def chat(self, history, text):
        ai = nab_ai.get()
        t = (text or "").strip()
        if not t:
            return {"ok": False, "error": "Say something first."}
        m = re.match(r"^(?:remember|মনে রাখো)[:,\s]+(.+)$", t, re.I | re.S)
        if m:
            self.add_note(m.group(1), "told")
            return {"ok": True, "reply": "Got it, I will remember that.", "learned": m.group(1)[:120]}
        m = re.match(r"^(?:forget|ভুলে যাও)[:,\s]+(.+)$", t, re.I | re.S)
        if m:
            q = m.group(1).lower()
            hit = [i for i, n in enumerate(self.d["notes"]) if q in n["t"].lower()]
            for i in reversed(hit):
                self.del_note(i)
            return {"ok": True, "reply": f"Forgot {len(hit)} note(s)." if hit else "I had nothing like that."}
        if getattr(self, "agent_on", True):
            r = self.agent().run(history, t)
            if r.get("ok") and not r.get("offline"):
                r["learned"] = self.learn(t, r.get("reply", "")) if not r.get("confirm") else ""
            return r
        msgs = [{"role": "system", "content": self.system()}]
        for h in (history or [])[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("text"):
                msgs.append({"role": h["role"], "content": str(h["text"])[:600]})
        msgs.append({"role": "user", "content": t[:1200]})
        out, why = ai.chat(msgs, max_tokens=420, temperature=0.5)
        if out is None:
            return {"ok": False, "error": why, "offline": True}
        out = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", out).strip()
        learned = self.learn(t, out)
        return {"ok": True, "reply": out, "learned": learned}

    def agent(self):
        if not hasattr(self, "_agent"):
            import nab_agent
            self._agent = nab_agent.Agent(self.e, nab_ai.get(), self)
        return self._agent

    def learn(self, user_text, reply):
        """Ask the small model whether the user stated something durable about how they work."""
        if len(user_text) < 12 or user_text.endswith("?") and len(user_text) < 40:
            return ""
        j, why = nab_ai.get().ask_json(
            "Extract at most 2 DURABLE facts or preferences the USER states about how they work with NAB or how they want the helper to behave "
            "(e.g. 'saves Telecom clips with key 4', 'wants answers in Bangla', 'colleague uses a slow PC'). Ignore questions and one-off requests. "
            'Return JSON: {"notes": ["short fact", ...]} with an empty list if none.', user_text[:600])
        got = []
        for n in ((j or {}).get("notes") or [])[:2]:
            if isinstance(n, str) and self.add_note(n, "learned"):
                got.append(n)
        return "; ".join(got)

    def tip(self):
        """One useful tip, favouring things the user has not been shown."""
        ai = nab_ai.get()
        shown = self.d["asked"].setdefault("tips", [])
        out, why = ai.chat([{"role": "system", "content": self.system()},
                            {"role": "user", "content": "Give ONE short practical tip (max 25 words) about a NAB feature or shortcut that would save time. "
                             "Do not repeat these: " + " | ".join(shown[-8:])}], model=ai.cfg["fast_model"], max_tokens=90, temperature=0.9)
        if out:
            shown.append(out[:80])
            self.d["asked"]["tips"] = shown[-20:]
            self._save()
        return out, why
