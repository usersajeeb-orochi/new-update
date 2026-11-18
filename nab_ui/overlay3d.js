/* Overlay 3D layer (reads the overlay's own DOM; touches none of its logic) */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const th = $(".ov-th"), img = $("#ovImg"), cat = $("#ovCat"), q = $("#ovQ"), stat = $("#ovS"), nEl = $("#ovN");
  if (!th || !img) return;
  const quiet = () => { try { return localStorage.getItem("nab_quiet") === "1"; } catch (e) { return false; } };
  /* 4 · tilt + glare following the pointer */
  th.addEventListener("pointermove", (e) => { if (quiet()) return; const r = th.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    img.style.setProperty("--ry", ((x - .5) * 14).toFixed(1) + "deg"); img.style.setProperty("--rx", ((.5 - y) * 10).toFixed(1) + "deg"); th.style.setProperty("--gx", (x * 100) + "%"); th.style.setProperty("--gy", (y * 100) + "%"); });
  th.addEventListener("pointerleave", () => { img.style.setProperty("--ry", "0deg"); img.style.setProperty("--rx", "0deg"); });
  /* 6 · queue stack: the number of waiting clips shows as cards behind the front one */
  const s2 = document.createElement("div"); s2.className = "qs2"; th.appendChild(s2);
  function stack() { const n = +(nEl.textContent || 0) || 0; th.dataset.n = n; th.classList.toggle("deep", n >= 3); th.classList.toggle("many", n >= 6); }
  new MutationObserver(stack).observe(nEl, { childList: true, characterData: true, subtree: true }); stack();
  /* 2 · category wheel: neighbours + mouse-wheel to change the armed quick category */
  const btns = () => Array.from(q.querySelectorAll("button"));
  function wheel(dir) { const b = btns(); if (!b.length) return; let i = b.findIndex((x) => x.classList.contains("on")); i = i < 0 ? (dir > 0 ? 0 : b.length - 1) : (i + dir + b.length) % b.length; cat.style.setProperty("--sp", dir > 0 ? "-60deg" : "60deg"); b[i].click(); }
  function labels() { const b = btns(); if (b.length < 2) { cat.dataset.prev = ""; cat.dataset.next = ""; return; } const i = Math.max(0, b.findIndex((x) => x.classList.contains("on"))), t = (x) => (x.title || x.textContent || "").trim();
    cat.dataset.prev = "▲ " + t(b[(i - 1 + b.length) % b.length]); cat.dataset.next = "▼ " + t(b[(i + 1) % b.length]); }
  cat.addEventListener("wheel", (e) => { e.preventDefault(); wheel(e.deltaY > 0 ? 1 : -1); }, { passive: false });
  new MutationObserver(() => { labels(); cat.classList.remove("spin"); void cat.offsetWidth; if (!quiet()) cat.classList.add("spin"); }).observe(q, { subtree: true, attributes: true, attributeFilter: ["class"], childList: true });
  labels();
  /* 3 · save: stamp, shake, the card drops away */
  new MutationObserver(() => { if (!/^Saved/i.test(stat.textContent || "") || quiet()) return;
    const st = document.createElement("div"); st.className = "ov-stamp"; st.textContent = "SAVED"; th.appendChild(st); setTimeout(() => st.remove(), 1000);
    th.classList.remove("shake"); void th.offsetWidth; th.classList.add("shake"); img.classList.remove("out"); void img.offsetWidth; img.classList.add("out"); setTimeout(() => img.classList.remove("out"), 1000); })
    .observe(stat, { childList: true, characterData: true, subtree: true });
  /* 5 · page-size ghost: the size you typed (W x H) as a translucent page outline on the clip */
  const g = document.createElement("div"); g.className = "ov-ghost"; g.innerHTML = "<b></b>"; th.appendChild(g);
  function ghost() { const w = parseFloat(($("#oS1") || {}).value), h = parseFloat(($("#oS2") || {}).value), c1 = ($("#oC1") || {}).value, c2 = ($("#oC2") || {}).value;
    if (!(w > 0 && h > 0)) { g.classList.remove("on"); return; } const R = th.getBoundingClientRect(), mx = Math.min(R.width * .7, 150), k = Math.min(mx / w, (R.height * .62) / h);
    g.style.width = (w * k) + "px"; g.style.height = (h * k) + "px"; g.style.marginLeft = -(w * k) / 2 + "px"; g.style.marginTop = -(h * k) / 2 + "px";
    g.querySelector("b").textContent = w + " × " + h + (c1 && c2 ? "  ·  col " + c1 + "-" + c2 : ""); g.classList.add("on"); }
  ["oS1", "oS2", "oC1", "oC2"].forEach((id) => { const e = document.getElementById(id); if (e) { e.addEventListener("input", ghost); e.addEventListener("change", ghost); } });
  setInterval(ghost, 1500); ghost();
})();
