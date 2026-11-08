// common.js — API client, events, helpers shared by the main window and the overlay.
(function () {
  const TOKEN = window.NAB.token;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  async function api(name, args) {
    const r = await fetch("/api/" + name, { method: "POST", headers: { "X-NAB-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(args || {}) });
    if (!r.ok && r.status !== 404 && r.status !== 401) throw new Error("HTTP " + r.status);
    return r.json();
  }
  const url = (p) => p + (p.includes("?") ? "&" : "?") + "t=" + encodeURIComponent(TOKEN);

  // ---- live events (SSE, auto-reconnect) ------------------------------------
  const handlers = {};
  function on(type, fn) { (handlers[type] = handlers[type] || []).push(fn); }
  function connect() {
    const es = new EventSource(url("/events"));
    es.onmessage = (m) => { try { const ev = JSON.parse(m.data); (handlers[ev.type] || []).forEach(f => f(ev)); (handlers["*"] || []).forEach(f => f(ev)); } catch (e) { console.error(e); } };
    es.onerror = () => { es.close(); setTimeout(connect, 1200); };
  }

  // ---- hue per category root -------------------------------------------------
  const HUES = [212, 262, 330, 16, 158, 38, 190, 292];
  function catColor(root, roots) { const i = Math.max(0, (roots || []).indexOf(root)); return "hsl(" + HUES[i % HUES.length] + " 70% 52%)"; }

  // ---- Tk hotkey string <Control-Shift-v> -> matcher ------------------------
  function parseTk(s) {
    if (!s || s === "None" || s === "Unbound") return null;
    let m = s.replace(/^</, "").replace(/>$/, "").split("-");
    const o = { ctrl: false, shift: false, alt: false, key: "" };
    m.forEach((p, i) => {
      const l = p.toLowerCase();
      if (i < m.length - 1 && l === "control") o.ctrl = true;
      else if (i < m.length - 1 && l === "shift") o.shift = true;
      else if (i < m.length - 1 && (l === "alt" || l === "meta")) o.alt = true;
      else o.key = p;
    });
    const map = { Delete: "Delete", Up: "ArrowUp", Down: "ArrowDown", Left: "ArrowLeft", Right: "ArrowRight", Return: "Enter", Escape: "Escape", space: " " };
    o.key = map[o.key] || o.key;
    return o;
  }
  function matchTk(o, e) {
    if (!o) return false;
    if (!!o.ctrl !== (e.ctrlKey || e.metaKey)) return false;
    if (!!o.alt !== e.altKey) return false;
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (k !== (o.key.length === 1 ? o.key.toLowerCase() : o.key)) return false;
    if (o.shift && !e.shiftKey) return false;
    if (!o.shift && o.key.length > 1 && e.shiftKey) return false;
    return true;
  }
  // quick-save key: "1".."9" or "Ctrl+1"
  function qsKey(e) {
    if (e.altKey) return "";
    const k = e.key.length === 1 ? e.key : e.key;
    if (!/^[0-9a-zA-Z]$/.test(k) && !/^F\d+$/.test(k)) return "";
    return (e.ctrlKey || e.metaKey ? "Ctrl+" : "") + k;
  }

  // ---- one-line metadata parser (mirror of nab_meta.py; tested for parity) ---
  const SIZE = /^(\d+(?:\.\d+)?)[xX×*](\d+(?:\.\d+)?)$/, COLS = /^(\d+)[-–—](\d+)$/, PAGE = /^[A-Za-z0-9]{1,6}$/;
  const fmtNum = (s) => { const f = parseFloat(s); return Number.isInteger(f) ? String(f) : String(+f.toFixed(3)); };
  function parseMeta(line) {
    const out = { page: "", cols: "", size: "", errors: [], tokens: [], ok: false, missing: [] };
    const toks = (line || "").trim().split(/[\s,;]+/).filter(Boolean), seen = {};
    for (const t of toks) {
      let m;
      if ((m = SIZE.exec(t))) {
        const w = parseFloat(m[1]), h = parseFloat(m[2]);
        if (w <= 0 || h <= 0) { out.tokens.push({ t, kind: "size", ok: false }); out.errors.push("size " + t + ": must be above 0"); }
        else if (seen.size) { out.tokens.push({ t, kind: "size", ok: false }); out.errors.push("size given twice"); }
        else { out.size = fmtNum(m[1]) + "x" + fmtNum(m[2]); seen.size = 1; out.tokens.push({ t, kind: "size", ok: true }); }
        continue;
      }
      if ((m = COLS.exec(t))) {
        const a = +m[1], b = +m[2]; let msg = "";
        if (a < 1 || a > 8 || b < 1 || b > 8) msg = "columns are 1-8"; else if (a > b) msg = "first column must not be bigger than the second"; else if (seen.cols) msg = "columns given twice";
        if (msg) { out.tokens.push({ t, kind: "cols", ok: false, msg }); out.errors.push("columns " + t + ": " + msg); }
        else { out.cols = a + "-" + b; seen.cols = 1; out.tokens.push({ t, kind: "cols", ok: true }); }
        continue;
      }
      if (PAGE.test(t)) {
        if (seen.page) { out.tokens.push({ t, kind: "page", ok: false }); out.errors.push("page given twice"); }
        else { out.page = t; seen.page = 1; out.tokens.push({ t, kind: "page", ok: true }); }
        continue;
      }
      out.tokens.push({ t, kind: "bad", ok: false }); out.errors.push("'" + t + "': not a page, columns (1-3) or size (4x6)");
    }
    if (!out.page) out.missing.push("page"); if (!out.cols) out.missing.push("columns"); if (!out.size) out.missing.push("size");
    if (out.missing.length && toks.length && !out.errors.length) out.errors.push("still needed: " + out.missing.join(", "));
    out.ok = !out.errors.length && !out.missing.length;
    return out;
  }

  // ---- single metadata fields (Page / Position / Size boxes) ---------------------
  function normField(kind, v) {
    v = (v || "").trim();
    if (kind === "cols") { const d = v.replace(/[^0-9]/g, ""); if (/^[1-8][1-8]$/.test(d) && !/[-–—:.]/.test(v)) return d[0] + "-" + d[1]; return v.replace(/[\s,;–—:.]+/g, "-"); }
    if (kind === "size") return v.replace(/[\s*×Xx]+/g, "x").replace(/^x|x$/g, "");
    if (kind === "page") return v.replace(/\s+/g, "").toUpperCase();
    return v;
  }
  function fieldCheck(kind, v) {   // -> "" (empty) | "ok" | error message
    if (!v) return "";
    const m = parseMeta(v);
    if (m.tokens.length === 1 && m.tokens[0].kind === kind && m.tokens[0].ok) return "ok";
    const e = m.errors.filter(x => !/^still needed/.test(x))[0];
    return e || ("not a valid " + (kind === "cols" ? "position, e.g. 1-3" : kind === "size" ? "size, e.g. 4x6" : "page, e.g. B1"));
  }

  // ---- two single-digit boxes that behave like one "a-b" / "axb" field ------------------------------
  function pairField(a, b, sep, wrap, h) {
    h = h || {};
    const digits = (s) => (s || "").replace(/[^0-9]/g, "");
    const num = (s) => { s = (s || "").replace(/[^0-9.]/g, ""); const i = s.indexOf("."); return i < 0 ? s : s.slice(0, i + 1) + s.slice(i + 1).replace(/\./g, ""); };
    const obj = {
      a, b, wrap, classList: wrap.classList,
      get value() { const x = a.value, y = b.value; return x && y ? x + sep + y : x ? x + sep : y ? sep + y : ""; },
      set value(v) { const p = String(v || "").split(/[-xX×*]/); a.value = digits(p[0]).slice(0, 1); b.value = h.b2 ? num(p[1]).slice(0, 4) : digits(p[1]).slice(0, 1); },
      focus() { (a.value ? (b.value ? b : b) : a).focus(); (document.activeElement.select || (() => {})).call(document.activeElement); },
      focusFirst() { a.focus(); a.select(); },
      select() { }, blur() { a.blur(); b.blur(); }, addEventListener() { }
    };
    [a, b].forEach(el => { el.setAttribute("maxlength", el === b && h.b2 ? "4" : "2"); el.setAttribute("inputmode", "numeric"); el.setAttribute("autocomplete", "off"); el.addEventListener("focus", () => el.select()); });
    a.addEventListener("input", () => {
      const d = digits(a.value);
      if (d.length > 1) { a.value = d[0]; b.value = d[1]; } else a.value = d;
      h.change && h.change();
      if (a.value) { b.focus(); b.select(); if (b.value && d.length > 1) h.done && h.done(); }
    });
    b.addEventListener("input", () => {
      if (h.b2) { b.value = num(b.value).slice(0, 4); h.change && h.change(); return; }
      const d = digits(b.value); b.value = d.slice(-1);
      h.change && h.change();
      if (b.value) h.done && h.done();
    });
    const keys = (el, first) => el.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "Enter") { e.preventDefault(); h.enter && h.enter(); }
      else if (e.key === "Escape") { e.preventDefault(); h.esc && h.esc(); }
      else if (e.key === "Backspace" && !el.value) { e.preventDefault(); if (first) h.prev && h.prev(); else { a.focus(); a.select(); } }
      else if (first && /^[-xX*×,.\s]$/.test(e.key) && !(h.b2 && e.key === "." )) { e.preventDefault(); if (a.value) { b.focus(); b.select(); } }
      else if (e.key.length === 1 && !(/[0-9]/.test(e.key) || (!first && h.b2 && e.key === "." && !el.value.includes(".")))) e.preventDefault();
    });
    keys(a, true); keys(b, false);
    wrap.addEventListener("focusout", (e) => { if (!wrap.contains(e.relatedTarget)) h.leave && h.leave(); });
    return obj;
  }
  // ---- toast -----------------------------------------------------------------
  function toast(text, kind, ms, action) {
    const box = $("#toasts"); if (!box) return;
    const d = document.createElement("div"); d.className = "toast " + (kind || "");
    d.innerHTML = "<span>" + esc(text) + "</span>";
    if (action) { const b = document.createElement("button"); b.textContent = action.label; b.onclick = () => { action.fn(); d.remove(); }; d.appendChild(b); }
    box.appendChild(d); while (box.children.length > 3) box.firstChild.remove();
    setTimeout(() => d.remove(), ms || 3500); return d;
  }

  // ---- modal -------------------------------------------------------------------
  function modal(html, bind) {
    const m = $("#modal"), c = $("#modalCard"); c.innerHTML = html; m.classList.remove("hidden");
    const close = () => m.classList.add("hidden");
    if (bind) bind(c, close);
    return close;
  }

  function theme(v) { v = ["light", "blue", "snow", "shadow", "neon"].includes(v) ? v : "dark"; document.documentElement.setAttribute("data-theme", v); document.documentElement.setAttribute("data-mode", (v === "light" || v === "snow") ? "light" : "dark"); setTimeout(titlebar, 60); setTimeout(titlebar, 1500); setTimeout(titlebar, 4000); }
  let tbLast = "";
  function titlebar() { try { let c = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(); if (/^#[0-9a-f]{3}$/i.test(c)) c = "#" + c.slice(1).split("").map(x => x + x).join(""); if (/^#[0-9a-f]{6}$/i.test(c)) { tbLast = c; api("titlebar", { bg: c }); } } catch (e) { } }
  function debounce(fn, ms) { let h; return function () { clearTimeout(h); const a = arguments; h = setTimeout(() => fn.apply(null, a), ms); }; }

  const clean = (p) => String(p || "").replace(/^[^\p{L}\p{N}]+/u, "").trim() || String(p || "");
  window.C = { clean, $, $$, esc, api, url, on, connect, catColor, parseTk, matchTk, qsKey, parseMeta, toast, modal, theme, normField, fieldCheck, pairField, debounce, TOKEN };
})();
