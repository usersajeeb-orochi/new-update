import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_secrets
import nab_access
import nab_session
import nab_accounts


def test_sign_detects_edit():
    d = nab_secrets.sign({"a": 1}, "x")
    assert nab_secrets.valid(d, "x")
    d["a"] = 2
    assert not nab_secrets.valid(d, "x")
    assert not nab_secrets.valid(nab_secrets.sign({"a": 1}, "x"), "y")


def test_blocked_file_edit_is_not_trusted(tmp_path, monkeypatch):
    f = tmp_path / "b.json"
    monkeypatch.setattr(nab_access, "BLOCKED_PCS_FILE", str(f))
    monkeypatch.setattr(nab_secrets, "reg_get", lambda n: "")
    monkeypatch.setattr(nab_secrets, "reg_set", lambda n, v: True)
    nab_access._save_blocked_pcs({"PC1": {"user": "x"}})
    assert "PC1" in nab_access._load_blocked_pcs()
    d = json.load(open(f))
    d.pop("PC1")                                  # someone removes the block by hand
    json.dump(d, open(f, "w"))
    assert nab_access._load_blocked_pcs()         # not trusted: this PC stays blocked


def test_blocked_file_deleted_comes_back_from_registry(tmp_path, monkeypatch):
    f = tmp_path / "b.json"
    store = {}
    monkeypatch.setattr(nab_access, "BLOCKED_PCS_FILE", str(f))
    monkeypatch.setattr(nab_secrets, "reg_get", lambda n: store.get(n, ""))
    monkeypatch.setattr(nab_secrets, "reg_set", lambda n, v: store.__setitem__(n, v) or True)
    nab_access._save_blocked_pcs({"PC1": {"user": "x"}})
    os.remove(f)
    assert "PC1" in nab_access._load_blocked_pcs()


def test_session_forged_remember_is_ignored(tmp_path):
    nab_session.init(str(tmp_path), "PC1")
    nab_session.remember(time.time() + 3600)
    assert nab_session.check(0)[0] == "remember"
    p = tmp_path / "nab_session.json"
    d = json.load(open(p))
    d["remember_until"] = time.time() + 10 ** 9
    json.dump(d, open(p, "w"))
    assert nab_session.check(0)[0] is None


def test_session_remember_is_capped(tmp_path):
    nab_session.init(str(tmp_path), "PC1")
    nab_session.remember(time.time() + 10 ** 9)
    assert nab_session.load()["remember_until"] <= time.time() + nab_session.MAX_REMEMBER + 5


def test_accounts_role_edit_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(nab_accounts, "USERS_FILE", str(tmp_path / "u.json"))
    monkeypatch.setattr(nab_secrets, "reg_get", lambda n: "1")        # signing already switched on
    monkeypatch.setattr(nab_secrets, "reg_set", lambda n, v: True)
    nab_accounts._save({"v": 1, "users": {"bob": {"role": "viewer"}}})
    assert nab_accounts._load()["users"]["bob"]["role"] == "viewer"
    d = json.load(open(tmp_path / "u.json"))
    d["users"]["bob"]["role"] = "owner"
    json.dump(d, open(tmp_path / "u.json", "w"))
    assert nab_accounts._load()["users"] == {}
    assert nab_accounts.tampered()
