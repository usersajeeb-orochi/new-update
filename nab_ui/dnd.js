// dnd.js - smooth drag-to-reorder for the layer list (pointer based: the row follows the finger/mouse, the others slide out of the way).
(function () {
  const box = document.getElementById("layers");
  if (!box) return;
  const REDUCE = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let g = null;

  box.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button,input")) return;
    const row = e.target.closest(".ly"); if (!row) return;
    g = { row, id: +row.dataset.id, y0: e.clientY, started: false, pid: e.pointerId };
  });
  window.addEventListener("pointermove", (e) => {
    if (!g || e.pointerId !== g.pid) return;
    if (!g.started) {
      if (Math.abs(e.clientY - g.y0) < 5) return;
      begin(); if (!g) return;
    }
    const dy = e.clientY - g.y0 + (box.scrollTop - g.scroll0);
    g.dy = dy; g.row.style.transform = `translateY(${dy}px) scale(1.02)`;
    // new slot = where the dragged row's centre sits among the other rows' original centres
    const c = g.mid + dy; let slot = 0; g.others.forEach(o => { if (c > o.mid) slot++; });
    if (slot !== g.slot) { g.slot = slot; shift(); }
    const r = box.getBoundingClientRect();                                   // auto-scroll near the edges
    g.auto = e.clientY < r.top + 24 ? -8 : e.clientY > r.bottom - 24 ? 8 : 0;
    if (g.auto && !g.raf) g.raf = requestAnimationFrame(tick);
  });
  function tick() { if (!g) return; g.raf = 0; if (g.auto) { box.scrollTop += g.auto; g.raf = requestAnimationFrame(tick); } }
  function begin() {
    const rows = Array.from(box.querySelectorAll(".ly")); if (rows.length < 2) { g = null; return; }
    g.started = true; g.scroll0 = box.scrollTop; g.from = rows.indexOf(g.row);
    const rects = rows.map(r => r.getBoundingClientRect()), h = rects[g.from].height, gap = rows.length > 1 ? Math.max(0, rects[1].top - rects[0].bottom) : 0;
    g.step = h + gap; g.mid = rects[g.from].top + h / 2;
    g.others = rows.map((r, i) => ({ r, i, mid: rects[i].top + rects[i].height / 2 })).filter(o => o.i !== g.from);
    g.slot = g.from; g.rows = rows;
    box.classList.add("dragging"); g.row.classList.add("lifted"); document.body.style.userSelect = "none";
    g.others.forEach(o => { o.r.style.transition = REDUCE ? "none" : "transform .16s cubic-bezier(.2,.8,.2,1)"; });
  }
  function shift() {
    // final order = the others with the dragged row inserted at g.slot; each other row moves by (final position - original position) steps
    g.others.forEach((o, k) => { const fin = k < g.slot ? k : k + 1, off = (fin - o.i) * g.step; o.r.style.transform = off ? `translateY(${off}px)` : ""; });
  }
  function end(commit) {
    if (!g) return; const s = g; g = null;
    cancelAnimationFrame(s.raf); document.body.style.userSelect = "";
    if (!s.started) return;
    const clean = () => { box.classList.remove("dragging"); s.rows.forEach(r => { r.style.transform = ""; r.style.transition = ""; r.classList.remove("lifted"); }); };
    if (!commit || s.slot === s.from) { s.row.style.transition = REDUCE ? "none" : "transform .15s ease"; s.row.style.transform = ""; setTimeout(clean, 170); return; }
    // settle the dragged row into its slot, then tell the engine (the list re-renders from the new order)
    const target = (s.slot - s.from) * s.step; s.row.style.transition = REDUCE ? "none" : "transform .14s ease"; s.row.style.transform = `translateY(${target}px)`;
    setTimeout(() => { clean(); if (window.CLIPUI && CLIPUI.layerMove) CLIPUI.layerMove(s.id, s.slot); }, REDUCE ? 0 : 150);
  }
  window.addEventListener("pointerup", (e) => { if (g && e.pointerId === g.pid) end(true); });
  window.addEventListener("pointercancel", () => end(false));
  window.addEventListener("keydown", (e) => { if (e.key === "Escape" && g) end(false); });
})();
