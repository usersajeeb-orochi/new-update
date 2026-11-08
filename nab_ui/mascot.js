/* Riko — NAB mascot. Lives in whichever NAB window is visible (main or mini window).
   Never blocks clicks: the layer ignores the mouse, only Riko herself is clickable. */
(function () {
  "use strict";
  const ROLE = (window.NAB && NAB.role) || "main", BASE = "/s/mascot/";
  const ALIAS = { react_surprised: "surprised", react_happy: "happy", react_angry: "angry", tap: "laptop", lie: "lounge" };
  const slotOf = (n) => ALIAS[n] || n;
  const MOODS = { happy: ["#fff1f5", "#f27ba3"], excited: ["#fff6e6", "#f5a623"], wink: ["#fff1f5", "#f27ba3"], cheeky: ["#f6eeff", "#a77bf2"], angry: ["#ffecec", "#e0392b"], sad: ["#eaf4ff", "#5b9be0"], surprised: ["#eaf9ff", "#4fb6e0"], sleepy: ["#eeebff", "#7b72d9"], embarrassed: ["#ffeff0", "#f0788a"] };
  const L = {
    click: [["tap", "excited", ["Yes? You rang?", "Boop received. Processing… ok done.", "I'm not saying I'm the best intern, but…"]],
    ["react_surprised", "surprised", ["Bro. Personal space.", "Eep! Warn a guy first!", "Who touched me?!"]],
    ["heart_hug", "embarrassed", ["Aww, a boop! Take my heart ♥", "Okay fine, you can stay."]],
    ["react", "happy", ["Gaming break? …No? Fine.", "Pause. Controller down."]],
    ["react_happy", "happy", ["Stonks (that's you)", "Certified clip-slayer.", "You're cooking. Chef's kiss."]],
    ["react_angry", "angry", ["Not the hair. NOT. THE. HAIR.", "I will remember this.", "This is fine. (It is not fine.)"]]],
    tickle: ["Stop it I'm ticklish!", "HAHA okay okay you win!"],
    paste: ["Ooh, fresh clip. Mine now.", "Clip acquired. Nice.", "That's a lot of newspaper, boss."],
    paste2: ["Another one?! Hungry today.", "Clips stacking up like my snack pile.", "Chop chop, we're on a roll."],
    cat: ["Big brain pick.", "Ooh, that folder? Bold.", "Categories assigned. Very organised, much wow."],
    ok: ["Saved. Easy money.", "Another one for the archive 📰", "Yeet! Into the folder it goes."],
    fail: ["Oh no. Oh NO. It's not saving.", "This is fine… (it's on fire)", "Bruh. The save failed."],
    miss: ["Psst. You forgot to save that clip!", "Clip's just sitting there… waiting…", "Unsaved clip alert"],
    work: ["Uploading… go touch grass.", "Beep boop, working on it."],
    nap: ["Zzz… wake me when there's news.", "Nap time. Don't touch my chair."],
    wake: ["I'm up! I'm up! I wasn't sleeping.", "Mmm… did you miss me?"],
    hop: ["Plot twist: I live here now.", "Yoink! New window, who dis?", "Back at the big screen. Miss me?"],
    outfit: ["Outfit check! Better?", "Brb, changing. Don't look!", "New skin, who dis?", "Drip upgrade complete."],
    hi: ["Hi! Riko on duty", "Ready to clip. Are you?"],
    chat: [["happy", "Drink some water. Doctor's orders."], ["wink", "Psst… I'm right here."], ["cheeky", "Bet you can't catch me!"], ["excited", "What's next? I'm ready!"], ["embarrassed", "Don't stare…"]]
  };
  const LB = {
    ok: ["সেভ হয়ে গেছে! দারুণ!", "আরেকটা ক্লিপ আর্কাইভে!", "ইয়াহু! ফোল্ডারে ঢুকে গেল।"],
    fail: ["ইশ! সেভ হলো না!", "আরে ভাই, সেভ ফেইল করেছে!", "সব ঠিক আছে… (আসলে নেই)"],
    miss: ["ওই যে, ক্লিপটা সেভ করোনি!", "ক্লিপ বসে বসে অপেক্ষা করছে…", "আনসেভড ক্লিপ অ্যালার্ট!"],
    work: ["আপলোড চলছে… একটু অপেক্ষা।", "বিপ বুপ, কাজ চলছে।"],
    paste: ["নতুন ক্লিপ! এটা এখন আমার।", "ক্লিপ পেয়ে গেছি, দারুণ!", "অনেক কাগজ আজ, বস!"],
    paste2: ["আবার একটা? আজ খুব খিদে!", "ক্লিপের পাহাড় জমছে…", "চলো চলো, জোরে চালাও!"],
    cat: ["দারুণ বাছাই!", "ওই ফোল্ডার? সাহসী পছন্দ!", "ক্যাটাগরি ঠিক, দারুণ গোছানো!"],
    wake: ["উঠে গেছি! ঘুমাইনি তো!", "উম… আমাকে মিস করেছিলে?"],
    nap: ["জ্জ্জ… খবর এলে ডেকো।", "ঘুমের সময়, ডিস্টার্ব কোরো না।"],
    hop: ["সারপ্রাইজ: এখন এখানেই থাকি!", "নতুন জানালা, কেমন আছো?"],
    hi: ["হাই! রিকো ডিউটিতে!", "ক্লিপ করতে রেডি তো?"],
    outfit: ["নতুন সাজ! কেমন লাগছে?", "একটু অপেক্ষা, সাজছি, তাকিও না!"],
    tickle: ["থামো! সুড়সুড়ি লাগে!", "হা হা ঠিক আছে, তুমি জিতলে!"]
  };
  const DEFAULT_SKIN = "sajeeb";
  const vis_ = (i) => !!R.skins && !!R.skins[i] && (R.skins[i].who || "sajeeb") === R.who;     // which skins belong to the chosen character
  const HK = { onFrame: null, onEvent: null, skinOk: null, onHit: null };     // hooks used by mascot_plus.js
  let NAME = "Sajeeb", TAG = true, lang = "en", extra = [], quiet = false, crit = false, chatLevel = 1;
  const ln = (key) => { const en = L[key] || [""], bn = LB[key]; let a = en; if (bn && (lang === "bn" || (lang === "mix" && Math.random() < .5))) a = bn; if (extra.length && (key === "ok" || key === "hi" || key === "wake") && Math.random() < .35) a = extra; return pick(a); };
  const R = { who: "sajeeb", on: false, ready: false, size: 150, sp: {}, el: null, skin: null, skinId: "", skins: null, mode: "auto" };
  const now = () => performance.now() / 1000, rnd = (a, b) => a + Math.random() * (b - a), pick = a => a[Math.floor(Math.random() * a.length)];
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const slow = () => document.body.classList.contains("slow") || (window.matchMedia && matchMedia("(prefers-reduced-motion:reduce)").matches);
  let nameEl, layer, pet, sh, bub, bi, bt_, raf = 0;
  let W = 0, H = 0, gy = 0, x = 0, y = -80, vx = 0, vy = 0, st = "fall", sp = "react_surprised", flip = false, ang = 0, face = 1, until = 0, t = 0, last = 0;
  let clicks = [], hist = [], dragging = false, down = null, grab = { x: 0, y: 0 }, dvx = 0, act = 0, bubT = 0, sT = 0, fxT = 0, nClips = 0, nSaved = 0, G = 2600, loaded = 0;

  // ───────── world: what she can stand on, and where she must never go ─────────
  const SEL = {
    main: ".rb,.icon-btn,.panel,.card,.btn,.cat-root,.cat-sub,.qc,.tk-card,.pill,.kv,.suggest,#statusBar,.tabs,.toolbar,.stage-wrap,.tb,.sk,.mf,.row,.layers,.panel-h,.qchips,.header-prev,.tag",
    overlay: ".ov-h,.ov-th,.ov-cat,.ov-q button,.ov-s"
  };
  const ZONE = ROLE === "main" ? ["#dock"] : [".ov-m"];       // the metadata strip: Page / Position / Size / Save
  const FOCUS = ROLE === "main"
    ? { paste: ".tb", cat: "#catTree", ok: "#saveBtn", error: "#saveBtn", warn: "#saveBtn", busy: "#stStatus" }
    : { paste: "#ovImg", cat: "#ovCat", ok: "#ovQ", error: "#ovQ", warn: "#ovQ", busy: "#ovS" };
  let idleSp = "sit", plats = [], zones = [], worldT = -9, cur = null, path = [], goal = null, wx = 0, wThen = null, wStart = 0;
  let energy = 1, cursor = { x: -1, y: -1, t: -99 }, visited = {}, pendingGo = null, cx0 = 0, cty = 0, jumping = false, jTarget = null, dropping = false;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 ? r : null; };

  function refreshWorld(force) {
    const nw = now(); if (!force && nw - worldT < .7) return; worldT = nw; measure0();
    const out = [{ x1: 0, x2: W, y: gy, g: 1 }];
    const sit0 = R.sp.sit, minY = sit0 && sit0.naturalHeight ? sit0.naturalHeight * k() * .44 + 8 : 70;
    const seen = new Set(), els = document.querySelectorAll(SEL[ROLE]);
    for (let i = 0; i < els.length && out.length < 130; i++) {
      const e = els[i]; if (layer && layer.contains(e)) continue;
      const r = vis(e); if (!r || r.width < 48 || r.height < 14 || r.top < minY || r.top > gy - 24 || r.left > W || r.right < 0) continue;
      if (zones.some(z => r.left < z.x2 && r.right > z.x1 && r.top > z.y1 - 4)) continue;
      const k = Math.round(r.top / 4) + ":" + Math.round(r.left / 16); if (seen.has(k)) continue; seen.add(k);
      out.push({ x1: Math.max(0, r.left), x2: Math.min(W, r.right), y: Math.round(r.top) });
    }
    if (ROLE === "main") { const hd = document.querySelector("header.top"); if (hd) { const r = vis(hd); if (r && r.bottom >= minY) out.push({ x1: 0, x2: W, y: Math.round(r.bottom) }); } }
    if (ROLE === "main") {          // the big page area is empty most of the time: give it a few ledges so she can roam the middle too
      const sw = document.querySelector(".stage-wrap"), r = sw && vis(sw);
      if (r) for (const f of [0, .34, .67]) { const yy = Math.round(r.top + 49 + (r.height - 49) * f); if (yy >= minY && yy < gy - 24) out.push({ x1: r.left + 10, x2: r.right - 10, y: yy }); }
    }
    plats = out;
  }
  function measure0() {
    W = innerWidth; H = innerHeight; zones = []; gy = H - (ROLE === "main" ? 34 : 2);
    for (const s of ZONE) { const e = document.querySelector(s); if (e && e.offsetParent !== null || (e && getComputedStyle(e).position === "fixed")) { const r = e.getBoundingClientRect(); if (r.height > 0 && r.top > H * .3) { zones.push({ x1: r.left, x2: r.right, y1: r.top }); gy = Math.min(gy, r.top + 1); } } }
  }
  const measure = measure0;
  const platAt = (px, py, tol) => { let b = null; for (const p of plats) if (px >= p.x1 && px <= p.x2 && Math.abs(p.y - py) <= (tol || 5) && (!b || Math.abs(p.y - py) < Math.abs(b.y - py))) b = p; return b; };
  const IDLES = () => { const sl = R.skin ? R.skin.slots : {}; const w = { sit: 5, phone: 2, laptop: 2, tea: 1, paws: 1, wink: 1, sitbox: 1, umbrella: .4, thinking: 1, react: .6 }, a = [];
    Object.keys(w).forEach(n => { if (sl[n] && !(sl[n].bust && n !== "thinking" && R.skinId !== "blue")) for (let i = 0; i < Math.ceil(w[n] * 2); i++) a.push(n); }); return a; };
  const landSp = () => (R.skin && R.skin.slots.jump && R.skin.slots.jump.anim === "phase") ? "jump" : "sit";
  let trav = 0;                                                  // distance walked / climbed: drives the step frames so feet do not slide
  function jumpFrame(n) {
    const sa = now() - sT; if (st === "land") return Math.min(n - 1, sa < .12 ? n - 2 : n - 1);
    if (st === "drag") return Math.min(n - 1, 4);
    if (sa < .08 && jumping) return 1;
    return vy < -260 ? 2 : vy < 60 ? 3 : Math.min(n - 3 > 0 ? 4 : n - 1, 4);
  }
  function fslot() {                                              // slot name of the picture to show right now (multi-frame poses pick a frame)
    const base = slotOf(sp), s0 = R.skin && R.skin.slots[base]; if (!s0 || !s0.frames) return base; const n = s0.frames.length; let i = 0;
    if (s0.anim === "dist") i = Math.floor(trav / Math.max(4, R.size * (s0.stride || .12))) % n;
    else if (s0.anim === "phase") i = jumpFrame(n);
    else i = Math.floor(now() * (s0.fps || 8)) % n;
    return base + "#" + i;
  }
  const jumpH = () => R.size * .85, reach = () => R.size * 1.1;

  // ───────── path planning over the platforms (walk / jump / climb / drop) ─────────
  function edges(i) {
    const a = plats[i], res = [], J = jumpH(), Rg = reach();
    for (let j = 0; j < plats.length; j++) {
      if (j === i) continue; const b = plats[j], up = a.y - b.y, gap = Math.max(0, b.x1 - a.x2, a.x1 - b.x2), ov = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
      const bc = (b.x1 + b.x2) / 2;
      if (up >= -4 && up <= J && gap <= Rg) {                       // jump (up or across)
        const lx = clamp(bc, a.x1 + 10, a.x2 - 10), tx = clamp(lx, b.x1 + 12, b.x2 - 12);
        res.push({ j, c: 3 + gap / 200, st: [{ t: "walk", x: lx }, { t: "jump", tx, ty: b.y }] });
      } else if (up > J && up <= R.size * 5 && ov >= 24) {          // climb the side of the element
        const lx = clamp(bc, Math.max(a.x1, b.x1) + 10, Math.min(a.x2, b.x2) - 10);
        res.push({ j, c: 5 + up / 120, st: [{ t: "walk", x: lx }, { t: "climb", x: lx, ty: b.y }] });
      } else if (up < -4) {                                         // step off the edge and drop
        for (const ex of [a.x1 - 6, a.x2 + 6]) if (ex >= b.x1 + 6 && ex <= b.x2 - 6) { res.push({ j, c: 1 + (-up) / 500, st: [{ t: "walk", x: ex < (a.x1 + a.x2) / 2 ? a.x1 + 6 : a.x2 - 6, then: "drop", dir: ex < (a.x1 + a.x2) / 2 ? -1 : 1 }] }); break; }
      }
    }
    return res;
  }
  function dijkstra(s) {
    const n = plats.length, d = new Array(n).fill(1e9), prev = new Array(n).fill(null), done = new Array(n).fill(false); d[s] = 0;
    for (let k = 0; k < n; k++) {
      let u = -1; for (let i = 0; i < n; i++) if (!done[i] && (u < 0 || d[i] < d[u])) u = i; if (u < 0 || d[u] >= 1e9) break; done[u] = true;
      for (const e of edges(u)) { const nd = d[u] + e.c; if (nd < d[e.j]) { d[e.j] = nd; prev[e.j] = { from: u, st: e.st }; } }
    }
    return { d, prev };
  }
  const stepsTo = (map, j) => { const out = []; while (map.prev[j]) { out.unshift(...map.prev[j].st); j = map.prev[j].from; } return out; };
  function myPlat() { const p = platAt(x, y, 6); return p ? plats.indexOf(p) : -1; }

  // ───────── a small utility AI: she scores what she could do and picks, instead of rolling dice ─────────
  function decide() {
    refreshWorld(true); const me = myPlat(); const nw = now();
    if (me < 0) { fall(0, 0); return; }
    if (pendingGo) {                                                // something just happened in NAB → go and look at it
      const el = document.querySelector(pendingGo.sel); pendingGo = null;
      if (el) { const r = vis(el); if (r) { const j = nearestPlat(r.left + r.width / 2, r.top); if (j >= 0) return goTo(j, { x: clamp(r.left + r.width / 2, 20, W - 20), look: "event" }); } }
    }
    const map = dijkstra(me), cands = [];
    const act_ = nw - act, curA = nw - cursor.t < 6 && cursor.x >= 0;
    for (let j = 0; j < plats.length; j++) {
      if (map.d[j] >= 1e9 || j === me) continue; const p = plats[j], key = Math.round(p.y / 40) + ":" + Math.round((p.x1 + p.x2) / 160);
      const nov = Math.min(40, nw - (visited[key] || -40)) / 10, far = Math.min(1.4, Math.abs((p.x1 + p.x2) / 2 - x) / Math.max(W, 1) * 2.2);   // no height bias: anywhere on screen is fair game
      cands.push({ k: "visit", j, s: nov + far + rnd(0, 1.6) - map.d[j] * .1 + (energy > .5 ? 0 : -1) });
    }
    if (curA) { const j = nearestPlat(cursor.x, cursor.y); if (j >= 0 && j !== me && map.d[j] < 1e9) cands.push({ k: "cursor", j, s: 3.2 + (energy > .4 ? 1 : 0) - map.d[j] * .1 }); }
    if (energy < .55 || act_ > 25) { const opts = []; for (let j = 0; j < plats.length; j++) if (map.d[j] < 1e9 && j !== me) opts.push(j); if (opts.length) { const best = pick(opts); cands.push({ k: "rest", j: best, s: (1 - energy) * 6 + act_ / 20 - map.d[best] * .1 }); } }
    if (R.mode === "auto" && R.skins && Object.keys(R.skins).filter(vis_).length > 1) cands.push({ k: "outfit", s: .3 });
    cands.push({ k: "stay", s: .4 + (1 - energy) * 2 + (quiet ? 3 : 0) }); if (!quiet && energy > .3) cands.push({ k: "wander", s: 1.5 + energy }); cands.push({ k: "dance", s: quiet ? -3 : .9 + (energy > .7 ? 1 : 0) }); cands.push({ k: "chat", s: quiet || chatLevel === 0 ? -3 : (chatLevel === 2 ? 2 : 1) });
    if (HK.fun) cands.push({ k: "fun", s: quiet || chatLevel === 0 ? -3 : (chatLevel === 2 ? 1.6 : .9) });
    // softmax pick
    const tmp = .8, ws = cands.map(c => Math.exp(c.s / tmp)), tot = ws.reduce((a, b) => a + b, 0); let r = Math.random() * tot, c = cands[0];
    for (let i = 0; i < cands.length; i++) { r -= ws[i]; if (r <= 0) { c = cands[i]; break; } }
    if (c.k === "visit") goTo(c.j, {}); else if (c.k === "cursor") goTo(c.j, { look: "cursor" }); else if (c.k === "rest") goTo(c.j, { rest: true });
    else if (c.k === "wander") goTo(me, {});
    else if (c.k === "outfit") { const n = nextSkin(); if (n) changeSkin(n); setS("idle", "sit"); wait(3); } else if (c.k === "fun") { if (!HK.fun()) { setS("idle", "sit"); wait(2); } } else if (c.k === "dance") dance(5, null); else if (c.k === "chat") { chat(); setS("idle", "sit", 0, false); wait(rnd(4, 8)); }
    else { if (energy < .5 && Math.random() < .6) setS("lie", "lie", rnd(5, 9)); else { idleSp = pick(IDLES().length ? IDLES() : ["sit"]); setS("idle", idleSp, 0, face < 0); wait(rnd(2.5, 6)); } }
  }
  const wait = (s) => { until = now() + s; };
  function fleeFrom(px, py) {
    refreshWorld(true); const me = myPlat(); if (me < 0 || st === "drag" || st === "fall") return false; const map = dijkstra(me); let b = -1, bs = -1;
    for (let j = 0; j < plats.length; j++) { if (map.d[j] >= 1e9 || j === me) continue; const p = plats[j], cx = clamp(px, p.x1, p.x2), d = Math.hypot(cx - px, p.y - py) - map.d[j] * 6 + rnd(0, 120); if (d > bs) { bs = d; b = j; } }
    if (b < 0) return false; goTo(b, {}); return true;
  }
  function nearestPlat(px, py) {
    let b = -1, bd = 1e9; for (let j = 0; j < plats.length; j++) { const p = plats[j], dx = px < p.x1 ? p.x1 - px : px > p.x2 ? px - p.x2 : 0, dd = dx * 1.2 + Math.abs(p.y - py) * (p.y > py ? .6 : 1.6); if (dd < bd) { bd = dd; b = j; } } return b;
  }
  function goTo(j, g) {
    const me = myPlat(); if (me < 0) return; goal = Object.assign({ j }, g || {});
    const map = dijkstra(me); if (map.d[j] >= 1e9) { goal = null; setS("idle", "sit"); wait(2); return; }
    path = stepsTo(map, j); const p = plats[j]; const fx_ = goal.x != null ? clamp(goal.x, p.x1 + 12, p.x2 - 12) : rnd(p.x1 + 12, Math.max(p.x1 + 13, p.x2 - 12)); path.push({ t: "walk", x: fx_ });
    visited[Math.round(p.y / 40) + ":" + Math.round((p.x1 + p.x2) / 160)] = now(); nextStep();
  }
  function nextStep() {
    const s = path.shift(); if (!s) return arrive();
    if (s.t === "walk") { wx = s.x; wThen = s; wStart = now(); face = wx >= x ? 1 : -1; setS("walk", "walk"); }
    else if (s.t === "jump") {
      const J0 = y - s.ty + R.size * .22, v0 = -Math.sqrt(2 * G * Math.max(J0, R.size * .2)), tt = (-v0 + Math.sqrt(v0 * v0 + 2 * G * (s.ty - y))) / G;
      jumping = true; jTarget = s; face = s.tx >= x ? 1 : -1; flip = face < 0; fall(clamp((s.tx - x) / Math.max(tt, .2), -900, 900), v0); jumping = true; say(pick(["Hup!", "Parkour!", "Yoink!", "Up we go~"]), "excited", 900);
    } else if (s.t === "climb") { cx0 = s.x; cty = s.ty; setS("climb", R.skin.slots.climb ? "climb" : "back_view"); face = 1; }
  }
  function arrive() {
    const g = goal; goal = null; path = [];
    if (g && g.look === "cursor") { idleSp = "peek"; face = cursor.x >= x ? 1 : -1; setS("idle", R.skin.slots[idleSp] ? idleSp : "sit", 0, face < 0); wait(rnd(3, 6)); if (Math.random() < .5) say(pick(["I see you, cursor.", "Whatcha clicking?", "Go on, I'm watching."]), "cheeky"); }
    else if (g && g.look === "event") { idleSp = "point"; setS("idle", R.skin.slots.point ? "point" : "sit", 0, face < 0); wait(rnd(3, 5)); }
    else if (g && g.rest) { setS("lie", "lie", rnd(8, 14)); energy = Math.min(1, energy + .1); }
    else { setS("idle", "sit", 0, face < 0); wait(rnd(1.5, 4.5)); }
  }
  function look() { return { x, y }; }
  addEventListener("pointermove", e => { cursor = { x: e.clientX, y: e.clientY, t: now() }; if (R.on && st === "sleep" && false) act = now(); }, { passive: true });

  // ───────── skins: each skin is a set of poses listed in mascot/skins.json ─────────
  const MOODPOSE = { happy: "happy", excited: "celebrate", wink: "wink", cheeky: "wink", angry: "angry", sad: "sad", surprised: "surprised", embarrassed: "shy", sleepy: "sleep" };
  const FACE_CACHE = {};
  function faceUrl(f) {      // small head-shot for the speech bubble, cut from the pose itself
    const pose = MOODPOSE[f] || "happy", key = R.skinId + pose; if (FACE_CACHE[key]) return FACE_CACHE[key];
    const im = R.sp[pose]; if (!im || !im.naturalWidth) return slotUrl(pose);
    try {
      const sl = R.skin.slots[pose], ww = im.naturalWidth, hh = im.naturalHeight;
      const side = pose === "sleep" ? Math.max(ww, hh) : Math.min(ww, hh * (sl.bust ? .8 : .58)), sx = (ww - side) / 2, sy = pose === "sleep" ? (hh - side) / 2 : 0;
      const cv = document.createElement("canvas"); cv.width = 96; cv.height = 96; const g = cv.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(im, sx, sy, side, side, 0, 0, 96, 96);
      return (FACE_CACHE[key] = cv.toDataURL("image/png"));
    } catch (e) { return slotUrl(pose); }
  }
  const slotUrl = (slot) => { const sl = R.skin && R.skin.slots[slotOf(slot)]; return sl ? BASE + R.skinId + "/" + sl.f + ".webp" : ""; };
  const DPR = Math.max(1, window.devicePixelRatio || 1); const crispC = {};
  const unit = () => (R.skin ? 674 / R.skin.ref : 1);
  function crisp(name) {
    const slot = slotOf(name), im = R.sp[slot]; if (!im || !im.naturalWidth) return slotUrl(slot);
    const tw = Math.round(im.naturalWidth * k() * DPR), key = R.skinId + slot + ":" + tw, c = crispC[key];
    if (c && c.url) return c.url; if (tw >= im.naturalWidth * .95) return slotUrl(slot);
    if (!c) {
      crispC[key] = { url: null };
      try {
        let w = im.naturalWidth, h = im.naturalHeight, src = im;
        while (w / 2 > tw) { const cv = document.createElement("canvas"); w = Math.round(w / 2); h = Math.round(h / 2); cv.width = w; cv.height = h; const g = cv.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(src, 0, 0, w, h); src = cv; }
        const th = Math.round(im.naturalHeight * tw / im.naturalWidth), cv = document.createElement("canvas"); cv.width = tw; cv.height = th; const g = cv.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(src, 0, 0, tw, th);
        cv.toBlob(b => { if (b && crispC[key]) crispC[key].url = URL.createObjectURL(b); }, "image/png");
      } catch (e) { }
    }
    return slotUrl(slot);
  }
  function clearCrisp() { Object.keys(crispC).forEach(k_ => { const u = crispC[k_].url; if (u) URL.revokeObjectURL(u); delete crispC[k_]; }); }
  function loadSkin(id, cb) {
    const sk = R.skins[id]; if (!sk) return cb && cb(false);
    Object.keys(sk.slots).forEach(n => { const sl = sk.slots[n]; if (sl.frames && !sk.slots[n + "#0"]) sl.frames.forEach((fn, i) => { sk.slots[n + "#" + i] = Object.assign({}, sl, { f: fn, frames: null }); }); });   // multi-frame poses: walk#0, walk#1 ...
    const next = {}, files = {}; let left = 0, done = false; const fin = () => { if (done) return; done = true; R.skin = sk; R.skinId = id; R.sp = next; clearCrisp(); try { localStorage.setItem("riko.skin", id); } catch (e) { } cb && cb(true); };
    Object.keys(sk.slots).forEach(slot => { const f = sk.slots[slot].f; if (!files[f]) { files[f] = new Image(); left++; files[f].onload = files[f].onerror = () => { if (--left === 0) fin(); }; files[f].src = BASE + id + "/" + f + ".webp"; } next[slot] = files[f]; });
    if (!left) fin();
  }
  const firstSkin = () => { const a = Object.keys(R.skins || {}).filter(vis_); return a.indexOf(DEFAULT_SKIN) >= 0 ? DEFAULT_SKIN : (a[0] || Object.keys(R.skins)[0]); };
  function load(cb) {
    if (R.ready) return cb();
    fetch(BASE + "skins.json").then(r => r.json()).then(j => {
      R.skins = j; let id = null; try { id = localStorage.getItem("riko.skin"); } catch (e) { }
      if (R.mode !== "auto" && j[R.mode]) id = R.mode; R.skins = j; if (!j[id] || !vis_(id)) id = firstSkin();
      loadSkin(id, () => { R.ready = true; cb(); });
    }).catch(() => { });
  }
  const k = () => R.size * (ROLE === "main" ? 1 : .6) / 775 * unit();
  let fit = 1;
  const dim = () => { const i = R.sp[fslot()] || R.sp[slotOf(sp)] || R.sp.sit; return { w: (i.naturalWidth || 300) * k() * fit, h: (i.naturalHeight || 400) * k() * fit }; };
  function build() {
    if (layer) return;
    const css = document.createElement("style");
    css.textContent = `#rk{position:fixed;inset:0;z-index:60;pointer-events:none;overflow:hidden}
#rk img{-webkit-user-drag:none;user-select:none}
#rkPet{position:absolute;left:0;top:0;pointer-events:auto;cursor:grab;will-change:transform;touch-action:none}
#rkSh{position:absolute;left:0;top:0;height:8px;border-radius:50%;background:#0000002e;pointer-events:none}
#rkName{position:absolute;left:0;top:0;padding:2px 9px;border-radius:999px;background:#12141fd9;border:1px solid #ffffff30;color:#fff;font:700 11px/1.3 system-ui,sans-serif;letter-spacing:.3px;white-space:nowrap;pointer-events:none;box-shadow:0 2px 8px #0005}
#rkBub{position:absolute;left:0;top:0;display:none;max-width:230px;border:2px solid #f27ba3;border-radius:14px;padding:6px 10px 6px 6px;align-items:center;gap:7px;font:600 12.5px/1.3 system-ui,sans-serif;color:#5a2a3c;pointer-events:none;box-shadow:0 6px 18px #0006}
#rkBub::after{content:"";position:absolute;bottom:-9px;left:var(--tx,50%);width:12px;height:12px;background:inherit;border-right:2px solid var(--bb,#f27ba3);border-bottom:2px solid var(--bb,#f27ba3);transform:translateX(-50%) rotate(45deg)}
#rkBub img{height:44px;width:44px;object-fit:contain}
.rkfx{position:absolute;left:0;top:0;pointer-events:none;font-weight:700;animation:rkfl 1.3s ease-out forwards}
@keyframes rkfl{0%{opacity:0;transform:translate(var(--x),var(--y)) scale(.5)}15%{opacity:1}100%{opacity:0;transform:translate(calc(var(--x) + var(--dx)),calc(var(--y) + var(--dy))) scale(1.1)}}
.slow .rkfx{animation:none!important;display:none}`;
    document.head.appendChild(css);
    layer = document.createElement("div"); layer.id = "rk";
    layer.innerHTML = `<div id="rkSh"></div><img id="rkPet" alt="" draggable="false"><div id="rkName"></div><div id="rkBub"><img id="rkBi" alt=""><span id="rkBt"></span></div>`;
    document.body.appendChild(layer);
    nameEl = layer.querySelector("#rkName"); pet = layer.querySelector("#rkPet"); sh = layer.querySelector("#rkSh"); bub = layer.querySelector("#rkBub"); bi = layer.querySelector("#rkBi"); bt_ = layer.querySelector("#rkBt");
    pet.addEventListener("pointerdown", pdown); pet.addEventListener("pointermove", pmove);
    pet.addEventListener("pointerup", e => pup(e, true)); pet.addEventListener("pointercancel", e => pup(e, false));
    addEventListener("resize", () => refreshWorld(true));
  }
  function say(text, f, ms) {
    if (!crit && (quiet || chatLevel === 0)) return;
    text = String(text).replace(/Riko|রিকো/g, NAME); const m = MOODS[f] || MOODS.happy; bub.style.background = m[0]; bub.style.borderColor = m[1]; bub.style.setProperty("--bb", m[1]);
    bi.src = faceUrl(f); bt_.textContent = text; bub.style.display = "flex"; bubT = now() + (ms ? ms / 1000 : Math.max(2.8, .06 * text.length));
  }
  function setS(s, spr, sec, fl) { st = s; sT = now(); if (spr) sp = spr; if (fl !== undefined) flip = fl; until = sec ? now() + sec : 0; }
  function idle() { path = []; goal = null; setS("idle", "sit", 0, false); wait(rnd(.3, 1.5)); }
  function fx(ch, col, dx, dy, fs) {
    if (slow()) return; const e = document.createElement("span"), d = dim(); e.className = "rkfx"; e.textContent = ch;
    e.style.cssText = `--x:${x + rnd(-d.w * .2, d.w * .2)}px;--y:${y - d.h * .85}px;--dx:${dx}px;--dy:${dy}px;color:${col};font-size:${fs || 18}px`;
    layer.appendChild(e); setTimeout(() => e.remove(), 1400);
  }
  function react(spr, f, text, sec) {
    act = now(); path = []; goal = null; setS("react", spr, sec || 2.8); say(text, f);
    if (spr === "react_happy") for (let i = 0; i < 3; i++) fx("♥", "#f27ba3", rnd(-40, 40), -80, 20);
    if (spr === "react_surprised" || spr === "react_angry") fx("!", "#e0392b", 0, -50, 28);
  }
  function sleep() { path = []; goal = null; setS("sleep", "sleep"); say(ln("nap"), "sleepy", 4000); }
  function wake() { act = now(); energy = Math.min(1, energy + .3); react("react_happy", "happy", ln("wake")); }
  function dance(sec, txt) { act = now(); path = []; goal = null; setS("dance", "dance", sec || 6); if (txt !== null) say(txt || "Dance party!", "excited"); }
  function fall(a, b) { vx = a; vy = b; cur = null; setS("fall", "jump"); }
  function changeSkin(id) {
    if (!R.skins || !R.skins[id] || id === R.skinId || R.switching || (HK.skinOk && !HK.skinOk(id))) return; R.switching = true; act = now();
    for (let i = 0; i < 9; i++) fx("✦", pick(["#f5a623", "#7b72d9", "#4fb6e0", "#f27ba3"]), rnd(-80, 80), rnd(-90, -20), 18);
    if (pet) pet.style.opacity = "0";
    setTimeout(() => loadSkin(id, () => { R.switching = false; if (pet) pet.style.opacity = ""; if (R.on) say(ln("outfit"), "wink"); }), 260);
  }
  function nextSkin() { const ids = Object.keys(R.skins || {}).filter(i => i !== R.skinId && vis_(i) && (!HK.skinOk || HK.skinOk(i))); return ids.length ? pick(ids) : null; }
  function chat() { if (extra.length && Math.random() < .4) { say(pick(extra), "cheeky"); return; } const c = pick(L.chat); say(c[1], c[0]); }
  function confetti() { for (let i = 0; i < 16; i++) fx("■", pick(["#f27ba3", "#f5a623", "#4fb6e0", "#7b72d9", "#5cc98a"]), rnd(-110, 110), rnd(-130, -30), 11); }

  function cmd(c) { crit = true; try { cmd0(c); } finally { crit = false; } if (HK.onEvent) HK.onEvent(String(c).toLowerCase()); }
  function cmd0(c) {
    if (!R.on || !R.ready) return; c = String(c).toLowerCase(); act = now(); energy = Math.min(1, energy + .05);
    if (st === "drag") return;
    const go = (key) => { if (FOCUS[key]) pendingGo = { sel: FOCUS[key] }; };
    if (c === "success") { setS("celebrate", "celebrate", 3.5); say(ln("ok"), "excited"); confetti(); go("ok"); }
    else if (c === "error") { react("sad", "sad", ln("fail"), 3.8); go("error"); }
    else if (c === "warn") { react("panic", "surprised", ln("miss"), 3.8); go("warn"); }
    else if (c === "busy") { react("laptop", "excited", ln("work"), 3.2); go("busy"); }
    else if (c === "paste") { react("tap", "excited", nClips > 1 ? ln("paste2") : ln("paste"), 2.4); go("paste"); }
    else if (c === "cat") { react("react_happy", "cheeky", ln("cat"), 2.4); go("cat"); }
    else if (c === "outfit") { const n = nextSkin(); if (n) changeSkin(n); } else if (c === "dance") dance(); else if (c === "sleep") sleep(); else if (c === "chat") chat();
  }
  function hopIn() {
    crit = true; setTimeout(() => { crit = false; }, 0); refreshWorld(true); path = []; goal = null; x = clamp(W * rnd(.3, .7), 60, W - 60); y = -120; fall(rnd(-120, 120), 0); say(ln("hop"), "cheeky", 2800); act = now();
  }

  function tick(ts) {
    raf = requestAnimationFrame(tick);
    if (document.visibilityState === "hidden") { last = 0; return; }
    refreshWorld(false);
    const tm = ts / 1000, dt = Math.min(tm - (last || tm), .1); last = tm; t += dt; const nw = now(); let bob = 0, cw = 0;
    { const full = dim().h / fit, want = y < full + 4 ? Math.max(.42, Math.min(1, (y - 8) / full)) : 1; fit += (want - fit) * Math.min(1, dt * 8); }
    const d = dim(), half = d.w / 2, spd = 80 * (R.size / 150) * (.8 + .4 * energy) * (R.speedMul || 1);
    if (st === "drag") { const tg = clamp(dvx * .02, -28, 28); ang += (tg - ang) * Math.min(1, dt * 10); }
    else if (st === "fall") {
      const py = y; vy += G * dt; x += vx * dt; y += vy * dt; ang += (jumping ? 0 : vx * .05 * dt * 6);
      if (x - half < 0) { x = half; vx = Math.abs(vx) * .7 } else if (x + half > W) { x = W - half; vx = -Math.abs(vx) * .7 }
      let land = null;
      if (vy > 0) for (const p of plats) if (x >= p.x1 && x <= p.x2 && py <= p.y + 1 && y >= p.y && (!land || p.y < land.y)) land = p;
      if (land || y > gy + 2) {                         // landed (or popped out of the metadata strip)
        y = land ? land.y : gy; const hard = Math.abs(vy) > 900 && !jumping; ang = 0; const wasJ = jumping, tgt = jTarget; jumping = false; jTarget = null; vx = vy = 0;
        const cont = (wasJ || dropping) && goal; dropping = false;
        if (cont) { setS("land", landSp(), .25); }
        else { path = []; goal = null; setS("land", landSp(), 1.4); say(hard ? "Oof! My dignity!" : "Phew. Stuck the landing.", hard ? "surprised" : "happy", 1600); }
      }
    } else {
      ang += (0 - ang) * Math.min(1, dt * 10);
      const onP = platAt(x, y, 6);
      if (!onP && st !== "climb" && st !== "dance") fall(0, 0); else if (onP && st !== "climb") y = onP.y;
      if (st === "idle") { if (nw >= until) decide(); }
      else if (st === "walk") {
        const dx = wx - x; face = dx >= 0 ? 1 : -1; flip = face < 0; const run = Math.abs(dx) > 360; sp = run ? "run" : "walk"; { const stp = Math.min(Math.abs(dx), spd * (run ? 2.3 : 1) * dt); x += face * stp; trav += stp; } energy = Math.max(0, energy - dt * .006);
        if (Math.abs(wx - x) < 2) { if (wThen && wThen.then === "drop") { path = path; fall(wThen.dir * 70, 0); jumping = false; dropping = true; } else nextStep(); }
        else if (nw - wStart > 14) idle();
      }
      else if (st === "climb") {
        x = cx0; y -= 150 * dt * (R.size / 150); const cs0 = R.skin.slots.climb; sp = cs0 ? "climb" : "back_view"; cw = cs0 ? 0 : Math.sin(t * 14) * 5; trav += 150 * dt * (R.size / 150); energy = Math.max(0, energy - dt * .02);
        if (y <= cty) { y = cty; setS("land", landSp(), .2); st = "land"; jumping = false; }
      }
      else if (st === "dance") { const f = Math.floor(t / .45), d0 = R.skin.slots.dance; if (d0 && d0.frames) { sp = "dance"; flip = false; } else { sp = ["dance", "wave", "jump", "celebrate", "love"][f % 5]; flip = f % 2 === 1; } if (nw >= until) idle(); }
      else if (st === "land") { if (nw >= until) { if (goal) nextStep(); else idle(); } }
      else if (["lie", "react", "celebrate"].includes(st)) { if (nw >= until) idle(); }
      if (nw - act > 45 && ["idle", "walk", "lie"].includes(st)) sleep();
      if (st === "sleep" || st === "lie") energy = Math.min(1, energy + dt * .03);
    }
    const dd = dim(), sa = nw - sT, pp = t * 9, bb = Math.abs(Math.sin(pp)); let sx = 1, sy = 1, sw = cw;
    const sl00 = R.skin && R.skin.slots[slotOf(sp)], AN = !!(sl00 && sl00.frames);       // drawn frames already contain the motion: no squash / hop on top
    if (st === "walk") { if (AN) { sw = 0; } else { bob = bb * R.size * .05; sy = .95 + .09 * bb; sx = 1.04 - .07 * bb; sw = Math.sin(pp) * 3 + face * 3; } }
    else if (st === "idle") { sy = 1 + .011 * Math.sin(t * 2.1); sx = 1 - .005 * Math.sin(t * 2.1); }
    else if (AN && (st === "dance" || st === "celebrate" || st === "land" || st === "fall" || st === "climb")) { if (st === "celebrate") bob = Math.abs(Math.sin(t * 6)) * R.size * .03; }
    else if (st === "sleep" || st === "lie") { }
    else if (st === "dance") { const c = Math.abs(Math.sin(t * 8)); bob = c * R.size * .07; sw = Math.sin(t * 7) * 7; sy = .94 + .1 * c; sx = 1.05 - .08 * c; }
    else if (st === "celebrate") { const c = Math.abs(Math.sin(t * 7)); bob = c * R.size * .08; sy = .93 + .14 * c; sx = 1.06 - .1 * c; }
    else if (st === "land") { const e = Math.exp(-sa * 9); sy = 1 - .2 * e; sx = 1 + .12 * e; }
    else if (st === "react") { const e = Math.exp(-sa * 7) * Math.cos(sa * 24) * .12; sx = sy = 1 + e; }
    else if (st === "fall") { sy = 1 + Math.min(.15, Math.abs(vy) / 9000); sx = 2 - sy; }
    else if (st === "climb") { bob = 0; sy = 1 + .03 * Math.sin(t * 14); }
    const sl0 = R.skin && R.skin.slots[slotOf(sp)]; const frameSp = fslot(); const src = crisp(frameSp); if (pet.getAttribute("src") !== src) pet.src = src;
    const mk = sl0 && sl0.bust ? "linear-gradient(#000 80%,transparent)" : "none"; if (pet._mk !== mk) { pet._mk = mk; pet.style.webkitMaskImage = mk; pet.style.maskImage = mk; }
    pet.style.width = Math.round(dd.w) + "px"; pet.style.transformOrigin = st === "drag" ? "50% 0" : st === "fall" ? "50% 50%" : "50% 100%";
    pet.style.transform = `translate(${Math.round(x - dd.w / 2)}px,${Math.round(y - dd.h - bob)}px) rotate(${ang + sw}deg) scale(${sx * ((flip !== !!(sl0 && sl0.left)) ? -1 : 1)},${sy})`;
    const g = st !== "drag" && st !== "fall"; sh.style.display = g ? "block" : "none"; sh.style.width = dd.w * .55 * (1 - bob / R.size) + "px"; sh.style.transform = `translate(${x - dd.w * .275 * (1 - bob / R.size)}px,${y - 4}px)`;
    if (nameEl) { if (TAG) { if (nameEl.textContent !== NAME) nameEl.textContent = NAME; nameEl.style.display = "block"; const nw_ = nameEl.offsetWidth, nh_ = nameEl.offsetHeight; nameEl.style.transform = `translate(${Math.round(clamp(x - nw_ / 2, 2, W - nw_ - 2))}px,${Math.round(Math.min(y + 3, H - nh_ - 2))}px)`; } else nameEl.style.display = "none"; }
    if (HK.onFrame) HK.onFrame({ x, y, w: dd.w, h: dd.h, bob, flip, st, now: nw });
    if (nw > fxT) { if (st === "sleep") { fx("z", "#7b72d9", 24, -60, 18); fxT = nw + 1.3 } else if (st === "dance") { fx("♪", "#f5a623", rnd(-40, 40), -70, 20); fxT = nw + .5 } }
    if (bub.style.display === "flex") {
      if (nw > bubT) bub.style.display = "none";
      else { const bw = bub.offsetWidth, bh = bub.offsetHeight, l = clamp(x - bw / 2, 4, W - bw - 4), tp = Math.max(4, y - dd.h - bob - bh - 14); bub.style.transform = `translate(${l}px,${tp}px)`; bub.style.setProperty("--tx", clamp(x - l, 16, bw - 16) + "px"); }
    }
  }
  function pdown(e) { e.stopPropagation(); pet.setPointerCapture(e.pointerId); down = { id: e.pointerId, x: e.clientX, y: e.clientY }; grab = { x: x - e.clientX, y: y - e.clientY }; hist = [[now(), e.clientX, e.clientY]]; dragging = false; act = now(); }
  function pmove(e) {
    if (!down || e.pointerId !== down.id) return; const nw = now();
    if (!dragging && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 8) { dragging = true; act = nw; path = []; goal = null; setS("drag", "react_surprised"); say("Hey! Put me down!", "surprised", 2000); }
    if (dragging) { x = e.clientX + grab.x; y = e.clientY + grab.y; hist.push([nw, e.clientX, e.clientY]); hist = hist.filter(h => nw - h[0] < .12); if (hist.length > 1) { const a = hist[0], b = hist[hist.length - 1]; dvx = (b[1] - a[1]) / Math.max(b[0] - a[0], .001); } }
  }
  function pup(e, ok) {
    if (!down || e.pointerId !== down.id) return; crit = true; setTimeout(() => { crit = false; }, 0); if (ok && !dragging && HK.onHit) HK.onHit();
    if (dragging) {
      let a = 0, b = 0; if (hist.length > 1) { const p = hist[0], q = hist[hist.length - 1], dt = Math.max(q[0] - p[0], .001); a = (q[1] - p[1]) / dt; b = (q[2] - p[2]) / dt; }
      a = clamp(a, -2200, 2200); b = clamp(b, -2200, 2200); dragging = false; jumping = false; fall(a, b); if (Math.hypot(a, b) > 700) say("WHEEEEE", "excited", 1800);
    } else if (ok) {
      const nw = now(); clicks = clicks.filter(c => nw - c < 2).concat(nw);
      if (st === "sleep") wake();
      else if (clicks.length >= 4) { clicks = []; react("heart_hug", "cheeky", ln("tickle")); }
      else { const c = pick(L.click); react(c[0], c[1], pick(c[2])); }
    }
    down = null;
  }

  function start() {
    if (R.on) return; R.on = true;
    load(() => {
      if (!R.on) return; build(); layer.style.display = ""; refreshWorld(true); pet.style.width = "0";
      x = clamp(W * rnd(.1, .9), 60, Math.max(61, W - 60)); y = -120; last = 0; act = now(); fall(0, 0);
      if (!raf) raf = requestAnimationFrame(tick);
      setTimeout(() => { if (R.on && st !== "drag") say(ln("hi"), "happy"); }, 1400);
    });
  }
  function stop() { R.on = false; if (raf) cancelAnimationFrame(raf); raf = 0; if (layer) layer.style.display = "none"; }
  function setSize(v) { R.size = Math.max(90, Math.min(320, +v || 150)); clearCrisp(); }

  let lastVis = document.visibilityState;
  document.addEventListener("visibilitychange", () => {      // main hidden → overlay shows (and the reverse): Riko hops over
    const v = document.visibilityState; if (v === "visible" && lastVis !== "visible" && R.on && R.ready && st !== "drag") hopIn(); lastVis = v;
  });

  function setMode(m) { R.mode = m || "auto"; if (R.ready && R.mode !== "auto" && R.skins && R.skins[R.mode] && vis_(R.mode) && R.mode !== R.skinId) changeSkin(R.mode); }
  async function applyCfg(st0) {
    try {
      const s = st0 || await C.api("state"), u = (s && s.ui) || {};
      const who = u.mascot_who === "riko" ? "riko" : "sajeeb"; R.who = who;
      NAME = (u.mascot_char || "").trim() || (who === "riko" ? "Riko" : "Sajeeb"); TAG = u.mascot_tag !== false;
      if (who === "riko" && NAME === "Sajeeb") NAME = "Riko";
      setSize(u.mascot_size || 150); setMode(u.mascot_skin || "auto"); if (HK.cfg) HK.cfg(u);
      if (R.ready && R.skins && !vis_(R.skinId)) { const f = firstSkin(); if (f && f !== R.skinId) { R.switching = false; changeSkin(f); } }
      const want = u.mascot === true && !(s && s.slow);
      if (want) start(); else stop();
    } catch (e) { }
  }
  function wire() {
    C.on("clips", d => { const n = d.n || 0; if (n > nClips) { nClips = n; cmd("paste"); } nClips = n; });
    C.on("saved", () => { cmd("success"); if (R.mode === "auto" && ++nSaved % 12 === 0) setTimeout(() => cmd("outfit"), 4200); }); C.on("save_failed", () => cmd("error")); C.on("save_partial", () => cmd("warn")); C.on("missed_save", () => cmd("warn"));
    C.on("upload", d => { if (d && d.running) cmd("busy"); });
    C.on("state_changed", () => applyCfg()); C.on("settings_changed", () => applyCfg());
  }
  window.RIKO = { hooks: HK, core: { say: (t_, f_, ms) => { crit = true; try { say(t_, f_, ms); } finally { crit = false; } }, react: (a, b, c_, d_) => { crit = true; try { react(a, b, c_, d_); } finally { crit = false; } }, fx, dance, fleeFrom, confetti, setS, get pos() { return { x, y, st, W, H, gy }; }, get energy() { return energy; }, set energy(v) { energy = clamp(v, 0, 1); }, set idle(v) { idleSp = v; }, setQuiet: v => { quiet = !!v; }, get quiet() { return quiet; }, setChat: v => { chatLevel = +v; }, setLang: v => { lang = v || "en"; }, setExtra: a => { extra = a || []; }, speed: 1, get skin() { return R.skinId; }, setSpeed: v => { R.speedMul = v; }, get on() { return R.on && R.ready; }, el: () => pet, layer: () => layer, nearest: nearestPlat, plats: () => plats, sleep, wake, state: () => st, pick, ln }, dbg: () => ({ x, y, st, gy, goal: !!goal, n: plats.length, plats, zones, W, H }), command: cmd, apply: applyCfg, setMode, outfit: () => cmd("outfit"), skinSlots: () => (R.skin ? R.skin.slots : null), skins: () => R.skins ? Object.keys(R.skins).map(i => [i, R.skins[i].name]) : [], setEnabled: v => { v ? start() : stop(); }, setSize, wire };
  window.riko = { command: cmd };
  if (window.C && C.on) { wire(); setTimeout(applyCfg, ROLE === "main" ? 1500 : 800); }
})();
