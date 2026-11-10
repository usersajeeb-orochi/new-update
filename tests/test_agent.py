import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_agent


class FakeAI:
    def __init__(self, outs): self.outs = list(outs); self.seen = []
    def chat(self, msgs, **k): self.seen.append(msgs); return (self.outs.pop(0), "") if self.outs else (None, "none left")


class Brain:
    def system(self): return "SYS"


class Arch:
    def search(self, q, a, lim, **f): return {"rows": [{"name": "x.png", "paper": "Prothom Alo", "ocr": "SECRET"}], "total": 1, "more": False}
    def facets(self): return {"papers": ["A"], "cats": ["Bank"]}


def mk(outs):
    a = nab_agent.Agent(object(), FakeAI(outs), Brain()); a._arch = lambda: Arch(); return a


def test_read_tool_then_reply():
    a = mk([json.dumps({"tool": "search_archive", "args": {"q": "bank"}}), json.dumps({"reply": "Found 1 clip."})])
    r = a.run([], "find bank clips")
    assert r["reply"] == "Found 1 clip."
    fed = a.ai.seen[1][-1]["content"]
    assert "Prothom Alo" in fed and "SECRET" not in fed          # result reaches the model, raw OCR text does not


def test_write_tool_needs_confirm(monkeypatch):
    a = mk([json.dumps({"tool": "make_report", "args": {"range": "today"}})])
    ran = []
    a.do_write = lambda n, ar: ran.append(n) or {"ok": True, "text": "made"}
    r = a.run([], "make today's report")
    assert r["confirm"] and not ran                              # nothing made yet
    assert a.confirm(r["confirm"]["id"], False)["reply"].startswith("Cancelled") and not ran
    r = a.run([], "again") if False else None
    a.outs = None


def test_confirm_runs_once():
    a = mk([json.dumps({"tool": "make_report", "args": {}})])
    ran = []
    a.do_write = lambda n, ar: ran.append(n) or {"ok": True, "text": "made"}
    pid = a.run([], "report")["confirm"]["id"]
    assert a.confirm(pid)["reply"] == "made" and ran == ["make_report"]
    assert not a.confirm(pid)["ok"] and len(ran) == 1            # second press does nothing


def test_unknown_tool_and_plain_text_and_loop_limit():
    a = mk([json.dumps({"tool": "delete_everything"}), json.dumps({"reply": "no"})])
    assert a.run([], "x")["reply"] == "no"
    assert mk(["just words"]).run([], "x")["reply"] == "just words"
    loop = [json.dumps({"tool": "list_filters"})] * 10
    assert "could not finish" in mk(loop).run([], "x")["reply"]


def test_offline():
    assert mk([]).run([], "x")["offline"]
