import os, datetime
import pytest
from PIL import Image
import nab_archive as A
import nab_reports as R


@pytest.fixture
def arch(tmp_path):
    root = tmp_path / "Monitoring"
    for i, (day, cat, paper) in enumerate([("08-11-2026", "Bank", "Daily Star"), ("08-11-2026", "Telecom", "Prothom Alo"), ("07-11-2026", "Bank", "Daily Star")]):
        d = root / day / cat
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (400 + i * 50, 300), (200, 220 - i * 30, 240)).save(d / f"{paper}, Page-0{i + 1}, Pos-1-3, S-4x5, Date-{day}.jpg")
    a = A.Archive(str(tmp_path / "a.db"))
    a.scan([str(root)], str(root))
    return a


def tpl(**k):
    return R.clean_template(dict({"name": "T", "title": "Coverage", "client": "Beximco", "footer": "NAB"}, **k))


def test_build_report_pdf_and_excel(arch, tmp_path):
    rows = arch.search("")["rows"]
    r = R.build_report(rows, tpl(), ("2026-11-07", "2026-11-08"), user="amin", out_dir=str(tmp_path / "o"))
    assert r["ok"] and r["n"] == 3 and r["pages"] == 4          # cover + 3 clip pages
    assert open(r["path"], "rb").read(5) == b"%PDF-"
    assert os.path.exists(r["xlsx"])


def test_two_per_page_and_no_cover(arch, tmp_path):
    r = R.build_report(arch.search("")["rows"], tpl(per_page=2, cover=False), out_dir=str(tmp_path / "o"))
    assert r["ok"] and r["pages"] == 2


def test_filters_through_run_report(arch, tmp_path):
    R.TEMPLATES_FILE = str(tmp_path / "t.json")
    r = R.run_report(arch, {"template": "Standard", "cat": "Bank", "range": "", "date_from": "2026-11-08", "date_to": "2026-11-08"}, out_dir=str(tmp_path / "o"))
    assert r["ok"] and r["n"] == 1


def test_empty_selection_is_a_clear_error(arch, tmp_path):
    r = R.run_report(arch, {"cat": "Nothing"}, out_dir=str(tmp_path / "o"))
    assert not r["ok"] and "nothing" in r["error"].lower()


def test_range_presets():
    t = datetime.date(2026, 11, 9)
    assert R.resolve_range("yesterday", today=t) == ("2026-11-08", "2026-11-08")
    assert R.resolve_range("last7", today=t) == ("2026-11-03", "2026-11-09")
    assert R.resolve_range("last_month", today=t) == ("2026-10-01", "2026-10-31")
    assert R.resolve_range("this_month", today=t)[0] == "2026-11-01"


def test_template_cleaning_and_save(tmp_path):
    R.TEMPLATES_FILE = str(tmp_path / "t.json")
    out = R.save_templates([{"name": "A", "accent": "not a colour", "per_page": 5}, {"name": "a"}])
    assert len(out) == 1 and out[0]["accent"] == "#2f5fd0" and out[0]["per_page"] == 1
    assert R.get_template("a")["name"] == "A"
