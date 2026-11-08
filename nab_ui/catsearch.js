// Category search (Ctrl+K): type 1-3 letters, Tab / arrows move, Enter picks, Alt+Enter adds to a batch and keeps going.
(function () {
  "use strict";
  let box = null;
  function paths(cats) {
    const out = [];
    Object.keys(cats || {}).forEach((r) => { const subs = cats[r] || []; if (!subs.length) out.push(r); else subs.forEach((s) => out.push(r + "/" + s)); });
    return out;
  }
  function score(p, q) {
    const l = p.toLowerCase(), words = l.split(/[\s\/&,\-_()]+/).filter(Boolean);
    if (!q) return 1;
    const parts = q.split(/\s+/).filter(Boolean);
    let sc = 0;
    for (const w of parts) {
      let s = 0;
      if (words.some((x) => x.startsWith(w))) s = 3;
      else if (l.includes(w)) s = 2;
      else { let i = 0; for (const ch of w) { i = l.indexOf(ch, i); if (i < 0) break; i++; } if (i >= 0 && w.length > 1) s = 1; }
      if (!s) return 0; sc += s;
    }
    return sc + (words[0] && words[0].startsWith(parts[0]) ? 1 : 0);
  }
  function open(cats, current, onPick) {
    if (box) return;
    const all = paths(cats); if (!all.length) return;
    const colorOf = (p) => (window.C && C.catColor) ? C.catColor(p.split("/")[0], Object.keys(cats)) : "var(--acc,#5b8cff)";
    const prevFocus = document.activeElement;
    box = document.createElement("div"); box.id = "catSearch";
    box.style.cssText = "position:fixed;inset:0;z-index:100000;display:flex;align-items:flex-start;justify-content:center;padding-top:8vh;background:rgba(5,6,12,.55)";
    box.innerHTML = '<div style="width:min(480px,92vw);background:var(--surf,#131521);border:1px solid var(--line,#292d43);border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.55);color:var(--txt,#f3f4fa);font-size:13px;overflow:hidden">' +
      '<div style="padding:10px 12px;border-bottom:1px solid var(--line,#292d43)"><input id="csI" autocomplete="off" spellcheck="false" placeholder="Type 1-3 letters of a category" style="width:100%;background:transparent;border:0;outline:0;color:inherit;font-size:15px"></div>' +
      '<div id="csB" style="display:none;gap:6px;flex-wrap:wrap;padding:8px 12px;border-bottom:1px solid var(--line,#292d43)"></div>' +
      '<div id="csL" style="max-height:44vh;overflow:auto;padding:4px"></div>' +
      '<div style="padding:7px 12px;color:var(--dim,#8f93ac);font-size:11px;border-top:1px solid var(--line,#292d43)">Tab / arrows: move &nbsp; Enter: select &nbsp; Alt+Enter: add and pick another &nbsp; Esc: close</div></div>';
    document.body.appendChild(box);
    const inp = box.querySelector("#csI"), list = box.querySelector("#csL"), bw = box.querySelector("#csB");
    let items = [], idx = 0; const batch = [];
    const chip = (p) => '<span style="padding:3px 9px;border-radius:99px;background:' + colorOf(p) + ';color:#fff;font-size:12px">' + p.split("/").join(" › ").replace(/</g, "&lt;") + "</span>";
    function draw() {
      const q = inp.value.trim().toLowerCase();
      items = all.map((p) => [p, score(p, q)]).filter((x) => x[1] > 0 && !batch.includes(x[0])).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map((x) => x[0]).slice(0, 60);
      if (idx >= items.length) idx = Math.max(0, items.length - 1);
      list.innerHTML = items.length ? items.map((p, i) => '<div data-i="' + i + '" style="display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;cursor:pointer;background:' + (i === idx ? "rgba(91,140,255,.18)" : "transparent") + '"><i style="width:9px;height:9px;border-radius:50%;background:' + colorOf(p) + '"></i><span>' + p.split("/").join(" › ").replace(/</g, "&lt;") + "</span>" + (current && current.includes(p) ? '<span style="margin-left:auto;color:var(--dim,#8f93ac);font-size:11px">armed</span>' : "") + "</div>").join("") : '<div style="padding:12px;color:var(--dim,#8f93ac)">No category matches</div>';
      bw.style.display = batch.length ? "flex" : "none"; bw.innerHTML = batch.map(chip).join("");
      const a = list.querySelector('[data-i="' + idx + '"]'); if (a && a.scrollIntoView) a.scrollIntoView({ block: "nearest" });
    }
    function close() { box.remove(); box = null; document.removeEventListener("keydown", key, true); try { if (prevFocus && prevFocus.focus) prevFocus.focus(); } catch (e) {} }
    function finish() { const pick = batch.slice(); if (items[idx] && (inp.value.trim() || !pick.length)) pick.push(items[idx]); close(); if (pick.length) onPick(pick); }
    function key(e) {
      if (!box) return;
      const k = e.key;
      if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
      if (k === "Tab" || k === "ArrowDown" || k === "ArrowUp") { e.preventDefault(); e.stopPropagation(); if (items.length) idx = (idx + ((k === "ArrowUp" || (k === "Tab" && e.shiftKey)) ? -1 : 1) + items.length) % items.length; draw(); return; }
      if (k === "Enter") { e.preventDefault(); e.stopPropagation(); if (e.altKey) { if (items[idx]) { batch.push(items[idx]); inp.value = ""; idx = 0; draw(); } } else finish(); return; }
      e.stopPropagation();
    }
    document.addEventListener("keydown", key, true);
    inp.addEventListener("input", () => { idx = 0; draw(); });
    list.addEventListener("mousedown", (e) => { const r = e.target.closest("[data-i]"); if (!r) return; e.preventDefault(); idx = +r.dataset.i; if (e.altKey) { batch.push(items[idx]); inp.value = ""; idx = 0; draw(); inp.focus(); } else finish(); });
    box.addEventListener("mousedown", (e) => { if (e.target === box) close(); });
    draw(); setTimeout(() => inp.focus(), 0);
  }
  function install(getCats, getArmed, onPick, canOpen) {
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") {
        if (canOpen && !canOpen()) return;
        e.preventDefault(); e.stopImmediatePropagation(); open(getCats(), getArmed(), onPick);
      }
    }, true);
  }
  window.CATSEARCH = { open, install };
})();
