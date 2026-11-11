# nab_text.py - small text helpers with no dependencies.
import re

_EMOJI_PREFIX_RE = re.compile(r"^[\U0001F000-\U0001FFFF\u2190-\u2BFF\uFE0F\u200D\s]+")


def strip_emoji_prefix(name):
    """'📰 New Age' -> 'New Age'; a plain 'New Age' is returned untouched."""
    if not name:
        return name
    out = _EMOJI_PREFIX_RE.sub("", name, count=1)
    return out if out else name.strip()
