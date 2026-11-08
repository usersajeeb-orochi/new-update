# nab_learn.py — learn URL/title mappings from the operator's corrections.
import re
from urllib.parse import urlparse

_GENERIC = re.compile(r"\be[\s\-_.]*paper\b|\bepaper\b|\bprint edition\b|\bpage\s*\d+\b|\bhome\b",
                      re.I)
_SPLIT = re.compile(r"\s+[-|–—:•·]\s+|\s*\|\s*")


def suggest_fragment(title="", url=""):
    """Best mapping fragment for a tab. A site's host is the most stable
    handle; failing that, the most distinctive title segment."""
    if url:
        try:
            host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
            host = re.sub(r"^(www|epaper|e-paper|m)\.", "", host)
            if host and "." in host:
                return host
        except Exception:
            pass
    t = _GENERIC.sub(" ", title or "")
    segs = [s.strip() for s in _SPLIT.split(t) if re.sub(r"[\W\d_]+", "", s)]
    # drop browser suffixes such as "Google Chrome"
    segs = [s for s in segs if not re.search(r"google chrome|microsoft.*edge|mozilla|brave|opera", s, re.I)]
    if not segs:
        return ""
    best = max(segs, key=lambda s: len(re.sub(r"[\W\d_]+", "", s)))
    best = re.sub(r"\s+", " ", re.sub(r"\d+", "", best)).strip(" -|:")
    return best[:40].lower()


def fragment_is_safe(frag, url_mappings):
    """Reject fragments too short/generic to be a useful key."""
    f = (frag or "").strip().lower()
    if len(re.sub(r"[\W_]+", "", f)) < 4:
        return False
    return f not in ("epaper", "e-paper", "news", "daily", "bangladesh")


class LearnTracker:
    """Pure state: remembers what detection saw at the last event so a
    later manual dropdown change can be turned into a mapping suggestion."""
    WINDOW_S = 90

    def __init__(self):
        self.ctx = None

    def note_event(self, now, title, url, detected):
        self.ctx = {"ts": now, "title": title or "", "url": url or "", "detected": detected}

    def on_user_choice(self, now, chosen, current_mappings):
        """Returns a suggestion dict or None."""
        c = self.ctx
        if not c or now - c["ts"] > self.WINDOW_S:
            return None
        if not chosen or chosen == c["detected"]:
            return None
        frag = suggest_fragment(c["title"], c["url"])
        if not fragment_is_safe(frag, current_mappings):
            return None
        if current_mappings.get(frag) == chosen:
            return None
        return {"fragment": frag, "paper": chosen, "title": c["title"], "url": c["url"],
                "replaces": c["detected"]}
