import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_daily_report as D

PAPERS = ["Daily Star", "Prothom Alo", "Financial Express", "New Age", "Daily Sun", "Bonik Barta", "Samakal"]
CATS = ["Beximco/Bank", "Beximco/Capital Market", "GP", "BL", "Robi", "Telecom industry", "Teletalk", "Edotco", "Economy", "Loan"]


def fake(day, seed=3, days=31):
    random.seed(seed)
    d0 = datetime.date.fromisoformat(day)
    rows = []
    for k in range(days):
        d = (d0 - datetime.timedelta(days=k)).isoformat()
        for _ in range(random.randint(25, 70)):
            p = random.choice(PAPERS[: (7 if k else 6)])               # Samakal missing today
            rows.append({"paper": p, "page": str(random.randint(1, 12)), "pos": "1-2", "size": "4x6", "cat": random.choice(CATS), "date": d,
                         "user": random.choice(["Sajeeb", "Rafi", "Mim"]), "kb": random.randint(40, 300), "path": f"C:/x/{k}.jpg",
                         "added": f"{d} {random.randint(9, 22):02d}:{random.randint(0, 59):02d}:00"})
    return rows


def test_analyse_and_workbook(tmp_path):
    day = "2026-11-11"
    rows = fake(day)
    A = D.analyse(rows, day)
    assert A["n"] == sum(1 for r in rows if r["date"] == day)
    assert any(m[0] == "Samakal" for m in A["missing"])
    assert A["insights"] and "clips saved" in A["insights"][0]
    path, _ = D.build_workbook(rows, day, out_dir=str(tmp_path), client="Test")
    assert os.path.getsize(path) > 8000
    import openpyxl
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames[0] == "Overview" and "Paper x Category" in wb.sheetnames and "Clips" in wb.sheetnames
    assert len(wb["Overview"]._charts) >= 4


def test_empty_day_does_not_crash(tmp_path):
    path, A = D.build_workbook([], "2026-11-11", out_dir=str(tmp_path))
    assert A["n"] == 0 and os.path.exists(path)


def test_doc_archive(tmp_path):
    A = D.analyse(fake("2026-11-10", 1, 30), "2026-11-10")
    p = D.build_doc(A, out_dir=str(tmp_path))
    from docx import Document
    d = Document(p)
    assert "Clip Archive" in d.paragraphs[0].text and len(d.tables) >= 3


def test_natural_page_order():
    assert sorted(["10", "2", "1"], key=D._nat) == ["1", "2", "10"]
