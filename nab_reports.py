# nab_reports.py - client coverage reports built from the clip archive (free: reportlab + openpyxl, both already in NAB).
#
# A report = cover page (client, period, totals by newspaper / category / day) + one page per clip with a caption.
# Templates (title, colour, footer, logo) live in Documents\nab_report_templates.json and sync from the owner PC.
import os
import re
import io
import json
import time
import logging
import datetime
import collections

DOC = os.path.join(os.path.expanduser("~"), "Documents")
TEMPLATES_FILE = os.path.join(DOC, "nab_report_templates.json")
OUT_DIR = os.path.join(DOC, "NAB Reports")

DEFAULT_TEMPLATE = {"name": "Standard", "title": "Media Coverage Report", "client": "", "accent": "#2f5fd0", "footer": "", "logo": "",
                    "cover": True, "per_page": 1, "caption": True}


# ------------------------------------------------------------------ templates
def load_templates():
    try:
        with open(TEMPLATES_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("templates"), list) and d["templates"]:
            return [clean_template(t) for t in d["templates"]]
    except Exception:
        pass
    return [dict(DEFAULT_TEMPLATE)]


def clean_template(t):
    o = dict(DEFAULT_TEMPLATE)
    o["name"] = re.sub(r"\s+", " ", str(t.get("name") or "Standard")).strip()[:40] or "Standard"
    o["title"] = str(t.get("title") or DEFAULT_TEMPLATE["title"])[:80]
    o["client"] = str(t.get("client") or "")[:80]
    acc = str(t.get("accent") or "")
    o["accent"] = acc if re.fullmatch(r"#[0-9a-fA-F]{6}", acc) else DEFAULT_TEMPLATE["accent"]
    o["footer"] = str(t.get("footer") or "")[:120]
    o["logo"] = str(t.get("logo") or "")
    o["cover"] = bool(t.get("cover", True))
    o["per_page"] = 2 if int(t.get("per_page") or 1) == 2 else 1
    o["caption"] = bool(t.get("caption", True))
    return o


def save_templates(items):
    seen, out = set(), []
    for t in items or []:
        c = clean_template(t)
        if c["name"].lower() not in seen:
            seen.add(c["name"].lower())
            out.append(c)
    out = out or [dict(DEFAULT_TEMPLATE)]
    os.makedirs(os.path.dirname(TEMPLATES_FILE), exist_ok=True)
    tmp = TEMPLATES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "templates": out}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TEMPLATES_FILE)
    return out


def get_template(name):
    ts = load_templates()
    return next((t for t in ts if t["name"].lower() == (name or "").lower()), ts[0])


# ------------------------------------------------------------------ date ranges
def resolve_range(kind, d_from="", d_to="", today=None):
    t = today or datetime.date.today()
    iso = lambda d: d.isoformat()
    if kind == "today":
        return iso(t), iso(t)
    if kind == "yesterday":
        y = t - datetime.timedelta(days=1)
        return iso(y), iso(y)
    if kind == "last7":
        return iso(t - datetime.timedelta(days=6)), iso(t)
    if kind == "last30":
        return iso(t - datetime.timedelta(days=29)), iso(t)
    if kind == "this_month":
        return iso(t.replace(day=1)), iso(t)
    if kind == "last_month":
        e = t.replace(day=1) - datetime.timedelta(days=1)
        return iso(e.replace(day=1)), iso(e)
    return d_from or "", d_to or ""


# ------------------------------------------------------------------ report
def _hex(c):
    from reportlab.lib.colors import HexColor
    return HexColor(c)


def _sort_key(r):
    return (r.get("date") or "", r.get("paper") or "", r.get("page") or "", r.get("pos") or "")


def build_report(rows, tpl, period=("", ""), user="", out_dir=None, name_hint=""):
    """rows: clip dicts from Archive.search. Returns {ok, path, xlsx, n, pages}."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    rows = sorted([r for r in rows if os.path.isfile(r["path"])], key=_sort_key)
    if not rows:
        return {"ok": False, "error": "No clips match, so there is nothing to put in the report."}
    out_dir = out_dir or os.path.join(OUT_DIR, time.strftime("%Y-%m-%d"))
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "", (name_hint or tpl.get("client") or tpl["name"])).strip() or "Report"
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    pdf_path = os.path.join(out_dir, f"{safe} - {tpl['title']} {stamp}.pdf")
    W, H = A4
    M = 40
    acc = _hex(tpl["accent"])
    pageno = [0]
    c = canvas.Canvas(pdf_path, pagesize=A4)
    c.setTitle(f"{tpl['title']} - {safe}")
    c.setAuthor("NAB")

    def footer():
        pageno[0] += 1
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(.45, .45, .45)
        if tpl["footer"]:
            c.drawString(M, 22, tpl["footer"])
        c.drawRightString(W - M, 22, f"Page {pageno[0]}")
        c.setStrokeColor(acc)
        c.setLineWidth(1.2)
        c.line(M, 34, W - M, 34)

    d1, d2 = period
    pl = (f"{d1} to {d2}" if d1 and d2 and d1 != d2 else (d1 or d2 or "All dates"))
    # ---- cover
    if tpl["cover"]:
        c.setFillColor(acc)
        c.rect(0, H - 150, W, 150, fill=1, stroke=0)
        y_logo = H - 40
        if tpl["logo"] and os.path.isfile(tpl["logo"]):
            try:
                ir = ImageReader(tpl["logo"])
                iw, ih = ir.getSize()
                sc = min(120 / iw, 60 / ih)
                c.drawImage(ir, W - M - iw * sc, H - 40 - ih * sc, iw * sc, ih * sc, mask="auto")
            except Exception as e:
                logging.error(f"report logo: {e}")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(M, H - 80, tpl["title"])
        c.setFont("Helvetica", 14)
        c.drawString(M, H - 106, tpl["client"] or safe)
        c.setFont("Helvetica", 11)
        c.drawString(M, H - 128, pl)
        y = H - 190
        by_paper = collections.Counter(r["paper"] or "Unknown" for r in rows)
        by_cat = collections.Counter(r["cat"] or "Uncategorised" for r in rows)
        by_day = collections.Counter(r["date"] or "?" for r in rows)
        c.setFillColorRGB(.1, .1, .1)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(M, y, f"{len(rows)} clip{'s' if len(rows) != 1 else ''} from {len(by_paper)} newspaper{'s' if len(by_paper) != 1 else ''}")
        y -= 28

        def table(title, counter, y):
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(acc)
            c.drawString(M, y, title.upper())
            y -= 6
            c.setStrokeColorRGB(.8, .8, .8)
            c.line(M, y, W - M, y)
            y -= 14
            c.setFillColorRGB(.15, .15, .15)
            c.setFont("Helvetica", 10)
            for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:14]:
                c.drawString(M + 4, y, k[:60])
                c.drawRightString(W - M - 4, y, str(v))
                y -= 14
            if len(counter) > 14:
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(M + 4, y, f"and {len(counter) - 14} more")
                y -= 14
            return y - 12
        y = table("By newspaper", by_paper, y)
        y = table("By category", by_cat, y)
        if y > 140:
            y = table("By day", dict(sorted(by_day.items())), y)
        if user:
            c.setFont("Helvetica", 8)
            c.setFillColorRGB(.5, .5, .5)
            c.drawString(M, 46, f"Prepared by {user} on {time.strftime('%d %B %Y, %H:%M')}")
        footer()
        c.showPage()
    # ---- clips
    slots = tpl["per_page"]
    top, bottom = H - M, 52
    slot_h = (top - bottom) / slots
    for i, r in enumerate(rows):
        pos = i % slots
        if pos == 0 and i:
            footer()
            c.showPage()
        y_top = top - pos * slot_h
        try:
            ir = ImageReader(r["path"])
            iw, ih = ir.getSize()
        except Exception as e:
            logging.error(f"report image {r['path']}: {e}")
            continue
        cap_h = 30 if tpl["caption"] else 0
        box_w, box_h = W - 2 * M, slot_h - cap_h - 14
        sc = min(box_w / iw, box_h / ih, 1.6)
        dw, dh = iw * sc, ih * sc
        x = M + (box_w - dw) / 2
        c.drawImage(ir, x, y_top - dh, dw, dh)
        c.setStrokeColorRGB(.85, .85, .85)
        c.rect(x, y_top - dh, dw, dh, fill=0, stroke=1)
        if tpl["caption"]:
            c.setFillColorRGB(.1, .1, .1)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(M, y_top - dh - 15, (r["paper"] or r["name"])[:70])
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(.35, .35, .35)
            dm = ""
            if r["date"]:
                try:
                    dm = datetime.date.fromisoformat(r["date"]).strftime("%d %b %Y")
                except Exception:
                    dm = r["date"]
            bits = [dm, f"Page {r['page']}" if r["page"] else "", f"Pos {r['pos']}" if r["pos"] else "", f"Size {r['size']}" if r["size"] else "", r["cat"]]
            c.drawString(M, y_top - dh - 28, "   |   ".join(b for b in bits if b)[:130])
    footer()
    c.showPage()
    c.save()
    xlsx = _summary_xlsx(rows, out_dir, safe, tpl, pl)
    return {"ok": True, "path": pdf_path, "xlsx": xlsx, "n": len(rows), "pages": pageno[0]}


def _summary_xlsx(rows, out_dir, safe, tpl, period_label):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append([tpl["title"]])
        ws["A1"].font = Font(bold=True, size=14)
        ws.append([tpl["client"] or safe, period_label])
        ws.append([])
        for title, key in (("Newspaper", "paper"), ("Category", "cat"), ("Date", "date")):
            ws.append([title, "Clips"])
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=tpl["accent"].lstrip("#"))
            for k, v in sorted(collections.Counter(r[key] or "-" for r in rows).items(), key=lambda kv: (-kv[1], kv[0])):
                ws.append([k, v])
            ws.append([])
        ws.column_dimensions["A"].width = 36
        ws.column_dimensions["B"].width = 12
        cl = wb.create_sheet("Clips")
        cl.append(["Paper", "Date", "Page", "Position", "Size", "Category", "Saved by", "KB", "File"])
        for cell in cl[1]:
            cell.font = Font(bold=True)
        for r in rows:
            cl.append([r["paper"], r["date"], r["page"], r["pos"], r["size"], r["cat"], r["user"], r["kb"], r["path"]])
        for col, w in zip("ABCDEFGHI", (24, 12, 8, 10, 10, 28, 14, 8, 70)):
            cl.column_dimensions[col].width = w
        cl.freeze_panes = "A2"
        p = os.path.join(out_dir, f"{safe} - {tpl['title']} {time.strftime('%Y-%m-%d_%H%M%S')}.xlsx")
        wb.save(p)
        return p
    except Exception as e:
        logging.error(f"report xlsx: {e}")
        return ""


# ------------------------------------------------------------------ one call used by the screen and the scheduler
def run_report(arch, params, user="", out_dir=None):
    tpl = get_template(params.get("template"))
    d1, d2 = resolve_range(params.get("range", ""), params.get("date_from", ""), params.get("date_to", ""))
    flt = {"paper": params.get("paper", ""), "cat": params.get("cat", ""), "date_from": d1, "date_to": d2, "user": params.get("user", "")}
    rows = arch.search("", False, 20000, **flt)["rows"]
    name = params.get("client") or tpl.get("client") or params.get("cat") or params.get("paper") or tpl["name"]
    return build_report(rows, tpl, (d1, d2), user=user, out_dir=out_dir, name_hint=name)
