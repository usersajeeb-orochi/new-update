// tool_tracker.js — Newspaper Tracker + Subscriptions as in-app screens.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast, modal } = C;
  const T = { el: null, tab: "check", date: null, papers: [], prices: {}, cfg: {}, checks: new Set(), ov: {}, entry: {}, detect: { matched: {}, unknown: {} }, scanTok: 0, my: 0, mm: 0 };
  const iso = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  const fmt = (n) => "৳" + (Math.round(n * 100) / 100).toFixed(2);
  const TABS = [["check", "Checklist"], ["month", "Calendar"], ["heat", "Heatmap"], ["papers", "Papers & prices"], ["set", "Settings"]];

  function mount(el) {
    T.el = el; el.innerHTML = '<div class="tk"><div class="tk-tabs" id="tkTabs"></div><div class="tk-body" id="tkBody"></div></div>';
    $("#tkTabs").innerHTML = TABS.map(([k, n]) => `<button data-k="${k}">${n}</button>`).join(""); $$("#tkTabs button").forEach(b => b.onclick = () => go(b.dataset.k));
    $("#tkTabs").insertAdjacentHTML("beforeend", '<span class="tk-sp"></span><button id="tkSync" class="tk-act" title="Read the latest entries from the Google Sheet (other PCs)">Sync from sheet</button><button id="tkOpen" class="tk-act" title="Open the Google Sheet in your browser">Open sheet</button>');
    $("#tkOpen").onclick = async () => { const r = await api("tracker_open_sheet"); if (r && r.ok === false) toast(r.error || "Could not open the sheet", "warn", 3000); };
    $("#tkSync").onclick = () => { const b = $("#tkSync"); b.disabled = true; b.textContent = "Syncing..."; api("tracker_sync", { months: 3 }); };
    on("tool", (ev) => {
      if (ev.tool !== "tracker") return;
      if (ev.stage === "pulled") {
        const b = $("#tkSync"); if (b) { b.disabled = false; b.textContent = "Sync from sheet"; }
        if (ev.ok === false) { if (ev.manual) toast("Sync failed: " + (ev.error || "unknown error"), "warn", 5000); return; }
        const n = (ev.changed || []).length, df = (ev.differ || []).length, pa = (ev.papers_added || []).length;
        if (n || pa) {
          toast("Synced " + n + " day(s) from the sheet" + (pa ? " and " + pa + " paper(s)" : "") + (df ? " - " + df + " day(s) differ from the sheet" : ""), "ok", 4000);
          if (pa) api("tracker_load").then(r => { T.papers = r.papers; });
          if (T.tab === "month") vMonth(); else if (T.tab === "check" && (ev.changed || []).includes(T.date)) loadDay(false); else if (T.tab === "heat" || T.tab === "papers") go(T.tab);
        } else if (ev.manual) toast(df ? "Up to date. " + df + " day(s) differ from the sheet (kept your version)" : "Already up to date", "ok", 3000);
        return;
      }
      if (ev.stage === "synced") { if (ev.errors && ev.errors.length) toast("⚠ " + ev.errors.join(" | "), "warn", 6000); else toast("Synced to Google Sheet & Telegram ✓", "ok", 2200); }
      if (ev.stage === "heatmap_pushed") toast(ev.ok ? "Pushed → " + ev.title + " ✓" : "❌ " + ev.error, ev.ok ? "ok" : "error", 4000);
    });
  }
  async function show() {
    const r = await api("tracker_load"); T.papers = r.papers; T.prices = r.prices; T.cfg = r.cfg; T.today = r.today;
    if (!T.date) { T.date = r.today; const d = new Date(); T.my = d.getFullYear(); T.mm = d.getMonth() + 1; }
    go(T.tab);
  }
  function go(k) { T.tab = k; $$("#tkTabs button").forEach(b => b.classList.toggle("on", b.dataset.k === k)); ({ check: vCheck, month: vMonth, heat: vHeat, papers: vPapers, set: vSet })[k](); }
  const body = () => $("#tkBody");

  // ───────── Checklist ─────────
  async function loadDay(scan) {
    const r = await api("tracker_day", { date: T.date }); T.entry = r.entry || {}; T.mstat = r.month;
    const st = T.entry.status || "", rec = new Set(T.entry.received || []);
    T.checks = (st === "submitted" || rec.size) ? rec : new Set(); T.ov = {};
    const sp = T.entry.prices || {}; for (const p in sp) { if (Math.abs((sp[p] || 0) - (T.prices[p] || 0)) > 0.001) T.ov[p] = String(sp[p]); }
    T.detect = { matched: {}, unknown: {} };
    drawCheck();
    if (!rec.size && st !== "off_day" && st !== "submitted" && scan !== false) scanDay();
  }
  async function scanDay() {
    const tok = ++T.scanTok; $("#tkMsg") && ($("#tkMsg").textContent = "🔎 Scanning clips…");
    const r = await api("tracker_scan", { date: T.date, papers: T.papers }); if (tok !== T.scanTok) return;
    T.detect = { matched: r.matched || {}, unknown: r.unknown || {} }; for (const p in T.detect.matched) T.checks.add(p);
    drawCheck(); const n = Object.keys(T.detect.matched).length;
    $("#tkMsg").textContent = n ? `🔎 Auto-ticked ${n} paper(s) from ${Object.values(T.detect.matched).reduce((a, b) => a + b, 0)} clip(s)` : "🔎 No clips found for this date";
    drawUnknown();
  }
  function summary() { const rec = T.papers.filter(p => T.checks.has(p)); const tot = rec.reduce((s, p) => s + effPrice(p), 0); return { rec: rec.length, miss: T.papers.length - rec.length, tot }; }
  const effPrice = (p) => { const o = parseFloat(T.ov[p]); return isNaN(o) ? (T.prices[p] || 0) : o; };
  function vCheck() { body().innerHTML = '<div id="tkCheck"></div>'; loadDay(); }
  function drawCheck() {
    const d = new Date(T.date + "T00:00:00"), isToday = T.date === T.today, st = T.entry.status || "";
    const badge = st === "off_day" ? "🏖 OFF DAY" : st === "auto_missed" ? "❓ NOT SUBMITTED" : st === "submitted" ? "✅ SUBMITTED" : "";
    const s = summary(), ms = T.mstat || {};
    $("#tkCheck").innerHTML = `
      <div class="tk-bar"><button class="btn" id="dPrev">◀</button><div class="tk-date"><b>${isToday ? "TODAY — " : ""}${d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</b> <span class="tag">${badge}</span></div><button class="btn" id="dNext" ${isToday ? "disabled" : ""}>▶</button><input type="date" id="dPick" value="${T.date}" max="${T.today}"><button class="btn" id="dToday">Today</button><span class="grow"></span>
        <span class="tk-month">${new Date(T.date + "T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "numeric" })}: <b>${fmt(ms.total || 0)}</b> · ${ms.submitted || 0} sent · ${ms.off || 0} off · ${ms.missed || 0} missed</span></div>
      <div class="tk-sum"><b id="tkSum">✅ ${s.rec} &nbsp; ❌ ${s.miss} &nbsp; | &nbsp; ${fmt(s.tot)}</b><span id="tkMsg" class="tag"></span><span class="grow"></span><button class="btn" id="allOn">Tick all</button><button class="btn" id="allOff">Clear</button><button class="btn" id="rescan">🔎 Scan clips</button></div>
      <div id="tkUnk"></div>
      <div class="tk-grid" id="tkGrid">${T.papers.map(p => { const on_ = T.checks.has(p), n = T.detect.matched[p]; return `<div class="tk-card ${on_ ? "on" : ""}" data-p="${esc(p)}"><span class="ck">${on_ ? "✓" : ""}</span><span class="nm">${esc(C.clean(p))}${n ? ` <i>${n} clip${n > 1 ? "s" : ""}</i>` : ""}</span><span class="pr">৳ <input class="ovp" value="${esc(T.ov[p] != null ? T.ov[p] : "")}" placeholder="${(T.prices[p] || 0).toFixed(2)}" title="Price override for this day"></span></div>`; }).join("")}</div>
      <div class="tk-foot"><button class="btn" id="offBtn">🏖 Off day</button><span class="grow"></span><button class="btn pri" id="subBtn">✅ Submit day</button></div>`;
    $("#dPrev").onclick = () => shift(-1); $("#dNext").onclick = () => shift(1); $("#dToday").onclick = () => { T.date = T.today; loadDay(); };
    $("#dPick").onchange = (e) => { if (e.target.value) { T.date = e.target.value; loadDay(); } };
    $("#allOn").onclick = () => { T.papers.forEach(p => T.checks.add(p)); drawCheck(); }; $("#allOff").onclick = () => { T.checks.clear(); drawCheck(); }; $("#rescan").onclick = scanDay;
    $$(".tk-card").forEach(c => { const p = c.dataset.p; c.onclick = (e) => { if (e.target.closest(".ovp")) return; if (T.checks.has(p)) T.checks.delete(p); else T.checks.add(p); c.classList.toggle("on", T.checks.has(p)); c.querySelector(".ck").textContent = T.checks.has(p) ? "✓" : ""; sumUpd(); };
      c.querySelector(".ovp").oninput = (e) => { T.ov[p] = e.target.value; sumUpd(); }; });
    $("#subBtn").onclick = submit; $("#offBtn").onclick = off; drawUnknown();
  }
  function sumUpd() { const s = summary(); $("#tkSum").innerHTML = `✅ ${s.rec} &nbsp; ❌ ${s.miss} &nbsp; | &nbsp; ${fmt(s.tot)}`; }
  function shift(n) { const d = new Date(T.date + "T00:00:00"); d.setDate(d.getDate() + n); if (iso(d) > T.today) return; T.date = iso(d); loadDay(); }
  function drawUnknown() {
    const u = T.detect.unknown || {}, box = $("#tkUnk"); if (!box) return; const k = Object.keys(u);
    box.innerHTML = k.length ? `<div class="tk-unk">⚠ Clips with names NAB doesn't know: ${k.map(r => `<button class="chip" data-r="${esc(r)}">${esc(r)} (${u[r]}) → map</button>`).join(" ")}</div>` : "";
    $$(".chip", box).forEach(b => b.onclick = () => mapUnknown(b.dataset.r, u[b.dataset.r], drawCheck));
  }
  function mapUnknown(raw, count, done) {
    modal(`<h3>"${esc(raw)}" is actually…</h3><div class="field"><select id="mpSel">${T.papers.map(p => `<option value="${esc(p)}">${esc(C.clean(p))}</option>`).join("")}</select></div><p class="sub">Remembered from now on — this spelling will match automatically.</p><div class="modal-actions"><button class="btn pri" id="mpOk">Save mapping</button><button class="btn" id="mpNo">Cancel</button></div>`, (c, close) => {
      $("#mpNo", c).onclick = () => { close(); done && done(); }; $("#mpOk", c).onclick = async () => { const p = $("#mpSel", c).value; await api("tracker_alias", { raw, paper: p }); if (T.detect && T.detect.matched) { T.detect.matched[p] = (T.detect.matched[p] || 0) + count; delete T.detect.unknown[raw]; T.checks && T.checks.add(p); } close(); done && done(); };
    });
  }
  async function submit() {
    if (T.date < T.today && !confirm("You're editing a past day (" + T.date + "). Save this entry?")) return;
    $("#subBtn").disabled = true; $("#tkMsg").textContent = "⏳ Saving…";
    const r = await api("tracker_submit", { date: T.date, papers: T.papers, received: Array.from(T.checks), overrides: T.ov });
    toast(`Saved — ${r.missing} missing · ${fmt(r.total)}`, "ok", 3000); await loadDay(false);
  }
  async function off() {
    if (T.date < T.today && !confirm("Mark " + T.date + " as an off day?")) return;
    await api("tracker_off", { date: T.date }); toast("🏖 Marked as off day", "ok", 2200); loadDay(false);
  }

  // ───────── Calendar ─────────
  async function vMonth() {
    const r = await api("tracker_month", { year: T.my, month: T.mm }), names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const label = new Date(T.my, T.mm - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
    let cells = ""; for (let i = 0; i < r.first_weekday; i++) cells += '<div class="cal-c empty"></div>';
    for (let d = 1; d <= r.ndays; d++) { const k = T.my + "-" + String(T.mm).padStart(2, "0") + "-" + String(d).padStart(2, "0"), e = r.days[k], st = e ? e.status : "", fut = k > T.today;
      cells += `<div class="cal-c ${st} ${fut ? "fut" : ""}" data-d="${k}"><b>${d}</b><small>${st === "submitted" ? fmt(e.total) + (e.missing ? " · ❌" + e.missing : "") : st === "off_day" ? "OFF" : st === "auto_missed" ? "missed" : ""}</small></div>`; }
    body().innerHTML = `<div class="tk-bar"><button class="btn" id="mP">◀</button><b style="min-width:150px;text-align:center">${label}</b><button class="btn" id="mN">▶</button><span class="grow"></span><span class="tk-month"><b>${fmt(r.stats.total)}</b> · ${r.stats.submitted} sent · ${r.stats.off} off · ${r.stats.missed} missed</span></div>
      <div class="cal">${names.map(n => `<div class="cal-h">${n}</div>`).join("")}${cells}</div><div class="tk-leg"><span class="lg submitted">Submitted</span><span class="lg off_day">Off</span><span class="lg auto_missed">Missed</span><span class="lg">No data</span></div>`;
    $("#mP").onclick = () => { T.mm--; if (T.mm < 1) { T.mm = 12; T.my--; } vMonth(); }; $("#mN").onclick = () => { T.mm++; if (T.mm > 12) { T.mm = 1; T.my++; } vMonth(); };
    $$(".cal-c[data-d]").forEach(c => c.onclick = () => { if (c.dataset.d > T.today) return; T.date = c.dataset.d; go("check"); });
  }

  // ───────── Heatmap ─────────
  async function vHeat() {
    const m = T.hm || new Date().toISOString().slice(0, 7);
    body().innerHTML = `<div class="tk-bar"><label>Month <input id="hmM" value="${m}" style="width:90px"></label><button class="btn" id="hmGo">🔄 Load</button><span id="hmS" class="tag"></span><span class="grow"></span><button class="btn" id="hmPush">📤 Push to Sheet</button></div><div id="hmBox" class="hm-box"></div><div class="tk-leg"><span class="lg h1">1</span><span class="lg h2">2-3</span><span class="lg h3">4-5</span><span class="lg h4">6+</span><span class="lg">0</span></div>`;
    $("#hmGo").onclick = loadHeat; $("#hmPush").onclick = async () => { const r = await api("tracker_heatmap_push"); if (!r.ok) toast(r.error, "warn", 2500); else $("#hmS").textContent = "Pushing…"; }; loadHeat();
  }
  async function loadHeat() {
    T.hm = $("#hmM").value.trim(); $("#hmS").textContent = "Scanning archive…"; const r = await api("tracker_heatmap", { month: T.hm });
    if (!r.ok) { $("#hmS").textContent = r.error; return; } const cnt = {}; r.cells.forEach(([p, c, n]) => cnt[p + "\u0001" + c] = n);
    if (!r.papers.length) { $("#hmBox").innerHTML = '<p class="sub" style="padding:20px">No clips found for ' + esc(r.month) + "</p>"; $("#hmS").textContent = "No data"; return; }
    const cls = (n) => n ? (n >= 6 ? "h4" : n >= 4 ? "h3" : n >= 2 ? "h2" : "h1") : "";
    $("#hmBox").innerHTML = '<table class="t hm"><thead><tr><td>Paper</td>' + r.cats.map(c => `<td title="${esc(c)}">${esc(c.length > 14 ? c.slice(0, 13) + "…" : c)}</td>`).join("") + "<td>Total</td></tr></thead><tbody>" +
      r.papers.map(p => { let tot = 0; const tds = r.cats.map(c => { const n = cnt[p + "\u0001" + c] || 0; tot += n; return `<td class="${cls(n)}">${n || ""}</td>`; }).join(""); return `<tr><td>${esc(C.clean(p))}</td>${tds}<td><b>${tot}</b></td></tr>`; }).join("") + "</tbody></table>";
    $("#hmS").textContent = r.papers.length + " papers";
  }

  // ───────── Papers & prices ─────────
  function vPapers() {
    body().innerHTML = `<p class="sub" style="margin:8px 4px">Newspapers the tracker checks every day, and their default price (৳). Use the price box on a paper card for one-day changes.</p><div class="card" id="ppC"></div><div class="tk-foot"><button class="btn" id="ppAdd">+ Add paper</button><button class="btn" id="ppReset">Reset list</button><span class="grow"></span><button class="btn pri" id="ppSave">Save</button></div>`;
    const c = $("#ppC"), add = (p) => { const r = document.createElement("div"); r.className = "kv"; r.style.gridTemplateColumns = "1fr 100px auto auto auto";
      r.innerHTML = `<input class="pn" value="${esc(p || "")}" placeholder="Paper name"><input class="pp" value="${p ? (T.prices[p] != null ? T.prices[p] : 0) : ""}" placeholder="৳"><button class="btn" style="height:30px;padding:0 8px">↑</button><button class="btn" style="height:30px;padding:0 8px">↓</button><button class="btn" style="height:30px;padding:0 10px">✕</button>`;
      const [u, dn, x] = r.querySelectorAll("button"); u.onclick = () => r.previousElementSibling && c.insertBefore(r, r.previousElementSibling); dn.onclick = () => r.nextElementSibling && c.insertBefore(r.nextElementSibling, r); x.onclick = () => r.remove(); c.appendChild(r); };
    T.papers.forEach(add); $("#ppAdd").onclick = () => { add(""); c.lastChild.querySelector(".pn").focus(); };
    $("#ppReset").onclick = async () => { if (!confirm("Reset to the default newspaper list?")) return; const r = await api("tracker_papers_reset"); T.papers = r.papers; vPapers(); };
    $("#ppSave").onclick = async () => { const names = [], prices = {}; $$(".kv", c).forEach(r => { const n = r.querySelector(".pn").value.trim(); if (n) { names.push(n); prices[n] = r.querySelector(".pp").value; } });
      await api("tracker_papers_save", { papers: names }); await api("tracker_prices_save", { prices }); const r = await api("tracker_load"); T.papers = r.papers; T.prices = r.prices; toast("Saved ✓", "ok", 1500); };
  }

  // ───────── Settings ─────────
  function vSet() {
    const c = T.cfg;
    body().innerHTML = `<div class="card"><h4>Telegram</h4><div class="field"><label>Bot token ${c.has_token ? "(saved — leave empty to keep)" : ""}</label><input id="sTok" type="password" placeholder="${c.has_token ? "••••••••" : "token"}"></div><div class="field"><label>Chat ID</label><input id="sChat" value="${esc(c.tg_chat_id)}"></div><div class="field"><label>Reminder hour (0–23, empty = off)</label><input id="sHr" value="${esc(c.remind_hour)}" style="width:90px"></div></div>
      <div class="card"><h4>Google Sheet</h4><div class="field"><label>Spreadsheet ID</label><input id="sSid" value="${esc(c.gs_sheet_id)}"></div><div class="field"><label>Key file ${c.has_key ? "✓ found" : "⚠ not found"}</label><input id="sKey" value="${esc(c.gs_creds_path)}"></div><div class="row"><button class="btn" id="sTest">Test connection</button><span id="sRes" class="tag"></span></div></div>
      <div class="tk-foot"><span class="grow"></span><button class="btn pri" id="sSave">Save settings</button></div>`;
    $("#sSave").onclick = async () => { await api("tracker_settings_save", { tg_token: $("#sTok").value, tg_chat_id: $("#sChat").value, remind_hour: $("#sHr").value, gs_sheet_id: $("#sSid").value, gs_creds_path: $("#sKey").value }); toast("Settings saved ✓", "ok", 1500); const r = await api("tracker_load"); T.cfg = r.cfg; };
    $("#sTest").onclick = async () => { $("#sRes").textContent = "Testing…"; await $("#sSave").onclick(); const r = await api("tracker_test_sheet"); $("#sRes").textContent = r.ok ? "✅ Connected: " + r.title : "❌ " + r.error; };
  }

  // ───────── end-of-day prompt (called when closing NAB) ─────────
  function endPrompt() {
    return new Promise(async (resolve) => {
      let wc; modal('<h3>Closing NAB…</h3><p class="sub">Checking today\'s papers</p><div class="sk-l" style="height:16px;width:80%"></div><div class="sk-l" style="height:16px;width:60%"></div><div class="sk-l" style="height:16px;width:70%"></div>', (c, close) => { wc = close; });
      let r; try { r = await Promise.race([api("tracker_end_check"), new Promise(res => setTimeout(() => res({ timeout: true }), 8000))]); } catch (e) { wc && wc(); return resolve("ok"); }
      wc && wc();
      if (!r.ok || r.skip || r.timeout) return resolve("ok");
      const matched = r.matched || {}, unknown = Object.assign({}, r.unknown || {}), rest = r.papers.filter(p => !(p in matched)), tick = new Set(Object.keys(matched)); let close0;
      const draw = (c) => {
        c.innerHTML = `<h3>📰 Before you close — today's papers</h3><p class="sub">${new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
          <div class="eod">${Object.keys(matched).length ? `<h5>✅ Clipped today (${Object.keys(matched).length})</h5><div class="eod-g">${Object.keys(matched).map(p => `<span class="chip ok">${esc(C.clean(p))} · ${matched[p]}</span>`).join("")}</div>` : '<h5>No clips found on disk for today</h5>'}
          ${Object.keys(unknown).length ? `<h5>⚠ Unrecognised names</h5><div class="eod-g">${Object.keys(unknown).map(k => `<button class="chip" data-r="${esc(k)}">${esc(k)} → map</button>`).join("")}</div>` : ""}
          <h5>Which of these actually arrived? <button class="linkish" id="eAll">tick all</button></h5><div class="tk-grid sm">${rest.map(p => `<div class="tk-card ${tick.has(p) ? "on" : ""}" data-p="${esc(p)}"><span class="ck">${tick.has(p) ? "✓" : ""}</span><span class="nm">${esc(C.clean(p))}</span></div>`).join("")}</div></div>
          <div class="modal-actions"><button class="btn" id="eStay">← Back to NAB</button><button class="btn" id="eOff">🏖 Off day</button><button class="btn" id="eSkip">Skip</button><button class="btn pri" id="eSub">✅ Submit day</button></div>`;
        $$(".tk-card", c).forEach(k => k.onclick = () => { const p = k.dataset.p; if (tick.has(p)) tick.delete(p); else tick.add(p); k.classList.toggle("on", tick.has(p)); k.querySelector(".ck").textContent = tick.has(p) ? "✓" : ""; });
        $$(".chip[data-r]", c).forEach(b => b.onclick = () => { const raw = b.dataset.r; close0(); mapUnknown(raw, unknown[raw], () => resolve(endPrompt())); });
        $("#eAll", c).onclick = () => { rest.forEach(p => tick.add(p)); draw(c); };
        $("#eStay", c).onclick = () => { close0(); resolve("cancel"); };
        $("#eSkip", c).onclick = () => { close0(); resolve("ok"); };
        $("#eOff", c).onclick = async () => { $("#eOff", c).disabled = true; await api("tracker_off", { date: r.date, wait: true }); close0(); resolve("ok"); };
        $("#eSub", c).onclick = async () => { $("#eSub", c).disabled = true; $("#eSub", c).textContent = "Saving…"; const all = new Set([...Object.keys(matched), ...tick]); await api("tracker_submit", { date: r.date, papers: r.papers, received: Array.from(all), wait: true }); close0(); resolve("ok"); };
      };
      modal("", (c, close) => { close0 = close; draw(c); });
    });
  }

  window.TOOLS.tracker = { mount, show, endPrompt };

  // ═════════════ Subscriptions ═════════════
  const SUB = { el: null };
  window.TOOLS.subs = {
    mount(el) { SUB.el = el; },
    async show() {
      const r = await api("subs_list");
      SUB.el.innerHTML = `<div class="tk"><div class="tk-body"><h2 style="margin:8px 4px 2px">Subscription expiry dates</h2><p class="sub" style="margin:0 4px 10px">You get a reminder ${r.warn} days before a paper's subscription runs out. Papers with no date are never checked.</p>
        <div class="card">${r.rows.map(x => { const dd = x.days; const tag = dd == null ? "" : dd < 0 ? `<span class="tag bad">expired ${-dd}d ago</span>` : dd <= r.warn ? `<span class="tag warn">${dd}d left</span>` : `<span class="tag">${dd}d left</span>`; return `<div class="kv" style="grid-template-columns:1fr 160px 110px 32px"><span>${esc(x.paper)}</span><input type="date" data-p="${esc(x.raw)}" value="${x.iso}"><span>${tag}</span><button class="btn" data-c="${esc(x.raw)}" style="height:30px;padding:0 8px" title="Clear">✕</button></div>`; }).join("")}</div></div></div>`;
      $$("input[type=date]", SUB.el).forEach(i => i.onchange = async () => { await api("subs_set", { paper: i.dataset.p, iso: i.value }); window.TOOLS.subs.show(); });
      $$("button[data-c]", SUB.el).forEach(b => b.onclick = async () => { await api("subs_set", { paper: b.dataset.c, iso: "" }); window.TOOLS.subs.show(); });
    },
    async remind() {
      const r = await api("subs_expiring"); if (!r.items || !r.items.length) return;
      modal(`<h3>🧾 Subscription expiry reminder</h3>${r.items.map(i => `<div class="kv" style="grid-template-columns:1fr auto"><b>${esc(i.paper)}</b><span class="tag ${i.days < 0 ? "bad" : "warn"}">${i.days < 0 ? "expired " + (-i.days) + "d ago" : i.days === 0 ? "expires today" : i.days + "d left"} (${esc(i.date)})</span></div>`).join("")}<div class="modal-actions"><button class="btn" id="sbOpen">Manage</button><button class="btn pri" id="sbOk">OK</button></div>`, (c, close) => { $("#sbOk", c).onclick = close; $("#sbOpen", c).onclick = () => { close(); MAIN.show("subs"); }; });
    },
  };
})();
