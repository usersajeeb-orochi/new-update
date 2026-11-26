import os, sys, json, threading, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nab_mcp


def _cfg(tmp_path, monkeypatch, **kw):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    c = nab_mcp.load_cfg()
    c.update(kw)
    return nab_mcp.save_cfg(c)


def test_initialize_and_tools_list():
    r = nab_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}, lambda *a: {})
    assert r["result"]["protocolVersion"] == "2025-06-18" and r["result"]["serverInfo"]["name"] == "NAB"
    names = [t["name"] for t in nab_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, lambda *a: {}, reports=False)["result"]["tools"]]
    assert "search_archive" in names and "make_report" not in names
    names = [t["name"] for t in nab_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, lambda *a: {}, reports=True)["result"]["tools"]]
    assert "make_report" in names


def test_notification_gets_no_answer_and_unknown_method_errors():
    assert nab_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, lambda *a: {}) is None
    assert nab_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"}, lambda *a: {})["error"]["code"] == -32601


def test_tool_call_results_and_errors():
    ok = nab_mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "list_filters", "arguments": {}}}, lambda n, a: {"papers": ["X"]})
    assert ok["result"]["isError"] is False and "X" in ok["result"]["content"][0]["text"]
    bad = nab_mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "search_archive", "arguments": {}}}, lambda n, a: {"error": "give a keyword"})
    assert bad["result"]["isError"] is True
    boom = nab_mcp.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "self_check"}}, lambda n, a: 1 / 0)
    assert boom["result"]["isError"] is True
    assert nab_mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "make_report"}}, lambda n, a: {}, reports=False)["error"]


class _Eng:
    authorized = True


def _post(port, body, token="", extra=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    h.update(extra or {})
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=json.dumps(body).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def test_server_needs_token_blocks_browsers_and_locked_nab(tmp_path, monkeypatch):
    c = _cfg(tmp_path, monkeypatch, enabled=True, port=0 + 46790)
    eng = _Eng()
    s = nab_mcp.McpServer(eng)
    monkeypatch.setattr(s, "_call", lambda n, a: {"papers": []} if eng.authorized else (_ for _ in ()).throw(RuntimeError("locked")))
    assert s.start()
    try:
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert _post(46790, msg)[0] == 403                                        # no token
        assert _post(46790, msg, "wrong")[0] == 403
        assert _post(46790, msg, c["token"], {"Origin": "https://evil.example"})[0] == 403   # browser page
        st, body = _post(46790, msg, c["token"])
        assert st == 200 and "search_archive" in body.decode()
        st, body = _post(46790, {"jsonrpc": "2.0", "method": "notifications/initialized"}, c["token"])
        assert st == 202
        nab_mcp.save_cfg(dict(nab_mcp.load_cfg(), enabled=False))                 # switched off: refused at once
        assert _post(46790, msg, c["token"])[0] == 403
    finally:
        s.stop()


def test_worker_runs_only_read_tools_and_needs_no_sign_in(tmp_path, monkeypatch):
    class Eng:
        authorized = False                                     # not signed in: still answers
    w = nab_mcp.CloudWorker(Eng())
    import nab_agent
    monkeypatch.setattr(nab_agent.Agent, "run_tool", lambda self, n, a: {"n": n, "a": a})
    assert w._run({"tool": "list_filters", "args": {"q": 1}}) == {"n": "list_filters", "a": {"q": 1}}
    assert "not allowed" in w._run({"tool": "make_report", "args": {}})["error"]
    assert "not allowed" in w._run({"tool": "rm_everything"})["error"]


def test_bridge_answers_locally_and_reports_nab_closed(tmp_path, monkeypatch):
    c = _cfg(tmp_path, monkeypatch, enabled=True, port=46799)                    # nothing listens there
    assert "tools" in nab_mcp.bridge_call({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, c)["result"]
    r = nab_mcp.bridge_call({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_filters"}}, c)
    assert r["result"]["isError"] and "not open" in r["result"]["content"][0]["text"]
    off = dict(c, enabled=False)
    assert "switched off" in nab_mcp.bridge_call({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_filters"}}, off)["result"]["content"][0]["text"]


def test_install_desktop_keeps_other_servers(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = nab_mcp.desktop_config_path()
    os.makedirs(os.path.dirname(p))
    json.dump({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}, open(p, "w"))
    ok, _ = nab_mcp.install_desktop()
    d = json.load(open(p))
    assert ok and d["mcpServers"]["other"] == {"command": "x"} and "nab" in d["mcpServers"] and d["theme"] == "dark"
    assert os.path.exists(p + ".bak")
