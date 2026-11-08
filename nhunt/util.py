"""Small helpers: HTTP without extra packages, URL clean-up, dates, text tokens."""
import datetime
import email.utils
import gzip
import html
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def http_get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data, r.geturl()


def http_post(url, body, headers=None, timeout=25):
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


_TRACK = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_|igshid|ocid|cmpid|spm)", re.I)


def canon_url(u):
    """The same article often arrives with different tracking tails; compare on this form."""
    try:
        p = urllib.parse.urlsplit(u.strip())
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if not _TRACK.match(k)]
        host = p.netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        path = p.path.rstrip("/") or "/"
        return urllib.parse.urlunsplit((p.scheme.lower(), host, path, urllib.parse.urlencode(q), ""))
    except Exception:
        return u


def domain_of(u):
    try:
        h = urllib.parse.urlsplit(u).netloc.lower().split(":")[0]
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def parse_date(s):
    """RSS dates, ISO dates and GDELT dates to an aware UTC datetime, or None."""
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        pass
    for f in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.datetime.strptime(s, f)
            return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def clean_text(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return " ".join(s.split())


STOP_EN = set("a an the and or but if of to in on at by for with from as is are was were be been being it its this that these those he she they we you i his her their our your not no yes will would can could may might shall should has have had do does did say says said after before over under about into than then so such also more most new news how what when where who whom why which just up out off per amid".split())
STOP_BN = set("এই ওই সেই একটি একটা এবং ও বা কিন্তু যে যা কি কী না নেই আছে ছিল হয় হয়েছে হবে করা করে করেছে করবে থেকে জন্য সঙ্গে সাথে মধ্যে পর আগে নিয়ে দিয়ে তার তাদের তিনি তারা আমরা আমি আপনি এক দুই তিন বলে বলেন বলেছেন হচ্ছে".split())


def tokens(s):
    s = (s or "").lower()
    out = []
    for w in re.findall(r"[0-9a-zঀ-৿]+", s):
        if w in STOP_EN or w in STOP_BN or len(w) < 2:
            continue
        out.append(w)
    return out
