# nab_tabreader.py — read the REAL URL of the foreground browser tab.
#
# Two sources, best first:
#   1. The NAB Tab Reporter browser extension pushes {url,title} over the
#      existing local WebSocket (see nab_server.NABPreviewServer.tab_info).
#   2. Fallback: Windows UI Automation reads the address bar of the
#      foreground Chrome/Edge/Brave/Firefox window. Needs `pip install
#      uiautomation`; if it's missing or the browser changed its layout this
#      silently returns "" and detection carries on exactly as before.
import re
import logging

_BROWSER_HINTS = ("chrome", "edge", "brave", "firefox", "opera", "vivaldi")
_uia = None
_uia_failed = False


def _load_uia():
    global _uia, _uia_failed
    if _uia is not None or _uia_failed:
        return _uia
    try:
        import uiautomation as auto
        _uia = auto
    except Exception:
        _uia_failed = True
    return _uia


def looks_like_browser(title):
    t = (title or "").lower()
    return any(h in t for h in _BROWSER_HINTS)


def _clean_url(text):
    text = (text or "").strip()
    if not text or " " in text:
        return ""
    if re.match(r"^[a-z][a-z0-9+.\-]*://", text, re.I):
        return text
    if re.match(r"^[\w\-]+(\.[\w\-]+)+(/.*)?$", text):
        return "https://" + text
    return ""


def read_address_bar(hwnd, budget_s=0.4):
    """Best-effort URL of the browser window `hwnd`. Never raises."""
    auto = _load_uia()
    if not auto or not hwnd:
        return ""
    try:
        with auto.UIAutomationInitializerInThread():
            win = auto.ControlFromHandle(hwnd)
            if not win:
                return ""
            auto.SetGlobalSearchTimeout(budget_s)
            # Chromium: an Edit control named "Address and search bar";
            # Firefox: "Search with ... or enter address". Take the first
            # Edit whose value parses as a URL.
            for name_hint in ("Address and search bar", "Address", "address", ""):
                try:
                    ed = win.EditControl(searchDepth=12, SubName=name_hint) if name_hint \
                        else win.EditControl(searchDepth=12)
                    if ed and ed.Exists(0, 0):
                        pat = ed.GetValuePattern()
                        u = _clean_url(pat.Value if pat else "")
                        if u:
                            return u
                except Exception:
                    continue
    except Exception as e:
        logging.debug(f"nab_tabreader: {e}")
    return ""
