# nab_clip_scan.py — "which newspapers were actually clipped on date X?"
#
# Shared by nab_app.py (end-of-session prompt) and nab_tracker.py (auto-tick
# the Daily Check list). Kept in its own module so neither has to import the
# other — the tracker is loaded by nab_constants, so importing nab_app from
# it would be circular.
#
# Clip filenames are written by NAB as:
#     "{Paper}, Page-{n}, Pos-{p}, S-{s}, Date-{DD-MM-YYYY}.jpg"
# under:
#     base_root / YYYY / Month / DD-MM-YYYY / Category[/Sub] /
#
import os
import re
import json
import logging
import difflib
import nab_text   # strip_emoji_prefix - no GUI deps

_DOC = os.path.join(os.path.expanduser("~"), "Documents")

# NAB writes its settings here. The tracker used to look for "nab_settings.json",
# which NAB has never written — so its base_root lookup always silently fell
# through to a folder that doesn't exist, and the heatmap came up empty.
SETTINGS_FILE = os.path.join(_DOC, "news_clipper_settings.json")

_DATE_IN_NAME = re.compile(r"Date-(\d{2}-\d{2}-\d{4})", re.I)
_IMG_EXT = (".jpg", ".jpeg", ".png")


def nab_base_root():
    """Where NAB saves clips. Reads NAB's real settings file, falls back to
    the same default NAB itself uses."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                root = json.load(f).get("base_root", "")
            if root and os.path.isdir(root):
                return root
    except Exception as e:
        logging.error(f"nab_base_root: {e}")
    return os.path.join(_DOC, "Monitoring")


# Learned spellings, one file per PC (not synced between machines). A raw
# filename name that doesn't match anything — a typo, a house abbreviation,
# a paper renamed since — gets mapped here once (via the tracker's "🔗 Map"
# button on an unmatched clip) and auto-matches every time after that,
# instead of showing up as "unknown" forever.
ALIASES_FILE = os.path.join(_DOC, "nab_paper_aliases.json")


def load_aliases():
    try:
        if os.path.exists(ALIASES_FILE):
            with open(ALIASES_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logging.error(f"load_aliases: {e}")
    return {}


def save_alias(raw_name, canonical_name):
    """Remember raw_name -> canonical_name for every future scan."""
    try:
        aliases = load_aliases()
        aliases[_norm(raw_name)] = canonical_name
        os.makedirs(os.path.dirname(ALIASES_FILE), exist_ok=True)
        with open(ALIASES_FILE, "w", encoding="utf-8") as f:
            json.dump(aliases, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"save_alias: {e}")
        return False


def _norm(name):
    """Normalise a paper name for matching.

    NAB's source list and the tracker's paper list are maintained separately,
    so the same paper is often spelled differently ('Daily Star' vs 'The Daily
    Star', 'Kaler Kantha' vs 'Kaler Kantho'). Lowercase, drop a leading
    'the', strip everything that isn't a letter or digit."""
    n = (name or "").strip().lower()
    if n.startswith("the "):
        n = n[4:]
    return re.sub(r"[^a-z0-9]", "", n)


def clipped_paper_names(target_date, base_root=None):
    """Raw paper names (as written into filenames) clipped on target_date.

    target_date: datetime.date or a 'DD-MM-YYYY' string.
    Returns {raw_name: clip_count}."""
    if hasattr(target_date, "strftime"):
        dstr = target_date.strftime("%d-%m-%Y")
    else:
        dstr = str(target_date)

    base = base_root or nab_base_root()
    found = {}
    if not base or not os.path.isdir(base):
        return found

    def _walk(path, in_date_folder=False, depth=0):
        if depth > 8:            # guard against symlink loops
            return
        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError):
            return
        for e in entries:
            if e.name.startswith(".") or e.name.startswith("__"):
                continue
            try:
                if e.is_dir():
                    _walk(e.path, in_date_folder or e.name == dstr, depth + 1)
                    continue
                if not e.name.lower().endswith(_IMG_EXT):
                    continue
            except OSError:
                continue

            # Trust the date stamped in the filename when it's there; fall
            # back to the folder name for files saved before that convention.
            m = _DATE_IN_NAME.search(e.name)
            if m:
                if m.group(1) != dstr:
                    continue
            elif not in_date_folder:
                continue

            paper = e.name.split(",")[0].strip()
            if paper:
                found[paper] = found.get(paper, 0) + 1

    _walk(base)
    return found


def match_to_list(raw_counts, known_papers, return_methods=False):
    """Map raw filename paper names onto a canonical list (the tracker's).

    Tries, in order, until one hits:
      1. exact match (normalised)
      2. a previously learned alias (see save_alias)
      3. substring match, longest candidate wins
      4. fuzzy match (catches typos/near-spellings a substring test can't —
         "Kaler Kantho" vs "Kaler Kantha" — without being loose enough to
         cross-match two genuinely different papers)

    Returns (matched, unknown), or (matched, unknown, methods) when
    return_methods=True — methods is {canonical_paper: how_it_matched}, used
    by the tracker to show a confidence hint next to fuzzy matches so the
    operator can sanity-check them instead of blindly trusting a guess.
      matched — {canonical_paper: clip_count}
      unknown — {raw_name: clip_count} for names that matched nothing, so the
                UI can show them instead of silently dropping them.
    """
    index = {}
    for p in known_papers:
        index.setdefault(_norm(p), p)
    aliases = load_aliases()

    matched, unknown, methods = {}, {}, {}
    for raw, count in raw_counts.items():
        key = _norm(raw)
        hit, how = index.get(key), "exact"

        if not hit and key in aliases and aliases[key] in known_papers:
            hit, how = aliases[key], "alias"

        if not hit:
            # Substring match both ways — handles 'Daily Star' vs
            # 'The Daily Star Online', and abbreviations that are a prefix.
            # Longest candidate wins so 'Sangbad' can't steal a clip that
            # belongs to 'Pratidiner Sangbad'.
            cands = [orig for k, orig in index.items()
                     if k and (k in key or key in k)]
            if cands:
                hit, how = max(cands, key=lambda s: len(_norm(s))), "substring"

        if not hit and key:
            close = difflib.get_close_matches(
                key, list(index.keys()), n=1, cutoff=0.84)
            if close:
                hit, how = index[close[0]], "fuzzy"

        if hit:
            matched[hit] = matched.get(hit, 0) + count
            # Keep the strongest method seen for this paper across multiple
            # raw spellings (an exact hit elsewhere shouldn't be downgraded
            # to "fuzzy" just because one clip that day used a typo).
            rank = {"exact": 0, "alias": 1, "substring": 2, "fuzzy": 3}
            if hit not in methods or rank[how] < rank[methods[hit]]:
                methods[hit] = how
        else:
            unknown[raw] = unknown.get(raw, 0) + count

    if return_methods:
        return matched, unknown, methods
    return matched, unknown


def papers_clipped_on(target_date, known_papers, base_root=None, return_methods=False):
    """Convenience wrapper: date + canonical list → (matched, unknown)."""
    return match_to_list(clipped_paper_names(target_date, base_root), known_papers,
                         return_methods=return_methods)


# ─────────────────────────────────────────────────────────────────────────
# LIVE PAPER DETECTION (used by NAB's clipboard monitor)
# ─────────────────────────────────────────────────────────────────────────
# Kept here, not in nab_app.py, so the decision logic is a plain function
# that can be tested without a GUI or Windows APIs.

def _name_key(s):
    """Lowercase letters/digits only (unicode-aware, so Bangla names keep
    their letters), emoji prefix removed. Never returns something that
    could spuriously equal another empty key — callers must check truthy."""
    return re.sub(r"[\W_]+", "", nab_text.strip_emoji_prefix(s or "").lower())


def resolve_paper(name, paper_list):
    """Map a mapping/lock value onto the exact entry in paper_list.
    A mapping typed without the emoji prefix ("New Age") used to fail the
    plain `in paper_list` check against "📰 New Age" and silently select
    nothing."""
    if not name:
        return None
    if name in paper_list:
        return name
    key = _name_key(name)
    if not key:
        return None
    for p in paper_list:
        if _name_key(p) == key:
            return p
    return None


def detect_paper(context, signal_text, url_mappings, paper_list,
                 lock_paper=None, allow_name_fallback=False):
    """Decide which paper a browser tab / copied image belongs to.

    Returns (paper_or_None, how, detail). Order matters:
      1. URL/title mapping — the LONGEST matching fragment wins, and a
         fragment whose paper can't be resolved is skipped (next-longest
         is tried) rather than ending the search.
      2. An explicit 📍 lock for this tab (operator intent beats a guess,
         but never beats a real mapping match — an accidental lock must not
         be able to override genuine detection).
      3. Paper-NAME match against title/URL, only when allowed: sites whose
         tab title is "Rupali Bangladesh ePaper" carry the name even though
         no mapping was ever written. The generic word "epaper" is removed
         first so it can't match or mask anything.
    """
    ctx = (context or "").lower()
    if ctx.strip():
        hits = sorted(((f, v) for f, v in url_mappings.items()
                       if f and f.lower() in ctx),
                      key=lambda fv: len(fv[0]), reverse=True)
        for frag, val in hits:
            paper = resolve_paper(val, paper_list)
            if paper:
                return paper, "mapping", frag

    if lock_paper:
        paper = resolve_paper(lock_paper, paper_list)
        if paper:
            return paper, "lock", ""

    if allow_name_fallback and (signal_text or "").strip():
        s = re.sub(r"\be[\s\-_.]*paper\b", " ", signal_text.lower())
        s = re.sub(r"[\W_]+", "", s)
        best, best_len = None, 0
        for p in paper_list:
            n = _name_key(p)
            # >= 5 chars: short names ("TBS", "TOB") are too likely to
            # appear inside unrelated text — those rely on mappings.
            if len(n) >= 5 and n in s and len(n) > best_len:
                best, best_len = p, len(n)
        if best:
            return best, "name", _name_key(best)

    return None, None, ""


def explain_detection(text, url_mappings, paper_list):
    """Mapping tester: what would detection do with this title/URL?
    Returns (paper_or_None, [lines]) — the lines say which fragments
    matched, which one won, and what happens if none did."""
    lines = []
    ctx = (text or "").lower()
    if not ctx.strip():
        return None, ["Paste a tab title or URL above."]
    hits = sorted(((f, v) for f, v in url_mappings.items() if f and f.lower() in ctx),
                  key=lambda fv: len(fv[0]), reverse=True)
    winner = None
    for i, (frag, val) in enumerate(hits):
        paper = resolve_paper(val, paper_list)
        tag = ""
        if paper and winner is None:
            winner, tag = paper, "  ← WINS (longest resolvable match)"
        elif not paper:
            tag = "  (skipped — paper not in your list)"
        lines.append(f"✔ '{frag}' → {val}{tag}")
    if winner:
        return winner, lines
    paper, how, detail = detect_paper(text, text, url_mappings, paper_list,
                                      allow_name_fallback=True)
    if paper:
        lines.append(f"✔ No mapping matched, but the paper NAME '{detail}' appears "
                     f"in the text → {paper} (only used right after copying an image)")
        return paper, lines
    lines.append("✘ No mapping fragment is contained in this text, and no paper name "
                 "of 5+ letters appears in it.")
    lines.append("Add a fragment that appears in the text above (domain or a distinctive title word).")
    return None, lines
