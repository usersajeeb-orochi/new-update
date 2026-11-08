# nab_tool_shot.py — Screenshot Bot (the old "Nitro PR Engine" / Screenshot_Bot.pyw), now a NAB tool.
#
# Paste links -> a real browser opens each page, scrolls it so lazy images load, hides the junk (ads, sticky bars,
# cookie banners, sidebars) and saves ONE tidy JPEG of the article.  Every shot is written to  shots.json  with its
# real pixel width / height, which the PR Value Calculator uses for the Online sheet.
#
# Changes compared with the old script:
#   * runs inside NAB (progress, log, stop button) — no second window / process
#   * browser order: Google Chrome -> Microsoft Edge (always on Windows) -> bundled Chromium
#   * the crop finds the article's real bottom edge from the page itself; the pixel-density scan is only the fallback
#   * pre-flight only drops links that are really dead (404 / 410 / no such host); 403 and 429 are bot-protection, not dead
#   * duplicate file names get _2, _3 (the old one overwrote them); results are saved as a manifest
#   * lazy-load scrolling instead of a fixed 4 s sleep, ad/tracker blocking by domain list, resume-safe stop
import os
import re
import io
import json
import time
import asyncio
import logging
import threading
import urllib.request
import urllib.error
import concurrent.futures
from urllib.parse import urlparse

import nab_engine

SETTINGS_FILE = os.path.join(nab_engine.DOC_DIR, "nab_shot_settings.json")
DEFAULTS = {"out_dir": "", "live": False, "conc": 3, "crop": "auto", "quality": 70, "width": 1366, "pad": 20}
AD_HOSTS = ("googleads", "doubleclick", "googlesyndication", "google-analytics", "googletagmanager", "taboola", "outbrain",
            "adsystem", "adnxs", "facebook.net/tr", "hotjar", "scorecardresearch", "quantserve")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CLEAN_JS = """() => {
  const kill = 'iframe, aside, .sidebar, #sidebar, .widget-area, #comments, .comments, .ad, .ads, .advert, [id^="google_ads"], [class*="cookie"], [id*="cookie"], [class*="consent"], [class*="newsletter"], [class*="popup"], [class*="modal-backdrop"]';
  document.querySelectorAll(kill).forEach(e => { try { e.remove(); } catch (x) {} });
  document.querySelectorAll('*').forEach(e => {
    const st = getComputedStyle(e);
    if (st.position === 'fixed' || st.position === 'sticky') e.style.display = 'none';
  });
}"""

ARTICLE_JS = """() => {
  const sel = ['[itemprop="articleBody"]','article','.article-body','.story-body','.news-details','.details','.post-content','.entry-content','.content-details','main','#content'];
  let best = null, bs = 0;
  for (const s of sel) for (const e of document.querySelectorAll(s)) {
    const r = e.getBoundingClientRect(); if (r.height < 250 || r.width < 300) continue;
    const t = (e.innerText || '').length; if (t < 400) continue;
    const score = t - Math.abs(r.width - innerWidth) * 0.2; if (score > bs) { bs = score; best = e; }
  }
  if (!best) return null;
  const r = best.getBoundingClientRect();
  return { bottom: Math.round(r.bottom + scrollY), top: Math.round(r.top + scrollY), h: Math.round(document.documentElement.scrollHeight) };
}"""

SCROLL_JS = """async () => {
  const h = () => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  let y = 0; const step = Math.max(400, innerHeight * 0.8);
  while (y < h() && y < 30000) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 160)); y += step; }
  window.scrollTo(0, h()); await new Promise(r => setTimeout(r, 400)); window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 500));
  return h();
}"""


def _safe(s):
    return re.sub(r'[\\/*?:"<>|]+', "", s or "").strip().strip(".")


def _slug(url):
    p = [x for x in urlparse(url).path.split("/") if x]
    s = re.sub(r"\.(html?|php|aspx?)$", "", p[-1], flags=re.I) if p else "home"
    s = re.sub(r"[^\w\-]+", "-", s)[:24].strip("-")
    return s or "home"


def deps():
    """Which optional pieces are installed — shown in the UI so nothing fails silently."""
    out = {}
    for name in ("playwright", "playwright_stealth", "cv2", "numpy"):
        try:
            __import__(name)
            out[name] = True
        except Exception:
            out[name] = False
    return out


class Tool:
    def __init__(self, engine):
        self.e = engine
        self.lock = threading.Lock()
        self.running = False
        self.stop = False
        self.set = self._load()

    # ------------------------------------------------------------------ settings
    def _load(self):
        d = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                d.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except Exception:
            pass
        return d

    def _save(self):
        try:
            tmp = SETTINGS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.set, f)
            os.replace(tmp, SETTINGS_FILE)
        except Exception as e:
            logging.error(f"shot settings: {e}")

    def _emit(self, **kw):
        self.e.hub.emit("tool", tool="shot", **kw)

    def _log(self, msg, kind=""):
        self._emit(ev="log", msg=msg, kind=kind, at=time.strftime("%H:%M:%S"))

    def _out_dir(self):
        base = self.set.get("out_dir") or os.path.join(nab_engine.DOC_DIR, "NAB_Screenshots")
        return os.path.join(base, time.strftime("%d-%m-%Y"))

    def api_state(self, a):
        return {"ok": True, "settings": self.set, "running": self.running, "deps": deps(), "out": self._out_dir()}

    def api_settings(self, a):
        for k in DEFAULTS:
            if k in a:
                v = a[k]
                if k in ("live",):
                    v = bool(v)
                elif k in ("conc", "quality", "width", "pad"):
                    try:
                        v = int(v)
                    except Exception:
                        continue
                    v = max({"conc": 1, "quality": 30, "width": 800, "pad": 0}[k], min(v, {"conc": 8, "quality": 95, "width": 2560, "pad": 400}[k]))
                elif k == "crop" and v not in ("auto", "density", "none"):
                    continue
                self.set[k] = v
        self._save()
        return {"ok": True, "settings": self.set, "out": self._out_dir()}

    def api_stop(self, a):
        self.stop = True
        return {"ok": True}

    def api_open(self, a):
        p = a.get("path") or self._out_dir()
        return self.e.reveal(p if os.path.isdir(p) else os.path.dirname(p))

    # ------------------------------------------------------------------ run
    def api_run(self, a):
        urls = []
        for u in re.split(r"[\s,]+", a.get("text") or "\n".join(a.get("urls") or [])):
            u = u.strip()
            if not u:
                continue
            if not re.match(r"^https?://", u, re.I):
                u = "https://" + u
            if re.match(r"^https?://[^/\s]+\.[^/\s]+", u, re.I):
                urls.append(u)
        urls = list(dict.fromkeys(urls))
        if not urls:
            return {"ok": False, "error": "Paste at least one link."}
        d = deps()
        if not d["playwright"]:
            return {"ok": False, "error": "Playwright is not installed.  Run:  pip install playwright playwright-stealth   then   playwright install chromium"}
        with self.lock:
            if self.running:
                return {"ok": False, "error": "A run is already in progress."}
            self.running, self.stop = True, False
        threading.Thread(target=self._thread, args=(urls,), daemon=True, name="NAB-Shot").start()
        return {"ok": True, "n": len(urls)}

    def _thread(self, urls):
        t0 = time.time()
        res = {"ok": 0, "fail": 0, "out": self._out_dir()}
        try:
            os.makedirs(res["out"], exist_ok=True)
            self._emit(ev="begin", total=len(urls))
            asyncio.run(self._main(urls, res))
        except Exception as e:
            logging.exception("shot")
            self._log(f"Stopped: {e}", "err")
        finally:
            self.running = False
            self._emit(ev="done", ok_n=res["ok"], fail_n=res["fail"], out=res["out"], secs=round(time.time() - t0, 1), stopped=self.stop)

    # ---- pre-flight: drop only links that are certainly dead
    @staticmethod
    def _ping(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
            with urllib.request.urlopen(req, timeout=8) as r:
                return url, True
        except urllib.error.HTTPError as e:
            return url, e.code not in (404, 410)
        except urllib.error.URLError as e:
            return url, "Name or service not known" not in str(e) and "getaddrinfo failed" not in str(e) and "nodename" not in str(e)
        except Exception:
            return url, True

    async def _launch(self, p):
        prof = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "NAB", "shot_profile")
        os.makedirs(prof, exist_ok=True)
        base = dict(user_data_dir=prof, headless=not self.set["live"], user_agent=UA,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                    viewport={"width": int(self.set["width"]), "height": 900}, device_scale_factor=1)
        last = None
        for ch in ("chrome", "msedge", None):
            try:
                kw = dict(base)
                if ch:
                    kw["channel"] = ch
                ctx = await p.chromium.launch_persistent_context(**kw)
                self._log("Browser: " + {"chrome": "Google Chrome", "msedge": "Microsoft Edge"}.get(ch, "built-in Chromium"))
                return ctx
            except Exception as e:
                last = e
        raise RuntimeError("No browser could be started (install Google Chrome, or run  playwright install chromium).  " + str(last)[:160])

    async def _main(self, urls, res):
        loop = asyncio.get_running_loop()
        self._log(f"Checking {len(urls)} link(s)…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            pings = await asyncio.gather(*[loop.run_in_executor(ex, self._ping, u) for u in urls])
        good = [u for u, ok in pings if ok]
        dead = [u for u, ok in pings if not ok]
        manifest = []
        for u in dead:
            res["fail"] += 1
            manifest.append({"url": u, "fail": "dead link", "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
            self._emit(ev="item", url=u, ok=False, error="Dead link (404 / no such site)")
        if dead:
            self._log(f"{len(dead)} dead link(s) skipped.", "warn")
        done = len(dead)
        self._emit(ev="prog", n=done, total=len(urls))
        if good:
            try:
                from playwright.async_api import async_playwright
                try:
                    from playwright_stealth import Stealth
                    cm = Stealth().use_async(async_playwright())
                except Exception as e:
                    self._log("Stealth mode not available, continuing without it", "warn")
                    cm = async_playwright()
                async with cm as p:
                    ctx = await self._launch(p)

                    async def block(route):
                        u = route.request.url
                        if any(h in u for h in AD_HOSTS):
                            await route.abort()
                        else:
                            await route.continue_()
                    await ctx.route("**/*", block)
                    sem = asyncio.Semaphore(int(self.set["conc"]))
                    lockn = asyncio.Lock()
                    used = set()

                    async def one(u):
                        nonlocal done
                        if self.stop:
                            return
                        async with sem:
                            if self.stop:
                                return
                            r = await self._capture(ctx, u, res["out"], used, lockn)
                        manifest.append(r)
                        res["ok" if not r.get("fail") else "fail"] += 1
                        done += 1
                        self._emit(ev="item", url=u, ok=not r.get("fail"), file=r.get("file"), w=r.get("w"), h=r.get("h"), kb=r.get("kb"), error=r.get("fail"))
                        self._emit(ev="prog", n=done, total=len(urls))
                    await asyncio.gather(*[one(u) for u in good])
                    await ctx.close()
            except Exception as e:
                self._log(str(e), "err")
                for u in good:
                    if not any(m["url"] == u for m in manifest):
                        manifest.append({"url": u, "fail": str(e)[:100], "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
                        res["fail"] += 1
        self._write_manifest(res["out"], manifest)
        fails = [m["url"] for m in manifest if m.get("fail")]
        if fails:
            try:
                with open(os.path.join(res["out"], f"Failed_Links_{int(time.time())}.txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(fails))
            except Exception:
                pass

    @staticmethod
    def _write_manifest(folder, items):
        path = os.path.join(folder, "shots.json")
        old = []
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            pass
        urls = {i["url"] for i in items}
        merged = [o for o in old if o.get("url") not in urls] + items
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=1)
        except Exception as e:
            logging.error(f"manifest: {e}")

    # ---- one page: up to 3 strategies, each more patient than the last
    STRATS = ({"wait": "domcontentloaded", "load": 15000, "settle": 0.5}, {"wait": "commit", "load": 9000, "settle": 6}, {"wait": "commit", "load": 9000, "settle": 12})

    @staticmethod
    def _why(e):
        m = str(e).split("\n")[0]
        for k, v in (("ERR_NAME_NOT_RESOLVED", "site not found (check the link / internet)"), ("ERR_CONNECTION_REFUSED", "connection refused"),
                     ("ERR_CERT", "certificate problem on the site"), ("ERR_TOO_MANY_REDIRECTS", "redirect loop"), ("ERR_BLOCKED", "blocked by the site"),
                     ("ERR_CONNECTION_TIMED_OUT", "site too slow / blocked"), ("Timeout", "page took too long (slow site or bot check)"),
                     ("ERR_INTERNET_DISCONNECTED", "no internet"), ("ERR_TUNNEL_CONNECTION_FAILED", "no internet / proxy or firewall blocks the site"), ("ERR_PROXY", "proxy problem"), ("Target page, context or browser has been closed", "browser was closed")):
            if k in m:
                return v
        return m[:110] or "failed"

    async def _capture(self, ctx, url, folder, used, lockn):
        dom = urlparse(url).netloc.replace("www.", "")
        short = dom if re.match(r"^[\d.:]+$", dom.split(":")[0]) else dom.split(".")[0]
        last_err = "failed"
        for attempt, stg in enumerate(self.STRATS):
            if self.stop:
                break
            page = await ctx.new_page()
            try:
                self._log(f"{short}" + (f"  (try {attempt + 1}: slower)" if attempt else ""))
                try:
                    await page.goto(url, wait_until=stg["wait"], timeout=60000)
                except Exception as e:
                    if "Timeout" not in str(e):
                        raise
                    self._log(f"{short}: slow page, using what has loaded", "warn")
                try:
                    await page.wait_for_load_state("load", timeout=stg["load"])
                except Exception:
                    pass
                if "news.google." in urlparse(page.url).netloc:              # Google News link: wait for the real article
                    try:
                        await page.wait_for_url(lambda u: "news.google." not in u, timeout=20000)
                        await page.wait_for_load_state("load", timeout=12000)
                    except Exception:
                        pass
                if stg["settle"]:
                    await asyncio.sleep(stg["settle"])
                title = await page.title()
                if any(k in title for k in ("Just a moment", "Attention Required", "Cloudflare", "Verify you are human")):
                    self._log(f"{short}: security check, waiting up to 45 s" + ("" if self.set["live"] else " (turn on Live view to solve it by hand)"), "warn")
                    await page.wait_for_function("() => !/Just a moment|Attention Required|Cloudflare|Verify you are human/.test(document.title)", timeout=45000)
                    await asyncio.sleep(3)
                await page.evaluate(SCROLL_JS)
                site = await page.evaluate("""() => { const m = document.querySelector('meta[property="og:site_name"]'); return m ? m.content : ''; }""")
                await page.evaluate(CLEAN_JS)
                await asyncio.sleep(0.4)
                vw = int(self.set["width"])
                info = await page.evaluate(ARTICLE_JS) if self.set["crop"] == "auto" else None
                total_h = await page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
                clip_h = None
                if info and info.get("bottom"):
                    clip_h = max(300, min(int(total_h), 16000, info["bottom"] + int(self.set["pad"])))
                png = await page.screenshot(full_page=True, type="png")      # (clip + full_page repeats content in Chromium, so crop afterwards)
                data, w, h, ink = self._finish(png, self.set["crop"] == "density" or (self.set["crop"] == "auto" and not info), int(self.set["quality"]),
                                               clip_h, self.set["crop"] != "none")
                if h < 450 or ink < 0.004:
                    last_err = "page came out blank or too short (blocked, paywall or bot check)"
                    self._log(f"{short}: {last_err}", "warn")
                    continue
                name = _safe(site) or short.capitalize()
                base = re.sub(r'[\\/*?:"<>|]', "_", f"{name} - {_slug(url)}")
                async with lockn:
                    fn, n = base + ".jpg", 1
                    while fn in used or os.path.exists(os.path.join(folder, fn)):
                        n += 1
                        fn = f"{base}_{n}.jpg"
                    used.add(fn)
                with open(os.path.join(folder, fn), "wb") as f:
                    f.write(data)
                self._log(f"saved  {fn}  ({w}x{h}, {len(data) // 1024} KB)", "ok")
                return {"url": url, "file": fn, "site": name, "w": w, "h": h, "kb": len(data) // 1024, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "mode": "article" if info else ("density" if self.set["crop"] != "none" else "full")}
            except Exception as e:
                last_err = self._why(e)
                self._log(f"{short}: {last_err}", "warn" if attempt < len(self.STRATS) - 1 else "err")
                if last_err.startswith(("site not found", "no internet", "browser was closed", "proxy")):
                    break
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
        return {"url": url, "fail": last_err, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---- image post-processing
    @staticmethod
    def _footer_cut(im):
        """Top of a full-width dark / coloured footer band (>= 120 rows), else None.  Looks only below 25 % of the page."""
        import numpy as np
        a = np.asarray(im.resize((120, max(1, im.height // 4))).convert("L"), dtype="int16")
        nonwhite = (a < 235).mean(axis=1) > 0.92             # a row that is (almost) all coloured / dark = band
        n = len(nonwhite)
        run_start, best = None, None
        for i in range(int(n * 0.25), n + 1):
            on = i < n and nonwhite[i]
            if on and run_start is None:
                run_start = i
            elif not on and run_start is not None:
                if (i - run_start) * 4 >= 120:
                    best = run_start * 4
                    break
                run_start = None
        return best

    @staticmethod
    def _finish(png, density, quality, clip_h=None, trim=True):
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if clip_h and clip_h < im.height:
            im = im.crop((0, 0, im.width, clip_h))
        if density and trim:
            try:
                import numpy as np
                cut = Tool._footer_cut(im)
                if cut and cut > 300:
                    im = im.crop((0, 0, im.width, cut))
                g = np.asarray(im.convert("L"), dtype="int16")
                edges = (np.abs(np.diff(g, axis=1)) > 40).sum(axis=1)
                ys = np.nonzero(edges > 12)[0]                           # drop empty white space at the bottom
                if len(ys):
                    bottom = min(im.height, int(ys[-1]) + 60)
                    if bottom > 300:
                        im = im.crop((0, 0, im.width, bottom))
            except Exception as e:
                logging.debug(f"density crop: {e}")
        ink = 1.0
        try:
            import numpy as np
            g = np.asarray(im.convert("L").resize((200, max(1, int(200 * im.height / max(im.width, 1))))), dtype="int16")
            ink = float((g < 200).mean())                    # share of non-white pixels: ~0 means a blank page
        except Exception:
            pass
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue(), im.width, im.height, ink
