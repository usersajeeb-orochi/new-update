"""One search from start to finish: fetch -> keep news sites -> time window -> same-story groups -> only what is new -> save/send."""
import datetime
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import sources, filters, textmatch, resolve, output, bdfilter, aicheck
from .util import canon_url, domain_of, now, tokens


def rule_of(cfg):
    def L(k):
        v = cfg.get(k) or []
        return [x.strip() for x in (v.split("\n") if isinstance(v, str) else v) if str(x).strip()]
    return {"any": L("any"), "all": L("all"), "none": L("none")}


def _strip_source(title, source):
    if source and title.endswith(" - " + source):
        return title[: -len(source) - 3].strip()
    m = re.match(r"^(.*) - ([^-]{2,40})$", title)
    return m.group(1).strip() if (m and not source) else title


def gather(queries, hours, cfg, settings, log=print):
    srcs = cfg.get("sources") or ["gnews"]
    langs = cfg.get("languages") or ["en", "bn"]
    jobs = []
    for q in queries:
        if "gnews" in srcs:
            jobs.append((q, lambda q=q: sources.google_news(q, settings, langs, log)))
        if "gdelt" in srcs:
            jobs.append((q, lambda q=q: sources.gdelt(q, hours, settings, log)))
        if "brave" in srcs:
            jobs.append((q, lambda q=q: sources.brave(q, hours, settings, log)))
    if "feeds" in srcs:
        jobs.append(("feeds", lambda: sources.feeds(settings.get("feeds"), log)))

    def one(j):
        try:
            return j[1]()
        except Exception as e:
            log(f"  source failed: {str(e)[:90]}")
            return []
    out = []
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(jobs)))) as ex:
        for r in ex.map(one, jobs):
            out += r or []
    return out


def queries_for(rule, hours, chunk=5):
    """Long keyword lists are split into several short searches (Google ignores very long queries)."""
    anys = rule.get("any") or []
    if len(anys) <= chunk:
        return [textmatch.google_query(rule, hours)]
    return [textmatch.google_query({"any": anys[i:i + chunk], "all": rule.get("all"), "none": rule.get("none")}, hours) for i in range(0, len(anys), chunk)]


def process(items, rule, cfg, settings, hours, log=print, reference=None, min_sim=0.0, workers=10, judge=None):
    """Returns (items kept, stats). Each kept item has link/title/source/domain/published/ckey/resolved/via(/sim,label)."""
    block, allow = settings.get("blocklist") or [], settings.get("allowlist") or []
    cut = now() - datetime.timedelta(hours=hours) if hours else None
    st = {"fetched": len(items), "old": 0, "social": 0, "rule": 0, "dup": 0, "off": 0}
    step = []
    for it in items:
        it["title"] = _strip_source(it["title"], it.get("source", ""))
        if not it["title"] or not it["link"]:
            continue
        if cut and it.get("published") and it["published"] < cut:
            st["old"] += 1
            continue
        probe = it.get("source_url") or it["link"]
        if "news.google.com" in domain_of(it["link"]) and not it.get("source_url"):
            probe = ""
        if probe and (filters.blocked(probe, block) or not filters.allowed(probe, allow)):
            st["social"] += 1
            continue
        if not textmatch.rule_ok(rule, it["title"], it.get("snippet", ""), strict=(it["via"] == "feed")):
            st["rule"] += 1
            continue
        step.append(it)
    seen_t, uniq = set(), []                                     # same headline from the same outlet: resolve it once
    for it in step:
        k = (textmatch.norm(it["title"]), (it.get("source") or "").lower())
        if k in seen_t:
            st["dup"] += 1
            continue
        seen_t.add(k)
        uniq.append(it)

    def fix(it):
        it["link"], it["resolved"] = resolve.resolve(it["link"], log)
        return it
    with ThreadPoolExecutor(max_workers=workers) as ex:
        uniq = list(ex.map(fix, uniq))
    keep, seen_k = [], set()
    for it in uniq:
        d = domain_of(it["link"])
        if it["resolved"] and (filters.blocked(it["link"], block) or not filters.allowed(it["link"], allow)):
            st["social"] += 1
            continue
        it["domain"] = d if it["resolved"] else (domain_of(it.get("source_url", "")) or it.get("source", ""))
        it["ckey"] = canon_url(it["link"]) if it["resolved"] else "gn:" + textmatch.norm(it["title"]) + "|" + (it.get("source") or "")
        if it["ckey"] in seen_k:
            st["dup"] += 1
            continue
        seen_k.add(it["ckey"])
        if judge is not None and judge(it) is None:
            st["off"] += 1
            continue
        if reference is not None:
            it["sim"] = round(textmatch.similarity(reference, tokens(it["title"] + " " + it.get("snippet", ""))), 2)
            it["label"] = "same story" if it["sim"] >= 0.5 else "related" if it["sim"] >= 0.25 else "weak"
            if it["sim"] < min_sim:
                continue
        keep.append(it)
    return keep, st


def make_judge(rule, cfg):
    """Bangladesh-only + topic check from NewsBot. cfg: bd_only (bool), level Strict/Balanced/Wide, topic 'tower' or 'keywords'."""
    if not cfg.get("bd_only"):
        return None
    level = cfg.get("level") or "Balanced"
    if cfg.get("topic") == "tower":
        ctx = {"level": level, "kind": "default"}
    else:
        sets = [bdfilter.compile_terms(bdfilter.query_terms(k)) for k in (rule.get("any") or []) + (rule.get("all") or [])]
        ctx = {"level": level, "kind": "query", "term_sets": sets}

    def judge(it):
        it["host"] = it.get("domain") or domain_of(it.get("source_url", "")) or ""
        if not it.get("resolved", True) and not it["host"]:
            it["host"] = "unknown"
        return bdfilter.evaluate(it, ctx)
    return judge


def group(items, thr=0.6):
    """Cluster near-identical headlines (the same wire story run by many outlets); newest first inside, groups newest first."""
    items = sorted(items, key=lambda x: x.get("published") or datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc), reverse=True)
    groups = []
    for it in items:
        for g in groups:
            if textmatch.title_sim(g[0]["title"], it["title"]) >= thr:
                g.append(it)
                break
        else:
            groups.append([it])
    for i, g in enumerate(groups):
        for it in g:
            it["grp"] = i
    return groups


def slug(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")[:40] or "search"


def run_search(sid, cfg, settings, store, out_dir, log=print, ai=None):
    name = cfg.get("name") or sid
    hours = float(cfg.get("hours", 24))
    rule = rule_of(cfg)
    if not (rule["any"] or rule["all"]):
        log("  nothing to search: add at least one keyword")
        return {"new": 0, "groups": []}
    log(f"== {name}  (last {hours:g} h)")
    raw = gather(queries_for(rule, hours), hours, cfg, settings, log)
    keep, st = process(raw, rule, cfg, settings, hours, log, judge=make_judge(rule, cfg))
    if ai is not None and keep:
        keep = aicheck.review(keep, cfg, ai, log)
    fresh = [it for it in keep if not store.seen(sid, it["ckey"])]
    groups = group(fresh)
    if ai is not None and len(groups) > 1:
        groups = aicheck.merge(groups, ai, log)
    ids = []
    for g in groups:
        for it in g:
            i = store.add(sid, it)
            it["_id"] = i
            if i:
                ids.append(i)
    store.log_run(sid, st["fetched"], len(fresh), f"old {st['old']}, social/blocked {st['social']}, rule {st['rule']}, duplicate {st['dup']}")
    log(f"  fetched {st['fetched']}, dropped: {st['old']} too old, {st['social']} social/blocked, {st['rule']} not matching, {st.get('off',0)} off-topic/foreign, {st['dup']} duplicates  ->  {len(fresh)} new links in {len(groups)} stories")
    path = None
    if groups:
        title = f"{name}: {len(groups)} new stories, last {hours:g} h  ({datetime.datetime.now().strftime('%d %b %Y %H:%M')})"
        outs = cfg.get("outputs") or ["txt"]
        if "txt" in outs:
            path = output.write_txt(os.path.join(out_dir, f"{slug(name)}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.txt"), title, groups)
            output.write_txt(os.path.join(out_dir, f"{slug(name)}_latest_links.txt"), title, groups, plain_links=True)
            log(f"  text file: {path}")
        if "telegram" in outs:
            if output.send_telegram(settings, title, groups, log):
                store.mark_sent(ids)
    return {"new": len(fresh), "groups": groups, "file": path, "stats": st}


def find_similar(headline, body, cfg, settings, log=print, hours=72):
    """Paste a news item: search its keywords, keep what is the same story or closely related."""
    text = (headline + " " + body).strip()
    kw = textmatch.keywords_of(text, 8)
    if not kw:
        return {"queries": [], "groups": [], "stats": {}}
    queries = []
    if headline.strip():
        queries.append(headline.strip())
    queries += [" ".join(kw[:4]), " ".join(kw[:6])]
    queries = list(dict.fromkeys(queries))
    c = dict(cfg or {})
    raw = gather([q + (f" when:{int(hours)}h" if hours else "") for q in queries], hours, c, settings, log)
    ref = tokens(text)
    keep, st = process(raw, {"any": [], "all": [], "none": []}, c, settings, hours, log, reference=ref, min_sim=0.18)
    groups = group(keep)
    groups.sort(key=lambda g: -max(x.get("sim", 0) for x in g))
    for i, g in enumerate(groups):
        g.sort(key=lambda x: -x.get("sim", 0))
        for it in g:
            it["grp"] = i
    return {"queries": queries, "keywords": kw, "groups": groups, "stats": st}


class Scheduler(threading.Thread):
    """Runs each enabled saved search every N minutes. Last run times come from the database, so a restart does not re-run at once."""
    def __init__(self, load_searches, run_one, store, log=print):
        super().__init__(daemon=True)
        self.load, self.run_one, self.store, self.log = load_searches, run_one, store, log
        self.stop = threading.Event()

    def last(self, sid):
        r = self.store.db.execute("SELECT started FROM runs WHERE search=? ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        return datetime.datetime.fromisoformat(r[0]) if r else None

    def run(self):
        while not self.stop.is_set():
            for sid, cfg in (self.load() or {}).items():
                try:
                    every = float(cfg.get("every_minutes") or 0)
                    if not cfg.get("enabled", True) or every <= 0:
                        continue
                    last = self.last(sid)
                    if last is None or (datetime.datetime.now() - last).total_seconds() >= every * 60:
                        self.run_one(sid, cfg)
                except Exception as e:
                    self.log(f"scheduler: {sid}: {e}")
            self.stop.wait(30)
