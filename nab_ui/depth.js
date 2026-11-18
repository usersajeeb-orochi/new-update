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
      b.style.setProperty("--ds", (1 + k * .16).toFixed(3)); b.style.setProperty("--dx", (k * 5).toFixed(1) + "px"); });
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
  /* a clip card "flies" from where it was saved into the category button, with a little 3D turn */
  function fly(fromEl, toEl, label) {
    if (!on || !fromEl || !toEl) return;
    const a = fromEl.getBoundingClientRect(), b = toEl.getBoundingClientRect(); if (!a.width || !b.width) return;
    const g = document.createElement("div"); g.className = "dfly"; const w = Math.min(a.width, 200), h = Math.min(a.height, 140); g.style.cssText = `left:${a.left + a.width / 2 - w / 2}px;top:${a.top + a.height / 2 - h / 2}px;width:${w}px;height:${h}px`;
    document.body.appendChild(g);
    const dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
    const an = g.animate([{ transform: "perspective(700px) translate3d(0,0,0) rotateY(0) scale(1)", opacity: .95 }, { transform: `perspective(700px) translate3d(${dx * .5}px,${dy * .5 - 60}px,120px) rotateY(160deg) scale(.7)`, opacity: .9, offset: .55 }, { transform: `perspective(700px) translate3d(${dx}px,${dy}px,0) rotateY(360deg) scale(.08)`, opacity: 0 }], { duration: 620, easing: "cubic-bezier(.5,.1,.3,1)" });
    an.onfinish = () => { g.remove(); toEl.classList.add("dpulse"); setTimeout(() => toEl.classList.remove("dpulse"), 650); };
  }
  window.DEPTH = { enable, fly, isOn: () => on };
  let saved = "1"; try { saved = localStorage.getItem(KEY) || "1"; } catch (e) { }
  enable(saved !== "0");
})();
