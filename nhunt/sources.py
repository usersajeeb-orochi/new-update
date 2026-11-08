"""Where results come from. Every source returns a list of dicts: title, link, source, published (datetime or None), snippet, via."""
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from .util import http_get, parse_date, clean_text, domain_of

DEFAULTS = {"gnews": "https://news.google.com", "gdelt": "https://api.gdeltproject.org", "brave": "https://api.search.brave.com", "telegram": "https://api.telegram.org"}

# Google News editions: (hl, gl, ceid). Bangladesh in English and in Bangla.
EDITIONS = {"en": ("en-BD", "BD", "BD:en"), "bn": ("bn", "BD", "BD:bn"), "en-us": ("en-US", "US", "US:en"), "en-in": ("en-IN", "IN", "IN:en")}


def _base(settings, key):
    return ((settings.get("endpoints") or {}).get(key) or DEFAULTS[key]).rstrip("/")


def _items_from_rss(xml_bytes, via):
    out = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        src = it.find("source")
        title = clean_text(it.findtext("title") or "")
        out.append({"title": title, "link": (it.findtext("link") or "").strip(), "source": clean_text(src.text if src is not None else ""),
                    "source_url": (src.get("url") if src is not None else "") or "", "published": parse_date(it.findtext("pubDate")),
                    "snippet": clean_text(it.findtext("description") or ""), "via": via})
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):                         # Atom feeds
        link = it.find("{http://www.w3.org/2005/Atom}link")
        out.append({"title": clean_text(it.findtext("{http://www.w3.org/2005/Atom}title") or ""), "link": (link.get("href") if link is not None else ""),
                    "source": "", "source_url": "", "published": parse_date(it.findtext("{http://www.w3.org/2005/Atom}updated") or it.findtext("{http://www.w3.org/2005/Atom}published")),
                    "snippet": clean_text(it.findtext("{http://www.w3.org/2005/Atom}summary") or ""), "via": via})
    return out


def google_news(query, settings, langs=("en", "bn"), log=print):
    out = []
    for lg in langs:
        hl, gl, ceid = EDITIONS.get(lg, EDITIONS["en"])
        url = f"{_base(settings, 'gnews')}/rss/search?" + urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
        try:
            data, _ = http_get(url)
            got = _items_from_rss(data, "google-news")
            log(f"    Google News ({lg}): {len(got)} items")
            out += got
        except Exception as e:
            log(f"    Google News ({lg}) failed: {e}")
    return out


def gdelt(rule_query, hours, settings, log=print):
    q = rule_query.replace(f" when:{int(hours)}h", "") if hours else rule_query
    url = f"{_base(settings, 'gdelt')}/api/v2/doc/doc?" + urllib.parse.urlencode({"query": q, "mode": "artlist", "format": "json", "maxrecords": 120,
                                                                                  "timespan": f"{max(1, int(hours or 24))}h", "sort": "datedesc"})
    try:
        data, _ = http_get(url)
        arts = json.loads(data.decode("utf-8", "replace") or "{}").get("articles", [])
        log(f"    GDELT: {len(arts)} items")
        return [{"title": a.get("title", ""), "link": a.get("url", ""), "source": a.get("domain", ""), "source_url": "", "published": parse_date(a.get("seendate")),
                 "snippet": "", "via": "gdelt"} for a in arts]
    except Exception as e:
        log(f"    GDELT failed: {e}")
        return []


def brave(query, hours, settings, log=print):
    key = settings.get("brave_key")
    if not key:
        log("    Brave skipped (no API key in Settings)")
        return []
    fresh = "pd" if (hours or 24) <= 24 else "pw" if hours <= 168 else "pm"
    url = f"{_base(settings, 'brave')}/res/v1/news/search?" + urllib.parse.urlencode({"q": re.sub(r"\s*when:\S+", "", query), "count": 50, "freshness": fresh, "country": "BD"})
    try:
        data, _ = http_get(url, {"X-Subscription-Token": key, "Accept": "application/json"})
        res = json.loads(data.decode("utf-8", "replace")).get("results", [])
        log(f"    Brave: {len(res)} items")
        return [{"title": clean_text(r.get("title", "")), "link": r.get("url", ""), "source": (r.get("meta_url") or {}).get("hostname", "") or domain_of(r.get("url", "")),
                 "source_url": "", "published": parse_date(r.get("page_age") or ""), "snippet": clean_text(r.get("description", "")), "via": "brave"} for r in res]
    except Exception as e:
        log(f"    Brave failed: {e}")
        return []


def feeds(feed_list, log=print):
    out = []
    for f in feed_list or []:
        url = f["url"] if isinstance(f, dict) else f
        name = f.get("name", "") if isinstance(f, dict) else ""
        try:
            data, _ = http_get(url)
            got = _items_from_rss(data, "feed")
            for g in got:
                g["source"] = g["source"] or name or domain_of(url)
            out += got
        except Exception as e:
            log(f"    feed {name or url} failed: {e}")
    if feed_list:
        log(f"    Site feeds: {len(out)} items from {len(feed_list)} feeds")
    return out
