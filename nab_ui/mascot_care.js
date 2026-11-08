/* mascot_care.js — Riko's "care" abilities: tracker watch, pre-save check, colleague mode, end-of-day wrap-up, moods that carry
   over between days, rare surprises, reacting to the screen, where-was-I, shortcut trainer, practice mode. */
(function () {
  "use strict";
  if (!window.RIKO || !window.C) return;
  const RK = RIKO, K = RK.core, ROLE = (window.NAB && NAB.role) || "main", { api } = C;
  let cfg = {}, started = false, hiddenAt = 0, last = { cat: "", page: "" }, mouseUse = {}, said = {}, practice = null, lastCat = "";
  const now = () => Date.now(), pick = (a) => a[Math.floor(Math.random() * a.length)];
  const $ = (s) => document.querySelector(s), pad = (n) => String(n).padStart(2, "0");
  const day = () => { const d = new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); };
  const on = (k) => cfg.mascot_care !== false && cfg[k] !== false;
  const free = (k, ms) => { if (said[k] && now() - said[k] < ms) return false; said[k] = now(); return true; };
  const say = (t, f, ms) => { if (K.on) K.say(t, f || "happy", ms || 6000); };

  // ───────── moods that carry over ─────────
  const M = { get() { try { return JSON.parse(localStorage.getItem("riko.mood") || "{}"); } catch (e) { return {}; } }, set(o) { try { localStorage.setItem("riko.mood", JSON.stringify(o)); } catch (e) { } } };
  function moodStart() {
    const m = M.get(), d = day(); let aff = m.aff == null ? 50 : m.aff, en = m.en == null ? 1 : m.en;
    if (m.day && m.day !== d) { const gap = Math.round((new Date(d) - new Date(m.day)) / 864e5); aff = Math.max(10, aff - Math.max(0, gap - 1) * 6); en = Math.max(en, .8); if (gap >= 3) setTimeout(() => say(pick(["You're back! I missed you.", "Three days?! I was waiting."]), "happy", 7000), 3500); else if (aff > 75) setTimeout(() => say("Good morning! Ready for a great day?", "happy"), 3500); }
    else if (m.day === d) K.energy = en;
    M.set({ aff, en, day: d }); RK.care.aff = aff;
  }
  function moodBump(n) { const m = M.get(); m.aff = Math.max(0, Math.min(100, (m.aff == null ? 50 : m.aff) + n)); m.en = K.energy; m.day = day(); M.set(m); RK.care.aff = m.aff; }

  // ───────── tracker watch ─────────
  async function trackerWatch(force) {
    if (!K.on || ROLE !== "main" || (!force && !on("mascot_trkwatch"))) return;
    const h = new Date().getHours(); if (!force && (h < 14 || !free("trk", 90 * 60000))) return;
    try {
      const l = await api("tracker_load"); if (!l || !l.papers) return;
      const s = await api("tracker_scan", { date: l.today, papers: l.papers }), got = Object.keys(s.matched || {}), miss = l.papers.filter(p => !got.includes(p));
      if (!miss.length) { if (force) say("Every paper is clipped today. Perfect!", "happy"); return; }
      say("Not clipped yet: " + miss.slice(0, 4).join(", ") + (miss.length > 4 ? " +" + (miss.length - 4) + " more" : "") + ".", "think", 9000);
    } catch (e) { }
  }

  // ───────── pre-save check ─────────
  function preSave() {
    if (!on("mascot_presave") || !K.on) return;
    const cat = ($("#dockCatName") || {}).textContent || "", page = (($("#mPage") || {}).value || "").trim(), size = (($("#mS1") || {}).value || "").trim() && (($("#mS2") || {}).value || "").trim();
    const nocat = !cat || cat === (window.t ? t("pick_cat") : "Pick a category");
    if (nocat) return say("Wait, no category is picked.", "surprised", 5000);
    if (!page) return say("Page number is empty. Fix it before saving?", "think", 5000);
    if (!size) return say("Size is empty. Still want to save?", "think", 4500);
    if (page && page === last.page && cat === last.cat && free("samepage", 20000)) say("Same page as the last clip. Intended?", "think", 4500);
  }
  function wirePre() {
    document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest("#saveBtn")) preSave(); }, true);
    document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "s") preSave(); }, true);
    C.on("saved", () => { last = { cat: ($("#dockCatName") || {}).textContent || "", page: (($("#mPage") || {}).value || "").trim() }; moodBump(1); K.energy = Math.max(0, K.energy - .01); });
  }

  // ───────── reacting to what's on screen ─────────
  const CATLINE = [[/sport|খেলা/i, "Sports! Is there a goal?"], [/politic|রাজনীতি/i, "Politics. Deep breath."], [/business|economy|অর্থ/i, "Money news. Check the numbers."], [/entertain|film|বিনোদন/i, "Entertainment, my favourite!"], [/crime|অপরাধ/i, "Crime page. Stay sharp."], [/weather|আবহাওয়া/i, "Weather: umbrella report."]];
  function screenWatch() {
    if (!on("mascot_screen") || !K.on || ROLE !== "main") return;
    const cat = (($("#dockCatName") || {}).textContent || "").trim(); if (!cat || cat === lastCat) return; lastCat = cat;
    const cust = (cfg.mascot_cat_lines || "").split(/\n/).map(l => l.split("=")).filter(a => a.length > 1 && a[0].trim());
    const hit = cust.find(a => cat.toLowerCase().includes(a[0].trim().toLowerCase()));
    if (hit && free("cl" + hit[0], 120000)) return say(hit.slice(1).join("=").trim(), "happy", 4000);
    const b = CATLINE.find(c => c[0].test(cat)); if (b && Math.random() < .5 && free("cl" + b[1], 600000)) say(b[1], "happy", 4000);
  }

  // ───────── rare surprises ─────────
  function surprise() {
    if (!on("mascot_surprise") || !K.on || K.quiet || Math.random() > .012) return;
    const a = pick([() => { K.react("heart_hug", "happy", "Surprise! You're doing great.", 4); }, () => K.confetti && K.confetti(), () => say("Fun fact: some animals use the Earth's magnetic field to hunt. Clippers use Ctrl+V.", "cheeky", 8000), () => K.dance && K.dance(), () => say("I found a pixel! …it was yours.", "cheeky", 5000)]); a();
  }

  // ───────── where was I (resume after a break) ─────────
  function wireResume() {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") { hiddenAt = now(); return; }
      if (!hiddenAt || !on("mascot_resume") || ROLE !== "main") return; const gone = now() - hiddenAt; hiddenAt = 0; if (gone < 15 * 60000) return;
      const cat = (($("#dockCatName") || {}).textContent || "").trim(), page = (($("#mPage") || {}).value || "").trim(), clips = parseInt(($("#stClips") || {}).textContent) || 0;
      setTimeout(() => say("Welcome back! " + (clips ? clips + " clip(s) waiting" : "Nothing pending") + (cat && cat !== (window.t ? t("pick_cat") : "") ? ", last category " + cat : "") + (page ? ", page " + page : "") + ".", "happy", 8000), 500);
    });
  }

  // ───────── shortcut trainer ─────────
  function wireTrainer() {
    document.addEventListener("click", (e) => {
      if (!on("mascot_trainer") || !K.on || !e.isTrusted) return; const b = e.target.closest && e.target.closest(".qc[data-k]"); if (!b) return;
      const k = b.dataset.k; mouseUse[k] = (mouseUse[k] || 0) + 1; if (mouseUse[k] >= 3 && free("tr" + k, 15 * 60000)) say("You can press " + k + " instead of clicking.", "think", 6000);
    }, true);
  }

  // ───────── end of day wrap-up ─────────
  function wrap() {
    const s = (RK.plus && RK.plus.stats) ? RK.plus.stats() : ""; const m = M.get();
    say("That's a wrap! " + s + (m.aff > 70 ? " See you tomorrow, partner." : " Rest well."), "happy", 9000);
  }
  function wireWrap() { C.on("close_request", () => { if (on("mascot_wrap")) wrap(); }); }

  // ───────── practice mode ─────────
  const STEPS = [["Step 1 of 5: paste or capture a clip (Ctrl+V).", () => (parseInt(($("#stClips") || {}).textContent) || 0) > 0], ["Step 2: press a category key (for example Ctrl+1).", () => { const c = (($("#dockCatName") || {}).textContent || ""); return c && c !== (window.t ? t("pick_cat") : "Pick a category"); }], ["Step 3: type the page number, then press Tab.", () => (($("#mPage") || {}).value || "").trim().length > 0], ["Step 4: change the category with Alt+] and see that Page stays.", () => !!practice && practice.cat !== (($("#dockCatName") || {}).textContent || "")], ["Step 5: press Ctrl+S to save.", () => practice && practice.saved]];
  function startPractice() {
    if (ROLE !== "main") return say("Practice mode works in the main window.", "think"); if (practice) return stopPractice();
    practice = { i: 0, saved: false, cat: "", t: setInterval(practiceTick, 800) }; C.on("saved", () => { if (practice) practice.saved = true; }); say("Practice mode on. I'll guide you. Ctrl+K → Practice to stop.", "happy", 5000); setTimeout(() => practiceSay(), 2500);
  }
  function practiceSay() { if (practice) { if (practice.i === 3) practice.cat = (($("#dockCatName") || {}).textContent || ""); say(STEPS[practice.i][0], "happy", 12000); } }
  function practiceTick() {
    if (!practice) return; let ok = false; try { ok = STEPS[practice.i][1](); } catch (e) { }
    if (!ok) return; practice.i++; if (practice.i >= STEPS.length) { stopPractice(); K.react("heart_hug", "happy", "You did it! Practice complete.", 5); if (K.confetti) K.confetti(); return; }
    say("Nice!", "happy", 1500); setTimeout(practiceSay, 1800);
  }
  function stopPractice() { if (practice) { clearInterval(practice.t); practice = null; } }

  // ───────── bootstrap ─────────
  RK.care = { aff: 50, commands: [["Sajeeb: practice mode (guided tour)", startPractice], ["Sajeeb: which papers are not clipped yet?", () => trackerWatch(true)], ["Sajeeb: end of day wrap-up", wrap]], startPractice, trackerWatch, wrap, moodBump };
  function start() {
    if (started || !K.on) return; started = true; moodStart(); wirePre(); wireResume(); wireTrainer(); wireWrap();
    setInterval(() => trackerWatch(false), 5 * 60000); setInterval(screenWatch, 1500); setInterval(surprise, 60000);
    setInterval(() => { const m = M.get(); m.en = K.energy; m.day = day(); M.set(m); }, 120000);
    document.addEventListener("pointerdown", (e) => { const p = K.el && K.el(); if (p && e.target && p.contains(e.target)) moodBump(.3); }, true);
  }
  const prevCfg = RK.hooks.cfg; RK.hooks.cfg = (u) => { cfg = u || {}; if (prevCfg) prevCfg(u); };
  setInterval(start, 2500);
})();
