// main.js — boot, login gate, top bar, command bar, recent saves, status bar, events.
(function () {
  const { $, $$, esc, api, url, on, toast, modal, debounce } = C;
  const M = window.MAIN = { view: "clip", st: null };
  let timers = {};

  // ───────────────────────── boot ─────────────────────────
  const hideSkel = () => { const k = document.getElementById("skel"); if (k) { k.classList.add("off"); setTimeout(() => k.remove(), 300); } };
  setTimeout(hideSkel, 25000);                                   // never leave the skeleton up for ever
  async function boot() {
    try { await boot0(); } finally { hideSkel(); if (window.INTRO) INTRO.ready(); }
  }
  async function boot0() {
    C.connect();
    const s0 = await api("state_min");
    if (s0.ui && s0.ui.theme) C.theme(s0.ui.theme);
    if (s0.ui && s0.ui.lang) { LANG = s0.ui.lang; applyI18n(); }
    if (!s0.authorized) {
      const pre = await api("login_precheck"), dm = (s0.ui && s0.ui.auth_default) || "ask";
      if (pre.auto) { showGate(s0.login, pre.auto); api("login_begin", { auto: true }); }
      else if (dm === "group" || dm === "owner") { showGate(s0.login, "", dm); api("login_begin", { mode: dm }); }
      else showChoice(pre, s0.login);
    }
    else await start();
  }
  function showGate(last, auto, mode) {
    const g = $("#gate"); g.classList.remove("hidden"); document.body.classList.add("locked");
    const who = auto === "remember" ? "Welcome back — this PC is remembered for today." : auto === "regrace" ? "Welcome back — reopening your session." : mode === "owner" ? "A login request was sent to the owner on Telegram." : "A login request was sent to the Telegram group.";
    g.innerHTML = '<div class="card"><div class="big"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg></div><h2>' + t("lock_title") + '</h2><p>' + who + '</p><div class="status-line" id="gStatus" style="color:#f59e0b">' + t("waiting") + '</div><p id="gTimer"></p>' + (auto ? "" : '<p>Waiting for <b>Allow</b> or <b>Deny</b> on Telegram.</p>') + '</div>';
    if (last) onLogin(last);
  }
  function showChoice(pre, last) {
    const g = $("#gate"); g.classList.remove("hidden"); document.body.classList.add("locked");
    g.innerHTML = '<div class="card gate-ch"><div class="big"><svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg></div><h2>' + t("lock_title") + '</h2><p>How should this login be approved?</p>' +
      '<div class="gate-btns"><button class="gate-b' + (pre.mode === "group" ? " last" : "") + '" id="gcG"><b>Authorize by group</b><small>Anyone in the Telegram group can approve</small></button>' +
      '<button class="gate-b' + (pre.mode === "owner" ? " last" : "") + '" id="gcO"><b>Authorize by owner</b><small>Only the owner can approve, in a private chat</small></button></div>' +
      '<input id="gcR" class="gate-r" maxlength="140" placeholder="Reason (optional) — shown to whoever approves" autocomplete="off"><label class="gate-k"><input type="checkbox" id="gcK"> Remember my choice</label></div>';
    const go = (mode) => { const reason = $("#gcR").value.trim(), keep = $("#gcK").checked; if (keep) api("ui_set", { auth_default: mode }); showGate(last, "", mode); api("login_begin", { mode, reason }); };
    $("#gcG").onclick = () => go("group"); $("#gcO").onclick = () => go("owner");
    $("#gcR").addEventListener("keydown", (e) => { if (e.key === "Enter") go(pre.mode === "owner" ? "owner" : "group"); });
  }
  let loginTimer = null;
  function onLogin(ev) {
    const g = $("#gStatus"); if (!g) return;
    if (ev.stage === "waiting") {
      let left = ev.timeout || 120; clearInterval(loginTimer);
      const tick = () => { const el = $("#gTimer"); if (el) el.textContent = "Auto-denied in " + Math.max(0, left--) + "s"; };
      tick(); loginTimer = setInterval(tick, 1000);
    } else { clearInterval(loginTimer); const el = $("#gTimer"); if (el) el.textContent = "";
      if (ev.stage === "granted") { g.style.color = "#22c55e"; g.textContent = "✅ " + t("granted"); setTimeout(start, 600); }
      else { g.style.color = "#ef4444"; g.textContent = "⛔ " + t("denied"); } }
  }
  on("login", onLogin);

  let started = false;
  async function start() {
    if (started) return; started = true;
    $("#gate").classList.add("hidden"); document.body.classList.remove("locked");
    const st = await api("state"); M.st = st; CLIP.st = st;
    if (st.ui.theme) C.theme(st.ui.theme); if (st.ui.lang) { LANG = st.ui.lang; applyI18n(); }
    $("#stVer").textContent = "v" + st.version + " · " + st.pc;
    setTimeout(() => { try { if (window.TOOLS && TOOLS.subs) { if (!TOOLS.subs._m) { TOOLS.subs._m = true; TOOLS.subs.mount($("#view-subs")); } TOOLS.subs.remind && TOOLS.subs.remind(); } } catch (e) {} }, 2500);
    renderTop(); CLIPUI.init(st); renderStatusCounts(); logoPreload();
    if (window.SETTINGS) SETTINGS.init();
    if (window.EXTRAS) EXTRAS.onStart(st);
  }
  M.reload = () => reloadState();
  async function reloadState() { const st = await api("state"); M.st = st; CLIP.st = st; renderTop(); CLIPUI.setState(st); renderStatusCounts(); if (window.EXTRAS) EXTRAS.onState(st); return st; }

  // ───────────────────────── top bar ─────────────────────────
  function renderTop() {
    const st = M.st; $("#paperName").textContent = st.paper_clean || "—";
    $("#paperLogo").src = url("/logo?n=" + encodeURIComponent(st.paper)); $("#paperLogo").onerror = function () { this.style.visibility = "hidden"; }; $("#paperLogo").onload = function () { this.style.visibility = "visible"; };
    const d = new Date(st.date + "T00:00:00"); $("#dateTxt").textContent = d.toLocaleDateString(LANG === "bn" ? "bn-BD" : "en-GB", { day: "numeric", month: "short", year: "numeric", weekday: "short" });
    $("#dateInput").value = st.date;
  }
  function logoPreload() { /* warms logo requests so the dropdown is instant */ }
  // own calendar popup (the browser's date picker does not open reliably inside the app window)
  function pickDate(cur, done) {
    const old = document.getElementById("calPop"); if (old) { old.remove(); return; }
    const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    let v = new Date((cur || iso(new Date())) + "T00:00:00"); if (isNaN(v)) v = new Date();
    let y = v.getFullYear(), m = v.getMonth(); const sel = iso(v), today = iso(new Date());
    const pop = document.createElement("div"); pop.id = "calPop";
    pop.style.cssText = "position:fixed;z-index:9999;top:50px;left:50%;transform:translateX(-50%);width:288px;padding:12px;background:var(--surf,#131521);border:1px solid var(--line,#292d43);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.45);color:var(--txt,#f3f4fa);font-size:13px";
    document.body.appendChild(pop);
    const close = () => { pop.remove(); document.removeEventListener("mousedown", out, true); document.removeEventListener("keydown", key, true); };
    const out = (e) => { if (!pop.contains(e.target) && e.target.id !== "dateBtn" && !e.target.closest("#dateBtn")) close(); };
    const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    function draw() {
      const first = new Date(y, m, 1), lead = (first.getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
      let h = '<div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><button class="btn" data-n="-1" style="width:30px">&lsaquo;</button><b style="flex:1;text-align:center">' + first.toLocaleDateString("en-GB", { month: "long", year: "numeric" }) + '</b><button class="btn" data-n="1" style="width:30px">&rsaquo;</button></div>';
      h += '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center">' + ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map(x => '<span style="color:var(--dim,#8f93ac);font-size:11px;padding:3px 0">' + x + '</span>').join("");
      for (let i = 0; i < lead; i++) h += "<span></span>";
      for (let d = 1; d <= days; d++) { const k = iso(new Date(y, m, d)); h += '<button data-d="' + k + '" style="height:32px;border-radius:8px;border:1px solid ' + (k === today ? "var(--acc,#5b8cff)" : "transparent") + ';background:' + (k === sel ? "var(--acc,#5b8cff)" : "transparent") + ';color:' + (k === sel ? "#fff" : "inherit") + ';cursor:pointer">' + d + '</button>'; }
      h += '</div><div style="display:flex;gap:6px;margin-top:8px"><button class="btn" data-d="' + today + '" style="flex:1">Today</button><button class="btn" id="calX" style="flex:1">Close</button></div>';
      pop.innerHTML = h;
      pop.querySelectorAll("[data-n]").forEach(b => b.onclick = () => { m += +b.dataset.n; if (m < 0) { m = 11; y--; } if (m > 11) { m = 0; y++; } draw(); });
      pop.querySelectorAll("[data-d]").forEach(b => b.onclick = () => { close(); done(b.dataset.d); });
      pop.querySelector("#calX").onclick = close;
    }
    draw(); setTimeout(() => { document.addEventListener("mousedown", out, true); document.addEventListener("keydown", key, true); }, 0);
  }
  $("#dateBtn").onclick = () => pickDate(M.st && M.st.date, async (d) => { await api("set_date", { date: d }); M.st.date = d; renderTop(); CLIPUI.refresh(true); CLIPUI.updateDock(); });
  $("#dateInput").onchange = async (e) => { await api("set_date", { date: e.target.value }); M.st.date = e.target.value; renderTop(); CLIPUI.refresh(true); CLIPUI.updateDock(); };
  on("date", (ev) => { if (M.st) { M.st.date = ev.date; renderTop(); CLIPUI.refresh(true); CLIPUI.updateDock(); } });
  on("paper", (ev) => { if (M.st) { M.st.paper = ev.paper; M.st.paper_clean = ev.clean; renderTop(); CLIPUI.refresh(true); } });
  on("settings_changed", reloadState); on("state_changed", reloadState);

  // paper menu
  M.paperMenu = function () {
    const menu = $("#paperMenu"); if (!menu.classList.contains("hidden")) { menu.classList.add("hidden"); return; }
    const r = $("#paperBtn").getBoundingClientRect(); menu.style.left = r.left + "px"; menu.style.top = (r.bottom + 6) + "px";
    menu.innerHTML = '<input id="pmSearch" placeholder="Search…" style="width:100%;height:34px;border-radius:9px;border:1px solid var(--line);background:var(--surf2);padding:0 10px;margin-bottom:6px;-webkit-user-select:text;user-select:text"><div id="pmList"></div><div class="mi" id="pmEdit" style="border-top:1px solid var(--line);margin-top:6px;justify-content:center;font-weight:600">Add or edit papers…</div>';
    menu.classList.remove("hidden"); const inp = $("#pmSearch"); inp.focus();
    let hl = 0;
    const draw = () => {
      const q = inp.value.toLowerCase(), list = M.st.papers.filter(p => C.clean(p).toLowerCase().includes(q)); hl = Math.min(hl, Math.max(0, list.length - 1));
      $("#pmList").innerHTML = list.map((p, i) => '<div class="mi' + (p === M.st.paper ? " sel" : "") + (i === hl ? " hl" : "") + '" data-p="' + esc(p) + '"><img loading="lazy" src="' + url("/logo?n=" + encodeURIComponent(p)) + '" onerror="this.style.visibility=\'hidden\'"><span>' + esc(C.clean(p)) + "</span></div>").join("");
      $$("#pmList .mi").forEach(n => n.onclick = () => pick(n.dataset.p));
    };
    $("#pmEdit").onclick = () => { menu.classList.add("hidden"); const b = document.querySelector('[data-view="settings"]'); b && b.click(); setTimeout(() => window.SETTINGS_GO && window.SETTINGS_GO("papers"), 150); };
    const pick = async (p) => { menu.classList.add("hidden"); await api("set_paper", { paper: p }); M.st.paper = p; };
    inp.oninput = () => { hl = 0; draw(); };
    inp.onkeydown = (e) => { const list = $$("#pmList .mi"); if (e.key === "ArrowDown") { hl = Math.min(list.length - 1, hl + 1); draw(); e.preventDefault(); } else if (e.key === "ArrowUp") { hl = Math.max(0, hl - 1); draw(); e.preventDefault(); } else if (e.key === "Enter") { if (list[hl]) pick(list[hl].dataset.p); } else if (e.key === "Escape") { menu.classList.add("hidden"); } e.stopPropagation(); };
    draw();
  };
  $("#paperBtn").onclick = M.paperMenu;
  document.addEventListener("pointerdown", (e) => { const m = $("#paperMenu"); if (!m.classList.contains("hidden") && !e.target.closest("#paperMenu,#paperBtn")) m.classList.add("hidden"); });

  // detection pill, learn card, lock
  on("detected", (ev) => {
    if (M.st) { M.st.paper = ev.paper; M.st.paper_clean = ev.clean; renderTop(); }
    const p = $("#detectPill"); p.className = "pill"; p.style.color = "#22c55e"; p.textContent = "📍 " + ev.clean + "  (" + ev.how + ")"; clearTimeout(timers.det); timers.det = setTimeout(() => p.classList.add("hidden"), 2600); CLIPUI.refresh(true);
  });
  on("detect_miss", (ev) => { const p = $("#detectPill"); p.className = "pill"; p.style.color = "#ef4444"; p.textContent = "⚠ No paper match — tab: " + ev.tab; clearTimeout(timers.det); timers.det = setTimeout(() => p.classList.add("hidden"), 3800); });
  on("learn", (ev) => {
    const c = $("#learnCard"); c.classList.remove("hidden");
    c.innerHTML = "<b>Remember this?</b><div style='margin-top:4px'>Detection picked <b>" + esc(ev.replaces || "nothing") + "</b>.<br>Always choose <b>" + esc(ev.clean) + "</b> for tabs containing:</div><input id='lrnFrag' value='" + esc(ev.fragment) + "' style='width:100%;margin-top:6px;height:32px;border-radius:8px;border:1px solid var(--line);background:var(--surf2);padding:0 8px;-webkit-user-select:text;user-select:text'><div style='color:var(--dim);font-size:11px;margin-top:3px'>" + esc((ev.url || ev.title || "").slice(0, 70)) + "</div><div class='row'><button class='btn pri' id='lrnYes'>Remember</button><button class='btn' id='lrnNo'>Not this one</button></div>";
    $("#lrnYes").onclick = async () => { const r = await api("learn_remember", { fragment: $("#lrnFrag").value, paper: ev.paper }); if (!r.ok) toast(r.error, "warn", 2500); c.classList.add("hidden"); };
    $("#lrnNo").onclick = () => { api("learn_decline", { fragment: ev.fragment }); c.classList.add("hidden"); };
    clearTimeout(timers.lrn); timers.lrn = setTimeout(() => c.classList.add("hidden"), 20000);
  });
  $("#lockBtn").onclick = async () => { const r = await api("lock_tab"); toast(r.msg || r.error, r.ok ? "ok" : "warn", 2800); };
  $("#lockBtn").oncontextmenu = async (e) => { e.preventDefault(); const r = await api("clear_tab_locks"); toast(r.msg, "ok", 2000); };
  $("#overlayBtn").onclick = () => api("window", { action: "overlay" });

  // ───────────────────────── toasts / generic events ─────────────────────────
  on("toast", (ev) => toast(ev.text, ev.kind, ev.ms));
  on("clips", () => CLIPUI.onClips());
  on("saved", (ev) => { if (M.st) M.st.saved_today += ev.n; renderStatusCounts(); if (!$("#drawer").classList.contains("hidden")) loadRecent(); refreshQueue(); });
  on("save_failed", (ev) => toast("Save failed: " + (ev.failed[0] && ev.failed[0].error || ""), "error", 6000));
  on("save_partial", (ev) => toast(ev.failed.length + " categor" + (ev.failed.length > 1 ? "ies" : "y") + " failed to save", "warn", 6000));
  on("snatched", () => { });
  on("recent_changed", () => { if (!$("#drawer").classList.contains("hidden")) loadRecent(); });
  on("broadcast", (ev) => modal("<h3>📣 Message</h3><p style='white-space:pre-wrap;font-size:16px'>" + esc(ev.text) + "</p><div class='modal-actions'><button class='btn pri' id='mOk'>OK</button></div>", (c, close) => { $("#mOk").onclick = close; }));
  on("expiry", (ev) => toast("⚠ " + ev.text, "warn", 9000));
  on("synced", (ev) => { toast("🔄 Synced: " + ev.namespaces.join(", "), "ok", 3000); });
  on("pause", (ev) => { const g = $("#gate"); if (ev.paused) { g.classList.remove("hidden"); document.body.classList.add("locked"); g.innerHTML = '<div class="card"><div class="big">⏸</div><h2>APP PAUSED</h2><p>Send /resume on Telegram to continue.</p></div>'; } else { g.classList.add("hidden"); document.body.classList.remove("locked"); } });
  on("quit", () => { document.body.innerHTML = "<div style='display:flex;height:100vh;align-items:center;justify-content:center;color:#888'>NAB was closed.</div>"; setTimeout(() => window.close(), 300); });

  // ───────────────────────── status bar ─────────────────────────
  on("status", (ev) => { const el = $("#stStatus"); el.textContent = ev.text; el.style.color = ev.color || ""; clearTimeout(timers.st); if (ev.text !== "READY") timers.st = setTimeout(() => { el.textContent = t("ready"); el.style.color = ""; }, 4200); });
  function renderStatusCounts() {
    const st = M.st; if (!st) return; $("#stSaved").textContent = st.saved_today + " " + t("saved"); renderUploadChip(st.pending_uploads, st.upload); renderSync(st.sync);
  }
  function renderUploadChip(pending, up) {
    const b = $("#stUpload"); up = up || {};
    if (up.running) b.textContent = "⬆ uploading… " + (up.done || 0) + (up.current ? " · " + up.current.slice(0, 26) : "");
    else b.textContent = pending ? "⬆ " + pending + " waiting" : "⬆ all uploaded";
    b.style.color = pending && !up.running ? "var(--warn)" : "";
  }
  async function refreshQueue() { const st = await api("state"); M.st.pending_uploads = st.pending_uploads; M.st.upload = st.upload; M.st.sync = st.sync; renderStatusCounts(); }
  on("upload", (ev) => { if (M.st) { M.st.upload = ev; } renderUploadChip(M.st ? M.st.pending_uploads : 0, ev); if (!ev.running) refreshQueue(); });
  $("#stUpload").onclick = async () => { const r = await api("upload_now"); toast(r.ok ? "Uploading today's files…" : r.error, r.ok ? "ok" : "warn", 2500); };
  function renderSync(s) {
    const b = $("#stSync"); if (!s) return;
    let tx = "☁ …"; if (s.no_drive) tx = "☁ no Google key"; else if (s.offline) tx = "☁ offline"; else if (s.time) { const d = new Date(s.time * 1000); tx = "☁ synced " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
    b.textContent = tx; b.style.color = s.no_drive ? "var(--bad)" : "";
  }
  $("#stSync").onclick = async () => { await api("sync_now"); toast("Syncing…", "", 1500); setTimeout(refreshQueue, 4000); };
  setInterval(() => { if (M.st && started) refreshQueue(); }, 30000);

  // updates
  on("update", (ev) => {
    const s = $("#dlStrip");
    if (ev.stage === "downloading") { s.classList.remove("hidden"); s.textContent = "⬇  Downloading update v" + (ev.version || "") + " in background…  " + (ev.pct || 0) + "%"; }
    else if (ev.stage === "ready" || ev.stage === "applying" || ev.stage === "apply_error") {
      s.classList.add("hidden"); const g = $("#gate"); document.body.classList.add("locked");
      if (!$("#uGo") && !$("#uBar")) {
        g.classList.remove("hidden");
        g.innerHTML = '<div class="card upd"><div class="updring"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="44" class="r1"/><circle cx="50" cy="50" r="32" class="r2"/><circle cx="50" cy="50" r="6" class="r3"/></svg></div><h2 id="uT">' + t("update_ready") + '</h2><p>New version <b style="color:#22c55e">v' + esc(ev.version) + '</b></p><p id="uD">The update has been downloaded and is ready to install.<br>You cannot use NAB until it is applied.</p><div class="ubar hidden" id="uBarW"><i id="uBar"></i></div><p id="uMsg"></p><button class="btn pri" id="uGo" style="width:100%;height:46px;font-size:15px">' + t("restart_update") + '</button></div>';
        $("#uGo").onclick = async () => { $("#uGo").disabled = true; $("#uMsg").textContent = "Starting…"; const r = await api("apply_update"); if (!r.ok) { $("#uMsg").textContent = r.error || "Failed"; $("#uGo").disabled = false; } };
      }
      if (ev.stage === "applying") {
        const go = $("#uGo"); if (go) go.classList.add("hidden");
        $("#uBarW").classList.remove("hidden"); $("#uT").textContent = "Updating NAB"; $("#uD").textContent = "Please wait. NAB restarts by itself when this finishes.";
        const bar = $("#uBar"); if (bar) bar.style.width = (ev.pct || 0) + "%"; $("#uMsg").textContent = (ev.msg || "") + "  " + (ev.pct || 0) + "%";
        document.querySelector(".upd").classList.add("busy");
      } else if (ev.stage === "apply_error") {
        const go = $("#uGo"); if (go) { go.classList.remove("hidden"); go.disabled = false; } $("#uBarW").classList.add("hidden");
        document.querySelector(".upd").classList.remove("busy"); $("#uT").textContent = "Update failed"; $("#uMsg").textContent = ev.error || "Could not apply the update. Try again.";
      }
    } else s.classList.add("hidden");
  });

  // ───────────────────────── recent saves drawer ─────────────────────────
  async function loadRecent() {
    const r = await api("recent", { limit: 60 }), body = $("#drawerBody");
    if (!r.items.length) { body.innerHTML = "<div style='color:var(--dim);padding:20px;text-align:center'>Nothing saved yet this session.</div>"; return; }
    body.innerHTML = r.items.map(it => '<div class="rs" data-i="' + it.i + '"><img loading="lazy" src="' + url("/thumb?w=130&p=" + encodeURIComponent(it.path)) + '"><div class="tx"><b>' + esc(it.category) + "</b><small>" + esc(it.time) + " · " + esc(it.paper || "") + "</small><small>Page " + esc(it.page) + " · Pos " + esc(it.pos) + " · " + esc(it.size) + '</small><div class="act"><button class="b" data-a="reopen">↩ Reopen</button><button class="b" data-a="retag">✏ Retag</button><button class="b" data-a="wa">WhatsApp</button><button class="b" data-a="show">📂</button><button class="b" data-a="del">🗑</button></div></div></div>').join("");
    { const first = body.querySelector(".rs"), top = r.items[0].path; if (first && M._rcTop && M._rcTop !== top) first.classList.add("in"); M._rcTop = top; }
    $$("#drawerBody .rs").forEach(row => {
      const it = r.items.find(x => String(x.i) === row.dataset.i);
      row.querySelector('[data-a="reopen"]').onclick = async () => { const rr = await api("reopen", { path: it.path }); if (rr.ok) { $("#drawer").classList.add("hidden"); C.toast(rr.trimmed ? "Reopened - old logo removed, ready to edit" : "Reopened for editing", "ok", 2200); } };
      row.querySelector('[data-a="wa"]').onclick = () => window.WA && WA.sendRecent(it);
      row.querySelector('[data-a="show"]').onclick = () => api("reveal", { path: it.path });
      row.querySelector('[data-a="del"]').onclick = () => modal("<h3>Delete this file?</h3><p>" + esc(it.name) + "</p><div class='modal-actions'><button class='btn' id='mNo'>Cancel</button><button class='btn bad' id='mYes'>Delete</button></div>", (c, close) => { $("#mNo").onclick = close; $("#mYes").onclick = async () => { close(); const x = await api("delete_saved", { i: it.i }); if (!x.ok) toast(x.error, "error", 3000); else loadRecent(); }; });
      row.querySelector('[data-a="retag"]').onclick = () => retag(it);
    });
  }
  function retag(it) {
    modal("<h3>Retag file</h3><div class='field'><label>Paper</label><select id='rtPaper'>" + M.st.papers.map(p => "<option value='" + esc(p) + "'" + (C.clean(p) === it.paper ? " selected" : "") + ">" + esc(C.clean(p)) + "</option>").join("") + "</select></div><div class='field'><label>Page</label><input id='rtPage' value='" + esc(it.page) + "'></div><div class='field'><label>Position (columns)</label><input id='rtPos' value='" + esc(it.pos) + "'></div><div class='field'><label>Size</label><input id='rtSize' value='" + esc(it.size) + "'></div><p style='color:var(--dim);font-size:12px'>Renames the file. The header already printed on the image does not change — use Reopen to re-render it.</p><div class='modal-actions'><button class='btn' id='mNo'>Cancel</button><button class='btn pri' id='mYes'>Rename</button></div>", (c, close) => {
      $("#mNo").onclick = close;
      $("#mYes").onclick = async () => { const m = C.parseMeta($("#rtPage").value + " " + $("#rtPos").value + " " + $("#rtSize").value); if (!m.ok) { toast(m.errors[0] || "Check page / columns / size", "error", 2800); return; } const r = await api("retag", { i: it.i, paper: $("#rtPaper").value, page: m.page, pos: m.cols, size: m.size }); if (!r.ok) toast(r.error, "error", 3000); else { close(); loadRecent(); } };
    });
  }
  M.recent = () => { const d = $("#drawer"); if (d.classList.contains("hidden")) { d.classList.remove("hidden"); loadRecent(); } else d.classList.add("hidden"); };
  $("#recentBtn").onclick = M.recent; $("#drawerX").onclick = () => $("#drawer").classList.add("hidden");

  // ───────────────────────── command bar ─────────────────────────
  function commands() {
    const st = M.st, out = [];
    const add = (label, hint, fn) => out.push({ label, hint, fn });
    add("Paste clip from clipboard", "Ctrl V", () => CLIPUI.paste()); add("Open image file…", "Ctrl O", () => window.CLIP_open && CLIP_open()); add("Open a saved clip…", "Ctrl Shift O", () => M.recent());
    add("Undo", "Ctrl Z", () => CLIPUI.layerCmd("undo")); add("Redo", "Ctrl Y", () => CLIPUI.layerCmd("redo"));
    add("Save to armed category", "Enter", () => CLIPUI.doSave());
    add("Undo last save", "", () => CLIPUI.undoSave());
    [["trim", "Trim empty margins", "Ctrl T"], ["clean", "Remove frame lines", "Ctrl L"], ["pad", "Add white padding", "Ctrl E"], ["sharpen", "Sharpen", ""], ["upscale", "Upscale 2×", ""], ["rotate", "Rotate 90°", ""], ["autocontrast", "Auto contrast", ""], ["grayscale", "Black & white", ""]].forEach(([f, l, h]) => add("Image: " + l, h, () => CLIPUI.filter(f)));
    add("Layers: merge all visible", "Ctrl Shift E", () => CLIPUI.layerCmd("merge_visible")); add("Layers: merge last two side by side", "", () => CLIPUI.layerCmd("merge_side")); add("Layers: swap last two", "Ctrl ←", () => CLIPUI.layerCmd("swap"));
    add("Apply suggested crop", "Enter", () => CLIPUI.applySuggest());
    add("Open last save folder", "Ctrl O", async () => { const r = await api("reveal", {}); if (!r.ok) toast(r.error, "warn", 2200); });
    add("Recent saves", "Ctrl H", M.recent);
    add("Upload today's files now", "", () => $("#stUpload").click());
    add("Build today's PDFs", "", () => { M.show("pdf"); setTimeout(() => { const g = $("#pdGo"); if (g && !g.disabled) g.click(); }, 1300); });
    add("Open PDF Maker", "", () => M.show("pdf")); add("Open Send by mail", "", () => M.show("mail")); add("Open Tracker", "", () => M.show("tracker"));
    add("Open OCR search", "", () => M.show("search")); add("Open Subscriptions", "", () => M.show("subs")); add("Open Screenshot Bot", "", () => M.show("shot")); add("Open PR Value Calculator", "", () => M.show("pr")); add("Open News Hunter", "", () => M.show("hunt")); add("WhatsApp setup", "", () => window.WA && WA.setup());
    add("Open classic NAB window (Batch mode etc.)", "", () => api("launch_tool", { name: "classic" }));
    add("Lock this tab to the current paper 📍", "", () => $("#lockBtn").click());
    add("Show / hide mini overlay", "", () => api("window", { action: "overlay" }));
    add("Settings", "", () => M.show("settings")); add("Settings: Connections (Advanced)", "", () => { M.show("settings"); SETTINGS.go("connections"); });
    add("Toggle light / dark theme", "", () => { const n = document.documentElement.getAttribute("data-mode") === "light" ? "dark" : "light"; C.theme(n); api("ui_set", { theme: n }); });
    [["blue", "Blue"], ["snow", "Snow"], ["shadow", "Shadow Cat"], ["neon", "Neon Cat"]].forEach(([k, n]) => add("Theme: " + n, "", () => { C.theme(k); api("ui_set", { theme: k }); }));
    add("Language: English / বাংলা", "", () => { LANG = LANG === "en" ? "bn" : "en"; applyI18n(); api("ui_set", { lang: LANG }); CLIPUI.updateDock(); CLIPUI.renderCats(); });
    Object.keys(st.categories).forEach(r => { add("Save to: " + r, "category", () => CLIPUI.arm([r], true)); st.categories[r].forEach(s => add("Save to: " + r + " › " + s, "category", () => CLIPUI.arm([r + "/" + s], true))); });
    st.papers.forEach(p => add("Paper: " + C.clean(p), "newspaper", async () => { await api("set_paper", { paper: p }); }));
    if (window.EXTRAS) EXTRAS.commands(add);
    return out;
  }
  M.cmdk = function () {
    const box = $("#cmdk"), inp = $("#cmdkInput"), list = $("#cmdkList"); box.classList.remove("hidden"); box.classList.remove("open"); void box.offsetWidth; box.classList.add("open"); inp.value = ""; inp.focus();
    const all = commands(); let shown = all, hl = 0;
    const draw = () => { list.innerHTML = shown.slice(0, 60).map((c, i) => '<div class="ci' + (i === hl ? " hl" : "") + '" data-i="' + i + '"><span>' + esc(c.label) + "</span><small>" + esc(c.hint) + "</small></div>").join(""); $$("#cmdkList .ci").forEach(n => { n.onclick = () => run(+n.dataset.i); }); const h = $("#cmdkList .hl"); if (h) h.scrollIntoView({ block: "nearest" }); };
    const run = (i) => { const c = shown[i]; box.classList.add("hidden"); if (c) setTimeout(c.fn, 0); };
    inp.oninput = () => { const q = inp.value.toLowerCase().split(/\s+/).filter(Boolean); shown = q.length ? all.filter(c => q.every(w => c.label.toLowerCase().includes(w))) : all; hl = 0; draw(); };
    inp.onkeydown = (e) => { if (e.key === "ArrowDown") { hl = Math.min(shown.length - 1, hl + 1); draw(); e.preventDefault(); } else if (e.key === "ArrowUp") { hl = Math.max(0, hl - 1); draw(); e.preventDefault(); } else if (e.key === "Enter") run(hl); else if (e.key === "Escape") box.classList.add("hidden"); e.stopPropagation(); };
    box.onpointerdown = (e) => { if (e.target === box) box.classList.add("hidden"); };
    draw();
  };
  $("#cmdBtn").onclick = M.cmdk;
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); M.cmdk(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "h" && !e.shiftKey && started) { e.preventDefault(); M.recent(); }
    else if (e.key === "F11") { e.preventDefault(); api("window", { action: "fullscreen" }); }
  });

  // ───────────────────────── nav / views ─────────────────────────
  M.show = function (v) {
    M.view = v; $$(".view").forEach(n => n.classList.add("hidden")); $("#view-" + v).classList.remove("hidden");
    $$("#rail .rb[data-view]").forEach(b => b.classList.toggle("active", b.dataset.view === v));
    $("#dock").classList.toggle("hidden", v !== "clip"); if (v === "clip") setTimeout(() => CLIPUI.onShow(), 0); if (v === "settings") SETTINGS.render();
    if (window.TOOLS && TOOLS[v]) { const T = TOOLS[v]; if (!T._m) { T._m = true; T.mount($("#view-" + v)); } T.show && T.show(); }
  };
  $$("#rail .rb[data-view]").forEach(b => b.onclick = () => M.show(b.dataset.view));
  $$("#rail .rb[data-tool]").forEach(b => b.onclick = async () => { const r = await api("launch_tool", { name: b.dataset.tool }); if (!r.ok) toast(r.error || "Could not open", "error", 3000); else toast("Opening " + b.title + "…", "", 1500); });

  // ───────────────────────── closing ─────────────────────────
  on("close_request", async () => {
    try { if (window.TOOLS && TOOLS.tracker && (await TOOLS.tracker.endPrompt()) === "cancel") return; } catch (e) {}
    const sm = await api("close_summary");
    if (!sm.pending) return finishClose("skip");
    let left = 30, iv;
    modal("<h3>📁 " + t("end_title") + "</h3><p>" + sm.saves + " file(s) saved today · " + sm.pending + " not uploaded yet.</p><div class='modal-actions'><button class='btn pri' id='cNow'>" + t("upload_now_b") + "</button><button class='btn' id='cLater'>" + t("next_time") + "</button><button class='btn' id='cSkip'>" + t("skip") + "</button></div><p id='cCnt' style='color:var(--dim);font-size:12px;text-align:right'>Auto-skipping in 30s…</p><div style='text-align:right'><button class='linkish' id='cStay'>← Back to NAB</button></div>", (c, close) => {
      const done = (ch) => { clearInterval(iv); close(); finishClose(ch); };
      $("#cNow").onclick = () => done("now"); $("#cLater").onclick = () => done("later"); $("#cSkip").onclick = () => done("skip"); $("#cStay").onclick = () => { clearInterval(iv); close(); };
      iv = setInterval(() => { left--; $("#cCnt").textContent = "Auto-skipping in " + left + "s…"; if (left <= 0) done("skip"); }, 1000);
    });
  });
  async function finishClose(choice) { try { modal("<h3>Closing NAB…</h3><div class=\"sk-l\" style=\"height:14px;width:70%\"></div>"); } catch (e) { } await api("quit", { upload: choice }); }

  // external window actions pushed from the Windows side
  on("hotkey_hint", () => { });
  window.addEventListener("load", boot);
  M.reloadState = reloadState; M.renderTop = renderTop;
})();
