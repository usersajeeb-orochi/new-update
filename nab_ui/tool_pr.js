// tool_pr.js — PR Value Calculator (print / online / TV), rates looked up automatically.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, toast } = C;
  let el, S = null, D = { print: [], online: [], tv: [] }, mult = 3.5, tab = "print", lists = {};
  const n = (v) => { v = parseFloat(String(v).replace(/,/g, "")); return isFinite(v) ? v : 0; };
  const money = (v) => v.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 0 });
  const val = { print: r => n(r.colinch) * n(r.ad) * mult, online: r => n(r.w) * n(r.h) * n(r.rate) * mult, tv: r => n(r.secs) * n(r.rate) * mult };
  const tot = (k) => D[k].reduce((a, r) => a + val[k](r), 0);
  const save = C.debounce(() => api("pr_save", { print: D.print, online: D.online, tv: D.tv, multiplier: mult }), 400);
  const HTML = `<div class="tk"><div class="pr-top"><div><h2>PR Value Calculator</h2><div class="sub">Rates are filled in for you. Print comes from your saved clips, online from the Screenshot Bot.</div></div><span style="flex:1"></span>
    <label class="lbl">PR multiplier <input id="prMult" type="number" step="0.1" min="0.1" class="mini-in" style="width:76px"></label><button class="btn" id="prRates">Rates</button><button class="btn pri" id="prExp">Export .xlsx</button></div>
    <div class="stats"><div class="stat" style="--c:#5b8cff"><i></i><small>Print</small><b id="stP">0</b></div><div class="stat" style="--c:#22c55e"><i></i><small>Online</small><b id="stO">0</b></div><div class="stat" style="--c:#f59e0b"><i></i><small>TV</small><b id="stT">0</b></div><div class="stat total"><i></i><small>Grand total (Tk)</small><b id="stA">0</b></div></div>
    <div class="tk-bar"><div class="tabs-s" id="prTabs"><button data-t="print" class="on">Print</button><button data-t="online">Online</button><button data-t="tv">TV</button></div><span id="prImp" class="tk-bar"></span><span style="flex:1"></span><button class="btn sm" id="prAI">AI summary</button><button class="btn sm" id="prAdd">Add row</button><button class="btn sm" id="prClr">Clear tab</button></div>
    <div class="drop" id="prDrop"><input type="file" id="prFile" multiple style="display:none"><span id="prDropT"></span></div><div class="grid-wrap" id="prGrid"></div><datalist id="dlP"></datalist><datalist id="dlO"></datalist><datalist id="dlT"></datalist></div>`;
  function totals() { $("#stP").textContent = money(tot("print")); $("#stO").textContent = money(tot("online")); $("#stT").textContent = money(tot("tv")); $("#stA").textContent = money(tot("print") + tot("online") + tot("tv")); }
  const sel = (opts, v, f) => `<select data-f="${f}">${opts.map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  const inp = (f, v, cls, ph, list) => `<td class="${cls || ""}"><input data-f="${f}" value="${esc(v == null ? "" : v)}" ${ph ? `placeholder="${ph}"` : ""} ${list ? `list="${list}"` : ""}></td>`;
  function grid() {
    const rows = D[tab], g = $("#prGrid"); let h = "";
    if (tab === "print") h = `<thead><tr><th style="width:26%">Media</th><th>Page type</th><th>Ink</th><th>Col x Inch</th><th>Ad value</th><th style="text-align:right">PR value</th><th></th></tr></thead>` + rows.map((r, i) => `<tr data-i="${i}">${inp("media", r.media, "", "Daily Star", "dlP")}<td>${sel(S.page_types, r.page_type || "Inner Page", "page_type")}</td><td>${sel(["Colour", "B/W"], r.colour === false ? "B/W" : "Colour", "colour")}</td>${inp("colinch", r.colinch, "n")}${inp("ad", r.ad, "n")}<td class="v">${money(val.print(r))}${r.note ? `<span class="nr">${esc(r.note)}</span>` : ""}</td><td class="x"><button class="mini" data-x>x</button></td></tr>`).join("");
    else if (tab === "online") h = `<thead><tr><th style="width:26%">Media</th><th>Date</th><th>Tier</th><th>Width</th><th>Height</th><th>Rate</th><th style="text-align:right">PR value</th><th></th></tr></thead>` + rows.map((r, i) => `<tr data-i="${i}">${inp("media", r.media, "", "bssnews.net", "dlO")}${inp("date", r.date, "", "yyyy-mm-dd")}${inp("tier", r.tier, "n")}${inp("w", r.w, "n")}${inp("h", r.h, "n")}${inp("rate", r.rate, "n")}<td class="v">${money(val.online(r))}${r.note ? `<span class="nr">${esc(r.note)}</span>` : ""}</td><td class="x"><button class="mini" data-x>x</button></td></tr>`).join("");
    else h = `<thead><tr><th style="width:26%">Channel</th><th>Date</th><th>Peak / Off</th><th>Seconds</th><th>Rate / sec</th><th style="text-align:right">PR value</th><th></th></tr></thead>` + rows.map((r, i) => `<tr data-i="${i}">${inp("media", r.media, "", "NTV", "dlT")}${inp("date", r.date, "", "yyyy-mm-dd")}${inp("peak", r.peak, "", "Peak")}${inp("secs", r.secs, "n")}${inp("rate", r.rate, "n")}<td class="v">${money(val.tv(r))}</td><td class="x"><button class="mini" data-x>x</button></td></tr>`).join("");
    g.innerHTML = rows.length ? `<table class="g">${h}</table>` : `<div class="empty-s"><b>No ${tab} rows yet</b><br>${tab === "print" ? "Use Import saved clips, or Add row." : tab === "online" ? "Use Import screenshots, or Add row." : "Add a row for each channel."}</div>`;
    $$("#prGrid tr[data-i]").forEach(tr => {
      const r = rows[+tr.dataset.i];
      tr.querySelectorAll("[data-f]").forEach(e => e.addEventListener("change", async () => {
        const f = e.dataset.f; r[f] = f === "colour" ? e.value === "Colour" : e.value; delete r.auto;
        if (["media", "page_type", "colour"].includes(f) || (tab !== "print" && f === "media")) await lookup(r);
        totals(); save(); grid();
      }));
      tr.querySelector("[data-x]").onclick = () => { rows.splice(+tr.dataset.i, 1); totals(); save(); grid(); };
    });
  }
  async function lookup(r) {
    const q = { kind: tab, media: r.media, page_type: r.page_type || "Inner Page", colour: r.colour !== false };
    const x = await api("pr_lookup", q);
    if (x.ok) { if (tab === "print") r.ad = x.rate; else { r.rate = x.rate; r.tier = x.tier != null ? x.tier : r.tier; } r.note = ""; } else r.note = r.media ? "no rate found" : "";
  }
  function imp() {
    const b = $("#prImp"), today = S.date;
    b.innerHTML = tab === "print" ? `<input type="date" id="iF" value="${today}" class="mini-in"><input type="date" id="iT" value="${today}" class="mini-in"><label class="lbl"><input type="checkbox" id="iC" checked> Colour</label><button class="btn sm" id="iGo">Import saved clips</button>`
      : tab === "online" ? `<button class="btn sm" id="iGo">Import screenshots</button><span class="lbl">reads the Screenshot Bot results</span>` : "";
    const go = $("#iGo"); if (!go) return;
    go.onclick = async () => {
      const r = tab === "print" ? await api("pr_import_print", { from: $("#iF").value, to: $("#iT").value, colour: $("#iC").checked }) : await api("pr_import_online", {});
      if (!r.ok) return toast(r.error || "Import failed", "error", 4000);
      D = r.data; totals(); grid(); toast(`${r.added} row(s) added` + (r.no_rate ? `, ${r.no_rate} without a rate` : ""), r.added ? "ok" : "warn", 3500);
    };
  }

  // ───────── upload: the screen measures each file itself (no big uploads) ─────────
  const loadImg = (f) => new Promise((res, rej) => { const u = URL.createObjectURL(f), im = new Image(); im.onload = () => { const k = Math.min(1, 1100 / Math.max(im.width, im.height)), c = document.createElement("canvas"); c.width = Math.round(im.width * k); c.height = Math.round(im.height * k); c.getContext("2d").drawImage(im, 0, 0, c.width, c.height); const o = { w: im.naturalWidth, h: im.naturalHeight, thumb: c.toDataURL("image/jpeg", .7) }; URL.revokeObjectURL(u); res(o); }; im.onerror = () => { URL.revokeObjectURL(u); rej(); }; im.src = u; });
  const loadVid = (f) => new Promise((res, rej) => { const u = URL.createObjectURL(f), v = document.createElement("video"); v.preload = "metadata"; v.muted = true; v.onloadedmetadata = () => { const d = v.duration; if (!isFinite(d)) { URL.revokeObjectURL(u); return rej(); } v.currentTime = Math.min(1, d / 2); }; v.onseeked = () => { let th = null; try { const c = document.createElement("canvas"), k = Math.min(1, 900 / Math.max(v.videoWidth, 1)); c.width = v.videoWidth * k; c.height = v.videoHeight * k; c.getContext("2d").drawImage(v, 0, 0, c.width, c.height); th = c.toDataURL("image/jpeg", .7); } catch (e) { } URL.revokeObjectURL(u); res({ secs: v.duration, w: v.videoWidth, h: v.videoHeight, thumb: th }); }; v.onerror = () => { URL.revokeObjectURL(u); rej(); }; v.src = u; });
  async function upload(files) {
    files = [...files]; if (!files.length) return; const isV = tab === "tv", items = [], bad = [];
    $("#prDropT").textContent = "Measuring " + files.length + " file(s)...";
    for (const f of files) { try { const m = isV ? await loadVid(f) : await loadImg(f); items.push(Object.assign({ name: f.name }, m)); } catch (e) { bad.push(f.name); } }
    if (items.length) { $("#prDropT").textContent = "Reading names with AI..."; const r = await api("pr_analyze", { kind: tab, items, colour: true }); if (r.ok) { D = r.data; totals(); grid(); toast(`${r.added} added` + (r.ai ? ` (AI helped on ${r.ai})` : ""), "ok", 3000); } else toast(r.error || "Failed", "error", 4000); }
    if (bad.length) toast("Could not read: " + bad.slice(0, 3).join(", "), "warn", 5000);
    dropText();
  }
  function dropText() { $("#prDropT").innerHTML = tab === "print" ? "Drop clip images here or click. Files named by NAB give exact col x inch; others are estimated from your inch calibration." : tab === "online" ? "Drop website screenshots here or click. Width x height in pixels is read from each image." : "Drop TV recordings here or click. The length in seconds is read from each video."; $("#prFile").accept = tab === "tv" ? "video/*,audio/*" : "image/*"; }
  function mount(e) {
    el = e; el.innerHTML = HTML;
    const dz = $("#prDrop"); dz.onclick = () => $("#prFile").click(); $("#prFile").onchange = (ev) => { upload(ev.target.files); ev.target.value = ""; };
    ["dragenter", "dragover"].forEach(n => dz.addEventListener(n, (ev) => { ev.preventDefault(); dz.classList.add("on"); })); ["dragleave", "drop"].forEach(n => dz.addEventListener(n, (ev) => { ev.preventDefault(); dz.classList.remove("on"); }));
    dz.addEventListener("drop", (ev) => upload(ev.dataTransfer.files)); dropText();
    $("#prAI").onclick = async () => { const r = await api("pr_report", {}); if (!r.ok) return toast(r.error || "AI unavailable", "warn", 4000); C.modal(`<h3>Summary</h3><textarea id="rpT" rows="7" style="width:100%">${esc(r.text)}</textarea><div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" id="rpC">Copy</button><button class="btn pri" id="rpX">Close</button></div>`, (close) => { $("#rpX").onclick = close; $("#rpC").onclick = () => { $("#rpT").select(); document.execCommand("copy"); toast("Copied", "ok", 1200); }; }); };
    $("#prTabs").onclick = (ev) => { const b = ev.target.closest("button"); if (!b) return; tab = b.dataset.t; $$("#prTabs button").forEach(x => x.classList.toggle("on", x === b)); imp(); dropText(); grid(); };
    $("#prAdd").onclick = () => { D[tab].push(tab === "print" ? { media: "", page_type: "Inner Page", colour: true, colinch: 0, ad: 0 } : tab === "online" ? { media: "", date: S.date, w: 0, h: 0, rate: 0 } : { media: "", date: S.date, secs: 0, rate: 0 }); grid(); const t = $$("#prGrid tr[data-i]"); t.length && t[t.length - 1].querySelector("input").focus(); save(); };
    $("#prClr").onclick = () => { if (!D[tab].length || !confirm("Clear all " + tab + " rows?")) return; D[tab] = []; totals(); grid(); save(); };
    $("#prMult").onchange = (ev) => { const v = n(ev.target.value); if (v > 0) { mult = v; totals(); grid(); save(); } };
    $("#prExp").onclick = async () => { await api("pr_save", { print: D.print, online: D.online, tv: D.tv, multiplier: mult }); const r = await api("pr_export", {}); if (!r.ok) return toast(r.error, "error", 5000); toast("Saved: " + r.path, "ok", 6000, { label: "Open folder", fn: () => api("pr_reveal", { path: r.path }) }); };
    $("#prRates").onclick = ratesDlg;
  }
  function ratesDlg() {
    C.modal(`<h3>Add or change a rate</h3><div class="field"><label>Table</label><select id="rK"><option value="print">Print (per column inch)</option><option value="online">Online (per pixel)</option><option value="tv">TV (per second)</option></select></div>
      <div class="field"><label>Media name</label><input id="rN" style="width:100%"></div><div class="field" id="rPt"><label>Page type / ink</label><select id="rP">${S.page_types.map(p => `<option>${esc(p)}</option>`).join("")}</select> <select id="rC"><option value="1">Colour</option><option value="0">B/W</option></select></div>
      <div class="field"><label>Rate</label><input id="rR" type="number" step="any" style="width:140px"></div><div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" id="rReset" title="Back to the shipped rate sheet">Reset all</button><button class="btn" id="rNo">Cancel</button><button class="btn pri" id="rOk">Save</button></div>`, (close) => {
      const k = $("#rK"); k.onchange = () => { $("#rPt").style.display = k.value === "print" ? "" : "none"; }; $("#rNo").onclick = close;
      $("#rReset").onclick = async () => { if (!confirm("Restore the shipped rate sheet? Your changes to rates are lost.")) return; await api("pr_rates_reset"); close(); toast("Rates restored", "ok", 2000); await show(true); };
      $("#rOk").onclick = async () => { const r = await api("pr_rate_set", { kind: k.value, name: $("#rN").value, page_type: $("#rP").value, colour: $("#rC").value === "1", rate: $("#rR").value }); if (!r.ok) return toast(r.error, "error", 3000); close(); toast("Rate saved", "ok", 1800); await show(true); };
    });
  }
  async function show(keep) {
    S = await api("pr_state"); D = S.data; mult = S.multiplier; $("#prMult").value = mult;
    $("#dlP").innerHTML = S.pubs.map(x => `<option value="${esc(x)}">`).join(""); $("#dlO").innerHTML = S.sites.map(x => `<option value="${esc(x)}">`).join(""); $("#dlT").innerHTML = S.tvs.map(x => `<option value="${esc(x)}">`).join("");
    totals(); imp(); grid();
  }
  window.TOOLS.pr = { mount, show };
})();
