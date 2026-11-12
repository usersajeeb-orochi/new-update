# nab_daily_report.py - the daily NAB analysis workbook (Excel) and its upload to the shared Google Drive.
#
# One .xlsx per day with: Overview (KPIs, written insights, charts), By paper, By category, Paper x Category heat map,
# By hour, People, 30-day trend, Missing papers, and every clip. Built from the clip archive with openpyxl only (free, already in NAB).
import collections
import datetime
import logging
import os
import re
import time

DOC = os.path.join(os.path.expanduser("~"), "Documents")
OUT_DIR = os.path.join(DOC, "NAB Reports", "Daily")
DRIVE_SUBFOLDER = "NAB Daily Reports"
ACCENT, DARK, SOFT = "2F5FD0", "1B2340", "EAF0FF"


def _main(cat):
    return (cat or "").split("/")[0].strip() or "(no category)"


def _hour(r):
    m = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}):", r.get("added") or "")
    return int(m.group(1)) if m else None


def _day(d):
    return datetime.date.fromisoformat(d)


def analyse(rows_all, day):
    """Everything the workbook shows, as plain data (also used by the tests)."""
    d0 = _day(day)
    prev = (d0 - datetime.timedelta(days=1)).isoformat()
    today = [r for r in rows_all if r["date"] == day]
    yest = [r for r in rows_all if r["date"] == prev]
    last7 = [r for r in rows_all if day > r["date"] >= (d0 - datetime.timedelta(days=7)).isoformat()]
    A = {"day": day, "rows": today, "n": len(today), "n_prev": len(yest)}
    A["avg7"] = round(len(last7) / 7.0, 1)
    A["by_paper"] = collections.Counter(r["paper"] or "-" for r in today)
    A["by_cat"] = collections.Counter(_main(r["cat"]) for r in today)
    A["by_fullcat"] = collections.Counter(r["cat"] or "(no category)" for r in today)
    A["by_user"] = collections.Counter(r["user"] or "-" for r in today)
    A["by_hour"] = collections.Counter(h for h in (_hour(r) for r in today) if h is not None)
    A["matrix"] = collections.defaultdict(collections.Counter)
    for r in today:
        A["matrix"][r["paper"] or "-"][_main(r["cat"])] += 1
    A["cat_prev"] = collections.Counter(_main(r["cat"]) for r in yest)
    # trend: 30 days ending on `day`
    days = [(d0 - datetime.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    tc, tp = collections.Counter(), collections.defaultdict(set)
    for r in rows_all:
        tc[r["date"]] += 1
        tp[r["date"]].add(r["paper"])
    A["trend"] = [(d, tc.get(d, 0), len(tp.get(d, ()))) for d in days]
    # papers that normally appear (any clip in the 7 days before) but not today
    seen7 = collections.Counter(r["paper"] for r in last7 if r["paper"])
    lastseen = {}
    for r in rows_all:
        if r["paper"] and r["date"] < day:
            lastseen[r["paper"]] = max(lastseen.get(r["paper"], ""), r["date"])
    A["missing"] = sorted([(p, c, lastseen.get(p, "")) for p, c in seen7.items() if p not in A["by_paper"]], key=lambda x: -x[1])
    # insights
    ins = []
    n = A["n"]
    if n == 0:
        ins.append("No clips were saved on this day.")
    else:
        d = n - A["n_prev"]
        ins.append(f"{n} clips saved ({'+' if d >= 0 else ''}{d} vs the day before, 7-day average {A['avg7']}).")
        p, pc = A["by_paper"].most_common(1)[0]
        c, cc = A["by_cat"].most_common(1)[0]
        ins.append(f"Most clipped paper: {p} with {pc} clips ({round(100 * pc / n)}%). Most clipped category: {c} with {cc} clips ({round(100 * cc / n)}%).")
        top3 = sum(v for _, v in A["by_cat"].most_common(3))
        ins.append(f"The top 3 categories make up {round(100 * top3 / n)}% of the day.")
        if A["by_hour"]:
            h, hc = A["by_hour"].most_common(1)[0]
            ins.append(f"Busiest hour: {h:02d}:00-{(h + 1) % 24:02d}:00 with {hc} clips.")
        if len(A["by_user"]) > 1:
            u, uc = A["by_user"].most_common(1)[0]
            ins.append(f"{len(A['by_user'])} people saved clips; {u} saved the most ({uc}).")
        moves = [(c, A["by_cat"].get(c, 0) - A["cat_prev"].get(c, 0)) for c in set(A["by_cat"]) | set(A["cat_prev"])]
        moves = [m for m in moves if m[1]]
        if moves and A["n_prev"]:
            up = max(moves, key=lambda m: m[1])
            dn = min(moves, key=lambda m: m[1])
            if up[1] > 0:
                ins.append(f"Biggest rise: {up[0]} (+{up[1]}).")
            if dn[1] < 0:
                ins.append(f"Biggest drop: {dn[0]} ({dn[1]}).")
        nocat = sum(1 for r in today if not r["cat"])
        if nocat:
            ins.append(f"{nocat} clips have no category - worth fixing for clean reports.")
    if A["missing"]:
        ins.append("No clips today from: " + ", ".join(p for p, _, _ in A["missing"][:8]) + (" ..." if len(A["missing"]) > 8 else "") + ".")
    A["insights"] = ins
    return A


def build_workbook(rows_all, day, out_dir=None, client=""):
    import openpyxl
    import openpyxl.worksheet.properties
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    A = analyse(rows_all, day)
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    wb = openpyxl.Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=ACCENT)
    thin = Side(style="thin", color="D5DCEE")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    def header(ws, row, labels, col=1):
        for i, t in enumerate(labels):
            c = ws.cell(row=row, column=col + i, value=t)
            c.font, c.fill, c.alignment, c.border = head_font, head_fill, Alignment(horizontal="center", vertical="center", wrap_text=True), box

    def widths(ws, ws_widths):
        for i, w in enumerate(ws_widths, 1):
            ws.column_dimensions[L(i)].width = w

    def title(ws, text, sub=""):
        ws["A1"] = text
        ws["A1"].font = Font(bold=True, size=16, color=DARK)
        if sub:
            ws["A2"] = sub
            ws["A2"].font = Font(color="667799", italic=True)

    n = A["n"]
    papers = sorted(A["by_paper"].items(), key=lambda kv: (-kv[1], kv[0]))
    cats = sorted(A["by_cat"].items(), key=lambda kv: (-kv[1], kv[0]))
    nice = _day(day).strftime("%A, %d %B %Y")

    # ---------------- Overview (charts are filled in after the data sheets exist)
    ov = wb.active
    ov.title = "Overview"
    ov.sheet_view.showGridLines = False
    title(ov, (client + " - " if client else "") + "NAB Daily News Report", f"{nice}   |   generated {time.strftime('%Y-%m-%d %H:%M')}")
    kpis = [("Clips today", n), ("Papers covered", len(A["by_paper"])), ("Categories", len(A["by_cat"])), ("People", len(A["by_user"])),
            ("vs yesterday", (n - A["n_prev"])), ("7-day average", A["avg7"])]
    for i, (k, v) in enumerate(kpis):
        col = 1 + i * 2
        ov.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
        ov.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
        a, b = ov.cell(row=4, column=col, value=k), ov.cell(row=5, column=col, value=v)
        a.font, b.font = Font(color="667799", size=10), Font(bold=True, size=22, color=DARK)
        a.alignment = b.alignment = Alignment(horizontal="center", vertical="center")
        for r in (4, 5):
            for cc in (col, col + 1):
                ov.cell(row=r, column=cc).fill = PatternFill("solid", fgColor=SOFT)
        if k == "vs yesterday":
            b.number_format = '+0;-0;0'
            b.font = Font(bold=True, size=22, color=("1E8E3E" if v >= 0 else "C5221F"))
    ov.row_dimensions[5].height = 36
    ov["A7"] = "What stands out"
    ov["A7"].font = Font(bold=True, size=13, color=ACCENT)
    for i, t in enumerate(A["insights"]):
        c = ov.cell(row=8 + i, column=1, value="• " + t)
        ov.merge_cells(start_row=8 + i, start_column=1, end_row=8 + i, end_column=12)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ov.row_dimensions[8 + i].height = 32 if len(t) > 95 else 18
    chart_row = 8 + len(A["insights"]) + 2
    widths(ov, [13] * 12)

    # ---------------- By paper
    bp = wb.create_sheet("By paper")
    title(bp, "Clips by newspaper", nice)
    header(bp, 4, ["Newspaper", "Clips", "Share %", "Categories", "Top category", "Pages", "Avg KB", "First saved", "Last saved"])
    for i, (p, c) in enumerate(papers):
        rs = [r for r in A["rows"] if (r["paper"] or "-") == p]
        cc = collections.Counter(_main(r["cat"]) for r in rs)
        times = sorted(r["added"][11:16] for r in rs if r.get("added"))
        row = [p, c, round(100.0 * c / n, 1) if n else 0, len(cc), cc.most_common(1)[0][0], len({r["page"] for r in rs if r["page"]}),
               round(sum(r["kb"] for r in rs) / len(rs)) if rs else 0, times[0] if times else "", times[-1] if times else ""]
        for j, v in enumerate(row, 1):
            bp.cell(row=5 + i, column=j, value=v).border = box
    if papers:
        bp.conditional_formatting.add(f"B5:B{4 + len(papers)}", DataBarRule(start_type="num", start_value=0, end_type="max", color="5B8DEF"))
    widths(bp, [28, 9, 9, 11, 26, 8, 9, 12, 12])
    bp.freeze_panes = "A5"

    # ---------------- By category
    bc = wb.create_sheet("By category")
    title(bc, "Clips by category (top level) and full category path", nice)
    header(bc, 4, ["Category", "Clips", "Share %", "Papers", "Top paper"])
    for i, (c, v) in enumerate(cats):
        rs = [r for r in A["rows"] if _main(r["cat"]) == c]
        pc = collections.Counter(r["paper"] or "-" for r in rs)
        for j, x in enumerate([c, v, round(100.0 * v / n, 1) if n else 0, len(pc), pc.most_common(1)[0][0]], 1):
            bc.cell(row=5 + i, column=j, value=x).border = box
    if cats:
        bc.conditional_formatting.add(f"B5:B{4 + len(cats)}", DataBarRule(start_type="num", start_value=0, end_type="max", color="F5A623"))
    r0 = 7 + len(cats)
    bc.cell(row=r0, column=1, value="Full category paths").font = Font(bold=True, size=13, color=ACCENT)
    header(bc, r0 + 1, ["Category path", "Clips", "Share %"])
    for i, (c, v) in enumerate(sorted(A["by_fullcat"].items(), key=lambda kv: (-kv[1], kv[0]))):
        for j, x in enumerate([c, v, round(100.0 * v / n, 1) if n else 0], 1):
            bc.cell(row=r0 + 2 + i, column=j, value=x).border = box
    widths(bc, [40, 9, 9, 9, 28])
    bc.freeze_panes = "A5"

    # ---------------- Paper x Category heat map
    mx = wb.create_sheet("Paper x Category")
    title(mx, "Which paper has which category", nice + "  |  darker = more clips")
    top_cats = [c for c, _ in cats][:14]
    header(mx, 4, ["Newspaper"] + top_cats + (["Other"] if len(cats) > 14 else []) + ["Total"])
    for i, (p, _c) in enumerate(papers):
        mx.cell(row=5 + i, column=1, value=p).border = box
        tot = 0
        for j, c in enumerate(top_cats, 2):
            v = A["matrix"][p].get(c, 0)
            mx.cell(row=5 + i, column=j, value=v or None).border = box
            tot += v
        col = 2 + len(top_cats)
        if len(cats) > 14:
            other = sum(v for c, v in A["matrix"][p].items() if c not in top_cats)
            mx.cell(row=5 + i, column=col, value=other or None).border = box
            tot += other
            col += 1
        t = mx.cell(row=5 + i, column=col, value=tot)
        t.font, t.border = Font(bold=True), box
    last = 4 + len(papers)
    lastcol = 1 + len(top_cats) + (1 if len(cats) > 14 else 0)
    if papers:
        mx.conditional_formatting.add(f"B5:{L(lastcol)}{last}", ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color="2F5FD0"))
    for j in range(1, lastcol + 2):
        mx.column_dimensions[L(j)].width = 26 if j == 1 else 12
    mx.row_dimensions[4].height = 42
    mx.freeze_panes = "B5"
    if papers and top_cats:
        ch = BarChart()
        ch.type, ch.grouping, ch.overlap = "col", "stacked", 100
        ch.title = "Categories inside each newspaper"
        ch.add_data(Reference(mx, min_col=2, max_col=lastcol, min_row=4, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(mx, min_col=1, min_row=5, max_row=last))
        ch.height, ch.width = 10, 26
        mx.add_chart(ch, f"A{last + 3}")

    # ---------------- By hour
    bh = wb.create_sheet("By hour")
    title(bh, "When the clips were saved", nice)
    header(bh, 4, ["Hour", "Clips"])
    for h in range(24):
        bh.cell(row=5 + h, column=1, value=f"{h:02d}:00").border = box
        bh.cell(row=5 + h, column=2, value=A["by_hour"].get(h, 0)).border = box
    widths(bh, [10, 9])

    # ---------------- People
    pe = wb.create_sheet("People")
    title(pe, "Clips by person", nice)
    header(pe, 4, ["Person", "Clips", "Share %", "Papers", "Categories", "First saved", "Last saved"])
    for i, (u, c) in enumerate(sorted(A["by_user"].items(), key=lambda kv: (-kv[1], kv[0]))):
        rs = [r for r in A["rows"] if (r["user"] or "-") == u]
        times = sorted(r["added"][11:16] for r in rs if r.get("added"))
        for j, x in enumerate([u, c, round(100.0 * c / n, 1) if n else 0, len({r["paper"] for r in rs}), len({_main(r["cat"]) for r in rs}),
                               times[0] if times else "", times[-1] if times else ""], 1):
            pe.cell(row=5 + i, column=j, value=x).border = box
    widths(pe, [24, 9, 9, 9, 11, 12, 12])

    # ---------------- Trend
    tr = wb.create_sheet("Trend 30 days")
    title(tr, "Last 30 days", "clips per day and how many papers were covered")
    header(tr, 4, ["Date", "Clips", "Papers"])
    for i, (d, c, p) in enumerate(A["trend"]):
        for j, x in enumerate([d, c, p], 1):
            tr.cell(row=5 + i, column=j, value=x).border = box
    widths(tr, [12, 9, 9])
    lc = LineChart()
    lc.title = "Clips per day"
    lc.add_data(Reference(tr, min_col=2, max_col=3, min_row=4, max_row=4 + len(A["trend"])), titles_from_data=True)
    lc.set_categories(Reference(tr, min_col=1, min_row=5, max_row=4 + len(A["trend"])))
    lc.height, lc.width = 9, 22
    tr.add_chart(lc, "E4")

    # ---------------- Missing
    ms = wb.create_sheet("Missing papers")
    title(ms, "Papers that usually appear but had no clip today", "based on the 7 days before")
    header(ms, 4, ["Newspaper", "Clips in last 7 days", "Last clip on"])
    for i, (p, c, d) in enumerate(A["missing"]):
        for j, x in enumerate([p, c, d], 1):
            ms.cell(row=5 + i, column=j, value=x).border = box
    widths(ms, [28, 18, 14])

    # ---------------- all clips
    cl = wb.create_sheet("Clips")
    header(cl, 1, ["Newspaper", "Date", "Page", "Position", "Size", "Category", "Saved by", "Saved at", "KB", "File"])
    for i, r in enumerate(sorted(A["rows"], key=lambda r: (r["paper"] or "", r["page"] or "", r["pos"] or "")), 2):
        for j, x in enumerate([r["paper"], r["date"], r["page"], r["pos"], r["size"], r["cat"], r["user"], (r.get("added") or "")[11:16], r["kb"], r["path"]], 1):
            cl.cell(row=i, column=j, value=x)
    widths(cl, [24, 12, 8, 10, 10, 30, 14, 10, 8, 70])
    cl.freeze_panes = "A2"
    cl.auto_filter.ref = f"A1:J{max(2, len(A['rows']) + 1)}"

    # ---------------- Overview charts
    def bar(ws, data_ws, min_row, max_row, text, color, anchor, horizontal=True):
        ch = BarChart()
        ch.type = "bar" if horizontal else "col"
        ch.title, ch.legend = text, None
        ch.add_data(Reference(data_ws, min_col=2, min_row=min_row - 1, max_row=max_row), titles_from_data=True)
        ch.set_categories(Reference(data_ws, min_col=1, min_row=min_row, max_row=max_row))
        ch.series[0].graphicalProperties.solidFill = color
        ch.dataLabels = DataLabelList()
        ch.dataLabels.showVal = True
        ch.dataLabels.showSerName = ch.dataLabels.showCatName = ch.dataLabels.showLegendKey = False
        ch.height, ch.width = 8.5, 14
        if horizontal:
            ch.y_axis.delete = False
            ch.x_axis.scaling.orientation = "maxMin"
        ws.add_chart(ch, anchor)

    r = chart_row
    if papers:
        bar(ov, bp, 5, min(4 + len(papers), 14), "Clips by newspaper (top 10)", ACCENT, f"A{r}")
    if cats:
        pie_rows = cats[:8] + ([("Other", sum(v for _, v in cats[8:]))] if len(cats) > 8 else [])
        pr = len(papers) + 8
        # helper table for the pie on the By paper sheet (right side), so the Overview stays clean
        bp.cell(row=4, column=12, value="Category").font = Font(bold=True)
        bp.cell(row=4, column=13, value="Clips").font = Font(bold=True)
        for i, (c, v) in enumerate(pie_rows):
            bp.cell(row=5 + i, column=12, value=c)
            bp.cell(row=5 + i, column=13, value=v)
        pie = PieChart()
        pie.title = "Share by category"
        pie.add_data(Reference(bp, min_col=13, min_row=4, max_row=4 + len(pie_rows)), titles_from_data=True)
        pie.set_categories(Reference(bp, min_col=12, min_row=5, max_row=4 + len(pie_rows)))
        pie.dataLabels = DataLabelList()
        pie.dataLabels.showPercent = True
        pie.dataLabels.showVal = pie.dataLabels.showSerName = pie.dataLabels.showCatName = pie.dataLabels.showLegendKey = False
        pie.height, pie.width = 8.5, 14
        ov.add_chart(pie, f"G{r}")
        bp.column_dimensions["L"].width = 26
    r2 = r + 19
    lc2 = LineChart()
    lc2.title = "Last 30 days"
    lc2.add_data(Reference(tr, min_col=2, min_row=4, max_row=4 + len(A["trend"])), titles_from_data=True)
    lc2.set_categories(Reference(tr, min_col=1, min_row=5, max_row=4 + len(A["trend"])))
    lc2.legend = None
    lc2.height, lc2.width = 8.5, 14
    ov.add_chart(lc2, f"A{r2}")
    bar(ov, bh, 5, 28, "Clips by hour", "F5A623", f"G{r2}", horizontal=False)

    for ws in wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr = openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", client).strip()
    import socket
    path = os.path.join(out_dir, f"NAB Daily Report {day}" + (f" - {safe}" if safe else "") + f" ({socket.gethostname()}).xlsx")
    wb.save(path)
    return path, A


def build_for_day(arch, day, out_dir=None, client=""):
    d0 = _day(day)
    d_from = (d0 - datetime.timedelta(days=30)).isoformat()
    rows = arch.search("", False, 50000, date_from=d_from, date_to=day)["rows"]
    path, A = build_workbook(rows, day, out_dir=out_dir, client=client)
    return {"ok": True, "path": path, "n": A["n"], "day": day, "insights": A["insights"]}


# ------------------------------------------------------------------ Drive upload
def upload_to_drive(path, subfolder=DRIVE_SUBFOLDER):
    """Put the file in <NAB Cloud folder>/NAB Daily Reports/. A second run for the same day replaces the first."""
    import nab_connections
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = nab_connections.drive_credentials()
    if not creds:
        raise RuntimeError("No Google sign-in in this build")
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    root = nab_connections.drive_folder_id()
    kw = dict(supportsAllDrives=True, includeItemsFromAllDrives=True)
    q = f"name='{subfolder}' and '{root}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    f = svc.files().list(q=q, fields="files(id)", pageSize=1, **kw).execute().get("files", [])
    fid = f[0]["id"] if f else svc.files().create(body={"name": subfolder, "mimeType": "application/vnd.google-apps.folder", "parents": [root]},
                                                  fields="id", supportsAllDrives=True).execute()["id"]
    name = os.path.basename(path)
    media = MediaFileUpload(path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resumable=False)
    old = svc.files().list(q=f"name='{name}' and '{fid}' in parents and trashed=false", fields="files(id)", pageSize=1, **kw).execute().get("files", [])
    if old:
        out = svc.files().update(fileId=old[0]["id"], media_body=media, fields="id,webViewLink", supportsAllDrives=True).execute()
    else:
        out = svc.files().create(body={"name": name, "parents": [fid]}, media_body=media, fields="id,webViewLink", supportsAllDrives=True).execute()
    return out.get("webViewLink", "")
