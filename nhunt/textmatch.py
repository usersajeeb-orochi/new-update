"""Keyword rules (any / all / none) and 'find the same story' scoring."""
import re
from collections import Counter

from .util import tokens


def norm(s):
    return " ".join((s or "").lower().replace("‌", "").replace("‍", "").split())


def _hit(term, text):
    t = norm(term)
    if not t:
        return False
    if t.endswith("*"):
        t = t[:-1]
        return re.search(r"(?<![0-9a-z])" + re.escape(t), text) is not None if re.match(r"[a-z0-9]", t) else t in text
    if re.match(r"[a-z0-9]", t):
        return re.search(r"(?<![0-9a-z])" + re.escape(t) + r"(?:s|es)?(?![0-9a-z])", text) is not None
    return t in text


def rule_ok(rule, title, snippet="", strict=True):
    """rule = {any:[], all:[], none:[]}. When strict is False (engine already searched the keywords) only 'none' is enforced."""
    text = norm(title + " " + snippet)
    if any(_hit(t, text) for t in rule.get("none") or []):
        return False
    if not strict:
        return True
    anys = rule.get("any") or []
    if anys and not any(_hit(t, text) for t in anys):
        return False
    return all(_hit(t, text) for t in rule.get("all") or [])


def google_query(rule, hours=None):
    """Turn a rule into one search string:  ("a b" OR c) "d" -x  when:24h"""
    def q(t):
        t = t.strip().rstrip("*")
        return f'"{t}"' if " " in t else t
    parts = []
    if rule.get("any"):
        parts.append("(" + " OR ".join(q(t) for t in rule["any"]) + ")")
    parts += [q(t) for t in rule.get("all") or []]
    parts += ["-" + q(t) for t in rule.get("none") or []]
    if hours:
        parts.append(f"when:{int(hours)}h" if hours < 48 else f"when:{int(round(hours / 24))}d")
    return " ".join(parts)


def keywords_of(text, n=8):
    """Most telling words of a pasted news item: names, numbers and repeated words first."""
    raw = re.findall(r"[0-9A-Za-zঀ-৿]+", text or "")
    cnt = Counter(tokens(text))
    caps = {w.lower() for w in raw if w[:1].isupper() and len(w) > 2}
    score = {}
    for w, c in cnt.items():
        s = c + (1.5 if w in caps else 0) + (1.0 if re.search(r"\d", w) else 0) + (0.5 if len(w) > 6 else 0) + (0.5 if re.search(r"[ঀ-৿]", w) else 0)
        score[w] = s
    return [w for w, _ in sorted(score.items(), key=lambda x: (-x[1], x[0]))[:n]]


def similarity(a_tokens, b_tokens):
    A, B = set(a_tokens), set(b_tokens)
    if not A or not B:
        return 0.0
    return len(A & B) / ((len(A) * len(B)) ** 0.5)


def title_sim(a, b):
    A, B = set(tokens(a)), set(tokens(b))
    return len(A & B) / len(A | B) if A and B else 0.0
