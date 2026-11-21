# build_handoff.py - writes NAB_handoff.xlsx: everything a fresh Claude chat needs to know about NAB, read from the code.
# Usage: python handoff/build_handoff.py [path-to-nab-bot-repo]     (run at every version push, then upload the file to the Google Sheet)
import os, re, sys, ast, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notes
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = (sys.argv[1] if len(sys.argv) > 1 else "") or os.environ.get("NAB_BOT_DIR") or next(
    (p for p in (os.path.join(os.path.dirname(APP), "nab-bot"), "/home/claude/nab-bot") if os.path.isdir(p)), "")


def rd(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def version():
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', rd(os.path.join(APP, "nab_constants.py")))
    return m.group(1) if m else "?"


def purpose(path, text):
    """First meaningful line of the file header (comment/docstring)."""
    ext = os.path.splitext(path)[1]
    lines = text.splitlines()[:25]
    out = []
    if ext == ".py":
        j = "\n".join(lines).lstrip()
        if j.startswith(('"""', "'''")):
            q = j[:3]; body = j[3:].split(q)[0]
            out = [l.strip() for l in body.splitlines() if l.strip()]
        else:
            for l in lines:
                if l.startswith("#!") or l.startswith("# -*-"):
                    continue
                if l.startswith("#"):
                    out.append(l.lstrip("# ").strip())
                elif out or l.strip():
                    break
    elif ext in (".js", ".css"):
        j = "\n".join(lines).lstrip()
        if j.startswith("/*"):
            out = [re.sub(r"^\s*\*\s?", "", l).strip() for l in j[2:].split("*/")[0].splitlines()]
        else:
            for l in lines:
                if l.startswith("//"):
                    out.append(l.lstrip("/ ").strip())
                elif out or l.strip():
                    break
        out = [o for o in out if o and o not in ('"use strict";',)]
    elif ext == ".html":
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        out = [m.group(1).strip()] if m else []
    s = " ".join(x for x in out if x)[:300]
    return s


def files(base, pats, skip=()):
    rows = []
    for pat in pats:
        for p in sorted(glob.glob(os.path.join(base, pat))):
            if any(s in p for s in skip) or not os.path.isfile(p):
                continue
            t = rd(p)
            rows.append((os.path.relpath(p, base).replace("\\", "/"), t.count("\n") + 1, purpose(p, t)))
    return rows


def versions():
    txt = rd(os.path.join(APP, "README_v3.txt"))
    ent, cur = [], None
    for line in txt.splitlines():
        m = re.match(r"^v?(\d+\.\d+\.\d+)\b\s*[-:]?\s*(.*)$", line.strip())
        if m and not line.startswith((" ", "\t")):
            cur = [m.group(1), m.group(2)]
            ent.append(cur)
        elif cur and line.strip():
            cur[1] = (cur[1] + " " + line.strip().lstrip("*- ").strip()).strip()
    key = lambda v: tuple(int(x) for x in v[0].split("."))
    return [(v, d[:1500]) for v, d in sorted(ent, key=key, reverse=True)]


def features():
    txt = rd(os.path.join(APP, "riko_knowledge.md"))
    out, title, buf = [], None, []
    for l in txt.splitlines():
        if l.startswith("## "):
            if title:
                out.append((title, " ".join(buf).strip()[:2500]))
            title, buf = l[3:].strip(), []
        elif title and l.strip():
            buf.append(l.strip())
    if title:
        out.append((title, " ".join(buf).strip()[:2500]))
    return out


def tool_apis():
    rows = []
    tools = {}
    m = re.search(r"TOOLS\s*=\s*(\{.*?\})", rd(os.path.join(APP, "nab_tools.py")), re.S)
    if m:
        try:
            tools = ast.literal_eval(m.group(1))
        except Exception:
            pass
    for name, mod in tools.items():
        src = rd(os.path.join(APP, mod + ".py"))
        for mm in re.finditer(r"def (api_\w+)\(self[^)]*\):\s*\n(\s+(?:\"\"\"(.*?)\"\"\"|#\s*(.*)))?", src, re.S):
            d = (mm.group(3) or mm.group(4) or "").strip().splitlines()
            rows.append((name, name + "_" + mm.group(1)[4:], mod + ".py", (d[0] if d else "")[:200]))
    return rows


def engine_apis():
    src = rd(os.path.join(APP, "nab_web.py"))
    rows = []
    for mm in re.finditer(r"    def (\w+)\(self, a\):\s*\n(\s+(?:\"\"\"(.*?)\"\"\"|#\s*(.*)))?", src, re.S):
        d = (mm.group(3) or mm.group(4) or "").strip().splitlines()
        rows.append((mm.group(1), (d[0] if d else "")[:200]))
    return rows


def cloud():
    src = rd(os.path.join(BOT, "main.py")) if BOT else ""
    routes = []
    for mm in re.finditer(r"@app\.route\(\s*['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]*)\])?\s*\)\s*\ndef (\w+)\([^)]*\):\s*\n(\s+(?:\"\"\"(.*?)\"\"\"|#\s*(.*)))?", src, re.S):
        d = (mm.group(5) or mm.group(6) or "").strip().splitlines()
        routes.append((mm.group(1), (mm.group(2) or "GET").replace("'", "").replace('"', ""), mm.group(3), (d[0] if d else "")[:200]))
    for extra in ("web_admin.py", "m_api.py", "ai_proxy.py", "google_gate.py"):
        s = rd(os.path.join(BOT, extra)) if BOT else ""
        for mm in re.finditer(r"@\w+\.route\(\s*['\"]([^'\"]+)['\"](?:,\s*methods=\[([^\]]*)\])?\s*\)\s*\n(?:@[^\n]*\n)*def (\w+)", s):
            routes.append((mm.group(1), (mm.group(2) or "GET").replace("'", "").replace('"', ""), mm.group(3), extra))
    cmds = {}
    for mm in re.finditer(r"<code>(/[^<]+)</code>\s*[-–:]\s*([^\\\n\"<]*)", src):
        cmds.setdefault(mm.group(1).split()[0], (mm.group(1), mm.group(2).strip()))
    for mm in re.finditer(r"cmd (?:==|in) \(?((?:\"/\w+\",?\s*)+)\)?", src):
        for c in re.findall(r"/\w+", mm.group(1)):
            cmds.setdefault(c, (c, ""))
    doc = {m.group(1): (m.group(2) or "").strip().splitlines()[0] for m in re.finditer(r"def (\w+)\([^)]*\):\s*\n\s+(?:\"\"\"(.*?)\"\"\")?", src, re.S) if m.group(2)}
    for mm in re.finditer(r"cmd (?:==|in) \(?((?:\"/\w+\",?\s*)+)\)?[^\n]*:\s*\n[^\n]*?(handle_\w+|cmd_\w+)", src):
        for c in re.findall(r"/\w+", mm.group(1)):
            old = cmds.get(c)
            if (not old or not old[1]) and doc.get(mm.group(2)):
                cmds[c] = ((old[0] if old else c), doc[mm.group(2)][:160])
    envs = sorted(set(re.findall(r"environ(?:\.get)?\(?\[?\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']", src + "".join(rd(os.path.join(BOT, f)) for f in ("web_admin.py", "m_api.py", "ai_proxy.py", "google_gate.py", "durable_state.py") if BOT))))
    keys = sorted(set(re.findall(r"st(?:ate)?\.(?:get|setdefault|pop)\(\s*[\"'](\w+)[\"']", src)) | set(re.findall(r"state\[\s*[\"'](\w+)[\"']\s*\]", src)))
    return routes, sorted(cmds.values()), envs, keys


def defaults():
    out = []
    src = rd(os.path.join(APP, "nab_engine.py"))
    try:
        tree = ast.parse(src)
    except Exception:
        return out
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], "id", "").startswith("DEFAULT_"):
            try:
                v = ast.literal_eval(n.value)
            except Exception:
                continue
            nm = n.targets[0].id
            if isinstance(v, dict):
                for k, x in v.items():
                    out.append((nm, str(k), str(x)[:300]))
            elif isinstance(v, (list, tuple)):
                for x in v:
                    out.append((nm, "", str(x)[:300]))
    return out


def tests():
    rows = []
    for p in sorted(glob.glob(os.path.join(APP, "tests", "test_*.py"))):
        t = rd(p)
        names = re.findall(r"^def (test_\w+)", t, re.M)
        rows.append((os.path.basename(p), len(names), purpose(p, t) or ", ".join(n[5:] for n in names[:4])))
    if BOT:
        for p in sorted(glob.glob(os.path.join(BOT, "tests", "test_*.py"))):
            t = rd(p)
            rows.append(("nab-bot/" + os.path.basename(p), len(re.findall(r"^def (test_\w+)", t, re.M)), purpose(p, t)))
    return rows


def sheet(wb, title, header, rows, widths, first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title[:31]
    ws.append(list(header))
    for r in rows:
        ws.append([("" if c is None else (c if isinstance(c, (int, float)) else str(c)[:32000])) for c in r])
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="3B3F8F")
        c.alignment = Alignment(vertical="center")
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    return ws


def main():
    v = version()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb = Workbook()
    start = [("Generated", f"{now} from NAB v{v} (this sheet is refreshed at every version push)")] + notes.START
    sheet(wb, "START HERE", ("Topic", "Details"), start, (30, 140), first=True)
    sheet(wb, "Rules", ("Rule", "Details"), notes.RULES, (26, 140))
    vs = versions()
    sheet(wb, "Versions AUTO", ("Version", "What changed"), vs, (12, 150))
    sheet(wb, "Features AUTO", ("Area", "How it works (from riko_knowledge.md)"), features(), (30, 150))
    sheet(wb, "Architecture", ("Topic", "Details"), notes.ARCH, (32, 150))
    sheet(wb, "App modules AUTO", ("File", "Lines", "Purpose (file header)"), files(APP, ["*.py", "*.pyw", "*.cs", "*.bat", "*.iss"], skip=("handoff",)), (32, 8, 130))
    sheet(wb, "UI files AUTO", ("File", "Lines", "Purpose (file header)"), files(os.path.join(APP, "nab_ui"), ["*.js", "*.css", "*.html"], skip=("intro_3d.js",)), (30, 8, 130))
    sheet(wb, "Tool APIs AUTO", ("Tool", "API call (POST /api/...)", "Module", "Note"), tool_apis(), (14, 34, 26, 90))
    sheet(wb, "Engine APIs AUTO", ("API call (POST /api/...)", "Note"), engine_apis(), (36, 100))
    routes, cmds, envs, keys = cloud()
    sheet(wb, "Cloud routes AUTO", ("Path", "Methods", "Function", "Note"), routes, (30, 12, 28, 90))
    sheet(wb, "Telegram cmds AUTO", ("Command", "What it does"), cmds, (34, 110))
    sheet(wb, "Cloud config AUTO", ("Kind", "Name"), [("env var (value on Render, never here)", e) for e in envs] + [("state key", k) for k in keys], (36, 50))
    sheet(wb, "Defaults AUTO", ("Setting group", "Key", "Default"), defaults(), (26, 28, 100))
    sheet(wb, "Tests AUTO", ("File", "Tests", "Covers"), tests(), (34, 8, 110))
    sheet(wb, "Open items", ("Item", "Details", "Status"), notes.OPEN, (28, 120, 12))
    sheet(wb, "Ideas", ("Area", "Idea", "Status"), notes.IDEAS, (16, 130, 12))
    sheet(wb, "Update process", ("Step", "What to do"), notes.PROCESS, (8, 150))
    out = os.path.join(APP, "handoff", "NAB_handoff.xlsx")
    wb.save(out)
    print(out, "v" + v, {ws.title: ws.max_row - 1 for ws in wb.worksheets})


if __name__ == "__main__":
    main()
