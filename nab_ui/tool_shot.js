// tool_shot.js — Screenshot Bot screen (the old "Nitro PR Engine", now inside NAB).
window.TOOLS = window.TOOLS || {};
(function () {
  const { $, $$, esc, api, on, toast } = C;
  let el, running = false, st = null;
  const HTML = `<div class="tk"><div class="sh-top pr-top"><div><h2>Screenshot Bot</h2><div class="sub">Paste links, get one clean JPEG per article. Width and height are saved for the PR Value Calculator.</div></div><span class="grow" style="flex:1"></span><span id="shDeps"></span></div>
  <div class="sh-wrap">
    <div class="sh-col"><textarea id="shLinks" class="sh-links" placeholder="Paste article links here, one per line&#10;(duplicates are removed automatically)"></textarea>
      <div class="tk-bar"><button class="btn pri" id="shGo">Start capturing</button><button class="btn" id="shStop" disabled>Stop</button><button class="btn" id="shImp">Import .txt</button><input type="file" id="shFile" accept=".txt" style="display:none"><span class="grow" style="flex:1"></span><span id="shCnt" class="lbl"></span></div>
      <div class="sh-bar"><div id="shBar"></div></div><div class="sh-items" id="shItems"></div></div>
    <div class="sh-col"><div class="card set-card"><h4 style="margin:0">Options</h4>
      <div class="row"><span>Live view (watch the browser, solve checks by hand)</span><input type="checkbox" id="shLive"></div>
      <div class="row"><span>Pages at once</span><select id="shConc" class="mini-in">${[1, 2, 3, 4, 5, 6].map(n => `<option>${n}</option>`).join("")}</select></div>
      <div class="row"><span>Crop</span><select id="shCrop" class="mini-in"><option value="auto">Smart (article edge)</option><option value="density">Density scan only</option><option value="none">No crop</option></select></div>
      <div class="row"><span>JPEG quality</span><input id="shQ" type="number" min="30" max="95" class="mini-in" style="width:80px"></div>
      <div class="row"><span>Page width (px)</span><input id="shW" type="number" min="800" max="2560" step="10" class="mini-in" style="width:90px"></div>
      <div class="row"><span class="lbl" id="shOut" style="word-break:break-all"></span><button class="btn sm" id="shOpen">Open folder</button></div></div>
      <div class="sh-log" id="shLog"></div></div></div></div>`;
  const log = (m, k, t) => { const b = $("#shLog"); if (!b) return; const d = document.createElement("div"); if (k) d.className = k; d.innerHTML = `<time>${esc(t || new Date().toLocaleTimeString("en-GB"))}</time>${esc(m)}`; b.appendChild(d); b.scrollTop = b.scrollHeight; };
  const count = () => { const n = new Set($("#shLinks").value.split(/[\s,]+/).filter(x => x.trim())).size; $("#shCnt").textContent = n ? n + " link" + (n > 1 ? "s" : "") : ""; };
  function lock(on_) { running = on_; $("#shGo").disabled = on_; $("#shStop").disabled = !on_; $("#shGo").textContent = on_ ? "Working…" : "Start capturing"; }
  const sets = C.debounce(() => api("shot_settings", { live: $("#shLive").checked, conc: $("#shConc").value, crop: $("#shCrop").value, quality: $("#shQ").value, width: $("#shW").value }).then(r => { if (r.out) $("#shOut").textContent = r.out; }), 300);
  function mount(e) {
    el = e; el.innerHTML = HTML;
    $("#shLinks").addEventListener("input", count);
    $("#shImp").onclick = () => $("#shFile").click();
    $("#shFile").onchange = async (ev) => { const f = ev.target.files[0]; if (!f) return; $("#shLinks").value = ($("#shLinks").value.trim() + "\n" + await f.text()).trim() + "\n"; count(); ev.target.value = ""; };
    $("#shGo").onclick = async () => {
      const r = await api("shot_run", { text: $("#shLinks").value }); if (!r.ok) return toast(r.error, "error", 5000);
      $("#shItems").innerHTML = ""; $("#shBar").style.width = "0"; lock(true); log("Started: " + r.n + " link(s)");
    };
    $("#shStop").onclick = () => { api("shot_stop"); log("Stopping after the current pages…", "warn"); };
    $("#shOpen").onclick = () => api("shot_open");
    ["shLive", "shConc", "shCrop", "shQ", "shW"].forEach(id => $("#" + id).addEventListener("change", sets));
    on("tool", (ev) => {
      if (ev.tool !== "shot" || !el) return;
      if (ev.ev === "log") log(ev.msg, ev.kind, ev.at);
      else if (ev.ev === "begin") lock(true);
      else if (ev.ev === "prog") $("#shBar").style.width = Math.round(100 * ev.n / Math.max(1, ev.total)) + "%";
      else if (ev.ev === "item") { const d = document.createElement("div"); d.className = "sh-it" + (ev.ok ? "" : " bad"); let host = ev.url; try { host = new URL(ev.url).hostname.replace(/^www\./, ""); } catch (x) { }
        d.innerHTML = `<span class="d"></span><span class="t">${esc(ev.ok ? ev.file : host)}</span><small>${ev.ok ? ev.w + " x " + ev.h + " · " + ev.kb + " KB" : esc(ev.error || "failed")}</small>`; $("#shItems").prepend(d); }
      else if (ev.ev === "done") { lock(false); $("#shBar").style.width = "100%"; log(`Done: ${ev.ok_n} saved, ${ev.fail_n} failed in ${ev.secs}s${ev.stopped ? " (stopped)" : ""}`, ev.fail_n ? "warn" : "ok"); toast(ev.ok_n + " screenshot(s) saved", ev.ok_n ? "ok" : "warn", 4000); $("#shOut").textContent = ev.out; }
    });
  }
  async function show() {
    st = await api("shot_state"); const s = st.settings;
    $("#shLive").checked = !!s.live; $("#shConc").value = s.conc; $("#shCrop").value = s.crop; $("#shQ").value = s.quality; $("#shW").value = s.width; $("#shOut").textContent = st.out;
    const d = st.deps; $("#shDeps").innerHTML = [["playwright", "Playwright"], ["playwright_stealth", "Stealth"], ["cv2", "OpenCV"]].map(([k, n]) => `<span class="dep ${d[k] ? "ok" : "no"}">${n}: ${d[k] ? "ready" : "missing"}</span>`).join(" ");
    if (!d.playwright) log("Playwright is missing: pip install playwright playwright-stealth, then: playwright install chromium", "err");
    lock(!!st.running); count();
  }
  window.TOOLS.shot = { mount, show };
})();
