/* Spatial room: every screen has a place in one room. Clicking the rail (or Ctrl+Alt+arrows) glides the camera there. */
(function () {
  "use strict";
  const KEY = "nab_room";
  /* where each screen stands in the room: x right, y down */
  const POS = { settings: [-1, 0], clip: [0, 0], tracker: [1, 0], hunt: [2, 0], shot: [-1, 1], reports: [0, 1], pr: [1, 1], pdf: [2, 1], search: [0, 2], mail: [1, 2], subs: [2, 2] };
  const NAME = { settings: "Settings shelf", clip: "Clip desk", tracker: "Paper wall", hunt: "News hunter", shot: "Screenshots", reports: "Reports table", pr: "PR value", pdf: "PDF bench", search: "Search", mail: "Mail desk", subs: "Subscriptions" };
  let on = false, prev = "clip", wrapped = false, map = null, bg = null;
  const reduce = () => { try { return matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; } };
  const live = () => on && !document.body.classList.contains("quiet") && !!window.DEPTH && DEPTH.isOn();

  function glide(from, to) {                       // soft: the new screen eases in (fade + a few pixels), nothing 3D, nothing heavy
    if (!live() || from === to || !POS[from] || !POS[to]) return;
    const nv = document.getElementById("view-" + to); if (!nv) return;
    const a = POS[from], b = POS[to], dx = Math.sign(b[0] - a[0]) * 14, dy = Math.sign(b[1] - a[1]) * 10;
    nv.animate([{ opacity: 0, transform: `translate3d(${dx}px,${dy}px,0)` }, { opacity: 1, transform: "none" }], { duration: 190, easing: "ease-out" });
  }
  function floor(v) { if (!bg) return; const p = POS[v] || [0, 0]; bg.style.setProperty("--rx", p[0]); bg.style.setProperty("--ry", p[1]); }
  function mark(v) {
    floor(v); if (!map) return; map.querySelectorAll("i").forEach((i) => i.classList.toggle("on", i.dataset.v === v));
    map.title = (NAME[v] || v) + "  (Ctrl+Alt+arrows to move)";
  }
  function build() {
    if (!bg) { bg = document.createElement("div"); bg.id = "roomBg"; bg.innerHTML = "<b></b>"; document.body.insertBefore(bg, document.body.firstChild); }
    if (!map) {
      map = document.createElement("div"); map.id = "roomMap";
      Object.keys(POS).forEach((v) => { const i = document.createElement("i"); i.dataset.v = v; i.style.gridColumn = POS[v][0] + 2; i.style.gridRow = POS[v][1] + 1; i.title = NAME[v]; i.onclick = () => window.MAIN && MAIN.show(v); map.appendChild(i); });
      const h = document.querySelector("#quietBtn"); if (h && h.parentNode) h.parentNode.insertBefore(map, h); else return false;
    }
    return true;
  }
  function step(dx, dy) {
    const cur = (window.MAIN && MAIN.view) || "clip", a = POS[cur] || [0, 0]; let best = null, bd = 1e9;
    Object.keys(POS).forEach((v) => { const p = POS[v], ex = p[0] - a[0], ey = p[1] - a[1]; if (!(ex * dx > 0 || ey * dy > 0)) return; if (dx && ey) return; if (dy && ex) return; const d = Math.abs(ex) + Math.abs(ey); if (d < bd) { bd = d; best = v; } });
    if (best) MAIN.show(best);
  }
  function wrap() {
    if (wrapped) return; if (!window.MAIN || !MAIN.show) return setTimeout(wrap, 300); wrapped = true;
    const orig = MAIN.show; MAIN.show = function (v) { const from = MAIN.view; const r = orig.apply(this, arguments); try { if (from !== v) { glide(from, v); } prev = v; mark(v); } catch (e) { } return r; };
    mark(MAIN.view || "clip");
  }
  function enable(v) {
    v = !!v && !reduce(); on = v; document.body.classList.toggle("room", on);
    if (on && build()) { wrap(); mark((window.MAIN && MAIN.view) || "clip"); }
    try { localStorage.setItem(KEY, on ? "1" : "0"); } catch (e) { }
  }
  document.addEventListener("keydown", (e) => {
    if (!on || !e.ctrlKey || !e.altKey) return; const k = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key]; if (k) { e.preventDefault(); step(k[0], k[1]); }
  });
  window.ROOM = { enable, isOn: () => on, go: (v) => window.MAIN && MAIN.show(v) };
  let s = "1"; try { s = localStorage.getItem(KEY) || "1"; } catch (e) { }
  const start = () => { enable(s !== "0"); if (on && !map) setTimeout(() => enable(true), 1200); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
