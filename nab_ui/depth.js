/* 3D depth layer — CSS-3D only (no WebGL), so it is light on every PC.
   Tilt on cards, dock-style rail, fly-to-folder after save. Toggle: Settings > Start-up > "3D depth". */
(function () {
  "use strict";
  const KEY = "nab_depth"; let on = false, cur = null, raf = 0, ev = null;
  const reduce = () => window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SEL = ".card,.dtilt";
  function reset(el) { if (!el) return; el.classList.remove("dt-on"); el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); }
  function tick() {
    raf = 0; if (!ev) return; const e = ev; ev = null;
    const rail = document.querySelector(".rail");
    if (rail && rail.contains(e.target)) { dock(e); if (cur) { reset(cur); cur = null; } return; }
    const el = e.target.closest && e.target.closest(SEL);
    if (el !== cur) { reset(cur); cur = el; }
    if (!el) return;
    const r = el.getBoundingClientRect(); if (r.width < 40 || r.height < 30) return;
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    const big = Math.max(r.width, r.height) > 560 ? .35 : 1;                    // big panels tilt less so text stays steady
    el.classList.add("dt-on");
    el.style.setProperty("--ry", ((px - .5) * 9 * big).toFixed(2) + "deg"); el.style.setProperty("--rx", ((.5 - py) * 7 * big).toFixed(2) + "deg");
    el.style.setProperty("--gx", (px * 100).toFixed(1) + "%"); el.style.setProperty("--gy", (py * 100).toFixed(1) + "%");
  }
  function dock(e) {
    document.querySelectorAll(".rail .rb").forEach((b) => { const r = b.getBoundingClientRect(), d = Math.abs(e.clientY - (r.top + r.height / 2)), k = Math.max(0, 1 - d / 110);
      b.style.setProperty("--ds", (1 + k * .07).toFixed(3)); b.style.setProperty("--dx", "0px"); });
  }
  function undock() { document.querySelectorAll(".rail .rb").forEach((b) => { b.style.setProperty("--ds", 1); b.style.setProperty("--dx", "0px"); }); }
  function move(e) { ev = e; if (!raf) raf = requestAnimationFrame(tick); }
  function leave() { reset(cur); cur = null; undock(); }
  function enable(v) {
    v = !!v && !reduce(); if (v === on) return; on = v; document.body.classList.toggle("depth", on);
    if (on) { document.addEventListener("pointermove", move, { passive: true }); document.addEventListener("pointerleave", leave); document.querySelector(".rail") && document.querySelector(".rail").addEventListener("pointerleave", undock); }
    else { document.removeEventListener("pointermove", move); document.removeEventListener("pointerleave", leave); leave(); }
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { }
  }
  /* a saved clip "flies" from the canvas into its category: the list scrolls to the row, the row jumps up to catch it */
  function fly(fromEl, toEl) {
    if (!on || !fromEl || !toEl) return;
    try { toEl.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) { }
    setTimeout(() => {
      const a = fromEl.getBoundingClientRect(); let b = toEl.getBoundingClientRect(); if (!a.width || !b.width) return;
      const w = Math.min(a.width, 200), h = Math.min(a.height, 140), g = document.createElement("div"); g.className = "dfly";
      g.style.cssText = `left:${a.left + a.width / 2 - w / 2}px;top:${a.top + a.height / 2 - h / 2}px;width:${w}px;height:${h}px`; document.body.appendChild(g);
      const dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
      toEl.classList.add("dreach");                                              // the row leans out to meet the clip
      const an = g.animate([{ transform: "perspective(700px) translate3d(0,0,0) rotateY(0) scale(1)", opacity: .95 }, { transform: `perspective(700px) translate3d(${dx * .5}px,${dy * .5 - 70}px,120px) rotateY(160deg) scale(.7)`, opacity: .9, offset: .55 }, { transform: `perspective(700px) translate3d(${dx}px,${dy}px,0) rotateY(360deg) scale(.1)`, opacity: .15 }], { duration: 640, easing: "cubic-bezier(.5,.1,.3,1)" });
      an.onfinish = () => { g.remove(); toEl.classList.remove("dreach"); toEl.classList.add("dcatch"); const n = document.createElement("span"); n.className = "dplus"; n.textContent = "+1"; toEl.appendChild(n); setTimeout(() => { toEl.classList.remove("dcatch"); n.remove(); }, 900); };
    }, 380);
  }
  /* hover the recent-saves button: the last saves fan out as a 3D card stack, click opens the full list */
  let peekEl = null, peekT = 0;
  function peekClose() { clearTimeout(peekT); peekT = setTimeout(() => { if (peekEl) { peekEl.remove(); peekEl = null; } }, 220); }
  async function peekOpen(btn) {
    if (!on || !window.C) return; clearTimeout(peekT); if (peekEl) return;
    let r; try { r = await C.api("recent", { limit: 6 }); } catch (e) { return; } if (!r || !r.items || !r.items.length || peekEl) return;
    const box = document.createElement("div"); box.className = "dpeek"; const br = btn.getBoundingClientRect();
    box.style.cssText = `left:${Math.max(8, Math.min(innerWidth - 300, br.left - 120))}px;top:${br.bottom + 8}px`;
    box.innerHTML = r.items.slice(0, 6).map((it, i) => `<div class="dp-c" style="--i:${i}"><img src="${C.url("/thumb?w=220&p=" + encodeURIComponent(it.path))}"><b>${C.esc(it.category || "")}</b><small>${C.esc(it.time || "")}</small></div>`).join("");
    box.onmouseenter = () => clearTimeout(peekT); box.onmouseleave = peekClose; box.onclick = () => { box.remove(); peekEl = null; window.MAIN && MAIN.recent(); };
    document.body.appendChild(box); peekEl = box;
  }
  function wirePeek() { const b = document.getElementById("recentBtn"); if (!b) return setTimeout(wirePeek, 500); b.addEventListener("mouseenter", () => peekOpen(b)); b.addEventListener("mouseleave", peekClose); }
  /* 3D bar chart (CSS 3D): drag to turn it */
  function bars(host, title, rows) {
    rows = (rows || []).filter((r) => r && r[1] > 0).slice(0, 8); if (!rows.length) return;
    const mx = Math.max(...rows.map((r) => r[1])), C0 = ["#5b8cff", "#a78bfa", "#22d3ee", "#34d399", "#fbbf24", "#fb7185", "#60a5fa", "#c084fc"];
    const d = document.createElement("div"); d.className = "d3b";
    d.style.setProperty("--ww", rows.length * 54 + "px");
    d.innerHTML = `<div class="d3b-t">${C.esc(title)}</div><div class="d3b-s"><div class="d3b-w">${rows.map((r, i) => `<div class="d3b-b" style="--x:${i};--h:${Math.max(8, r[1] / mx * 130)}px;--c:${C0[i % 8]};--d:${i * 80}ms"><i class="t"></i><i class="f"></i><i class="k"></i><i class="r"></i><i class="l"></i></div>`).join("")}</div></div><div class="d3b-lg">${rows.map((r, i) => `<span style="--c:${C0[i % 8]}"><i></i>${C.esc(String(r[0]))} <b>${r[1]}</b></span>`).join("")}</div>`;
    host.appendChild(d);
    const w = d.querySelector(".d3b-w"); let ax = 62, az = -32, down = null;
    const set = () => { w.style.transform = `rotateX(${ax}deg) rotateZ(${az}deg)`; }; set();
    d.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY, ax, az]; d.setPointerCapture(e.pointerId); });
    d.addEventListener("pointermove", (e) => { if (!down) return; az = down[3] + (e.clientX - down[0]) * .4; ax = Math.max(20, Math.min(80, down[2] - (e.clientY - down[1]) * .3)); set(); });
    d.addEventListener("pointerup", () => { down = null; });
  }

  /* ───── quiet mode: every effect off at once (Ctrl+Shift+Q) ───── */
  let quiet = false, pre = null;
  function setQuiet(v) {
    v = !!v; if (v === quiet) return; quiet = v; document.body.classList.toggle("quiet", v);
    const qb = document.getElementById("quietBtn"); if (qb) qb.classList.toggle("on", v);
    if (v) { pre = { d: on, m: !!(window.MAIN && MAIN.mouseFxOn && MAIN.mouseFxOn()) }; enable(false); if (window.MAIN && MAIN.mouseFx) MAIN.mouseFx(false); }
    else if (pre) { enable(pre.d); if (pre.m && window.MAIN && MAIN.mouseFx) MAIN.mouseFx(true); }
    try { localStorage.setItem("nab_quiet", v ? "1" : "0"); } catch (e) { }
  }
  document.addEventListener("keydown", (e) => { if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "q") { e.preventDefault(); setQuiet(!quiet); } });
  document.addEventListener("click", (e) => { if (e.target.closest && e.target.closest("#quietBtn")) setQuiet(!quiet); });
  /* ───── smart focus: while you work on the canvas the rest of the app steps back ───── */
  let ft = 0;
  function focusOn() { if (quiet || !on) return; clearTimeout(ft); document.body.classList.add("dfocus"); }
  function focusOff() { clearTimeout(ft); ft = setTimeout(() => document.body.classList.remove("dfocus"), 500); }
  function wireFocus() { const st = document.getElementById("stage"); if (!st) return setTimeout(wireFocus, 600); st.addEventListener("pointerdown", focusOn); st.addEventListener("pointerleave", focusOff); st.addEventListener("pointerenter", () => { if (document.body.classList.contains("dfocus")) clearTimeout(ft); }); }
  /* ───── daily goal ring around the logo ───── */
  let goal = 30; try { goal = +localStorage.getItem("nab_goal") || 30; } catch (e) { }
  async function ring() {
    const el = document.querySelector(".logo-dot"); if (!el || !window.C) return;
    try { const r = await C.api("recent", { limit: 500 }); const n = (r.items || []).length, p = Math.min(1, n / goal);
      el.style.setProperty("--p", (p * 360).toFixed(0) + "deg"); el.classList.toggle("gold", p >= 1); el.parentElement.title = n + " clips saved this session / goal " + goal; } catch (e) { }
  }
  /* ───── team online row ───── */
  async function team() {
    const b = document.getElementById("teamRow"); if (!b || !window.C) return;
    try { const r = await C.api("team_online", {}); const l = (r.pcs || []).slice(0, 8);
      b.innerHTML = l.map((n, i) => `<i class="dav" style="--i:${i};--h:${(n.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 37) % 360}" title="${C.esc(n)} is online">${C.esc(n.replace(/^DESKTOP-?/i, "").slice(0, 2).toUpperCase() || "PC")}</i>`).join("");
      b.classList.toggle("hidden", !l.length); } catch (e) { }
  }
  function startExtras() { wireFocus(); ring(); team(); setInterval(ring, 20000); setInterval(team, 30000); document.addEventListener("clips", ring); if (window.C && C.on) { C.on("saved", () => setTimeout(ring, 600)); } try { if (localStorage.getItem("nab_quiet") === "1") setQuiet(true); } catch (e) { } }
  setTimeout(startExtras, 1500);
  window.DEPTH = { enable, fly, bars, isOn: () => on, quiet: setQuiet, isQuiet: () => quiet, goal: (n) => { goal = Math.max(1, +n || 30); try { localStorage.setItem("nab_goal", goal); } catch (e) { } ring(); }, getGoal: () => goal };
  wirePeek();
  let saved = "1"; try { saved = localStorage.getItem(KEY) || "1"; } catch (e) { }
  enable(saved !== "0");
})();
