# nab_tool_phone.py - the Phone queue: metadata typed on the colleague's phone (NAB Metadata app) waits here.
# Entries are tiny JSON files on the NAB Drive folder (written by the cloud bot); this reads them with the same Drive key.
# Also keeps the epaper address of each paper (shared with the phone through settings sync, namespace paper_urls).
import os
import io
import json
import time
import logging

import nab_connections

DOC = os.path.join(os.path.expanduser("~"), "Documents")
URLS_FILE = os.path.join(DOC, "nab_paper_urls.json")
PREFIX = "nab_m_"


def load_urls():
    try:
        with open(URLS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_urls(d):
    os.makedirs(DOC, exist_ok=True)
    tmp = URLS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, URLS_FILE)


class Tool:
    def __init__(self, engine):
        self.e = engine
        self._svc = None

    # -- drive --
    def _service(self):
        if self._svc:
            return self._svc
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        kf = nab_connections.google_key_file()
        if not kf:
            raise RuntimeError("The Google key is missing in this build.")
        creds = service_account.Credentials.from_service_account_file(kf, scopes=["https://www.googleapis.com/auth/drive"])
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._svc

    def _root(self):
        return nab_connections.drive_folder_id()

    def _list(self):
        svc, root, out, tok = self._service(), self._root(), [], None
        while True:
            r = svc.files().list(q=f"name contains '{PREFIX}' and '{root}' in parents and trashed=false", fields="nextPageToken,files(id)",
                                 pageSize=200, pageToken=tok, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            for f in r.get("files", []):
                try:
                    raw = svc.files().get_media(fileId=f["id"], supportsAllDrives=True).execute()
                    d = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
                    d["_fid"] = f["id"]
                    out.append(d)
                except Exception:
                    pass
            tok = r.get("nextPageToken")
            if not tok:
                return out

    # -- api --
    def api_list(self, a):
        try:
            es = [e for e in self._list() if e.get("status") == "new"]
        except Exception as ex:
            logging.error(f"phone list: {ex}")
            return {"ok": False, "error": "Could not read the phone queue from Drive: " + str(ex)[:100]}
        es.sort(key=lambda e: e.get("created", ""))
        return {"ok": True, "items": [{k: v for k, v in e.items() if k != "_fid"} for e in es]}

    def api_taken(self, a):
        """Mark an entry as taken (the phone then can no longer edit or delete it)."""
        from googleapiclient.http import MediaIoBaseUpload
        eid = str(a.get("id") or "")
        try:
            for e in self._list():
                if e.get("id") == eid:
                    fid = e.pop("_fid")
                    e.update(status="clipped", taken_at=time.strftime("%Y-%m-%d %H:%M:%S"))
                    media = MediaIoBaseUpload(io.BytesIO(json.dumps(e, ensure_ascii=False).encode()), mimetype="application/json", resumable=False)
                    self._service().files().update(fileId=fid, media_body=media, supportsAllDrives=True).execute()
                    return {"ok": True}
            return {"ok": False, "error": "That entry is gone (the phone user may have deleted it)."}
        except Exception as ex:
            return {"ok": False, "error": "Drive error: " + str(ex)[:100]}

    def api_papers(self, a):
        urls = load_urls()
        return {"ok": True, "papers": [{"name": p, "url": urls.get(p, "")} for p in self.e.paper_list]}

    def api_set_url(self, a):
        name, url = str(a.get("name") or ""), str(a.get("url") or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "The address must start with https://"}
        d = load_urls()
        if url:
            d[name] = url
        else:
            d.pop(name, None)
        save_urls(d)
        return {"ok": True}
