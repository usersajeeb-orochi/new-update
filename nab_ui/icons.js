/* icons.js — replaces emoji / symbol glyphs everywhere with crisp inline SVG icons (one consistent set).
   Runs once on load and then watches the page, so toasts, modals and tool pages are covered too. */
(function () {
  "use strict";
  const P = {   // 24x24 stroke paths
    scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
    news: '<path d="M4 5h13a1 1 0 0 1 1 1v13H6a2 2 0 0 1-2-2zM18 9h2v8a2 2 0 0 1-2 2"/><path d="M7 9h8M7 13h8M7 16h5"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    pencil: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    marquee: '<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3 2.5"/>',
    ellipse: '<ellipse cx="12" cy="12" rx="8.5" ry="7" stroke-dasharray="3 2.5"/>',
    lasso: '<path d="M7 17c-3-1-4-3-4-5 0-4 4-7 9-7s9 3 9 6-4 5-9 5c-1 0-2 0-3-.2"/><path d="M7 17c0 2 1 3 3 4"/>',
    wand: '<path d="m4 20 11-11M15 9l2-2M14 3v3M20 10h-3M19 5l-2 2M9 3v2M4 8h2"/>',
    swap: '<path d="M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7"/>',
    invert: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor"/>',
    move: '<path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    eraser: '<path d="m7 21-4-4a2 2 0 0 1 0-2.8L14 3.200a2 2 0 0 1 2.800 0l4 4a2 2 0 0 1 0 2.800L11 20.500H21M9 6.500l8.500 8.500"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    crop: '<path d="M6 2v14a2 2 0 0 0 2 2h14M18 22V8a2 2 0 0 0-2-2H2"/>',
    square: '<rect x="4" y="4" width="16" height="16" rx="2"/>',
    marker: '<path d="m9 11-5 5v4h4l5-5M9 11l6-6 5 5-6 6M9 11l4 4"/><path d="M3 21h7"/>',
    redact: '<rect x="4" y="4" width="16" height="16" rx="2" fill="currentColor"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.500a5.500 5.500 0 0 1 0 11H11"/>',
    redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.500a5.500 5.500 0 0 0 0 11H13"/>',
    reset: '<path d="M3 12a9 9 0 1 0 3-6.700L3 8"/><path d="M3 3v5h5"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pin: '<path d="M12 22s7-6.500 7-12a7 7 0 0 0-14 0c0 5.500 7 12 7 12z"/><circle cx="12" cy="10" r="2.500"/>',
    windows: '<rect x="3" y="5" width="14" height="12" rx="2"/><rect x="11" y="10" width="10" height="9" rx="2" fill="var(--surf2,#1b1e2f)"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    columns: '<rect x="3" y="4" width="8" height="16" rx="1.500"/><rect x="13" y="4" width="8" height="16" rx="1.500"/>',
    trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/>',
    arrowsH: '<path d="m7 8-4 4 4 4M17 8l4 4-4 4M3 12h18"/>',
    arrowsV: '<path d="m8 7 4-4 4 4M8 17l4 4 4-4M12 3v18"/>',
    link: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    check: '<path d="m4 12.500 5 5L20 6.500"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    checkc: '<circle cx="12" cy="12" r="9"/><path d="m8 12.500 3 3 5-6"/>',
    xc: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m5.600 5.600 12.800 12.800"/>',
    alert: '<path d="M10.300 3.900 1.800 18a2 2 0 0 0 1.700 3h17a2 2 0 0 0 1.700-3L13.700 3.900a2 2 0 0 0-3.400 0zM12 9v4M12 17h.01"/>',
    hourglass: '<path d="M6 2h12M6 22h12M7 2c0 5 3 6 5 10-2 4-5 5-5 10M17 2c0 5-3 6-5 10 2 4 5 5 5 10"/>',
    refresh: '<path d="M21 12a9 9 0 0 1-15.500 6.200L3 16M3 12a9 9 0 0 1 15.500-6.200L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
    up: '<path d="M12 19V5M5 12l7-7 7 7"/>', down: '<path d="M12 5v14M5 12l7 7 7-7"/>',
    right: '<path d="M5 12h14M12 5l7 7-7 7"/>', left: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    chevD: '<path d="m6 9 6 6 6-6"/>', chevL: '<path d="m15 6-6 6 6 6"/>', chevR: '<path d="m9 6 6 6-6 6"/>',
    cloud: '<path d="M7 18a5 5 0 1 1 1.500-9.800A6 6 0 0 1 20 11a3.500 3.500 0 0 1-1 7z"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.700 21a2 2 0 0 1-3.400 0"/>',
    horn: '<path d="M3 11v3a1 1 0 0 0 1 1h3l8 5V5L7 10H4a1 1 0 0 0-1 1zM19 9a4 4 0 0 1 0 6"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.900 4.900l1.400 1.400M17.700 17.700l1.400 1.400M2 12h2M20 12h2M4.900 19.100l1.400-1.400M17.700 6.300l1.400-1.400"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.500 9a2.500 2.500 0 1 1 3.500 2.300c-.7.400-1 1-1 1.700M12 17h.01"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.500"/><path d="m21 16-5-5-9 9"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    expand: '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    dot: '<circle cx="12" cy="12" r="8"/>',
    circle: '<circle cx="12" cy="12" r="8"/>'
  };
  const G = {   // glyph → icon
    "✂": "scissors", "📰": "news", "🗞": "news", "📄": "file", "📧": "mail", "✉": "mail", "📨": "mail", "🔎": "search", "🔍": "search", "🧾": "receipt", "⚙": "gear", "✎": "pencil", "✏": "pencil",
    "▭": "marquee", "◯": "ellipse", "➰": "lasso", "🪄": "wand", "⇋": "swap", "◐": "invert", "✥": "move", "🧽": "eraser", "⎘": "copy", "⛶": "crop", "▢": "square",
    "🖍": "marker", "■": "redact", "↶": "undo", "↩": "undo", "↷": "redo", "↺": "reset", "📂": "folder", "📁": "folder", "🕘": "clock", "📍": "pin", "🗗": "windows", "⇲": "expand",
    "👁": "eye", "⇆": "columns", "🗑": "trash", "↔": "arrowsH", "⇅": "arrowsV", "🔗": "link", "✓": "check", "✔": "check", "✕": "x", "✗": "x", "✖": "x",
    "✅": "checkc", "❌": "xc", "⛔": "ban", "⚠": "alert", "⏳": "hourglass", "🔄": "refresh", "⬆": "up", "↑": "up", "⬇": "down", "↓": "down", "👉": "right",
    "◀": "chevL", "▶": "chevR", "▾": "chevD", "☁": "cloud", "🔐": "lock", "⏸": "pause", "⏹": "stop", "⏰": "bell", "📣": "horn", "🏖": "sun", "❓": "help",
    "🖼": "image", "📤": "upload", "☰": "menu", "⬜": "circle"
  };
  const RE = new RegExp("(" + Object.keys(G).map(k => k).join("|") + ")[\\uFE0E\\uFE0F]?", "g");
  const TEST = new RegExp(Object.keys(G).join("|") + "|[\\uFE0E\\uFE0F]");
  const svg = (n) => '<svg class="ic ic-' + n + '" viewBox="0 0 24 24" aria-hidden="true">' + (P[n] || P.dot) + "</svg>";
  const SKIP = /^(SCRIPT|STYLE|SVG|TEXTAREA|OPTION|INPUT|SELECT|TITLE)$/;
  function fixNode(tn) {
    const p = tn.parentNode; if (!p || SKIP.test(p.nodeName) || (p.closest && p.closest("#rk,svg"))) return;
    const s = tn.nodeValue; if (!TEST.test(s)) return;
    if (p.nodeName === "OPTION" || p.nodeName === "TEXTAREA") return;
    const frag = document.createDocumentFragment(); let last = 0, m; RE.lastIndex = 0;
    while ((m = RE.exec(s))) {
      if (m.index > last) frag.appendChild(document.createTextNode(s.slice(last, m.index)));
      const t = document.createElement("template"); t.innerHTML = svg(G[m[1]]); frag.appendChild(t.content.firstChild); last = m.index + m[0].length;
    }
    if (last < s.length) frag.appendChild(document.createTextNode(s.slice(last)));
    p.replaceChild(frag, tn);
  }
  const strip = (s) => s.replace(RE, "").replace(/\s{2,}/g, " ").replace(/\(\s*\)/g, "").trim();
  function scan(root) {
    if (!root) return;
    if (root.nodeType === 3) return fixNode(root);
    if (root.nodeType !== 1 || root.id === "rk" || SKIP.test(root.nodeName)) return;
    if (TEST.test(root.textContent || "")) {
      const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), list = []; let n;
      while ((n = w.nextNode())) if (TEST.test(n.nodeValue)) list.push(n);
      list.forEach(fixNode);
    }
    const els = root.querySelectorAll ? root.querySelectorAll("[title],[placeholder]") : [];
    const one = (e) => { ["title", "placeholder"].forEach(a => { const v = e.getAttribute(a); if (v && TEST.test(v)) e.setAttribute(a, strip(v)); }); };
    if (root.getAttribute) one(root); els.forEach(one);
    root.querySelectorAll && root.querySelectorAll("option").forEach(o => { if (TEST.test(o.textContent)) o.textContent = strip(o.textContent); });
  }
  let q = [], busy = false;
  const flush = () => { busy = false; const l = q; q = []; l.forEach(scan); };
  function init() {
    scan(document.body);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === "characterData") q.push(m.target); else m.addedNodes.forEach(n => q.push(n));
      }
      if (!busy && q.length) { busy = true; requestAnimationFrame(flush); }
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  window.ICONS = { svg, scan };
  const css = document.createElement("style");
  css.textContent = `.ic{width:1.15em;height:1.15em;vertical-align:-.2em;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none;pointer-events:none}
.rb span .ic{width:22px;height:22px}.tb .ic,.mini .ic{width:17px;height:17px}.icon-btn .ic{width:18px;height:18px}.mini .ic{width:14px;height:14px}
.empty-ic .ic{width:54px;height:54px;stroke-width:1.5}.big .ic{width:56px;height:56px;stroke-width:1.6}.fr-ic .ic{width:22px;height:22px}
.ic-checkc{color:#22c55e}.ic-xc,.ic-ban{color:#ef4444}.ic-alert{color:#f5a623}.btn .ic,.pill .ic{margin-right:5px}
.car .ic{width:11px;height:11px;stroke-width:2.6}.fold .ic{width:11px;height:11px;stroke-width:2.6}`;
  document.head.appendChild(css);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
