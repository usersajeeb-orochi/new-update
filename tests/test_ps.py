import os
import pytest
from PIL import Image

import nab_core
import nab_ps


class Hub:
    def emit(self, *a, **k):
        pass


class Eng(nab_ps.PSMixin):
    def __init__(self):
        self.doc = nab_core.Document()
        self.hub = Hub()
        self._preview_cache = None
        self.last_page = self.last_pos = ""
        self.paper_clean = ""
        self.logo_scale = self.text_scale = 0.5
        self.show_header = True

    def header_text(self, p, c):
        return "Page-%s, Pos-%s" % (p, c)

    def get_logo(self, paper, small=False):
        return None


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))


def img(path, color, size=(80, 50)):
    Image.new("RGB", size, color).save(path)
    return str(path)


def test_open_many_each_own_canvas(tmp_path):
    e = Eng()
    r = e.ps_open([img(tmp_path / "a.png", "red"), img(tmp_path / "b.jpg", "blue"), str(tmp_path / "x.txt")])
    assert r["opened"] == 2 and len(r["skipped"]) == 1
    assert e.ps_on and [d["name"] for d in r["docs"]] == ["a", "b"]
    assert r["cur"] == 0 and e.doc is e._psd()["docs"][0]["doc"]
    e.ps_switch(1)
    assert e.doc is e._psd()["docs"][1]["doc"]


def test_save_first_asks_then_overwrites(tmp_path, monkeypatch):
    e = Eng()
    e.ps_open([img(tmp_path / "a.png", "red")])
    out = tmp_path / "out" / "edited.png"
    monkeypatch.setattr(nab_ps.nab_winutil, "save_dialog", lambda *a, **k: str(out))
    r = e.ps_save()
    assert r["ok"] and out.is_file()
    assert Image.open(out).width >= 80          # logo + header are on by default (page may be padded)
    monkeypatch.setattr(nab_ps.nab_winutil, "save_dialog", lambda *a, **k: pytest.fail("must not ask again"))
    assert e.ps_save()["ok"]
    monkeypatch.setattr(nab_ps.nab_winutil, "save_dialog", lambda *a, **k: "")
    assert e.ps_save(save_as=True).get("cancel")


def test_merge_down_and_dirty(tmp_path):
    e = Eng()
    e.ps_open([img(tmp_path / "a.png", "red")])
    e.doc.add(Image.new("RGB", (30, 30), "green"), "L2")
    assert len(e.doc.layers) == 2
    e.doc.merge_down(e.doc.layers[-1].id)
    assert len(e.doc.layers) == 1
    assert e.ps_state()["docs"][0]["dirty"]


def test_close_and_off(tmp_path):
    e = Eng()
    e.ps_open([img(tmp_path / "a.png", "red"), img(tmp_path / "b.png", "blue")])
    r = e.ps_close(0)
    assert len(r["docs"]) == 1
    r = e.ps_set(False)
    assert not r["on"] and e.doc.layers


def test_scan_flow(tmp_path, monkeypatch):
    e = Eng()
    raw = tmp_path / "raw.bmp"
    Image.new("RGB", (60, 90), "white").save(raw)
    monkeypatch.setattr(nab_ps.nab_winutil, "scan_image", lambda base, **k: (str(raw), ""))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    r = e.ps_scan()
    assert r["ok"] and e.ps_on and r["docs"][-1]["w"] == 60
    monkeypatch.setattr(nab_ps.nab_winutil, "scan_image", lambda base, **k: ("", ""))
    assert e.ps_scan().get("cancel")
    monkeypatch.setattr(nab_ps.nab_winutil, "scan_image", lambda base, **k: ("", "No scanner found."))
    assert "scanner" in e.ps_scan()["error"]


def test_brand_stays_on_in_ps_mode(tmp_path):
    e = Eng()
    assert e.ps_state()["brand"] is True
    e.ps_open([img(tmp_path / "a.png", "red")])
    assert e.ps_state()["brand"] is True          # logo + header stay on in Photoshop mode
    assert e.brand_set(False)["brand"] is False
    e.ps_set(False)
    assert e.brand_set(True)["brand"] is True
