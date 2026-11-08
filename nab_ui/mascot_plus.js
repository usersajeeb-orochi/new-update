/* mascot_plus.js — Riko's extra abilities: clip carrier, daily counter, smart reminders, deadline nudge, quiet mode, moods,
   special days, outfit unlocks, mini-games, sounds, custom lines, breaks, tips, stats, snack, petting. */
(function () {
  "use strict";
  if (!window.RIKO || !window.C) return;
  const RK = RIKO, HK = RK.hooks, K = RK.core, ROLE = (window.NAB && NAB.role) || "main", { api } = C;
  let cfg = {}, tick = [], games = null, lastTouch = Date.now(), lastSulk = Date.now(), actMin = 0, cur = { x: -1, y: -1, t: 0 }, evts = [], quietAuto = 0, quietMan = 0, nClips = 0, carryId = 0, since = {}, warned = {};
  const now = () => Date.now(), rnd = (a, b) => a + Math.random() * (b - a), pick = (a) => a[Math.floor(Math.random() * a.length)];
  const pad = (n) => String(n).padStart(2, "0"), today = () => { const d = new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); };
  const TIPS = ["Tip: Ctrl+K opens every command.", "Tip: Ctrl+T trims a clip, Ctrl+E pads it.", "Tip: press Ctrl+Alt+N to switch to NAB from anywhere.", "Tip: after choosing a category, Tab moves you from Page to Position.", "Tip: Ctrl+Enter saves with the last Page / Position / Size.", "Tip: C crops to your selection, E erases, R redacts.", "Tip: the suggested crop is applied for you. Ctrl+Z undoes it.", "Tip: minimise NAB and the mini window keeps you saving.", "Tip: Ctrl+H shows your recent saves.", "Tip: hold Shift on the mini window's close button to turn it off.", "Tip: Settings > Paper defaults lets each paper have its own size and trim."];
  const DAYS = { "01-01": ["Happy New Year! New year, new clips.", "star"], "02-14": ["Happy Valentine's Day! Clips are my love language.", "heart"], "02-21": ["Remembering Language Martyrs' Day today.", "none"], "03-26": ["Happy Independence Day!", "confetti"], "04-14": ["Shubho Noboborsho! Happy Pohela Boishakh!", "confetti"], "10-31": ["Boo! Happy Halloween.", "star"], "12-16": ["Happy Victory Day!", "confetti"], "12-25": ["Merry Christmas!", "snow"] };
  const THR = { blue: 0, snow: 50, neon: 150, shadow: 300 };
  const NAMEOF = { blue: "Blue", snow: "Snow", neon: "Neon Cat", shadow: "Shadow Cat" };

  // ───────── stats (kept in this browser profile only) ─────────
  const store = { get() { try { return JSON.parse(localStorage.getItem("riko.stats") || "{}"); } catch (e) { return {}; } }, set(o) { try { localStorage.setItem("riko.stats", JSON.stringify(o)); } catch (e) { } } };
  function stats() { const s = store.get(); s.days = s.days || {}; s.total = s.total || 0; s.best = s.best || 0; s.games = s.games || {}; return s; }
  function streakOf(s) { let n = 0; const d = new Date(); if (!(s.days[today()] > 0)) d.setDate(d.getDate() - 1); for (let i = 0; i < 400; i++) { const k = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); if (s.days[k] > 0) { n++; d.setDate(d.getDate() - 1); } else break; } return n; }
  function addSaved(n) {
    const s = stats(), d = today(), before = s.total; s.days[d] = (s.days[d] || 0) + n; s.total += n; const keys = Object.keys(s.days).sort(); while (keys.length > 120) delete s.days[keys.shift()];
    s.best = Math.max(s.best, s.days[d]); store.set(s); return { s, before };
  }
  const statsText = () => { const s = stats(), n = s.days[today()] || 0; return "Today " + n + " clip" + (n === 1 ? "" : "s") + " · streak " + streakOf(s) + " day" + (streakOf(s) === 1 ? "" : "s") + " · total " + s.total; };
  const skinOk = (id) => !cfg.mascot_unlock || stats().total >= (THR[id] || 0);
  HK.skinOk = skinOk;

  // ───────── sounds (tiny synthesised beeps, off by default) ─────────
  let ac = null;
  function tone(f, f2, dur, type, vol, delay) {
    if (!cfg.mascot_sound) return; try {
      ac = ac || new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === "suspended") ac.resume();
      const o = ac.createOscillator(), g = ac.createGain(), t0 = ac.currentTime + (delay || 0), v = (cfg.mascot_vol == null ? 30 : cfg.mascot_vol) / 100 * (vol || 1) * .25;
      o.type = type || "sine"; o.frequency.setValueAtTime(f, t0); if (f2) o.frequency.exponentialRampToValueAtTime(f2, t0 + dur); g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(v, t0 + .02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      o.connect(g); g.connect(ac.destination); o.start(t0); o.stop(t0 + dur + .05);
    } catch (e) { }
  }
  const SND = { success: () => { tone(660, 0, .12, "triangle"); tone(880, 0, .12, "triangle", 1, .1); tone(1320, 0, .2, "triangle", 1, .2); }, error: () => { tone(220, 110, .35, "sawtooth", .8); }, warn: () => { tone(520, 0, .1, "square", .6); tone(520, 0, .1, "square", .6, .15); }, paste: () => tone(400, 800, .09, "sine"), cat: () => tone(700, 0, .06, "sine"), click: () => tone(500, 1200, .12, "sine"), pop: () => tone(300, 900, .07, "sine"), cheer: () => { [523, 659, 784, 1046].forEach((f, i) => tone(f, 0, .14, "triangle", 1, i * .09)); } };
  const snd = (k) => { if (SND[k]) SND[k](); };
  HK.onEvent = (kind) => { snd(kind); lastTouch = now(); };

  // ───────── DOM bits: carrier, badge, hud ─────────
  let carry, badge, hud, css;
  function dom() {
    if (carry || !K.layer()) return; const L = K.layer();
    css = document.createElement("style");
    css.textContent = `#rkCarry{position:absolute;left:0;top:0;width:34px;height:34px;border-radius:7px;border:2px solid #fff;object-fit:cover;box-shadow:0 3px 10px #0007;pointer-events:none;display:none;background:#fff}
#rkBadge{position:absolute;left:0;top:0;padding:2px 9px;border-radius:999px;font:700 11px/1.5 system-ui,sans-serif;color:#fff;background:#141629d9;border:1px solid #ffffff30;pointer-events:none;white-space:nowrap;display:none;overflow:hidden}
#rkBadge i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,#5b8cffaa,#8b6cffaa);z-index:-1}
#rkHud{position:fixed;bottom:84px;left:50%;transform:translateX(-50%);z-index:70;background:#141629f2;color:#fff;border:1px solid #ffffff40;border-radius:999px;padding:6px 16px;font:700 13px system-ui,sans-serif;display:none;pointer-events:none}
.rkItem{position:fixed;z-index:65;width:38px;height:38px;border-radius:50%;background:#fff;color:#334;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px #0006;cursor:pointer;pointer-events:auto}
.rkItem .ic{width:22px;height:22px}
.rkSpark{position:fixed;z-index:70;pointer-events:none;font:700 18px system-ui;color:#f5a623}`;
    document.head.appendChild(css);
    carry = document.createElement("img"); carry.id = "rkCarry"; carry.alt = ""; L.appendChild(carry);
    badge = document.createElement("div"); badge.id = "rkBadge"; L.appendChild(badge);
    hud = document.createElement("div"); hud.id = "rkHud"; document.body.appendChild(hud);
  }
  HK.onFrame = (f) => {
    if (!carry) { dom(); return; }
    if (carry.style.display === "block") carry.style.transform = `translate(${Math.round(f.x + (f.flip ? -1 : 1) * f.w * .3 - 17)}px,${Math.round(f.y - f.h * .44 - f.bob - 17)}px) rotate(${f.flip ? 8 : -8}deg)`;
    if (badge.style.display === "block") { const w = badge.offsetWidth; badge.style.transform = `translate(${Math.round(f.x - w / 2)}px,${Math.round(f.y + 3)}px)`; }
  };
  function refreshBadge() {
    if (!badge) return; const s = stats(), n = s.days[today()] || 0, goal = +cfg.mascot_goal || 0;
    if (cfg.mascot_badge === false || (n === 0 && !goal)) { badge.style.display = "none"; return; }
    badge.innerHTML = (goal ? `<i style="width:${Math.min(100, n / goal * 100)}%"></i>` : "") + "Today " + n + (goal ? " / " + goal : "") + (streakOf(s) > 1 ? " · " + streakOf(s) + "d" : ""); badge.style.display = "block";
  }
  const spark = (x, y, n) => { for (let i = 0; i < (n || 6); i++) { const e = document.createElement("span"); e.className = "rkSpark"; e.textContent = "✦"; e.style.left = x + "px"; e.style.top = y + "px"; document.body.appendChild(e); const a = rnd(0, 6.28), d = rnd(24, 56); const an = e.animate([{ transform: "translate(0,0) scale(.6)", opacity: 1 }, { transform: `translate(${Math.cos(a) * d}px,${Math.sin(a) * d}px) scale(1.2)`, opacity: 0 }], { duration: 650, easing: "ease-out" }); an.onfinish = () => e.remove(); } };

  // ───────── clip carrier ─────────
  async function showCarry() {
    if (cfg.mascot_carry === false || !carry) return;
    try { const r = await api("layers"), l = (r.layers || []).slice(-1)[0]; if (!l) { carry.style.display = "none"; return; } if (l.id !== carryId) { carryId = l.id; carry.src = C.url("/lthumb?id=" + l.id + "&w=72&r=" + r.rev); } carry.style.display = "block"; } catch (e) { }
  }
  function deliver() {
    if (!carry || carry.style.display !== "block") return; const FOCUS = ROLE === "main" ? "#saveBtn" : "#ovQ", el = document.querySelector(FOCUS); carry.style.display = "none";
    if (!el) return; const r = el.getBoundingClientRect(), c = carry.getBoundingClientRect(), ghost = carry.cloneNode(); ghost.style.cssText = `position:fixed;left:0;top:0;width:34px;height:34px;border-radius:7px;border:2px solid #fff;z-index:70;pointer-events:none;display:block`;
    document.body.appendChild(ghost); const a = ghost.animate([{ transform: `translate(${c.left}px,${c.top}px) scale(1)`, opacity: 1 }, { transform: `translate(${r.left + r.width / 2 - 17}px,${r.top + r.height / 2 - 17}px) scale(.3)`, opacity: .2 }], { duration: 600, easing: "cubic-bezier(.5,0,.8,.4)" });
    a.onfinish = () => { ghost.remove(); spark(r.left + r.width / 2, r.top + r.height / 2, 7); snd("pop"); };
  }

  // ───────── events from NAB ─────────
  function milestone(n, before) {
    const goal = +cfg.mascot_goal || 0, total = before.total;
    if (goal && n === goal) { K.say("Daily goal reached! " + n + " clips. Legend.", "excited", 7000); K.dance(7, null); K.confetti(); snd("cheer"); return; }
    if ([10, 25, 50, 100, 150, 200, 300].includes(n)) { K.say(n + " clips today! Absolute machine.", "excited", 6500); setTimeout(() => { K.dance(6, null); K.confetti(); snd("cheer"); }, 900); }
    if (cfg.mascot_unlock) for (const id in THR) if (total < THR[id] && stats().total >= THR[id]) setTimeout(() => { K.say("New outfit unlocked: " + NAMEOF[id] + "!", "excited", 7000); K.confetti(); snd("cheer"); }, 2200);
  }
  function wireEvents() {
    C.on("clips", (d) => { const n = d.n || 0; if (n > nClips) { evts.push(now()); showCarry(); } else if (n === 0) { if (carry) carry.style.display = "none"; } nClips = n; if (n > 0) showCarry(); });
    C.on("saved", (ev) => { const n = Math.max(1, (ev && ev.n) || 1); evts.push(now()); const r = addSaved(n); deliver(); refreshBadge(); milestone(r.s.days[today()], { total: r.before }); warned = {}; since = {}; });
    C.on("save_failed", () => { if (carry) carry.style.display = "none"; });
  }

  // ───────── smart reminders ─────────
  const $ = (s) => document.querySelector(s);
  function remindTick() {
    if (!K.on || cfg.mascot_remind === false || document.visibilityState === "hidden") return;
    let clips, armed, page;
    if (ROLE === "main") { clips = parseInt(($("#stClips") || {}).textContent) || 0; armed = ($("#dockCatName") || {}).textContent !== (window.t ? t("pick_cat") : "Pick a category"); page = (($("#mPage") || {}).value || "").trim(); }
    else { clips = nClips; const c = (($("#ovCat") || {}).textContent || "").trim(); armed = c && c !== "—"; page = (($("#oPage") || {}).value || "").trim(); }
    if (!clips) { since = {}; return; }
    const key1 = "cat" + clips, key2 = "page" + clips + armed; since[key1] = since[key1] || now(); since[key2] = since[key2] || now();
    if (!armed && now() - since[key1] > 25000 && !warned[key1]) { warned[key1] = 1; K.react("point", "surprised", "Pick a category for this clip!", 3.5); snd("warn"); }
    else if (armed && !page && now() - since[key2] > 12000 && !warned[key2]) { warned[key2] = 1; K.react("point", "wink", "Page number? Tab to the Page box.", 3.5); snd("warn"); }
  }

  // ───────── deadline nudge ─────────
  async function deadlineTick() {
    const dl = (cfg.mascot_deadline || "").trim(); if (!/^\d{1,2}:\d{2}$/.test(dl) || ROLE !== "main") return; const [h, m] = dl.split(":").map(Number), d = new Date(), mins = d.getHours() * 60 + d.getMinutes();
    let st = {}; try { st = JSON.parse(localStorage.getItem("riko.dl") || "{}"); } catch (e) { } if (st.day !== today()) st = { day: today(), n: 0, t: 0 };
    if (mins < h * 60 + m || st.n >= 2 || (st.n === 1 && now() - st.t < 30 * 60000)) return;
    try { const r = await api("tracker_day", { date: today() }), s = (r.entry || {}).status; if (s === "submitted" || s === "off_day") { st.n = 9; } else { st.n++; st.t = now(); K.react("panic", "surprised", "It's " + dl + ". Tracker not submitted yet!", 6); K.say("It's " + dl + ". Tracker not submitted yet!", "surprised", 9000); snd("warn"); } localStorage.setItem("riko.dl", JSON.stringify(st)); } catch (e) { }
  }

  // ───────── quiet mode, moods, break, tips, special days ─────────
  function quietTick() {
    const t = now(); evts = evts.filter(x => t - x < 120000);
    if (cfg.mascot_quiet !== false && evts.length >= 5 && !quietAuto) { quietAuto = t + 4 * 60000; K.setQuiet(true); }
    const off = (quietAuto && t > quietAuto) && (!quietMan || t > quietMan); if (off) { quietAuto = 0; quietMan = 0; K.setQuiet(false); }
    else if (quietMan && t > quietMan && !quietAuto) { quietMan = 0; K.setQuiet(false); }
  }
  let lastYawn = 0;
  function moodTick() {
    const d = new Date(), h = d.getHours(), t = now(); if (!K.on) return;
    if (h >= 23 || h < 5) { K.energy = Math.min(K.energy, .5); if (t - lastYawn > 25 * 60000 && !K.quiet) { lastYawn = t; K.say(pick(["So sleepy… maybe call it a night?", "Yaaawn. It's late, boss.", "Even fast clippers need sleep. Wrap up soon?"]), "sleepy", 6000); } }
    else if (h >= 5 && h < 11) K.energy = Math.max(K.energy, .7);
    if (t - lastTouch > 2 * 3600000 && t - lastSulk > 2 * 3600000 && !K.quiet) { lastSulk = t; K.react("sad", "sad", pick(["Hello? I'm here too, you know.", "Nobody says hi to me anymore…", "Two hours and not even a boop?"]), 5); }
    if (t - cur.t < 120000) actMin += 1 / 1; else actMin = actMin;
    const b = +cfg.mascot_break || 0; if (b > 0 && actMin >= b) { actMin = 0; K.react("tea", "happy", "Break time! Stretch and drink some water.", 7); K.say("Break time! Stretch and drink some water.", "happy", 9000); snd("pop"); }
  }
  function tipTick() { if (cfg.mascot_tips === false || !K.on || K.quiet || Math.random() > .35) return; K.say(pick(TIPS), "wink", 7000); }
  function specialDay() {
    if (!K.on) return; const d = new Date(), key = pad(d.getMonth() + 1) + "-" + pad(d.getDate()); let seen = ""; try { seen = localStorage.getItem("riko.sday") || ""; } catch (e) { } if (seen === today()) return;
    let m = DAYS[key]; (cfg.mascot_days || "").split(/\n/).forEach(l => { const mm = l.trim().match(/^(\d{1,2})-(\d{1,2})\s+(.+)$/); if (mm && pad(+mm[1]) + "-" + pad(+mm[2]) === key) m = [mm[3], "confetti"]; });
    const h = d.getHours(), nm = (cfg.mascot_name || "").trim(), g = (h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening") + (nm ? ", " + nm : "") + "!";
    try { localStorage.setItem("riko.sday", today()); } catch (e) { }
    setTimeout(() => { if (!K.on) return; if (m) { K.say(m[0], "excited", 8000); const kind = m[1]; if (kind === "confetti") K.confetti(); else for (let i = 0; i < 12; i++) setTimeout(() => K.fx(kind === "snow" ? "❄" : kind === "heart" ? "♥" : "✦", kind === "heart" ? "#f27ba3" : kind === "snow" ? "#9cc9ff" : "#f5a623", rnd(-80, 80), rnd(-110, -30), 20), i * 140); } else K.say(g, "happy", 5000); }, 3500);
  }

  // ───────── mini-games ─────────
  const hudSet = (t) => { if (hud) { hud.textContent = t; hud.style.display = t ? "block" : "none"; } };
  function endGame(msg) {
    if (!games) return; clearInterval(games.iv); (games.items || []).forEach(e => e.remove()); K.setSpeed(1); const g = games; games = null; hudSet(""); const s = stats(), best = s.games[g.type] || 0; if (g.score > best) { s.games[g.type] = g.score; store.set(s); }
    K.say((msg || "Time!") + " Score " + g.score + (g.score > best ? " — new best!" : " (best " + best + ")"), g.score > best ? "excited" : "happy", 7000); if (g.score > best) { K.confetti(); snd("cheer"); }
  }
  function playCatch() {
    if (games || !K.on) return; games = { type: "catch", score: 0, end: now() + 20000 }; K.setSpeed(2.2); K.say("Catch me if you can!", "cheeky", 2500); hudSet("Catch me! 20s · 0");
    games.iv = setInterval(() => { const left = Math.max(0, Math.ceil((games.end - now()) / 1000)); hudSet("Catch me! " + left + "s · " + games.score); if (left <= 0) return endGame("Time's up!"); const p = K.pos; if (K.state() !== "fall" && K.state() !== "drag" && (Math.hypot(cur.x - p.x, cur.y - p.y) < 260 || Math.random() < .3)) K.fleeFrom(cur.x < 0 ? p.x : cur.x, cur.y < 0 ? p.y : cur.y); }, 700);
  }
  function playRain() {
    if (games) return; games = { type: "rain", score: 0, end: now() + 22000, items: [] }; K.say("Clip rain! Catch them!", "excited", 2500);
    games.iv = setInterval(() => {
      const left = Math.max(0, Math.ceil((games.end - now()) / 1000)); hudSet("Clip rain! " + left + "s · " + games.score); if (left <= 0) return endGame("That's the rain!");
      if (left < 4) return; const e = document.createElement("div"); e.className = "rkItem"; e.innerHTML = window.ICONS ? ICONS.svg("news") : "N"; e.style.left = rnd(20, innerWidth - 60) + "px"; e.style.top = "-50px"; document.body.appendChild(e); games.items.push(e);
      const an = e.animate([{ transform: "translateY(0) rotate(0)" }, { transform: `translateY(${innerHeight + 80}px) rotate(${rnd(-90, 90)}deg)` }], { duration: rnd(3800, 6200), easing: "linear" }); an.onfinish = () => e.remove();
      e.onpointerdown = (ev) => { ev.stopPropagation(); if (!games) return; games.score++; const r = e.getBoundingClientRect(); spark(r.left + 19, r.top + 19, 5); snd("pop"); e.remove(); };
    }, 750);
  }
  const prevHit = HK.onHit;
  HK.onHit = () => {
    lastTouch = now(); snd("click");
    if (games && games.type === "catch") { games.score++; K.say(pick(["Gotcha!", "Ow! Nice one.", "Too slow! …oh.", "Okay, that was fast."]), "cheeky", 1200); }
    else if (!games && Math.random() < .18) setTimeout(() => K.say(statsText(), "happy", 6000), 60);
  };

  // ───────── commands and petting ─────────
  function snack() { K.energy = 1; K.react("tea", "happy", pick(["Snack! Nom nom nom.", "Bubble tea?! You're the best.", "Fuel acquired."]), 3.6); for (let i = 0; i < 3; i++) K.fx("♥", "#f27ba3", rnd(-40, 40), -80, 20); snd("pop"); }
  function hideFor(min) { RK.setEnabled(false); setTimeout(() => RK.apply(), min * 60000); }
  function quietFor(min) { quietMan = now() + min * 60000; K.setQuiet(true); }
  let hoverT = 0, bound = false;
  function bindPet() {
    if (bound) return; const p = K.el(); if (!p) return; bound = true;
    p.addEventListener("pointerenter", () => { clearTimeout(hoverT); hoverT = setTimeout(() => { if (K.state() === "idle" || K.state() === "walk") { K.react("heart_hug", "embarrassed", pick(["Purr purr…", "Okay, that's nice.", "Head pats accepted."]), 3); for (let i = 0; i < 3; i++) K.fx("♥", "#f27ba3", rnd(-40, 40), -80, 20); lastTouch = now(); } }, 1500); });
    p.addEventListener("pointerleave", () => clearTimeout(hoverT));
  }
  const COMMANDS = [["Sajeeb: show my stats", () => K.say(statsText(), "happy", 7000)], ["Sajeeb: give snack", snack], ["Sajeeb: play Catch me", playCatch], ["Sajeeb: play Clip rain", playRain], ["Sajeeb: quiet for 30 minutes", () => quietFor(30)], ["Sajeeb: hide for 10 minutes", () => hideFor(10)], ["Sajeeb: tell me a tip", () => K.say(pick(TIPS), "wink", 7000)]];

  // ───────── config + timers ─────────
  HK.cfg = (u) => {
    cfg = u || {}; K.setChat(cfg.mascot_chat == null ? 1 : cfg.mascot_chat); K.setLang(cfg.mascot_lang || "en");
    K.setExtra((cfg.mascot_lines || "").split(/\n/).map(x => x.trim()).filter(Boolean)); refreshBadge();
    if (!tick.length && K.on) startTimers();
  };
  function startTimers() {
    tick.push(setInterval(remindTick, 3000), setInterval(quietTick, 5000), setInterval(moodTick, 60000), setInterval(deadlineTick, 30000), setInterval(tipTick, 420000), setInterval(() => { bindPet(); refreshBadge(); }, 2500));
    setTimeout(specialDay, 1500); dom(); wireOnce();
  }
  let wired = false; const wireOnce = () => { if (!wired) { wired = true; wireEvents(); } };
  document.addEventListener("pointermove", (e) => { cur = { x: e.clientX, y: e.clientY, t: now() }; }, { passive: true });
  document.addEventListener("pointerdown", () => { if (ac && ac.state === "suspended") ac.resume(); }, { passive: true });
  RK.plus = { commands: COMMANDS, stats: statsText, total: () => stats().total, skinOk, thresholds: THR, names: NAMEOF, snack, playCatch, playRain, quietFor, hideFor };
  setTimeout(() => { if (K.on && !tick.length) startTimers(); }, 4000);
  setInterval(() => { if (K.on && !tick.length) startTimers(); }, 5000);
})();
