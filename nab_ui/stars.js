/* Constellations and asterisms that wake up when the pointer comes near. Plain 2D canvas: light on CPU/GPU (no WebGL, no downloads). */
(function () {
  "use strict";
  // unit-box shapes: points + edges
  const SHAPES = {
    dipper: { p: [[.05, .30], [.22, .28], [.36, .36], [.52, .40], [.80, .30], [.80, .56], [.58, .62]], e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 3]] },
    orion: { p: [[.25, .08], [.80, .14], [.38, .50], [.50, .47], [.62, .44], [.30, .92], [.86, .88], [.5, .02]], e: [[0, 1], [0, 2], [1, 4], [2, 3], [3, 4], [2, 5], [4, 6], [0, 7], [1, 7]] },
    cassio: { p: [[0, .70], [.22, .20], [.50, .55], [.78, .15], [1, .60]], e: [[0, 1], [1, 2], [2, 3], [3, 4]] },
    crux: { p: [[.5, .02], [.5, .98], [.12, .45], [.88, .55], [.66, .74]], e: [[0, 1], [2, 3]] },
    scorpio: { p: [[.05, .12], [.18, .22], [.28, .40], [.40, .52], [.52, .66], [.66, .80], [.82, .78], [.95, .60], [.92, .42]], e: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8]] },
    summer: { p: [[.15, .20], [.85, .10], [.55, .90]], e: [[0, 1], [1, 2], [2, 0]] },
    pleiades: { p: [[.2, .3], [.4, .2], [.55, .4], [.35, .55], [.7, .65], [.8, .3]], e: [] },
    kite: { p: [[.5, .0], [.9, .4], [.5, 1], [.1, .4], [.5, .4]], e: [[0, 1], [1, 2], [2, 3], [3, 0], [0, 4], [4, 2]] },
  };
  // where each one lives: [shape, x frac, y frac, size in px, rotation deg]
  const PLACE = [["dipper", .80, .09, 190, -8], ["orion", .965, .50, 150, 8], ["cassio", .50, .035, 150, 0], ["crux", .035, .30, 90, 0], ["scorpio", .06, .86, 190, -12],
    ["summer", .93, .90, 120, 0], ["pleiades", .30, .90, 90, 0], ["kite", .16, .05, 80, 12]];
  function create(cv, opt) {
    opt = opt || {}; const g = cv.getContext("2d"); let W = 0, H = 0, dpr = 1, stars = [], lines = [], mx = -999, my = -999, raf = 0, on = true, last = 0, flash = 0, dead = false;
    const R = 120, acc = opt.accent || "#5b8cff";
    function rgb(c) { c = String(c).trim(); const m = /^#?([0-9a-f]{6})$/i.exec(c); if (m) { const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; } return [91, 140, 255]; }
    let A = rgb(acc), BASE = [225, 232, 255];
    function theme() { const d = document.documentElement.getAttribute("data-theme") || document.documentElement.getAttribute("data-mode") || ""; BASE = /light|snow/.test(d) ? [60, 70, 110] : [225, 232, 255]; try { A = rgb(getComputedStyle(document.documentElement).getPropertyValue("--acc") || acc); } catch (e) { } }
    function layout() {
      W = innerWidth; H = innerHeight; dpr = Math.min(1.5, window.devicePixelRatio || 1); cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); cv.style.width = W + "px"; cv.style.height = H + "px";
      stars = []; lines = []; let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      PLACE.forEach(([k, fx, fy, sz, rot]) => {
        const s = SHAPES[k], base = stars.length, c = Math.cos(rot * Math.PI / 180), sn = Math.sin(rot * Math.PI / 180), size = sz * Math.min(1, W / 1300 + .25);
        s.p.forEach(([u, v]) => { const dx = (u - .5) * size, dy = (v - .5) * size * .8; const x = fx * W + dx * c - dy * sn, y = fy * H + dx * sn + dy * c; stars.push({ hx: x, hy: y, x, y, vx: 0, vy: 0, b: 0, ph: rnd() * 6.28, r: 1.3 + rnd() * 1.3, big: rnd() > .7 }); });
        s.e.forEach(([a, b]) => lines.push([base + a, base + b]));
      });
      for (let i = 0; i < 46; i++) stars.push({ hx: rnd() * W, hy: rnd() * H, x: 0, y: 0, vx: 0, vy: 0, b: 0, ph: rnd() * 6.28, r: .6 + rnd() * .8, dust: true }), stars[stars.length - 1].x = stars[stars.length - 1].hx, stars[stars.length - 1].y = stars[stars.length - 1].hy;
    }
    const col = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
    function frame(now) {
      raf = 0; if (dead || !on || document.hidden) return; raf = requestAnimationFrame(frame);
      if (now - last < 33) return; const dt = Math.min(.05, (now - last) / 1000); last = now; const t = now / 1000;
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H); flash = Math.max(0, flash - dt * 1.4);
      for (const s of stars) {                                        // spring back to the home place; the pointer pulls a star toward itself and lights it
        const dx = mx - s.x, dy = my - s.y, d = Math.hypot(dx, dy), near = d < R ? 1 - d / R : 0;
        const tx = s.hx + (near ? dx * .18 * near : 0), ty = s.hy + (near ? dy * .18 * near : 0);
        s.vx = (s.vx + (tx - s.x) * 14 * dt) * .86; s.vy = (s.vy + (ty - s.y) * 14 * dt) * .86; s.x += s.vx; s.y += s.vy;
        s.b += ((near > 0 ? near : 0) - s.b) * Math.min(1, dt * 9); s.tw = .55 + .45 * Math.sin(t * 1.3 + s.ph);
      }
      g.lineWidth = 1;
      for (const [a, b] of lines) { const p = stars[a], q = stars[b], lit = Math.max(p.b, q.b); g.strokeStyle = lit > .02 ? col(A, .12 + lit * .6) : col(BASE, .07 + flash * .3); g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(q.x, q.y); g.stroke(); }
      for (const s of stars) {
        const lit = s.b, r = s.r * (1 + lit * 1.6 + flash), al = (s.dust ? .22 : .38) * (s.tw || 1) + lit * .6 + flash * .4;
        if (lit > .05 || s.big) { const gr = g.createRadialGradient(s.x, s.y, 0, s.x, s.y, r * 6); gr.addColorStop(0, col(lit > .05 ? A : BASE, Math.min(.5, .12 + lit * .45))); gr.addColorStop(1, col(A, 0)); g.fillStyle = gr; g.beginPath(); g.arc(s.x, s.y, r * 6, 0, 6.283); g.fill(); }
        g.fillStyle = col(lit > .05 ? A : BASE, Math.min(1, al)); g.beginPath(); g.arc(s.x, s.y, r, 0, 6.283); g.fill();
      }
      if (mx > -500) {                                                // lines from the pointer to the stars it wakes: it draws its own little asterism
        const lit = stars.filter((s) => s.b > .18).sort((u, v) => v.b - u.b).slice(0, 4);
        g.lineWidth = .8; lit.forEach((s) => { g.strokeStyle = col(A, s.b * .55); g.beginPath(); g.moveTo(mx, my); g.lineTo(s.x, s.y); g.stroke(); });
      }
    }
    function kick() { if (!raf && on && !dead) raf = requestAnimationFrame(frame); }
    const onResize = () => { layout(); };
    window.addEventListener("resize", onResize); theme(); layout(); kick();
    document.addEventListener("visibilitychange", kick);
    return {
      move(x, y) { mx = x; my = y; kick(); },
      active(v) { on = !!v || on; kick(); },
      pulse() { flash = 1; kick(); },
      theme,
      dispose() { dead = true; if (raf) cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); document.removeEventListener("visibilitychange", kick); },
    };
  }
  window.STARS = { create };
})();
