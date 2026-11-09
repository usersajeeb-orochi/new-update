# nab_archive.py - the clip archive: one SQLite file that knows every saved clip.
#
# Documents\nab_archive.db (WAL).  One row per clip file: paper, page, position, size, date, category, who saved it,
# a small "difference hash" for duplicate warnings, and the OCR text.  Search uses FTS5 first (fast, prefix words)
# and falls back to a plain substring scan, which also finds Bangla text FTS5 may split badly.  Free: only the
# Python standard library and Pillow.
import os
import re
import json
import time
import sqlite3
import logging
import threading
import datetime

DOC = os.path.join(os.path.expanduser("~"), "Documents")
DB_FILE = os.path.join(DOC, "nab_archive.db")
EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
_NAME_RE = re.compile(
    r"^(?P<paper>.+?), Page-(?P<page>[^,]*), Pos-(?P<pos>[^,]*), S-(?P<size>[^,]*), "
    r"Date-(?P<date>[\d\-]+)(?P<dup>_\d+)?(?P<ext>\.\w+)$")
_lock = threading.RLock()


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()


def iso_date(dmy):
    """05-06-2026 -> 2026-06-05 ; anything else -> ''."""
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", dmy or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def dhash(path):
    """64-bit difference hash as 16 hex chars; '' if the image can't be read."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            try:
                im.draft("L", (96, 96))
            except Exception:
                pass
            g = im.convert("L").resize((9, 8), Image.BILINEAR)
            px = list(g.tobytes())
        bits = 0
        for r in range(8):
            for c in range(8):
                bits = (bits << 1) | (1 if px[r * 9 + c] > px[r * 9 + c + 1] else 0)
        return f"{bits:016x}"
    except Exception:
        return ""


def _ham(a, b):
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 64


class Archive:
    def __init__(self, path=None):
        self.path = path or DB_FILE
        self.fts = True
        self._init()

    # ---------------------------------------------------------------- db
    def _con(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        c = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        return c

    def _init(self):
        with _lock:
            c = self._con()
            try:
                c.executescript("""
                CREATE TABLE IF NOT EXISTS clips(
                  id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, name TEXT, paper TEXT, page TEXT, pos TEXT, size TEXT,
                  cat TEXT, date TEXT, user TEXT, mtime INTEGER, bytes INTEGER, dhash TEXT, ocr TEXT DEFAULT '', added TEXT);
                CREATE INDEX IF NOT EXISTS ix_clips_date ON clips(date);
                CREATE INDEX IF NOT EXISTS ix_clips_paper ON clips(paper);
                CREATE INDEX IF NOT EXISTS ix_clips_cat ON clips(cat);
                CREATE TABLE IF NOT EXISTS saved(id INTEGER PRIMARY KEY, name TEXT UNIQUE, query TEXT);
                CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
                """)
                try:
                    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS clips_fts USING fts5(name, paper, cat, ocr, tokenize='unicode61 remove_diacritics 0')")
                except sqlite3.Error as e:
                    self.fts = False
                    logging.warning(f"archive: FTS5 not available ({e}); using plain search")
                c.commit()
            finally:
                c.close()

    def count(self):
        with _lock:
            c = self._con()
            try:
                return c.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
            finally:
                c.close()

    # ---------------------------------------------------------------- writing
    def _fts_put(self, c, rid, name, paper, cat, ocr):
        if not self.fts:
            return
        c.execute("DELETE FROM clips_fts WHERE rowid=?", (rid,))
        c.execute("INSERT INTO clips_fts(rowid,name,paper,cat,ocr) VALUES(?,?,?,?,?)", (rid, name or "", paper or "", cat or "", ocr or ""))

    def upsert(self, path, base_root="", user="", ocr=None, with_hash=True):
        """Add or refresh one clip file. Returns its row id (or 0 when the file isn't there)."""
        try:
            st = os.stat(path)
        except OSError:
            return 0
        name = os.path.basename(path)
        m = _NAME_RE.match(name)
        g = m.groupdict() if m else {}
        cat = ""
        if base_root:
            try:
                rel = os.path.relpath(os.path.dirname(path), base_root).replace("\\", "/")
                parts = [p for p in rel.split("/") if p and p != "."]
                # Monitoring\<date>\<category...>  - the date folder is not part of the category
                if parts and re.fullmatch(r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}", parts[0]):
                    parts = parts[1:]
                cat = "/".join(parts)
            except Exception:
                cat = ""
        with _lock:
            c = self._con()
            try:
                old = c.execute("SELECT id, dhash, ocr, user, added FROM clips WHERE path=?", (path,)).fetchone()
                h = (old["dhash"] if old and old["dhash"] else "") or (dhash(path) if with_hash else "")
                text = ocr if ocr is not None else (old["ocr"] if old else "")
                who = user or (old["user"] if old else "")
                added = old["added"] if old else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""INSERT INTO clips(path,name,paper,page,pos,size,cat,date,user,mtime,bytes,dhash,ocr,added)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                             ON CONFLICT(path) DO UPDATE SET name=excluded.name,paper=excluded.paper,page=excluded.page,pos=excluded.pos,
                               size=excluded.size,cat=excluded.cat,date=excluded.date,user=excluded.user,mtime=excluded.mtime,
                               bytes=excluded.bytes,dhash=excluded.dhash,ocr=excluded.ocr""",
                          (path, name, g.get("paper", ""), g.get("page", ""), g.get("pos", ""), g.get("size", ""), cat,
                           iso_date(g.get("date", "")), who, int(st.st_mtime), st.st_size, h, text, added))
                rid = c.execute("SELECT id FROM clips WHERE path=?", (path,)).fetchone()[0]
                self._fts_put(c, rid, name, g.get("paper", ""), cat, text)
                c.commit()
                return rid
            finally:
                c.close()

    def has(self, path):
        with _lock:
            c = self._con()
            try:
                return c.execute("SELECT 1 FROM clips WHERE path=?", (path,)).fetchone() is not None
            finally:
                c.close()

    def set_ocr(self, path, text):
        with _lock:
            c = self._con()
            try:
                r = c.execute("SELECT id,name,paper,cat FROM clips WHERE path=?", (path,)).fetchone()
                if not r:
                    return False
                c.execute("UPDATE clips SET ocr=? WHERE id=?", (text or "", r["id"]))
                self._fts_put(c, r["id"], r["name"], r["paper"], r["cat"], text)
                c.commit()
                return True
            finally:
                c.close()

    def remove(self, path):
        with _lock:
            c = self._con()
            try:
                r = c.execute("SELECT id FROM clips WHERE path=?", (path,)).fetchone()
                if r:
                    c.execute("DELETE FROM clips WHERE id=?", (r["id"],))
                    if self.fts:
                        c.execute("DELETE FROM clips_fts WHERE rowid=?", (r["id"],))
                    c.commit()
            finally:
                c.close()

    def rename(self, old, new, base_root=""):
        self.remove(old)
        self.upsert(new, base_root)

    def scan(self, folders, base_root="", progress=None, should_stop=None):
        """Fast pass: add new or changed image files and forget ones that were deleted. No OCR here."""
        seen, todo = set(), []
        with _lock:
            c = self._con()
            try:
                known = {r["path"]: (r["mtime"], r["bytes"]) for r in c.execute("SELECT path,mtime,bytes FROM clips")}
            finally:
                c.close()
        for folder in folders:
            for root, _d, files in os.walk(folder):
                for n in files:
                    if os.path.splitext(n)[1].lower() not in EXTS:
                        continue
                    p = os.path.join(root, n)
                    seen.add(p)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    if known.get(p) != (int(st.st_mtime), st.st_size):
                        todo.append(p)
        gone = [p for p in known if p not in seen and any(p.startswith(f) for f in folders)]
        for p in gone:
            self.remove(p)
        total = len(todo)
        for i, p in enumerate(todo, 1):
            if should_stop and should_stop():
                break
            self.upsert(p, base_root)
            if progress and (i % 20 == 0 or i == total):
                progress(i, total, os.path.basename(p))
        return {"added": len(todo), "removed": len(gone), "total": self.count()}

    def import_legacy_ocr(self, files):
        """Take text from the old JSON OCR index so nothing has to be read again. files: {path:{t:text,...}}"""
        n = 0
        for p, v in (files or {}).items():
            t = v.get("t", "") if isinstance(v, dict) else ""
            if t and self.set_ocr(p, t):
                n += 1
        return n

    # ---------------------------------------------------------------- searching
    @staticmethod
    def _terms(q):
        return [w for w in (_norm(x) for x in re.split(r"[,\n]", q or "")) if w]

    def _filters(self, f):
        where, args = [], []
        if f.get("paper"):
            where.append("c.paper = ? COLLATE NOCASE"); args.append(f["paper"])
        if f.get("cat"):
            where.append("(c.cat = ? OR c.cat LIKE ?)"); args += [f["cat"], f["cat"] + "/%"]
        if f.get("page"):
            where.append("c.page = ? COLLATE NOCASE"); args.append(f["page"])
        if f.get("user"):
            where.append("c.user = ? COLLATE NOCASE"); args.append(f["user"])
        if f.get("date_from"):
            where.append("c.date >= ?"); args.append(f["date_from"])
        if f.get("date_to"):
            where.append("c.date <= ?"); args.append(f["date_to"])
        return where, args

    def search(self, q="", all_terms=False, limit=500, **flt):
        terms = self._terms(q)
        where, args = self._filters(flt)
        rows = None
        with _lock:
            c = self._con()
            try:
                if terms and self.fts:
                    try:
                        expr = (" AND " if all_terms else " OR ").join('"' + t.replace('"', "") + '"*' for t in terms)
                        sql = ("SELECT c.* FROM clips c JOIN clips_fts f ON f.rowid=c.id WHERE clips_fts MATCH ?" +
                               "".join(" AND " + w for w in where) + " ORDER BY c.date DESC, c.name LIMIT ?")
                        rows = c.execute(sql, [expr] + args + [limit + 1]).fetchall()
                    except sqlite3.Error as e:
                        logging.warning(f"archive fts: {e}")
                        rows = None
                if terms and not rows:
                    like = [("(lower(c.name||' '||c.paper||' '||c.cat||' '||c.ocr) LIKE ?)", "%" + t + "%") for t in terms]
                    glue = " AND " if all_terms else " OR "
                    sql = ("SELECT c.* FROM clips c WHERE (" + glue.join(x[0] for x in like) + ")" +
                           "".join(" AND " + w for w in where) + " ORDER BY c.date DESC, c.name LIMIT ?")
                    rows = c.execute(sql, [x[1] for x in like] + args + [limit + 1]).fetchall()
                if not terms:
                    sql = "SELECT c.* FROM clips c" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY c.date DESC, c.name LIMIT ?"
                    rows = c.execute(sql, args + [limit + 1]).fetchall()
                total = len(rows)
            finally:
                c.close()
        out = []
        for r in rows[:limit]:
            t = _norm(r["ocr"])
            sn = ""
            hit = next((w for w in terms if w in t), "")
            if hit:
                i = t.find(hit)
                sn = ("..." if i > 60 else "") + t[max(0, i - 60): i + 100] + "..."
            out.append({"id": r["id"], "path": r["path"], "name": r["name"], "paper": r["paper"], "page": r["page"], "pos": r["pos"],
                        "size": r["size"], "cat": r["cat"], "date": r["date"], "user": r["user"], "kb": round((r["bytes"] or 0) / 1024),
                        "snip": sn, "has_text": bool(r["ocr"])})
        return {"rows": out, "total": total, "more": total > limit}

    def facets(self):
        with _lock:
            c = self._con()
            try:
                def col(name):
                    return [r[0] for r in c.execute(f"SELECT DISTINCT {name} FROM clips WHERE {name}<>'' ORDER BY {name} COLLATE NOCASE")]
                return {"papers": col("paper"), "cats": col("cat"), "pages": col("page"), "users": col("user")}
            finally:
                c.close()

    # ---------------------------------------------------------------- duplicates
    def dup_of(self, path, exclude=(), maxdist=3):
        """The closest other clip that looks the same, or None."""
        h = dhash(path)
        if not h:
            return None
        ex = {os.path.normcase(p) for p in exclude} | {os.path.normcase(path)}
        best = None
        with _lock:
            c = self._con()
            try:
                for r in c.execute("SELECT path,name,date,added,dhash FROM clips WHERE dhash<>''"):
                    if os.path.normcase(r["path"]) in ex or not os.path.exists(r["path"]):
                        continue
                    d = _ham(h, r["dhash"])
                    if d <= maxdist and (best is None or d < best[0]):
                        best = (d, {"path": r["path"], "name": r["name"], "date": r["date"], "added": r["added"], "dist": d})
            finally:
                c.close()
        return best[1] if best else None

    def duplicate_groups(self, maxdist=2, limit=200):
        with _lock:
            c = self._con()
            try:
                rows = [(r["id"], r["path"], r["name"], r["dhash"]) for r in c.execute("SELECT id,path,name,dhash FROM clips WHERE dhash<>''")]
            finally:
                c.close()
        used, groups = set(), []
        for i, a in enumerate(rows):
            if a[0] in used:
                continue
            g = [a]
            for b in rows[i + 1:]:
                if b[0] not in used and _ham(a[3], b[3]) <= maxdist:
                    g.append(b)
            if len(g) > 1:
                for x in g:
                    used.add(x[0])
                groups.append([{"path": x[1], "name": x[2]} for x in g])
                if len(groups) >= limit:
                    break
        return groups

    # ---------------------------------------------------------------- saved searches (smart folders)
    def saved_list(self):
        with _lock:
            c = self._con()
            try:
                return [{"name": r["name"], "query": json.loads(r["query"] or "{}")} for r in c.execute("SELECT name,query FROM saved ORDER BY name COLLATE NOCASE")]
            finally:
                c.close()

    def saved_put(self, name, query):
        name = (name or "").strip()[:60]
        if not name:
            return False
        with _lock:
            c = self._con()
            try:
                c.execute("INSERT INTO saved(name,query) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET query=excluded.query", (name, json.dumps(query or {}, ensure_ascii=False)))
                c.commit()
                return True
            finally:
                c.close()

    def saved_delete(self, name):
        with _lock:
            c = self._con()
            try:
                c.execute("DELETE FROM saved WHERE name=?", (name,))
                c.commit()
            finally:
                c.close()

    # ---------------------------------------------------------------- export
    def export(self, rows, folder, kind="xlsx"):
        os.makedirs(folder, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        head = ["Paper", "Date", "Page", "Position", "Size", "Category", "Saved by", "KB", "File"]
        data = [[r["paper"], r["date"], r["page"], r["pos"], r["size"], r["cat"], r["user"], r["kb"], r["path"]] for r in rows]
        if kind == "xlsx":
            try:
                import openpyxl
                from openpyxl.styles import Font
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Clips"
                ws.append(head)
                for c in ws[1]:
                    c.font = Font(bold=True)
                for d in data:
                    ws.append(d)
                for col, w in zip("ABCDEFGHI", (24, 12, 8, 10, 10, 28, 14, 8, 70)):
                    ws.column_dimensions[col].width = w
                ws.freeze_panes = "A2"
                p = os.path.join(folder, f"NAB clips {stamp}.xlsx")
                wb.save(p)
                return p
            except ImportError:
                kind = "csv"
        import csv
        p = os.path.join(folder, f"NAB clips {stamp}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(data)
        return p


_inst = [None]


def get():
    if _inst[0] is None:
        _inst[0] = Archive()
    return _inst[0]
