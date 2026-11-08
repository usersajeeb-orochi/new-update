"""Every link the hunter has seen, so the same one is never reported twice."""
import datetime
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS found(
  id INTEGER PRIMARY KEY, search TEXT, ckey TEXT, link TEXT, title TEXT, source TEXT, domain TEXT, published TEXT, via TEXT,
  grp INTEGER, sim REAL, label TEXT, first_seen TEXT, sent INTEGER DEFAULT 0, resolved INTEGER DEFAULT 1,
  UNIQUE(search, ckey));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, search TEXT, started TEXT, fetched INTEGER, new INTEGER, note TEXT);
"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def seen(self, search, ckey):
        return self.db.execute("SELECT 1 FROM found WHERE search=? AND ckey=?", (search, ckey)).fetchone() is not None

    def add(self, search, it):
        with self.lock:
            try:
                cur = self.db.execute("INSERT INTO found(search,ckey,link,title,source,domain,published,via,grp,sim,label,first_seen,resolved) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                      (search, it["ckey"], it["link"], it["title"], it.get("source", ""), it.get("domain", ""),
                                       it["published"].isoformat() if it.get("published") else "", it.get("via", ""), it.get("grp"), it.get("sim"), it.get("label", ""),
                                       datetime.datetime.now().isoformat(timespec="seconds"), 1 if it.get("resolved", True) else 0))
                self.db.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def mark_sent(self, ids):
        with self.lock:
            self.db.executemany("UPDATE found SET sent=1 WHERE id=?", [(i,) for i in ids])
            self.db.commit()

    def log_run(self, search, fetched, new, note=""):
        with self.lock:
            self.db.execute("INSERT INTO runs(search,started,fetched,new,note) VALUES(?,?,?,?,?)", (search, datetime.datetime.now().isoformat(timespec="seconds"), fetched, new, note))
            self.db.commit()

    def results(self, search=None, since=None, text=None, limit=2000):
        q, a = "SELECT * FROM found WHERE 1=1", []
        if search:
            q += " AND search=?"; a.append(search)
        if since:
            q += " AND first_seen>=?"; a.append(since)
        if text:
            q += " AND title LIKE ?"; a.append("%" + text + "%")
        return [dict(r) for r in self.db.execute(q + " ORDER BY first_seen DESC, grp, id LIMIT ?", a + [limit])]

    def names(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT search FROM found ORDER BY search")]

    def last_runs(self, n=15):
        return [dict(r) for r in self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,))]
