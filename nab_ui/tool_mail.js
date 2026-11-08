// tool_mail.js — "Send by mail": groups with rules, prepare files (PDF / JPG / ZIP), confirm, send with progress, log.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast, modal } = C;
  const S = { el: null, d: null, plans: {}, sel: new Set(), working: {}, wired: false, prepWait: null };
  const MB = (b) => (b / 1048576 < 0.1 ? Math.max(0.01, b / 1048576).toFixed(2) : (b / 1048576).toFixed(1)) + " MB";
  const ATT = { pdf: "PDF", jpg: "JPG", zip: "ZIP" };
  const rule = (g) => g.mode === "zip" ? "ZIP always" : (ATT[g.mode] + (g.if_large === "zip" ? " · ZIP if large" : ""));
  const srcText = (g) => { if (g.take_rest) return "everything not taken by other groups";  const a = g.sources.slice(), n = (g.items || []).length; if (g.mode === "pdf") { a.length = 0; (g.from_cats || []).forEach(c_ => a.push("all PDFs from " + c_)); } if (n) a.push(n + " named PDF" + (n === 1 ? "" : "s")); return a.join(", ") || "nothing chosen"; };
  const cfg = () => S.d.cfg, grp = (id) => cfg().groups.find(g => g.id === id);
  const split = (v) => String(v || "").split(/[,;\s]+/).map(x => x.trim()).filter(Boolean);
  const EMAIL = /^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/;

  function mount(el) {
    S.el = el;
    el.innerHTML = '<div class="ml"><div class="ml-top" id="mlTop"></div><div class="ml-main"><div class="ml-left card" id="mlLeft"></div><div class="ml-right" id="mlRight"></div></div><div class="ml-bar card" id="mlBar"></div></div>';
    if (S.wired) return; S.wired = true;
    on("mail_plan", (ev) => {
      if (ev.stage === "work") S.working[ev.id] = true;
      if (ev.stage === "group") { S.plans[ev.plan.id] = ev.plan; delete S.working[ev.plan.id]; }
      if (ev.stage === "done" || ev.stage === "error") { S.working = {}; if (ev.stage === "error") toast(ev.error, "error", 5000); if (S.prepWait) { S.prepWait(); S.prepWait = null; } }
      if (S.d) drawRows();
    });
    on("mail_progress", progress);
  }
  async function show() { await reload(); }
  async function reload(keepSel) {
    S.d = await api("mail_load");
    if (!keepSel) { S.sel = new Set(S.d.cfg.groups.filter(g => g.enabled).map(g => g.id)); }
    draw();
  }

  // ───────── main screen ─────────
  function draw() {
    const c = cfg(), a = c.account, ready = a.email && S.d.has_password;
    $("#mlTop").innerHTML = `<h2>Send by mail</h2><span class="dim">Date</span><span class="pill">${esc(S.d.date)}</span><div class="grow"></div>
      <span class="chip ${ready ? "ok" : "warn"}"><i></i>${ready ? "Sending as " + esc(a.email) : "Mail account not set up"}</span><button class="btn" id="mlSet">Mail settings</button>`;
    $("#mlSet").onclick = settings;
    $("#mlLeft").innerHTML = `<div class="ml-h"><b>Groups to send</b><span class="dim" id="mlCount"></span><div class="grow"></div><button class="btn sm" id="mlPrep">Prepare files</button><button class="btn sm" id="mlAdd">Add group</button></div>
      ${S.d.day_exists ? "" : '<div class="ml-note">No folder for this date yet. Save some clips first.</div>'}
      <div class="ml-th"><span></span><span>Group</span><span>Attachment rule</span><span>To / CC</span><span>Status</span></div><div id="mlRows"></div>`;
    $("#mlPrep").onclick = () => prepare(true); $("#mlAdd").onclick = () => editGroup(null);
    $("#mlRight").innerHTML = `<div class="card"><h4>Email text</h4><label class="dim sm">Subject</label><input id="mlSub"><label class="dim sm">Message</label><textarea id="mlBody" rows="5"></textarea>
      <div class="dim sm">Placeholders: {Group} {Date} {Count} {Size} {Part}</div></div>
      <div class="card"><h4>Safety</h4><label class="ck"><input type="checkbox" id="bAsk"><span>Ask me before sending</span></label><label class="ck"><input type="checkbox" id="bTg"><span>Tell me on Telegram when done</span></label><label class="ck"><input type="checkbox" id="bSkip"><span>Skip groups already sent today</span></label>
      <div class="kv2"><span>Always Bcc</span><input id="bMe" placeholder="optional address"></div></div>
      <div class="card ml-log"><h4>Send log</h4><div id="mlLog"></div></div>`;
    $("#mlSub").value = c.text.subject; $("#mlBody").value = c.text.body;
    $("#bAsk").checked = c.behaviour.ask; $("#bTg").checked = c.behaviour.telegram; $("#bSkip").checked = c.behaviour.skip_sent; $("#bMe").value = c.behaviour.bcc_me || "";
    const keep = () => { c.text.subject = $("#mlSub").value; c.text.body = $("#mlBody").value; c.behaviour.ask = $("#bAsk").checked; c.behaviour.telegram = $("#bTg").checked; c.behaviour.skip_sent = $("#bSkip").checked; c.behaviour.bcc_me = $("#bMe").value.trim(); persist(); };
    ["mlSub", "mlBody", "bMe"].forEach(i => $("#" + i).onchange = keep); ["bAsk", "bTg", "bSkip"].forEach(i => $("#" + i).onchange = keep);
    $("#mlBar").innerHTML = `<div id="mlSum"></div><div class="grow"></div><button class="btn" id="mlPrev">Preview emails</button><button class="btn" id="mlTest">Send test to me only</button><button class="btn pri" id="mlSend">Send all</button>`;
    $("#mlPrev").onclick = preview; $("#mlTest").onclick = () => send(true); $("#mlSend").onclick = () => send(false);
    drawRows(); drawLog();
  }
  async function persist() { const r = await api("mail_save", { cfg: cfg() }); if (!r.ok) toast(r.error, "error", 4000); else S.d.cfg = r.cfg; }
  function statusOf(g) {
    if (S.working[g.id]) return ["Working…", "run"];
    const p = S.plans[g.id];
    if (p) {
      if (p.status === "ready") { const hw = (p.hints || []).filter(h => h[0] === "warn").length; return [`${ATT[p.attach] || ""} · ${p.attach === "zip" && p.inner ? p.inner + " files" : p.n + " file" + (p.n === 1 ? "" : "s")} · ${MB(p.bytes)}${hw ? " · check " + hw : ""}`, hw ? "warn" : "ok"]; }
      return [p.note || "No files", "warn"];
    }
    if (g.mode === "pdf") return ["Not checked", "dim"];
    const has = g.sources.some(s => S.d.folders.includes(s));
    return has ? ["Not prepared", "dim"] : ["No folder today", "warn"];
  }
  function drawRows() {
    const box = $("#mlRows"); if (!box) return; const gs = cfg().groups;
    box.innerHTML = gs.map(g => { const [t, k] = statusOf(g);
      return `<div class="ml-row ${g.enabled ? "" : "off"}" data-id="${g.id}"><input type="checkbox" class="pick" ${S.sel.has(g.id) ? "checked" : ""} ${g.enabled ? "" : "disabled"}>
      <b>${esc(g.name)}</b><span class="dim">${esc(rule(g))}<br><small>${esc(srcText(g))}</small></span><span class="rc">${g.to.length ? "To: " + esc(g.to.join(", ")) : '<em class="warn">no receivers</em>'}${g.cc.length ? "<br>CC: " + esc(g.cc.join(", ")) : ""}</span><span class="st ${k}">${esc(t)}</span></div>`; }).join("") || '<div class="ml-note">No groups yet. Press Add group.</div>';
    $$(".ml-row", box).forEach(r => { r.onclick = (e) => { if (e.target.classList.contains("pick")) return; editGroup(grp(r.dataset.id)); };
      $(".pick", r).onchange = (e) => { e.target.checked ? S.sel.add(r.dataset.id) : S.sel.delete(r.dataset.id); sum(); }; });
    $("#mlCount").textContent = gs.filter(g => g.enabled).length + " groups";
    sum();
  }
  function sum() {
    const ids = [...S.sel], gs = cfg().groups.filter(g => ids.includes(g.id) && g.enabled); const n = gs.length, rc = gs.reduce((a, g) => a + g.to.length + g.cc.length, 0);
    const none = gs.filter(g => S.plans[g.id] && S.plans[g.id].status !== "ready").map(g => g.name);
    $("#mlSum").innerHTML = `<b>${n}</b> emails · <b>${rc}</b> receivers${none.length ? ` · <span class="warn">${esc(none.join(", "))}: no files</span>` : ""}`;
  }
  function drawLog() {
    const L = S.d.log || [], box = $("#mlLog"); if (!box) return;
    box.innerHTML = L.slice(0, 14).map(e => `<div class="lg ${e.ok ? "ok" : "bad"}"><span>${esc(e.date || "")}</span><span>${esc(e.group)}${e.test ? " (test)" : ""}</span><span>${e.ok ? "sent" + (e.parts > 1 ? " · " + e.parts + " parts" : "") : esc((e.error || "failed").slice(0, 50))}</span></div>`).join("") || '<div class="dim sm">Nothing sent yet.</div>';
  }

  // ───────── prepare ─────────
  function prepare(makePdfs) {
    return new Promise(async (res) => {
      const btn = $("#mlPrep"), reset = () => { const b = $("#mlPrep"); if (b) b.textContent = "Check files"; };
      S.prepWait = () => { reset(); res(); }; if (btn) btn.textContent = "Checking…";
      const r = await api("mail_prepare", { make_pdfs: makePdfs, ids: [...S.sel] });
      if (!r.ok) { S.prepWait = null; reset(); toast(r.error, "warn", 3500); res(); }
    });
  }

  // ───────── preview / send ─────────
  const chosen = () => cfg().groups.filter(g => g.enabled && S.sel.has(g.id));
  async function ensure() {
    const need = chosen().some(g => !S.plans[g.id]); if (need) await prepare(true);
    return chosen();
  }
  async function preview() {
    const gs = await ensure(), c = cfg();
    modal(`<h3>Preview emails</h3><div class="ml-pv">${gs.map(g => { const p = S.plans[g.id] || {}; const subj = (g.own_text && g.subject ? g.subject : c.text.subject).replace(/\{Group\}/g, g.name).replace(/\{Date\}/g, S.d.date).replace(/\{Count\}/g, p.n || 0).replace(/\{Size\}/g, MB(p.bytes || 0)).replace(/\{Part\}/g, 1).replace(/\{Total\}/g, 1);
      return `<div class="pv"><b>${esc(subj)}</b><div class="dim sm">To: ${esc(g.to.join(", ") || "—")}${g.cc.length ? " · CC: " + esc(g.cc.join(", ")) : ""}</div><div class="sm">${p.status === "ready" ? (p.names || []).map(esc).join(", ") + " · " + MB(p.bytes) : '<span class="warn">' + esc(p.note || "No files") + "</span>"}</div></div>`; }).join("")}</div><div class="modal-actions"><button class="btn pri" id="pvX">Close</button></div>`, (m, close) => { $("#pvX", m).onclick = close; });
  }
  async function send(test) {
    const gs = await ensure(); if (!gs.length) return toast("Select at least one group.", "warn", 2500);
    const c = cfg(), go = async () => { const r = await api("mail_send", { ids: gs.map(g => g.id), test }); if (!r.ok) return toast(r.error, "error", 6000); openProgress(); };
    if (test || !c.behaviour.ask) return go();
    const ok = gs.filter(g => S.plans[g.id] && S.plans[g.id].status === "ready"), bad = gs.filter(g => !ok.includes(g));
    modal(`<h3>Send ${ok.length} email${ok.length === 1 ? "" : "s"} now?</h3><p class="dim">Each group gets only its own files, To and CC. Check once more.</p><div class="ml-pv">${ok.map(g => `<div class="pv sm"><b>${esc(g.name)}</b> → ${esc(ATT[S.plans[g.id].attach])} · ${S.plans[g.id].n} file(s) · ${g.to.length} To, ${g.cc.length} CC${(S.plans[g.id].hints || []).map(h => `<div class="${h[0] === "warn" ? "warn" : "dim"}">${h[0] === "warn" ? "Check: " : "Note: "}${esc(h[1])}</div>`).join("")}</div>`).join("")}</div>
      ${bad.length ? `<p class="warn sm">${esc(bad.map(g => g.name).join(", "))} have no files and will be skipped.</p>` : ""}<div class="modal-actions"><button class="btn" id="cfN">Cancel</button><button class="btn pri" id="cfY">Yes, send</button></div>`,
      (m, close) => { $("#cfN", m).onclick = close; $("#cfY", m).onclick = () => { close(); go(); }; });
  }
  function openProgress() {
    modal(`<h3 id="pgT">Sending…</h3><div class="ml-bar2"><div id="pgB"></div></div><div id="pgL" class="ml-pv"></div><div class="modal-actions"><button class="btn" id="pgR" disabled>Retry failed</button><button class="btn pri" id="pgX" disabled>Close</button></div>`, (m, close) => { S.pClose = close; $("#pgX", m).onclick = () => { close(); reload(true); }; });
  }
  function progress(ev) {
    if (!$("#pgL")) { if (ev.stage === "start") openProgress(); else return; }
    const it = ev.items || [], done = it.filter(x => ["ok", "fail", "skip"].includes(x.st)).length;
    $("#pgB").style.width = (it.length ? done / it.length * 100 : 0) + "%";
    $("#pgL").innerHTML = it.map(x => `<div class="pg ${x.st}"><i></i><span>${esc(x.name)}</span><em>${esc(x.msg || (x.st === "wait" ? "Waiting" : ""))}</em></div>`).join("");
    if (ev.stage === "done") {
      $("#pgT").textContent = ev.test ? `Test finished: ${ev.ok} sent to you` : `Done: ${ev.ok} sent${ev.fail ? ", " + ev.fail + " failed" : ""}`;
      $("#pgX").disabled = false; const r = $("#pgR"); r.disabled = !ev.fail;
      r.onclick = async () => { const ids = it.filter(x => x.st === "fail").map(x => x.id); const q = await api("mail_send", { ids, test: false }); if (!q.ok) toast(q.error, "error", 5000); else { r.disabled = true; $("#pgX").disabled = true; } };
    }
    if (ev.stage === "error") { $("#pgT").textContent = "Stopped: " + ev.error; $("#pgX").disabled = false; }
  }

  // ───────── group editor ─────────
  function chips(box, list, ph, validate) {
    const draw = () => { box.innerHTML = list.map((v, i) => `<span class="cp ${validate && !validate(v) ? "bad" : ""}">${esc(v)}<b data-i="${i}">×</b></span>`).join("") + `<input class="cin" placeholder="${esc(ph)}" list="${box.dataset.list || ""}">`;
      $$("b", box).forEach(b => b.onclick = () => { list.splice(+b.dataset.i, 1); draw(); });
      const inp = $(".cin", box), add = (txt) => { split(txt).forEach(v => { if (!list.includes(v)) list.push(v); }); draw(); box.querySelector(".cin").focus(); };
      inp.onkeydown = (e) => { if (["Enter", ",", ";", " ", "Tab"].includes(e.key) && inp.value.trim()) { e.preventDefault(); add(inp.value); } else if (e.key === "Backspace" && !inp.value && list.length) { list.pop(); draw(); box.querySelector(".cin").focus(); } };
      inp.onblur = () => { if (inp.value.trim()) add(inp.value); }; inp.onpaste = (e) => { const t = (e.clipboardData || window.clipboardData).getData("text"); if (/[,;\s]/.test(t.trim())) { e.preventDefault(); add(t); } };
    }; draw();
  }
  async function editGroup(g0) {
    const ir = await api("mail_items"), CATS = ir.cats || [], PDFS = ir.pdfs || [];
    const c = cfg(), isNew = !g0, g = JSON.parse(JSON.stringify(g0 || { id: "n" + Date.now().toString(36), name: "", enabled: true, sources: [], items: [], mode: "pdf", if_large: "zip", items: [], take_rest: false, large_files: null, large_mb: null, zip_name: "{Group} {Date}.zip", zip_root: "", to: [], cc: [], bcc: [], own_text: false, subject: "", body: "", extra_files: [], send_empty: false }));
    const ex = g.extra_files[0] || { name: "link.txt", text: "" };
    modal(`<div class="ml-ed"><h3>${isNew ? "Add group" : "Edit group: " + esc(g.name)}</h3>
      <label>Group name</label><input id="gN" value="${esc(g.name)}">
      <div class="g2"><div><label>Send as</label><select id="gM"><option value="pdf">PDF files</option><option value="jpg">JPG files</option><option value="zip">ZIP of the folder (always)</option></select></div>
      <div><label>If large</label><select id="gL"><option value="zip">Make a ZIP</option><option value="none">Send as they are</option></select></div></div>
      <label class="ck"><input type="checkbox" id="gRest" ${g.take_rest ? "checked" : ""}><span><b>Everything not taken by another group</b> <span class="dim">(new PDFs, like a new category, go here automatically)</span></span></label>
      <div id="gPick"><label>PDFs for this group. Tick the PDFs this group should get (PDF maker names, any folder)</label><input id="gFind" placeholder="Search a PDF name"><div class="tree" id="gTree"></div></div>
      <div id="gFold"><label id="gFoldT">Whole folders</label><div class="tree" id="gFolders"></div></div>
      <label>Other folder names (only if a folder is not in the list above)</label><datalist id="gDl">${CATS.map(f => `<option value="${esc(f.name)}">`).join("")}</datalist><div class="chips" id="gS" data-list="gDl"></div>
      <div class="g2"><div><label>Large = more than (files)</label><input id="gLf" type="number" min="1" placeholder="${c.limits.large_files} (global)" value="${g.large_files || ""}"></div><div><label>or more than (MB)</label><input id="gLm" type="number" min="1" placeholder="${c.limits.large_mb} (global)" value="${g.large_mb || ""}"></div></div>
      <div class="g2"><div><label>ZIP file name</label><input id="gZ" value="${esc(g.zip_name)}"></div><div><label>Folder name inside the ZIP (empty = same as source)</label><input id="gR" value="${esc(g.zip_root)}" placeholder="e.g. Edotco industry"></div></div>
      <label>Extra file added inside the ZIP (for example link.txt). Empty text = none</label><div class="g2"><input id="gEn" value="${esc(ex.name)}"><span></span></div><textarea id="gEt" rows="2" placeholder="Text of the file, for example the link">${esc(ex.text)}</textarea>
      <label>To</label><div class="chips" id="gTo"></div><label>CC</label><div class="chips" id="gCc"></div><label>Bcc</label><div class="chips" id="gBc"></div>
      <label class="ck"><input type="checkbox" id="gOwn" ${g.own_text ? "checked" : ""}><span>Use own subject and message for this group</span></label>
      <div id="gOwnBox" class="${g.own_text ? "" : "hidden"}"><input id="gSu" value="${esc(g.subject)}" placeholder="${esc(c.text.subject)}"><textarea id="gBo" rows="3" placeholder="${esc(c.text.body)}">${esc(g.body)}</textarea></div>
      <label class="ck"><input type="checkbox" id="gEn1" ${g.enabled ? "checked" : ""}><span>Include in the daily send</span></label>
      <label class="ck"><input type="checkbox" id="gEm" ${g.send_empty ? "checked" : ""}><span>Send even when there are no files (empty note)</span></label>
      <div class="modal-actions">${isNew ? "" : '<button class="btn bad" id="gDel">Delete group</button>'}<div class="grow"></div><button class="btn" id="gX">Cancel</button><button class="btn pri" id="gOk">Save</button></div></div>`, (m, close) => {
      $("#gM", m).value = g.mode; $("#gL", m).value = g.if_large;
      const todayCats = CATS.map(x => x.name), extra = g.sources.filter(x => !todayCats.includes(x)); chips($("#gS", m), extra, "folder name", null);
      // keys saved by older builds -> new name-based keys; whole-folder choice of a PDF group -> its PDFs
      g.items = g.items.map(k => { const r = PDFS.find(x => x.legacy === k); return r ? r.key : k; });
      g.from_cats = g.from_cats || [];
      if (g.mode === "pdf") { g.sources.forEach(n => { if (!g.from_cats.includes(n)) g.from_cats.push(n); }); g.sources = []; }
      const FK = () => ($("#gM", m).value === "pdf" ? "from_cats" : "sources");
      const tree = $("#gTree", m), fold = $("#gFolders", m);
      const drawTree = () => { const mode = $("#gM", m).value, rest = $("#gRest", m).checked, q = ($("#gFind", m).value || "").toLowerCase().trim();
        $("#gPick", m).classList.toggle("off", rest); $("#gFold", m).classList.remove("hidden"); $("#gFoldT", m).textContent = mode === "pdf" ? "Also take every PDF that was made from these folders (for example United Group = all PDFs of the United Group folder)" : "Whole folders (JPG / ZIP groups send every file of the folder)";
        const rows = PDFS.filter(x => !q || (x.short + " " + x.category).toLowerCase().includes(q));
        tree.innerHTML = rows.map(x => `<label class="ck ti"><input type="checkbox" data-key="${esc(x.key)}" ${g.items.includes(x.key) ? "checked" : ""} ${rest ? "disabled" : ""}><span>${esc(x.short)} <span class="dim">· from ${esc(x.category)}${x.kind === "combined" ? " (combined)" : ""}${x.hidden ? " · own PDF, the PDF maker does not make this one" : ""} · ${x.n ? x.n + " file" + (x.n === 1 ? "" : "s") + " today" : "not today"}</span></span></label>`).join("") || `<div class="dim sm">${PDFS.length ? "Nothing matches." : "No PDFs found yet. Save some clips first."}</div>`;
        const lost = g.items.filter(k => !PDFS.some(x => x.key === k));
        if (lost.length) tree.innerHTML += '<div class="dim sm" style="margin-top:6px">Chosen but not seen lately: ' + lost.map(k => esc(k.replace(/^pdf\|/, ""))).join(", ") + ' <a id="gClr">remove</a></div>';
        const cl = $("#gClr", m); if (cl) cl.onclick = () => { g.items = g.items.filter(k => PDFS.some(x => x.key === k)); drawTree(); };
        $$("input[data-key]", tree).forEach(i => i.onchange = () => { const k = i.dataset.key; if (i.checked) { if (!g.items.includes(k)) g.items.push(k); } else g.items = g.items.filter(x => x !== k); });
        fold.innerHTML = CATS.map(ct => `<label class="ck ti"><input type="checkbox" data-cat="${esc(ct.name)}" ${g[FK()].includes(ct.name) ? "checked" : ""}><span><b>${esc(ct.name)}</b> <span class="dim">${ct.n} file${ct.n === 1 ? "" : "s"} today</span></span></label>`).join("") || '<div class="dim sm">No folders yet.</div>';
        $$("input[data-cat]", fold).forEach(i => i.onchange = () => { const n = i.dataset.cat, k = FK(); if (i.checked) { if (!g[k].includes(n)) g[k].push(n); } else g[k] = g[k].filter(x => x !== n); }); };
      drawTree(); $("#gFind", m).oninput = drawTree; $("#gM", m).onchange = drawTree; $("#gRest", m).onchange = drawTree;
      $("#gOwn", m).onchange = (e) => $("#gOwnBox", m).classList.toggle("hidden", !e.target.checked);
      $("#gX", m).onclick = close;
      if (!isNew) $("#gDel", m).onclick = async () => { if (!confirm("Delete group " + g.name + "?")) return; c.groups = c.groups.filter(x => x.id !== g.id); await persist(); close(); await reload(true); };
      $("#gOk", m).onclick = async () => {
        g.name = $("#gN", m).value.trim(); if (!g.name) return toast("Give the group a name.", "warn", 2200);
        g.mode = $("#gM", m).value; if (g.mode === "pdf") { g.sources = []; } else { g.from_cats = []; g.sources = g.sources.filter(x => todayCats.includes(x)).concat(extra.filter(x => !g.sources.includes(x))); } g.take_rest = $("#gRest", m).checked;
        g.mode = $("#gM", m).value; g.if_large = $("#gL", m).value; g.large_files = +$("#gLf", m).value || null; g.large_mb = +$("#gLm", m).value || null;
        g.zip_name = $("#gZ", m).value.trim() || "{Group} {Date}.zip"; g.zip_root = $("#gR", m).value.trim(); g.extra_files = $("#gEt", m).value.trim() ? [{ name: $("#gEn", m).value.trim() || "link.txt", text: $("#gEt", m).value }] : [];
        g.own_text = $("#gOwn", m).checked; g.subject = $("#gSu", m).value; g.body = $("#gBo", m).value; g.enabled = $("#gEn1", m).checked; g.send_empty = $("#gEm", m).checked;
        const bad = g.to.concat(g.cc, g.bcc).filter(v => !EMAIL.test(v)); if (bad.length) return toast("Not a valid address: " + bad[0], "warn", 3500);
        const i = c.groups.findIndex(x => x.id === g.id); if (i >= 0) c.groups[i] = g; else c.groups.push(g);
        await persist(); delete S.plans[g.id]; close(); await reload(true); S.sel.add(g.id); drawRows();
      };
    });
  }

  // ───────── settings ─────────
  function settings() {
    const c = JSON.parse(JSON.stringify(cfg())), a = c.account;
    modal(`<div class="ml-ed"><h3>Mail settings</h3>
      <h4>Account</h4><div class="g2"><div><label>Mail service</label><select id="sK"><option value="gmail">Gmail / Google Workspace</option><option value="smtp">Other mail (SMTP)</option></select></div><div><label>Sender name</label><input id="sNm" value="${esc(a.name)}"></div></div>
      <div class="g2"><div><label>Sender address</label><input id="sE" value="${esc(a.email)}" placeholder="desk@company.com"></div><div><label>${S.d.has_password ? "Password (saved, type to change)" : "Password / app password"}</label><input id="sP" type="password" autocomplete="new-password" placeholder="${S.d.has_password ? "••••••••••••" : ""}"></div></div>
      <div id="sSm" class="${a.kind === "smtp" ? "" : "hidden"}"><div class="g3"><div><label>Server</label><input id="sH" value="${esc(a.host)}" placeholder="mail.company.com"></div><div><label>Port</label><input id="sPt" type="number" value="${a.port}"></div><div><label>Security</label><select id="sSe"><option value="ssl">SSL (465)</option><option value="starttls">STARTTLS (587)</option><option value="none">None</option></select></div></div><label>Login name (empty = sender address)</label><input id="sU" value="${esc(a.user || "")}"></div>
      <div class="g2"><button class="btn" id="sT">Test connection</button><span id="sTr" class="dim sm"></span></div>
      <h4>Default text</h4><label>Subject</label><input id="tS" value="${esc(c.text.subject)}"><label>Message</label><textarea id="tB" rows="4">${esc(c.text.body)}</textarea>
      <div class="g2"><div><label>Date format (%d-%m-%Y)</label><input id="tD" value="${esc(c.text.date_format)}"></div><div><label>Part label when split</label><input id="tP" value="${esc(c.text.part_label)}"></div></div>
      <h4>Sizes and big files</h4><div class="g3"><div><label>Large: more than (files)</label><input id="lF" type="number" value="${c.limits.large_files}"></div><div><label>or more than (MB)</label><input id="lM" type="number" value="${c.limits.large_mb}"></div><div><label>Max per mail (MB)</label><input id="lX" type="number" value="${c.limits.max_mail_mb}"></div></div>
      <label>When a mail is over the maximum</label><select id="lO"><option value="split">Split into parts</option><option value="drive">Send as Google Drive link (Gmail only, needs link sharing allowed)</option></select>
      <h4>Sending</h4><div class="g3"><div><label>Wait between mails (s)</label><input id="bW" type="number" value="${c.behaviour.wait_s}"></div><div><label>Retry failed (times)</label><input id="bR" type="number" value="${c.behaviour.retries}"></div><div><label>Reminder time</label><input id="bT" value="${esc(c.behaviour.remind_at)}"></div></div>
      <h4>Keep without updating NAB</h4><div class="dim sm">Groups, receivers, rules and texts are saved in a settings file on this PC. Copy them to another PC with Export and Import.</div>
      <div class="g2"><button class="btn" id="xD">Restore default groups (keeps receivers)</button><span></span></div>
      <div class="g2"><button class="btn" id="xE">Export settings (text)</button><button class="btn" id="xI">Import settings (paste)</button></div><textarea id="xT" rows="4" class="hidden" spellcheck="false"></textarea>
      <div class="modal-actions"><button class="btn" id="sX">Cancel</button><button class="btn pri" id="sOk">Save</button></div></div>`, (m, close) => {
      $("#sK", m).value = a.kind; $("#sSe", m).value = a.security; $("#lO", m).value = c.limits.over_max;
      $("#sK", m).onchange = (e) => { const g = e.target.value === "gmail"; $("#sSm", m).classList.toggle("hidden", g); if (g) { $("#sH", m).value = "smtp.gmail.com"; $("#sPt", m).value = 465; $("#sSe", m).value = "ssl"; } };
      const grab = () => { a.kind = $("#sK", m).value; a.name = $("#sNm", m).value.trim(); a.email = $("#sE", m).value.trim(); a.host = a.kind === "gmail" ? "smtp.gmail.com" : $("#sH", m).value.trim(); a.port = +$("#sPt", m).value || 465; a.security = a.kind === "gmail" ? "ssl" : $("#sSe", m).value; a.user = $("#sU", m).value.trim();
        c.text = { subject: $("#tS", m).value, body: $("#tB", m).value, date_format: $("#tD", m).value || "%d-%m-%Y", part_label: $("#tP", m).value || "Part {Part} of {Total}" };
        c.limits = { large_files: +$("#lF", m).value || 20, large_mb: +$("#lM", m).value || 20, max_mail_mb: +$("#lX", m).value || 24, over_max: $("#lO", m).value };
        c.behaviour.wait_s = +$("#bW", m).value || 0; c.behaviour.retries = +$("#bR", m).value || 0; c.behaviour.remind_at = $("#bT", m).value.trim(); };
      $("#sX", m).onclick = close;
      $("#sT", m).onclick = async () => { grab(); const pw = $("#sP", m).value; if (pw) await api("mail_password", { pw }); $("#sTr", m).textContent = "Testing…"; const r = await api("mail_test_conn", { cfg: c }); $("#sTr", m).textContent = r.ok ? "Connected. Login accepted." : r.error; $("#sTr", m).style.color = r.ok ? "var(--ok)" : "var(--bad)"; };
      $("#xD", m).onclick = async () => { if (!confirm("Replace the groups with the default list? Receivers of groups with the same name are kept.")) return; const d = await api("mail_defaults"); const old = Object.fromEntries(c.groups.map(g => [g.name, g]));
        c.groups = d.groups.map(g => { const o = old[g.name]; if (o) { g.to = o.to; g.cc = o.cc; g.bcc = o.bcc; g.extra_files = o.extra_files && o.extra_files.length ? o.extra_files : g.extra_files; } return g; }); toast("Default groups loaded. Press Save to keep.", "ok", 3000); };
      $("#xE", m).onclick = () => { grab(); const t = $("#xT", m); t.classList.remove("hidden"); t.value = JSON.stringify(c, null, 1); t.select(); try { document.execCommand("copy"); toast("Settings copied (no password inside).", "ok", 2500); } catch (e) { } };
      $("#xI", m).onclick = () => { const t = $("#xT", m); if (t.classList.contains("hidden") || !t.value.trim()) { t.classList.remove("hidden"); t.value = ""; t.placeholder = "Paste exported settings here, then press Import again"; t.focus(); return; }
        try { const j = JSON.parse(t.value); if (!j.groups) throw 0; Object.assign(c, j); c.account = Object.assign({}, j.account || {}); toast("Imported. Press Save to keep.", "ok", 2500); } catch (e) { toast("That is not valid exported settings.", "error", 3000); } };
      $("#sOk", m).onclick = async () => { grab(); const pw = $("#sP", m).value; if (pw) await api("mail_password", { pw }); S.d.cfg = c; const r = await api("mail_save", { cfg: c }); if (!r.ok) return toast(r.error, "error", 4000); close(); await reload(true); toast("Mail settings saved", "ok", 1800); };
    });
  }

  window.TOOLS.mail = { mount, show };
})();
