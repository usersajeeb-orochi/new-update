import os
import types
import pytest
from PIL import Image

H = pytest.importorskip("nab_engine_host")


def stub(tmp_path, names):
    for n in names:
        Image.new("RGB", (20, 20), "white").save(tmp_path / n)
    got = []
    s = types.SimpleNamespace(added=got)
    s.add_images = lambda imgs, name="": got.append(name)
    for m in ("batch_start", "batch_next", "batch_stop"):
        setattr(s, m, types.MethodType(getattr(H.Engine, m), s))
    return s


def test_natural_order_and_advance(tmp_path):
    s = stub(tmp_path, ["p10.jpg", "p2.jpg", "p1.jpg"])
    r = s.batch_start(str(tmp_path))
    assert r["ok"] and r["name"] == "p1.jpg" and r["total"] == 3 and r["left"] == 2
    assert s.batch_next()["name"] == "p2.jpg"
    last = s.batch_next()
    assert last["name"] == "p10.jpg" and last["left"] == 0
    assert not s.batch_next()["ok"]                   # batch closed itself


def test_bad_folder_and_empty_folder(tmp_path):
    s = stub(tmp_path, [])
    assert not s.batch_start(str(tmp_path / "nope"))["ok"]
    assert not s.batch_start(str(tmp_path))["ok"]


def test_unreadable_file_is_skipped(tmp_path):
    s = stub(tmp_path, ["a.jpg", "c.jpg"])
    (tmp_path / "b.jpg").write_bytes(b"not an image")
    assert s.batch_start(str(tmp_path))["name"] == "a.jpg"
    assert s.batch_next()["name"] == "c.jpg"
