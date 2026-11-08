// overlay.js — mini window shown while NAB is minimized: live thumbnail, armed category, metadata line.
(function () {
  const { $, esc, api, url, on, connect, catColor, qsKey, parseMeta } = C;
  const S = { st: null, armed: [], rev: -1, small: false, busy: false, hide: false };
  const roots = () => Object.keys((S.st && S.st.categories) || {});
  const colorOf = (p) => catColor(p.split("/")[0], roots());
  const label = (p) => p.split("/").join(" › ");

  async function load() {
    S.st = await api("state"); if (!S.st.authorized) { setTimeout(load, 1000); return; }
    if (S.st.ui && S.st.ui.theme) C.theme(S.st.ui.theme);
    $("#ovPaper").textContent = S.st.paper_clean || "NAB";
    $("#ovLogo").src = url("/logo?n=" + encodeURIComponent(S.st.paper)); $("#ovLogo").onerror = function () { this.style.display = "none"; }; $("#ovLogo").onload = function () { this.style.display = ""; };
    applyMeta(S.st.draft_sync || {});
    renderQ(); thumb(); inchSoon();
  }
  function applyMeta(m) {
    if (!m) return; S.armed = (m.cats || []).slice();
    const f = m.f || {}, ae = document.activeElement;
    for (const k of ORD) { if (F[k].value !== (f[k] || "") && !(F[k].contains ? F[k].contains(ae) : ae === F[k])) { F[k].value = f[k] || ""; F[k]._t = 0; } }
    renderQ(); paint();
  }
  on("meta", (ev) => { if (ev.src === "overlay") return; applyMeta(ev); });
  function renderQ() {
    const qs = S.st.quick_saves || {}, keys = Object.keys(qs).sort((a, b) => (a.startsWith("Ctrl") - b.startsWith("Ctrl")) || a.localeCompare(b, undefined, { numeric: true }));
    $("#ovQ").innerHTML = keys.map(k => `<button data-k="${esc(k)}" class="${S.armed.includes(qs[k]) ? "on" : ""}" style="--cc:${colorOf(qs[k])}" title="${esc(label(qs[k]))}">${esc(k.replace("Ctrl+", "^"))}</button>`).join("");
    Array.from($("#ovQ").children).forEach(b => b.onclick = () => arm(qs[b.dataset.k]));
    const c = S.armed[0]; $("#ovCat").textContent = S.armed.length ? S.armed.map(label).join(", ") : "Pick a category (1–9)";
    $("#ovCat").style.setProperty("--cc", c ? colorOf(c) : "var(--acc)"); if (S._ovK !== S.armed.join("|")) { S._ovK = S.armed.join("|"); const oc = $("#ovCat"); oc.classList.remove("pop"); void oc.offsetWidth; oc.classList.add("pop"); }
  }
  function armAdd(p) { const i = S.armed.indexOf(p); if (i >= 0) S.armed.splice(i, 1); else S.armed.push(p); renderQ(); paint(); push(); focusK("page"); }
  function repeatLast(save) {
    const m = (S.st && S.st.last_meta) || {}; if (!m.page && !m.cols && !m.size) { $("#ovS").textContent = "Nothing saved yet to repeat"; return; }
    F.page.value = m.page || ""; F.cols.value = m.cols || ""; F.size.value = m.size || ""; ORD.forEach(k => F[k]._t = 1); paint(); draft();
    if (save) save_(); else focusK("page");
  }
  function arm(p) { S.armed = [p]; renderQ(); prefill(); paint(); push(); F.page.focus(); F.page.select(); }
  async function thumb() {
    try {
      const L = await api("layers"), n = (L.layers || []).length; S.rev = L.rev;
      $("#ovN").textContent = n; $("#ovEmpty").style.display = n ? "none" : "block"; $("#ovN").style.display = n ? "" : "none";
      if (!n) { $("#ovImg").style.display = "none"; return; }
      const r = await api("preview", { h: 260 });
      if (r.img && !r.empty) { $("#ovImg").style.display = ""; $("#ovImg").classList.remove("swap"); void $("#ovImg").offsetWidth; $("#ovImg").classList.add("swap"); $("#ovImg").src = url(r.img); } else $("#ovImg").style.display = "none";
    } catch (e) { $("#ovImg").style.display = "none"; $("#ovEmpty").style.display = "block"; }
  }
  const tick = C.debounce(() => { thumb(); inchSoon(); }, 120);
  on("clips", tick); on("date", tick); on("paper", () => load()); on("state_changed", load); on("settings_changed", load);

  const push = () => api("set_draft", { cats: S.armed, line: line(), f: { page: F.page.value.trim(), cols: F.cols.value.trim(), size: F.size.value.trim() }, src: "overlay" });
  const F = { page: $("#oPage") }, ORD = ["page", "cols", "size"];
  const draft = () => push();
  const oEnter = (k) => { const i = ORD.indexOf(k); F[k]._t = 1; const r = C.fieldCheck(k, F[k].value); paint(); if (r !== "ok") { $("#ovS").textContent = r || ("Enter the " + k); return; } if (i < 2) focusK(ORD[i + 1]); else save(); };
  const focusK = (k) => { const e = F[k]; if (e.focusFirst) e.focusFirst(); else { e.focus(); e.select(); } };
  F.cols = C.pairField($("#oC1"), $("#oC2"), "-", $("#oColsW"), { esc: disarm, change() { F.cols._t = 0; autoWidth(); paint(); draft(); inchSoon(); }, done() { autoWidth(); if (F.size.a.value) { F.size.b.focus(); F.size.b.select(); } else focusK("size"); }, enter() { oEnter("cols"); }, prev() { focusK("page"); }, leave() { F.cols._t = 1; paint(); } });
  F.size = C.pairField($("#oS1"), $("#oS2"), "x", $("#oSizeW"), { esc: disarm, b2: true, change() { F.size._t = 0; paint(); draft(); }, enter() { oEnter("size"); }, prev() { F.cols.b.focus(); }, leave() { F.size._t = 1; paint(); } });
  function autoWidth() { const a = +F.cols.a.value, b = +F.cols.b.value; if (a >= 1 && b >= a && b <= 9) { const w = String(b - a + 1); if (F.size.a.value !== w) F.size.a.value = w; } }
  function disarm() { if (S.armed.length) { S.armed = []; renderQ(); } push(); if (document.activeElement) document.activeElement.blur(); }
  const inchSoon = C.debounce(async () => {
    try { const r = await api("inches"); S.inch = r; const row = $("#ovInchRow"); row.classList.toggle("hidden", !r.ok); if (r.ok) $("#ovInch").textContent = "≈ " + r.size + " in"; } catch (e) {}
  }, 300);
  $("#ovInchUse").onclick = () => { if (S.inch && S.inch.ok) { F.size.value = S.inch.size; F.size._t = 1; paint(); draft(); } };
  const line = () => ORD.map(k => F[k].value.trim()).filter(Boolean).join(" ");
  function prefill() { const m = (S.st && S.st.meta) || {}; if (!F.page.value && m.page) F.page.value = m.page; if (!F.size.value && m.size) F.size.value = m.size; }
  function paint() { ORD.forEach(k => { const r = C.fieldCheck(k, F[k].value); F[k].classList.toggle("good", r === "ok"); F[k].classList.toggle("bad", !!r && r !== "ok" && !!F[k]._t); }); }
  async function save() {
    if (S.busy) return; if (!S.armed.length) { $("#ovS").textContent = t("need_cat"); return; }
    for (const k of ORD) { F[k].value = C.normField(k, F[k].value); F[k]._t = 1; const r = C.fieldCheck(k, F[k].value); if (r !== "ok") { paint(); $("#ovS").textContent = r || ("Enter the " + k); F[k].focus(); return; } }
    S.busy = true;
    try {
      const snap = { cats: S.armed.slice(), page: F.page.value, cols: F.cols.value, size: F.size.value };
      const r = await api("save", { cats: S.armed, line: line() });
      if (r.ok) { S.lastSave = Object.assign(snap, { at: Date.now() }); if (S.st && r.meta) S.st.last_meta = { page: r.meta.page, cols: r.meta.cols, size: r.meta.size }; typed = false; $("#ovS").textContent = "Saved ✓ " + S.armed.map(label).join(", "); F.cols.value = ""; F.cols._t = 0; S.armed = []; renderQ(); paint(); } else $("#ovS").textContent = r.error || "Not saved";
    } finally { S.busy = false; }
  }
  ORD.forEach((k, i) => {
    const el = F[k]; if (k !== "page") return;
    el.oninput = () => {
      el._t = 0; clearTimeout(el._jt);
      if (k === "cols" && /^[1-8][1-8]$/.test(el.value)) el.value = el.value[0] + "-" + el.value[1];
      if (k === "page") el.value = el.value.toUpperCase();
      paint(); push();
      if (k === "cols" && /^[1-8]-[1-8]$/.test(el.value) && C.fieldCheck("cols", el.value) === "ok") { F.size.focus(); F.size.select(); }
    };
    el.onblur = () => { el._t = 1; el.value = C.normField(k, el.value); paint(); };
    el.onkeydown = (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) return;
      if (e.key === "Escape") { e.preventDefault(); disarm(); return; }
      if (e.key === "Enter") { e.preventDefault(); el.value = C.normField(k, el.value); el._t = 1; const r = C.fieldCheck(k, el.value); paint(); if (r !== "ok") { $("#ovS").textContent = r || ("Enter the " + k); return; } if (i < 2) { F[ORD[i + 1]].focus(); F[ORD[i + 1]].select(); } else save(); }
      else if (e.key === "Backspace" && !el.value && i > 0) { e.preventDefault(); F[ORD[i - 1]].focus(); }
    };
  });
  $("#ovSave").onclick = save;
  function save_() { return save(); }
  let hinted = "", typed = false;
  F.page.addEventListener("input", () => { typed = true; });
  on("page_hint", (ev) => { if (document.activeElement === F.page || !ev.page) return; if (!F.page.value || F.page.value === hinted || !typed) { F.page.value = C.normField("page", ev.page); hinted = F.page.value; typed = false; paint(); draft(); } });
  on("missed_save", () => { const h = document.querySelector(".ov-h"); h.style.background = "#f59e0b"; $("#ovS").textContent = "Clip waiting - save it"; setTimeout(() => { h.style.background = ""; }, 6000); });
  on("saved", (ev) => { const f = ev.files || []; if (f.length) $("#ovS").textContent = "Saved " + Math.max.apply(null, f.map(x => x.kb || 0)) + " KB"; });
  const discard = async (all) => { const r = await api("discard", { all: !!all }); $("#ovS").textContent = r.ok ? (all ? "All clips deleted - Ctrl+Z to undo" : "Clip deleted - Ctrl+Z to undo") : (r.error || "No clip"); thumb(); };
  $("#ovDel").onclick = (e) => discard(e.shiftKey);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Delete" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); discard(e.shiftKey); return; }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && S.lastSave && Date.now() - S.lastSave.at < 20000) {
      e.preventDefault(); const ls = S.lastSave; S.lastSave = null;
      api("undo_save").then(r => { if (!r.ok) { $("#ovS").textContent = r.error || "Can't undo"; return; }
        S.armed = ls.cats; renderQ(); F.page.value = ls.page; F.cols.value = ls.cols; F.size.value = ls.size; ORD.forEach(k => F[k]._t = 1); paint(); push(); thumb(); $("#ovS").textContent = "Save undone - fix it and press Enter"; focusK("page"); });
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === "z" && !(document.activeElement && document.activeElement.tagName === "INPUT")) { e.preventDefault(); api("layer", { cmd: "undo" }).then(thumb); return; }
    if (e.key === "Escape") { e.preventDefault(); disarm(); return; }
    if (e.altKey && !e.ctrlKey && /^[0-9]$/.test(e.key) && S.st && S.st.quick_saves[e.key]) { e.preventDefault(); armAdd(S.st.quick_saves[e.key]); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); repeatLast(true); return; }
    if (document.activeElement && document.activeElement.tagName === "INPUT") { if (!(e.ctrlKey && /^[0-9]$/.test(e.key))) return; }
    const q = qsKey(e), qs = (S.st && S.st.quick_saves) || {};
    if (q && qs[q]) { e.preventDefault(); const b = $("#ovQ [data-k='" + q + "']"); if (b) { b.classList.add("flash"); setTimeout(() => b.classList.remove("flash"), 200); } arm(qs[q]); }
    else if (e.key === "Enter") { e.preventDefault(); F.page.focus(); F.page.select(); }
  });
  $("#ovBack").onclick = () => api("window", { action: "restore" });
  $("#ovSmall").onclick = () => { sizeI = (sizeI + 1) % SIZES.length; const z = SIZES[sizeI]; api("window", { action: "overlay_resize", w: z[0], h: z[1], final: true }); document.body.classList.toggle("sm", sizeI === 0); };
  document.addEventListener("dblclick", (e) => { if (e.target.closest("input,button")) return; api("window", { action: "restore" }); });
  // corner grip: resize by dragging; stop the window's easy-drag from grabbing this mouse-down
  window.addEventListener("mousedown", (e) => {
    if (!(e.target.closest && e.target.closest("#ovGrip")) || e.button !== 0) return;
    e.preventDefault(); e.stopImmediatePropagation(); api("window", { action: "ov_js" });
    const d = { x: e.screenX, y: e.screenY, w: window.innerWidth, h: window.innerHeight, t: 0, nw: 0, nh: 0 };
    const mv = (m) => { const n = Date.now(); if (n - d.t < 35) return; d.t = n; d.nw = Math.round(d.w + m.screenX - d.x); d.nh = Math.round(d.h + m.screenY - d.y); api("window", { action: "overlay_resize", w: d.nw, h: d.nh }); };
    const up = () => { window.removeEventListener("mousemove", mv, true); window.removeEventListener("mouseup", up, true); if (d.nw) api("window", { action: "overlay_resize", w: d.nw, h: d.nh, final: true }); };
    window.addEventListener("mousemove", mv, true); window.addEventListener("mouseup", up, true);
  }, true);
  const SIZES = [[240, 330], [300, 440], [380, 560]]; let sizeI = 1;
  $("#ovClose").onclick = (e) => api("window", { action: "overlay_hide", off: !!e.shiftKey });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
  window.addEventListener("focus", () => thumb());
  setInterval(async () => { if (document.hidden || !S.st) return; try { const L = await api("layers"); if (L.rev !== S.rev) thumb(); } catch (e) {} }, 4000);
  connect(); load();
  CATSEARCH.install(() => (S.st && S.st.categories) || {}, () => S.armed, (ps) => { S.armed = ps.slice(); renderQ(); prefill(); paint(); push(); F.page.focus(); F.page.select(); });
})();
