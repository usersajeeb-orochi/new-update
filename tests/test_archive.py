import os
import pytest
from PIL import Image, ImageDraw

import nab_archive as A


def mk(path, seed=0, size=(300, 200)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    import random
    rnd = random.Random(seed)
    for i in range(14):
        x, y = rnd.randint(0, size[0] - 40), rnd.randint(0, size[1] - 40)
        d.rectangle([x, y, x + rnd.randint(8, 40), y + rnd.randint(8, 40)], fill=(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    im.save(path, "JPEG", quality=90)


@pytest.fixture
def arch(tmp_path):
    root = tmp_path / "Monitoring"
    f = lambda day, cat, name: str(root / day / cat / name)
    mk(f("08-11-2026", "Bank", "Daily Star, Page-09, Pos-1-4, S-4x5, Date-08-11-2026.jpg"), 1)
    mk(f("08-11-2026", "Telecom/GP", "Prothom Alo, Page-B1, Pos-2-3, S-2x12, Date-08-11-2026.jpg"), 2)
    mk(f("07-11-2026", "Bank", "Daily Star, Page-02, Pos-1-2, S-3x3, Date-07-11-2026.jpg"), 3)
    a = A.Archive(str(tmp_path / "a.db"))
    a.scan([str(root)], str(root))
    return a, str(root)


def test_scan_reads_metadata_from_name_and_folder(arch):
    a, root = arch
    r = a.search("", paper="Daily Star")["rows"]
    assert len(r) == 2 and {x["cat"] for x in r} == {"Bank"}
    assert a.search("", cat="Telecom")["rows"][0]["cat"] == "Telecom/GP"
    assert a.search("", date_from="2026-11-08")["total"] == 2


def test_filters_combine(arch):
    a, _ = arch
    r = a.search("", paper="Daily Star", date_to="2026-11-07")["rows"]
    assert len(r) == 1 and r[0]["page"] == "02"
    assert a.search("", page="b1")["total"] == 1


def test_text_search_fts_prefix_and_all_vs_any(arch):
    a, _ = arch
    p = a.search("")["rows"][0]["path"]
    a.set_ocr(p, "Grameenphone announces new tariff for subscribers")
    assert a.search("grameen")["total"] == 1
    assert a.search("grameen, nothing", all_terms=True)["total"] == 0
    assert a.search("grameen, nothing")["total"] == 1


def test_bangla_text_found_by_fallback(arch):
    a, _ = arch
    p = a.search("")["rows"][0]["path"]
    a.set_ocr(p, "বাংলাদেশ ব্যাংক নতুন নীতি ঘোষণা করেছে")
    assert a.search("ব্যাংক")["total"] == 1


def test_deleted_files_are_forgotten_on_rescan(arch):
    a, root = arch
    p = a.search("")["rows"][0]["path"]
    os.remove(p)
    res = a.scan([root], root)
    assert res["removed"] == 1 and a.count() == 2


def test_duplicate_detection(arch, tmp_path):
    a, root = arch
    src = a.search("", paper="Prothom Alo")["rows"][0]["path"]
    copy = str(tmp_path / "Monitoring" / "08-11-2026" / "Other" / "Prothom Alo, Page-B1, Pos-2-3, S-2x12, Date-08-11-2026_2.jpg")
    os.makedirs(os.path.dirname(copy))
    Image.open(src).save(copy, "JPEG", quality=70)
    d = a.dup_of(copy)
    assert d and d["path"] == src
    other = a.search("", paper="Daily Star", page="02")["rows"][0]["path"]
    assert a.dup_of(other) is None
    assert a.dup_of(copy, exclude=[src]) is None            # same save (multi-category) is never a duplicate


def test_saved_searches(arch):
    a, _ = arch
    assert a.saved_put("Bank this week", {"cat": "Bank"})
    assert a.saved_list()[0]["query"]["cat"] == "Bank"
    a.saved_delete("Bank this week")
    assert a.saved_list() == []


def test_export_xlsx_and_csv(arch, tmp_path):
    a, _ = arch
    rows = a.search("")["rows"]
    p = a.export(rows, str(tmp_path / "out"), "xlsx")
    assert os.path.exists(p)
    q = a.export(rows, str(tmp_path / "out"), "csv")
    assert q.endswith(".csv") and open(q, encoding="utf-8-sig").read().count("\n") == 4


def test_facets(arch):
    a, _ = arch
    f = a.facets()
    assert "Daily Star" in f["papers"] and "Bank" in f["cats"]
