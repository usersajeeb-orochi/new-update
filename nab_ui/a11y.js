// a11y.js - keeps the UI usable with a keyboard and a screen reader, and light on weak PCs.
// 1. every icon-only button and every unlabeled field gets a name (from its title or placeholder)
// 2. dialogs announce themselves, toasts are read out
// 3. animations pause when the window is hidden or minimised (saves CPU on slow PCs)
(function () {
  function name(el) {
    if (el.matches("button,[role=button],a")) {
      if (!el.getAttribute("aria-label") && !el.textContent.trim() && el.title) el.setAttribute("aria-label", el.title);
    } else if (el.matches("input:not([type=hidden]),select,textarea")) {
      const hasLabel = el.labels && el.labels.length, wrap = el.closest("label");
      if (!hasLabel && !wrap && !el.getAttribute("aria-label")) {
        const kv = el.closest(".kv"), kt = kv && kv.firstElementChild && kv.firstElementChild !== el ? kv.firstElementChild.textContent : "";
        const t = el.placeholder || el.title || kt || (el.previousElementSibling && el.previousElementSibling.tagName === "LABEL" ? el.previousElementSibling.textContent : "");
        if (t) el.setAttribute("aria-label", t.trim());
      }
    }
    if (el.classList && (el.classList.contains("modal") || el.classList.contains("modal-card")) && !el.getAttribute("role")) { el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); }
    if (el.classList && el.classList.contains("toast") && !el.getAttribute("role")) el.setAttribute("role", "status");
  }
  function scan(root) {
    if (!root || root.nodeType !== 1) return;
    name(root);
    root.querySelectorAll("button,[role=button],a,input,select,textarea,.modal,.modal-card,.toast").forEach(name);
  }
  let pend = new Set(), raf = 0;
  const obs = new MutationObserver(ms => { ms.forEach(m => m.addedNodes.forEach(n => n.nodeType === 1 && pend.add(n))); if (!raf) raf = requestAnimationFrame(() => { raf = 0; const p = pend; pend = new Set(); p.forEach(n => n.isConnected && scan(n)); }); });
  document.addEventListener("DOMContentLoaded", () => {
    scan(document.body); obs.observe(document.body, { childList: true, subtree: true });
    const tc = document.getElementById("toasts") || document.querySelector(".toasts"); if (tc) { tc.setAttribute("aria-live", "polite"); tc.setAttribute("role", "status"); }
  });
  document.addEventListener("visibilitychange", () => document.documentElement.classList.toggle("bg-hidden", document.hidden));
})();
