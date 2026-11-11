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
  let items = [], timer = 0, box;
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
  function card(x, i) {
    const cats = (x.cats || []).map(c => String(c).replace("/", " › ")).join(", ");
    return `<div class="ph-it" draggable="true" data-i="${i}" title="Drag onto the canvas, or press Use"><div class="ph-top"><b>${esc(x.paper)}</b><span>Page ${esc(x.page)}</span><span>${esc(x.position)} · ${esc(x.size)}</span></div>
      <div class="ph-cat">${esc(cats)}</div>${x.note ? `<div class="ph-note">${esc(x.note)}</div>` : ""}
      <div class="ph-bot"><small>${esc(x.user)} · ${esc((x.created || "").slice(11, 16))}</small><span class="grow"></span>${x.has_image ? `<button class="mini" data-im="${i}">Image</button>` : ""}<button class="mini pri" data-u="${i}">Use</button></div></div>`;
  }
  function paint(err) {
    const order = group(items), flat = [];
    box.innerHTML = `<div class="panel-h"><b>Phone clips</b><span class="tag" id="phN">${items.length}</span><span class="grow"></span><button class="mini" id="phR" title="Refresh">↻</button><button class="mini" id="phU" title="Epaper address of each paper">⚙</button></div>` +
      (err ? `<div class="tag warn" style="display:block;margin:6px 0">${esc(err)}</div>` : "") +
      `<div class="ph-list">` + (order.length ? order.map(([n, arr, byPaper]) => `<div class="ph-g${byPaper ? "" : " pri"}"><div class="ph-gh">${esc(n)} <i>${arr.length}</i>${byPaper ? `<img class="plg" alt="" src="${url("/logo?n=" + encodeURIComponent(n))}" onerror="this.remove()">` : ""}</div>${arr.map(x => { flat.push(x); return card(x, flat.length - 1); }).join("")}</div>`).join("")
        : `<p class="sub">${err ? "" : "Nothing waiting."}</p>`) + `</div>`;
    $("#phR", box).onclick = () => load(true); $("#phU", box).onclick = urls;
    $$("[data-im]", box).forEach(b => b.onclick = async () => { const r = await api("phone_image", { id: flat[+b.dataset.im].id }); toast(r.ok ? "Image opened. Copy it, then press Use." : r.error, r.ok ? "ok" : "error", 3500); });
    const use = async (x) => {
      if (!window.CLIP_APPLY) return toast("The Clip screen is not ready", "error", 2500);
      const t = await api("phone_taken", { id: x.id });
      if (!t.ok) { toast(t.error, "error", 3500); return load(); }
      await window.CLIP_APPLY(x); load();
      toast("Filled in from the phone. Clip the news now.", "ok", 3500);
    };
    window.PHONE_USE = (idx) => flat[+idx] && use(flat[+idx]);
    window.PHONE_NEXT = async () => { const x = flat[0]; if (!x) return toast("No phone clips waiting", "", 1800); if (x.has_image) api("phone_image", { id: x.id }); await use(x); };
    $$("[data-u]", box).forEach(b => b.onclick = () => use(flat[+b.dataset.u]));
    $$(".ph-it", box).forEach(el => { el.ondragstart = (e) => { e.dataTransfer.setData("application/x-nab-phone", el.dataset.i); e.dataTransfer.effectAllowed = "copy"; el.classList.add("dragging"); }; el.ondragend = () => el.classList.remove("dragging"); });
  }
  async function load(manual) {
    if (!manual && (document.hidden || !$("#view-clip") || $("#view-clip").classList.contains("hidden"))) return;
    const r = await api("phone_list").catch(() => ({ ok: false, error: "No connection" }));
    items = r.items || [];
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
