# nab_mailer.py — send the day's clips to fixed groups by e-mail (PDF / JPG / ZIP per group rule).
# Pure module: no UI, no engine. The engine passes the day folder and callbacks.  Settings live in nab_mail.json
# (per PC); the mail password is stored separately and protected with Windows DPAPI when available.
import os, re, json, time, copy, glob, base64, shutil, smtplib, ssl, logging, mimetypes, zipfile, uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate

IMG_EXT = (".jpg", ".jpeg", ".png")
NOCOMP = (".jpg", ".jpeg", ".png", ".pdf", ".zip", ".rar", ".webp")
JUNK = ("thumbs.db", "desktop.ini", ".ds_store")

DEFAULT_GROUPS = [
    ("Beximco group", ["Beximco"], "pdf"), ("United Group", ["United Group"], "pdf"), ("Pride Group", ["Pride Group"], "pdf"),
    ("BAT", ["BAT"], "jpg"), ("Xiaomi", ["Xiaomi"], "jpg"), ("ASK", ["ASK"], "jpg"),
    ("Telecom industry", ["Telecom"], "zip"), ("Edotco industry", ["Telecom"], "zip"),
]


def new_group(name="", sources=None, mode="pdf"):
    return {"id": uuid.uuid4().hex[:8], "name": name, "enabled": True, "sources": list(sources or []), "items": [], "from_cats": [], "take_rest": False, "mode": mode, "if_large": "zip",
            "large_files": None, "large_mb": None, "zip_name": "{Group} {Date}.zip", "zip_root": "", "to": [], "cc": [], "bcc": [],
            "own_text": False, "subject": "", "body": "", "extra_files": [], "send_empty": False}


def default_config():
    gs = []
    for n, src, mode in DEFAULT_GROUPS:
        g = new_group(n, src, mode)
        if mode == "zip":
            g["zip_name"] = "{Group}.zip"
        if n == "Beximco group":
            g["sources"], g["take_rest"] = [], True                    # everything the other groups do not take
        elif n == "United Group":
            g["sources"], g["from_cats"] = [], ["United Group"]        # every PDF made from the United Group folder, plus the two named below
            g["items"] = ["pdf|United Group news media monitoring report", "pdf|Banking & Finance news media monitoring report",
                          "pdf|Power, Energy & Mineral news media monitoring report"]
        elif n == "Pride Group":
            g["sources"], g["items"] = [], ["pdf|Pride Group news media monitoring report"]
        if n == "Edotco industry":
            g["enabled"] = False                                       # sent by hand for now; tick it on in the list when wanted
            g["zip_root"] = "Edotco industry"
            g["extra_files"] = [{"name": "link.txt", "text": ""}]
        gs.append(g)
    return {"v": 1,
            "account": {"kind": "gmail", "email": "", "name": "Media Desk", "host": "smtp.gmail.com", "port": 465, "security": "ssl", "user": ""},
            "text": {"subject": "{Group} news media monitoring on {Date}",
                     "body": "Dear all,\nPlease find attached the {Group} clips for {Date}.\nRegards, Desk",
                     "date_format": "%d-%m-%Y", "part_label": "Part {Part} of {Total}"},
            "limits": {"large_files": 20, "large_mb": 20, "max_mail_mb": 24, "over_max": "split"},
            "behaviour": {"wait_s": 5, "retries": 3, "remind_at": "18:30", "bcc_me": "", "ask": True, "telegram": True, "skip_sent": False},
            "groups": gs}


def _merge(base, over):
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


# ───────────────────────── storage ─────────────────────────
class Store:
    def __init__(self, folder):
        self.folder = folder
        self.cfg_path = os.path.join(folder, "nab_mail.json")
        self.log_path = os.path.join(folder, "nab_mail_log.json")
        self.secret_path = os.path.join(folder, "nab_mail_secret.bin")

    def load(self):
        cfg = default_config()
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            groups = d.pop("groups", None)
            _merge(cfg, d)
            if isinstance(groups, list):
                cfg["groups"] = [_merge(new_group(), g) for g in groups if isinstance(g, dict)]
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.error(f"mail load: {e}")
        return cfg

    def save(self, cfg):
        clean = clean_config(cfg)
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.cfg_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.cfg_path)
        return clean

    # password (never written to nab_mail.json)
    def set_password(self, pw):
        os.makedirs(self.folder, exist_ok=True)
        if not pw:
            try:
                os.remove(self.secret_path)
            except OSError:
                pass
            return
        raw = pw.encode("utf-8")
        blob = _dpapi(raw, True)
        with open(self.secret_path, "wb") as f:
            f.write((b"D1" if blob is not None else b"B1") + (blob if blob is not None else base64.b64encode(raw)))

    def get_password(self):
        try:
            with open(self.secret_path, "rb") as f:
                d = f.read()
            if d[:2] == b"D1":
                r = _dpapi(d[2:], False)
                return r.decode("utf-8") if r is not None else ""
            return base64.b64decode(d[2:]).decode("utf-8")
        except Exception:
            return ""

    def has_password(self):
        return os.path.exists(self.secret_path) and bool(self.get_password())

    # log
    def log(self):
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def add_log(self, entry):
        L = self.log()
        L.append(entry)
        L = L[-600:]
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(L, f, ensure_ascii=False)
        except Exception as e:
            logging.error(f"mail log: {e}")


def _dpapi(data, protect):
    """Windows DPAPI via ctypes; None when not on Windows / unavailable."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        buf = ctypes.create_string_buffer(data, len(data))
        i = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        o = BLOB()
        f = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
        ok = f(ctypes.byref(i), None, None, None, None, 0, ctypes.byref(o))
        if not ok:
            return None
        out = ctypes.string_at(o.pbData, o.cbData)
        ctypes.windll.kernel32.LocalFree(o.pbData)
        return out
    except Exception:
        return None


_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def split_addrs(v):
    if isinstance(v, str):
        v = re.split(r"[,;\n]+", v)
    out = []
    for a in v or []:
        a = str(a).strip()
        if a and a not in out:
            out.append(a)
    return out


def clean_config(cfg):
    base = default_config()
    cfg = copy.deepcopy(cfg or {})
    groups = cfg.pop("groups", [])
    _merge(base, cfg)
    base["account"]["port"] = int(base["account"].get("port") or 465)
    for k in ("large_files", "large_mb", "max_mail_mb"):
        base["limits"][k] = max(1, int(float(base["limits"].get(k) or 1)))
    base["behaviour"]["wait_s"] = max(0, int(float(base["behaviour"].get("wait_s") or 0)))
    base["behaviour"]["retries"] = max(0, min(10, int(float(base["behaviour"].get("retries") or 0))))
    gs, seen = [], set()
    for g in groups:
        g = _merge(new_group(), g)
        for k in ("to", "cc", "bcc", "sources", "items", "from_cats"):
            g[k] = split_addrs(g.get(k)) if k in ("to", "cc", "bcc") else [str(s).strip() for s in (g.get(k) or []) if str(s).strip()]
        for k in ("large_files", "large_mb"):
            g[k] = int(float(g[k])) if g.get(k) not in (None, "", 0) else None
        g["name"] = str(g.get("name") or "").strip() or "Group"
        if g["mode"] not in ("pdf", "jpg", "zip"):
            g["mode"] = "pdf"
        if g["if_large"] not in ("zip", "none"):
            g["if_large"] = "zip"
        if g["id"] in seen:
            g["id"] = uuid.uuid4().hex[:8]
        seen.add(g["id"])
        g["extra_files"] = [{"name": _safe(e.get("name") or "link.txt"), "text": str(e.get("text") or "")} for e in (g.get("extra_files") or []) if isinstance(e, dict)]
        gs.append(g)
    base["groups"] = gs
    return base


def _safe(n):
    return re.sub(r'[\\/:*?"<>|]+', "_", str(n)).strip() or "file"


def fill(tpl, **kw):
    out = str(tpl or "")
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def validate(cfg):
    """Problems that would stop a send (list of strings)."""
    errs = []
    a = cfg["account"]
    if not a.get("email"):
        errs.append("Sender e-mail is empty.")
    for g in cfg["groups"]:
        if not g["enabled"]:
            continue
        if not g["to"] and not g["cc"]:
            errs.append(f"{g['name']}: no receivers.")
        for x in g["to"] + g["cc"] + g["bcc"]:
            if not _EMAIL.match(x):
                errs.append(f"{g['name']}: '{x}' is not a valid address.")
        if not g["sources"] and not g["items"] and not g.get("take_rest"):
            errs.append(f"{g['name']}: no files chosen (pick folders or PDFs).")
    return errs


# ───────────────────────── files and plans ─────────────────────────
def day_categories(day_folder):
    try:
        return sorted(d for d in os.listdir(day_folder) if os.path.isdir(os.path.join(day_folder, d)) and d not in ("OutputPDF", "OutputMail"))
    except OSError:
        return []


def _walk(folder):
    for r, ds, fs in os.walk(folder):
        ds[:] = [d for d in ds if d not in ("OutputPDF", "OutputMail")]
        for f in sorted(fs):
            if f.lower() in JUNK or f.startswith("~$"):
                continue
            yield os.path.join(r, f)


def _images(folder):
    return [p for p in _walk(folder) if p.lower().endswith(IMG_EXT)]


def _size(paths):
    t = 0
    for p in paths:
        try:
            t += os.path.getsize(p)
        except OSError:
            pass
    return t


def _build_zip(dest, entries, extra):
    """entries: [(abs_path, arcname)], extra: [(arcname, text)]"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for src, arc in entries:
            ct = zipfile.ZIP_STORED if src.lower().endswith(NOCOMP) else zipfile.ZIP_DEFLATED
            z.write(src, arc.replace("\\", "/"), compress_type=ct)
        for arc, text in extra:
            z.writestr(arc.replace("\\", "/"), text)
    os.replace(tmp, dest)
    return dest


def _recent_days(day_folder, n=6):
    """Today's folder plus the latest earlier day folders next to it, so groups can be set up even when today has no clips yet."""
    out = [day_folder]
    month_dir = os.path.dirname(day_folder)
    year_dir = os.path.dirname(month_dir)
    dirs = []
    for md in ([month_dir] + [os.path.join(year_dir, d) for d in (os.listdir(year_dir) if os.path.isdir(year_dir) else [])]):
        if os.path.isdir(md):
            for d in os.listdir(md):
                if re.match(r"^\d\d-\d\d-\d{4}$", d) and os.path.join(md, d) != day_folder:
                    dirs.append(os.path.join(md, d))
    dirs = sorted(set(dirs), key=lambda p: tuple(reversed(os.path.basename(p).split("-"))), reverse=True)
    return out + dirs[:n]


_DATE_TAIL = re.compile(r"\s+on\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4}$")


def pdf_short(fn):
    """'Pride Group news media monitoring report on October 21, 2026.pdf' -> 'Pride Group news media monitoring report'."""
    stem = os.path.splitext(os.path.basename(fn))[0]
    return _DATE_TAIL.sub("", stem).strip()


def output_pdfs(day_folder):
    """The PDFs that really are in <day>/OutputPDF (made by the PDF maker). Origin folder is learned from the PDF maker's own naming."""
    od = os.path.join(day_folder, "OutputPDF")
    if not os.path.isdir(od):
        return []
    origin = {}
    try:
        import nab_pdf
        for it in nab_pdf.list_pdf_items(day_folder, include_hidden=True):
            origin.setdefault(it["short"], it["category"])
            origin.setdefault(pdf_short(it["name"]), it["category"])
    except Exception as e:
        logging.error(f"pdf origin: {e}")
    out = []
    for f in sorted(os.listdir(od)):
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(od, f)):
            sh = pdf_short(f)
            out.append({"path": os.path.join(od, f), "name": f, "short": sh, "key": "pdf|" + sh, "category": origin.get(sh, "")})
    return out


def list_items(day_folder):
    """For the group editor: today's folders and the PDFs found in OutputPDF (today, plus names seen on recent days; n=0 = not today)."""
    cats = [{"name": c, "n": len(_images(os.path.join(day_folder, c)))} for c in day_categories(day_folder)]
    pdfs, seen = [], {}
    for i, df in enumerate(_recent_days(day_folder)):
        for it in output_pdfs(df):
            if it["key"] in seen:
                continue
            row = {"key": it["key"], "legacy": "", "short": it["short"], "name": it["name"], "category": it["category"], "kind": "real",
                   "n": 1 if i == 0 else 0, "hidden": False}
            seen[it["key"]] = row
            pdfs.append(row)
    if not pdfs:                                      # nothing made yet anywhere: show what the PDF maker would make
        import nab_pdf
        for df in _recent_days(day_folder):
            try:
                its = nab_pdf.list_pdf_items(df)
            except Exception:
                continue
            for it in its:
                if it["key"] not in seen and not it.get("hidden"):
                    seen[it["key"]] = row = {"key": it["key"], "legacy": it["legacy_key"], "short": it["short"], "name": it["name"], "category": it["category"], "kind": "planned", "n": 0, "hidden": False}
                    pdfs.append(row)
    pdfs.sort(key=lambda x: x["short"].lower())
    return {"cats": cats, "pdfs": pdfs}


def _item_map(day_folder):
    import nab_pdf
    m = {}
    for it in nab_pdf.list_pdf_items(day_folder, include_hidden=True):
        m[it["key"]] = it
        m.setdefault(it["legacy_key"], it)           # keys saved by v3.0.25/26
    return m


def _rel(day_folder, p):
    return os.path.relpath(p, day_folder)


def claimed_keys(cfg, exclude_id=None):
    out = set()
    for h in cfg["groups"]:
        if h["enabled"] and h["id"] != exclude_id and not h.get("take_rest"):
            out.update(h.get("items") or [])
    return out


def claimed_cats(cfg, exclude_id=None):
    out = set()
    for h in cfg["groups"]:
        if h["enabled"] and h["id"] != exclude_id and not h.get("take_rest"):
            out.update(h.get("from_cats") or [])
            if h["mode"] == "pdf":
                out.update(h.get("sources") or [])
    return out


def pdf_files_for(g, cfg, day_folder):
    """Real PDFs of OutputPDF that belong to this group: named ones, ones made from its folders, or the leftovers (catch-all)."""
    allp = output_pdfs(day_folder)
    keys, cats = set(g.get("items") or []), set(g.get("from_cats") or []) | set(g.get("sources") or [])
    pick, seen = [], set()
    for it in allp:
        if it["key"] in keys or (it["category"] and it["category"] in cats):
            pick.append(it)
    if g.get("take_rest"):
        tk, tc = claimed_keys(cfg, g["id"]), claimed_cats(cfg, g["id"])
        for it in allp:
            if it["key"] not in tk and not (it["category"] and it["category"] in tc) and it not in pick:
                pick.append(it)
    return pick, bool(allp)


def plan_group(g, cfg, day_folder, date_s, make_pdfs=False, logger=None):
    """Work out (and, when needed, build) the attachments of one group.  Returns a dict for the UI/sender.
    A group takes whole folders (g.sources) and/or single PDF-maker items (g.items: 'Category|kind|label')."""
    lim = cfg["limits"]
    lf, lm = g.get("large_files") or lim["large_files"], g.get("large_mb") or lim["large_mb"]
    res = {"id": g["id"], "name": g["name"], "status": "ready", "attach": "", "files": [], "n": 0, "bytes": 0, "note": ""}
    if g["mode"] == "pdf":                          # PDF groups only pick up what the PDF maker already made
        pk, any_pdf = pdf_files_for(g, cfg, day_folder)
        files = sorted({it["path"] for it in pk})
        if not files:
            res.update(status="nofiles", note=("None of this group's PDFs are in OutputPDF today." if any_pdf else "No PDFs in OutputPDF yet. Make the PDFs in the PDF tab first."))
            return res
        large = len(files) > lf or _size(files) > lm * 1048576
        if large and g["if_large"] == "zip":
            zipname = _safe(fill(g["zip_name"] or "{Group} {Date}.zip", Group=g["name"], Date=date_s))
            if not zipname.lower().endswith(".zip"):
                zipname += ".zip"
            dest = os.path.join(day_folder, "OutputMail", zipname)
            try:
                _build_zip(dest, [(f, os.path.basename(f)) for f in files], [])
            except Exception as e:
                res.update(status="error", note=f"ZIP failed: {e}")
                return res
            res.update(attach="zip", files=[dest], n=1, bytes=_size([dest]), inner=len(files), note=f"{len(files)} PDFs in ZIP (large)", src_names=[os.path.basename(f) for f in files])
            return res
        res.update(attach="pdf", files=files, n=len(files), bytes=_size(files), inner=0, src_names=[os.path.basename(f) for f in files])
        return res
    srcs = [s_ for s_ in g["sources"] if os.path.isdir(os.path.join(day_folder, s_))]
    keys = list(g.get("items") or [])
    imap = _item_map(day_folder) if (keys or g.get('take_rest') or (g['mode'] == 'pdf' and srcs)) else {}
    items = [imap[k] for k in keys if k in imap]
    if g.get('take_rest'):
        taken = claimed_keys(cfg, g['id'])
        items += [it for it in {id(v): v for v in imap.values()}.values() if not it.get('hidden') and it['key'] not in taken and it not in items]
    if not srcs and not items and not g.get('take_rest'):
        miss = ", ".join(g["sources"] + [k.split("|")[0] + " / " + (k.split("|")[2] or "main") for k in keys]) or "nothing selected"
        res.update(status="nofiles", note="Not found today: " + miss)
        return res
    outdir = os.path.join(day_folder, "OutputMail")
    mode = g["mode"]
    files, kind, inner = [], mode, 0
    img_pairs = []                                  # (abs, arcname) of every image behind this group
    for s_ in srcs:
        base = os.path.join(day_folder, s_)
        for p_ in _images(base):
            img_pairs.append((p_, _rel(day_folder, p_)))
    for it in items:
        for p_ in it["images"]:
            img_pairs.append((p_, _rel(day_folder, p_)))
    seen_i, uniq = set(), []
    for p_, a_ in img_pairs:
        if p_ not in seen_i:
            seen_i.add(p_)
            uniq.append((p_, a_))
    img_pairs = uniq
    try:
        if mode == "pdf":
            pitems = list(items) + [it for it in imap.values() if it["category"] in srcs and it["key"] not in keys and not it.get("hidden")]
            for it in pitems:
                if make_pdfs and it["images"]:
                    import nab_pdf
                    if logger:
                        logger(f"PDF: {it['name']}")
                    os.makedirs(os.path.dirname(it["out"]), exist_ok=True)
                    nab_pdf.CFG = nab_pdf.load_config()
                    nab_pdf.process_single_pdf_task(it["task"])
                if os.path.exists(it["out"]):
                    files.append(it["out"])
            files = sorted(set(files))
            kind = "pdf"
        elif mode == "jpg":
            files = [p_ for p_, _ in img_pairs]
            kind = "jpg"
    except Exception as e:
        logging.error(f"plan {g['name']}: {e}")
        res.update(status="error", note=str(e))
        return res
    if mode != "zip" and not files:
        res.update(status="nofiles", note="No " + ("PDF yet. Press Prepare files." if mode == "pdf" else "images today."))
        return res
    large = mode != "zip" and (len(files) > lf or _size(files) > lm * 1048576)
    zipname = _safe(fill(g["zip_name"] or "{Group} {Date}.zip", Group=g["name"], Date=date_s))
    if not zipname.lower().endswith(".zip"):
        zipname += ".zip"
    if mode == "zip" or (large and g["if_large"] == "zip"):
        entries, extra = [], []
        if mode == "zip":
            for s_ in srcs:
                root = g["zip_root"] if (g["zip_root"] and len(srcs) == 1 and not items) else s_
                base = os.path.join(day_folder, s_)
                for p_ in _walk(base):
                    entries.append((p_, os.path.join(root, os.path.relpath(p_, base))))
            for it in items:                               # every file of the item's folders (not only images)
                if it["dirs"]:
                    for d_ in it["dirs"]:
                        for p_ in _walk(d_):
                            entries.append((p_, _rel(day_folder, p_)))
                else:
                    for p_ in it["images"]:
                        entries.append((p_, _rel(day_folder, p_)))
            root0 = g["zip_root"] if (g["zip_root"] and len(srcs) == 1 and not items) else None
            for e in g["extra_files"]:
                if e["text"].strip():
                    arc = os.path.join(root0 or (srcs[0] if srcs else "."), e["name"])
                    extra.append((arc, e["text"]))
                    entries = [x for x in entries if x[1].replace("\\", "/") != arc.replace("\\", "/")]
            dd, seen_e = [], set()
            for x in entries:
                if x[1] not in seen_e:
                    seen_e.add(x[1])
                    dd.append(x)
            entries = dd
        else:
            amap = dict(img_pairs)
            for p_ in files:
                entries.append((p_, amap.get(p_) or os.path.basename(p_)))
        if not entries and not extra:
            res.update(status="nofiles", note="Folder is empty.")
            return res
        dest = os.path.join(outdir, zipname)
        try:
            _build_zip(dest, entries, extra)
        except Exception as e:
            logging.error(f"zip {g['name']}: {e}")
            res.update(status="error", note=f"ZIP failed: {e}")
            return res
        files, kind, inner = [dest], "zip", len(entries) + len(extra)
        res["note"] = f"{inner} files in ZIP" + (" (large)" if large else "")
    res.update(attach=kind, files=files, n=len(files), bytes=_size(files))
    res["inner"] = inner
    return res


# ───────────────────────── learning from earlier sends ─────────────────────────
def _names_of(plan):
    nm = plan.get("src_names") or [os.path.basename(f) for f in plan.get("files", [])]
    return [pdf_short(n) if n.lower().endswith(".pdf") else n for n in nm]


def log_facts(plan):
    """What to remember about one send (written into the mail log)."""
    n = plan.get("inner") or len(plan.get("files", []))
    return {"files": _names_of(plan)[:80], "count": n, "bytes": plan.get("bytes", 0), "kind": plan.get("attach", "")}


def hints(g, plan, log):
    """Smart checks from the group's own history: usual files missing, new files, much fewer/smaller than usual, receivers changed."""
    hist = [e for e in log if e.get("group") == g["name"] and e.get("ok") and not e.get("test") and e.get("files") is not None][-10:]
    out = []
    if len(hist) < 2:
        return out
    today = set(_names_of(plan)) if plan.get("status") == "ready" else set()
    n_now = plan.get("inner") or len(plan.get("files", []))
    counts = sorted(e.get("count", 0) for e in hist)
    med = counts[len(counts) // 2]
    if plan.get("status") != "ready":
        if med:
            out.append(["warn", f"Usually gets about {med} file(s), nothing today."])
        return out
    freq = {}
    for e in hist:
        for f in set(e.get("files") or []):
            freq[f] = freq.get(f, 0) + 1
    if all(len(e.get("files") or []) <= 80 for e in hist) and g["mode"] == "pdf":
        miss = [f for f, c in freq.items() if c >= max(2, int(len(hist) * .7 + .5)) and f not in today]
        if miss:
            out.append(["warn", "Usually included, not found today: " + ", ".join(sorted(miss)[:4]) + (" …" if len(miss) > 4 else "")])
        new = [f for f in today if f not in freq]
        if new:
            out.append(["info", "New file (never sent to this group before): " + ", ".join(sorted(new)[:4])])
    if med >= 2 and n_now < med * .5:
        out.append(["warn", f"Only {n_now} files, usually about {med}."])
    bs = sorted(e.get("bytes", 0) for e in hist if e.get("bytes"))
    if bs and plan.get("bytes", 0) < bs[len(bs) // 2] * .3:
        out.append(["warn", "Much smaller than usual."])
    last = hist[-1].get("to")
    now_to = len(g.get("to", [])) + len(g.get("cc", []))
    if last is not None and last != now_to:
        out.append(["info", f"Receivers changed since last send ({last} → {now_to})."])
    return out


# ───────────────────────── sending ─────────────────────────
def split_parts(files, max_bytes):
    """Greedy split; returns (parts, too_big) where too_big are single files over the limit."""
    parts, cur, size, big = [], [], 0, []
    for f in sorted(files, key=lambda p: -os.path.getsize(p)):
        s = os.path.getsize(f)
        if s > max_bytes:
            big.append(f)
            continue
        if cur and size + s > max_bytes:
            parts.append(cur)
            cur, size = [], 0
        cur.append(f)
        size += s
    if cur:
        parts.append(cur)
    return parts, big


def _connect(cfg, password):
    a = cfg["account"]
    host, port, sec = a.get("host") or "smtp.gmail.com", int(a.get("port") or 465), a.get("security") or "ssl"
    ctx = ssl.create_default_context()
    if sec == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=60, context=ctx)
    else:
        s = smtplib.SMTP(host, port, timeout=60)
        s.ehlo()
        if sec == "starttls":
            s.starttls(context=ctx)
            s.ehlo()
    user = a.get("user") or a.get("email")
    if a.get("kind") == "gmail" and password:
        password = "".join(password.split())          # Google shows app passwords as 4 groups with spaces
    if password:
        s.login(user, password)
    return s


def test_connection(cfg, password):
    try:
        s = _connect(cfg, password)
        s.quit()
        return {"ok": True}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Login refused. Check the address and the app password (a normal Google password does not work)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _compose(cfg, g, date_s, files, part, total, test_to=None, links=None):
    t = cfg["text"]
    subj_t = g["subject"] if g["own_text"] and g["subject"] else t["subject"]
    body_t = g["body"] if g["own_text"] and g["body"] else t["body"]
    size = f"{_size(files) / 1048576:.1f} MB"
    kw = dict(Group=g["name"], Date=date_s, Count=len(files), Size=size, Part=part, Total=total)
    subj, body = fill(subj_t, **kw), fill(body_t, **kw)
    if total > 1:
        subj += " (" + fill(t.get("part_label") or "Part {Part} of {Total}", **kw) + ")"
    if links:
        body += "\n\n" + "\n".join(links)
    m = EmailMessage()
    a = cfg["account"]
    m["From"] = formataddr((a.get("name") or "", a.get("email")))
    if test_to:
        m["To"] = test_to
        m["Subject"] = "[TEST] " + subj
        rcpt = [test_to]
    else:
        m["To"] = ", ".join(g["to"]) if g["to"] else a["email"]
        if g["cc"]:
            m["Cc"] = ", ".join(g["cc"])
        m["Subject"] = subj
        rcpt = g["to"] + g["cc"] + g["bcc"]
        me = cfg["behaviour"].get("bcc_me")
        if me and me not in rcpt:
            rcpt.append(me)
    m["Date"] = formatdate(localtime=True)
    m.set_content(body)
    for f in files:
        ct, _ = mimetypes.guess_type(f)
        mt, st = (ct or "application/octet-stream").split("/", 1)
        with open(f, "rb") as fh:
            m.add_attachment(fh.read(), maintype=mt, subtype=st, filename=os.path.basename(f))
    return m, rcpt


def send_group(cfg, password, g, plan, date_s, test_to=None, drive_link=None, on_msg=None):
    """Send one group (maybe several parts).  Returns {ok, parts, error}."""
    files = plan["files"]
    if not files and not g["send_empty"]:
        return {"ok": False, "error": "No files."}
    max_b = cfg["limits"]["max_mail_mb"] * 1048576
    parts, links = [files], []
    if files and _size(files) > max_b:
        if cfg["limits"]["over_max"] == "drive" and drive_link:
            try:
                links = [drive_link(f) for f in files]
                parts = [[]]
            except Exception as e:
                logging.error(f"drive link: {e}; splitting instead")
                links = []
        if not links:
            parts, big = split_parts(files, max_b)
            if big:
                return {"ok": False, "error": "File too big for one mail: " + ", ".join(os.path.basename(b) for b in big) + ". Use the Drive link option."}
    elif not files:
        parts = [[]]
    total = len(parts)
    sent = 0
    for i, pf in enumerate(parts, 1):
        msg, rcpt = _compose(cfg, g, date_s, pf, i, total, test_to, links if i == 1 else None)
        err = None
        for attempt in range(cfg["behaviour"]["retries"] + 1):
            try:
                s = _connect(cfg, password)
                try:
                    s.send_message(msg, from_addr=cfg["account"]["email"], to_addrs=rcpt)
                finally:
                    try:
                        s.quit()
                    except Exception:
                        pass
                err = None
                break
            except Exception as e:
                err = str(e)
                logging.error(f"mail {g['name']} part {i} try {attempt + 1}: {e}")
                time.sleep(min(10, 2 + attempt * 2))
        if err:
            return {"ok": False, "parts": sent, "error": err}
        sent += 1
        if on_msg:
            on_msg(i, total)
    return {"ok": True, "parts": sent, "total": total}
