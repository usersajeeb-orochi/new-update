import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_every_engine_call_from_the_web_layer_exists():
    """acct_is_owner_pc was lost once (login screen broke): every self.e.<name>( used in nab_web must be defined somewhere."""
    defined = set()
    for fn in os.listdir(ROOT):
        if fn.startswith("nab_") and fn.endswith(".py"):
            defined |= set(re.findall(r"def (\w+)\(", _src(fn)))
    used = set(re.findall(r"self\.e\.(\w+)\(", _src("nab_web.py")))
    assert not (used - defined), used - defined


def test_session_end_and_block_commands_are_handled_on_the_pc():
    a = _src("nab_auth.py")
    for word in ('"sessionend"', '"block_self"', '"unblock_self"'):
        assert word in a
    assert "def lock_session" in _src("nab_engine_host.py")
    assert 'on("lock"' in _src(os.path.join("nab_ui", "main.js"))


def test_update_check_does_not_depend_on_the_rate_limited_api():
    u = _src("nab_update.py")
    assert "/releases/latest" in u and 'method="HEAD"' in u
