import json, time
import pytest
import nab_accounts as A


@pytest.fixture(autouse=True)
def tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(A, "AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    A._fails.clear()
    A.logout()
    A.init("TESTPC")
    yield


def test_first_account_becomes_owner_and_password_is_not_stored():
    assert A.add_user("Sajeeb", "secret1", "viewer", actor_ok=True)["ok"]
    raw = open(A.USERS_FILE, encoding="utf-8").read()
    assert "secret1" not in raw
    assert json.loads(raw)["users"]["sajeeb"]["role"] == "owner"


def test_only_owner_pc_may_manage():
    assert not A.add_user("a", "secret1", actor_ok=False)["ok"]


def test_login_ok_and_wrong_password():
    A.add_user("amin", "secret1", actor_ok=True)
    assert not A.login("amin", "nope")["ok"]
    assert A.login("AMIN", "secret1")["ok"]
    assert A.current()["name"] == "amin"


def test_lockout_after_repeated_failures():
    A.add_user("amin", "secret1", actor_ok=True)
    for _ in range(4):
        A.login("amin", "bad")
    r = A.login("amin", "secret1")
    assert not r["ok"] and "Try again" in r["error"]


def test_roles_permissions():
    A.add_user("boss", "secret1", actor_ok=True)
    A.add_user("staff1", "secret1", "staff", actor_ok=True)
    A.add_user("view1", "secret1", "viewer", actor_ok=True)
    A.login("staff1", "secret1"); assert A.can("save") and A.can("send") and not A.can("manage")
    A.login("view1", "secret1"); assert not A.can("save") and not A.can("send")
    A.login("boss", "secret1"); assert A.can("manage")
    A.logout(); assert A.can("save")          # no account signed in = Telegram login, full access as before


def test_cannot_remove_last_owner():
    A.add_user("boss", "secret1", actor_ok=True)
    assert not A.delete_user("boss", actor_ok=True)["ok"]
    assert not A.set_role("boss", "staff", actor_ok=True)["ok"]
    assert not A.set_disabled("boss", True, actor_ok=True)["ok"]


def test_reset_forces_change_and_old_password_dies():
    A.add_user("boss", "secret1", actor_ok=True)
    A.add_user("amin", "secret1", actor_ok=True)
    A.reset_password("amin", "temp123", actor_ok=True)
    assert not A.login("amin", "secret1")["ok"]
    r = A.login("amin", "temp123"); assert r["ok"] and r["must_change"]
    assert A.change_own_password("temp123", "newpass1")["ok"]
    A.logout(); assert A.login("amin", "newpass1")["ok"]


def test_disabled_account_cannot_sign_in():
    A.add_user("boss", "secret1", actor_ok=True)
    A.add_user("amin", "secret1", actor_ok=True)
    A.set_disabled("amin", True, actor_ok=True)
    assert not A.login("amin", "secret1")["ok"]


def test_audit_log_records_and_filters():
    A.add_user("boss", "secret1", actor_ok=True)
    A.login("boss", "secret1"); A.audit("save", "Bank | 09 1-3 4x6")
    rows = A.audit_tail(10, action="save")
    assert rows and rows[0]["user"] == "boss"
    assert any(r["action"] == "account_add" for r in A.audit_tail(10))


def test_short_password_and_bad_name_rejected():
    assert not A.add_user("ab", "123", actor_ok=True)["ok"]
    assert not A.add_user("<script>", "secret1", actor_ok=True)["ok"]
