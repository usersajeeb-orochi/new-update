// settings.js — the Settings view. window.SETTINGS = { init, render, go }
(function () {
  const { $, $$, esc, api, toast, on } = C;
  const S = { sec: "general", box: null, cur: null };
  const SECS = [["general", "general"], ["papers", "papers"], ["detect", "detection"], ["quick", "quicksave"], ["keys", "hotkeys"], ["rules", "mapping"], ["cats", "categories_edit"], ["pdefs", "pdefs"], ["comfort", "comfort"], ["riko", "riko"], ["connections", "connections"], ["ai", "ai_sec"], ["sync", "sync"], ["accounts", "Accounts"], ["whatsapp", "WhatsApp"], ["selfcheck", "Self-check"], ["backups", "backups"], ["about", "about"]];
  const KEYS = [["paste", "Paste"], ["undo", "Undo"], ["redo", "Redo"], ["delete", "Delete layer"], ["generate", "Save"], ["trim", "Trim"], ["clean", "Clean"], ["pad", "Pad"], ["open", "Open file"], ["move_up", "Layer up"], ["move_down", "Layer down"], ["swap", "Swap last two"], ["tool_crop", "Crop tool"], ["tool_erase", "Erase tool"], ["tool_highlight", "Highlight tool"], ["tool_redact", "Redact tool"], ["discard", "Delete grabbed clip"]];
  const QKEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Ctrl+6", "Ctrl+7", "Ctrl+8", "Ctrl+9"];

  function st() { return (window.MAIN && MAIN.st) || {}; }
  function init() { S.box = $("#view-settings"); }
  async function render() {
    if (!S.box) init();
    S.cur = await api("state"); if (window.MAIN) MAIN.st = S.cur;
    S.box.innerHTML = '<nav class="s-nav">' + SECS.map(([id, k]) => `<button data-s="${id}" class="${S.sec === id ? "on" : ""}">${esc(t(k))}</button>`).join("") + '</nav><div class="s-body" id="sBody"></div>';
    $$(".s-nav button", S.box).forEach(b => b.onclick = () => go(b.dataset.s));
    await body();
  }
  function go(sec) { S.sec = sec; S.enter = true; if (S.box && !$("#view-settings").classList.contains("hidden")) render(); else render(); }
  async function body() {
    const b = $("#sBody"); const f = S["r_" + S.sec] || r_general; b.innerHTML = ""; await f(b); applyI18n(b);
    if (S.enter) { S.enter = false; b.classList.remove("enter"); $$(".card", b).forEach((c, i) => c.style.setProperty("--i", Math.min(i, 8))); void b.offsetWidth; b.classList.add("enter"); }
  }
  const hd = (b, title, sub) => { b.insertAdjacentHTML("beforeend", `<h2>${esc(title)}</h2>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}`); };
  function card(b, title, html) { const d = document.createElement("div"); d.className = "card"; d.innerHTML = (title ? `<h4>${esc(title)}</h4>` : "") + html; b.appendChild(d); return d; }
  const chk = (id, label, v) => `<label class="row"><input type="checkbox" id="${id}" ${v ? "checked" : ""}> ${esc(label)}</label>`;
  const num = (id, label, v, min, max) => `<div class="kv"><span>${esc(label)}</span><input id="${id}" type="number" value="${v}" min="${min}" max="${max}"><span></span></div>`;
  async function opt(o) { const r = await api("set_options", o); if (r && r.ok === false) toast(r.error || "Failed", "bad"); }
  function bindOpt(d, map) {
    Object.keys(map).forEach(id => { const el = $("#" + id, d); if (!el) return; el.onchange = () => opt({ [map[id]]: el.type === "checkbox" ? el.checked : (el.type === "number" ? Number(el.value) : el.value) }); });
  }

  // ───── General ─────
  async function r_general(b) {
    const s = S.cur.settings, ui = S.cur.ui || {};
    hd(b, t("general"));
    let d = card(b, t("language"), `<div class="btn-grid"><button class="btn ${LANG === "en" ? "pri" : ""}" data-l="en">English</button><button class="btn ${LANG === "bn" ? "pri" : ""}" data-l="bn">বাংলা</button></div>`);
    $$("[data-l]", d).forEach(x => x.onclick = async () => { LANG = x.dataset.l; await api("ui_set", { lang: LANG }); applyI18n(); render(); });
    d = card(b, t("theme"), `<div class="btn-grid">${[["dark", t("dark")], ["light", t("light")], ["blue", "Blue"], ["snow", "Snow"], ["shadow", "Shadow Cat"], ["neon", "Neon Cat"]].map(([k, n]) => `<button class="btn ${(ui.theme || "dark") === k ? "pri" : ""}" data-th="${k}">${esc(n)}</button>`).join("")}</div>`);
    $$("[data-th]", d).forEach(x => x.onclick = async () => { C.theme(x.dataset.th); await api("ui_set", { theme: x.dataset.th }); render(); });
    d = card(b, "Saving", `<div class="kv"><span>Save folder</span><input id="o_root" value="${esc(s.base_root)}"><button class="btn" id="o_reveal">Open</button></div>
      ${num("o_min", "Min file size (KB)", s.min_kb, 1, 5000)}${num("o_max", "Max file size (KB)", s.max_kb, 50, 50000)}
      ${chk("o_fit", "Smart size — find the best quality under the limit automatically", s.smart_fit !== false)}${num("o_ft", "Target size (KB)", s.fit_target_kb, 100, 5000)}${num("o_fb", "Target for very big clips, source over 4 MB (KB)", s.fit_big_kb, 200, 5000)}
      ${chk("o_hd", "HD mode (max JPEG quality, ignores smart size)", s.hd_mode)}${num("o_q", "Manual JPEG quality (used when Smart size is off)", s.quality, 40, 100)}`);
    bindOpt(d, { o_root: "base_root", o_min: "min_kb", o_max: "max_kb", o_fit: "smart_fit", o_ft: "fit_target_kb", o_fb: "fit_big_kb", o_hd: "hd_mode", o_q: "quality" });
    $("#o_reveal", d).onclick = () => api("reveal", { path: s.base_root });
    d = card(b, "Clipping", `${chk("o_snatch", t("auto_snatch"), s.auto_snatch)}${chk("o_polish", t("auto_polish"), s.auto_polish)}${chk("o_suggest", "Suggest a crop for single-item clips", s.auto_crop_suggest)}${chk("o_sapply", "Apply the suggested crop automatically (with some margin)", s.auto_crop_apply)}${chk("o_hdr", t("show_header"), s.show_header)}`);
    bindOpt(d, { o_snatch: "auto_snatch", o_polish: "auto_polish", o_suggest: "auto_crop_suggest", o_sapply: "auto_crop_apply", o_hdr: "show_header" });
    d = card(b, "Upload & reports", `${chk("o_upen", "Upload clips to Google (master switch)", s.upload_enabled)}${chk("o_up", "Upload to Drive automatically after saving", s.auto_upload)}${chk("o_as", "Autosave draft clips", s.autosave_enabled)}${num("o_asi", "Autosave every (sec)", s.autosave_interval, 30, 3600)}
      ${chk("o_dr", "Send daily report to Telegram", s.daily_report_enabled)}${num("o_drh", "Report hour (0–23)", s.daily_report_hour, 0, 23)}${num("o_goal", "Daily goal (clips)", s.daily_goal, 0, 9999)}
      <div class="row"><button class="btn" id="o_upnow">${esc(t("upload_now"))}</button><button class="btn" id="o_dt">Test Drive</button><span id="o_msg" class="tag"></span></div>`);
    bindOpt(d, { o_upen: "upload_enabled", o_up: "auto_upload", o_as: "autosave_enabled", o_asi: "autosave_interval", o_dr: "daily_report_enabled", o_drh: "daily_report_hour", o_goal: "daily_goal" });
    $("#o_upnow", d).onclick = async () => { await api("upload_now"); toast("Upload started"); };
    d.querySelector("#o_upnow").insertAdjacentHTML("afterend", ' <button class="btn" id="o_upold">Upload older days…</button>');
    $("#o_upold", d).onclick = async () => { const r = await api("upload_days"); const days = r.days || [];
      C.modal("<h3>Upload older days</h3><p class='sub'>Files already on Drive are skipped.</p><label class='row'><input type='checkbox' id='uAll'> All days</label><div style='max-height:260px;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:4px'>" + days.map(x => "<label class='row'><input type='checkbox' class='uD' value='" + x + "'> " + x + "</label>").join("") + "</div><div class='modal-actions'><button class='btn' id='uNo'>Cancel</button><button class='btn pri' id='uGo'>Upload</button></div>", (c, close) => {
        $("#uNo").onclick = close; $("#uGo").onclick = async () => { const sel = $("#uAll").checked ? ["all"] : Array.from(c.querySelectorAll(".uD:checked")).map(x => x.value); const x = await api("upload_dates", { dates: sel }); close(); toast(x.ok ? "Upload started" : x.error, x.ok ? "ok" : "error", 3000); }; }); };
    $("#o_dt", d).onclick = async () => { const r = await api("drive_test"); $("#o_msg", d).textContent = r.ok ? "✓ Drive OK" : "✗ " + (r.error || "failed"); };
    d = card(b, "Tools", `<div class="btn-grid">${[["batch", "Batch clipper (classic window)"], ["classic", "Classic NAB window"]].map(([k, n]) => `<button class="btn" data-tool="${k}">${n}</button>`).join("")}</div>`);
    $$("[data-tool]", d).forEach(x => x.onclick = () => api("launch_tool", { name: x.dataset.tool }));
  }
  S.r_general = r_general;

  // ───── Papers (+ logos) ─────
  const cleanName = (p) => (p || "").replace(/^[^\p{L}\p{N}]+/u, "").trim();
  S.r_papers = async function (b) {
    hd(b, t("papers"), "Name, order and logo of every newspaper. Everything saves the moment you change it, and NAB keeps backup copies of the list. The logo is printed at the top of every saved clip.");
    const lg = await api("logos"); let bust = Date.now();
    const d = card(b, "", `<p class="sub">Logos found: <b id="ppFound">${lg.found}/${lg.total}</b>. To add a logo: choose a PNG with <b>Logo…</b>, or press <b>Win+Shift+S</b>, drag around the logo, then click <b>Paste shot</b>. NAB looks for <code>Paper Name.png</code> in: ${(lg.dirs || []).map(esc).join(" · ")}</p><div id="ppRows"></div><div class="row"><button class="btn pri" id="ppAdd">+ Add newspaper</button><span class="sub" style="margin:0">Type the name and press Enter. The paper appears everywhere straight away.</span></div>`);
    const rows = $("#ppRows", d);
    const names = () => Array.from(rows.children).map(r => r.dataset.orig).filter(Boolean);
    const addRow = (name) => {
      const r = document.createElement("div"); r.className = "kv"; r.style.gridTemplateColumns = "84px 1fr auto auto auto auto auto"; r.dataset.orig = name || "";
      r.innerHTML = `<span class="lg" style="height:34px;display:flex;align-items:center;justify-content:center;background:#fff;border-radius:8px;border:1px solid var(--line);overflow:hidden"><img class="lgi" style="max-width:80px;max-height:30px;visibility:hidden"></span>
        <input class="pn" value="${esc(cleanName(name || ""))}" placeholder="Paper name"><button class="btn up" style="height:30px;padding:0 10px" title="Choose a logo file (PNG)">Logo…</button><button class="btn cap" style="height:30px;padding:0 10px" title="Take a screenshot (Win+Shift+S), then click this">Paste shot</button>
        <button class="btn mv" style="height:30px;padding:0 8px" title="Move up">Up</button><button class="btn mv2" style="height:30px;padding:0 8px" title="Move down">Down</button><button class="btn rm" style="height:30px;padding:0 10px" title="Remove this paper">Remove</button>
        <input type="file" accept="image/*" hidden>`;
      const img = r.querySelector(".lgi"), pn = r.querySelector(".pn"), fi = r.querySelector("input[type=file]");
      const showLogo = () => { const o = r.dataset.orig; if (!o) { img.style.visibility = "hidden"; return; } img.onload = () => { img.style.visibility = "visible"; }; img.onerror = () => { img.style.visibility = "hidden"; }; img.src = C.url("/logo?n=" + encodeURIComponent(o) + "&r=" + bust); };
      // commit: a new row is added to the list, an existing one is renamed - immediately, no Save button to forget
      const commit = async () => {
        const v = pn.value.trim(), o = r.dataset.orig; if (!v) return false;
        if (!o) { const x = await api("paper_add", { name: v }); if (!x.ok) { toast(x.error || "Could not add", "warn", 2600); return false; } r.dataset.orig = v; toast("Added " + cleanName(v), "ok", 1600); showLogo(); return true; }
        if (cleanName(o) !== v) { const x = await api("paper_rename", { old: o, new: v }); if (!x.ok) { toast(x.error || "Could not rename", "warn", 2600); pn.value = cleanName(o); return false; } r.dataset.orig = v; toast("Renamed", "ok", 1400); showLogo(); }
        return true;
      };
      pn.onchange = commit; pn.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); pn.blur(); } };
      const needName = async () => { if (!pn.value.trim()) { toast("Type the paper name first", "warn", 1800); pn.focus(); return false; } return await commit(); };
      r.querySelector(".up").onclick = async () => { if (await needName()) fi.click(); };
      fi.onchange = async () => { const f = fi.files[0]; fi.value = ""; if (!f) return; const dataUrl = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(f); }); const x = await api("logo_upload", { paper: r.dataset.orig, data: dataUrl }); if (x.ok) { bust = Date.now(); showLogo(); toast("Logo saved for " + cleanName(r.dataset.orig), "ok", 1800); } else toast(x.error || "Could not use that image", "warn", 2600); };
      r.querySelector(".cap").onclick = async () => { if (!(await needName())) return; const x = await api("logo_from_clipboard", { paper: r.dataset.orig }); if (x.ok) { bust = Date.now(); showLogo(); toast("Logo saved for " + cleanName(r.dataset.orig), "ok", 1800); } else toast(x.error || "No picture on the clipboard. Press Win+Shift+S first.", "warn", 3000); };
      const saveOrder = async () => { const l = names(); if (l.length) await api("set_papers", { papers: l }); };
      r.querySelector(".mv").onclick = async () => { if (r.previousElementSibling) { rows.insertBefore(r, r.previousElementSibling); await saveOrder(); } };
      r.querySelector(".mv2").onclick = async () => { if (r.nextElementSibling) { rows.insertBefore(r.nextElementSibling, r); await saveOrder(); } };
      const rm = r.querySelector(".rm"); let armed = 0;
      rm.onclick = async () => {
        if (!r.dataset.orig) { r.remove(); return; }
        if (!armed) { armed = 1; rm.textContent = "Sure?"; setTimeout(() => { armed = 0; rm.textContent = "Remove"; }, 2500); return; }
        const x = await api("paper_remove", { name: r.dataset.orig }); if (x.ok) { r.remove(); toast("Removed", "ok", 1400); } else toast(x.error || "Could not remove", "warn", 2400);
      };
      rows.appendChild(r); showLogo();
    };
    (S.cur.papers || []).forEach(addRow);
    $("#ppAdd", d).onclick = () => { addRow(""); const n = rows.lastChild.querySelector(".pn"); n.focus(); n.scrollIntoView({ block: "center" }); };
  };

  // ───── Detection log ─────
  let detTimer = null;
  S.r_detect = async function (b) {
    hd(b, t("detection"), "What NAB sees while you work in the browser: window title, address, and which paper it picked. Use this to check or to send me a screenshot.");
    const d = card(b, "", `<div class="row"><span class="tag" id="dtS">…</span><span class="tag" id="dtE">…</span><span class="tag" id="dtT">…</span><span class="tag" id="dtM">…</span></div><p class="sub" id="dtL"></p><table class="t"><thead><tr><td>Time</td><td>Window title</td><td>Address</td><td>Copy</td><td>Result</td></tr></thead><tbody id="dtB"></tbody></table>`);
    const pull = async () => {
      if (!$("#dtB")) { clearInterval(detTimer); return; }
      const r = await api("detect_log");
      $("#dtS").textContent = r.win32 ? "Windows access OK" : "No Windows access (detection off)"; $("#dtE").textContent = r.tab_ext ? "Tab extension: sending URLs ✓" : "Tab extension: no URL received yet";
      const ts = r.tab_server || {}; $("#dtT").textContent = "Listener: " + (ts.status || "?") + (ts.clients ? " · " + ts.clients + " browser connected" : " · no browser connected");
      const mo = r.mon; $("#dtM").textContent = mo ? ("Monitor alive · clipboard #" + mo.seq + (mo.img ? " (image)" : "") + " · window: " + (mo.title || "NAB/none")) : "Monitor: not running yet";
      $("#dtL").textContent = "Log file: " + (r.log_file || "");
      $("#dtB").innerHTML = (r.rows || []).slice().reverse().map(x => `<tr><td>${esc(x.t)}</td><td>${esc(x.title)}</td><td>${esc(x.url)}</td><td>${x.clip ? (x.img ? "🖼 image" : "copy") : ""}</td><td>${x.paper ? "✅ " + esc(x.paper) + " <i>(" + esc(x.how) + ")</i>" : "—"}</td></tr>`).join("");
    };
    d.insertAdjacentHTML("afterbegin", '<div class="row"><button class="btn pri" id="dtTest">Detection test</button><button class="btn" id="dtGuide">Setup guide</button></div>');
    $("#dtTest", d).onclick = () => EXTRAS.detectTest(); $("#dtGuide", d).onclick = () => EXTRAS.guide();
    clearInterval(detTimer); await pull(); detTimer = setInterval(pull, 1500);
  };

  // ───── Quick-save keys ─────
  function allPaths() { const o = []; const c = S.cur.categories || {}; Object.keys(c).forEach(r => { o.push(r); (c[r] || []).forEach(s => o.push(r + "/" + s)); }); return o; }
  S.r_quick = async function (b) {
    hd(b, t("quicksave"), "Press the key in the Clip screen to arm that category. Then type the metadata line and press Enter.");
    const paths = allPaths(), qs = S.cur.quick_saves || {};
    const d = card(b, "", QKEYS.map(k => `<div class="kv"><span>${k}</span><select data-k="${k}" style="height:34px;border-radius:9px;border:1px solid var(--line);background:var(--surf2);color:var(--txt)"><option value="">—</option>${paths.map(p => `<option ${qs[k] === p ? "selected" : ""}>${esc(p)}</option>`).join("")}</select><span></span></div>`).join("") + '<div class="row"><button class="btn pri" id="qS">Save</button></div>');
    $("#qS", d).onclick = async () => { const m = {}; $$("select", d).forEach(s => { if (s.value) m[s.dataset.k] = s.value; }); await api("set_quick_saves", { map: m }); toast("Quick-save keys saved ✓"); };
  };

  // ───── Shortcuts ─────
  function tkFromEvent(e) {
    const k = e.key; if (["Control", "Shift", "Alt", "Meta"].includes(k)) return null;
    const map = { ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", Enter: "Return", " ": "space" };
    let n = map[k] || (k.length === 1 ? k.toLowerCase() : k); let p = [];
    if (e.ctrlKey || e.metaKey) p.push("Control"); if (e.altKey) p.push("Alt"); if (e.shiftKey) p.push("Shift"); p.push(n);
    return p.length === 1 && n.length === 1 ? n : "<" + p.join("-") + ">";
  }
  S.r_keys = async function (b) {
    hd(b, t("hotkeys"), "Click a box, then press the new key combination.");
    const hk = S.cur.hotkeys || {};
    const d = card(b, "", KEYS.map(([k, n]) => `<div class="kv"><span>${esc(n)}</span><input readonly data-h="${k}" value="${esc(hk[k] || "")}"><span></span></div>`).join("") + '<div class="row"><button class="btn pri" id="hS">Save</button></div>');
    $$("input[data-h]", d).forEach(i => i.onkeydown = (e) => { e.preventDefault(); e.stopPropagation(); const v = tkFromEvent(e); if (!v) return; i.value = v; });
    $("#hS", d).onclick = async () => { const m = {}; $$("input[data-h]", d).forEach(i => m[i.dataset.h] = i.value); await api("set_hotkeys", { map: m }); await window.MAIN.reload(); toast("Shortcuts saved ✓"); };
  };

  // ───── Tab → paper rules ─────
  S.r_rules = async function (b) {
    hd(b, t("mapping"), "When the browser tab's address or title contains the text on the left, NAB switches to that paper.");
    const m = (await api("get_mappings")).map || {}; const papers = S.cur.papers || [];
    const rows = Object.keys(m).map(k => [k, m[k]]);
    const d = card(b, "", `<table class="t"><tbody id="rb"></tbody></table><div class="row"><button class="btn" id="rA">+ Add rule</button><button class="btn pri" id="rS">Save</button></div>
      <div class="field"><label>Test: paste a tab address or title</label><input id="rT" placeholder="https://www.thedailystar.net/…"></div><div id="rE" class="tag" style="white-space:pre-wrap"></div>`);
    const add = (k, v) => { const tr = document.createElement("tr"); tr.innerHTML = `<td><input class="k" value="${esc(k)}"></td><td><select class="v" style="height:30px;border-radius:8px;border:1px solid var(--line);background:var(--surf2);color:var(--txt)">${papers.map(p => `<option value="${esc(p)}" ${p === v ? "selected" : ""}>${esc(C.clean(p))}</option>`).join("")}</select></td><td><button class="btn" style="height:28px;padding:0 10px">✕</button></td>`; tr.querySelector("button").onclick = () => tr.remove(); $("#rb", d).appendChild(tr); };
    rows.forEach(([k, v]) => add(k, v));
    $("#rA", d).onclick = () => add("", papers[0] || "");
    $("#rS", d).onclick = async () => { const o = {}; $$("#rb tr", d).forEach(tr => { const k = tr.querySelector(".k").value.trim(), v = tr.querySelector(".v").value; if (k) o[k] = v; }); await api("set_mappings", { map: o }); toast("Rules saved ✓"); };
    $("#rT", d).oninput = C.debounce(async () => { const r = await api("explain", { text: $("#rT", d).value }); $("#rE", d).textContent = r.text || ""; }, 250);
  };

  // ───── Categories ─────
  S.r_cats = async function (b) {
    hd(b, t("categories_edit"), "One row per category. Sub-categories are comma-separated.");
    const c = S.cur.categories || {};
    const d = card(b, "", `<table class="t"><tbody id="cb"></tbody></table><div class="row"><button class="btn" id="cA">+ Add category</button><button class="btn pri" id="cS">Save</button></div>`);
    const add = (k, v) => { const tr = document.createElement("tr"); tr.innerHTML = `<td style="width:34%"><input class="k" value="${esc(k)}"></td><td><input class="v" value="${esc((v || []).join(", "))}"></td><td><button class="btn" style="height:28px;padding:0 10px">✕</button></td>`; tr.querySelector("button").onclick = () => tr.remove(); $("#cb", d).appendChild(tr); };
    Object.keys(c).forEach(k => add(k, c[k]));
    $("#cA", d).onclick = () => add("", []);
    $("#cS", d).onclick = async () => {
      const o = {}; $$("#cb tr", d).forEach(tr => { const k = tr.querySelector(".k").value.trim(); if (k) o[k] = tr.querySelector(".v").value.split(",").map(x => x.trim()).filter(Boolean); });
      await api("set_categories", { cats: o }); toast("Categories saved ✓");
    };
  };

  // ───── Connections (Advanced) ─────
  S.r_connections = async function (b) {
    hd(b, t("connections"), "Everything is built in. You normally never need this page.");
    const r = await api("connections_get"); const sm = r.summary || {};
    card(b, "In use", Object.keys(sm).map(k => `<div class="kv"><span>${esc(k)}</span><span class="tag">${esc(sm[k])}</span><span></span></div>`).join(""));
    const F = [["drive_folder_id", "Drive folder ID"], ["sheet_id", "Tracker sheet ID"], ["cloud_url", "Cloud URL"], ["google_key_path", "Google key file path"], ["telegram_token", "Telegram token"]];
    const d = card(b, t("advanced"), F.map(([k, n]) => `<div class="kv"><span>${n}</span><input data-c="${k}" value="${esc(r.overrides[k] || "")}" placeholder="${esc((r.builtin && r.builtin[k]) || "built-in")}" ${k === "telegram_token" ? 'type="password"' : ""}><span></span></div>`).join("") + `<div class="row"><button class="btn pri" id="cnS">Save</button><button class="btn bad" id="cnR">${esc(t("reset_builtin"))}</button></div><p class="sub">Leave a box empty to use the built-in value.</p>`);
    const done = (x) => toast(x.restart ? "Saved — restart NAB to apply" : "Saved ✓");
    $("#cnS", d).onclick = async () => { const v = {}; $$("input[data-c]", d).forEach(i => v[i.dataset.c] = i.value.trim()); done(await api("connections_set", { values: v })); };
    $("#cnR", d).onclick = async () => { done(await api("connections_set", { reset: true })); render(); };
  };

  // ───── WhatsApp ─────
  S.r_whatsapp = async function (b) {
    hd(b, "WhatsApp", "Send saved clips to a chat or group through WhatsApp Web. Link once by scanning the QR code; NAB keeps you linked.");
    const r = await api("wa_state"), c = r.cfg || {};
    const lab = { idle: "Not started", starting: "Starting", login: "Waiting for QR scan", ready: "Linked", error: "Problem" };
    const d = card(b, "", `<div class="row"><span class="tag" id="waT">${esc(r.linked ? "Linked" : (lab[r.status] || r.status))}</span><span id="waM">${esc(r.msg || "")}</span></div>
      <div class="row"><button class="btn pri" id="waL">Link WhatsApp</button><button class="btn" id="waU">Unlink</button><button class="btn" id="waS">Chats and options…</button></div>
      <p class="sub">Chats: ${esc((c.chats || []).join(", ") || "none yet")}. Pictures are sent as files (full quality) ${c.as_document === false ? "- currently OFF, WhatsApp will compress them" : "- ON"}.</p>`);
    $("#waL", d).onclick = async () => { const x = await api("wa_login"); toast(x.ok ? "A browser window opens: scan the QR code" : x.error, x.ok ? "ok" : "bad"); };
    $("#waU", d).onclick = async () => { await api("wa_logout"); toast("Unlinked"); setTimeout(render, 800); };
    $("#waS", d).onclick = () => window.WA && WA.setup();
    const ago = (t) => { if (!t) return "never"; const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "just now" : m < 90 ? m + " min ago" : Math.round(m / 60) + " h ago"; };
    const num = (id, lbl, v, lo, hi, hint) => `<div class="kv"><span>${lbl}</span><input id="${id}" type="number" min="${lo}" max="${hi}" value="${v}" style="width:90px"><small class="sub">${hint}</small></div>`;
    const o = card(b, "Sending options", `${chk("wa_doc", "Send as file (full quality, no WhatsApp compression)", c.as_document !== false)}${chk("wa_cap", "Use the file name as caption", !!c.caption)}${chk("wa_auto", "Send every saved clip automatically (categories with a chat, or the default)", !!c.auto)}${chk("wa_show", "Show the browser window while sending", !!c.show_window)}${chk("wa_nf", "Tell me when a send fails", c.notify_fail !== false)}
      ${num("wa_gap", "Pause between sends (seconds)", c.gap_s ?? 3, 0, 60, "Longer is gentler on WhatsApp")}${num("wa_dup", "Ignore a repeat of the same file for (minutes)", c.dup_minutes ?? 10, 0, 240, "Stops double clicks sending twice. 0 = off")}${num("wa_to", "Wait for the send button (seconds)", c.send_timeout_s ?? 45, 15, 180, "Raise on a slow connection")}${num("wa_idle", "Close the hidden browser after idle (minutes)", c.idle_close_min ?? 30, 2, 240, "Saves memory")}
      <div class="row"><button class="btn pri" id="waSv">Save sending options</button></div>`);
    $("#waSv", o).onclick = async () => { await api("wa_settings", { as_document: $("#wa_doc", o).checked, caption: $("#wa_cap", o).checked, auto: $("#wa_auto", o).checked, show_window: $("#wa_show", o).checked, notify_fail: $("#wa_nf", o).checked, gap_s: $("#wa_gap", o).value, dup_minutes: $("#wa_dup", o).value, send_timeout_s: $("#wa_to", o).value, idle_close_min: $("#wa_idle", o).value }); toast("Saved"); };
    const qd = card(b, "Send queue", `<p class="sub" id="waH"></p><div id="waQ"></div><div class="row"><button class="btn" id="waCl">Clear finished</button></div>`);
    const stl = { queued: "Waiting", sending: "Sending", sent: "Sent", failed: "Failed" };
    const drawQ = async () => {
      const q = await api("wa_queue"); if (!$("#waQ", qd)) return;
      $("#waH", qd).textContent = (q.linked ? "Linked" : "Not linked") + ". Last successful send: " + ago(q.last_ok) + (q.last_error ? ". Last problem: " + q.last_error : "") + ".";
      $("#waQ", qd).innerHTML = (q.jobs || []).length ? '<table class="t"><tbody>' + q.jobs.slice().reverse().map(j => `<tr><td>${esc(j.name)}${j.n > 1 ? " +" + (j.n - 1) : ""}</td><td>${esc(j.chat)}</td><td>${esc(stl[j.state] || j.state)}${j.error ? ": " + esc(j.error) : ""}</td><td>${j.state === "failed" || j.state === "sent" ? `<button class="btn mini" data-r="${j.id}">${j.state === "failed" ? "Retry" : "Resend"}</button>` : ""}</td></tr>`).join("") + "</tbody></table>" : '<p class="sub">Nothing sent yet.</p>';
      $("#waQ", qd).querySelectorAll("button[data-r]").forEach(bt => bt.onclick = async () => { bt.disabled = true; const x = await api("wa_retry", { id: +bt.dataset.r }); toast(x.note || x.error || "Queued", x.ok ? "ok" : "bad"); setTimeout(drawQ, 600); });
    };
    $("#waCl", qd).onclick = async () => { await api("wa_clear_queue"); drawQ(); };
    drawQ();
    const off = on("tool", (ev) => { if (ev.tool !== "wa") return; if (ev.ev === "status" && $("#waT")) { $("#waT").textContent = lab[ev.status] || ev.status; $("#waM").textContent = ev.msg || ""; } if ($("#waQ")) drawQ(); });
  };

  // ───── Self-check ─────
  S.r_selfcheck = async function (b) {
    hd(b, "Self-check", "One look at everything NAB depends on. Red means something needs fixing now, amber means worth a look.");
    const d = card(b, "", `<div class="row"><button class="btn pri" id="scGo">Run the check</button><span class="tag" id="scT"></span></div><div id="scB"></div>`);
    const dot = { ok: "#22c55e", warn: "#f59e0b", bad: "#ef4444" }, word = { ok: "OK", warn: "Check", bad: "Problem" };
    const run = async () => {
      $("#scGo", d).disabled = true; $("#scT", d).textContent = "Checking…";
      const r = await api("selfcheck");
      $("#scGo", d).disabled = false; $("#scT", d).textContent = (r.overall === "ok" ? "All good" : r.overall === "warn" ? "Some things to look at" : "Needs attention") + " · " + r.at;
      $("#scB", d).innerHTML = '<table class="t"><tbody>' + (r.rows || []).map(x => `<tr><td style="width:14px"><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${dot[x.status]}"></i></td><td><b>${esc(x.label)}</b></td><td>${esc(word[x.status])}</td><td>${esc(x.detail)}${x.fix ? `<br><small class="sub">${esc(x.fix)}</small>` : ""}</td></tr>`).join("") + "</tbody></table>";
    };
    $("#scGo", d).onclick = run; run();
  };

  // ───── Accounts ─────
  S.r_accounts = async function (b) {
    hd(b, "Accounts", "Named logins with roles. Owner: everything. Staff: clip, save and send. Viewer: look only. Accounts are made on the owner PC and every other PC downloads them. Telegram approval still works as a way in.");
    const stt = await api("acct_status"), r = await api("acct_list"), cur = stt.current || {};
    const info = card(b, "", `<div class="row"><span class="tag">${cur.name ? "Signed in as " + esc(cur.display || cur.name) + " (" + esc(cur.role) + ")" : "Not signed in with an account"}</span>${cur.name ? '<button class="btn" id="acOut">Sign out</button>' : ""}</div>
      ${stt.owner_pc ? "" : '<p class="sub">This PC only downloads accounts. To add or change accounts, use the owner PC (Settings, Sync).</p>'}`);
    if ($("#acOut", info)) $("#acOut", info).onclick = async () => { await api("acct_logout"); toast("Signed out. Restart NAB to sign in as someone else."); setTimeout(render, 500); };
    const lst = card(b, "People", `<table class="t"><thead><tr><td>Name</td><td>Role</td><td>Last sign-in</td><td></td></tr></thead><tbody>${(r.users || []).map(u => `<tr data-n="${esc(u.name)}"><td><b>${esc(u.display)}</b>${u.disabled ? " (off)" : ""}${u.must_change ? " (must change password)" : ""}</td>
      <td><select data-a="role" ${stt.owner_pc ? "" : "disabled"}>${["owner", "staff", "viewer"].map(x => `<option ${u.role === x ? "selected" : ""}>${x}</option>`).join("")}</select></td><td>${esc(u.last_login || "never")}</td>
      <td>${stt.owner_pc ? `<button class="btn mini" data-a="reset">Reset password</button> <button class="btn mini" data-a="off">${u.disabled ? "Turn on" : "Turn off"}</button> <button class="btn mini" data-a="del">Delete</button>` : ""}</td></tr>`).join("") || '<tr><td colspan="4">No accounts yet. The first one you add becomes the owner.</td></tr>'}</tbody></table>`);
    const msg = (x, ok) => { toast(x.ok ? (ok || "Done") : x.error, x.ok ? "ok" : "bad", x.ok ? 2500 : 6000); if (x.ok) setTimeout(render, 600); };
    lst.querySelectorAll("tr[data-n]").forEach(tr => { const n = tr.dataset.n;
      const sel = tr.querySelector("select[data-a=role]"); if (sel) sel.onchange = async () => msg(await api("acct_role", { name: n, role: sel.value }), "Role changed");
      tr.querySelectorAll("button[data-a]").forEach(bt => bt.onclick = async () => {
        if (bt.dataset.a === "reset") { C.modal(`<h3>Reset password for ${esc(n)}</h3><p class="sub">Type a temporary password (at least 6 characters). They must change it at their next sign-in.</p><div class="field"><input id="rsP" type="text" maxlength="80"></div><div class="modal-actions"><button class="btn" id="rsNo">Cancel</button><button class="btn pri" id="rsYes">Reset</button></div>`, (cd, close) => { $("#rsNo").onclick = close; $("#rsYes").onclick = async () => { const pw = $("#rsP").value; close(); msg(await api("acct_reset", { name: n, password: pw }), "Password reset"); }; }); }
        else if (bt.dataset.a === "off") { const u = (r.users || []).find(x => x.name === n); msg(await api("acct_disable", { name: n, disabled: !(u && u.disabled) })); }
        else if (bt.dataset.a === "del") { C.modal(`<h3>Delete the account ${esc(n)}?</h3><p class="sub">They will no longer be able to sign in.</p><div class="modal-actions"><button class="btn" id="dlNo">Cancel</button><button class="btn pri" id="dlYes">Delete</button></div>`, (cd, close) => { $("#dlNo").onclick = close; $("#dlYes").onclick = async () => { close(); msg(await api("acct_delete", { name: n }), "Deleted"); }; }); }
      }); });
    if (stt.owner_pc) {
      const add = card(b, "Add a person", `<div class="kv"><span>Name</span><input id="anN" maxlength="32" placeholder="for example sajeeb"></div><div class="kv"><span>Password</span><input id="anP" type="password" maxlength="80" placeholder="at least 6 characters"></div>
        <div class="kv"><span>Role</span><select id="anR"><option>staff</option><option>viewer</option><option>owner</option></select></div><div class="row"><button class="btn pri" id="anGo">Add account</button></div>`);
      $("#anGo", add).onclick = async () => { const x = await api("acct_add", { name: $("#anN", add).value, password: $("#anP", add).value, role: $("#anR", add).value }); msg(x, "Account added"); };
    }
    if (cur.name) {
      const pw = card(b, "My password", `<div class="kv"><span>Current</span><input id="pwO" type="password"></div><div class="kv"><span>New</span><input id="pwN" type="password"></div><div class="row"><button class="btn" id="pwGo">Change my password</button></div>`);
      $("#pwGo", pw).onclick = async () => msg(await api("acct_change_pw", { old: $("#pwO", pw).value, new: $("#pwN", pw).value }), "Password changed");
    }
    const au = card(b, "Activity log", `<div class="row"><button class="btn" id="auGo">Show the latest 100 entries</button></div><div id="auB"></div>`);
    $("#auGo", au).onclick = async () => { const x = await api("audit_tail", { n: 100 }); $("#auB", au).innerHTML = '<table class="t"><tbody>' + (x.rows || []).map(e => `<tr><td>${esc(e.t)}</td><td>${esc(e.user)}</td><td>${esc(e.action)}</td><td>${esc(e.detail)}</td></tr>`).join("") + "</tbody></table>"; };
  };

  // ───── Sync ─────
  S.r_sync = async function (b) {
    hd(b, t("sync"), "One PC (the owner) uploads the settings. Every other PC downloads them automatically, so a new install is ready with no setup.");
    const s = S.cur.sync || {};
    const d = card(b, "", `<div class="row"><span class="tag">${s.started ? (s.no_drive ? "No Drive" : s.offline ? "Offline" : "OK") : "Not started"}</span><span>${esc(s.time || "")}</span></div>
      ${s.pulled && s.pulled.length ? `<div class="row">⬇ ${esc(s.pulled.join(", "))}</div>` : ""}${s.pushed && s.pushed.length ? `<div class="row">⬆ ${esc(s.pushed.join(", "))}</div>` : ""}${s.conflicts && s.conflicts.length ? `<div class="row">⚠ ${esc(s.conflicts.join(", "))}</div>` : ""}
      ${s.awaiting && s.awaiting.length ? `<div class="row">⏳ Waiting for your Telegram approval to upload: ${esc(s.awaiting.join(", "))}</div>` : ""}
      <div class="row"><span class="tag">${s.role && s.role.role === "owner" ? "Owner: this PC uploads" : "Follower: this PC only downloads"}</span>${s.role_pending ? "<span>Waiting for your Telegram approval…</span>" : ""}</div>
      <div class="row"><button class="btn" id="syO">${s.role && s.role.role === "owner" ? "Make this PC a follower" : "Make this PC the owner"}</button></div>
      <div class="kv"><span>Settings ID (optional)</span><input id="syI" value="${esc((s.role && s.role.id) || "")}" placeholder="empty = shared main settings"><button class="btn" id="syIs">Use ID</button></div>
      <p class="sub">With an ID, this PC downloads (or, on the owner PC, publishes) the settings set stored under that ID only, so each person can have their own.</p>
      <p class="sub">Shared through one file, <code>${esc(s.file || "nab_settings_sync.json")}</code>, in the built-in Google Drive folder (uploaded by NAB's service account). Downloading shared settings is always free.</p>
      ${chk("sy_ap", "Uploading my settings changes needs approval on Telegram", s.approval !== false)}${chk("sy_up", "Upload clips to Google (master switch)", st().settings.upload_enabled)}
      <div class="row"><button class="btn pri" id="sN">Sync now</button><button class="btn" id="sH">History</button></div><div id="sHB"></div>`);
    bindOpt(d, { sy_ap: "sync_approval", sy_up: "upload_enabled" });
    $("#syO", d).onclick = async () => { const own = s.role && s.role.role === "owner"; const x = await api("sync_role", { role: own ? "follower" : "owner" }); toast(x.pending ? "Approve on Telegram to make this PC the owner" : "Saved"); setTimeout(render, 600); };
    $("#syIs", d).onclick = async () => { await api("sync_role", { id: $("#syI", d).value.trim() }); await api("sync_now"); toast("ID saved - downloading its settings"); setTimeout(render, 1500); };
    $("#sN", d).onclick = async () => { await api("sync_now"); toast("Syncing…"); setTimeout(render, 2500); };
    $("#sH", d).onclick = async () => { const r = await api("sync_history"); const h = (r.history || r || []); $("#sHB", d).innerHTML = '<table class="t"><tbody>' + (Array.isArray(h) ? h : []).map(e => `<tr><td>${esc(e.at || "")}</td><td>${esc(e.ns || e.namespace || "")}</td><td>${esc(e.by || e.pc || "")}</td></tr>`).join("") + "</tbody></table>"; };
  };

  // ───── Paper defaults ─────
  S.r_pdefs = async function (b) {
    hd(b, t("pdefs"), "Per-newspaper settings. Leave a box empty to use the global setting.");
    const r = await api("paper_defaults"), D = r.defaults || {};
    const d = card(b, "", `<table class="t"><thead><tr><td>Paper</td><td>Auto-trim</td><td>Clean lines</td><td>Save width</td><td>Max KB</td><td>px / inch</td><td>Page pattern (regex)</td></tr></thead><tbody>${(r.papers || []).map(p => { const o = D[p] || {}; return `<tr data-p="${esc(p)}"><td><b>${esc(p)}</b></td>
      <td><select data-k="autotrim"><option value="">default</option><option value="1" ${o.autotrim === true ? "selected" : ""}>on</option><option value="0" ${o.autotrim === false ? "selected" : ""}>off</option></select></td>
      <td><input type="checkbox" data-k="clean" ${o.clean ? "checked" : ""}></td>
      <td><select data-k="out_width">${[0, 1600, 1200, 1000, 800].map(w => `<option value="${w}" ${(o.out_width || 0) === w ? "selected" : ""}>${w ? w + " px" : "original"}</option>`).join("")}</select></td>
      <td><input data-k="target_kb" type="number" min="0" max="5000" value="${o.target_kb || ""}" style="width:70px" placeholder="auto"></td>
      <td><input data-k="ppi" type="number" min="0" step="0.1" value="${o.ppi || ""}" style="width:74px" placeholder="—" title="Set with Calibrate inches in the Clip screen"></td>
      <td><input data-k="page_regex" value="${esc(o.page_regex || "")}" placeholder="e.g. /page/(\\d+)" style="width:160px"></td></tr>`; }).join("")}</tbody></table><p class="sub">Page pattern: only needed if a paper's address doesn't show the page in a common form (page=3, /page-3/, "Page 3"). The first group (…) is the page.</p>`);
    $$("tr[data-p]", d).forEach(tr => $$("[data-k]", tr).forEach(el => el.onchange = async () => {
      const k = el.dataset.k; let v = el.type === "checkbox" ? el.checked : el.value;
      if (k === "autotrim") v = v === "" ? null : v === "1"; if (["out_width", "target_kb", "ppi"].includes(k)) v = Number(v || 0);
      const x = await api("paper_defaults_set", { paper: tr.dataset.p, [k]: v }); if (x.ok) toast("Saved ✓", "ok", 900); else toast(x.error || "Failed", "warn", 2500);
    }));
    card(b, "Smart trim", chk("pd_trim", "Trim empty margins as soon as a clip is pasted (all papers, unless set above)", r.smart_trim)); bindOpt(b, { pd_trim: "smart_trim" });
  };

  // ───── Comfort & speed ─────

  // ───── Riko (mascot) ─────
  S.r_riko = async function (b) {
    const u = S.cur.ui || {}, P = (window.RIKO && RIKO.plus) || null, tot = P ? P.total() : 0;
    hd(b, "Sajeeb", "Your on-screen character. Everything here is saved on this PC only.");
    const set = (k, v) => { api("ui_set", { [k]: v }); S.cur.ui = Object.assign({}, S.cur.ui, { [k]: v }); if (window.RIKO) RIKO.apply(); };
    const tog = (id, label, v) => `<label class="row"><input type="checkbox" data-k="${id}" ${v ? "checked" : ""}> ${esc(label)}</label>`;
    const sel = (id, label, opts, v) => `<div class="kv"><span>${esc(label)}</span><select data-k="${id}">${opts.map(([val, t_, dis]) => `<option value="${val}" ${String(v) === String(val) ? "selected" : ""} ${dis ? "disabled" : ""}>${esc(t_)}</option>`).join("")}</select><span></span></div>`;
    const th = P ? P.thresholds : {}, nm = P ? P.names : {}, un = u.mascot_unlock === true;
    const who = u.mascot_who === "riko" ? "riko" : "sajeeb", th_ = P ? P.thresholds : {}, nm_ = P ? P.names : {}, un_ = u.mascot_unlock === true;
    const skinOpts = [["auto", "Auto (she changes by herself)"]].concat(["blue", "snow", "shadow", "neon"].map(i => [i, (nm_[i] || i) + (un_ && tot < (th_[i] || 0) ? "  (unlocks at " + th_[i] + " saves)" : ""), un_ && tot < (th_[i] || 0)]));
    let d = card(b, "Show " + ((u.mascot_char || "").trim() || "Sajeeb"), tog("mascot", "Show the character in NAB (off on slow PCs)", u.mascot === true) + sel("mascot_who", "Character", [["sajeeb", "Sajeeb (you)"], ["riko", "Riko (the fox)"]], who) + (who === "riko" ? sel("mascot_skin", "Riko outfit", skinOpts, u.mascot_skin || "auto") + tog("mascot_unlock", "Unlock outfits by saving clips (Snow 50, Neon 150, Shadow 300)", un_) : "") + `<div class="kv"><span>Name shown under him</span><input data-k="mascot_char" maxlength="20" placeholder="${who === "riko" ? "Riko" : "Sajeeb"}" value="${esc(u.mascot_char || "")}"><span></span></div>` + tog("mascot_tag", "Always show the name tag", u.mascot_tag !== false) + `<div class="kv"><span>Size</span><input type="range" data-k="mascot_size" min="90" max="320" step="10" value="${u.mascot_size || 150}"><span></span></div><div class="row"><button class="btn" id="rkFolder">Open character folder</button></div><p class="sub" id="rkFolderP"></p><p class="sub">Replace the pictures in that folder (same file names). Walk, run, dance, celebrate and sleep can have 2 or 3 frames: walk_1/2/3, run_1/2/3, dance_1/2, celebrate_1/2, sleep_1/2. Details are in READ ME FIRST.txt there. Restart NAB after changing pictures.</p><p class="sub">Total clips saved: ${tot}</p>`);
    d = card(b, "Care", tog("mascot_trkwatch", "Tell me which papers are not clipped yet (afternoons)", u.mascot_trkwatch !== false) + tog("mascot_presave", "Check page, size and category before saving", u.mascot_presave !== false) + tog("mascot_wrap", "End-of-day wrap-up when I close NAB", u.mascot_wrap !== false) + tog("mascot_resume", "Remind me where I was after a long break", u.mascot_resume !== false) + tog("mascot_trainer", "Suggest the shortcut key when I use the mouse", u.mascot_trainer !== false) + tog("mascot_screen", "React to the category I pick", u.mascot_screen !== false) + tog("mascot_surprise", "Rare surprises", u.mascot_surprise !== false) + `<div class="kv"><span>Own lines per category (Category=line, one per row)</span><textarea data-k="mascot_cat_lines" rows="3">${esc(u.mascot_cat_lines || "")}</textarea><span></span></div>`);
    d = card(b, "Helpers", tog("mascot_carry", "He carries the pasted clip and delivers it to Save", u.mascot_carry !== false) + tog("mascot_badge", "Show today's counter under him", u.mascot_badge !== false) + `<div class="kv"><span>Daily goal (clips, 0 = off)</span><input type="number" data-k="mascot_goal" min="0" max="999" value="${u.mascot_goal || 0}"><span></span></div>` + tog("mascot_remind", "Remind me when the category or page number is missing", u.mascot_remind !== false) + `<div class="kv"><span>Tracker reminder time (HH:MM, empty = off)</span><input data-k="mascot_deadline" placeholder="18:30" value="${esc(u.mascot_deadline || "")}"><span></span></div>` + `<div class="kv"><span>Break reminder every (minutes, 0 = off)</span><input type="number" data-k="mascot_break" min="0" max="240" value="${u.mascot_break == null ? 50 : u.mascot_break}"><span></span></div>` + tog("mascot_tips", "Show a shortcut tip now and then", u.mascot_tips !== false) + tog("mascot_fun", "Memes, quotes and fun activities (phone, tea, umbrella…)", u.mascot_fun !== false));
    d = card(b, "Personality", sel("mascot_chat", "How talkative", [[0, "Quiet (only important things)"], [1, "Normal"], [2, "Chatty"]], u.mascot_chat == null ? 1 : u.mascot_chat) + sel("mascot_lang", "Language of his lines", [["en", "English"], ["bn", "Bangla"], ["mix", "Mixed"]], u.mascot_lang || "en") + tog("mascot_quiet", "Go quiet automatically when I'm clipping fast", u.mascot_quiet !== false) + tog("mascot_sound", "Sounds (small beeps)", u.mascot_sound === true) + `<div class="kv"><span>Sound volume</span><input type="range" data-k="mascot_vol" min="0" max="100" value="${u.mascot_vol == null ? 30 : u.mascot_vol}"><span></span></div>` + `<div class="kv"><span>Your name (for greetings)</span><input data-k="mascot_name" value="${esc(u.mascot_name || "")}"><span></span></div>`);
    d = card(b, "Your own lines and special days", `<p class="sub">One line per row. He uses these when he greets you, finishes a save or chats.</p><textarea data-k="mascot_lines" rows="4" style="width:100%">${esc(u.mascot_lines || "")}</textarea><p class="sub">Special days: one per row, like <b>04-14 Happy Boishakh!</b> (month-day, then the message). Add Eid and other dates here.</p><textarea data-k="mascot_days" rows="3" style="width:100%">${esc(u.mascot_days || "")}</textarea>`);
    d = card(b, "Play", `<div class="row"><button class="btn" id="rkP1">Catch me</button><button class="btn" id="rkP2">Clip rain</button><button class="btn" id="rkP3">Give a snack</button></div>`);
    api("mascot_folder", {}).then(r => { const e = $("#rkFolderP", b); if (e && r.path) e.textContent = r.path; }); { const bt = $("#rkFolder", b); if (bt) bt.onclick = () => api("mascot_folder", { open: true }); }
    $("#rkP1", d).onclick = () => P && P.playCatch(); $("#rkP2", d).onclick = () => P && P.playRain(); $("#rkP3", d).onclick = () => P && P.snack();
    $$("[data-k]", b).forEach(el => el.onchange = () => { const k = el.dataset.k; let v = el.type === "checkbox" ? el.checked : (el.type === "number" || el.type === "range") ? Number(el.value) : el.value; if (k === "mascot_chat") v = Number(v); set(k, v); if (k === "mascot" && window.RIKO) RIKO.setEnabled(v && !document.body.classList.contains("slow")); if (k === "mascot_size" && window.RIKO) RIKO.setSize(v); if (k === "mascot_skin" && window.RIKO) RIKO.setMode(v); if (k === "mascot_who") { b.innerHTML = ""; S.r_riko(b); } if ((k === "mascot_char" || k === "mascot_tag") && window.RIKO) RIKO.apply(); });
  };

  S.r_comfort = async function (b) {
    const s = S.cur.settings; hd(b, t("comfort"));
    let d = card(b, "Speed", `<div class="kv"><span>Slow-PC mode</span><select id="cf_slow"><option value="auto" ${s.slow_mode === "auto" ? "selected" : ""}>Auto (detect)</option><option value="on" ${s.slow_mode === "on" ? "selected" : ""}>Always on</option><option value="off" ${s.slow_mode === "off" ? "selected" : ""}>Off</option></select><span class="tag">${S.cur.slow ? "active" : "not active"}</span></div><p class="sub">Slow-PC mode turns off animations and uses lighter previews. Works on Windows 10 and 11.</p>`);
    bindOpt(d, { cf_slow: "slow_mode" }); $("#cf_slow", d).addEventListener("change", () => setTimeout(() => MAIN.reload(), 300));
    d = card(b, "Mini window", `<div class="kv"><span>Opacity (%)</span><input id="cf_op" type="range" min="30" max="100" step="5" value="${s.ov_opacity}"><span class="tag" id="cf_opv">${s.ov_opacity}</span></div>${chk("cf_snap", "Snap to screen edges when released near them", s.ov_snap)}`);
    d.insertAdjacentHTML("beforeend", `<div class="kv"><span>Show it when NAB is minimized</span><input type="checkbox" id="cf_auto" ${((S.cur.ui || {}).overlay_auto === false) ? "" : "checked"}></div><div class="row"><span>Size</span><button class="btn" data-ovs="240,330">Small</button><button class="btn" data-ovs="300,440">Medium</button><button class="btn" data-ovs="380,560">Large</button></div>`);
    $("#cf_auto", d).onchange = (e) => api("ui_set", { overlay_auto: e.target.checked });
    $$("[data-ovs]", d).forEach(bt => bt.onclick = () => { const [w, h] = bt.dataset.ovs.split(",").map(Number); api("window", { action: "overlay_resize", w, h, final: true }); });
    bindOpt(d, { cf_op: "ov_opacity", cf_snap: "ov_snap" }); $("#cf_op", d).oninput = () => { $("#cf_opv", d).textContent = $("#cf_op", d).value; };
    const uiS = S.cur.ui || {};
    d = card(b, "Sign-in", `<div class="kv"><span>Approval way at start-up</span><select id="au_d"><option value="ask">Ask me each time</option><option value="group">Authorize by group</option><option value="owner">Authorize by owner</option></select><span></span></div><div class="kv"><span>Quick re-login window (minutes, 0 = off)</span><input id="au_g" type="number" min="0" max="120" value="${uiS.auth_grace == null ? 10 : uiS.auth_grace}"><span></span></div><div class="kv"><span>"Remember today" lasts until (HH:MM)</span><input id="au_u" value="${esc(uiS.auth_remember_until || "23:59")}"><span></span></div><div class="kv"><span>Owner "Remember for days" lasts (days)</span><input id="au_n" type="number" min="2" max="60" value="${uiS.auth_remember_days == null ? 7 : uiS.auth_remember_days}"><span></span></div><p class="sub">Quick re-login: if NAB closes by accident it reopens without asking again inside the window. "Remember today" is on both the group and the owner request. "Remember for days" is owner-only.</p>`);
    $("#au_d", d).value = uiS.auth_default || "ask"; $("#au_d", d).onchange = (e) => api("ui_set", { auth_default: e.target.value });
    $("#au_g", d).onchange = (e) => api("ui_set", { auth_grace: Math.max(0, Math.min(120, +e.target.value || 0)) });
    $("#au_n", d).onchange = (e) => { const v = Math.max(2, Math.min(60, parseInt(e.target.value, 10) || 7)); e.target.value = v; api("ui_set", { auth_remember_days: v }); };
    $("#au_u", d).onchange = (e) => { const v = e.target.value.trim(); if (/^\d{1,2}:\d{2}$/.test(v)) api("ui_set", { auth_remember_until: v }); else toast("Use HH:MM, for example 23:59", "warn", 2200); };
    d = card(b, "Start-up", `${chk("su_intro", "Play the start-up animation", localStorage.getItem("nab_intro") !== "0")}${chk("su_snd", "Start-up animation sound", localStorage.getItem("nab_intro_sound") !== "0")}${chk("su_full", "Open NAB maximised (F11 toggles full screen any time)", uiS.start_full !== false)}`);
    $("#su_intro", d).onchange = (e) => { try { localStorage.setItem("nab_intro", e.target.checked ? "1" : "0"); } catch (x) {} api("ui_set", { intro: e.target.checked }); };
    $("#su_snd", d).onchange = (e) => { try { localStorage.setItem("nab_intro_sound", e.target.checked ? "1" : "0"); } catch (x) {} api("ui_set", { intro_sound: e.target.checked }); };
    $("#su_full", d).onchange = (e) => api("ui_set", { start_full: e.target.checked });
    d = card(b, "Missed-save guard", `${chk("cf_mg", "Remind me when a clip stays unsaved while I'm in another window", s.missed_guard)}${num("cf_mgs", "Remind after (seconds)", s.missed_guard_s, 10, 600)}`);
    bindOpt(d, { cf_mg: "missed_guard", cf_mgs: "missed_guard_s" });
  };

  // ───── Backups ─────
  S.r_backups = async function (b) {
    hd(b, t("backups"), "NAB keeps a copy of your settings (paper list, categories, rules, shortcuts) — once a day, and after every update. Restore one if something ever gets lost.");
    const r = await api("backups");
    const d = card(b, "", `<div class="row"><button class="btn pri" id="bkNow">Back up now</button><span class="tag">${esc(r.dir || "")}</span></div><table class="t"><tbody>${(r.backups || []).map(x => `<tr><td>${esc(x.name)}</td><td>${x.kb} KB</td><td><button class="btn" data-n="${esc(x.name)}">Restore</button></td></tr>`).join("") || "<tr><td>No backups yet.</td></tr>"}</tbody></table>`);
    $("#bkNow", d).onclick = async () => { const x = await api("backup_now"); toast(x.ok ? "Backup saved ✓" : (x.error || "Failed"), x.ok ? "ok" : "warn", 1800); render(); };
    $$("[data-n]", d).forEach(bt => bt.onclick = () => C.modal("<h3>Restore this backup?</h3><p>Your current settings are backed up first, then replaced by <b>" + esc(bt.dataset.n) + "</b>.</p><div class='modal-actions'><button class='btn' id='mNo'>Cancel</button><button class='btn pri' id='mYes'>Restore</button></div>", (c, close) => { $("#mNo").onclick = close; $("#mYes").onclick = async () => { close(); const x = await api("backup_restore", { name: bt.dataset.n }); toast(x.ok ? "Restored ✓" : (x.error || "Failed"), x.ok ? "ok" : "error", 2500); MAIN.reload(); }; }));
  };

  // ───── About ─────
  S.r_ai = async function (b) {
    hd(b, "AI", "Groq powers Riko's chat, the PR calculator's media detection and the research helpers. Every feature still works without it.");
    const st = await api("ai_status");
    const d = card(b, "Connection", `${chk("ai_on", "Use AI features", st.enabled)}${chk("ai_bi", "Also use the built-in keys", st.use_builtin)}
      <div class="field"><label>Your own Groq keys (one per line; the next one is used when one hits its limit)</label><textarea id="ai_keys" rows="4" style="width:100%" placeholder="gsk_..."></textarea></div>
      <div class="kv"><span>Keys available</span><b id="ai_n">${st.keys}</b><span></span></div>
      <div class="kv"><span>Resting (rate-limited)</span><b>${st.resting}</b><span></span></div>
      <div class="row" style="gap:8px"><button class="btn" id="ai_test">Test connection</button><button class="btn pri" id="ai_save">Save</button><span id="ai_msg" class="sub"></span></div>`);
    const cfg = await api("ai_settings", {}); // no change, just echoes status
    d.querySelector("#ai_save").onclick = async () => { const r = await api("ai_settings", { enabled: $("#ai_on").checked, use_builtin: $("#ai_bi").checked, keys: $("#ai_keys").value }); $("#ai_n").textContent = r.keys; toast("Saved", "ok", 1500); };
    d.querySelector("#ai_test").onclick = async () => { $("#ai_msg").textContent = "Testing..."; const r = await api("ai_test"); $("#ai_msg").textContent = r.ok ? "Connected" : (r.error || "Failed"); };
    card(b, "Models", `<div class="kv"><span>Chat model</span><input id="ai_tm" value="${esc(st.text_model)}"><span></span></div><div class="kv"><span>Fast model</span><input id="ai_fm" value="${esc(st.fast_model)}"><span></span></div>
      <div class="kv"><span>Vision model (empty = auto)</span><input id="ai_vm" value="${esc(st.vision_model)}"><span></span></div><p class="sub">Change only if Groq retires a model. Riko remembers what you tell her; see her right-click menu > What have you learned.</p>`)
      .querySelectorAll("input").forEach(i => i.onchange = () => api("ai_settings", { text_model: $("#ai_tm").value, fast_model: $("#ai_fm").value, vision_model: $("#ai_vm").value }));
  };
  S.r_about = async function (b) {
    hd(b, "News Automation Pro", "Developed by Sajeeb · user.sajeeb@gmail.com");
    const u = S.cur.update || {};
    const d = card(b, "", `<div class="kv"><span>Version</span><span class="tag">v${esc(S.cur.version)}</span><span></span></div><div class="kv"><span>This PC</span><span>${esc(S.cur.pc)}</span><span></span></div>
      <div class="kv"><span>Saved today</span><span>${S.cur.saved_today}</span><span></span></div><div class="kv"><span>Pending uploads</span><span>${S.cur.pending_uploads}</span><span></span></div>
      ${u.ready ? `<div class="row"><button class="btn pri" id="aU">${esc(t("restart_update"))}</button></div>` : ""}`);
    if ($("#aU", d)) $("#aU", d).onclick = () => api("apply_update");
    d.insertAdjacentHTML("beforeend", '<div class="row"><button class="btn" id="aG">Run setup guide</button><button class="btn pri" id="aX">Set up the extension</button></div>'); $("#aG", d).onclick = () => EXTRAS.guide(); $("#aX", d).onclick = () => EXTRAS.extSetup();
    const im = (f, cap) => `<figure><img src="/s/manual/${f}.png" alt="${esc(cap)}" loading="lazy"><figcaption>${esc(cap)}</figcaption></figure>`;
    card(b, "User manual", `<div class="man">
      <h4>1. The daily flow</h4>
      <ol><li>Open the e-paper in your browser. NAB picks the newspaper from the tab address (needs the browser extension, see section 6) — or press <kbd>Ctrl</kbd>+<kbd>K</kbd> and type the paper name.</li>
      <li>Select the news and copy it (Win+Shift+S or the e-paper's own copy). NAB takes the clip automatically, or press <kbd>Ctrl</kbd>+<kbd>V</kbd>.</li>
      <li>Press a number key <kbd>1</kbd>–<kbd>9</kbd> (or <kbd>Ctrl</kbd>+<kbd>1</kbd>–<kbd>9</kbd>) to choose the category.</li>
      <li>Type the <b>Page</b> (e.g. B4), then the <b>Position</b> digits (1 then 3 → 1-3) and the <b>Size</b> (8 then 16 → 8x16). No symbols needed — the cursor jumps by itself. <kbd>Enter</kbd> saves.</li></ol>
      ${im("clip", "Clip window: category on the left, tools on top, metadata + Save at the bottom")}
      <h4>1b. Setup guide</h4><p>If something is missing (logos, browser extension, save folder…) NAB walks you through it. Open it any time from Settings → About.</p>
      ${im("guide", "Setup guide")}
      <h4>2. Command bar</h4><p>Press <kbd>Ctrl</kbd>+<kbd>K</kbd> for everything: switch paper, open Tracker/PDF/Search, settings, undo save, upload older days…</p>
      ${im("cmdk", "Command bar (Ctrl+K)")}
      <h4>3. Editing tools</h4>
      <table class="t"><tbody>
      <tr><td><kbd>M</kbd> / <kbd>L</kbd> / <kbd>W</kbd></td><td>Rectangle / free-hand / magic-wand selection</td></tr>
      <tr><td><kbd>C</kbd> · <kbd>E</kbd> · <kbd>H</kbd> · <kbd>R</kbd></td><td>Crop · erase to white · highlight · redact black (on the selection)</td></tr>
      <tr><td><kbd>B</kbd></td><td>Eraser brush ( <kbd>[</kbd> <kbd>]</kbd> = size )</td></tr>
      <tr><td><kbd>S</kbd> (⎘)</td><td><b>Clone stamp</b> — the "surgical" tool: <kbd>Alt</kbd>+click the clean spot to copy from, then paint over what you want to hide</td></tr>
      <tr><td><kbd>V</kbd></td><td>Move / resize layers or the selection</td></tr>
      <tr><td><kbd>T</kbd></td><td>Text</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>T</kbd> / <kbd>E</kbd> / <kbd>L</kbd></td><td>Trim margins · pad · clean</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Y</kbd></td><td>Undo / redo (for 10 seconds after a save, Ctrl+Z also un-saves)</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>I</kbd> (◐)</td><td>Invert the selection</td></tr>
      <tr><td>Straighten</td><td>Finds the tilt of a scanned clip and levels it (Image panel)</td></tr>
      <tr><td>Remember area / Clean-up (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>K</kbd>)</td><td>Select a fixed ad strip once → "Remember area"; next time one key erases it for that paper</td></tr></tbody></table>
      <h4>3b. Faster metadata</h4>
      <table class="t"><tbody>
      <tr><td><kbd>Alt</kbd>+<kbd>1</kbd>–<kbd>9</kbd></td><td>Add more categories to the same save (hold Alt and tap the quick keys) — one Enter saves into all of them</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>Enter</kbd> · ↺</td><td>Fill Page / Position / Size from the previous save (and save, if a category is picked)</td></tr>
      <tr><td>Page box (dashed)</td><td>Filled from the ePaper tab when the address shows the page. Type to change it</td></tr>
      <tr><td>Size box</td><td>Second number may have decimals: 4 then 3.5 → 4x3.5</td></tr>
      <tr><td>Calibrate inches</td><td>Select a part of known width (one column) → enter its inches. After that NAB shows the clip's size in inches and → fills the Size box</td></tr>
      <tr><td><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>C</kbd> / <kbd>F</kbd></td><td>Copy the last saved clip to the clipboard / open its folder</td></tr></tbody></table>
      <h4>3c. Size and quality</h4><p><b>Smart size</b> finds, for every clip, the highest JPEG quality that still fits under your limit (default 500 KB; clips whose original is over 4 MB aim for ~780 KB so they stay sharp). If quality alone cannot reach the limit, the picture is reduced slightly. The status bar shows what was used (e.g. <code>312 KB · q86</code>). Per-paper options are in Settings → Paper defaults.</p>
      <h4>4. Papers and logos</h4><p>Settings → Papers. For a logo: press <b>Win+Shift+S</b>, drag around the logo, then click <b>Paste shot</b> on that paper (margins are trimmed automatically). <b>Logo…</b> picks a PNG file instead. Names are shown without emoji.</p>
      ${im("papers", "Paper menu with logos")}
      <h4>5. Mini window (overlay)</h4><p>When NAB is minimized, a small window stays on top so you can keep saving while you browse. Drag it by the top strip, resize it from the bottom-right corner (or press ⇲ for Small / Medium / Large), press ✕ to hide it (Shift+click turns it off), <b>double-click</b> it (or press ⤢) to come back to the full app. <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>N</kbd> switches between the browser and NAB from anywhere.</p>
      ${im("overlay", "Mini window")}
      <h4>6. Browser extension (picks the newspaper and page for you)</h4>
      <p>The extension tells NAB which e-paper tab you are on. Browsers do not allow a program to install an extension silently, so NAB does everything except the last three clicks. Open it any time with <b>Settings → About → Set up the extension</b> (or <kbd>Ctrl</kbd>+<kbd>K</kbd> → “extension”). It also appears once on the first run.</p>
      <ol>
        <li>Click <b>Set up now</b>. NAB opens Chrome (or Edge) on its extensions page and <b>copies the folder path</b> for you.</li>
        <li>Turn on <b>Developer mode</b> (switch at the top right).</li>
        <li>Click <b>Load unpacked</b>, click the address bar of the folder window, press <kbd>Ctrl</kbd>+<kbd>V</kbd>, <kbd>Enter</kbd>, then <b>Select Folder</b>. (The button <b>Open folder</b> in NAB shows the same folder in Explorer.)</li>
        <li>Leave NAB open — the 4th step in NAB turns green by itself, and the dot at the bottom right becomes green.</li>
      </ol>
      ${im("ext1", "Steps 1–2: Developer mode")}${im("ext2", "Step 3: Load unpacked")}${im("ext3", "Step 4: pick the folder — the extension appears")}
      <ul><li><b>Chrome shows “Disable developer mode extensions” at start-up:</b> click the ✕ or “Keep”; do not disable it. This message is normal for extensions loaded this way.</li><li><b>Dot stays red/grey:</b> keep NAB running, reload the e-paper tab, and check the extension is switched on in <code>chrome://extensions</code>. If you moved or deleted the folder, run the setup again.</li><li><b>Using both Chrome and Edge:</b> do the steps once in each browser (choose it in the list).</li><li>The extension only sends the tab address to NAB on this PC (127.0.0.1). Nothing goes online.</li></ul>
      <h4>7. Tracker, PDF, Search</h4><p>Tracker marks which papers arrived today and fills the sheet; PDF makes a PDF from the day's clips; Search finds clips by text (OCR).</p>
      ${im("tracker", "Tracker")}
      <h4>8. If something is wrong</h4><ul><li>No logo: Settings → Papers shows how many were found and where NAB looks.</li><li>Paper not detected: Settings → Detection shows the window title and address NAB received.</li><li>Setup guide: Settings → About → Run setup guide, or click the coloured dot at the bottom right (green = browser extension connected).</li><li>Unsaved clips survive a crash — NAB offers to restore them at the next start. Settings are backed up daily (Settings → Backups).</li><li>The log file <code>Documents\nab_log.txt</code> is temporary (reset at every start, max 200 KB).</li></ul>
      <p class="credit">Developed by <b>Sajeeb</b> — <a href="mailto:user.sajeeb@gmail.com">user.sajeeb@gmail.com</a></p>
    </div>`);
  };

  window.SETTINGS = { init, render, go };
  window.SETTINGS_GO = go;
})();
