import types
import pytest

pytest.importorskip("PIL")
import nab_tool_wa as W


class Hub:
    def __init__(self): self.ev = []
    def emit(self, *a, **k): self.ev.append((a, k))


@pytest.fixture
def tool(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "FILE", str(tmp_path / "wa.json"))
    e = types.SimpleNamespace(hub=Hub(), categories=[])
    t = W.Tool(e)
    monkeypatch.setattr(t, "_ensure_worker", lambda: None)       # no browser in tests
    f = tmp_path / "clip.jpg"; f.write_bytes(b"x")
    return t, str(f)


def test_double_click_queues_once(tool):
    t, f = tool
    assert t._enqueue([f], "Group", None) == "queued"
    assert t._enqueue([f], "Group", None) == "busy"
    assert t.pending == 1 and len(t.jobs) == 1


def test_recent_send_is_ignored_then_force_allowed(tool):
    t, f = tool
    t._enqueue([f], "Group", None)
    data = next(iter(t.jobmap)); job = t.jobs[0]
    job["state"] = "sent"
    assert t._enqueue([f], "Group", None) == "dup"
    assert t._enqueue([f], "Group", None, force=True) == "queued"


def test_retry_of_failed_job_is_safe_against_double_click(tool):
    t, f = tool
    t._enqueue([f], "Group", None)
    t.jobs[0]["state"] = "failed"
    r1 = t.api_retry({"id": t.jobs[0]["id"]})
    r2 = t.api_retry({"id": t.jobs[0]["id"]})
    assert r1["ok"] and r2["ok"]
    assert sum(1 for j in t.jobs if j["state"] == "queued") == 1


def test_different_chat_is_a_different_job(tool):
    t, f = tool
    assert t._enqueue([f], "A", None) == "queued"
    assert t._enqueue([f], "B", None) == "queued"


def test_settings_are_clamped(tool):
    t, _ = tool
    t.api_settings({"gap_s": 9999, "dup_minutes": -4, "send_timeout_s": 1})
    assert t.cfg["gap_s"] == 60 and t.cfg["dup_minutes"] == 0 and t.cfg["send_timeout_s"] == 15
