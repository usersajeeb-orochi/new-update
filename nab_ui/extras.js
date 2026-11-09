// extras.js — v3.0.4 helpers: first-run guide, crash-draft prompt, learn-this-paper, extension light,
// missed-save guard, slow-PC mode, focus rules, recent-saves keyboard, extra commands.
(function () {
  const { $, $$, esc, api, on, toast, modal } = C;
  const X = window.EXTRAS = { st: null };

  // ───────────── start / state ─────────────
  X.onStart = async function (st) {
    X.onState(st);
    try {
      const d = await api("draft_check");
      if (d && d.found) return draftPrompt(d);
    } catch (e) { }
    if (!st.firstrun_done) setTimeout(() => firstRun(st), 800);
    setInterval(extPoll, 10000);
  };
  X.onState = function (st) {
    X.st = st; document.body.classList.toggle("slow", !!st.slow); extLight(st.ext);
  };

  // ───────────── crash-safe draft ─────────────
  function draftPrompt(d) {
    const mins = Math.max(1, Math.round((d.age || 0) / 60));
    modal("<h3>Unsaved clip found</h3><p>NAB closed last time with <b>" + d.n + " unsaved clip" + (d.n > 1 ? "s" : "") + "</b>" + (d.paper ? " (" + esc(C.clean(d.paper)) + ")" : "") + ", about " + mins + " min ago. Bring " + (d.n > 1 ? "them" : "it") + " back?</p><div class='modal-actions'><button class='btn' id='dNo'>Discard</button><button class='btn pri' id='dYes'>Restore</button></div>", (c, close) => {
      $("#dYes").onclick = async () => { close(); const r = await api("draft_restore"); toast(r.ok ? "Restored " + r.n + " clip" + (r.n > 1 ? "s" : "") : (r.error || "Could not restore"), r.ok ? "ok" : "warn", 2500); if (r.ok) { CLIPUI.onClips(); if (r.line) { /* metadata is re-typed; keep it simple */ } } };
      $("#dNo").onclick = async () => { close(); await api("draft_discard"); };
      setTimeout(() => $("#dYes").focus(), 0);
    });
  }

  // ───────────── extension light ─────────────
  function extLight(e) {
    const d = $("#stExt"); if (!d || !e) return; d.className = "ext-dot " + (e.state || "off"); d.title = e.text || "";
  }
  async function extPoll() { try { extLight(await api("ext_status")); } catch (e) { } }
  $("#stExt") && ($("#stExt").onclick = () => guide(false));

  // ───────────── browser extension: first-run question + guided setup ─────────────
  async function firstRun(st) {
    let e = null; try { e = await api("ext_status"); } catch (x) { }
    if (e && e.state !== "ok" && !((st.ui || {}).ext_prompted)) { api("ui_set", { ext_prompted: true }); return extPrompt(); }
    guide(true);
  }
  function extPrompt() {
    modal(`<h3>Set up the browser extension?</h3><p>It tells NAB which e-paper tab you are on, so the <b>newspaper and page number are picked automatically</b>. Without it NAB can't read the tab.</p><p class="sub">NAB will open your browser on its extensions page and show you the 3 clicks. It takes about a minute, and nothing leaves your PC.</p><div class="modal-actions"><button class="btn" id="exLater">Later</button><button class="btn pri" id="exYes">Set up now</button></div>`, (c, close) => {
      $("#exLater").onclick = () => { close(); guide(true); };
      $("#exYes").onclick = () => { close(); extSetup(); };
    });
  }
  X.extSetup = () => extSetup();
  async function extSetup() {
    const info = await api("ext_setup_info");
    const bro = info.browsers || [];
    const opts = bro.map((b, i) => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join("");
    modal(`<h3>Set up the browser extension</h3>
      <div class="ex-steps">
        <div class="ex-s"><span class="ex-n">1</span><div><b>Open the extensions page</b><div class="ex-row">${bro.length ? `<select id="exBr">${opts}</select><button class="btn pri" id="exOpen">Open ${esc(bro[0].name)}</button>` : `<small>No Chrome or Edge found. Open your browser and type <code>chrome://extensions</code> in the address bar.</small>`}</div></div></div>
        <div class="ex-s"><span class="ex-n">2</span><div><b>Turn on “Developer mode”</b><small>The switch is at the top right of that page.</small></div></div>
        <div class="ex-s"><span class="ex-n">3</span><div><b>Click “Load unpacked”, then choose this folder</b>
          <div class="ex-row"><input id="exPath" readonly value="${esc(info.dir || "")}"><button class="btn" id="exCopy">Copy path</button><button class="btn" id="exFold">Open folder</button></div>
          <small>In the folder window: click the address bar, press <kbd>Ctrl</kbd>+<kbd>V</kbd> and <kbd>Enter</kbd>, then <b>Select Folder</b>.</small></div></div>
        <div class="ex-s"><span class="ex-n" id="exDot">4</span><div><b id="exState">Waiting for the extension…</b><small>This turns green by itself when it connects. Keep NAB open.</small></div></div>
      </div>
      ${info.ok ? "" : `<p style="color:var(--bad)">${esc(info.error || "")}</p>`}
      <div class="modal-actions"><button class="btn" id="exClose">Close</button></div>`, (c, close) => {
      let alive = true; const stop = () => { alive = false; close(); };
      $("#exClose").onclick = stop;
      const br = $("#exBr"); if (br) br.onchange = () => { const b = bro.find(x => x.id === br.value); $("#exOpen").textContent = "Open " + b.name; };
      const op = $("#exOpen"); if (op) op.onclick = async () => { const r = await api("ext_open_browser", { browser: br ? br.value : null }); if (r.ok) { try { navigator.clipboard.writeText(info.dir); } catch (e) { } toast("Opening " + r.browser + " — the folder path is already copied", "ok", 3500); } else toast(r.error || "Could not open the browser", "warn", 4000); };
      $("#exCopy").onclick = () => { try { navigator.clipboard.writeText(info.dir); toast("Path copied", "ok", 1200); } catch (e) { $("#exPath").select(); } };
      $("#exFold").onclick = () => api("ext_open_folder");
      const tick = async () => {
        if (!alive || !document.body.contains($("#exState"))) return;
        try { const e = await api("ext_status"); extLight(e); if (e.state === "ok" || e.state === "idle") { $("#exState").textContent = "Extension connected ✓"; $("#exDot").textContent = "✓"; $("#exDot").classList.add("ok"); toast("Browser extension connected ✓", "ok", 2500); alive = false; return; } } catch (x) { }
        setTimeout(tick, 1500);
      };
      setTimeout(tick, 1500);
    });
  }

  // ───────────── first-run guide ─────────────
  async function guide(auto) {
    const r = await api("firstrun"); if (!r.ok) return;
    if (auto && r.all_ok) { api("firstrun_done"); return; }
    draw(r, auto);
  }
  X.guide = () => guide(false);
  function draw(r, auto) {
    const bad = r.steps.find(s => !s.ok), cur = bad || null;
    const list = r.steps.map(s => `<div class="fr-step"><span class="fr-ic">${s.ok ? "✅" : (cur && cur.id === s.id ? "👉" : "⬜")}</span><div><b>${esc(s.title)}${s.detail ? " — <span style='font-weight:500;color:var(--dim)'>" + esc(s.detail) + "</span>" : ""}</b>${!s.ok && cur && cur.id === s.id ? `<small>${esc(s.why)}</small><div class="fr-fix" style="margin-top:6px"><b style="font-weight:600">What to do:</b> ${esc(s.fix)}${extra(s)}</div>` : ""}</div></div>`).join("");
    modal(`<h3>Setup guide</h3><p class="sub">${bad ? "NAB found something that is not set up yet. I'll walk you through it." : "Everything is set up ✓"}</p>${list}<div class="modal-actions"><button class="btn" id="frSkip">${bad ? "Skip for now" : "Close"}</button><button class="btn" id="frRe">Check again</button>${bad && bad.id === "logos" ? '<button class="btn pri" id="frGo">Open Newspapers</button>' : ""}${bad && bad.id === "rules" ? '<button class="btn pri" id="frGo">Open rules</button>' : ""}${bad ? "" : '<button class="btn pri" id="frOk">Done</button>'}</div>`, (c, close) => {
      $("#frSkip").onclick = () => { close(); api("firstrun_done"); };
      $("#frRe").onclick = async () => { const n = await api("firstrun"); close(); draw(n, auto); };
      const ok = $("#frOk"); if (ok) ok.onclick = () => { close(); api("firstrun_done"); };
      const go = $("#frGo"); if (go) go.onclick = () => { close(); MAIN.show("settings"); SETTINGS.go(bad.id === "logos" ? "papers" : "rules"); };
      const sv = $("#frFolderOk"); if (sv) sv.onclick = async () => { const v = $("#frFolder").value.trim(); if (!v) return; const x = await api("set_options", { base_root: v }); close(); toast("Save folder set", "ok", 1500); const n = await api("firstrun"); draw(n, auto); };
      const fe = $("#frExt"); if (fe) fe.onclick = () => { close(); api("firstrun_done"); extSetup(); };
      const cp = $("#frCopy"); if (cp) cp.onclick = () => { try { navigator.clipboard.writeText(cp.dataset.t); toast("Copied", "ok", 1000); } catch (e) { } };
    });
  }
  function extra(s) {
    if (s.id === "folder") return `<div style="display:flex;gap:6px;margin-top:6px"><input id="frFolder" value="${esc(s.path || "")}" style="flex:1;height:32px;border-radius:8px;border:1px solid var(--line);background:var(--surf2);color:var(--txt);padding:0 8px"><button class="btn pri" id="frFolderOk">Use</button></div>`;
    if (s.id === "ext") return `<div style="margin-top:6px"><button class="btn pri" id="frExt">Set up now</button></div>`;
    if (s.id === "webview") return `<div style="margin-top:6px"><button class="btn" id="frCopy" data-t="https://developer.microsoft.com/microsoft-edge/webview2/">Copy download link</button></div>`;
    return "";
  }

  // ───────────── learn this paper ─────────────
  const asked = new Set();
  on("detect_miss", (ev) => {
    const src = ev.src || ""; const m = src.match(/^(?:https?:\/\/)?([^\/\s?#]+)/); const host = m && m[1].includes(".") ? m[1].replace(/^www\./, "") : "";
    if (!host || asked.has(host) || !X.st) return; asked.add(host);
    const c = $("#learnCard"); if (!c || !c.classList.contains("hidden")) return;
    c.classList.remove("hidden");
    c.innerHTML = "<b>Which paper is this?</b><div style='margin-top:4px'>NAB doesn't know <b>" + esc(host) + "</b> yet.</div><select id='lpSel' style='margin-top:6px;width:100%;height:32px;border-radius:8px;border:1px solid var(--line);background:var(--surf2);color:var(--txt)'>" + X.st.papers.map(p => "<option value='" + esc(p) + "'>" + esc(C.clean(p)) + "</option>").join("") + "</select><div class='modal-actions' style='margin-top:8px'><button class='btn' id='lpNo'>Not now</button><button class='btn pri' id='lpYes'>Remember</button></div>";
    $("#lpYes").onclick = async () => { const r = await api("learn_paper", { text: src, paper: $("#lpSel").value }); c.classList.add("hidden"); toast(r.ok ? "Learned: " + r.key + " → " + C.clean($("#lpSel").value) : (r.error || "Failed"), r.ok ? "ok" : "warn", 2500); MAIN.reload && MAIN.reload(); };
    $("#lpNo").onclick = () => c.classList.add("hidden");
    setTimeout(() => c.classList.add("hidden"), 25000);
  });

  // ───────────── missed-save guard / save info ─────────────
  on("missed_save", (ev) => toast("⏰ " + ev.n + " clip" + (ev.n > 1 ? "s are" : " is") + " still unsaved", "warn", 8000));
  on("saved", (ev) => {
    const f = (ev.files || []); if (!f.length) return; const kb = Math.max.apply(null, f.map(x => x.kb || 0)); const el = $("#stSize"); if (!el) return;
    const tail = (f[0].scaled && f[0].scaled < 1 ? " · scaled " + Math.round(f[0].scaled * 100) + "%" : "") + (f[0].q ? " · q" + f[0].q : "");
    if (document.body.classList.contains("slow") || (window.matchMedia && matchMedia("(prefers-reduced-motion:reduce)").matches)) { el.textContent = kb + " KB" + tail; return; }
    { const t0 = performance.now(), from = Math.round(kb * 0.4); const step = (n) => { const k = Math.min(1, (n - t0) / 380), v = Math.round(from + (kb - from) * (1 - Math.pow(1 - k, 3))); el.textContent = v + " KB" + tail; if (k < 1) requestAnimationFrame(step); }; requestAnimationFrame(step); return; }
    el.textContent = kb + " KB" + (f[0].scaled && f[0].scaled < 1 ? " · scaled " + Math.round(f[0].scaled * 100) + "%" : "") + (f[0].q ? " · q" + f[0].q : "");
  });

  // ───────────── focus rules ─────────────
  // 1. a clicked toolbar/panel button never keeps the keyboard (Enter/Space would re-press it)
  document.addEventListener("click", (e) => {
    const b = e.target.closest && e.target.closest("button"); if (!b || b.closest("#modal,#cmdk,#drawer,#paperMenu,.settings,.tool")) return;
    setTimeout(() => { if (document.activeElement === b) { const s = $("#stage"); s && s.focus(); } }, 0);
  }, true);
  // 2. a new clip arrives while a category is armed → straight to the Page box
  let lastN = 0;
  on("clips", (ev) => {
    const n = ev.n || 0;
    if (n > lastN && window.CLIPX && CLIPX.S.armed.length && MAIN.view === "clip" && !(document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))) setTimeout(() => CLIPX.focusMeta("page"), 60);
    lastN = n;
  });

  // ───────────── recent saves: keyboard ─────────────
  document.addEventListener("keydown", (e) => {
    const d = $("#drawer"); if (!d || d.classList.contains("hidden") || !$("#modal").classList.contains("hidden")) return;
    if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    const rows = $$("#drawerBody .rs"); if (!rows.length) return;
    let i = rows.findIndex(r => r.classList.contains("kb")); const k = e.key.toLowerCase();
    const mark = (n) => { rows.forEach(r => r.classList.remove("kb")); i = Math.max(0, Math.min(rows.length - 1, n)); rows[i].classList.add("kb"); rows[i].scrollIntoView({ block: "nearest" }); };
    if (e.key === "ArrowDown") { e.preventDefault(); mark(i + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mark(i < 0 ? 0 : i - 1); }
    else if (i >= 0 && k === "r") { e.preventDefault(); e.stopPropagation(); rows[i].querySelector('[data-a="retag"]').click(); }
    else if (i >= 0 && k === "o") { e.preventDefault(); rows[i].querySelector('[data-a="show"]').click(); }
    else if (i >= 0 && e.key === "Enter") { e.preventDefault(); rows[i].querySelector('[data-a="reopen"]').click(); }
    else if (i >= 0 && e.key === "Delete") { e.preventDefault(); rows[i].querySelector('[data-a="del"]').click(); }
    else if (e.key === "Escape") { d.classList.add("hidden"); }
  }, true);

  // ───────────── extra commands (Ctrl+K) ─────────────
  // ── batch folder mode: open page images one after another; the next one loads after each save ──
  const BATCH = { on: false };
  function batchStart() {
    C.modal(`<h3>Batch: open a folder of images</h3><p class="sub">NAB opens the first image. After you save it, the next one opens by itself. Paste the folder path.</p><div class="field"><input id="bF" placeholder="D:\\Papers\\08-11-2026\\Daily Star" style="width:100%"></div><div class="modal-actions"><button class="btn" id="bNo">Cancel</button><button class="btn pri" id="bOk">Start</button></div>`, (cd, close) => {
      $("#bNo").onclick = close; $("#bF").focus();
      const go = async () => { const r = await api("batch_start", { folder: $("#bF").value }); if (!r.ok) return C.toast(r.error, "warn", 4000); close(); BATCH.on = !r.done && r.left > 0; C.toast("Batch " + r.n + " of " + r.total + ": " + r.name + (r.left ? "" : " (last one)"), "ok", 3500); };
      $("#bOk").onclick = go; $("#bF").addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    });
  }
  async function batchNext(auto) {
    const r = await api("batch_next");
    if (!r.ok) { if (!auto) C.toast(r.error, "warn", 3000); BATCH.on = false; return; }
    if (r.done) { BATCH.on = false; C.toast("Batch finished", "ok", 3000); return; }
    BATCH.on = r.left > 0; C.toast("Batch " + r.n + " of " + r.total + ": " + r.name + (r.left ? "" : " (last one)"), "ok", 3000);
  }
  on("saved", () => { if (BATCH.on) setTimeout(() => batchNext(true), 600); });

  X.commands = function (add) {
    add("Batch: open a folder of images", "", batchStart);
    add("Batch: next image", "", () => batchNext(false));
    add("Batch: stop", "", async () => { await api("batch_stop"); BATCH.on = false; C.toast("Batch stopped", "ok", 2000); });
    add("Setup guide (check what is missing)", "", () => guide(false));
    add("Set up the browser extension", "", () => extSetup());
    add("Sajeeb: show or hide the mascot", "", () => { const on = !((window.M && M.st && M.st.ui) || {}).mascot; api("ui_set", { mascot: on }); if (M.st && M.st.ui) M.st.ui.mascot = on; if (window.RIKO) RIKO.setEnabled(on); });
    add("Sajeeb: change outfit", "", () => { if (window.RIKO) RIKO.outfit(); });
    if (window.RIKO && RIKO.plus) RIKO.plus.commands.forEach(([n, f]) => add(n, "", f));
    if (window.RIKO && RIKO.care) RIKO.care.commands.forEach(([n, f]) => add(n, "", f));
    if (window.RIKO && RIKO.fun) RIKO.fun.commands.forEach(([n, f]) => add(n, "", f));
    add("Next category (keep page and size)", "Alt ]", () => window.CLIP_switchCat && CLIP_switchCat(1));
    add("Previous category (keep page and size)", "Alt [", () => window.CLIP_switchCat && CLIP_switchCat(-1));
    add("Sajeeb: dance!", "", () => { if (window.RIKO) RIKO.command("dance"); });
    add("Copy last saved clip to clipboard", "Ctrl Shift C", () => CLIPX.copyLast());
    add("Open last saved clip in its folder", "Ctrl Shift F", () => api("open_last_folder"));
    add("Repeat last Page / Position / Size", "Ctrl Enter", () => CLIPX.repeatLast(false));
    add("Selection: invert", "Ctrl Shift I", () => CLIPX.invertSel());
    add("Straighten tilted clip", "", () => { const b = $('[data-f="deskew"]'); b && b.click(); });
    add("Clean-up: erase this paper's remembered areas", "Ctrl Shift K", () => $("#cuApply").click());
    add("Clean-up: remember selected area for this paper", "", () => $("#cuSave").click());
    add("Detection test (what does NAB see right now?)", "", () => detectTest());
    add("Backup settings now", "", async () => { const r = await api("backup_now"); toast(r.ok ? "Backup saved: " + r.name : (r.error || "Failed"), r.ok ? "ok" : "warn", 2500); });
    add("Google upload: turn on / off", "", async () => { const on_ = !(X.st && X.st.settings.upload_enabled); await api("set_options", { upload_enabled: on_ }); MAIN.reload(); toast("Google upload " + (on_ ? "ON" : "OFF"), "ok", 1800); });
  };
  async function detectTest() {
    const r = await api("detect_test");
    modal("<h3>Detection test</h3><div class='kv'><span>Window title</span><span>" + esc(r.title || "—") + "</span></div><div class='kv'><span>Tab address</span><span style='word-break:break-all'>" + esc(r.url || "— (extension not sending)") + "</span></div><div class='kv'><span>Extension</span><span>" + esc(r.ext.text) + "</span></div><div class='kv'><span>Paper picked</span><b>" + esc(r.paper || "none") + "</b></div><div class='kv'><span>Because</span><span>" + esc(r.how ? r.how + (r.detail ? " · " + r.detail : "") : "—") + "</span></div><div class='kv'><span>Page read</span><b>" + esc(r.page || "—") + "</b></div><p class='sub'>Tip: click a news tab first, then press Ctrl+K → Detection test. (This test uses the last browser window NAB saw.)</p><div class='modal-actions'><button class='btn pri' id='dtOk'>OK</button></div>", (c, close) => { $("#dtOk").onclick = close; });
  }
  X.detectTest = detectTest;
})();
