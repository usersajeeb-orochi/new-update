import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


import pytest


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Tests must never call the live cloud bot (on a CI runner it is reachable and slow, on a laptop it is not):
    by default the cloud counts as unreachable. A test that needs an answer patches these again itself."""
    try:
        import nab_remote
        monkeypatch.setattr(nab_remote, "session_state", lambda *a, **k: None)
        monkeypatch.setattr(nab_remote, "is_blocked", lambda *a, **k: None)
    except Exception:
        pass
