// tool_hunt.js — News Hunter screen: clients (keyword sets), results, find-similar, settings. Links go straight to the Screenshot Bot.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  let el, st = null, cur = null, tab = "res", rows = [], running = false, sel = new Set();
  const when = (s) => { if (!s) return ""; const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); };
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return ""; } };
  const HTML = `<div class="tk hn"><div class="sh-top pr-top"><div><h2>News Hunter</h2><div class="sub">Finds what was published about each client, on Bangladeshi news sites, in Bangla and English. Same story is grouped once.</div></div>
    <div class="grow"></div><div class="tabs-s" id="hnTabs"><button data-t="res" class="on">Results</button><button data-t="cli">Client setup</button><button data-t="sim">Find similar</button><button data-t="set">Settings</button></div></div>
  <div class="hn-wrap"><aside class="hn-side card"><h4>Clients</h4><div id="hnClients" class="hn-cl"></div>
    <div class="tk-bar"><button class="btn sm" id="hnNew">New client</button><button class="btn sm" id="hnPre" title="Restore the built-in Edotco / mobile tower client">Edotco preset</button></div>
    <button class="btn pri" id="hnRun">Hunt selected</button><button class="btn" id="hnAuto">Auto: off</button>
    <div class="sh-bar"><div id="hnBar"></div></div><div class="sh-log" id="hnLog"></div></aside>
  <section class="hn-main" id="hnMain"></section></div></div>`;
  const log = (m, k, t) => { const b = $("#hnLog"); if (!b) return; const d = document.createElement("div"); if (k) d.className = k; d.innerHTML = `<time>${esc(t || new Date().toLocaleTimeString())}</time>${esc(m)}`; b.appendChild(d); b.scrollTop = b.scrollHeight; };

  function side() {
    const cl = st.clients, ids = Object.keys(cl);
    $("#hnClients").innerHTML = ids.map(i => `<label class="hn-c${cur === i ? " on" : ""}" data-i="${i}"><input type="checkbox" ${sel.has(i) ? "checked" : ""}><span>${esc(cl[i].name)}</span><small>${cl[i].every_minutes > 0 ? "every " + cl[i].every_minutes + " min" : "manual"}</small></label>`).join("") || `<div class="lbl">No clients yet.</div>`;
    $$("#hnClients .hn-c").forEach(l => {
      l.querySelector("input").onchange = (e) => { e.target.checked ? sel.add(l.dataset.i) : sel.delete(l.dataset.i); };
      l.querySelector("span").onclick = (e) => { e.preventDefault(); cur = l.dataset.i; side(); if (tab === "cli") draw(); else { tab = "res"; setTab(); } };
    });
    $("#hnAuto").textContent = "Auto: " + (st.auto ? "on" : "off"); $("#hnAuto").classList.toggle("pri", !!st.auto);
  }
  function setTab() { $$("#hnTabs button").forEach(b => b.classList.toggle("on", b.dataset.t === tab)); draw(); }
  function draw() { ({ res: dRes, cli: dCli, sim: dSim, set: dSet })[tab](); }

  // ---- results
  async function dRes() {
    const m = $("#hnMain"); m.innerHTML = `<div class="tk-bar"><select id="hnF" class="mini-in"><option value="">All clients</option>${Object.keys(st.clients).map(i => `<option value="${i}" ${cur === i ? "selected" : ""}>${esc(st.clients[i].name)}</option>`).join("")}</select>
      <select id="hnW" class="mini-in"><option value="24">Last 24 h</option><option value="168">Last 7 days</option><option value="720">Last 30 days</option><option value="">All time</option></select>
      <input id="hnT" class="mini-in" placeholder="Filter by title" style="flex:1;min-width:120px"><span class="lbl" id="hnCnt"></span>
      <button class="btn sm" id="hnAll">Select all</button><button class="btn sm pri" id="hnShots">Send selected to Screenshot Bot</button><button class="btn sm" id="hnCopy">Copy links</button><button class="btn sm" id="hnExp">Export .txt</button><button class="btn sm" id="hnOpen">Open folder</button></div>
      <div class="hn-res" id="hnRes"></div>`;
    const go = C.debounce(load, 200);
    ["hnF", "hnW"].forEach(i => $("#" + i).onchange = load); $("#hnT").oninput = go;
    $("#hnAll").onclick = () => { const all = rows.every(r => sel2.has(r.link)); rows.forEach(r => all ? sel2.delete(r.link) : sel2.add(r.link)); paint(); };
    $("#hnShots").onclick = () => sendShots([...sel2].length ? [...sel2] : rows.map(r => r.link));
    $("#hnCopy").onclick = async () => { const t = ([...sel2].length ? [...sel2] : rows.map(r => r.link)).join("\n"); try { await navigator.clipboard.writeText(t); toast("Links copied", "ok"); } catch (e) { toast("Copy failed", "error"); } };
    $("#hnExp").onclick = async () => { const r = await api("hunt_export", { client: $("#hnF").value, text: $("#hnT").value }); toast(r.ok ? r.n + " links saved to " + r.path : "Export failed", r.ok ? "ok" : "error", 5000); };
    $("#hnOpen").onclick = () => api("hunt_open");
    await load();
  }
  const sel2 = new Set();
  async function load() {
    const r = await api("hunt_results", { client: $("#hnF").value, since: $("#hnW").value, text: $("#hnT").value }); rows = r.rows || []; paint();
  }
  function paint() {
    const box = $("#hnRes"); if (!box) return;
    const byGrp = new Map(); rows.forEach(r => { const k = r.search + "|" + r.first_seen.slice(0, 13) + "|" + r.grp; if (!byGrp.has(k)) byGrp.set(k, []); byGrp.get(k).push(r); });
    $("#hnCnt").textContent = rows.length + " links · " + byGrp.size + " stories";
    box.innerHTML = [...byGrp.values()].slice(0, 400).map(g => { const m = g[0];
      return `<div class="hn-g"><label class="hn-row"><input type="checkbox" data-l="${esc(m.link)}" ${sel2.has(m.link) ? "checked" : ""}><div><a href="${esc(m.link)}" target="_blank" rel="noopener" class="hn-t">${esc(m.title)}</a>
        <small>${esc(m.source || m.domain)} · ${esc(when(m.published) || when(m.first_seen))}${m.resolved ? "" : " · Google link (publisher address not readable)"} · ${esc((st.clients[m.search] || {}).name || m.search)}</small></div></label>
        ${g.slice(1).map(o => `<label class="hn-row also"><input type="checkbox" data-l="${esc(o.link)}" ${sel2.has(o.link) ? "checked" : ""}><div><a href="${esc(o.link)}" target="_blank" rel="noopener">${esc(o.source || o.domain || host(o.link))}</a><small>${esc(o.title)}</small></div></label>`).join("")}</div>`; }).join("") || `<div class="lbl" style="padding:20px">Nothing yet. Pick a client on the left and press Hunt selected.</div>`;
    $$("#hnRes input[type=checkbox]").forEach(c => c.onchange = () => { c.checked ? sel2.add(c.dataset.l) : sel2.delete(c.dataset.l); });
  }
  async function sendShots(links) {
    if (!links.length) return toast("No links to send", "warn");
    const r = await api("hunt_to_shots", { links }); if (!r.ok) return toast(r.error || "Screenshot Bot is busy", "error", 5000);
    toast(links.length + " link(s) sent to the Screenshot Bot", "ok"); window.MAIN && MAIN.show("shot");
  }

  // ---- client editor
  const L = (v) => (v || []).join("\n");
  function dCli() {
    const m = $("#hnMain"), c = st.clients[cur];
    if (!c) { m.innerHTML = `<div class="lbl" style="padding:20px">Pick a client on the left, or press New client.</div>`; return; }
    const chk = (k, v) => `<label class="chk"><input type="checkbox" data-k="src" value="${k}" ${(c.sources || []).includes(k) ? "checked" : ""}> ${v}</label>`;
    m.innerHTML = `<div class="card hn-ed"><div class="row"><span>Client name</span><input id="cName" class="mini-in" style="flex:1" value="${esc(c.name)}"></div>
      <div class="hn-two"><div><div class="lbl">Keywords (one per line; any of them)</div><textarea id="cAny" class="sh-links" style="height:190px">${esc(L(c.any))}</textarea></div>
      <div><div class="lbl">Must also contain (all of these, optional)</div><textarea id="cAll" class="sh-links" style="height:70px">${esc(L(c.all))}</textarea><div class="lbl" style="margin-top:8px">Never contain (optional)</div><textarea id="cNone" class="sh-links" style="height:70px">${esc(L(c.none))}</textarea></div></div>
      <div class="lbl">What this client is about (the AI uses this to drop wrong results)</div><textarea id="cBrief" class="sh-links" style="height:56px">${esc(c.brief || "")}</textarea>
      <div class="hn-opts"><div class="row"><span>Look back (hours)</span><input id="cHrs" type="number" min="1" class="mini-in" style="width:80px" value="${c.hours}"></div>
      <div class="row"><span>Repeat every (minutes, 0 = manual)</span><input id="cEvery" type="number" min="0" class="mini-in" style="width:80px" value="${c.every_minutes || 0}"></div>
      <div class="row"><span>Bangladesh only (trusted outlets, drops foreign and wrong "tower" stories)</span><input type="checkbox" id="cBd" ${c.bd_only ? "checked" : ""}></div>
      <div class="row"><span>Strictness</span><select id="cLvl" class="mini-in">${["Strict", "Balanced", "Wide"].map(x => `<option ${c.level === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="row"><span>Topic rules</span><select id="cTopic" class="mini-in"><option value="keywords" ${c.topic !== "tower" ? "selected" : ""}>Match my keywords</option><option value="tower" ${c.topic === "tower" ? "selected" : ""}>Mobile tower / Edotco rules</option></select></div>
      <div class="row"><span>AI double-check of doubtful results (Groq)</span><input type="checkbox" id="cAi" ${c.ai_check !== false ? "checked" : ""}></div>
      <div class="row"><span>Sources</span><span>${chk("gnews", "Google News")} ${chk("gdelt", "GDELT")} ${chk("brave", "Brave")} ${chk("feeds", "My feeds")}</span></div>
      <div class="row"><span>Languages</span><span><label class="chk"><input type="checkbox" data-k="lang" value="en" ${(c.languages || []).includes("en") ? "checked" : ""}> English</label> <label class="chk"><input type="checkbox" data-k="lang" value="bn" ${(c.languages || []).includes("bn") ? "checked" : ""}> Bangla</label></span></div>
      <div class="row"><span>Send each hunt to</span><span><label class="chk"><input type="checkbox" data-k="out" value="txt" ${(c.outputs || []).includes("txt") ? "checked" : ""}> Text file</label> <label class="chk"><input type="checkbox" data-k="out" value="telegram" ${(c.outputs || []).includes("telegram") ? "checked" : ""}> Telegram</label></span></div></div>
      <div class="tk-bar"><button class="btn pri" id="cSave">Save client</button><button class="btn" id="cDel">Delete client</button></div></div>`;
    const pick = (k) => $$(`#hnMain input[data-k=${k}]:checked`).map(x => x.value);
    $("#cSave").onclick = async () => {
      const r = await api("hunt_client_save", { id: cur, name: $("#cName").value, any: $("#cAny").value, all: $("#cAll").value, none: $("#cNone").value, brief: $("#cBrief").value, hours: $("#cHrs").value, every_minutes: $("#cEvery").value,
        bd_only: $("#cBd").checked, level: $("#cLvl").value, topic: $("#cTopic").value, ai_check: $("#cAi").checked, sources: pick("src"), languages: pick("lang"), outputs: pick("out") });
      if (r.ok) { toast("Saved", "ok"); await refresh(); } else toast("Could not save", "error");
    };
    $("#cDel").onclick = async () => { if (!confirm("Delete this client? Found links stay in the history.")) return; await api("hunt_client_delete", { id: cur }); cur = null; await refresh(); draw(); };
  }

  // ---- find similar
  function dSim() {
    $("#hnMain").innerHTML = `<div class="card hn-ed"><div class="lbl">Paste a headline (and the article if you like). The hunter finds the same story and close follow-ups on other sites, in both languages.</div>
      <input id="sHead" class="mini-in" style="width:100%;margin:6px 0" placeholder="Headline"><textarea id="sBody" class="sh-links" style="height:110px" placeholder="Article text (optional, improves accuracy)"></textarea>
      <div class="tk-bar"><select id="sHrs" class="mini-in"><option value="24">Last 24 h</option><option value="72" selected>Last 3 days</option><option value="168">Last 7 days</option></select><button class="btn pri" id="sGo">Find similar news</button></div></div><div class="hn-res" id="sRes"></div>`;
    $("#sGo").onclick = async () => {
      if (!$("#sHead").value.trim() && !$("#sBody").value.trim()) return toast("Paste a headline first", "warn");
      const r = await api("hunt_similar", { headline: $("#sHead").value, body: $("#sBody").value, hours: $("#sHrs").value }); if (!r.ok) toast(r.error, "error", 5000); else $("#sRes").innerHTML = `<div class="lbl" style="padding:10px">Searching…</div>`;
    };
  }
  function simResult(ev) {
    const box = $("#sRes"); if (!box || tab !== "sim") return;
    const gs = ev.groups || [];
    box.innerHTML = (gs.length ? `<div class="tk-bar"><button class="btn sm pri" id="sShots">Send all to Screenshot Bot</button><span class="lbl">${esc((ev.keywords || []).join(", "))}</span></div>` : "") + (gs.map(g => `<div class="hn-g">${g.map((o, i) => `<div class="hn-row${i ? " also" : ""}"><span class="hn-lab ${esc((o.label || "").replace(" ", "-"))}">${esc(o.label || "")}</span><div><a href="${esc(o.link)}" target="_blank" rel="noopener" class="hn-t">${esc(o.title)}</a><small>${esc(o.source || o.domain)} · ${esc(when(o.published))}${o.sim != null ? " · match " + Math.round(o.sim * 100) + "%" : ""}</small></div></div>`).join("")}</div>`).join("") || `<div class="lbl" style="padding:14px">No similar news found in that time.</div>`);
    const b = $("#sShots"); if (b) b.onclick = () => sendShots(gs.flat().map(o => o.link));
  }

  // ---- settings
  function dSet() {
    const s = st.settings, tg = s.telegram || {};
    $("#hnMain").innerHTML = `<div class="card hn-ed"><h4 style="margin:0 0 6px">Telegram digest</h4><div class="lbl">Create a bot with @BotFather, add it to your chat, paste the token and the numeric chat id.</div>
      <div class="row"><span>Bot token</span><input id="tgT" class="mini-in" style="flex:1" value="${esc(tg.token || "")}"></div><div class="row"><span>Chat id</span><input id="tgC" class="mini-in" style="flex:1" value="${esc(tg.chat_id || "")}"></div>
      <h4 style="margin:12px 0 6px">Wider coverage</h4><div class="row"><span>Brave Search key (optional)</span><input id="brK" class="mini-in" style="flex:1" value="${esc(s.brave_key || "")}"></div>
      <div class="lbl">Your own news-site feeds, one per line: Name | https://site/rss.xml</div><textarea id="stFeeds" class="sh-links" style="height:70px">${esc((s.feeds || []).map(f => f.name + " | " + f.url).join("\n"))}</textarea>
      <div class="lbl">Always ignore these sites (one per line)</div><textarea id="stBlock" class="sh-links" style="height:56px">${esc(L(s.blocklist))}</textarea>
      <div class="lbl">Only accept these sites (leave empty for every non-blocked site)</div><textarea id="stAllow" class="sh-links" style="height:56px">${esc(L(s.allowlist))}</textarea>
      <div class="tk-bar"><button class="btn pri" id="stSave">Save settings</button><button class="btn" id="stTg">Send Telegram test</button></div></div>`;
    $("#stSave").onclick = async () => { await api("hunt_settings", { telegram: { token: $("#tgT").value, chat_id: $("#tgC").value }, brave_key: $("#brK").value, feeds: $("#stFeeds").value, blocklist: $("#stBlock").value, allowlist: $("#stAllow").value }); toast("Saved", "ok"); await refresh(); };
    $("#stTg").onclick = async () => { await $("#stSave").onclick(); const r = await api("hunt_tgtest"); toast(r.ok ? "Telegram message sent" : "Telegram failed: check token and chat id", r.ok ? "ok" : "error", 4000); };
  }

  async function refresh() { st = await api("hunt_state"); side(); }
  function lock(b) { running = b; $("#hnRun").disabled = b; $("#hnRun").textContent = b ? "Hunting…" : "Hunt selected"; $("#hnBar").classList.toggle("spin", b); }
  function mount(e) {
    el = e; el.innerHTML = HTML;
    $$("#hnTabs button").forEach(b => b.onclick = () => { tab = b.dataset.t; setTab(); });
    $("#hnNew").onclick = async () => { const r = await api("hunt_client_save", { name: "New client", any: "" }); cur = r.id; await refresh(); tab = "cli"; setTab(); };
    $("#hnPre").onclick = async () => { const r = await api("hunt_preset"); cur = r.id; await refresh(); tab = "cli"; setTab(); toast("Edotco preset restored", "ok"); };
    $("#hnRun").onclick = async () => {
      const ids = [...sel]; if (!ids.length) return toast("Tick at least one client", "warn");
      const r = await api("hunt_run", { ids }); if (!r.ok) return toast(r.error, "error", 5000); $("#hnLog").innerHTML = ""; lock(true);
    };
    $("#hnAuto").onclick = async () => { const r = await api("hunt_auto", { on: !st.auto }); st.auto = r.auto; side(); toast(r.auto ? "Auto hunting on while NAB is open" : "Auto hunting off", "ok"); };
    on("tool", (ev) => {
      if (ev.tool !== "hunt" || !el) return;
      if (ev.ev === "log") log(ev.msg, "", ev.at);
      else if (ev.ev === "begin") lock(true);
      else if (ev.ev === "done") { lock(false); if (ev.similar) simResult(ev); else { log(`Done: ${ev.new || 0} new link(s)`, "ok"); refresh(); if (tab === "res") load(); } }
      else if (ev.ev === "auto") { refresh(); if (tab === "res") load(); }
    });
  }
  async function show() {
    await refresh(); if (!cur) cur = Object.keys(st.clients)[0] || null; if (!sel.size && cur) sel.add(cur);
    side(); lock(!!(st.job && !st.job.done)); setTab();
  }
  window.TOOLS.hunt = { mount, show };
})();
