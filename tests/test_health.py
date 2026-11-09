import types
import pytest
import nab_health as H


def test_row_shape_and_overall_worst(monkeypatch):
    monkeypatch.setattr(H, "check_clock", lambda: H._row("clock", "c", H.OK))
    monkeypatch.setattr(H, "check_internet", lambda: H._row("net", "n", H.BAD, "x"))
    for n in ("check_updates", "check_telegram", "check_tools", "check_accounts"):
        monkeypatch.setattr(H, n, lambda: H._row("x", "x", H.OK))
    for n in ("check_drive", "check_whatsapp", "check_disk", "check_backups"):
        monkeypatch.setattr(H, n, lambda e: H._row("x", "x", H.WARN))
    r = H.run_all(types.SimpleNamespace(), timeout=3)
    assert r["overall"] == "bad" and len(r["rows"]) >= 10
    assert all({"id", "label", "status", "detail", "fix"} <= set(x) for x in r["rows"])


def test_a_crashing_check_does_not_break_the_screen(monkeypatch):
    def boom(): raise RuntimeError("x")
    monkeypatch.setattr(H, "check_clock", boom)
    for n in ("check_internet", "check_updates", "check_telegram", "check_tools", "check_accounts"):
        monkeypatch.setattr(H, n, lambda: H._row("x", "x", H.OK))
    for n in ("check_drive", "check_whatsapp", "check_disk", "check_backups"):
        monkeypatch.setattr(H, n, lambda e: H._row("x", "x", H.OK))
    r = H.run_all(types.SimpleNamespace(), timeout=3)
    assert r["overall"] == "warn"
