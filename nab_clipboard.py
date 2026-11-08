# nab_clipboard.py — Windows clipboard / foreground-window helpers, no Tk.
import os
import io
import time
import struct
import logging
import platform

from PIL import Image, ImageGrab, ImageOps

IS_WIN = platform.system() == "Windows"

try:
    import win32clipboard
    import win32gui
    HAS_WIN32 = True
except Exception:
    win32clipboard = None
    win32gui = None
    HAS_WIN32 = False


def _ct_foreground():
    try:
        import ctypes
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        n = u.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, b, n + 1)
        return h, b.value
    except Exception:
        return None, ""


def foreground():
    """(hwnd, window title) of the foreground window, or (None, "")."""
    if not HAS_WIN32:
        return _ct_foreground() if IS_WIN else (None, "")
    try:
        h = win32gui.GetForegroundWindow()
        return h, win32gui.GetWindowText(h)
    except Exception:
        return None, ""


_snap_cache = {"seq": None, "source_url": "", "text": ""}


def _ct_clip_bytes(fmt):
    """Raw bytes of clipboard format `fmt` via ctypes (no pywin32 needed). Caller must NOT have the clipboard open."""
    import ctypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.argtypes = [ctypes.c_void_p]
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.OpenClipboard.argtypes = [ctypes.c_void_p]
    if not u32.OpenClipboard(None):
        return b""
    try:
        h = u32.GetClipboardData(fmt)
        if not h:
            return b""
        p = k32.GlobalLock(h)
        if not p:
            return b""
        try:
            n = k32.GlobalSize(h)
            return ctypes.string_at(p, n) if n else b""
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def snapshot():
    """One look at the clipboard: sequence number, image present?, the SourceURL Chrome/Edge/Firefox attach
    to HTML copies, and plain text. Pure ctypes (works without pywin32). Never raises.
    {"seq","has_image","source_url","text"}"""
    out = {"seq": None, "has_image": False, "source_url": "", "text": ""}
    if not IS_WIN:
        return out
    try:
        import ctypes
        u = ctypes.windll.user32
        out["seq"] = int(u.GetClipboardSequenceNumber())
        png = u.RegisterClipboardFormatW("PNG")
        html = u.RegisterClipboardFormatW("HTML Format")
        out["has_image"] = any(u.IsClipboardFormatAvailable(f) for f in (8, 2, 17, png))
        # SourceURL / text only need re-reading when the clipboard changed
        if _snap_cache["seq"] != out["seq"]:
            su, tx = "", ""
            if u.IsClipboardFormatAvailable(html):
                data = _ct_clip_bytes(html).decode("utf-8", errors="ignore")
                for line in data.splitlines():
                    if line.startswith("SourceURL:"):
                        su = line.split(":", 1)[1].strip()
                        break
            if not su and u.IsClipboardFormatAvailable(13):   # CF_UNICODETEXT
                raw = _ct_clip_bytes(13)
                tx = raw.decode("utf-16-le", errors="ignore").split("\x00")[0][:2000]
            _snap_cache.update(seq=out["seq"], source_url=su, text=tx)
        out["source_url"], out["text"] = _snap_cache["source_url"], _snap_cache["text"]
    except Exception as e:
        logging.error(f"clipboard snapshot: {e}")
    return out


def clipboard_text():
    if not HAS_WIN32:
        return ""
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) or ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception:
        pass
    return ""


def _dib_to_image():
    """Windows DIB fallback (Snipping Tool / Print Screen)."""
    if not IS_WIN:
        return None
    try:
        import ctypes
        CF_DIB, CF_DIBV4 = 8, 17
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalSize.argtypes = [ctypes.c_void_p]
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        u32.GetClipboardData.restype = ctypes.c_void_p
        if not u32.OpenClipboard(None):
            return None
        try:
            h = u32.GetClipboardData(CF_DIBV4) or u32.GetClipboardData(CF_DIB)
            if not h:
                return None
            ptr = k32.GlobalLock(h)
            size = k32.GlobalSize(h)
            if not ptr or not size:
                return None
            data = (ctypes.c_char * size).from_address(ptr)[:]
            k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()
        if len(data) < 40:
            return None
        bih_size, width, height = struct.unpack_from("<Iii", data, 0)[:3]
        height = abs(height)
        extra = 0
        if bih_size == 40:
            bpp, compression = struct.unpack_from("<HI", data, 14)
            if compression == 3 and bpp in (16, 32):
                extra = 12
        buf = io.BytesIO()
        buf.write(b"BM")
        buf.write(struct.pack("<I", 14 + len(data)))
        buf.write(bytes(4))
        buf.write(struct.pack("<I", 14 + bih_size + extra))
        buf.write(data)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    except Exception as e:
        logging.error(f"clipboard DIB: {e}")
        return None


def grab_images():
    """Everything image-like on the clipboard → list of RGB PIL images.
    Handles pixel data, DIB (Snipping Tool), and copied files / file paths."""
    out = []
    try:
        got = ImageGrab.grabclipboard()
    except Exception:
        got = None
    if isinstance(got, Image.Image):
        return [got.convert("RGB")]
    if isinstance(got, list):
        for f in got:
            if os.path.isfile(f):
                try:
                    out.append(ImageOps.exif_transpose(Image.open(f)).convert("RGB"))
                except Exception:
                    continue
        if out:
            return out
    img = _dib_to_image()
    if img is not None:
        return [img]
    txt = clipboard_text().strip()
    if txt:
        lines = [l.strip().strip('"') for l in txt.splitlines() if l.strip()]
        for f in lines:
            if os.path.isfile(f):
                try:
                    out.append(ImageOps.exif_transpose(Image.open(f)).convert("RGB"))
                except Exception:
                    pass
    return out


def thumb_hash(img):
    t = img.copy()
    t.thumbnail((32, 32))
    return hash(t.tobytes())


def set_clipboard_image(img):
    """Put a PIL image on the Windows clipboard (as a DIB, so every app can paste it)."""
    if not IS_WIN:
        return False
    import ctypes
    from ctypes import wintypes
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    dib = buf.getvalue()[14:]
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    h = k32.GlobalAlloc(0x0042, len(dib))     # GMEM_MOVEABLE | GMEM_ZEROINIT
    if not h:
        return False
    p = k32.GlobalLock(h)
    ctypes.memmove(p, dib, len(dib))
    k32.GlobalUnlock(h)
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        u32.EmptyClipboard()
        return bool(u32.SetClipboardData(8, h))   # CF_DIB
    finally:
        u32.CloseClipboard()
