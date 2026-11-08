// clip.js — the Clip screen: canvas viewer, selection/edit tools, layers,
// category bar, one-line metadata, saving.
(function () {
  const { $, $$, esc, api, url, on, catColor, parseMeta, toast, debounce, modal } = C;
  const S = {
    st: null,                 // engine state
    armed: [],                // categories chosen for the next save
    tool: "marquee",
    sel: null,                // {layer, shape} in LAYER pixels
    active: 0,                // active layer id
    layers: [], rev: -1,
    P: null,                  // current preview {w,h,k,layout,header_h,...}
    V: { z: 1, cx: .5, cy: .5 },
    sw: 0, sh: 0, tx: 0, ty: 0,
    drag: null, space: false, suggest: null, _autoCrop: new Set(),
    brush: 26, textColor: "#d32f2f",
    pendingFetch: 0,
  };
  window.CLIP = S;
  const stage = $("#stage"), pageEl = $("#page"), wrap = $("#pageWrap"), ov = $("#ov"), ctx = ov.getContext("2d");
  const F = { page: $("#mPage") }, FORDER = ["page", "cols", "size"];
  F.cols = C.pairField($("#mC1"), $("#mC2"), "-", $("#mColsW"), { esc: metaEsc, change() { S.touched.cols = false; autoWidth(); updateDock(); refreshMetaSoon(); sendDraft(); }, done() { autoWidth(); if (F.size.a.value) { F.size.b.focus(); F.size.b.select(); } else focusMeta("size"); }, enter() { metaEnter("cols"); }, prev() { focusMeta("page"); }, esc() { metaEsc(); }, leave() { S.touched.cols = true; updateDock(); } });
  F.size = C.pairField($("#mS1"), $("#mS2"), "x", $("#mSizeW"), { esc: metaEsc, change() { S.touched.size = false; updateDock(); sendDraft(); }, b2: true, done() { }, enter() { metaEnter("size"); }, prev() { F.cols.b.focus(); F.cols.b.select(); }, esc() { metaEsc(); }, leave() { S.touched.size = true; updateDock(); } });
  // the position (columns a-b) is the width of the clip: 1-3 = 3 columns, 2-6 = 5, 4-8 = 5 -> first size field is filled for you
  function autoWidth() { const a = +F.cols.a.value, b = +F.cols.b.value; if (a >= 1 && b >= a && b <= 9) { const w = String(b - a + 1); if (F.size.a.value !== w) F.size.a.value = w; } }
  const metaLine = () => FORDER.map(k => F[k].value.trim()).filter(Boolean).join(" ");
  const dpr = () => window.devicePixelRatio || 1;

  // ───────────────────────── geometry ─────────────────────────
  function measure() {
    const r = stage.getBoundingClientRect(); S.sw = r.width; S.sh = r.height;
    ov.width = Math.round(r.width * dpr()); ov.height = Math.round(r.height * dpr());
  }
  function fitScale() { const P = S.P; if (!P) return 1; return Math.max(0.01, Math.min((S.sw - 32) / P.w, (S.sh - 32) / P.h)); }
  function scale() { return fitScale() * S.V.z; }
  function applyView() {
    const P = S.P; if (!P) return;
    const s = scale(); S.tx = S.sw / 2 - S.V.cx * P.w * s; S.ty = S.sh / 2 - S.V.cy * P.h * s;
    wrap.style.transform = "translate(" + S.tx + "px," + S.ty + "px) scale(" + s + ")";
    $("#zoomTxt").textContent = Math.round(s * P.k * 100) + "%";
    drawOv();
  }
  const toPrev = (x, y) => { const s = scale(); return [(x - S.tx) / s, (y - S.ty) / s]; };
  const toView = (px, py) => { const s = scale(); return [px * s + S.tx, py * s + S.ty]; };
  function itemFor(id) { return S.P && S.P.layout.find(i => i.id === id); }
  function hitLayer(x, y) {
    if (!S.P) return null; const [px, py] = toPrev(x, y);
    const L = S.P.layout; let best = null, bd = 1e12;
    for (let i = L.length - 1; i >= 0; i--) { const it = L[i]; if (px >= it.x && px <= it.x + it.w && py >= it.y && py <= it.y + it.h) return it; }
    for (const it of L) { const dx = Math.max(it.x - px, 0, px - (it.x + it.w)), dy = Math.max(it.y - py, 0, py - (it.y + it.h)), d = dx * dx + dy * dy; if (d < bd) { bd = d; best = it; } }
    return best;
  }
  // view point -> layer pixel (clamped to the layer)
  function toLayer(it, x, y) {
    const [px, py] = toPrev(x, y);
    const lx = Math.max(0, Math.min(it.w, px - it.x)) * it.sx, ly = Math.max(0, Math.min(it.h, py - it.y)) * it.sy;
    return [lx, ly];
  }
  function fromLayer(it, lx, ly) { return toView(it.x + lx / it.sx, it.y + ly / it.sy); }

  // ───────────────────────── preview ─────────────────────────
  function metaForHeader() {
    return { page: C.normField("page", F.page.value), cols: F.cols.value.trim() };
  }
  async function refresh(force) {
    const id = ++S.pendingFetch;
    const P = S.P, fitH = P ? P.h * fitScale() : S.sh - 32;
    const need = Math.max(500, Math.min(4200, Math.round(fitH * S.V.z * dpr())));
    const h = metaForHeader();
    let r;
    try { r = await api("preview", { h: need, page: h.page, cols: h.cols, header: S.st ? S.st.settings.show_header : true, force: !!force }); } catch (e) { return; }
    if (id !== S.pendingFetch) return;
    $("#empty").classList.toggle("hidden", !r.empty);
    if (r.empty) { S.P = null; pageEl.removeAttribute("src"); wrap.style.display = "none"; drawOv(); return; }
    const im = new Image();
    im.onload = () => {
      if (id !== S.pendingFetch) return;
      const first = !S.P, aspectChanged = S.P && Math.abs(S.P.w / S.P.h - r.w / r.h) > 0.02;
      const layerCountChanged = !S.P || S.P.layout.length !== r.layout.length;
      S.P = r; pageEl.src = im.src; pageEl.width = r.w; pageEl.height = r.h; wrap.style.display = "";
      if (first || layerCountChanged) S.V = { z: 1, cx: .5, cy: .5 };
      else if (aspectChanged) S.V = { z: 1, cx: .5, cy: .5 };
      applyView(); renderLayers();
      if (first || layerCountChanged) { pageEl.classList.remove("arrive"); void pageEl.offsetWidth; pageEl.classList.add("arrive"); }
    };
    im.src = url(r.img);
  }
  const refreshSoon = debounce(refresh, 130);
  const refreshMetaSoon = debounce(refresh, 380);   // typing in Page / Position only changes the header line — no need to re-render on every key
  const hiresSoon = debounce(() => { if (S.P) { const need = S.P.h * fitScale() * S.V.z * dpr(); if (need > S.P.h * 1.15 || need < S.P.h * 0.6) refresh(); } }, 280);

  async function onClips() {
    const r = await api("layers");
    S.layers = r.layers; S.rev = r.rev; S.free = r.free; S.canvas = r.canvas; $("#undoBtn").disabled = !r.undo; $("#redoBtn").disabled = !r.redo;
    if (!S.layers.find(l => l.id === S.active)) S.active = S.layers.length ? S.layers[S.layers.length - 1].id : 0;
    if (S.sel && !S.layers.find(l => l.id === S.sel.layer)) S.sel = null;
    updateSizePanel();
    $("#stClips").textContent = S.layers.length + " " + t("clips");
    await refresh(); inchSoon();
    S.suggest = null; drawOv(); $("#suggest").classList.add("hidden");
    if (S.layers.length === 1) { const s = await api("suggest_crop"); if (s.rect && s.layer === S.layers[0].id) { S.suggest = { layer: s.layer, rect: s.rect }; $("#suggest").classList.remove("hidden"); drawOv();
      if (S._autoBusy) { S.layers.forEach(l => S._autoCrop.add(l.id)); }
      else if (!(S.st && S.st.settings && S.st.settings.auto_crop_apply === false) && !S._autoCrop.has(s.layer)) {
        S._autoCrop.add(s.layer); S._autoBusy = true;
        try { await applySuggest(); } finally { S._autoBusy = false; }
        S.layers.forEach(l => S._autoCrop.add(l.id)); if (S._autoCrop.size > 300) S._autoCrop.clear(); return; } } }
    updateDock();
  }

  // ───────────────────────── overlay drawing ─────────────────────────
  function pathShape(c, it, sh) {
    if (sh.type === "not") { pathShape(c, it, sh.inner); const [ia, ib] = fromLayer(it, 0, 0), [ic, id] = fromLayer(it, it.w * it.sx, it.h * it.sy); c.rect(ia, ib, ic - ia, id - ib); return; }
    c.beginPath();
    if (sh.type === "rect" || sh.type === "ellipse") {
      const [a, b] = fromLayer(it, Math.min(sh.x1, sh.x2), Math.min(sh.y1, sh.y2)), [d, e] = fromLayer(it, Math.max(sh.x1, sh.x2), Math.max(sh.y1, sh.y2));
      if (sh.type === "rect") c.rect(a, b, d - a, e - b); else c.ellipse((a + d) / 2, (b + e) / 2, Math.abs(d - a) / 2, Math.abs(e - b) / 2, 0, 0, Math.PI * 2);
    } else if (sh.type === "poly") {
      sh.points.forEach((p, i) => { const [x, y] = fromLayer(it, p[0], p[1]); if (i) c.lineTo(x, y); else c.moveTo(x, y); }); c.closePath();
    }
  }
  function strokeShape(it, sh) {
    pathShape(ctx, it, sh);
    ctx.lineWidth = 3; ctx.strokeStyle = "#000"; ctx.setLineDash([]); ctx.stroke();
    ctx.lineWidth = 1.5; ctx.strokeStyle = "#fff"; ctx.setLineDash([6, 5]); ctx.stroke(); ctx.setLineDash([]);
  }
  function bboxOf(sh) {
    if (sh.type === "not") return bboxOf(sh.inner);
    if (sh.type === "poly") { const xs = sh.points.map(p => p[0]), ys = sh.points.map(p => p[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; }
    return [Math.min(sh.x1, sh.x2), Math.min(sh.y1, sh.y2), Math.max(sh.x1, sh.x2), Math.max(sh.y1, sh.y2)];
  }
  function drawOv() {
    const d = dpr(); ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, S.sw, S.sh);
    if (!S.P) return;
    // suggestion
    if (S.suggest && !S.sel) {
      const it = itemFor(S.suggest.layer);
      if (it) {
        const [x1, y1, x2, y2] = S.suggest.rect, [a, b] = fromLayer(it, x1, y1), [c2, e] = fromLayer(it, x2, y2);
        ctx.fillStyle = "rgba(0,0,0,.35)";
        const [ia, ib] = fromLayer(it, 0, 0), [ic, id] = fromLayer(it, it.w * it.sx, it.h * it.sy);
        ctx.beginPath(); ctx.rect(ia, ib, ic - ia, id - ib); ctx.rect(a, b, c2 - a, e - b); ctx.fill("evenodd");
        ctx.lineWidth = 2; ctx.strokeStyle = "#2f8cff"; ctx.setLineDash([8, 5]); ctx.strokeRect(a, b, c2 - a, e - b); ctx.setLineDash([]);
        ctx.fillStyle = "#2f8cff"; [[a, b], [c2, b], [a, e], [c2, e], [(a + c2) / 2, b], [(a + c2) / 2, e], [a, (b + e) / 2], [c2, (b + e) / 2]].forEach(p => ctx.fillRect(p[0] - 4, p[1] - 4, 8, 8));
      }
    }
    const dr = S.drag;
    // layer move / resize (Move tool, no selection)
    if (S.tool === "move" && !S.sel) {
      const it = itemFor(S.active) || (S.P.layout.length ? S.P.layout[S.P.layout.length - 1] : null);
      if (it) {
        let r = { x: it.x, y: it.y, w: it.w, h: it.h };
        if (dr && (dr.kind === "lmove" || dr.kind === "lsize")) {
          r = dr.r;
          ctx.fillStyle = "rgba(255,255,255,.65)"; const [ox, oy] = toView(it.x, it.y); ctx.fillRect(ox, oy, it.w * scale(), it.h * scale());
          const [vx, vy] = toView(r.x, r.y); ctx.globalAlpha = .92; ctx.drawImage(pageEl, it.x, it.y, it.w, it.h, vx, vy, r.w * scale(), r.h * scale()); ctx.globalAlpha = 1;
        }
        const [vx, vy] = toView(r.x, r.y), vw = r.w * scale(), vh = r.h * scale();
        ctx.lineWidth = 1.5; ctx.strokeStyle = "#2f8cff"; ctx.setLineDash([]); ctx.strokeRect(vx, vy, vw, vh);
        ctx.fillStyle = "#fff"; ctx.strokeStyle = "#2f8cff";
        lhandles(vx, vy, vw, vh).forEach(h => { ctx.fillRect(h.x - 4, h.y - 4, 8, 8); ctx.strokeRect(h.x - 4, h.y - 4, 8, 8); });
        if (dr && dr.kind === "lsize") { ctx.fillStyle = "#2f8cff"; ctx.font = "600 12px system-ui"; ctx.fillText(Math.round(r.w * it.sx) + " × " + Math.round(r.h * it.sy), vx + 6, vy + vh + 16); }
      }
    }
    // selection (+ floating move preview)
    if (S.sel) {
      const it = itemFor(S.sel.layer); if (it) {
        if (dr && dr.kind === "move") {
          ctx.save();
          const bb = bboxOf(S.sel.shape), [cx, cy] = fromLayer(it, (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2);
          const sc = dr.scale || 1, s = scale() / (it.sx), k = 1;
          const dxv = dr.dx * (scale() / it.sx), dyv = dr.dy * (scale() / it.sy);
          ctx.translate(cx + dxv, cy + dyv); ctx.scale(sc, sc); ctx.translate(-cx, -cy);
          pathShape(ctx, it, S.sel.shape); ctx.clip();
          ctx.drawImage(pageEl, S.tx, S.ty, S.P.w * scale(), S.P.h * scale());
          ctx.restore();
          ctx.save(); ctx.translate(cx + dxv, cy + dyv); ctx.scale(sc, sc); ctx.translate(-cx, -cy); strokeShape(it, S.sel.shape); ctx.restore();
        } else strokeShape(it, S.sel.shape);
        if (S.tool === "move") {
          const bb = bboxOf(S.sel.shape), pts = [[bb[0], bb[1]], [bb[2], bb[1]], [bb[0], bb[3]], [bb[2], bb[3]]];
          ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = 1;
          pts.forEach(p => { const [x, y] = fromLayer(it, p[0], p[1]); ctx.fillRect(x - 4, y - 4, 8, 8); ctx.strokeRect(x - 4, y - 4, 8, 8); });
        }
      }
    }
    if (dr && dr.kind === "draw" && dr.shape) { const it = itemFor(dr.layer); if (it) strokeShape(it, dr.shape); }
    if (dr && dr.kind === "brush") {
      ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = dr.clone ? "rgba(80,160,255,.5)" : "rgba(255,80,80,.55)"; ctx.lineWidth = S.brush; ctx.beginPath();
      dr.view.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke();
    }
  }

  function lhandles(x, y, w, h) {
    return [{ k: "nw", x, y }, { k: "n", x: x + w / 2, y }, { k: "ne", x: x + w, y }, { k: "e", x: x + w, y: y + h / 2 },
      { k: "se", x: x + w, y: y + h }, { k: "s", x: x + w / 2, y: y + h }, { k: "sw", x, y: y + h }, { k: "w", x, y: y + h / 2 }];
  }
  function lhandleHit(x, y) {
    if (S.tool !== "move" || S.sel) return null; const it = itemFor(S.active); if (!it) return null;
    const [vx, vy] = toView(it.x, it.y);
    for (const h of lhandles(vx, vy, it.w * scale(), it.h * scale())) if (Math.abs(h.x - x) < 9 && Math.abs(h.y - y) < 9) return { k: h.k, it };
    return null;
  }
  function newRect(d, px, py, shift) {
    const o = d.it, r = { x: o.x, y: o.y, w: o.w, h: o.h }, k = d.h;
    let x1 = o.x, y1 = o.y, x2 = o.x + o.w, y2 = o.y + o.h;
    if (k.includes("w")) x1 = Math.min(px, x2 - 8); if (k.includes("e")) x2 = Math.max(px, x1 + 8);
    if (k.includes("n")) y1 = Math.min(py, y2 - 8); if (k.includes("s")) y2 = Math.max(py, y1 + 8);
    if (k.length === 2 && !shift) {   // corners keep the proportions (Shift = free)
      const ar = o.w / o.h; let w = x2 - x1, h = y2 - y1;
      if (w / h > ar) w = h * ar; else h = w / ar;
      if (k.includes("w")) x1 = x2 - w; else x2 = x1 + w; if (k.includes("n")) y1 = y2 - h; else y2 = y1 + h;
    }
    r.x = x1; r.y = y1; r.w = x2 - x1; r.h = y2 - y1; return r;
  }
  // ───────────────────────── tools / pointer ─────────────────────────
  function setTool(t) {
    S.tool = t; $$("#toolbar .tb[data-tool]").forEach(b => b.classList.toggle("active", b.dataset.tool === t));
    stage.className = "stage t-" + t + (S.space ? " pan" : ""); drawOv(); commitText();
  }
  function evPos(e) { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  function inSel(x, y) {
    if (!S.sel) return false; const it = itemFor(S.sel.layer); if (!it) return false;
    const [lx, ly] = toLayer(it, x, y), bb = bboxOf(S.sel.shape); return lx >= bb[0] && lx <= bb[2] && ly >= bb[1] && ly <= bb[3];
  }
  function cornerHit(x, y) {
    if (!S.sel) return null; const it = itemFor(S.sel.layer); if (!it) return null; const bb = bboxOf(S.sel.shape);
    for (const p of [[bb[0], bb[1]], [bb[2], bb[1]], [bb[0], bb[3]], [bb[2], bb[3]]]) { const [vx, vy] = fromLayer(it, p[0], p[1]); if (Math.abs(vx - x) < 9 && Math.abs(vy - y) < 9) return true; }
    return false;
  }
  function suggestHandle(x, y) {
    if (!S.suggest || S.sel) return null; const it = itemFor(S.suggest.layer); if (!it) return null;
    const [x1, y1, x2, y2] = S.suggest.rect, [a, b] = fromLayer(it, x1, y1), [c, d] = fromLayer(it, x2, y2);
    const near = (u, v, px, py) => Math.abs(u - px) < 9 && Math.abs(v - py) < 9;
    const H = { nw: [a, b], ne: [c, b], sw: [a, d], se: [c, d], n: [(a + c) / 2, b], s: [(a + c) / 2, d], w: [a, (b + d) / 2], e: [c, (b + d) / 2] };
    for (const k in H) if (near(x, y, H[k][0], H[k][1])) return k; return null;
  }

  stage.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".suggest,.card-float,.textbox")) return;
    stage.focus(); const [x, y] = evPos(e);
    if (e.button === 1 || S.space) { S.drag = { kind: "pan", x, y, cx: S.V.cx, cy: S.V.cy }; stage.setPointerCapture(e.pointerId); e.preventDefault(); return; }
    if (e.button !== 0 || !S.P) return;
    stage.setPointerCapture(e.pointerId);
    const sh = suggestHandle(x, y);
    if (sh) { S.drag = { kind: "sugg", h: sh }; return; }
    const it = hitLayer(x, y); if (!it) return;
    if (S.tool === "text") { startText(it, x, y); return; }
    if (S.tool === "move" && S.sel) {
      const its = itemFor(S.sel.layer), bb = bboxOf(S.sel.shape);
      if (cornerHit(x, y)) { const [cx, cy] = fromLayer(its, (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2); S.drag = { kind: "move", mode: "scale", x, y, cx, cy, d0: Math.hypot(x - cx, y - cy), dx: 0, dy: 0, scale: 1, copy: e.altKey }; return; }
      if (inSel(x, y)) { S.drag = { kind: "move", mode: "drag", x, y, dx: 0, dy: 0, scale: 1, copy: e.altKey }; return; }
    }
    if (S.tool === "move" && !S.sel) {
      const lh = lhandleHit(x, y);
      if (lh) { S.drag = { kind: "lsize", h: lh.k, it: lh.it, r: { x: lh.it.x, y: lh.it.y, w: lh.it.w, h: lh.it.h }, shift: e.shiftKey }; return; }
      S.active = it.id; renderLayers();
      S.drag = { kind: "lmove", it, x, y, r: { x: it.x, y: it.y, w: it.w, h: it.h } }; drawOv(); return;
    }
    S.active = it.id; renderLayers();
    if (S.tool === "wand") { const [wx, wy] = toLayer(it, x, y); api("wand", { layer: it.id, x: wx, y: wy, tol: e.shiftKey ? 60 : 28 }).then(r => { if (r.ok) { S.sel = { layer: r.layer, shape: r.shape }; drawOv(); } else toast(r.error || "Nothing selected", "warn", 1600); }); return; }
    if (S.tool === "clone") {
      const [lx, ly] = toLayer(it, x, y);
      if (e.altKey) { S.cloneSrc = { layer: it.id, x: lx, y: ly }; toast("Source set — now paint where you want to copy to", "", 1800); return; }
      if (!S.cloneSrc || S.cloneSrc.layer !== it.id) { toast("Alt+click first to pick the spot to copy FROM", "warn", 2500); return; }
      S.drag = { kind: "brush", clone: { dx: S.cloneSrc.x - lx, dy: S.cloneSrc.y - ly }, layer: it.id, view: [[x, y]], pts: [[lx, ly]], it }; return;
    }
    if (S.tool === "brush") { const [lx, ly] = toLayer(it, x, y); S.drag = { kind: "brush", layer: it.id, view: [[x, y]], pts: [[lx, ly]], it }; return; }
    S.sel = null;
    const [lx, ly] = toLayer(it, x, y);
    if (S.tool === "lasso") S.drag = { kind: "draw", layer: it.id, shape: { type: "poly", points: [[lx, ly]] }, it };
    else S.drag = { kind: "draw", layer: it.id, start: [lx, ly], shape: { type: S.tool === "ellipse" ? "ellipse" : "rect", x1: lx, y1: ly, x2: lx, y2: ly }, it };
    drawOv();
  });
  stage.addEventListener("pointermove", (e) => {
    const [x, y] = evPos(e), d = S.drag;
    if (!d) {
      const lh = lhandleHit(x, y);
      if (lh) { stage.style.cursor = ({ nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize", n: "ns-resize", s: "ns-resize", w: "ew-resize", e: "ew-resize" })[lh.k]; return; }
      const h = suggestHandle(x, y);
      stage.style.cursor = h ? ({ nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize", n: "ns-resize", s: "ns-resize", w: "ew-resize", e: "ew-resize" })[h] : "";
      return;
    }
    if (d.kind === "lmove") { const s = scale(); d.r = { x: d.it.x + (x - d.x) / s, y: d.it.y + (y - d.y) / s, w: d.it.w, h: d.it.h }; drawOv(); return; }
    if (d.kind === "lsize") { const [px, py] = toPrev(x, y); d.r = newRect(d, px, py, e.shiftKey); drawOv(); return; }
    if (d.kind === "pan") { const s = scale(); S.V.cx = d.cx - (x - d.x) / (S.P.w * s); S.V.cy = d.cy - (y - d.y) / (S.P.h * s); applyView(); return; }
    if (d.kind === "sugg") { const it = itemFor(S.suggest.layer), [lx, ly] = toLayer(it, x, y), r = S.suggest.rect; if (d.h.includes("w")) r[0] = Math.min(lx, r[2] - 20); if (d.h.includes("e")) r[2] = Math.max(lx, r[0] + 20); if (d.h.includes("n")) r[1] = Math.min(ly, r[3] - 20); if (d.h.includes("s")) r[3] = Math.max(ly, r[1] + 20); drawOv(); return; }
    if (d.kind === "draw") {
      const [lx, ly] = toLayer(d.it, x, y);
      if (d.shape.type === "poly") d.shape.points.push([lx, ly]); else { d.shape.x2 = lx; d.shape.y2 = ly; if (e.shiftKey && d.shape.type === "rect") { const w = d.shape.x2 - d.shape.x1; d.shape.y2 = d.shape.y1 + Math.sign(d.shape.y2 - d.shape.y1 || 1) * Math.abs(w); } }
      drawOv(); return;
    }
    if (d.kind === "brush") { const [lx, ly] = toLayer(d.it, x, y); d.view.push([x, y]); d.pts.push([lx, ly]); drawOv(); return; }
    if (d.kind === "move") {
      const it = itemFor(S.sel.layer), k = scale();
      if (d.mode === "drag") { d.dx = (x - d.x) / k * it.sx; d.dy = (y - d.y) / k * it.sy; }
      else { d.scale = Math.max(0.1, Math.min(8, Math.hypot(x - d.cx, y - d.cy) / (d.d0 || 1))); }
      drawOv();
    }
  });
  stage.addEventListener("pointerup", async (e) => {
    const d = S.drag; S.drag = null; if (!d) return;
    if (d.kind === "pan" || d.kind === "sugg") { drawOv(); hiresSoon(); return; }
    if (d.kind === "lmove") {
      const dx = (d.r.x - d.it.x) * d.it.sx, dy = (d.r.y - d.it.y) * d.it.sy;
      if (Math.abs(dx) < 2 && Math.abs(dy) < 2) { drawOv(); return; }
      await layerCmdFor(d.it.id, "move", { dx, dy }); return;
    }
    if (d.kind === "lsize") {
      const it = d.it, w = d.r.w * it.sx, h = d.r.h * it.sy, dx = (d.r.x - it.x) * it.sx, dy = (d.r.y - it.y) * it.sy;
      if (Math.abs(w - it.w * it.sx) < 2 && Math.abs(h - it.h * it.sy) < 2 && Math.abs(dx) < 2 && Math.abs(dy) < 2) { drawOv(); return; }
      const r = await api("layer", { cmd: "resize", layer: it.id, w, h, dx, dy }); if (r.ok) onClips(); else { toast(r.error || "Can't resize", "warn", 1600); drawOv(); } return;
    }
    if (d.kind === "draw") {
      const sh = d.shape; let tiny = false;
      if (sh.type === "poly") tiny = sh.points.length < 3; else tiny = Math.abs(sh.x2 - sh.x1) < 4 && Math.abs(sh.y2 - sh.y1) < 4;
      S.sel = tiny ? null : { layer: d.layer, shape: sh }; drawOv(); return;
    }
    if (d.kind === "brush") { if (d.pts.length) await doEdit(d.clone ? "clone" : "erase", { layer: d.layer, ...(d.clone || {}), shape: { type: "stroke", points: d.pts, width: S.brush / scale() * d.it.sx } }); return; }
    if (d.kind === "move") {
      if (Math.abs(d.dx) < 1 && Math.abs(d.dy) < 1 && Math.abs(d.scale - 1) < 0.01) { drawOv(); return; }
      const sel = S.sel; S.sel = null;
      await doEdit("move", { layer: sel.layer, shape: sel.shape, dx: d.dx, dy: d.dy, scale: d.scale, cut: !d.copy });
    }
  });
  stage.addEventListener("wheel", (e) => {
    e.preventDefault(); if (!S.P) return;
    const [x, y] = evPos(e), f = e.deltaY < 0 ? 1.15 : 1 / 1.15, nz = Math.max(0.2, Math.min(12, S.V.z * f));
    const s0 = scale(), px = (x - S.tx) / s0, py = (y - S.ty) / s0; S.V.z = nz; const s1 = scale();
    S.V.cx = (px - (x - S.sw / 2) / s1) / S.P.w; S.V.cy = (py - (y - S.sh / 2) / s1) / S.P.h; applyView(); hiresSoon();
  }, { passive: false });
  stage.addEventListener("dblclick", () => { S.V = { z: 1, cx: .5, cy: .5 }; applyView(); hiresSoon(); });
  window.addEventListener("resize", debounce(() => { measure(); applyView(); hiresSoon(); }, 100));

  // ───────────────────────── edits ─────────────────────────
  async function doEdit(op, o) {
    const r = await api("edit", Object.assign({ op }, o));
    if (!r.ok) { if (r.error) toast(r.error, "warn", 2200); drawOv(); return r; }
    S.sel = null; S.suggest = null; $("#suggest").classList.add("hidden");
    if (r.new_layer) S.active = r.new_layer;
    await onClips(); return r;
  }
  function needSel() { if (!S.sel) { toast("Make a selection first (M, drag)", "warn", 1800); return false; } return true; }
  async function applyAct(act) {
    if (act === "crop" && !S.sel && S.suggest) return applySuggest();
    if (!needSel()) return;
    const o = { layer: S.sel.layer, shape: S.sel.shape };
    if (act === "highlight") { o.color = [255, 235, 59]; o.alpha = 100; }
    return doEdit(act, o);
  }
  async function applySuggest() {
    if (!S.suggest) return; const [x1, y1, x2, y2] = S.suggest.rect; const l = S.suggest.layer;
    return doEdit("crop", { layer: l, shape: { type: "rect", x1, y1, x2, y2 } });
  }
  async function filter(name, extra) { const r = await api("filter", Object.assign({ name, layer: undefined }, extra || {})); if (r.ok) onClips(); else toast(r.error || "Nothing to edit", "warn", 1800); }
  async function layerCmd(cmd, extra) { const r = await api("layer", Object.assign({ cmd, layer: S.active }, extra || {})); if (r.ok) { if (r.new_layer) S.active = r.new_layer; S.sel = null; onClips(); } else if (r.error) toast(r.error, "warn", 1800); return r; }
  async function paste() { const r = await api("paste"); if (!r.ok) toast("Clipboard has no image", "warn", 1600); }
  function selectAll() { const it = itemFor(S.active) || (S.P && S.P.layout[S.P.layout.length - 1]); if (!it) return; S.sel = { layer: it.id, shape: { type: "rect", x1: 0, y1: 0, x2: it.w * it.sx, y2: it.h * it.sy } }; drawOv(); }
  function deselect() { S.sel = null; drawOv(); }

  // ── text tool (browser renders the text → shaped Bangla works) ──
  let tctx = null;
  function startText(it, x, y) {
    commitText(); const box = $("#textBox"), inp = $("#textInput"); tctx = { it, x, y };
    box.style.left = x + "px"; box.style.top = y + "px"; box.classList.remove("hidden"); inp.value = ""; setTimeout(() => inp.focus(), 0);
  }
  async function commitText() {
    const box = $("#textBox"), inp = $("#textInput"); if (!tctx || box.classList.contains("hidden")) return;
    const txt = inp.value.trim(), c = tctx; tctx = null; box.classList.add("hidden"); if (!txt) return;
    const fpx = Math.max(16, Math.round(c.it.w * c.it.sx * 0.035)), cv = document.createElement("canvas"), g = cv.getContext("2d");
    const font = "700 " + fpx + 'px "Segoe UI","Nirmala UI",Arial,sans-serif'; g.font = font;
    cv.width = Math.ceil(g.measureText(txt).width) + 10; cv.height = Math.ceil(fpx * 1.5); g.font = font; g.fillStyle = S.textColor; g.textBaseline = "top"; g.fillText(txt, 4, 3);
    const [lx, ly] = toLayer(c.it, c.x, c.y);
    await doEdit("stamp", { layer: c.it.id, x: lx, y: ly, png: cv.toDataURL("image/png") });
  }
  $("#textInput").addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") commitText(); if (e.key === "Escape") { $("#textBox").classList.add("hidden"); tctx = null; stage.focus(); } });

  // ───────────────────────── layers panel ─────────────────────────
  function renderLayers() {
    updateSizePanel(); const box = $("#layers"); box.innerHTML = ""; const _seen = S._lyIds || (S._lyIds = new Set());
    S.layers.slice().reverse().forEach((l) => {
      const d = document.createElement("div"); d.className = "ly" + (_seen.has(l.id) ? "" : " in") + (l.id === S.active ? " sel" : "") + (l.visible ? "" : " hid"); d.dataset.id = l.id; d.draggable = true;
      d.innerHTML = '<img loading="lazy" src="' + url("/lthumb?id=" + l.id + "&w=48&r=" + S.rev) + '"><span class="nm">' + esc(l.name) + " · " + l.w + "×" + l.h + '</span><button class="eye">' + (l.visible ? "👁" : "·") + "</button>";
      d.onclick = (e) => { if (e.target.closest(".eye")) { layerCmdFor(l.id, "visible", { visible: !l.visible }); return; } S.active = l.id; renderLayers(); };
      d.ondblclick = () => { const n = prompt("Layer name", l.name); if (n) layerCmdFor(l.id, "rename", { name: n }); };
      d.ondragstart = (e) => { e.dataTransfer.setData("text/plain", String(l.id)); };
      d.ondragover = (e) => e.preventDefault();
      d.ondrop = (e) => { e.preventDefault(); const from = +e.dataTransfer.getData("text/plain"); const idx = S.layers.findIndex(x => x.id === l.id); if (from && from !== l.id) layerCmdFor(from, "reorder", { index: idx }); };
      box.appendChild(d);
    });
    S._lyIds = new Set(S.layers.map(l => l.id));
  }
  function updateSizePanel() {
    const c = S.canvas || [0, 0]; $("#cvInfo").textContent = S.layers.length ? c[0] + " × " + c[1] + " px" : "—"; $("#cvFree").classList.toggle("hidden", !S.free);
    const l = S.layers.find(x => x.id === S.active); const w = $("#lyW"), h = $("#lyH");
    if (document.activeElement !== w && document.activeElement !== h) { w.value = l ? l.w : ""; h.value = l ? l.h : ""; }
  }
  const lockOn = () => $("#lyLock").dataset.on === "1";
  $("#lyLock").onclick = () => { $("#lyLock").dataset.on = lockOn() ? "0" : "1"; };
  $("#lyW").oninput = () => { const l = S.layers.find(x => x.id === S.active); if (l && lockOn() && +$("#lyW").value) $("#lyH").value = Math.round(+$("#lyW").value * l.h / l.w); };
  $("#lyH").oninput = () => { const l = S.layers.find(x => x.id === S.active); if (l && lockOn() && +$("#lyH").value) $("#lyW").value = Math.round(+$("#lyH").value * l.w / l.h); };
  async function applySize() { const l = S.layers.find(x => x.id === S.active); if (!l) return; const r = await api("layer", { cmd: "resize", layer: l.id, w: +$("#lyW").value, h: +$("#lyH").value }); if (r.ok) onClips(); else toast(r.error || "Can't resize", "warn", 1600); }
  $("#lyApply").onclick = applySize; ["#lyW", "#lyH"].forEach(i => $(i).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applySize(); } e.stopPropagation(); }));
  $$("[data-sc]").forEach(b => b.onclick = () => { const l = S.layers.find(x => x.id === S.active); if (l) layerCmdFor(l.id, "scale", { factor: +b.dataset.sc }); });
  $("#restackBtn").onclick = () => layerCmd("restack"); $("#matchBtn").onclick = () => layerCmd("match_width");
  $("#outW").onchange = async () => { await api("set_options", { out_width: +$("#outW").value }); if (S.st) S.st.settings.out_width = +$("#outW").value; $("#estOut").textContent = ""; };
  $("#estBtn").onclick = async () => { $("#estOut").textContent = "…"; const r = await api("estimate", { page: C.normField("page", F.page.value), cols: F.cols.value.trim() }); $("#estOut").textContent = r.ok ? r.w + "×" + r.h + " · " + (r.kb >= 1024 ? (r.kb / 1024).toFixed(2) + " MB" : Math.round(r.kb) + " KB") : (r.error || "—"); };
  async function layerCmdFor(id, cmd, extra) { const r = await api("layer", Object.assign({ cmd, layer: id }, extra || {})); if (r.ok) onClips(); }

  // ───────────────────────── categories ─────────────────────────
  function roots() { return Object.keys(S.st.categories); }
  function colorOf(path) { return catColor(path.split("/")[0], roots()); }
  function qsFor(path) { const o = []; for (const k in S.st.quick_saves) if (S.st.quick_saves[k] === path) o.push(k); return o; }
  function renderCats() {
    const tree = $("#catTree"); tree.innerHTML = ""; if (!S._catIn) { S._catIn = true; tree.classList.add("enter"); setTimeout(() => tree.classList.remove("enter"), 900); } const R = roots();
    R.forEach((r) => {
      const subs = S.st.categories[r], col = catColor(r, R);
      const row = document.createElement("div"); row.className = "cat-root" + (S.armed.includes(r) ? " sel" : ""); row.style.setProperty("--cc", col);
      row.innerHTML = '<span class="fold">' + (subs.length ? "▾" : "") + '</span><span class="cat-dot"></span><span>' + esc(r) + '</span><span class="cat-key">' + esc(qsFor(r).join(" ")) + "</span>";
      row.onclick = (e) => armToggle(r, e.ctrlKey || e.metaKey); tree.appendChild(row);
      subs.forEach((s) => {
        const p = r + "/" + s, sr = document.createElement("div"); sr.className = "cat-sub" + (S.armed.includes(p) ? " sel" : ""); sr.style.setProperty("--cc", col);
        sr.innerHTML = '<span class="cat-dot"></span><span>' + esc(s) + '</span><span class="cat-key">' + esc(qsFor(p).join(" ")) + "</span>";
        sr.onclick = (e) => armToggle(p, e.ctrlKey || e.metaKey); tree.appendChild(sr);
      });
    });
    const qc = $("#qChips"); qc.innerHTML = "";
    const keys = Object.keys(S.st.quick_saves).sort((a, b) => (a.startsWith("Ctrl") - b.startsWith("Ctrl")) || a.localeCompare(b, undefined, { numeric: true }));
    keys.forEach((k) => {
      const path = S.st.quick_saves[k], b = document.createElement("button"); b.className = "qc" + (S.armed.includes(path) ? " on" : ""); b.dataset.k = k; b.style.setProperty("--cc", colorOf(path));
      b.textContent = k.replace("Ctrl+", "^"); b.title = path; b.onclick = (e) => e.altKey ? armAdd(path) : arm([path], true); qc.appendChild(b);
    });
    updateDock();
  }
  function arm(paths, focus) { S.armed = paths.slice(); renderCats(); if (focus) { prefillMeta(); updateDock(); focusMeta("page"); } sendDraft(); }
  function armAdd(p) { const i = S.armed.indexOf(p); if (i >= 0) S.armed.splice(i, 1); else S.armed.push(p); renderCats(); updateDock(); focusMeta("page"); sendDraft(); }
  function armToggle(p, multi) { if (multi) { const i = S.armed.indexOf(p); if (i >= 0) S.armed.splice(i, 1); else S.armed.push(p); renderCats(); sendDraft(); } else arm([p], true); }
  function flashChip(k) { const b = $('#qChips .qc[data-k="' + k + '"]'); if (b) { b.classList.add("press"); setTimeout(() => b.classList.remove("press"), 140); } }
  window.CLIP_arm = arm;
  const metaF = () => ({ page: F.page.value.trim(), cols: F.cols.value.trim(), size: F.size.value.trim() });
  const pushDraft = () => api("set_draft", { cats: S.armed, line: metaLine(), f: metaF(), src: "app" });
  const sendDraft = debounce(pushDraft, 120);
  function disarm() { if (!S.armed.length) return; S.armed = []; renderCats(); updateDock(); pushDraft(); }
  // the engine is the single source of truth: whatever the overlay (or another window) changes lands here
  on("meta", (ev) => {
    if (ev.src === "app") return;
    S.armed = (ev.cats || []).slice(); renderCats();
    const f = ev.f || {}, ae = document.activeElement;
    for (const k of FORDER) { if (F[k].value !== (f[k] || "") && !(ae && F[k].contains && F[k].contains(ae))) F[k].value = f[k] || ""; }
    updateDock(); refreshMetaSoon();
  });
  const discard = async (all) => { const r = await api("discard", { all: !!all }); if (!r.ok) toast(r.error || "No clip", "warn", 1500); else toast(all ? "All clips deleted" : "Clip deleted", "ok", 5000, { label: t("undo") + " (Ctrl+Z)", fn: () => layerCmd("undo") }); };
  window.CLIP_discard = discard;
  $("#discardBtn").onclick = (e) => discard(e.shiftKey);
  document.addEventListener("keydown", (e) => {   // capture: works even while a Page / Position / Size box has focus
    if (!S.st) return;
    const hk = (S.st.hotkeys || {}).discard || "<Control-Delete>";
    const ev = { key: e.key, ctrlKey: e.ctrlKey, altKey: e.altKey, metaKey: e.metaKey, shiftKey: false };
    if (!C.matchTk(C.parseTk(hk), ev)) return;
    e.preventDefault(); e.stopPropagation(); discard(e.shiftKey);
  }, true);

  // ───────────────────────── metadata line + dock ─────────────────────────
  // one-key category switch: change armed category in place, keep Page/Position/Size and the focused field
  function switchCat(dir) {
    const ks = Object.keys(S.st.quick_saves).sort((a, b) => (a.startsWith("Ctrl") - b.startsWith("Ctrl")) || a.localeCompare(b, undefined, { numeric: true }));
    const paths = ks.map(k => S.st.quick_saves[k]).filter((p, i, a) => a.indexOf(p) === i);
    if (!paths.length) return;
    const i = paths.indexOf(S.armed[0]), n = i < 0 ? (dir > 0 ? 0 : paths.length - 1) : (i + dir + paths.length) % paths.length;
    const ae = document.activeElement; S.armed = [paths[n]]; renderCats(); updateDock(); sendDraft();
    if (ae && ae.focus) ae.focus();
  }
  window.CLIP_switchCat = switchCat;
  function focusMeta(k) { const el = F[k || "page"]; if (el.focusFirst) el.focusFirst(); else { el.focus(); el.select(); } }
  function metaEnter(k) { if (k === "cols") autoWidth(); const i = FORDER.indexOf(k); S.touched[k] = true; const r = C.fieldCheck(k, F[k].value); updateDock(); if (r !== "ok") { toast(r || ("Enter the " + (k === "cols" ? "position" : k)), "warn", 2200); return; } if (i < 2) { const nk = FORDER[i + 1]; if (nk === "size" && F.size.a.value) { F.size.b.focus(); F.size.b.select(); } else focusMeta(nk); } else doSave(); }
  function metaEsc() { disarm(); if (document.activeElement) document.activeElement.blur(); stage.focus(); }
  function prefillMeta() { const m = (S.st && S.st.meta) || {}; if (!F.page.value && m.page) F.page.value = C.normField("page", m.page); if (!F.size.value && m.size) F.size.value = m.size; }
  function updateDock() {
    const names = S.armed.map(p => p.split("/").join(" › "));
    { const dk = S.armed.join("|"); if (S._dockK !== dk) { S._dockK = dk; const dc = $("#dockCat"); dc.classList.remove("pulse"); void dc.offsetWidth; dc.classList.add("pulse"); } }
    $("#dockCatName").textContent = names.length ? names.join("  +  ") : t("pick_cat");
    { const box = $("#catStack"), prev = S._stack || []; box.innerHTML = "";
      if (!S.armed.length) box.innerHTML = '<div class="cs empty">—</div>';
      S.armed.forEach((p, i) => { const d = document.createElement("div"); d.className = "cs" + (i ? " more" : " main") + (prev.includes(p) ? "" : " pop"); d.style.setProperty("--cc", colorOf(p)); d.textContent = p.split("/").join(" › "); box.appendChild(d); });
      S._stack = S.armed.slice(); }
    const col = S.armed.length ? colorOf(S.armed[0]) : "var(--dim)"; $("#dockCat").style.setProperty("--cc", col); $("#catBar").style.setProperty("--cc", col);
    $("#dockHint").textContent = S.armed.length ? "Esc ✕" : "";
    $("#saveBtn").disabled = !S.layers.length || !S.armed.length;
    FORDER.forEach(k => { const r = C.fieldCheck(k, F[k].value); F[k].classList.toggle("good", r === "ok"); F[k].classList.toggle("bad", !!r && r !== "ok" && S.touched[k]); });
    const m = { page: C.normField("page", F.page.value), cols: F.cols.value.trim() };
    const hp = $("#hdrPrev"); const dt = S.st ? S.st.date.split("-").reverse().join("-") : ""; hp.textContent = "Page-" + (m.page || "·") + ", Pos-" + (m.cols || "·") + ", Date-" + dt;
  }
  S.touched = {};
  FORDER.forEach((k, i) => {
    const el = F[k]; if (k !== "page") return;
    el.addEventListener("input", () => {
      S.touched[k] = false; clearTimeout(el._jt);
      if (k === "cols" && /^[1-8][1-8]$/.test(el.value)) el.value = el.value[0] + "-" + el.value[1];
      if (k === "page") el.value = el.value.toUpperCase();
      updateDock(); if (k !== "size") refreshMetaSoon(); sendDraft();
      // auto-advance: position "1-3" jumps to size at once; the page field never jumps by itself (Tab / Enter moves on)
      if (k === "cols" && C.fieldCheck("cols", el.value) === "ok" && /^[1-8]-[1-8]$/.test(el.value)) focusMeta("size");
    });
    el.addEventListener("blur", () => { S.touched[k] = true; const v = C.normField(k, el.value); if (v !== el.value) el.value = v; updateDock(); });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) return;
      if (e.key === "Enter") {
        e.preventDefault(); el.value = C.normField(k, el.value); S.touched[k] = true; const r = C.fieldCheck(k, el.value); updateDock();
        if (r !== "ok") { toast(r || ("Enter the " + (k === "cols" ? "position" : k)), "warn", 2200); return; }
        if (i < 2) focusMeta(FORDER[i + 1]); else doSave();
      } else if (e.key === "Backspace" && !el.value && i > 0) { e.preventDefault(); focusMeta(FORDER[i - 1]); }
      else if (e.key === "Escape") { e.preventDefault(); disarm(); el.blur(); stage.focus(); }
    });
  });
  $("#saveBtn").onclick = doSave;
  // ── repeat last metadata ──
  function repeatLast(save) {
    const m = (S.st && S.st.last_meta) || {};
    if (!m.page && !m.cols && !m.size) { toast("Nothing saved yet to repeat", "warn", 1600); return; }
    F.page.value = m.page || ""; F.cols.value = m.cols || ""; F.size.value = m.size || ""; S.touched = { page: true, cols: true, size: true }; S.pageTyped = true;
    updateDock(); refreshMetaSoon(); sendDraft();
    if (!S.armed.length) toast("Last Page / Position / Size filled — pick a category", "", 2200);
    else if (save && S.layers.length) doSave(); else if (save) toast(t("nothing"), "warn", 1600);
  }
  $("#repeatBtn") && ($("#repeatBtn").onclick = () => repeatLast(false));
  // ── page from the ePaper tab ──
  S.hintPage = ""; S.pageTyped = false;
  F.page.addEventListener("input", () => { S.pageTyped = true; F.page.classList.remove("hint"); });
  on("page_hint", (ev) => {
    if (document.activeElement === F.page || !ev.page) return;
    if (!F.page.value || F.page.value === S.hintPage || !S.pageTyped) { F.page.value = C.normField("page", ev.page); S.hintPage = F.page.value; S.pageTyped = false; F.page.classList.add("hint"); F.page.title = "Page read from the ePaper tab — type to change"; updateDock(); refreshMetaSoon(); sendDraft(); }
  });
  // ── invert selection / straighten / clean-up memory / copy last saved ──
  function invertSel() {
    if (!S.sel) { toast("Select something first", "warn", 1400); return; }
    const sh = S.sel.shape; S.sel = { layer: S.sel.layer, shape: sh.type === "not" ? sh.inner : { type: "not", inner: sh } }; drawOv();
    toast(S.sel.shape.type === "not" ? "Selection inverted" : "Selection back to normal", "", 1000);
  }
  async function cleanupApply() { if (!S.active) return; const r = await api("cleanup_apply", { layer: S.active }); if (r.ok) { onClips(); toast("Clean-up applied", "ok", 1200); } else toast(r.error || "Failed", "warn", 3000); }
  async function copyLast() { const r = await api("copy_last_saved"); toast(r.ok ? "Copied to clipboard: " + r.name : (r.error || "Failed"), r.ok ? "ok" : "warn", 2200); }
  $("#invSelBtn") && ($("#invSelBtn").onclick = invertSel);
  $("#cuApply") && ($("#cuApply").onclick = cleanupApply);
  $("#cuSave") && ($("#cuSave").onclick = async () => { if (!S.sel) { toast("Select the area first (rectangle)", "warn", 1800); return; } const r = await api("cleanup_save", { layer: S.sel.layer, shape: S.sel.shape }); toast(r.ok ? "Remembered for this paper (" + r.n + ")" : (r.error || "Failed"), r.ok ? "ok" : "warn", 2200); });
  // ── inches ruler / calibration ──
  const inchSoon = debounce(async () => { const r = await api("inches"); S.inch = r; const o = $("#inchOut"); if (!o) return; o.textContent = r.ok ? "≈ " + r.size + " in" : (r.calibrated ? "" : "not calibrated"); $("#inchUse").classList.toggle("hidden", !r.ok); }, 250);
  S.inchSoon = inchSoon;
  $("#inchUse") && ($("#inchUse").onclick = () => { if (S.inch && S.inch.ok) { F.size.value = S.inch.size; S.touched.size = true; updateDock(); sendDraft(); toast("Size set to " + S.inch.size, "ok", 1200); } });
  $("#calBtn") && ($("#calBtn").onclick = () => {
    if (!S.sel) { toast("Select a part whose real width you know (e.g. one column), then click Calibrate", "warn", 3200); return; }
    const l = S.layers.find(x => x.id === S.sel.layer); const bb = bboxOf(S.sel.shape); const px = Math.round(bb[2] - bb[0]); if (px < 10) { toast("Selection too narrow", "warn", 1500); return; }
    modal("<h3>Calibrate inches</h3><p class='sub'>The selected part is <b>" + px + " px</b> wide. How wide is it on paper? (Keep the ePaper zoom the same each day.)</p><div class='field'><label>Width in inches</label><input id='calIn' type='number' step='0.01' min='0.1' placeholder='e.g. 1.8'></div><div class='modal-actions'><button class='btn' id='calNo'>Cancel</button><button class='btn pri' id='calOk'>Save for this paper</button></div>", (c, close) => {
      setTimeout(() => $("#calIn").focus(), 0); $("#calNo").onclick = close;
      const go = async () => { const v = +$("#calIn").value; if (!(v > 0)) return; const r = await api("calibrate", { px, inches: v }); close(); toast(r.ok ? "Saved: " + r.ppi + " px per inch" : (r.error || "Failed"), r.ok ? "ok" : "warn", 2500); inchSoon(); };
      $("#calOk").onclick = go; $("#calIn").onkeydown = (e) => { e.stopPropagation(); if (e.key === "Enter") go(); };
    });
  });

  async function doSave() {
    if (!S.layers.length) { toast(t("nothing"), "warn", 2200); return; }
    if (!S.armed.length) { toast(t("need_cat"), "warn", 2400); return; }
    for (const k of FORDER) { F[k].value = C.normField(k, F[k].value); S.touched[k] = true; }
    for (const k of FORDER) { const r = C.fieldCheck(k, F[k].value); if (r !== "ok") { updateDock(); toast(r || ("Enter the " + (k === "cols" ? "position" : k)), "error", 3200); focusMeta(k); return; } }
    const cats = S.armed.slice(), line = metaLine(), r = await api("save", { cats, line });
    if (!r.ok) { toast(r.error || "Save failed", "error", 3500); return; }
    { const sb = $("#saveBtn"); sb.classList.remove("ok"); void sb.offsetWidth; sb.classList.add("ok"); } S.armed = []; F.cols.value = ""; S.touched.cols = false; S.pageTyped = false; S.lastSaveAt = Date.now();
    if (S.st && r.meta) S.st.last_meta = { page: r.meta.page, cols: r.meta.cols, size: r.meta.size };
    updateDock(); S.sel = null; renderCats(); stage.focus();
    const label = cats.map(p => p.split("/").join(" › ")).join(", ");
    toast(t("saved_to") + " " + label + " ✓", "ok", 10000, { label: t("undo") + " (Ctrl+Z)", fn: undoSave });
  }
  async function undoSave() { const r = await api("undo_save"); if (r.ok) toast("Save undone", "ok", 1800); else toast(r.error || "Can't undo", "warn", 2000); }

  // ───────────────────────── keyboard ─────────────────────────
  const KEYTOOL = { m: "marquee", w: "wand", l: "lasso", v: "move", b: "brush", s: "clone", t: "text" };
  function typing(e) { const t2 = e.target; return t2 && (t2.tagName === "INPUT" || t2.tagName === "TEXTAREA" || t2.isContentEditable); }
  document.addEventListener("keydown", async (e) => {
    if (!S.st || document.body.classList.contains("locked")) return;
    if (C.$("#cmdk") && !C.$("#cmdk").classList.contains("hidden")) return;
    if (!C.$("#modal").classList.contains("hidden")) return;
    if (window.MAIN && MAIN.view !== "clip") return;
    const ctrl = e.ctrlKey || e.metaKey, tp = typing(e), k = e.key;
    if (e.key === " " && !tp) { S.space = true; stage.classList.add("pan"); e.preventDefault(); }
    // quick-save keys (Ctrl+digit works even while typing; bare digits only when not typing)
    if (e.altKey && !ctrl && /^[0-9]$/.test(k) && S.st.quick_saves[k]) { e.preventDefault(); flashChip(k); armAdd(S.st.quick_saves[k]); return; }
    if (e.altKey && !ctrl && (k === "[" || k === "]")) { e.preventDefault(); switchCat(k === "]" ? 1 : -1); return; }
    if (ctrl && !e.shiftKey && k === "Enter") { e.preventDefault(); repeatLast(true); return; }
    const q = C.qsKey(e);
    if (q && S.st.quick_saves[q] && (!tp || q.startsWith("Ctrl+")) && !e.shiftKey) { e.preventDefault(); flashChip(q); arm([S.st.quick_saves[q]], true); return; }
    if (tp) { if (ctrl && k.toLowerCase() === "s") { e.preventDefault(); doSave(); } return; }
    const HK = S.st.hotkeys, M = (n) => C.matchTk(C.parseTk(HK[n]), e);
    if (ctrl && e.shiftKey && k.toLowerCase() === "i") { e.preventDefault(); return invertSel(); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "k") { e.preventDefault(); return cleanupApply(); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "c") { e.preventDefault(); return copyLast(); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "f") { e.preventDefault(); return api("open_last_folder"); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "v") { e.preventDefault(); return layerCmd("paste_internal"); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "j") { e.preventDefault(); if (needSel()) doEdit("extract", { layer: S.sel.layer, shape: S.sel.shape, cut: true }); return; }
    if (ctrl && e.shiftKey && k.toLowerCase() === "e") { e.preventDefault(); return layerCmd("merge_visible"); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "t") { e.preventDefault(); if (!S.sel) selectAll(); setTool("move"); return; }
    if (ctrl && !e.shiftKey && k.toLowerCase() === "j") { e.preventDefault(); if (S.sel) doEdit("extract", { layer: S.sel.layer, shape: S.sel.shape, cut: false }); else layerCmd("duplicate"); return; }
    if (ctrl && k.toLowerCase() === "c" && !e.shiftKey) { e.preventDefault(); if (needSel()) { const r = await api("edit", { op: "copy", layer: S.sel.layer, shape: S.sel.shape }); toast(r.copied ? "Copied selection" : "Selection too small", r.copied ? "ok" : "warn", 1200); } return; }
    if (ctrl && k.toLowerCase() === "x") { e.preventDefault(); if (needSel()) doEdit("cut", { layer: S.sel.layer, shape: S.sel.shape }); return; }
    if (ctrl && k.toLowerCase() === "d") { e.preventDefault(); return deselect(); }
    if (ctrl && k.toLowerCase() === "a") { e.preventDefault(); return selectAll(); }
    if (ctrl && k === "0") { e.preventDefault(); S.V = { z: 1, cx: .5, cy: .5 }; applyView(); hiresSoon(); return; }
    if (ctrl && k === "1") { e.preventDefault(); if (S.P) { S.V.z = 1 / (fitScale() * S.P.k * dpr()) * dpr(); applyView(); hiresSoon(); } return; }
    if (ctrl && (k === "+" || k === "=")) { e.preventDefault(); S.V.z = Math.min(12, S.V.z * 1.25); applyView(); hiresSoon(); return; }
    if (ctrl && k === "-") { e.preventDefault(); S.V.z = Math.max(0.2, S.V.z / 1.25); applyView(); hiresSoon(); return; }
    if (M("paste")) { e.preventDefault(); return paste(); }
    if (M("undo")) { e.preventDefault(); if (!S.layers.length && Date.now() - (S.lastSaveAt || 0) < 10000) return undoSave(); return layerCmd("undo"); }
    if (M("redo")) { e.preventDefault(); return layerCmd("redo"); }
    if (M("generate")) { e.preventDefault(); return doSave(); }
    if (M("trim")) { e.preventDefault(); return filter("trim"); }
    if (M("clean")) { e.preventDefault(); return filter("clean"); }
    if (M("pad")) { e.preventDefault(); return filter("pad"); }
    if (ctrl && e.shiftKey && k.toLowerCase() === "o") { e.preventDefault(); return MAIN.recent(); }
    if (M("open")) { e.preventDefault(); return openDialog(); }
    if (S.tool === "move" && !S.sel && /^Arrow/.test(k) && S.active) { e.preventDefault(); const st2 = e.shiftKey ? 10 : 1; return layerCmdFor(S.active, "move", { dx: k === "ArrowLeft" ? -st2 : k === "ArrowRight" ? st2 : 0, dy: k === "ArrowUp" ? -st2 : k === "ArrowDown" ? st2 : 0 }); }
    if (M("move_up")) { e.preventDefault(); return layerCmd("move_up"); }
    if (M("move_down")) { e.preventDefault(); return layerCmd("move_down"); }
    if (M("swap")) { e.preventDefault(); return layerCmd("swap"); }
    if (M("delete")) { e.preventDefault(); if (S.sel) return applyAct("erase"); return layerCmd("undo"); }   // same as the old "smart delete"
    if (ctrl || e.altKey) return;
    if (k === "Enter" && S.suggest && !S.sel) { e.preventDefault(); return applySuggest(); }
    if (k === "Escape") { if (S.sel) deselect(); else if (S.suggest) { S.suggest = null; $("#suggest").classList.add("hidden"); drawOv(); } else if (S.armed.length) { disarm(); } return; }
    if (M("tool_crop")) { e.preventDefault(); return applyAct("crop"); }
    if (M("tool_erase")) { e.preventDefault(); return applyAct("erase"); }
    if (M("tool_highlight")) { e.preventDefault(); return applyAct("highlight"); }
    if (M("tool_redact")) { e.preventDefault(); return applyAct("redact"); }
    if (k === "[") { S.brush = Math.max(4, S.brush - 4); toast("Brush " + S.brush, "", 700); return; }
    if (k === "]") { S.brush = Math.min(160, S.brush + 4); toast("Brush " + S.brush, "", 700); return; }
    if (e.shiftKey && k.toLowerCase() === "m") { setTool("ellipse"); return; }
    const lk = k.toLowerCase(); if (KEYTOOL[lk] && !e.shiftKey) { e.preventDefault(); setTool(KEYTOOL[lk]); return; }
    if (lk === "p") { e.preventDefault(); MAIN.paperMenu(); return; }
    if (k === "/") { e.preventDefault(); MAIN.cmdk(); return; }
  });
  document.addEventListener("keyup", (e) => { if (e.key === " ") { S.space = false; stage.classList.remove("pan"); } });

  // ───────────────────────── toolbar wiring ─────────────────────────
  $$("#toolbar .tb[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  $$("#toolbar .tb[data-act]").forEach(b => b.onclick = () => applyAct(b.dataset.act));
  $("#undoBtn").onclick = () => layerCmd("undo"); $("#redoBtn").onclick = () => layerCmd("redo");
  $("#fitBtn").onclick = () => { S.V = { z: 1, cx: .5, cy: .5 }; applyView(); hiresSoon(); };
  $("#pasteBtn").onclick = paste;
  async function openFiles(files) {
    files = Array.from(files).filter(f => f.type.startsWith("image/")); if (!files.length) return;
    const imgs = await Promise.all(files.map(f => new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(f); })));
    const r = await api("paste_data", { images: imgs }); if (!r.ok) toast("Could not read that image", "warn", 2000);
  }
  function openDialog() { $("#fileIn").value = ""; $("#fileIn").click(); }
  $("#fileIn").onchange = (e) => openFiles(e.target.files); $("#openBtn").onclick = openDialog; $("#savedBtn").onclick = () => MAIN.recent();
  window.CLIP_open = openDialog;
  $("#suggestBtn").onclick = applySuggest; $("#suggestX").onclick = () => { S.suggest = null; $("#suggest").classList.add("hidden"); drawOv(); };
  $("#lyDup").onclick = () => layerCmd("duplicate"); $("#lyMerge").onclick = () => layerCmd("merge_down"); $("#lySide").onclick = () => layerCmd("merge_side"); $("#lyDel").onclick = () => layerCmd("delete");
  $$("[data-f]").forEach(b => b.onclick = () => filter(b.dataset.f));
  $('[data-f="deskew"]') && ($('[data-f="deskew"]').onclick = async () => { if (!S.active) return; const r = await api("filter", { name: "deskew", layer: S.active }); if (r.ok) { onClips(); toast("Straightened by " + r.angle + "°", "ok", 1800); } else toast(r.error || "Failed", "warn", 2400); });
  // ── Levels (brightness / contrast / gamma) with live CSS preview, applied once ──
  function levels() {
    const pg = $("#page"); if (!pg) return; const base = pg.style.filter;
    modal("<h3>Levels</h3><div class='field'><label>Brightness <b id='lvB'>1.00</b></label><input type='range' id='lB' min='0.4' max='2' step='0.01' value='1'></div><div class='field'><label>Contrast <b id='lvC'>1.00</b></label><input type='range' id='lC' min='0.4' max='2.5' step='0.01' value='1'></div><div class='field'><label>Gamma <b id='lvG'>1.00</b></label><input type='range' id='lG' min='0.4' max='2.5' step='0.01' value='1'></div><div class='modal-actions'><button class='btn' id='lNo'>Cancel</button><button class='btn pri' id='lOk'>Apply</button></div>", (c, close) => {
      const v = () => [+$("#lB").value, +$("#lC").value, +$("#lG").value];
      const live = () => { const [b, ct] = v(); $("#lvB").textContent = b.toFixed(2); $("#lvC").textContent = ct.toFixed(2); $("#lvG").textContent = v()[2].toFixed(2); pg.style.filter = "brightness(" + b + ") contrast(" + ct + ")"; };
      ["lB", "lC", "lG"].forEach(i => $("#" + i).oninput = live);
      const done = () => { pg.style.filter = base; close(); };
      $("#lNo").onclick = done; $("#lOk").onclick = async () => { const [b, ct, g] = v(); done(); await filter("levels", { brightness: b, contrast: ct, gamma: g }); };
    });
  }
  $("#levelsBtn") && ($("#levelsBtn").onclick = levels);

  // option controls
  const opt = (id, key, ev, conv) => { const el = $(id); el.addEventListener(ev, async () => { const v = conv ? conv(el) : el.checked; await api("set_options", { [key]: v }); if (S.st) S.st.settings[key] = v; if (id === "#optQuality") $("#qVal").textContent = v; refreshSoon(); }); };
  opt("#optHeader", "show_header", "change"); opt("#optLogo", "logo_scale", "input", e => +e.value); opt("#optText", "text_scale", "input", e => +e.value);
  opt("#optQuality", "quality", "input", e => +e.value); opt("#optHD", "hd_mode", "change"); opt("#optSnatch", "auto_snatch", "change"); opt("#optPolish", "auto_polish", "change"); $("#optFit") && opt("#optFit", "smart_fit", "change");
  // drag & drop image files onto the stage
  stage.addEventListener("dragover", (e) => e.preventDefault());
  stage.addEventListener("drop", async (e) => {
    e.preventDefault(); const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith("image/")); if (!files.length) return;
    const imgs = await Promise.all(files.map(f => new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(f); })));
    await api("paste_data", { images: imgs });
  });

  // ───────────────────────── public API for main.js ─────────────────────────
  window.CLIPUI = {
    init(st) { S.st = st; prefillMeta(); measure(); syncOptions(); renderCats(); onClips(); },
    setState(st) { S.st = st; syncOptions(); renderCats(); updateDock(); },
    onClips, refresh, measure, applyView, paste, doSave, undoSave, arm, filter, layerCmd, setTool, applySuggest,
    focusMeta, renderCats, updateDock,
    onShow() { measure(); applyView(); },
  };
  window.CLIPX = { S, F, focusMeta, doSave, updateDock, setTool, repeatLast, armAdd, invertSel, onClips, doEdit, undoSave, copyLast };
  function syncOptions() {
    const s = S.st.settings; $("#optHeader").checked = s.show_header; $("#optLogo").value = s.logo_scale; $("#optText").value = s.text_scale; $("#optQuality").value = s.quality;
    $("#qVal").textContent = Math.round(s.quality); $("#outW").value = String(s.out_width || 0); $("#optHD").checked = s.hd_mode; $("#optSnatch").checked = s.auto_snatch; $("#optPolish").checked = s.auto_polish; if ($("#optFit")) $("#optFit").checked = s.smart_fit !== false;
  }
  if (window.matchMedia) { /* narrow screens: panel toggle */
    const b = document.createElement("button"); b.className = "tb"; b.id = "panelBtn"; b.textContent = "☰"; b.title = "Panels";
    b.onclick = () => { $("#rightPanel").classList.toggle("open"); $("#leftPanel").classList.toggle("open"); }; $("#toolbar").insertBefore(b, $("#toolbar").firstChild);
  }
  CATSEARCH.install(() => (S.st && S.st.categories) || {}, () => S.armed, (ps) => arm(ps, true), () => !window.MAIN || MAIN.view === "clip");
})();
