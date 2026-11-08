// tool_wa.js — "Send to WhatsApp": setup dialog + send helper used by the recent-saves drawer, command bar and overlay-free workflows.
(function () {
  const { $, esc, api, on, toast, modal } = C;
  let st = null;
  const label = { idle: "Not started", starting: "Starting…", login: "Waiting for QR scan", ready: "Linked", error: "Problem" };
  async function load() { st = await api("wa_state"); return st; }

  async function setup() {
    await load(); const c = st.cfg;
    modal(`<h3>WhatsApp</h3>
      <div class="lbl" id="waSt"></div>
      <div class="tk-bar"><button class="btn pri" id="waLink">Link WhatsApp</button><button class="btn" id="waOut">Unlink</button></div>
      <div class="field"><label>Chats or groups (one per line: exact name as shown in WhatsApp, or your phone number with country code, for example 8801XXXXXXXXX)</label><textarea id="waChats" style="height:80px">${esc((c.chats || []).join("\n"))}</textarea></div>
      <div class="field"><label>Default chat</label><select id="waDef"></select></div>
      <div class="field"><label>Chat per category (optional, overrides the default)</label><div id="waCats" style="max-height:150px;overflow:auto"></div></div>
      <label class="row"><input type="checkbox" id="waDoc" ${c.as_document !== false ? "checked" : ""}> <span>Send as file (keeps full quality; otherwise WhatsApp compresses the picture)</span></label>
      <label class="row"><input type="checkbox" id="waCap" ${c.caption ? "checked" : ""}> <span>Use the file name as caption</span></label>
      <label class="row"><input type="checkbox" id="waAuto" ${c.auto ? "checked" : ""}> <span>Send every saved clip automatically (only categories with a chat, or the default)</span></label>
      <label class="row"><input type="checkbox" id="waShow" ${c.show_window ? "checked" : ""}> <span>Show the browser window while sending</span></label>
      <div class="modal-actions"><button class="btn" id="waNo">Close</button><button class="btn pri" id="waYes">Save</button></div>`, (card, close) => {
      const chats = () => $("#waChats").value.split(/\n+/).map(x => x.trim()).filter(Boolean);
      const fill = () => {
        const list = chats(), cur = $("#waDef").value || c.default;
        $("#waDef").innerHTML = `<option value="">(ask me each time)</option>` + list.map(x => `<option ${x === cur ? "selected" : ""}>${esc(x)}</option>`).join("");
        $("#waCats").innerHTML = (st.categories || []).map(k => `<div class="row"><span style="flex:1">${esc(C.clean(k))}</span><select class="mini-in wac" data-k="${esc(k)}"><option value="">default</option>${list.map(x => `<option ${(c.per_category || {})[k] === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>`).join("") || `<div class="lbl">No categories yet.</div>`;
      };
      const stat = (s) => { $("#waSt").textContent = (label[s.status] || s.status) + (s.msg ? ": " + s.msg : "") + (st.deps ? "" : "  (Playwright is not installed: pip install playwright)"); };
      stat(st); fill(); $("#waChats").oninput = fill;
      const off = on("tool", (ev) => { if (ev.tool === "wa" && ev.ev === "status" && $("#waSt")) stat(ev); });
      const save = async () => { const pc = {}; card.querySelectorAll(".wac").forEach(s => { if (s.value) pc[s.dataset.k] = s.value; });
        await api("wa_settings", { chats: chats(), default: $("#waDef").value, per_category: pc, as_document: $("#waDoc").checked, caption: $("#waCap").checked, auto: $("#waAuto").checked, show_window: $("#waShow").checked }); };
      $("#waLink").onclick = async () => { await save(); const r = await api("wa_login"); if (!r.ok) toast(r.error, "error", 5000); else toast("A browser window opens: scan the QR code", "ok", 4000); };
      $("#waOut").onclick = async () => { await api("wa_logout"); toast("Unlinked", "ok"); };
      $("#waNo").onclick = close; $("#waYes").onclick = async () => { await save(); toast("Saved", "ok"); close(); };
    });
  }

  async function sendRecent(it) {
    await load(); const c = st.cfg, chat = (c.per_category || {})[it.category] || c.default;
    if (!chat) {
      if (!(c.chats || []).length) { toast("Set up a chat first", "warn"); return setup(); }
      return modal(`<h3>Send to which chat?</h3><div class="field"><select id="waPick">${c.chats.map(x => `<option>${esc(x)}</option>`).join("")}</select></div><div class="modal-actions"><button class="btn" id="waNo">Cancel</button><button class="btn pri" id="waGo">Send</button></div>`, (cd, close) => {
        $("#waNo").onclick = close; $("#waGo").onclick = async () => { close(); go(it, $("#waPick").value); };
      });
    }
    go(it, chat);
  }
  async function go(it, chat) {
    const r = await api("wa_send_recent", { i: it.i, chat }); if (!r.ok) { toast(r.error, "error", 5000); if (/Choose|Playwright/.test(r.error || "")) setup(); return; }
    toast("Sending to " + chat + "…", "ok", 2500);
  }
  on("tool", (ev) => {
    if (ev.tool !== "wa") return;
    if (ev.ev === "sent") toast("Sent to " + ev.chat + ": " + ev.name, "ok", 3500);
    else if (ev.ev === "fail") toast("WhatsApp failed: " + ev.error, "error", 7000);
    else if (ev.ev === "status" && ev.status === "login") toast(ev.msg, "ok", 6000);
  });
  window.WA = { setup, sendRecent };
})();
