// tool_phone.js - Phone queue: clips described on the colleague's phone, ready to be taken into the Clip screen.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, toast } = C;
  let el, items = [];
  function mount(e) {
    el = e;
    el.innerHTML = `<div class="tk pdf"><div class="card"><div class="tk-bar"><b class="grow">Phone queue</b><button class="btn" id="phR">Refresh</button><button class="btn" id="phU">Epaper addresses</button></div>
      <p class="sub">Entries from the NAB Metadata app wait here. Press Use, then clip the news: paper, page, position, size and category are already filled in.</p><div id="phErr" class="tag warn" style="display:none"></div></div>
      <div class="tk-body" id="phList"></div></div>`;
    $("#phR").onclick = show; $("#phU").onclick = urls;
  }
  async function show() {
    $("#phList").innerHTML = '<p class="sub">Loading…</p>';
    const r = await api("phone_list"), er = $("#phErr");
    er.style.display = r.ok ? "none" : ""; er.textContent = r.ok ? "" : r.error;
    items = r.items || [];
    $("#phList").innerHTML = items.length ? '<table class="t"><thead><tr><td>By</td><td>Paper</td><td>Page</td><td>Position</td><td>Size</td><td>Category</td><td>Note</td><td></td></tr></thead><tbody>' +
      items.map((x, i) => `<tr><td>${esc(x.user)}<div class="sub">${esc(x.created)}</div></td><td>${esc(x.paper)}</td><td>${esc(x.page)}</td><td>${esc(x.position)}</td><td>${esc(x.size)}</td><td>${esc((x.cats || []).map(c => c.replace("/", " › ")).join(", "))}</td><td>${esc(x.note)}</td><td>${x.has_image ? `<button class="btn mini" data-im="${i}">Image</button> ` : ""}<button class="btn mini pri" data-u="${i}">Use</button></td></tr>`).join("") + "</tbody></table>" : (r.ok ? '<p class="sub">Nothing waiting.</p>' : "");
    $$("#phList [data-im]").forEach(b => b.onclick = async () => { const r = await api("phone_image", { id: items[+b.dataset.im].id }); toast(r.ok ? "Image opened. Copy it, then press Use." : r.error, r.ok ? "ok" : "error", 3500); });
    $$("#phList [data-u]").forEach(b => b.onclick = async () => {
      const x = items[+b.dataset.u];
      if (!window.CLIP_APPLY) return toast("The Clip screen is not ready", "error", 2500);
      const t = await api("phone_taken", { id: x.id });
      if (!t.ok) { toast(t.error, "error", 3500); return show(); }
      await window.CLIP_APPLY(x);
      const nav = document.querySelector('[data-view="clip"]'); nav && nav.click();
      toast("Filled in from the phone. Clip the news now.", "ok", 3500);
    });
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
  window.TOOLS.phone = { mount, show };
})();
