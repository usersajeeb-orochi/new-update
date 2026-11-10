import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import nab_accounts as A
import nab_google as G


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "USERS_FILE", str(tmp_path / "u.json")); monkeypatch.setattr(A, "AUDIT_FILE", str(tmp_path / "a.jsonl"))
    monkeypatch.setattr(G, "CFG", str(tmp_path / "g.json")); monkeypatch.setattr(G, "DOC", str(tmp_path))
    A._fails.clear()


def test_anyone_joins_then_block():
    assert A.add_user("sajeeb", "secret1", actor_ok=True)["ok"]
    r = A.login_google("New.Person@Gmail.com", "New Person")
    assert r["ok"] and r["user"]["role"] == "viewer"                       # first sign-in creates a viewer
    assert [u["email"] for u in A.list_users() if u["email"]] == ["new.person@gmail.com"]
    assert A.login_google("new.person@gmail.com")["ok"] and len(A.list_users()) == 2   # same person, no duplicate
    assert not A.block_email("new.person@gmail.com", True, actor_ok=False)["ok"]       # owner only
    assert A.block_email("new.person@gmail.com", True, actor_ok=True)["ok"]
    assert not A.login_google("new.person@gmail.com")["ok"]
    assert A.block_email("never@gmail.com", True, actor_ok=True)["ok"] and not A.login_google("never@gmail.com")["ok"]   # block before they ever joined
    assert A.block_email("new.person@gmail.com", False, actor_ok=True)["ok"] and A.login_google("new.person@gmail.com")["ok"]
    assert not A.login_google("")["ok"]
    assert not A.login("new.person@gmail.com", "")["ok"]                    # Google accounts have no password


class Resp:
    def __init__(s, j): s.j = j
    def json(s): return s.j


class Http:
    def __init__(s, j): s.j = j
    def get(s, *a, **k): return Resp(s.j)


def test_token_verify_rules():
    ok = {"aud": "cid", "email": "A@B.com", "email_verified": "true"}
    assert G.verify_id_token("t", "cid", Http(ok)) == ("a@b.com", "")
    assert G.verify_id_token("t", "cid", Http(dict(ok, aud="other")))[0] == ""           # token made for another app
    assert G.verify_id_token("t", "cid", Http(dict(ok, email_verified="false")))[0] == ""


def test_config_keeps_secret_and_begin_needs_client_id():
    assert not G.configured() and not G.begin()["ok"]
    G.save_config("id1", "sec1"); G.save_config("id2")
    assert G.config() == {"client_id": "id2", "client_secret": "sec1"} and G.configured()


def test_poll_consumes_result():
    G._state.update(s="ok", email="x@y.com", error="")
    assert G.poll()["email"] == "x@y.com" and G.poll()["state"] == "idle"
