// Sends the active tab's URL/title to NAB on 127.0.0.1:6789. Nothing leaves the PC.
// One file for every browser: Chrome, Edge, Brave, Opera, Vivaldi (service worker) and Firefox (event page).
const api = (typeof browser !== "undefined" && browser.tabs) ? browser : chrome;
let ws = null;
function connect() {
  try {
    ws = new WebSocket("ws://127.0.0.1:6789");
    ws.onclose = () => { ws = null; };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  } catch (e) { ws = null; }
}
function report(tab) {
  if (!tab || !tab.url || !/^https?:/.test(tab.url)) return;
  if (!ws || ws.readyState > 1) connect();
  const send = () => ws && ws.readyState === 1 &&
    ws.send(JSON.stringify({ type: "tab_info", url: tab.url, title: tab.title || "" }));
  if (ws && ws.readyState === 0) ws.addEventListener("open", send, { once: true }); else send();
}
async function reportActive() {
  try {
    const [tab] = await api.tabs.query({ active: true, lastFocusedWindow: true });
    report(tab);
  } catch (e) {}
}
api.tabs.onActivated.addListener(reportActive);
api.tabs.onUpdated.addListener((id, info, tab) => { if (tab.active) report(tab); });
api.windows.onFocusChanged.addListener(reportActive);
// Chromium service workers and Firefox event pages both sleep; this alarm wakes them to keep reporting.
try {
  if (api.alarms) { api.alarms.create("nab", { periodInMinutes: 0.5 }); api.alarms.onAlarm.addListener(reportActive); }
} catch (e) {}
setInterval(() => { if (ws && ws.readyState === 1) reportActive(); else { connect(); } }, 3000);  // heartbeat keeps NAB's view fresh and reconnects
reportActive();
