# nab_meta.py — one-line metadata:  "B1 1-3 4x6"  ->  page, columns, size
#
#   page     alphanumeric: 09, B1, B4, 01, 12 ...
#   columns  n-n with n in 1..8 and first <= second   (1-3, 2-6, 1-8)
#   size     inches x inches, decimals allowed        (4x6, 3.5x7)
#
# Tokens are recognised by SHAPE, so the order doesn't matter
# ("1-3 B1 4x6" is the same thing). Separators: spaces, commas, semicolons.
import re

_SIZE = re.compile(r"^(\d+(?:\.\d+)?)[xX×*](\d+(?:\.\d+)?)$")
_COLS = re.compile(r"^(\d+)[-–—](\d+)$")
_PAGE = re.compile(r"^[A-Za-z0-9]{1,6}$")
_SPLIT = re.compile(r"[\s,;]+")

MIN_COL, MAX_COL = 1, 8


def _fmt_num(s):
    """'4.0' -> '4', '03.50' -> '3.5' (filenames stay tidy)."""
    f = float(s)
    return str(int(f)) if f == int(f) else (f"{f:.3f}".rstrip("0").rstrip("."))


def parse(line):
    """Returns {"page","cols","size","errors":[...], "tokens":[(text, kind, ok, msg)], "ok": bool}.
    kind is 'page' | 'cols' | 'size' | 'bad'. Nothing is guessed: an invalid
    token is reported, never silently fixed."""
    out = {"page": "", "cols": "", "size": "", "errors": [], "tokens": [], "ok": False}
    toks = [t for t in _SPLIT.split((line or "").strip()) if t]
    seen = {}
    for t in toks:
        m = _SIZE.match(t)
        if m:
            w, h = float(m.group(1)), float(m.group(2))
            if w <= 0 or h <= 0:
                out["tokens"].append((t, "size", False, "size must be above 0"))
                out["errors"].append(f"size {t}: must be above 0")
            elif "size" in seen:
                out["tokens"].append((t, "size", False, "size given twice"))
                out["errors"].append("size given twice")
            else:
                out["size"] = f"{_fmt_num(m.group(1))}x{_fmt_num(m.group(2))}"
                seen["size"] = t
                out["tokens"].append((t, "size", True, ""))
            continue
        m = _COLS.match(t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            msg = ""
            if not (MIN_COL <= a <= MAX_COL and MIN_COL <= b <= MAX_COL):
                msg = f"columns are {MIN_COL}-{MAX_COL}"
            elif a > b:
                msg = "first column must not be bigger than the second"
            elif "cols" in seen:
                msg = "columns given twice"
            if msg:
                out["tokens"].append((t, "cols", False, msg))
                out["errors"].append(f"columns {t}: {msg}")
            else:
                out["cols"] = f"{a}-{b}"
                seen["cols"] = t
                out["tokens"].append((t, "cols", True, ""))
            continue
        if _PAGE.match(t):
            if "page" in seen:
                out["tokens"].append((t, "page", False, "page given twice"))
                out["errors"].append("page given twice")
            else:
                out["page"] = t
                seen["page"] = t
                out["tokens"].append((t, "page", True, ""))
            continue
        out["tokens"].append((t, "bad", False, "not a page, columns (1-3) or size (4x6)"))
        out["errors"].append(f"'{t}': not a page, columns (1-3) or size (4x6)")
    missing = [n for n, k in (("page", "page"), ("columns", "cols"), ("size", "size")) if not out[k]]
    if missing and toks and not out["errors"]:
        out["errors"].append("still needed: " + ", ".join(missing))
    out["missing"] = missing
    out["ok"] = not out["errors"] and not missing
    return out


def compose(page, cols, size):
    return " ".join(x for x in (page, cols, size) if x)
