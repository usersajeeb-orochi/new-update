import nab_meta


def test_normal_line():
    m = nab_meta.parse("09 1-3 4x6")
    assert m["ok"]


def test_missing_size_fails():
    assert not nab_meta.parse("09 1-3")["ok"]
