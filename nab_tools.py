# nab_tools.py — registry for the built-in tools (tracker, pdf, search, subs, shot, pr).
# Each tool is a module nab_tool_<name>.py exposing  class Tool:  __init__(self, engine)  and  api_<method>(self, a) -> dict.
# The web API routes  /api/<tool>_<method>  to  Tool.api_<method>.   Long jobs report through  engine.hub.emit("tool", tool=<name>, ...).
import importlib
import threading

TOOLS = {"tracker": "nab_tool_tracker", "pdf": "nab_tool_pdf", "search": "nab_tool_search", "subs": "nab_tool_subs", "shot": "nab_tool_shot", "pr": "nab_tool_pr", "ai": "nab_tool_ai", "hunt": "nab_tool_hunt", "wa": "nab_tool_wa", "phone": "nab_tool_phone"}
_inst = {}
_lock = threading.Lock()


def get(name, engine):
    with _lock:
        if name not in _inst:
            _inst[name] = importlib.import_module(TOOLS[name]).Tool(engine)
        return _inst[name]
