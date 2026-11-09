// tool_search.js - Search and archive: every saved clip, by words, paper, category, page, date or who saved it.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  let el, res = [], lastQ = {};
  const opt = (arr, cur) => '<option value="">Any</option>' + (arr || []).map(x => `<option ${x === cur ? "selected" : ""}>${esc(x)}</option>`).join("");

  function mount(e) {
    el = e;
    el.innerHTML = `<div class="tk pdf"><div class="card">
      <div class="tk-bar"><input id="sQ" placeholder="Words in the clip, separated by commas (leave empty to use only the filters)" style="flex:1;min-width:260px"><label class="row"><input type="checkbox" id="sAll"> Match all words</label><button class="btn pri" id="sGo">Search</button></div>
      <div class="tk-bar" style="margin-top:8px;flex-wrap:wrap">
        <label class="sub">Paper <select id="sPaper"></select></label><label class="sub">Category <select id="sCat"></select></label><label class="sub">Page <select id="sPage"></select></label><label class="sub">Saved by <select id="sUser"></select></label>
        <label class="sub">From <input type="date" id="sFrom"></label><label class="sub">To <input type="date" id="sTo"></label><button class="btn" id="sClear">Clear</button>
      </div>
      <div class="tk-bar" style="margin-top:8px;flex-wrap:wrap"><span class="sub">Saved searches</span><span id="sSaved" class="row" style="gap:6px;flex-wrap:wrap"></span><button class="btn" id="sSave">Save this search</button></div>
      <div class="tk-bar" style="margin-top:8px"><span id="sInfo" class="sub grow"></span><button class="btn" id="sDup">Find duplicates</button><button class="btn" id="sScan">Refresh list</button><button class="btn" id="sIdx">Read text (OCR)</button><button class="btn" id="sCfg">Folders</button></div>
      <div class="pd-prog"><div id="sBar"></div></div><div id="sErr" class="tag warn" style="display:none"></div></div>
      <div class="tk-body" id="sRes"></div>
      <div class="tk-foot"><span class="grow"></span><input id="sDest" placeholder="Copy results to folder" style="width:240px"><button class="btn" id="sCopy">Copy results</button><button class="btn" id="sXls">Export to Excel</button><button class="btn" id="sCsv">Export to CSV</button></div></div>`;
    $("#sGo").onclick = find;
    $("#sQ").addEventListener("keydown", ev => { if (ev.key === "Enter") find(); });
    $("#sClear").onclick = () => { $("#sQ").value = ""; ["sPaper", "sCat", "sPage", "sUser"].forEach(i => $("#" + i).value = ""); $("#sFrom").value = $("#sTo").value = ""; };
    $("#sScan").onclick = async () => { $("#sInfo").textContent = "Reading the folders…"; await api("search_scan"); };
    $("#sIdx").onclick = async () => { if ($("#sIdx").dataset.run) { await api("search_stop"); return; } const r = await api("search_index"); if (!r.ok) toast(r.error, "error", 5000); else { $("#sIdx").dataset.run = 1; $("#sIdx").textContent = "Stop"; } };
    $("#sCfg").onclick = cfg;
    $("#sCopy").onclick = async () => { const r = await api("search_copy", { dest: $("#sDest").value, paths: res.map(x => x.path) }); toast(r.ok ? r.n + " file(s) copied" : r.error, r.ok ? "ok" : "error", 3000); };
    $("#sXls").onclick = () => exp("xlsx"); $("#sCsv").onclick = () => exp("csv");
    $("#sSave").onclick = saveSearch; $("#sDup").onclick = dups;
    on("tool", (ev) => { if (ev.tool !== "search") return;
      if (ev.ev === "scan") { $("#sBar").style.width = ev.total ? Math.round(ev.n * 100 / ev.total) + "%" : "0"; $("#sInfo").textContent = "Reading " + ev.n + "/" + ev.total; }
      if (ev.ev === "scan_done") { $("#sBar").style.width = "100%"; $("#sInfo").textContent = ev.error ? "Problem: " + ev.error : "List ready: " + ev.total + " clips (" + ev.added + " new, " + ev.removed + " gone)"; loadFacets(); }
      if (ev.ev === "prog" || ev.ev === "begin") { $("#sBar").style.width = ev.total ? Math.round((ev.n || 0) * 100 / ev.total) + "%" : "0"; $("#sInfo").textContent = "Reading text " + (ev.n || 0) + "/" + ev.total + (ev.name ? " - " + ev.name : ""); }
      if (ev.ev === "done") { delete $("#sIdx").dataset.run; $("#sIdx").textContent = "Read text (OCR)"; $("#sBar").style.width = "100%"; $("#sInfo").textContent = ev.error ? "Problem: " + ev.error : "Text ready for " + ev.count + " images"; } });
  }

  const q = () => ({ q: $("#sQ").value, all: $("#sAll").checked, paper: $("#sPaper").value, cat: $("#sCat").value, page: $("#sPage").value, user: $("#sUser").value, date_from: $("#sFrom").value, date_to: $("#sTo").value });
  const setQ = (v) => { $("#sQ").value = v.q || ""; $("#sAll").checked = !!v.all; $("#sPaper").value = v.paper || ""; $("#sCat").value = v.cat || ""; $("#sPage").value = v.page || ""; $("#sUser").value = v.user || ""; $("#sFrom").value = v.date_from || ""; $("#sTo").value = v.date_to || ""; };

  async function loadFacets() {
    const f = await api("search_facets"); if (!f.ok) return;
    const keep = q();
    $("#sPaper").innerHTML = opt(f.papers); $("#sCat").innerHTML = opt(f.cats); $("#sPage").innerHTML = opt(f.pages); $("#sUser").innerHTML = opt(f.users);
    setQ(keep);
    drawSaved(f.saved);
  }
  function drawSaved(list) {
    const b = $("#sSaved"); b.innerHTML = (list || []).length ? list.map((s, i) => `<span class="tag" style="cursor:pointer" data-i="${i}">${esc(s.name)} <b data-x="${i}" title="Delete" style="margin-left:6px;opacity:.7">x</b></span>`).join("") : '<span class="sub">none yet</span>';
    b.querySelectorAll("[data-i]").forEach(t => t.onclick = (ev) => {
      const i = +t.dataset.i;
      if (ev.target.dataset.x !== undefined) { api("search_saved_delete", { name: list[i].name }).then(r => drawSaved(r.saved)); return; }
      setQ(list[i].query); find();
    });
  }
  function saveSearch() {
    C.modal(`<h3>Save this search</h3><p class="sub">It appears as a button above so you can run it again in one click.</p><div class="field"><input id="ssN" maxlength="60" placeholder="for example Bank this week"></div><div class="modal-actions"><button class="btn" id="ssNo">Cancel</button><button class="btn pri" id="ssOk">Save</button></div>`, (cd, close) => {
      $("#ssNo").onclick = close; $("#ssOk").onclick = async () => { const n = $("#ssN").value.trim(); if (!n) return; const r = await api("search_saved_put", { name: n, query: q() }); close(); drawSaved(r.saved); toast("Saved", "ok", 1500); };
    });
  }

  async function show() {
    const s = await api("search_state");
    const e = $("#sErr"); e.style.display = s.tess_error ? "" : "none"; e.textContent = s.tess_error ? s.tess_error + " Searching by paper, category, page and date still works." : "";
    $("#sInfo").textContent = s.count ? s.count + " clips in the archive, " + s.ocr_count + " with text" : "Nothing in the archive yet. Press Refresh list.";
    loadFacets();
    api("search_scan");                       // quick, quiet: picks up new, renamed and deleted clips
  }

  async function find() {
    lastQ = q();
    const r = await api("search_find", lastQ);
    if (!r.ok) return toast(r.error, "error", 2500);
    res = r.results;
    $("#sRes").innerHTML = `<p class="sub">${r.total}${r.more ? "+" : ""} clip${r.total === 1 ? "" : "s"}${r.more ? " (showing the first " + res.length + ")" : ""}</p>` +
      (res.length ? '<table class="t"><thead><tr><td>Paper</td><td>Date</td><td>Page</td><td>Pos</td><td>Size</td><td>Category</td><td>Saved by</td><td></td></tr></thead><tbody>' +
        res.map((x, i) => `<tr data-i="${i}"><td><b>${esc(x.paper || x.name)}</b>${x.snip ? `<div class="sub">${esc(x.snip)}</div>` : ""}</td><td>${esc(x.date)}</td><td>${esc(x.page)}</td><td>${esc(x.pos)}</td><td>${esc(x.size)}</td><td>${esc(x.cat)}</td><td>${esc(x.user)}</td><td><button class="btn mini" data-a="o">Open</button> <button class="btn mini" data-a="r">Folder</button></td></tr>`).join("") + "</tbody></table>" : '<p class="sub">Nothing found.</p>');
    $$("#sRes tr[data-i]").forEach(c => { const x = res[+c.dataset.i]; c.querySelector('[data-a=o]').onclick = () => api("search_open", { path: x.path }); c.querySelector('[data-a=r]').onclick = () => api("search_reveal", { path: x.path }); });
  }

  async function exp(kind) {
    const r = await api("search_export", Object.assign({}, q(), { kind }));
    if (!r.ok) return toast(r.error, "error", 3000);
    toast("Saved " + r.n + " rows to " + r.path, "ok", 6000);
    api("search_reveal", { path: r.path });
  }

  async function dups() {
    $("#sInfo").textContent = "Looking for clips that look the same…";
    const r = await api("search_dups", { dist: 2 });
    const g = r.groups || [];
    $("#sInfo").textContent = g.length ? g.length + " group(s) of look-alike clips" : "No look-alike clips found";
    $("#sRes").innerHTML = g.length ? g.map((grp, gi) => `<div class="card"><b>Group ${gi + 1}</b>${grp.map((x, i) => `<div class="row" style="gap:8px;margin-top:6px"><span class="grow">${esc(x.name)}</span><button class="btn mini" data-o="${gi}.${i}">Open</button><button class="btn mini" data-d="${gi}.${i}">Delete</button></div>`).join("")}</div>`).join("") : '<p class="sub">Nothing to clean up.</p>';
    $$("#sRes [data-o]").forEach(b => b.onclick = () => { const [gi, i] = b.dataset.o.split(".").map(Number); api("search_open", { path: g[gi][i].path }); });
    $$("#sRes [data-d]").forEach(b => b.onclick = () => { const [gi, i] = b.dataset.d.split(".").map(Number); const x = g[gi][i];
      C.modal(`<h3>Delete this clip?</h3><p class="sub">${esc(x.name)}</p><p class="sub">The file is removed from your folder. This cannot be undone.</p><div class="modal-actions"><button class="btn" id="dNo">Cancel</button><button class="btn pri" id="dYes">Delete</button></div>`, (cd, close) => {
        $("#dNo").onclick = close; $("#dYes").onclick = async () => { const r = await api("search_delete_files", { paths: [x.path] }); close(); toast(r.n ? "Deleted" : "Could not delete", r.n ? "ok" : "error", 2000); if (r.n) b.closest(".row").remove(); };
      }); });
  }

  async function cfg() {
    const s = await api("search_state");
    C.modal(`<h3>Folders to search</h3><textarea id="fF" rows="5" style="width:100%">${esc(s.folders.join("\n"))}</textarea><div class="field"><label>Text reading language</label><select id="fL">${["eng+ben", "eng", "ben"].map(l => `<option ${l === s.lang ? "selected" : ""}>${l}</option>`).join("")}</select></div><div class="modal-actions"><button class="btn" id="fNo">Cancel</button><button class="btn pri" id="fOk">Save</button></div>`, (cd, close) => {
      $("#fNo").onclick = close; $("#fOk").onclick = async () => { await api("search_folders", { folders: $("#fF").value.split("\n"), lang: $("#fL").value }); close(); toast("Saved. Press Refresh list.", "ok", 2500); };
    });
  }
  window.TOOLS.search = { mount, show };
})();
