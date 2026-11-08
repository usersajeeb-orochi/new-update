# nab_winutil.py — tiny Win32 helpers (no-ops elsewhere): window lookup, minimized test, foreground, global hotkey.
import sys
import threading
import logging

IS_WIN = sys.platform.startswith("win")
if IS_WIN:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

MOD = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def find_window(title):
    if not IS_WIN:
        return 0
    h = user32.FindWindowW(None, title) or 0
    if h:
        return h
    # Edge --app mode (and some shells) append text to the title → prefix search over top-level windows
    found = []
    try:
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hw, _lp):
            if user32.IsWindowVisible(hw) or user32.IsIconic(hw):
                t = window_title(hw)
                if t == title or t.startswith(title + " -") or t.startswith(title + " \u2013"):
                    found.append(hw)
                    return False
            return True
        user32.EnumWindows(proto(cb), 0)
    except Exception:
        pass
    return found[0] if found else 0


def is_iconic(hwnd):
    return bool(IS_WIN and hwnd and user32.IsIconic(hwnd))


def is_visible(hwnd):
    return bool(IS_WIN and hwnd and user32.IsWindowVisible(hwnd))


def show_window(hwnd, show):
    """Hide / show a window natively and without waiting for it (ShowWindowAsync never blocks on a busy window)."""
    if not IS_WIN or not hwnd:
        return False
    try:
        user32.ShowWindowAsync(hwnd, 8 if show else 0)     # SW_SHOWNA (no focus steal) / SW_HIDE
        return True
    except Exception:
        return False


def foreground():
    return user32.GetForegroundWindow() if IS_WIN else 0


def window_title(hwnd):
    if not IS_WIN or not hwnd:
        return ""
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def activate(hwnd):
    """Bring hwnd to front even when we are in the background (AttachThreadInput trick)."""
    if not IS_WIN or not hwnd:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        fg = user32.GetForegroundWindow()
        cur = kernel32.GetCurrentThreadId()
        fgt = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = False
        if fgt and fgt != cur:
            attached = bool(user32.AttachThreadInput(cur, fgt, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(cur, fgt, False)
        return True
    except Exception as e:
        logging.error(f"activate: {e}")
        return False


def parse_hotkey(s):
    """'Ctrl+Alt+N' -> (modifiers, vk) or None."""
    try:
        parts = [p.strip().lower() for p in (s or "").split("+") if p.strip()]
        mods, key = 0, None
        for p in parts:
            if p in MOD:
                mods |= MOD[p]
            else:
                key = p
        if not key or not mods:
            return None
        if len(key) == 1:
            vk = ord(key.upper())
        elif key.startswith("f") and key[1:].isdigit():
            vk = 0x6F + int(key[1:])
        else:
            return None
        return mods, vk
    except Exception:
        return None


def run_hotkey(spec, callback, stop):
    """Blocking: registers the hotkey on THIS thread and pumps messages until stop.is_set()."""
    if not IS_WIN:
        return False
    hk = parse_hotkey(spec)
    if not hk:
        return False
    if not user32.RegisterHotKey(None, 1, hk[0] | 0x4000, hk[1]):  # MOD_NOREPEAT
        logging.warning("global hotkey already taken: " + spec)
        return False
    msg = wintypes.MSG()
    try:
        while not stop.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0312:  # WM_HOTKEY
                    try:
                        callback()
                    except Exception as e:
                        logging.error(f"hotkey cb: {e}")
            else:
                stop.wait(0.05)
    finally:
        user32.UnregisterHotKey(None, 1)
    return True


def screen_size():
    if not IS_WIN:
        return 1366, 768
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def window_rect(hwnd):
    if not IS_WIN or not hwnd:
        return None
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


def place_topmost(hwnd, x=None, y=None, w=None, h=None, tool=True):
    """Always-on-top, no taskbar button, optionally moved/resized (physical pixels)."""
    if not IS_WIN or not hwnd:
        return False
    try:
        if tool:
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
        flags = 0x10 | (0x2 if x is None else 0) | (0x1 if w is None else 0)  # NOACTIVATE | NOMOVE | NOSIZE
        rc = window_rect(hwnd) or (0, 0, 300, 440)
        user32.SetWindowPos(hwnd, -1, int(x if x is not None else rc[0]), int(y if y is not None else rc[1]),
                            int(w if w is not None else rc[2] - rc[0]), int(h if h is not None else rc[3] - rc[1]), flags)
        return True
    except Exception as e:
        logging.error(f"place_topmost: {e}")
        return False


def flash_window(hwnd, count=4):
    """Blink the taskbar button (missed-save guard)."""
    if not IS_WIN or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
    fi = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 3 | 12, count, 0)   # FLASHW_ALL | FLASHW_TIMERNOFG
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
    return True


def set_alpha(hwnd, pct):
    """Whole-window opacity 20..100 % (overlay opacity option)."""
    if not IS_WIN or not hwnd:
        return False
    import ctypes
    u = ctypes.windll.user32
    GWL_EXSTYLE, WS_EX_LAYERED = -20, 0x80000
    st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if pct >= 100:
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, st & ~WS_EX_LAYERED)
        return True
    u.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_LAYERED)
    return bool(u.SetLayeredWindowAttributes(hwnd, 0, int(255 * max(20, pct) / 100), 2))   # LWA_ALPHA


def work_area():
    """(left, top, right, bottom) of the primary monitor's usable area (snap-to-edge)."""
    if not IS_WIN:
        return (0, 0, 1920, 1040)
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)   # SPI_GETWORKAREA
    return (r.left, r.top, r.right, r.bottom)


def cursor_pos():
    if not IS_WIN:
        return 0, 0
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def lbutton_down():
    return bool(IS_WIN and (user32.GetAsyncKeyState(0x01) & 0x8000))


def move_resize(hwnd, x, y, w, h):
    """Move/resize keeping topmost, without activating (overlay drag + resize)."""
    if not IS_WIN or not hwnd:
        return False
    return bool(user32.SetWindowPos(hwnd, -1, int(x), int(y), int(w), int(h), 0x10 | 0x4))   # NOACTIVATE | NOZORDER-ignored


def dpi_scale(hwnd):
    try:
        return max(1.0, user32.GetDpiForWindow(hwnd) / 96.0)
    except Exception:
        return 1.0


MAIN_HWND = 0


def theme_titlebar(hwnd, bg_hex):
    """Dark theme -> black title bar, light theme -> white title bar (Windows 10 / 11). On Windows 11 the bar also takes the theme colour."""
    import logging
    hwnd = hwnd or MAIN_HWND
    if not IS_WIN or not hwnd:
        return False
    try:
        h = str(bg_hex).strip().lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        dark = (0.299 * r + 0.587 * g + 0.114 * b) < 140
        dwm = ctypes.windll.dwmapi
        def put(attr, val):
            v = ctypes.c_int(val)
            return dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), ctypes.c_uint(attr), ctypes.byref(v), ctypes.c_uint(4))
        res = put(20, 1 if dark else 0)          # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 build 18985+ and 11)
        if res != 0:
            res = put(19, 1 if dark else 0)      # same flag on early Windows 10 20H1 builds
        col = r | (g << 8) | (b << 16)
        put(35, col)                             # caption colour, Windows 11 only (ignored on Windows 10)
        put(34, col)                             # border colour, Windows 11 only
        put(36, 0xF4F0EE if dark else 0x201A16)  # caption text, Windows 11 only
        try:                                     # Windows 10 only repaints the bar after a non-client refresh
            user32.SendMessageW(wintypes.HWND(hwnd), 0x86, 0, 0)     # WM_NCACTIVATE off
            user32.SendMessageW(wintypes.HWND(hwnd), 0x86, 1, 0)     # WM_NCACTIVATE on
            user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010)
            user32.RedrawWindow(wintypes.HWND(hwnd), None, None, 0x0001 | 0x0004 | 0x0400 | 0x0100)
        except Exception:
            pass
        if res != 0:
            logging.error(f"titlebar: DwmSetWindowAttribute result {res:#x} (this Windows build may not support a dark title bar)")
        return res == 0
    except Exception as e:
        logging.error(f"titlebar: {e}")
        return False
