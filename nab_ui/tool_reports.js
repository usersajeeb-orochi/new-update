// tool_reports.js - Reports: build a PDF + Excel summary now, edit templates, schedule jobs.
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  let el, st = {}, tab = "run";
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const RANGES = [["today", "Today"], ["yesterday", "Yesterday"], ["last7", "Last 7 days"], ["last30", "Last 30 days"], ["this_month", "This month"], ["last_month", "Last month"], ["custom", "Custom dates"]];
  const opt = (arr, cur, any) => (any ? '<option value="">' + any + "</option>" : "") + (arr || []).map(x => { const v = typeof x === "string" ? x : x[0], l = typeof x === "string" ? x : x[1]; return `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`; }).join("");

  function mount(e) {
    el = e;
    el.innerHTML = `<div class="tk pdf"><div class="card"><div class="tk-bar"><b class="grow">Reports</b>
      <button class="btn" data-t="run">Make a report</button><button class="btn" data-t="jobs">Scheduled</button><button class="btn" data-t="tpl">Templates</button></div></div><div class="tk-body" id="rpBody"></div></div>`;
    $$("[data-t]", el).forEach(b => b.onclick = () => { tab = b.dataset.t; draw(); });
    on("tool", ev => { if (ev.tool === "reports" && ev.ev === "job_done") show(); });
  }
  async function show() { st = await api("reports_state"); draw(); }
  function draw() {
    $$("[data-t]", el).forEach(b => b.classList.toggle("pri", b.dataset.t === tab));
    ({ run, jobs, tpl })[tab]();
  }

  // ---- make now
  function paramsForm(p, pre) {
    p = p || {};
    return `<div class="tk-bar" style="flex-wrap:wrap;gap:10px">
      <label class="sub">Template <select id="${pre}Tpl">${opt(st.templates.map(t => t.name), p.template)}</select></label>
      <label class="sub">Paper <select id="${pre}Paper">${opt(st.papers, p.paper, "Any")}</select></label>
      <label class="sub">Category <select id="${pre}Cat">${opt(st.cats, p.cat, "Any")}</select></label>
      <label class="sub">Period <select id="${pre}Range">${opt(RANGES, p.range || "yesterday")}</select></label>
      <label class="sub">From <input type="date" id="${pre}From" value="${esc(p.date_from || "")}"></label><label class="sub">To <input type="date" id="${pre}To" value="${esc(p.date_to || "")}"></label>
      <label class="sub">Saved by <select id="${pre}User">${opt(st.users, p.user, "Anyone")}</select></label></div>`;
  }
  const readParams = pre => ({ template: $("#" + pre + "Tpl").value, paper: $("#" + pre + "Paper").value, cat: $("#" + pre + "Cat").value, range: $("#" + pre + "Range").value, date_from: $("#" + pre + "From").value, date_to: $("#" + pre + "To").value, user: $("#" + pre + "User").value });

  function run() {
    $("#rpBody").innerHTML = `<div class="card">${paramsForm({}, "r")}<div class="tk-bar" style="margin-top:10px"><button class="btn pri" id="rGo">Make the report</button><span id="rInfo" class="sub grow"></span></div></div><div id="rOut"></div>`;
    $("#rGo").onclick = async () => {
      $("#rInfo").textContent = "Building…"; $("#rGo").disabled = true;
      const r = await api("reports_run", readParams("r")); $("#rGo").disabled = false;
      if (!r.ok) { $("#rInfo").textContent = ""; return toast(r.error || "Could not make the report", "error", 4000); }
      $("#rInfo").textContent = r.n + " clips, " + (r.pages || 0) + " pages";
      $("#rOut").innerHTML = `<div class="card"><b>Report ready</b><div class="sub">${esc(r.path)}</div>${r.xlsx ? `<div class="sub">${esc(r.xlsx)}</div>` : ""}<div class="tk-bar" style="margin-top:8px"><button class="btn" id="rOpen">Open folder</button></div></div>`;
      $("#rOpen").onclick = () => api("reports_open", { path: r.path.replace(/[\\/][^\\/]*$/, "") });
    };
  }

  // ---- scheduled jobs
  function jobs() {
    const j = st.jobs || [];
    $("#rpBody").innerHTML = `<div class="card"><div class="tk-bar"><span class="sub grow">Jobs run on this PC at the chosen time while NAB is open. A job missed while NAB was closed runs on opening if it is inside its catch-up window.</span><button class="btn pri" id="jNew">New job</button></div></div>` +
      (j.length ? '<table class="t"><thead><tr><td>Job</td><td>When</td><td>Sends to</td><td>Last</td><td></td></tr></thead><tbody>' + j.map((x, i) => `<tr><td><b>${esc(x.name)}</b><div class="sub">${x.kind === "report" ? "Report" : "Self-check"}${x.enabled ? "" : " (off)"}</div></td><td>${esc(x.time)}<div class="sub">${x.days.length === 7 ? "Every day" : x.days.map(d => DAYS[d]).join(" ")}</div></td><td>${esc(x.deliver.join(", "))}</td><td class="sub">${esc(x.last_result || "Not run yet")}</td><td><button class="btn mini" data-r="${i}">Run now</button> <button class="btn mini" data-e="${i}">Edit</button></td></tr>`).join("") + "</tbody></table>" : '<p class="sub">No scheduled jobs yet.</p>') +
      `<h4>Recent runs</h4>` + ((st.log || []).length ? (st.log || []).map(l => `<div class="sub">${esc(l.t)} - ${esc(l.msg)}: ${esc(l.result || "")}</div>`).join("") : '<p class="sub">Nothing yet.</p>');
    $("#jNew").onclick = () => jobForm({});
    $$("[data-e]").forEach(b => b.onclick = () => jobForm(j[+b.dataset.e]));
    $$("[data-r]").forEach(b => b.onclick = async () => { await api("reports_job_run", { id: j[+b.dataset.r].id }); toast("Running. The result shows under Recent runs.", "ok", 3000); });
  }
  function jobForm(j) {
    const isNew = !j.id, d = j.deliver || ["folder"];
    C.modal(`<h3>${isNew ? "New job" : "Edit job"}</h3><div style="max-height:62vh;overflow:auto">
      <div class="field"><label>Name</label><input id="jN" value="${esc(j.name || "")}" maxlength="60"></div>
      <div class="field"><label>What</label><select id="jK"><option value="report" ${j.kind !== "selfcheck" ? "selected" : ""}>Report (PDF + Excel)</option><option value="selfcheck" ${j.kind === "selfcheck" ? "selected" : ""}>Self-check, alert me only if something is wrong</option></select></div>
      <div id="jP">${paramsForm(j.params || {}, "j")}</div>
      <div class="tk-bar" style="flex-wrap:wrap"><label class="sub">Time <input type="time" id="jT" value="${esc(j.time || "09:00")}"></label><label class="sub">Catch-up hours <input type="number" id="jC" min="0" max="23" value="${j.catchup_h == null ? 6 : j.catchup_h}" style="width:70px"></label></div>
      <div class="tk-bar" style="flex-wrap:wrap">${DAYS.map((n, i) => `<label class="row"><input type="checkbox" data-d="${i}" ${!j.days || j.days.includes(i) ? "checked" : ""}> ${n}</label>`).join("")}</div>
      <div class="tk-bar" style="flex-wrap:wrap">${["folder", "telegram", "whatsapp", "mail"].map(k => `<label class="row"><input type="checkbox" data-s="${k}" ${d.includes(k) ? "checked" : ""}> ${{ folder: "Save in folder", telegram: "Telegram", whatsapp: "WhatsApp", mail: "E-mail" }[k]}</label>`).join("")}</div>
      <div class="field"><label>WhatsApp chat or group name</label><input id="jW" value="${esc(j.chat || "")}"></div>
      <div class="field"><label>E-mail addresses (comma separated)</label><input id="jM" value="${esc((j.mail_to || []).join(", "))}"></div>
      <label class="row"><input type="checkbox" id="jE" ${j.enabled === false ? "" : "checked"}> Job is on</label></div>
      <div class="modal-actions">${isNew ? "" : '<button class="btn" id="jDel">Delete</button>'}<button class="btn" id="jNo">Cancel</button><button class="btn pri" id="jOk">Save</button></div>`, (cd, close) => {
      $("#jNo").onclick = close;
      if (!isNew) $("#jDel").onclick = async () => { if (!confirm("Delete this job?")) return; const r = await api("reports_job_delete", { id: j.id }); st.jobs = r.jobs; close(); draw(); };
      $("#jOk").onclick = async () => {
        const job = { id: j.id, name: $("#jN").value, kind: $("#jK").value, params: readParams("j"), time: $("#jT").value, catchup_h: +$("#jC").value, enabled: $("#jE").checked, chat: $("#jW").value, mail_to: $("#jM").value,
          days: $$("[data-d]", cd).filter(x => x.checked).map(x => +x.dataset.d), deliver: $$("[data-s]", cd).filter(x => x.checked).map(x => x.dataset.s) };
        if (!job.name.trim()) return toast("Give the job a name", "warn", 2000);
        const r = await api("reports_job_save", { job }); st.jobs = r.jobs; close(); draw(); toast("Saved", "ok", 1500);
      };
    });
  }

  // ---- templates
  function tpl() {
    $("#rpBody").innerHTML = `<div class="card"><div class="tk-bar"><span class="sub grow">A template sets the report title, client name, colour and layout.</span><button class="btn pri" id="tNew">New template</button></div></div>` +
      '<table class="t"><thead><tr><td>Name</td><td>Title</td><td>Client</td><td>Per page</td><td></td></tr></thead><tbody>' + st.templates.map((t, i) => `<tr><td><b>${esc(t.name)}</b></td><td>${esc(t.title)}</td><td>${esc(t.client)}</td><td>${t.per_page}</td><td><button class="btn mini" data-e="${i}">Edit</button></td></tr>`).join("") + "</tbody></table>";
    $("#tNew").onclick = () => tplForm({});
    $$("[data-e]").forEach(b => b.onclick = () => tplForm(st.templates[+b.dataset.e]));
  }
  function tplForm(t) {
    C.modal(`<h3>${t.name ? "Edit template" : "New template"}</h3>
      <div class="field"><label>Name</label><input id="tN" value="${esc(t.name || "")}" maxlength="40"></div><div class="field"><label>Report title</label><input id="tT" value="${esc(t.title || "Media Coverage Report")}"></div>
      <div class="field"><label>Client name on the cover</label><input id="tC" value="${esc(t.client || "")}"></div><div class="field"><label>Footer text</label><input id="tF" value="${esc(t.footer || "")}"></div>
      <div class="field"><label>Accent colour</label><input id="tA" value="${esc(t.accent || "#2f5fd0")}" maxlength="7" style="width:110px"></div>
      <div class="tk-bar"><label class="row"><input type="checkbox" id="tCv" ${t.cover === false ? "" : "checked"}> Cover page</label><label class="row"><input type="checkbox" id="tCa" ${t.caption === false ? "" : "checked"}> Caption under each clip</label><label class="sub">Clips per page <select id="tP"><option ${t.per_page !== 2 ? "selected" : ""}>1</option><option ${t.per_page === 2 ? "selected" : ""}>2</option></select></label></div>
      <div class="modal-actions">${t.name && st.templates.length > 1 ? '<button class="btn" id="tDel">Delete</button>' : ""}<button class="btn" id="tNo">Cancel</button><button class="btn pri" id="tOk">Save</button></div>`, (cd, close) => {
      $("#tNo").onclick = close;
      if ($("#tDel")) $("#tDel").onclick = async () => { const r = await api("reports_template_delete", { name: t.name }); st.templates = r.templates; close(); draw(); };
      $("#tOk").onclick = async () => {
        if (!$("#tN").value.trim()) return toast("Give the template a name", "warn", 2000);
        const r = await api("reports_template_save", { template: { name: $("#tN").value, title: $("#tT").value, client: $("#tC").value, footer: $("#tF").value, accent: $("#tA").value, cover: $("#tCv").checked, caption: $("#tCa").checked, per_page: +$("#tP").value } });
        st.templates = r.templates; close(); draw(); toast("Saved", "ok", 1500);
      };
    });
  }
  window.TOOLS.reports = { mount, show };
})();
