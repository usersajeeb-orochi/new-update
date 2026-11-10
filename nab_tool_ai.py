# nab_tool_ai.py — web API for the AI settings, Riko's chat / notes, and AI helpers.
import nab_ai
import nab_riko


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.brain = nab_riko.Brain(engine)

    def api_status(self, a):
        s = nab_ai.get().status()
        s["ok"] = True
        s["notes"] = len(self.brain.notes())
        return s

    def api_settings(self, a):
        nab_ai.get().save(**{k: a[k] for k in ("enabled", "keys", "use_builtin", "text_model", "fast_model", "vision_model", "whisper_model") if k in a})
        return self.api_status({})

    def api_test(self, a):
        out, why = nab_ai.get().chat([{"role": "user", "content": "Reply with the single word: ready"}], model=nab_ai.get().cfg["fast_model"], max_tokens=8)
        return {"ok": out is not None, "reply": out, "error": why}

    def api_chat(self, a):
        return self.brain.chat(a.get("history"), a.get("text"))

    def api_confirm(self, a):
        return self.brain.agent().confirm(a.get("id"), bool(a.get("yes", True)))

    def api_tip(self, a):
        out, why = self.brain.tip()
        return {"ok": bool(out), "tip": out, "error": why}

    def api_notes(self, a):
        return {"ok": True, "notes": self.brain.notes()}

    def api_note_add(self, a):
        return {"ok": self.brain.add_note(a.get("text"), "told")}

    def api_note_del(self, a):
        return {"ok": self.brain.del_note(a.get("i"))}

    def api_notes_clear(self, a):
        self.brain.clear()
        return {"ok": True}
