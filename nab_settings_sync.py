# nab_settings_sync.py — one set of settings for every NAB PC.
#
# Change a setting on one PC and every other PC picks it up (within ~1 min
# or at next launch). Every change is logged with which PC made it and when
# (Sync dialog -> History), and locally in nab_sync_log.txt.
#
# What is shared (each is a "namespace" on the broker server):
#   app_settings  sliders, quality, hotkeys, quick-save keys, auto-snatch…
#   url_mappings  tab-title/URL -> paper
#   sources       the paper list
#   categories    the category tree
#   subscriptions paper subscription expiry dates
#   paper_aliases learned filename -> paper aliases
#   pdf_maker     PDF Maker settings
# What is NEVER shared (stays per-PC): base_root (your clip folder),
# daily goal / streak / last-active date, the PDF background image path.
#
# HOW: one small file, nab_settings_sync.json, in the same Google Drive folder
# NAB already uploads clips to. Every PC already has the Drive credentials, so
# there is no server, no keys and nothing extra to run or pay for.
#
# Conflict rule: if two PCs edited the same thing between syncs, the Drive
# version wins and YOUR copy is saved to Documents\nab_sync_conflicts\ — nothing
# is silently lost.
import os
import json
import time
import hashlib
import logging
import datetime
import threading

DOC = os.path.join(os.path.expanduser("~"), "Documents")
STATE_FILE = os.path.join(DOC, "nab_sync_state.json")
LOG_FILE = os.path.join(DOC, "nab_sync_log.txt")
CONFLICT_DIR = os.path.join(DOC, "nab_sync_conflicts")
INTERVAL_S = 60
ROLE_FILE = os.path.join(DOC, "nab_sync_role.json")      # per-PC, never synced


def get_role():
    """{"role": "follower"|"owner", "id": ""}.  Every PC is a follower (download only) unless it was made the owner."""
    d = _load_json(ROLE_FILE) or {}
    return {"role": "owner" if d.get("role") == "owner" else "follower", "id": "".join(c for c in str(d.get("id", "")) if c.isalnum() or c in "-_")[:40]}


def set_role(role=None, sid=None):
    d = get_role()
    if role in ("owner", "follower"):
        d["role"] = role
    if sid is not None:
        d["id"] = "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:40]
    _save_json(ROLE_FILE, d)
    return d

LOCAL_ONLY_SETTINGS = {"base_root", "last_active_date", "current_streak", "daily_goal"}
LOCAL_ONLY_PDF = {"bg_image"}


def _hash(value):
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   default=str).encode("utf-8")).hexdigest()


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    os.replace(tmp, path)


class FileAdapter:
    """One namespace <-> one local JSON file, minus per-PC-only keys."""

    def __init__(self, path, local_keys=(), wrap_key=None):
        self.path, self.local_keys, self.wrap_key = path, set(local_keys), wrap_key

    def read(self):
        data = _load_json(self.path)
        if data is None:
            return None
        if self.wrap_key:
            data = data.get(self.wrap_key) if isinstance(data, dict) else None
            return data
        if self.local_keys and isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in self.local_keys}
        return data

    def write(self, value):
        if self.wrap_key:
            _save_json(self.path, {self.wrap_key: value})
            return
        if self.local_keys and isinstance(value, dict):
            current = _load_json(self.path)
            keep = {k: v for k, v in (current or {}).items() if k in self.local_keys} \
                if isinstance(current, dict) else {}
            value = {**value, **keep}
        _save_json(self.path, value)


def default_adapters():
    import nab_subscriptions, nab_clip_scan
    try:
        import nab_pdf
        pdf_path = nab_pdf.CONFIG_FILE
    except Exception:
        pdf_path = os.path.join(DOC, "nab_pdf_config.json")
    return {
        "app_settings": FileAdapter(os.path.join(DOC, "news_clipper_settings.json"), LOCAL_ONLY_SETTINGS),
        "url_mappings": FileAdapter(os.path.join(DOC, "news_clipper_mappings.json"), wrap_key="url_mappings"),
        "sources": FileAdapter(os.path.join(DOC, "news_clipper_sources.json")),
        "categories": FileAdapter(os.path.join(DOC, "news_clipper_cats.json")),
        "subscriptions": FileAdapter(nab_subscriptions.SUBS_FILE),
        "paper_aliases": FileAdapter(nab_clip_scan.ALIASES_FILE),
        "pdf_maker": FileAdapter(pdf_path, LOCAL_ONLY_PDF),
    }


def log_line(msg):
    try:
        os.makedirs(DOC, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except Exception:
        pass


def sync_once(client, adapters, state, state_path=None, gate=None, push=True):
    """One pull+push cycle. `client` needs list_config_versions /
    get_synced_config / set_synced_config. Mutates and persists `state`.
    Returns {"pulled": [...], "pushed": [...], "conflicts": [...],
             "denied": [...], "offline": bool}."""
    res = {"pulled": [], "pushed": [], "conflicts": [], "denied": [], "offline": False, "awaiting": []}
    versions = client.list_config_versions()
    if versions is None:
        res["offline"] = True
        return res

    def pull(ns, ad, st, rv):
        r = client.get_synced_config(ns)
        if not r or r.get("value") is None:
            return False
        ad.write(r["value"])
        state[ns] = {"version": r.get("version", rv), "hash": _hash(ad.read())}
        return True

    for ns, ad in adapters.items():
        st = state.get(ns, {"version": 0, "hash": None})
        rv = (versions.get(ns) or {}).get("version", 0)
        local = ad.read()
        dirty = local is not None and _hash(local) != st.get("hash")
        if rv < st.get("version", 0):
            # The server is BEHIND what this PC last saw: it lost its data
            # (host restarted with a wiped disk). This PC's copy is the
            # newest known — re-publish it instead of waiting forever.
            log_line(f"SERVER RESET {ns}: server at v{rv}, this PC saw v{st['version']} — re-publishing")
            st = {"version": rv, "hash": None}
            state[ns] = st
            dirty = local is not None
        if rv > st.get("version", 0):
            if dirty:     # this PC has edits the server hasn't seen — back them up
                try:
                    os.makedirs(CONFLICT_DIR, exist_ok=True)
                    _save_json(os.path.join(CONFLICT_DIR,
                               f"{ns}_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"), local)
                except Exception:
                    pass
                if st.get("hash") is not None:      # genuinely both changed
                    res["conflicts"].append(ns)
                    log_line(f"CONFLICT {ns}: server version won; your copy saved in nab_sync_conflicts")
                else:
                    log_line(f"JOINED {ns}: adopted server settings; this PC's old copy saved in nab_sync_conflicts")
            if pull(ns, ad, st, rv):
                res["pulled"].append(ns)
                log_line(f"PULLED {ns} -> v{state[ns]['version']}")
        elif dirty and push:
            if gate is not None and not gate(ns):        # uploading needs Telegram approval
                res["awaiting"].append(ns)
                continue
            r = client.set_synced_config(ns, local, st.get("version", 0))
            if r.get("ok"):
                state[ns] = {"version": r["version"], "hash": _hash(local)}
                res["pushed"].append(ns)
                log_line(f"PUSHED {ns} -> v{r['version']}")
            elif r.get("error") == "version_conflict":
                if pull(ns, ad, st, r.get("version", 0)):
                    res["conflicts"].append(ns)
                    log_line(f"CONFLICT {ns}: lost a race, server version applied")
            elif r:   # 403 etc. — remember so we don't retry every minute
                state[ns] = {"version": st.get("version", 0), "hash": _hash(local)}
                res["denied"].append(ns)
                log_line(f"NOT SHARED {ns}: {r.get('error', 'refused')}")
            # r == {} -> network hiccup, retry next cycle
    try:
        _save_json(state_path or STATE_FILE, state)
    except Exception as e:
        logging.error(f"sync state save: {e}")
    return res


# ── Google Drive backend ────────────────────────────────────────────────
DRIVE_FILE = "nab_settings_sync.json"


def drive_file_name():
    i = get_role()["id"]
    return f"nab_settings_sync_{i}.json" if i else DRIVE_FILE
MAX_LOG = 300


class DriveClient:
    """Same interface the sync engine expects, backed by ONE json file in the
    NAB Drive folder:  {"namespaces": {ns: {value, version, by, at}}, "log": [...]}.
    Drive has no compare-and-swap, so two PCs saving in the same second could
    race; per-namespace version checks make that window a few seconds wide,
    and the loser's edit is backed up locally, never silently dropped."""

    def __init__(self, service, root_id, pc_name):
        self.svc, self.root, self.pc = service, root_id, pc_name
        self._fid = None
        self._cache = None      # (md5/modifiedTime token, doc)

    # -- low level --
    def _find(self):
        q = f"name='{drive_file_name()}' and '{self.root}' in parents and trashed=false"
        r = self.svc.files().list(q=q, fields="files(id,md5Checksum,modifiedTime)", pageSize=1,
                                  supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        f = (r.get("files") or [None])[0]
        self._fid = f["id"] if f else None
        return f

    def _load(self, fresh=False):
        f = self._find()
        if not f:
            self._cache = None
            return {"namespaces": {}, "log": []}
        token = f.get("md5Checksum") or f.get("modifiedTime")
        if not fresh and self._cache and self._cache[0] == token:
            return self._cache[1]
        raw = self.svc.files().get_media(fileId=f["id"], supportsAllDrives=True).execute()
        doc = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        doc.setdefault("namespaces", {})
        doc.setdefault("log", [])
        self._cache = (token, doc)
        return doc

    def _save(self, doc):
        import io
        from googleapiclient.http import MediaIoBaseUpload
        data = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/json", resumable=False)
        if self._fid:
            self.svc.files().update(fileId=self._fid, media_body=media, supportsAllDrives=True).execute()
        else:
            self.svc.files().create(body={"name": drive_file_name(), "parents": [self.root]},
                                    media_body=media, fields="id", supportsAllDrives=True).execute()
        self._cache = None

    # -- the interface sync_once() uses --
    def list_config_versions(self):
        try:
            doc = self._load()
            return {ns: {"version": e.get("version", 0)} for ns, e in doc["namespaces"].items()}
        except Exception as e:
            logging.error(f"DriveClient list: {e}")
            return None

    def get_synced_config(self, ns):
        try:
            e = self._load().get("namespaces", {}).get(ns)
        except Exception as ex:
            logging.error(f"DriveClient get: {ex}")
            return {}
        return {"value": e["value"], "version": e["version"]} if e else {"value": None, "version": 0}

    def set_synced_config(self, ns, value, expected_version):
        try:
            doc = self._load(fresh=True)
            cur = doc["namespaces"].get(ns, {"value": None, "version": 0})
            if cur["version"] != expected_version:
                return {"ok": False, "error": "version_conflict",
                        "value": cur["value"], "version": cur["version"]}
            now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
            doc["namespaces"][ns] = {"value": value, "version": cur["version"] + 1,
                                     "by": self.pc, "at": now}
            doc["log"].append({"at": now, "ns": ns, "pc_name": self.pc, "version": cur["version"] + 1,
                               "summary": summarize_change(cur["value"], value)})
            del doc["log"][:-MAX_LOG]
            self._save(doc)
            return {"ok": True, "version": cur["version"] + 1}
        except Exception as e:
            logging.error(f"DriveClient set: {e}")
            return {}

    def get_config_history(self, ns, limit=30):
        try:
            return [e for e in reversed(self._load().get("log", [])) if e.get("ns") == ns][:limit]
        except Exception:
            return []


def make_drive_client(app):
    """DriveClient for this app, or None if Drive isn't set up on this PC
    (needs the bundled Google key; the Drive folder ID is built in)."""
    try:
        svc = app._get_gdrive_service()
        root = app._drive_get_root_id()
        if not svc or not root:
            return None
        from nab_telegram import PC_NAME
        return DriveClient(svc, root, PC_NAME)
    except Exception as e:
        logging.error(f"make_drive_client: {e}")
        return None


class SyncManager:
    """Background loop for the app. `on_pulled(list_of_namespaces)` is called
    on the Tk thread (via app.after) when other PCs' changes were applied."""

    def __init__(self, app, on_pulled):
        self.app, self.on_pulled = app, on_pulled
        self.lock = threading.Lock()
        self.last = {"time": None, "result": None, "no_drive": False}
        self._stop = threading.Event()
        self._wake = threading.Event()

    _approved_until = 0.0
    _denied_until = 0.0

    def _gate(self, ns):
        """Upload gate: one Telegram approval covers 30 minutes of uploads; a denial is
        remembered for 10 minutes so the admin isn't spammed."""
        if get_role()["role"] == "owner":          # the owner PC was approved once when it became owner
            return True
        if not self.app.extra_settings.get("sync_approval", True):
            return True
        now = time.time()
        if now < self._approved_until:
            return True
        if now < self._denied_until:
            return False
        try:
            import nab_auth
            ok = nab_auth.TelegramAuth.request_sync_approval(f"Changed on this PC: {ns} (and any other pending settings)")
        except Exception as e:
            logging.error(f"sync approval: {e}")
            return False
        if ok is None:
            return False
        if ok:
            self._approved_until = now + 1800
            log_line("UPLOAD APPROVED on Telegram (30 min)")
        else:
            self._denied_until = now + 600
            log_line("UPLOAD DENIED / timed out on Telegram")
        return bool(ok)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="NAB-Sync").start()

    def sync_now(self):
        self._wake.set()

    def _loop(self):
        self._stop.wait(2)          # let the UI come up first; a new install downloads everything right away
        while not self._stop.is_set():
            self.run_cycle()
            self._wake.wait(INTERVAL_S)
            self._wake.clear()

    def run_cycle(self):
        with self.lock:
            try:
                client = make_drive_client(self.app)
                if client is None:
                    self.last = {"time": time.time(), "result": None, "no_drive": True}
                    return None
                role = get_role()
                state = _load_json(STATE_FILE) or {}
                if state.get("_file") != drive_file_name():      # a different ID/file: forget versions and adopt what is there
                    state = {"_file": drive_file_name()}
                res = sync_once(client, default_adapters(), state, gate=self._gate, push=(role["role"] == "owner"))
                self.last = {"time": time.time(), "result": res, "no_drive": False, "client": client}
                if res["pulled"]:
                    self.app.after(0, lambda p=list(res["pulled"]): self.on_pulled(p))
                return res
            except Exception as e:
                logging.error(f"sync cycle: {e}")
                return None

    def push_on_close(self, timeout=3.0):
        """Last-chance push of this session's edits; bounded so closing never hangs."""
        t = threading.Thread(target=self.run_cycle, daemon=True)
        t.start()
        t.join(timeout)


def summarize_change(old, new, limit=4):
    """Human one-liner for the History list: what changed between two values."""
    try:
        if isinstance(old, dict) and isinstance(new, dict):
            keys = [k for k in sorted(set(old) | set(new), key=str) if old.get(k) != new.get(k)]
            if not keys:
                return "no change"
            shown = ", ".join(str(k) for k in keys[:limit])
            return f"{len(keys)} changed: {shown}" + (" …" if len(keys) > limit else "")
        if isinstance(old, list) and isinstance(new, list):
            add, rem = [x for x in new if x not in old], [x for x in old if x not in new]
            parts = []
            if add: parts.append("+" + ", ".join(map(str, add[:limit])))
            if rem: parts.append("−" + ", ".join(map(str, rem[:limit])))
            return " ".join(parts) or "reordered"
    except Exception:
        pass
    return "first value" if old is None else "changed"
