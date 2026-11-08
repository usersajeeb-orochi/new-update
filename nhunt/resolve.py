"""Google News links point at news.google.com, not at the publisher. Turn them into the real article address."""
import base64
import re

from .util import http_get, domain_of


def _decode_old(link):
    m = re.search(r"/articles/([A-Za-z0-9_\-]+)", link)
    if not m:
        return None
    s = m.group(1)
    try:
        data = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        return None
    u = re.search(rb"https?://[\x21-\x7e]+", data)
    return u.group(0).decode("ascii", "ignore") if u else None


def resolve(link, log=print):
    """Returns (url, resolved_ok)."""
    if domain_of(link) != "news.google.com":
        return link, True
    u = _decode_old(link)
    if u:
        return u, True
    try:                                                    # newer links need Google's own decoder; the optional package handles it
        from googlenewsdecoder import gnewsdecoder
        r = gnewsdecoder(link, interval=1)
        if r.get("status") and r.get("decoded_url"):
            return r["decoded_url"], True
    except Exception:
        pass
    try:                                                    # last try: follow redirects
        _, final = http_get(link, timeout=15)
        if domain_of(final) not in ("news.google.com", "consent.google.com", "google.com"):
            return final, True
    except Exception:
        pass
    return link, False
