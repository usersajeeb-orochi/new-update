// mascot_ai.js — the character as an AI guide: right-click menu, chat panel, things she has learned.
(function () {
  if (!window.C || (window.NAB && window.NAB.role === "overlay")) return;
  const { $, esc, api, toast } = C;
  let hist = [], panel = null, menu = null, busy = false;
  const NAME = () => { const e = document.querySelector("#rkName"); return (e && e.textContent.replace(/\s*(·.*)?$/, "").trim()) || "Riko"; };
  const say = (t, f, ms) => { try { RIKO.core.say(t, f || "happy", ms); } catch (e) { } };
  const css = document.createElement("style");
  css.textContent = `
  .rkm{position:fixed;z-index:99998;min-width:210px;padding:6px;border-radius:14px;background:var(--surf);border:1px solid var(--line);box-shadow:0 18px 40px -14px rgba(0,0,0,.7);animation:fade .12s}
  .rkm b{display:block;padding:6px 10px 4px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
  .rkm button{display:flex;width:100%;align-items:center;gap:10px;padding:8px 10px;border-radius:9px;text-align:left;font-size:13px;color:var(--txt)}
  .rkm button:hover{background:var(--surf2)}.rkm hr{border:0;border-top:1px solid var(--line);margin:5px 4px}
  .rkc{position:fixed;z-index:99997;right:18px;bottom:46px;width:360px;max-width:calc(100vw - 24px);height:480px;max-height:calc(100vh - 80px);display:flex;flex-direction:column;border-radius:18px;background:var(--surf);border:1px solid var(--line);box-shadow:0 26px 60px -18px rgba(0,0,0,.75);overflow:hidden;animation:rkin .18s ease}
  @keyframes rkin{from{opacity:0;transform:translateY(10px) scale(.98)}to{opacity:1;transform:none}}
  .rkc header{display:flex;align-items:center;gap:10px;padding:12px 14px;background:var(--grad);color:#fff}.rkc header b{flex:1;font-size:14px}.rkc header button{color:#fff;opacity:.85;padding:2px 8px;border-radius:8px}.rkc header button:hover{background:rgba(255,255,255,.2)}
  .rkc .ms{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px;user-select:text}
  .rkc .m{max-width:86%;padding:8px 12px;border-radius:14px;font-size:13px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .rkc .m.a{align-self:flex-start;background:var(--surf2);border-bottom-left-radius:4px}.rkc .m.u{align-self:flex-end;background:var(--acc);color:#fff;border-bottom-right-radius:4px}
  .rkc .m.e{align-self:center;color:var(--warn);background:transparent;font-size:12px;text-align:center}.rkc .m.l{align-self:center;font-size:11px;color:var(--dim);background:transparent}
  .rkc .dots{display:inline-flex;gap:4px}.rkc .dots i{width:6px;height:6px;border-radius:50%;background:var(--dim);animation:rkd 1s infinite}.rkc .dots i:nth-child(2){animation-delay:.15s}.rkc .dots i:nth-child(3){animation-delay:.3s}@keyframes rkd{50%{opacity:.25;transform:translateY(-3px)}}
  .rkc .chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}.rkc .chips button{padding:5px 10px;border-radius:99px;background:var(--surf2);border:1px solid var(--line);font-size:12px;color:var(--dim)}.rkc .chips button:hover{color:var(--txt);border-color:var(--acc)}
  .rkc form{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}.rkc form input{flex:1;height:36px;padding:0 12px;border-radius:99px}.rkc form button{height:36px;padding:0 16px;border-radius:99px;background:var(--grad);color:#fff;font-weight:600}
  .rkn{max-height:300px;overflow:auto;display:flex;flex-direction:column;gap:6px;margin:8px 0}.rkn div{display:flex;gap:8px;align-items:center;padding:7px 10px;border-radius:9px;background:var(--surf2);font-size:13px}.rkn div span{flex:1}`;
  document.head.appendChild(css);

  function closeMenu() { if (menu) { menu.remove(); menu = null; } }
  function openMenu(x, y) {
    closeMenu(); menu = document.createElement("div"); menu.className = "rkm";
    const q = (() => { try { return RIKO.core.quiet; } catch (e) { return false; } })();
    const items = [["Chat with " + NAME(), () => chat()], ["Give me a tip", tip], ["How do I save a clip?", () => chat("How do I save a clip?")], ["What have you learned?", notes], null,
      ["Dance", () => { try { RIKO.core.dance(5); } catch (e) { } }], [q ? "Talk to me again" : "Be quiet for now", () => { try { RIKO.core.setQuiet(!q); say(q ? "I'm back!" : "Okay, quiet mode.", "happy", 1800); } catch (e) { } }], null,
      ["AI settings", () => { const b = document.querySelector('[data-view="settings"]'); b && b.click(); setTimeout(() => window.SETTINGS_GO && window.SETTINGS_GO("ai"), 150); }]];
    menu.innerHTML = `<b>${esc(NAME())}</b>`;
    items.forEach(it => { if (!it) { menu.appendChild(document.createElement("hr")); return; } const b = document.createElement("button"); b.textContent = it[0]; b.onclick = () => { closeMenu(); it[1](); }; menu.appendChild(b); });
    document.body.appendChild(menu);
    const r = menu.getBoundingClientRect(); menu.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + "px"; menu.style.top = Math.max(8, Math.min(y - r.height, innerHeight - r.height - 8)) + "px";
  }
  document.addEventListener("contextmenu", (e) => { if (e.target && e.target.id === "rkPet") { e.preventDefault(); e.stopPropagation(); openMenu(e.clientX, e.clientY); } }, true);
  document.addEventListener("pointerdown", (e) => { if (menu && !menu.contains(e.target)) closeMenu(); }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeMenu(); if (panel && document.activeElement && panel.contains(document.activeElement)) closePanel(); } });

  const add = (cls, t) => { const m = document.createElement("div"); m.className = "m " + cls; m.textContent = t; const ms = panel.querySelector(".ms"); ms.appendChild(m); ms.scrollTop = ms.scrollHeight; return m; };
  function closePanel() { if (panel) { panel.remove(); panel = null; } }
  function chat(first) {
    if (panel) { panel.querySelector("input").focus(); if (first) send(first); return; }
    panel = document.createElement("div"); panel.className = "rkc";
    panel.innerHTML = `<header><b>Chat with ${esc(NAME())}</b><button data-a="notes" title="What I learned">Notes</button><button data-a="clear" title="New chat">Clear</button><button data-a="x" title="Close">x</button></header><div class="ms"></div>
      <div class="chips">${["How do I save a clip?", "What do the shortcuts do?", "How does the PR calculator work?", "Why was my clip not saved?"].map(t => `<button>${esc(t)}</button>`).join("")}</div>
      <form><input placeholder="Ask me anything about NAB..." autocomplete="off"><button>Send</button></form>`;
    document.body.appendChild(panel);
    add("a", "Hi, I'm " + NAME() + ". Ask me how anything in NAB works, or tell me how you like to work and I'll remember it.");
    panel.querySelector('[data-a="x"]').onclick = closePanel; panel.querySelector('[data-a="notes"]').onclick = notes;
    panel.querySelector('[data-a="clear"]').onclick = () => { hist = []; panel.querySelector(".ms").innerHTML = ""; add("a", "Fresh start. What do you need?"); };
    panel.querySelectorAll(".chips button").forEach(b => b.onclick = () => send(b.textContent));
    panel.querySelector("form").onsubmit = (e) => { e.preventDefault(); const i = panel.querySelector("input"); const v = i.value.trim(); i.value = ""; if (v) send(v); };
    panel.querySelector("input").focus(); if (first) send(first);
  }
  async function send(text) {
    if (busy || !panel) return; busy = true; add("u", text);
    const w = add("a", ""); w.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>';
    const r = await api("ai_chat", { history: hist, text }).catch(() => ({ ok: false, error: "no connection" }));
    busy = false; if (!panel) return;
    if (!r.ok) { w.className = "m e"; w.textContent = r.error || "I could not answer right now."; return; }
    w.textContent = r.reply; hist.push({ role: "user", text }, { role: "assistant", text: r.reply }); hist = hist.slice(-12);
    if (r.confirm) {
      const bar = document.createElement("div"); bar.className = "chips";
      bar.innerHTML = `<button data-y="1">${esc(r.confirm.label)}</button><button data-y="0">Cancel</button>`;
      w.after(bar);
      bar.querySelectorAll("button").forEach(b => b.onclick = async () => {
        bar.remove(); const c = await api("ai_confirm", { id: r.confirm.id, yes: b.dataset.y === "1" }).catch(() => ({ ok: false, error: "no connection" }));
        add(c.ok ? "a" : "e", c.reply || c.error || "Done."); panel && (panel.querySelector(".ms").scrollTop = 1e6);
      });
    }
    if (r.learned) add("l", "Learned: " + r.learned);
    panel.querySelector(".ms").scrollTop = 1e6; say(r.reply.length > 110 ? r.reply.slice(0, 107) + "..." : r.reply, "happy", 4000);
  }
  async function tip() { const r = await api("ai_tip"); say(r.ok ? r.tip : (r.error || "No tip right now."), r.ok ? "excited" : "sleepy", 6000); }
  async function notes() {
    const r = await api("ai_notes"), L = r.notes || [];
    C.modal(`<h3>What ${esc(NAME())} has learned</h3><div class="rkn" id="rkN">${L.length ? L.map((n, i) => `<div><span>${esc(n.t)}</span><button class="mini" data-i="${i}" title="Forget">x</button></div>`).join("") : '<p class="sub">Nothing yet. Tell me how you work, or type: remember ...</p>'}</div>
      <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" id="rkClr">Forget all</button><button class="btn pri" id="rkOk">Close</button></div>`, (close) => {
      $("#rkOk").onclick = close; $("#rkClr").onclick = async () => { await api("ai_notes_clear"); close(); };
      document.querySelectorAll("#rkN [data-i]").forEach(b => b.onclick = async () => { await api("ai_note_del", { i: +b.dataset.i }); b.parentElement.remove(); });
    });
  }
  window.RIKO_CHAT = chat;
})();
