// tool_pdf.js — PDF Maker as an in-app screen.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  const S = { tab: "make", cfg: null, days: [], running: false, total: 0, el: null };
  const lines = (t) => t.split("\n").map(s => s.trim()).filter(Boolean);
  const kvLines = (o, sep) => Object.keys(o).map(k => k + sep + (Array.isArray(o[k]) ? o[k].join(", ") : o[k])).join("\n");

  function mount(el) {
    S.el = el;
    el.innerHTML = '<div class="tk pdf"><div class="tk-tabs"><button data-k="make">Make PDFs</button><button data-k="set">Settings</button></div><div class="tk-body" id="pdBody"></div></div>';
    $$(".tk-tabs button", el).forEach(b => b.onclick = () => go(b.dataset.k));
    on("tool", (ev) => {
      if (ev.tool !== "pdf") return;
      const lg = $("#pdLog"), bar = $("#pdBar"), st = $("#pdSt"); if (!st) return;
      if (ev.ev === "scan") st.textContent = ev.text;
      if (ev.ev === "begin") { S.total = ev.total; st.textContent = "Building " + ev.total + " PDF(s)…"; bar.style.width = "2%"; }
      if (ev.ev === "item") { bar.style.width = Math.round(ev.n * 100 / ev.total) + "%"; st.textContent = "Progress " + ev.n + "/" + ev.total;
        const d = document.createElement("div"); d.className = "pd-l " + ev.level; d.textContent = (ev.level === "bad" ? "❌ " : ev.level === "warn" ? "⚠ " : "✅ ") + ev.msg; lg.appendChild(d); lg.scrollTop = 1e9; }
      if (ev.ev === "done") { S.running = false; $("#pdGo").disabled = false; bar.style.width = ev.total ? "100%" : "0";
        st.textContent = ev.msg || ("✅ " + ev.ok + "/" + ev.total + " done in " + ev.secs + "s"); if (ev.msg) toast(ev.msg, "warn", 4000); else toast("PDFs ready ✓", "ok", 2500); }
    });
  }
  async function show() { go(S.tab); }
  function go(k) { S.tab = k; $$(".tk-tabs button", S.el).forEach(b => b.classList.toggle("on", b.dataset.k === k)); (k === "make" ? vMake : vSet)(); }

  async function vMake() {
    const r = await api("pdf_days"); S.days = r.days || [];
    $("#pdBody").innerHTML = `<div class="card"><h4>Which day?</h4><div class="eod-g" id="pdDays">${S.days.length ? S.days.map(d => `<button class="chip" data-p="${esc(d.path)}">${d.label}${d.pdf ? " · PDF ✓" : ""}</button>`).join("") : '<span class="sub">No day folders found under ' + esc(r.base) + "</span>"}</div>
      <div class="field" style="margin-top:10px"><label>Folder</label><input id="pdPath" value="${esc(S.days[0] ? S.days[0].path : r.today)}"></div>
      <div class="tk-foot"><button class="btn" id="pdPrev">👁 Preview</button><span class="grow"></span><button class="btn" id="pdOpen">📂 Open folder</button><button class="btn pri" id="pdGo">📄 Make PDFs</button></div></div>
      <div class="card" id="pdPv" style="display:none"></div>
      <div class="pd-prog"><div id="pdBar"></div></div><div id="pdSt" class="sub">Ready.</div><div id="pdLog" class="pd-log"></div>`;
    $$("#pdDays .chip").forEach(b => b.onclick = () => { $("#pdPath").value = b.dataset.p; $$("#pdDays .chip").forEach(x => x.classList.toggle("ok", x === b)); preview(); });
    $("#pdPrev").onclick = preview;
    $("#pdOpen").onclick = async () => { const x = await api("pdf_open", { path: $("#pdPath").value }); if (!x.ok) toast(x.error, "error", 3000); };
    $("#pdGo").onclick = async () => { $("#pdLog").innerHTML = ""; $("#pdBar").style.width = "0"; $("#pdSt").textContent = "Starting…"; $("#pdGo").disabled = true; S.running = true;
      const x = await api("pdf_start", { path: $("#pdPath").value }); if (!x.ok) { toast(x.error, "error", 3500); $("#pdGo").disabled = false; S.running = false; $("#pdSt").textContent = x.error; } };
    $("#pdPath").addEventListener("keydown", (e) => { if (e.key === "Enter") preview(); });
    if (S.days.length) preview();
  }
  async function preview() {
    const pv = $("#pdPv"); const r = await api("pdf_preview", { path: $("#pdPath").value }); pv.style.display = "";
    if (!r.ok) { pv.innerHTML = '<span class="tag bad">' + esc(r.error) + "</span>"; return; }
    pv.innerHTML = r.items.length ? "<h4>" + r.items.length + " PDF(s) will be made</h4>" + r.items.map(i => `<div class="kv" style="grid-template-columns:1fr auto"><span>${esc(i.name)}</span><span class="tag">${i.pages} page${i.pages > 1 ? "s" : ""}</span></div>`).join("") : '<span class="tag warn">Nothing to make here — check the folder, or Categories / Blacklist in Settings.</span>';
  }

  async function vSet() {
    const r = await api("pdf_config"), c = S.cfg = r.cfg;
    $("#pdBody").innerHTML = `<div class="card"><h4>Compression</h4>
      <label class="row"><input type="checkbox" id="cEn" ${c.compress_enabled ? "checked" : ""}> Compress images</label>
      <label class="row"><input type="checkbox" id="cSm" ${c.smart_compression ? "checked" : ""}> Smart (only images over 400 KB)</label>
      <div class="field"><label>Manual quality (when Smart is off): <b id="qV">${c.manual_quality}</b>%</label><input type="range" id="cQ" min="20" max="100" value="${c.manual_quality}"></div>
      <label class="row"><input type="checkbox" id="cOpen" ${c.auto_open ? "checked" : ""}> Open the folder when finished</label></div>
      <div class="card"><h4>Categories to process <span class="sub">(one per line)</span></h4><textarea id="cCat" rows="4">${esc(c.categories_to_process.join("\n"))}</textarea></div>
      <div class="card"><h4>Newspaper order <span class="sub">(top = first page)</span></h4><textarea id="cSort" rows="8">${esc(c.sort_order.join("\n"))}</textarea></div>
      <div class="card"><h4>File names for sub-folders <span class="sub">(Folder = name pattern, {date} is replaced)</span></h4><textarea id="cNames" rows="5">${esc(kvLines(c.custom_names, " = "))}</textarea>
        <div class="field"><label>Default pattern ({folder}, {date})</label><input id="cGen" value="${esc(c.generic_pattern)}"></div></div>
      <div class="card"><h4>Combined PDFs <span class="sub">(Name pattern = Folder, Folder, …)</span></h4><textarea id="cGrp" rows="4">${esc(kvLines(c.combined_groups, " = "))}</textarea>
        <h4 style="margin-top:10px">Only in combined PDF <span class="sub">(no own PDF)</span></h4><textarea id="cGo" rows="2">${esc(c.group_only.join("\n"))}</textarea></div>
      <div class="card"><h4>Skip these folders</h4><textarea id="cBl" rows="3">${esc(c.blacklist.join("\n"))}</textarea></div>
      <div class="tk-foot"><button class="btn" id="cReset">Reset to defaults</button><span class="grow"></span><button class="btn pri" id="cSave">Save settings</button></div>`;
    $("#cQ").oninput = () => $("#qV").textContent = $("#cQ").value;
    $("#cReset").onclick = async () => { if (!confirm("Reset PDF settings to defaults?")) return; await api("pdf_config_reset"); vSet(); toast("Reset ✓", "ok", 1500); };
    $("#cSave").onclick = async () => {
      const parse = (t, sep) => { const o = {}; lines(t).forEach(l => { const i = l.indexOf("="); if (i > 0) o[l.slice(0, i).trim()] = l.slice(i + 1).trim(); }); return o; };
      const names = parse($("#cNames").value), grp = parse($("#cGrp").value); Object.keys(grp).forEach(k => grp[k] = grp[k].split(",").map(s => s.trim()).filter(Boolean));
      const cfg = { compress_enabled: $("#cEn").checked, smart_compression: $("#cSm").checked, manual_quality: +$("#cQ").value, auto_open: $("#cOpen").checked,
        categories_to_process: lines($("#cCat").value), sort_order: lines($("#cSort").value), custom_names: names, generic_pattern: $("#cGen").value.trim() || "{folder} {date}.pdf",
        combined_groups: grp, group_only: lines($("#cGo").value), blacklist: lines($("#cBl").value) };
      const x = await api("pdf_config_save", { cfg }); toast(x.ok ? "Saved ✓" : "Could not save", x.ok ? "ok" : "error", 2000); };
  }
  window.TOOLS.pdf = { mount, show };
})();
