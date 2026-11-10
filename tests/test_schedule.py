import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import nab_schedule as S


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "FILE", str(tmp_path / "s.json")); monkeypatch.setattr(S, "LOG", str(tmp_path / "l.jsonl")); monkeypatch.setattr(S, "DOC", str(tmp_path))


def job(**k):
    return S.clean_job(dict({"name": "Daily", "time": "09:00", "days": [0, 1, 2, 3, 4, 5, 6]}, **k))


def at(h, m=0, day=9):          # 2026-11-09 is a Monday
    return datetime.datetime(2026, 11, day, h, m)


def test_clean_defaults():
    j = S.clean_job({"time": "99:99", "deliver": ["x"], "days": ["8"]})
    assert j["time"] == "23:59" and j["deliver"] == ["folder"] and j["days"] == [0, 1, 2, 3, 4, 5, 6] and j["params"]["range"] == "yesterday"


def test_due_rules():
    j = job()
    assert S.due(j, at(8, 59)) == "" and S.due(j, at(9, 0)) == "run" and S.due(j, at(14, 0)) == "run"
    assert S.due(j, at(16, 0)) == "skip"
    j["last_day"] = "2026-11-09"
    assert S.due(j, at(9, 5)) == ""
    assert S.due(job(days=[1]), at(9, 5)) == ""                       # Monday not in [Tuesday]
    assert S.due(job(enabled=False), at(9, 5)) == ""


def test_save_delete_roundtrip():
    c = S.save_job({"name": "A", "time": "07:30"})
    assert S.jobs()[0]["id"] == c["id"]
    S.save_job({"id": c["id"], "name": "B", "time": "08:00"})
    assert len(S.jobs()) == 1 and S.jobs()[0]["name"] == "B"
    S.delete_job(c["id"]); assert S.jobs() == []


def test_run_report_marks_day_and_delivers(monkeypatch, tmp_path):
    import nab_reports, nab_archive
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"%PDF")
    monkeypatch.setattr(nab_reports, "run_report", lambda arch, p, user="", out_dir=None: {"ok": True, "path": str(pdf), "n": 3})
    monkeypatch.setattr(nab_archive, "get", lambda: None)
    c = S.save_job({"name": "Rep", "time": "00:00", "deliver": ["folder", "telegram"]})
    r = S.Runner(None)
    sent = []
    r._tg_files = lambda paths, cap, chat: sent.append((paths, cap))
    res = r.run_now(c["id"], mark=True)
    assert res["ok"] and sent and "3 clips" in res["msg"]
    assert S.jobs()[0]["last_day"] == datetime.date.today().isoformat()


def test_delivery_failure_reported(monkeypatch, tmp_path):
    import nab_reports, nab_archive, nab_telegram
    pdf = tmp_path / "r.pdf"; pdf.write_bytes(b"x")
    monkeypatch.setattr(nab_reports, "run_report", lambda *a, **k: {"ok": True, "path": str(pdf), "n": 1})
    monkeypatch.setattr(nab_archive, "get", lambda: None)
    monkeypatch.setattr(nab_telegram, "_tg_send", lambda *a, **k: None)
    c = S.save_job({"name": "Rep", "deliver": ["whatsapp"]})          # no chat chosen
    res = S.Runner(None).run_now(c["id"])
    assert not res["ok"] and "no WhatsApp chat" in res["msg"]
