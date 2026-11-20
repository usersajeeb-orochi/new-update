# Login authority lives on the cloud: local files cannot grant, extend or lift anything.
import time
import nab_session, nab_remote, nab_access


def _cloud(monkeypatch, answer):
    monkeypatch.setattr(nab_remote, "available", lambda: True)
    monkeypatch.setattr(nab_remote, "session_state", lambda pc, op="touch", grace=0: answer)


def test_local_remember_cannot_override_cloud(tmp_path, monkeypatch):
    nab_session.init(str(tmp_path), "PC1")
    _cloud(monkeypatch, {"state": "none"})
    d = nab_session.load(); d["remember_until"] = time.time() + 86400; nab_session.save(d)   # a forged "remembered" file
    assert nab_session.check(10)[0] is None


def test_cloud_yes_then_cloud_down_is_bounded(tmp_path, monkeypatch):
    nab_session.init(str(tmp_path), "PC1")
    _cloud(monkeypatch, {"state": "ok", "kind": "remember", "until": time.time() + 3600})
    assert nab_session.check(10)[0] == "remember"
    _cloud(monkeypatch, None)                                       # cloud unreachable
    assert nab_session.check(10)[0] == "remember"                    # a minute later: still trusted
    d = nab_session.load(); d["cloud"]["at"] = time.time() - nab_session.OFFLINE_OK - 5; nab_session.save(d)
    assert nab_session.check(10)[0] is None                          # a stale cache grants nothing


def test_deleting_the_file_never_grants(tmp_path, monkeypatch):
    nab_session.init(str(tmp_path), "PC1")
    _cloud(monkeypatch, None)
    assert nab_session.check(10)[0] is None
    nab_session.clear()
    assert nab_session.check(10)[0] is None


def test_heartbeat_close_and_block(tmp_path, monkeypatch):
    nab_session.init(str(tmp_path), "PC1")
    _cloud(monkeypatch, {"state": "none"})
    assert nab_session.heartbeat(True)["state"] == "revoked"         # /close on the server
    assert nab_session.heartbeat(False)["state"] == "idle"           # an account session is not ended by a missing approval
    _cloud(monkeypatch, {"state": "blocked"})
    assert nab_session.heartbeat(False)["state"] == "revoked"        # but a block ends it
    _cloud(monkeypatch, None)
    assert nab_session.heartbeat(True)["state"] == "offline"
    dl = time.time() + 7200
    _cloud(monkeypatch, {"state": "ok", "kind": "timed", "until": dl, "deadline": dl})
    assert nab_session.heartbeat(True) == {"state": "ok", "deadline": dl}   # /extend arrives as a new deadline


def test_cloud_block_wins_over_a_deleted_local_file(monkeypatch):
    saved = {}
    monkeypatch.setattr(nab_access, "_load_blocked_pcs", lambda: dict(saved))
    monkeypatch.setattr(nab_access, "_save_blocked_pcs", lambda b: saved.update(b))
    monkeypatch.setattr(nab_remote, "is_blocked", lambda pc: True)
    assert nab_access.blocked_now("PC1") is True and "PC1" in saved   # local copy re-created
    monkeypatch.setattr(nab_remote, "is_blocked", lambda pc: False)
    assert nab_access.blocked_now("PC1") is False                     # /unblock on the server lifts the local copy too
    monkeypatch.setattr(nab_remote, "is_blocked", lambda pc: None)
    saved["PC1"] = {"x": 1}
    assert nab_access.blocked_now("PC1") is True                      # cloud down: the local block still holds
