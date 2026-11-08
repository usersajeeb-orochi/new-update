// Sends the active tab's URL/title to NAB on 127.0.0.1:6789. Nothing leaves the PC.
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
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  report(tab);
}
chrome.tabs.onActivated.addListener(reportActive);
chrome.tabs.onUpdated.addListener((id, info, tab) => { if (tab.active) report(tab); });
chrome.windows.onFocusChanged.addListener(reportActive);
// MV3 service workers sleep; this alarm wakes it every 30s to keep reporting.
chrome.alarms && chrome.alarms.create("nab", { periodInMinutes: 0.5 });
chrome.alarms && chrome.alarms.onAlarm.addListener(reportActive);
setInterval(() => { if (ws && ws.readyState === 1) reportActive(); else { connect(); } }, 3000);  // heartbeat keeps NAB's view fresh and reconnects
reportActive();
