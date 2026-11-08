"""A fake Google News / GDELT / Brave / feed / Telegram, for the self-test (no internet needed)."""
import base64
import datetime
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POSTS = []


def _rfc(h):
    d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=h)
    return d.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _gn_link(url):
    raw = b"\x08\x13\x22" + bytes([len(url)]) + url.encode() + b"\xd2\x01\x00"
    return "https://news.google.com/rss/articles/CBMi" + base64.urlsafe_b64encode(raw).decode().rstrip("=") + "?oc=5"


def rss(items):
    out = ['<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>t</title>']
    for t, link, src, srcurl, h in items:
        out.append(f"<item><title>{t}</title><link>{link}</link><pubDate>{_rfc(h)}</pubDate><description>&lt;a href='{link}'&gt;{t}&lt;/a&gt;</description>"
                   + (f'<source url="{srcurl}">{src}</source>' if src else "") + "</item>")
    out.append("</channel></rss>")
    return "".join(out).encode("utf-8")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _s(self, body, ct="application/xml; charset=utf-8", code=200):
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/rss/search":
            if q.get("hl", [""])[0] == "bn":
                return self._s(rss([("মোবাইল টাওয়ার নিয়ে নতুন নীতিমালা - বাংলা নিউজ", "http://banglanews.example/n1", "বাংলা নিউজ", "http://banglanews.example", 5)]))
            return self._s(rss([
                ("Mobile tower rollout expands in Barishal - Daily Example", "http://dailyexample.com/a1?utm_source=rss", "Daily Example", "http://dailyexample.com", 2),
                ("Mobile tower rollout expands in Barishal", "http://newstwo.com/b2", "News Two", "http://newstwo.com", 3),
                ("Mobile tower rollout expands in Barishal", "https://www.facebook.com/somepage/posts/1", "Facebook", "https://www.facebook.com", 1),
                ("Watch: mobile tower installation", "https://www.youtube.com/watch?v=abc", "YouTube", "https://www.youtube.com", 1),
                ("Tower dispute settled in court", _gn_link("http://tribune.example/c3"), "Tribune Example", "http://tribune.example", 6),
                ("Old mobile tower story from last week", "http://dailyexample.com/old", "Daily Example", "http://dailyexample.com", 72),
                ("Mobile tower lottery winners announced", "http://spam.example/lottery", "Spam Example", "http://spam.example", 2),
                ("Regulator fines operator over tower radiation limits", "https://www.linkedin.com/posts/x", "LinkedIn", "https://www.linkedin.com", 2),
            ]))
        if u.path == "/feed.xml":
            return self._s(rss([("Tower sharing deal signed by two operators", "http://feedsite.example/f1", "", "", 4),
                                ("Cricket: final tomorrow", "http://feedsite.example/f2", "", "", 4)]))
        if u.path == "/api/v2/doc/doc":
            arts = [{"url": "http://dailyexample.com/a1?utm_campaign=x", "title": "Mobile tower rollout expands in Barishal", "domain": "dailyexample.com", "seendate": (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")},
                    {"url": "http://gdeltsite.example/g9", "title": "Telecom tower tax to rise next year", "domain": "gdeltsite.example", "seendate": (datetime.datetime.utcnow() - datetime.timedelta(hours=8)).strftime("%Y%m%dT%H%M%SZ")}]
            return self._s(json.dumps({"articles": arts}).encode(), "application/json")
        if u.path == "/res/v1/news/search":
            if self.headers.get("X-Subscription-Token") != "KEY":
                return self._s(b"{}", "application/json", 401)
            return self._s(json.dumps({"results": [{"title": "Brave: tower sharing deal signed", "url": "http://bravesite.example/b1", "description": "Two operators sign", "page_age": "2026-11-02T01:00:00",
                                                    "meta_url": {"hostname": "bravesite.example"}}]}).encode(), "application/json")
        self._s(b"not found", "text/plain", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        POSTS.append((self.path, urllib.parse.parse_qs(self.rfile.read(n).decode())))
        self._s(b'{"ok":true}', "application/json")


def start():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
