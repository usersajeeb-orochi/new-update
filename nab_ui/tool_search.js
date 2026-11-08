// tool_search.js — OCR search inside the app.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  let el, res = [];
  function mount(e) {
    el = e;
    el.innerHTML = `<div class="tk pdf"><div class="card"><div class="tk-bar"><input id="sQ" placeholder="Keywords, separated by commas…" style="flex:1;min-width:240px"><label class="row"><input type="checkbox" id="sAll"> Match all</label><input type="date" id="sFrom" title="From"><input type="date" id="sTo" title="To"><button class="btn pri" id="sGo">🔎 Search</button></div>
      <div class="tk-bar" style="margin-top:8px"><span id="sInfo" class="sub grow"></span><button class="btn" id="sIdx">⚙ Update index</button><button class="btn" id="sCfg">Folders</button></div><div class="pd-prog"><div id="sBar"></div></div><div id="sErr" class="tag warn" style="display:none"></div></div>
      <div class="tk-body" id="sRes"></div><div class="tk-foot"><span class="grow"></span><input id="sDest" placeholder="Copy results to folder…" style="width:260px"><button class="btn" id="sCopy">Copy results</button></div></div>`;
    $("#sGo").onclick = find; $("#sQ").addEventListener("keydown", ev => { if (ev.key === "Enter") find(); });
    $("#sIdx").onclick = async () => { if ($("#sIdx").dataset.run) { await api("search_stop"); return; } const r = await api("search_index"); if (!r.ok) toast(r.error, "error", 5000); else { $("#sIdx").dataset.run = 1; $("#sIdx").textContent = "⏹ Stop"; } };
    $("#sCfg").onclick = cfg; $("#sCopy").onclick = async () => { const r = await api("search_copy", { dest: $("#sDest").value, paths: res.map(x => x.path) }); toast(r.ok ? r.n + " file(s) copied ✓" : r.error, r.ok ? "ok" : "error", 3000); };
    on("tool", (ev) => { if (ev.tool !== "search") return;
      if (ev.ev === "prog" || ev.ev === "begin") { $("#sBar").style.width = ev.total ? Math.round((ev.n || 0) * 100 / ev.total) + "%" : "0"; $("#sInfo").textContent = "Indexing " + (ev.n || 0) + "/" + ev.total + (ev.name ? " · " + ev.name : ""); }
      if (ev.ev === "done") { delete $("#sIdx").dataset.run; $("#sIdx").textContent = "⚙ Update index"; $("#sBar").style.width = "100%"; $("#sInfo").textContent = ev.error ? "❌ " + ev.error : "Index ready — " + ev.count + " images"; } });
  }
  async function show() { const s = await api("search_state"); $("#sInfo").textContent = s.count + " images indexed"; const e = $("#sErr"); e.style.display = s.tess_error ? "" : "none"; e.textContent = s.tess_error || ""; if (!s.count && !s.tess_error) $("#sInfo").textContent = "Nothing indexed yet — press Update index."; }
  async function find() {
    const r = await api("search_find", { q: $("#sQ").value, all: $("#sAll").checked, from: $("#sFrom").value, to: $("#sTo").value });
    if (!r.ok) return toast(r.error, "error", 2500); res = r.results;
    $("#sRes").innerHTML = `<p class="sub">${r.total} match${r.total === 1 ? "" : "es"}${r.total > res.length ? " (showing " + res.length + ")" : ""}</p>` + res.map((x, i) => `<div class="card" data-i="${i}"><b>${esc(x.name)}</b> <span class="tag">${esc(x.date)}</span><div class="sub">${esc(x.snip)}</div><div class="tk-foot"><button class="btn" data-a="o">Open</button><button class="btn" data-a="r">Show folder</button></div></div>`).join("");
    $$("#sRes .card").forEach(c => { const x = res[+c.dataset.i]; c.querySelector('[data-a=o]').onclick = () => api("search_open", { path: x.path }); c.querySelector('[data-a=r]').onclick = () => api("search_reveal", { path: x.path }); });
  }
  async function cfg() {
    const s = await api("search_state");
    C.modal(`<h3>Folders to search</h3><textarea id="fF" rows="5" style="width:100%">${esc(s.folders.join("\n"))}</textarea><div class="field"><label>OCR language</label><select id="fL">${["eng+ben", "eng", "ben"].map(l => `<option ${l === s.lang ? "selected" : ""}>${l}</option>`).join("")}</select></div><div class="modal-actions"><button class="btn" id="fNo">Cancel</button><button class="btn pri" id="fOk">Save</button></div>`, (c, close) => {
      $("#fNo").onclick = close; $("#fOk").onclick = async () => { await api("search_folders", { folders: $("#fF").value.split("\n"), lang: $("#fL").value }); close(); toast("Saved — press Update index", "ok", 2500); }; });
  }
  window.TOOLS.search = { mount, show };
})();
