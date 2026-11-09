import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_tool_phone as P


class E:
    paper_list = ["Daily Star", "Prothom Alo"]


def test_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DOC", str(tmp_path)); monkeypatch.setattr(P, "URLS_FILE", str(tmp_path / "u.json"))
    t = P.Tool(E())
    assert not t.api_set_url({"name": "Daily Star", "url": "javascript:x"})["ok"]
    assert t.api_set_url({"name": "Daily Star", "url": "https://epaper.thedailystar.net"})["ok"]
    assert t.api_papers({})["papers"][0]["url"].startswith("https://")
    assert t.api_set_url({"name": "Daily Star", "url": ""})["ok"] and t.api_papers({})["papers"][0]["url"] == ""
