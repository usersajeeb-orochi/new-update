"""Optional AI helpers (Groq through NAB): drop borderline off-topic headlines, merge the same story told in Bangla and English.
`ai` is an object with ask_json(system, user, fast=True, max_tokens=..) -> (dict|None, reason). Everything fails soft."""
import json

from . import bdfilter


def review(items, cfg, ai, log=print, below=4.0):
    brief = (cfg.get("brief") or "").strip()
    pool = [i for i, it in enumerate(items) if it.get("topic", 0) < below or not it.get("resolved", True)] if cfg.get("topic") == "tower" else \
           [i for i, it in enumerate(items) if it.get("score", 100) < 60]
    if not cfg.get("ai_check", True) or not pool:
        return items
    system = (bdfilter.PROMPT if cfg.get("topic") == "tower" else
              "You check news headlines for a Bangladesh press-release company. KEEP a headline only if it is clearly about the client brief below and is Bangladeshi news. "
              "DROP other countries, unrelated topics, name coincidences, social/press-release farms.\nCLIENT BRIEF: " + (brief or "keywords only") +
              '\nReply ONLY JSON: {"keep": [numbers]}')
    drop = set()
    for s in range(0, len(pool), 40):
        ch = pool[s:s + 40]
        lines = "\n".join(f"{n}. [{items[n].get('domain') or items[n].get('source', '')}] {items[n]['title']}" for n in ch)
        r, why = ai.ask_json(system, "Which headlines to KEEP? Reply ONLY JSON like {\"keep\": [1, 4]}.\n\n" + lines, fast=True, max_tokens=300)
        if r is None:
            log(f"  AI check skipped ({why})")
            return items
        keep = {int(x) for x in (r.get("keep") or []) if str(x).lstrip("-").isdigit()}
        drop |= {n for n in ch if n not in keep}
    if drop:
        log(f"  AI check removed {len(drop)} borderline link(s)")
    return [it for n, it in enumerate(items) if n not in drop]


def merge(groups, ai, log=print):
    """Join groups that are the same event in different words or languages. Cheap: only group titles are sent."""
    if len(groups) < 2 or len(groups) > 70:
        return groups
    lines = "\n".join(f"{i}. {g[0]['title']}" for i, g in enumerate(groups))
    r, why = ai.ask_json('Group news headlines (Bangla or English) that report the SAME single event. Reply ONLY JSON: {"same": [[0,3],[2,5,9]]}. Use [] if none. Do not merge merely related topics.',
                         lines, fast=True, max_tokens=300)
    if not r:
        return groups
    used, out = set(), []
    for s in r.get("same") or []:
        try:
            ids = [int(x) for x in s if 0 <= int(x) < len(groups) and int(x) not in used]
        except Exception:
            continue
        if len(ids) > 1:
            used |= set(ids)
            out.append([it for i in ids for it in groups[i]])
    if not out:
        return groups
    log(f"  AI joined {sum(len(o) for o in out) and len(used)} headlines into {len(out)} stories")
    rest = [g for i, g in enumerate(groups) if i not in used]
    res = out + rest
    for i, g in enumerate(res):
        for it in g:
            it["grp"] = i
    return res
