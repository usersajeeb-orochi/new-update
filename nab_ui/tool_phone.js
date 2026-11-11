// tool_phone.js - the colleague's phone clips, listed on the right of the Clip screen.
// Order: Telecom industry, GP, BL, Robi, Teletalk, Edotco first (each its own group), then everything else bundled by paper.
(function () {
  const { $, $$, esc, api, toast } = C;
  const PRIORITY = [
    ["Telecom industry", (p, s) => /telecom\/industry|telecom industry/.test(p) || (s === "industry" && /telecom/.test(p))],
    ["GP", (p, s) => s === "gp" || /grameenphone/.test(p)],
    ["BL", (p, s) => s === "bl" || /banglalink/.test(p)],
    ["Robi", (p, s) => s === "robi"],
    ["Teletalk", (p, s) => s === "tt" || /teletalk/.test(p)],
    ["Edotco", (p, s) => /edotco/.test(p)],
  ];
  let items = [], timer = 0, box, using = null, dragId = null;
  const ORD = "nab_phone_order";
  const getOrd = () => { try { return JSON.parse(localStorage.getItem(ORD) || "[]"); } catch (e) { return []; } };
  const setOrd = (a) => { try { localStorage.setItem(ORD, JSON.stringify(a.slice(-400))); } catch (e) { } };
  function sortItems() {
    const o = getOrd(), ix = new Map(o.map((id, i) => [id, i]));
    items.sort((a, b) => {
      const ia = ix.has(a.id), ib = ix.has(b.id);
      if (ia && ib) return ix.get(a.id) - ix.get(b.id);
      if (ia !== ib) return ia ? -1 : 1;
      return String(a.date || "").localeCompare(String(b.date || "")) || String(a.created || "").localeCompare(String(b.created || ""));
    });
  }
  function moveBefore(id, beforeId) {
    const ids = items.map(x => x.id).filter(i => i !== id), at = ids.indexOf(beforeId);
    ids.splice(at < 0 ? ids.length : at, 0, id); setOrd(ids);
    sortItems(); paint("");
  }
  const low = x => String(x || "").toLowerCase();
  // -> [["Telecom industry", [items]], ..., ["Daily Star", [items]]]
  function group(list) {
    const pri = PRIORITY.map(([n]) => [n, []]), rest = {};
    for (const x of list) {
      let hit = -1;
      for (let i = 0; i < PRIORITY.length && hit < 0; i++) if ((x.cats || []).some(c => { const p = low(c), s = low(String(c).split("/").pop()); return PRIORITY[i][1](p, s); })) hit = i;
      if (hit >= 0) pri[hit][1].push(x); else (rest[x.paper || "No paper"] = rest[x.paper || "No paper"] || []).push(x);
    }
    return [...pri.filter(g => g[1].length), ...Object.keys(rest).sort((a, b) => a.localeCompare(b)).map(k => [k, rest[k], 1])];
  }
  const url = (p) => p + (p.includes("?") ? "&" : "?") + "t=" + encodeURIComponent((window.NAB && window.NAB.token) || "");
  function beep() { try { const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain(); o.frequency.value = 880; g.gain.value = .06; o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + .12); } catch (e) {} }
  let known = null;
  const nabDate = () => { const i = document.getElementById("dateInput"); return i ? i.value : ""; };
  const dayName = (iso) => { const d = new Date(iso + "T00:00:00"); return isNaN(d) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short" }); };
  async function setNabDate(iso) { const i = document.getElementById("dateInput"); if (!i || !iso || i.value === iso) return; i.value = iso; i.dispatchEvent(new Event("change")); await new Promise(r => setTimeout(r, 250)); }
  const ask = (html, yes) => new Promise(res => C.modal(html + `<div class="modal-actions"><button class="btn" id="qNo">Cancel</button><button class="btn pri" id="qYes">${yes}</button></div>`, (cd, close) => { $("#qNo").onclick = () => { close(); res(false); }; $("#qYes").onclick = () => { close(); res(true); }; }));
  // a paper or category typed on the phone that NAB does not have yet: add it (after a yes), then carry on
  async function addNew(x) {
    const st = (window.CLIPX && CLIPX.S.st) || {}, papers = st.papers || [], cats = JSON.parse(JSON.stringify(st.categories || {})), newc = (x.new_cats || []).filter(p => { const [g, s] = String(p).split("/"); return !(cats[g] || []).includes(s); });
    const needP = x.new_paper && !papers.some(p => C.clean(p).toLowerCase() === String(x.paper).toLowerCase() || p === x.paper);
    if (!needP && !newc.length) return true;
    const lines = (needP ? [`Paper: <b>${esc(x.paper)}</b>`] : []).concat(newc.map(p => `Category: <b>${esc(String(p).replace("/", " › "))}</b>`));
    if (!(await ask(`<h3>New from the phone</h3><p class="sub">${esc(x.user)} added something NAB does not have yet:</p><p>${lines.join("<br>")}</p><p class="sub">Add it to NAB so you can clip it?</p>`, "Add and use"))) return false;
    if (needP) { const r = await api("paper_add", { name: x.paper }); if (!r.ok) { toast(r.error || "Could not add the paper", "error", 3500); return false; } }
    if (newc.length) { newc.forEach(p => { const [g, s] = String(p).split("/"); (cats[g] = cats[g] || []).includes(s) || cats[g].push(s); }); await api("set_categories", { cats }); }
    return true;
  }
  function card(x, i) {
    const cats = (x.cats || []).map(c => String(c).replace("/", " › ")).join(", ");
    const nd = nabDate(), dayB = x.date && nd && x.date !== nd ? `<span class="ph-day" title="The paper of this day">Paper of ${esc(dayName(x.date))}</span>` : "";
    const newB = (x.new_paper ? '<span class="ph-new">New paper</span>' : "") + ((x.new_cats || []).length ? '<span class="ph-new">New category</span>' : "");
    return `<div class="ph-it" draggable="true" data-i="${i}" data-id="${esc(x.id)}" title="Drag onto the canvas to use it, or drag up/down to reorder"><div class="ph-top"><img class="ph-lg" alt="" src="${url("/logo?n=" + encodeURIComponent(x.paper || ""))}" onerror="this.remove()"><b>${esc(x.paper)}</b><span>Page ${esc(x.page)}</span><span class="ph-pos">${esc(x.position)} · ${esc(x.size)}</span></div>${dayB || newB ? `<div class="ph-tags">${dayB}${newB}</div>` : ""}
      <div class="ph-cat">${esc(cats)}</div>${x.note ? `<div class="ph-note">${esc(x.note)}</div>` : ""}
      <div class="ph-bot"><small>${esc(x.user)} · ${esc((x.created || "").slice(11, 16))}</small><span class="grow"></span>${x.has_image ? `<button class="mini" data-im="${i}">Image</button>` : ""}<button class="mini" data-del="${i}" title="Delete this phone clip">Delete</button><button class="mini pri" data-u="${i}">Use</button></div></div>`;
  }
  function paint(err) {
    const order = group(items), flat = [];
    box.innerHTML = `<div class="panel-h"><b>Phone clips</b><span class="tag" id="phN">${items.length}</span><span class="grow"></span><button class="mini" id="phR" title="Refresh">↻</button><button class="mini" id="phU" title="Epaper address of each paper">⚙</button></div>` +
      (using ? `<div class="ph-using"><span>In use: <b>${esc(using.paper)}</b> p${esc(using.page)} ${esc(using.position)}</span><span class="grow"></span><button class="mini" id="phBack">Put back</button><button class="mini pri" id="phDone">Done</button></div>` : "") +
      (err ? `<div class="tag warn" style="display:block;margin:6px 0">${esc(err)}</div>` : "") +
      `<div class="ph-list">` + (order.length ? order.map(([n, arr, byPaper]) => `<div class="ph-g${byPaper ? "" : " pri"}"><div class="ph-gh">${esc(n)} <i>${arr.length}</i>${byPaper ? `<img class="plg" alt="" src="${url("/logo?n=" + encodeURIComponent(n))}" onerror="this.remove()">` : ""}</div>${arr.map(x => { flat.push(x); return card(x, flat.length - 1); }).join("")}</div>`).join("")
        : `<p class="sub">${err ? "" : "Nothing waiting."}</p>`) + `</div>`;
    $("#phR", box).onclick = () => load(true); $("#phU", box).onclick = urls;
    $$("[data-im]", box).forEach(b => b.onclick = async () => { const r = await api("phone_image", { id: flat[+b.dataset.im].id }); toast(r.ok ? "Image opened. Copy it, then press Use." : r.error, r.ok ? "ok" : "error", 3500); });
    const use = async (x) => {
      if (!window.CLIP_APPLY) return toast("The Clip screen is not ready", "error", 2500);
      if (!(await addNew(x))) return;
      const was = nabDate();
      items = items.filter(i => i.id !== x.id); using = x; paint("");          // gone from the list at once; Drive is told in the background
      api("phone_taken", { id: x.id }).then(t => { if (!t.ok) { toast(t.error, "error", 3500); using = null; load(true); } });
      await setNabDate(x.date);
      await window.CLIP_APPLY(x);
      if (x.date && was && x.date !== was) toast("Date changed to " + dayName(x.date) + " for this clip", "warn", 3500);
      toast("Filled in from the phone. Clip the news now.", "ok", 2500);
    };
    const back = $("#phBack", box), done = $("#phDone", box);
    if (back) back.onclick = async () => { const x = using; using = null; if (x) { items.push(x); sortItems(); } paint(""); const r = await api("phone_release", { id: x.id }); if (!r.ok) toast(r.error, "error", 3500); load(true); };
    if (done) done.onclick = () => { using = null; paint(""); };
    $$("[data-del]", box).forEach(b => b.onclick = async () => {
      const x = flat[+b.dataset.del];
      if (!(await ask(`<h3>Delete this phone clip?</h3><p>${esc(x.paper)} · Page ${esc(x.page)} · ${esc(x.position)}</p><p class="sub">It is removed for everyone.</p>`, "Delete"))) return;
      items = items.filter(i => i.id !== x.id); paint("");
      const r = await api("phone_delete", { id: x.id }); if (!r.ok) { toast(r.error, "error", 3500); load(true); }
    });
    window.PHONE_USE = (idx) => flat[+idx] && use(flat[+idx]);
    window.PHONE_NEXT = async () => { const x = flat[0]; if (!x) return toast("No phone clips waiting", "", 1800); if (x.has_image) api("phone_image", { id: x.id }); await use(x); };
    $$("[data-u]", box).forEach(b => b.onclick = () => use(flat[+b.dataset.u]));
    $$(".ph-it", box).forEach(el => {
      el.ondragstart = (e) => { dragId = el.dataset.id; e.dataTransfer.setData("application/x-nab-phone", el.dataset.i); e.dataTransfer.effectAllowed = "copyMove"; el.classList.add("dragging"); };
      el.ondragend = () => { dragId = null; el.classList.remove("dragging"); $$(".ph-it.over", box).forEach(n => n.classList.remove("over")); };
      el.ondragover = (e) => { if (!dragId || dragId === el.dataset.id) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; el.classList.add("over"); };
      el.ondragleave = () => el.classList.remove("over");
      el.ondrop = (e) => { if (!dragId || dragId === el.dataset.id) return; e.preventDefault(); e.stopPropagation(); el.classList.remove("over"); moveBefore(dragId, el.dataset.id); };
    });
  }
  async function load(manual) {
    if (!manual && (document.hidden || !$("#view-clip") || $("#view-clip").classList.contains("hidden"))) return;
    const r = await api("phone_list").catch(() => ({ ok: false, error: "No connection" }));
    items = (r.items || []).slice(); sortItems();
    if (using) items = items.filter(i => i.id !== using.id);
    if (r.ok) { const ids = new Set(items.map(x => x.id)); if (known && items.some(x => !known.has(x.id))) { beep(); toast("New clip from the phone", "ok", 2500); } known = ids; }
    paint(r.ok ? "" : r.error);
  }
  async function urls() {
    const r = await api("phone_papers");
    C.modal(`<h3>Epaper address of each paper</h3><p class="sub">The phone app shows an Open epaper button for each paper that has an address.</p><div style="max-height:55vh;overflow:auto">${(r.papers || []).map((p, i) => `<div class="field"><label>${esc(p.name)}</label><input data-n="${i}" value="${esc(p.url)}" placeholder="https://epaper..."></div>`).join("")}</div><div class="modal-actions"><button class="btn" id="uNo">Close</button><button class="btn pri" id="uOk">Save</button></div>`, (cd, close) => {
      $("#uNo").onclick = close;
      $("#uOk").onclick = async () => {
        let bad = "";
        for (const i of $$("[data-n]", cd)) { const p = r.papers[+i.dataset.n]; if (i.value.trim() !== (p.url || "")) { const s = await api("phone_set_url", { name: p.name, url: i.value }); if (!s.ok) bad = s.error; } }
        if (bad) return toast(bad, "error", 3500);
        close(); toast("Saved. The phone gets it within a minute or two.", "ok", 3000);
      };
    });
  }
  function start() { box = $("#phonePanel"); if (!box) return; paint(""); load(true); timer = setInterval(load, 6000); }
  window.PHONE_GROUP = group;
  window.addEventListener("keydown", (e) => { if (e.ctrlKey && e.shiftKey && (e.key === "N" || e.key === "n") && window.PHONE_NEXT) { e.preventDefault(); window.PHONE_NEXT(); } });
  if (document.readyState !== "loading") setTimeout(start, 0); else document.addEventListener("DOMContentLoaded", start);
})();
