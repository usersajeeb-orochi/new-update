# nab_mcp.py — lets Claude use NAB (Model Context Protocol).
#
#   * McpServer   a tiny loopback-only HTTP endpoint (http://127.0.0.1:6790/mcp) inside the running NAB.
#                 It exists only while the local switch is on in Settings > Claude, needs a secret token and refuses
#                 browsers (Origin header). No NAB sign-in is needed.
#   * bridge_main `NAB.exe --mcp`: stdio <-> that endpoint, for Claude Desktop (which can only start local programs).
#                 Claude Code and other HTTP-capable clients connect to the endpoint directly.
#
# The tools are the same ones Riko uses (nab_agent): search saved clips, today's numbers, health check, phone queue,
# schedules, and (only if allowed in Settings) making a report file. No tool deletes or changes clips.
import os
import sys
import json
import hmac
import secrets
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 6790
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_BODY = 64 * 1024

_S = {"type": "string"}
TOOLS = {
    "search_archive": {
        "description": "Search NAB's saved news clips by keyword and/or filters. Returns the total and up to 8 matching clips.",
        "schema": {"q": dict(_S, description="keywords"), "paper": dict(_S, description="newspaper name"), "cat": dict(_S, description="category"),
                   "date_from": dict(_S, description="DD-MM-YYYY or YYYY-MM-DD"), "date_to": dict(_S, description="DD-MM-YYYY or YYYY-MM-DD")},
        "write": False,
    },
    "list_filters": {"description": "List the newspapers and categories that exist in NAB's archive.", "schema": {}, "write": False},
    "daily_summary": {"description": "Today's (or a given day's) numbers: clips, papers, top categories, busiest hour, missing papers, findings.",
                      "schema": {"day": dict(_S, description="YYYY-MM-DD, default today")}, "write": False},
    "self_check": {"description": "Run NAB's health check (internet, Drive, Telegram, disk, backups) and list problems.", "schema": {}, "write": False},
    "phone_queue": {"description": "Entries the colleague sent from the phone that are not yet taken.", "schema": {}, "write": False},
    "scheduled_jobs": {"description": "NAB's scheduled reports and whether they are on.", "schema": {}, "write": False},
    "make_report": {"description": "Make a report file on this PC (Excel/PDF as set in NAB). Only offered when allowed in NAB Settings > Claude.",
                    "schema": {"range": dict(_S, description="today, yesterday, this_week, last_week, this_month, last_month"), "paper": _S, "cat": _S,
                               "client": _S, "template": _S}, "write": True},
}
INSTRUCTIONS = ("NAB is a newspaper-clipping app for a press-release office. Use search_archive to find saved clips, daily_summary for "
                "today's numbers and list_filters to see valid paper and category names. NAB must be open and signed in.")


# --------------------------------------------------------------------------------------------------- config file
def _dir():
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def cfg_path():
    return os.path.join(_dir(), "claude_mcp.json")


def load_cfg():
    try:
        with open(cfg_path(), "r", encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        c = {}
    return {"enabled": bool(c.get("enabled")), "reports": bool(c.get("reports")), "token": str(c.get("token") or ""),
            "port": int(c.get("port") or PORT), "cloud": bool(c.get("cloud", True))}


def save_cfg(c):
    c = dict(c)
    if not c.get("token"):
        c["token"] = secrets.token_urlsafe(32)
    tmp = cfg_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(tmp, cfg_path())
    return load_cfg()


# --------------------------------------------------------------------------------------------------- protocol
def _rpc_ok(i, result):
    return {"jsonrpc": "2.0", "id": i, "result": result}


def _rpc_err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


def tool_list(reports=True):
    out = []
    for n, t in TOOLS.items():
        if t["write"] and not reports:
            continue
        out.append({"name": n, "description": t["description"],
                    "inputSchema": {"type": "object", "properties": t["schema"]},
                    "annotations": {"readOnlyHint": not t["write"], "destructiveHint": False, "openWorldHint": False}})
    return out


def _text(obj, err=False):
    return {"content": [{"type": "text", "text": obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)}], "isError": bool(err)}


def handle(msg, call_tool, reports=True):
    """One JSON-RPC message in, one response dict out (None for notifications).
    call_tool(name, args) -> result dict, or raises; it is only used for tools/call."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _rpc_err(None, -32600, "invalid request")
    i, m = msg.get("id"), msg.get("method")
    if m is None or "id" not in msg:                       # notification or response from the client: nothing to answer
        return None
    p = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if m == "initialize":
        want = p.get("protocolVersion")
        try:
            from nab_constants import APP_VERSION as v
        except Exception:
            v = ""
        return _rpc_ok(i, {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[1], "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": "NAB", "version": v}, "instructions": INSTRUCTIONS})
    if m == "ping":
        return _rpc_ok(i, {})
    if m == "tools/list":
        return _rpc_ok(i, {"tools": tool_list(reports)})
    if m == "tools/call":
        name = p.get("name")
        t = TOOLS.get(name)
        if not t or (t["write"] and not reports):
            return _rpc_err(i, -32602, "unknown tool " + str(name))
        args = p.get("arguments") if isinstance(p.get("arguments"), dict) else {}
        try:
            r = call_tool(name, args)
        except Exception as e:
            logging.exception("mcp tool " + str(name))
            return _rpc_ok(i, _text("NAB could not do that: " + str(e)[:200], True))
        if isinstance(r, dict) and (r.get("error") or r.get("ok") is False):
            return _rpc_ok(i, _text(r.get("error") or r.get("text") or "failed", True))
        return _rpc_ok(i, _text(r))
    return _rpc_err(i, -32601, "method not found: " + str(m))


# --------------------------------------------------------------------------------------------------- server (inside NAB)
class McpServer:
    def __init__(self, engine):
        self.engine = engine
        self.httpd = None
        self.error = ""
        self._agent = None
        self._lock = threading.Lock()

    def running(self):
        return self.httpd is not None

    def _call(self, name, args):
        import nab_agent
        with self._lock:
            if self._agent is None:
                self._agent = nab_agent.Agent(self.engine, None, None)
            a = self._agent
        if TOOLS[name]["write"]:
            return a.do_write(name, args)
        return a.run_tool(name, args)

    def start(self):
        c = load_cfg()
        if not c["enabled"] or self.httpd:
            return self.running()
        if not c["token"]:
            c = save_cfg(c)
        srv = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "NAB-MCP"

            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _ok(self):
                host = (self.headers.get("Host") or "").split(":")[0].lower()
                if host not in ("127.0.0.1", "localhost") or self.headers.get("Origin"):
                    return False                                   # a web page in a browser can never talk to this
                cur = load_cfg()
                if not cur["enabled"] or not cur["token"]:
                    return False
                got = (self.headers.get("Authorization") or "")
                return got.startswith("Bearer ") and hmac.compare_digest(got[7:], cur["token"])

            def do_GET(self):
                self._send(405 if self._ok() else 403, b"", "text/plain")

            do_DELETE = do_GET

            def do_POST(self):
                try:
                    if not self._ok() or self.path.split("?")[0] != "/mcp":
                        return self._send(403, b"forbidden", "text/plain")
                    n = int(self.headers.get("Content-Length") or 0)
                    if n <= 0 or n > MAX_BODY:
                        return self._send(413, b"bad size", "text/plain")
                    msg = json.loads(self.rfile.read(n).decode("utf-8"))
                    reports = load_cfg()["reports"]
                    if isinstance(msg, list):
                        out = [r for r in (handle(x, srv._call, reports) for x in msg) if r is not None]
                    else:
                        out = handle(msg, srv._call, reports)
                    if not out:
                        return self._send(202)
                    self._send(200, json.dumps(out).encode("utf-8"))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception:
                    logging.exception("mcp request")
                    try:
                        self._send(400, json.dumps(_rpc_err(None, -32700, "parse error")).encode("utf-8"))
                    except Exception:
                        pass

        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", c["port"]), H)
            self.httpd.daemon_threads = True
            threading.Thread(target=self.httpd.serve_forever, daemon=True, name="NAB-MCP").start()
            self.error = ""
            logging.info(f"MCP: listening on 127.0.0.1:{c['port']}")
        except OSError as e:
            self.httpd = None
            self.error = f"port {c['port']} is busy ({e.strerror or e})"
            logging.error("MCP: " + self.error)
        return self.running()

    def stop(self):
        h, self.httpd = self.httpd, None
        if h:
            try:
                h.shutdown()
                h.server_close()
            except Exception:
                pass


# --------------------------------------------------------------------------------------------------- online connector worker
class CloudWorker:
    """Claude (claude.ai) -> cloud bot -> this PC. We long-poll the bot for jobs, run the read-only tool on the local archive
    and send the answer back. Outbound only: nothing on this PC listens. Switch: Settings > Claude (on by default)."""

    def __init__(self, engine):
        self.engine = engine
        self.agent = None
        self.polling = False
        self._t = None

    def start(self):
        if self._t is None:
            self._t = threading.Thread(target=self._loop, daemon=True, name="NAB-ClaudeWorker")
            self._t.start()

    def _run(self, job):
        name = job.get("tool")
        t = TOOLS.get(name)
        if not t or t["write"]:
            return {"error": "tool not allowed: " + str(name)}
        import nab_agent
        if self.agent is None:
            self.agent = nab_agent.Agent(self.engine, None, None)
        try:
            r = self.agent.run_tool(name, job.get("args") if isinstance(job.get("args"), dict) else {})
        except Exception as e:
            logging.exception("claude job " + str(name))
            return {"error": str(e)[:160]}
        if len(json.dumps(r, default=str)) > 250000:
            return {"error": "answer too large"}
        return r

    def _loop(self):
        import time
        import urllib.request
        import urllib.parse
        import nab_remote
        try:
            from nab_telegram import PC_NAME
        except Exception:
            PC_NAME = os.environ.get("COMPUTERNAME", "PC")
        while True:
            try:
                base = nab_remote.cloud_url()
                if not load_cfg()["cloud"] or not base:
                    self.polling = False
                    time.sleep(20)
                    continue
                req = urllib.request.Request(base + "/pc/jobs?pc=" + urllib.parse.quote(PC_NAME),
                                             headers=dict(nab_remote.sign_headers(PC_NAME), **{"User-Agent": "NAB/3"}))
                with urllib.request.urlopen(req, timeout=40) as r:
                    jobs = (json.loads(r.read().decode("utf-8")) or {}).get("jobs") or []
                self.polling = True
                for j in jobs:
                    res = self._run(j)
                    body = urllib.parse.urlencode({"pc": PC_NAME, "id": j.get("id", ""), "result": json.dumps(res, default=str)}).encode()
                    post = urllib.request.Request(base + "/pc/job_result", data=body, method="POST",
                                                  headers=dict(nab_remote.sign_headers(PC_NAME), **{"User-Agent": "NAB/3"}))
                    urllib.request.urlopen(post, timeout=20).close()
            except Exception as e:
                self.polling = False
                logging.info("claude worker: " + str(e)[:100])
                time.sleep(20)


# --------------------------------------------------------------------------------------------------- stdio bridge (NAB.exe --mcp)
def _std_streams():
    """NAB.exe is a windowed program, so Python gives it no stdin/stdout: open the inherited Windows pipes ourselves."""
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    import ctypes
    import msvcrt
    k = ctypes.windll.kernel32
    k.GetStdHandle.restype = ctypes.c_void_p
    hin, hout = k.GetStdHandle(-10), k.GetStdHandle(-11)
    return (os.fdopen(msvcrt.open_osfhandle(hin, os.O_RDONLY), "rb"), os.fdopen(msvcrt.open_osfhandle(hout, os.O_WRONLY), "wb"))


def _forward(msg, cfg):
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{cfg['port']}/mcp", data=json.dumps(msg).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["token"]})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    return json.loads(body.decode("utf-8")) if body else None


def bridge_call(msg, cfg=None):
    """initialize / tools/list are answered here (so Claude always sees the tools); tools/call goes to the running NAB."""
    cfg = cfg or load_cfg()
    if isinstance(msg, dict) and msg.get("method") == "tools/call" and "id" in msg:
        if not cfg["enabled"] or not cfg["token"]:
            return _rpc_ok(msg["id"], _text("The Claude connection is switched off. In NAB open Settings > Claude and turn it on.", True))
        try:
            return _forward(msg, cfg)
        except Exception:
            return _rpc_ok(msg["id"], _text("NAB is not open on this PC (or not reachable). Open NAB and sign in, then try again.", True))
    return handle(msg, lambda *a: {}, cfg["reports"])


def bridge_main():
    fin, fout = _std_streams()
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
            out = bridge_call(msg)
        except Exception as e:
            out = _rpc_err(None, -32700, "parse error: " + str(e)[:80])
        if out is not None:
            fout.write(json.dumps(out, ensure_ascii=False).encode("utf-8") + b"\n")
            fout.flush()


# --------------------------------------------------------------------------------------------------- setup helpers (Settings page)
def launch_command():
    """(command, args) that starts the stdio bridge."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mcp"]
    return sys.executable, [os.path.join(os.path.dirname(os.path.abspath(__file__)), "NAB_entry.pyw"), "--mcp"]


def desktop_config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Claude", "claude_desktop_config.json")


def install_desktop():
    """Add NAB to Claude Desktop's config (keeps every other entry, writes a .bak first). Returns (ok, message)."""
    p = desktop_config_path()
    try:
        data = {}
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                txt = f.read().strip()
            data = json.loads(txt) if txt else {}
            if not isinstance(data, dict):
                return False, "Claude Desktop's config file is not what NAB expected, so it was left alone."
            with open(p + ".bak", "w", encoding="utf-8") as f:
                f.write(txt)
        cmd, args = launch_command()
        data.setdefault("mcpServers", {})["nab"] = {"command": cmd, "args": args}
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True, "Added to Claude Desktop. Fully quit and reopen Claude Desktop."
    except Exception as e:
        return False, "Could not write Claude Desktop's config: " + str(e)[:120]


def claude_code_command():
    c = load_cfg()
    return f'claude mcp add --transport http nab http://127.0.0.1:{c["port"]}/mcp --header "Authorization: Bearer {c["token"]}"'
