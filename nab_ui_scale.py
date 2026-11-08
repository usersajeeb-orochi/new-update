# nab_ui_scale.py — DPI awareness + window fitting for mixed-resolution PCs
#
# WHY THIS EXISTS
# ---------------
# Every NAB window used a hardcoded pixel size (1400x950 main, 1450x900
# surgical, 980x740 tracker, 900x750 PDF settings...). Those numbers were
# picked on a 1920x1080 monitor. On a 1366x768 newsroom PC:
#   • the window is taller than the screen, so the bottom toolbar / Submit
#     button / Save button sits below the taskbar and is unreachable
#   • minsize() was ALSO hardcoded, so the user can't even resize it smaller
#   • Windows DPI virtualisation blurs the whole app at 125%/150% scaling
#
# This module fixes all three:
#   enable_dpi_awareness()  — call ONCE before any Tk root exists
#   apply_ctk_scaling(win)  — shrink all CustomTkinter widgets to fit
#   fit(win, w, h, ...)     — clamp a desired size to the real work area
#
import sys
import logging

# The resolution NAB's layouts were originally designed against.
BASE_W, BASE_H = 1600, 900

# Never shrink widgets below this — past it text becomes unreadable and
# it's better to let the window scroll/clip.
MIN_SCALE = 0.68

_cached_scale = None
_dpi_done = False


def enable_dpi_awareness():
    """Tell Windows we handle DPI ourselves, so it stops bitmap-stretching
    the app at 125%/150% display scaling (which is what makes NAB look
    blurry on laptops). MUST be called before the first Tk() / CTk() is
    created — NAB_entry.pyw calls it at the top of __main__."""
    global _dpi_done
    if _dpi_done or sys.platform != "win32":
        return
    _dpi_done = True
    try:
        import ctypes
        try:
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE (Win 8.1+). Matters when a
            # laptop is docked to an external monitor at a different DPI.
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            # Vista..Win8 fallback — system-wide awareness only.
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception as e:
        logging.error(f"enable_dpi_awareness: {e}")


def work_area(win=None):
    """Usable desktop rectangle as (x, y, w, h) — EXCLUDES the taskbar.

    winfo_screenheight() includes the taskbar, which is exactly why windows
    sized from it end up with their bottom row of buttons hidden."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                          ctypes.byref(rect), 0):
                return (rect.left, rect.top,
                        rect.right - rect.left, rect.bottom - rect.top)
        except Exception:
            pass
    # Cross-platform fallback: subtract a conservative taskbar allowance.
    if win is not None:
        try:
            return (0, 0, win.winfo_screenwidth(), win.winfo_screenheight() - 56)
        except Exception:
            pass
    return (0, 0, 1366, 712)


def ui_scale(win=None):
    """Widget scale factor for this machine's screen (MIN_SCALE .. 1.0).

    Computed once per process and cached — a mid-session change would
    require rebuilding every widget anyway."""
    global _cached_scale
    if _cached_scale is None:
        _, _, w, h = work_area(win)
        _cached_scale = max(MIN_SCALE, min(1.0, min(w / BASE_W, h / BASE_H)))
    return _cached_scale


def apply_ctk_scaling(ctk, win=None):
    """Shrink CustomTkinter widgets/fonts to fit this screen.

    Widget scaling only — window scaling is deliberately left at 1.0 so that
    geometry strings passed to fit() mean literal pixels. Otherwise CTk would
    multiply our already-clamped size a second time and shrink windows twice.
    """
    s = ui_scale(win)
    try:
        ctk.set_widget_scaling(s)
        ctk.set_window_scaling(1.0)
    except Exception as e:
        logging.error(f"apply_ctk_scaling: {e}")
    return s


def fit(win, w, h, min_w=None, min_h=None, center=True, parent=None,
        maximize_if_tight=False):
    """Size and place a window so it always fits on screen.

    w/h are the DESIRED size at 1600x900. They get clamped to the real work
    area. min_w/min_h are also clamped, so a small screen can never end up
    with a minsize larger than the screen itself (the original bug that made
    the tracker unresizable on 1366x768).

    maximize_if_tight: for the main window — if the desired size doesn't fit,
    just maximise instead of showing a shrunken floating window.
    """
    try:
        ax, ay, aw, ah = work_area(win)

        # Leave a small breathing margin so the border/shadow isn't clipped.
        max_w = max(360, aw - 16)
        max_h = max(280, ah - 16)

        fw = int(min(w, max_w))
        fh = int(min(h, max_h))

        if min_w or min_h:
            win.minsize(int(min(min_w or 0, fw)), int(min(min_h or 0, fh)))

        if maximize_if_tight and (w > max_w or h > max_h):
            win.geometry(f"{max_w}x{max_h}+{ax}+{ay}")
            try:
                win.state("zoomed")          # Windows "maximised"
            except Exception:
                try:
                    win.attributes("-zoomed", True)   # X11
                except Exception:
                    pass
            return fw, fh

        if center:
            if parent is not None:
                try:
                    parent.update_idletasks()
                    x = parent.winfo_rootx() + (parent.winfo_width() - fw) // 2
                    y = parent.winfo_rooty() + (parent.winfo_height() - fh) // 3
                    # Keep it on screen even if the parent is half off-screen.
                    x = max(ax, min(x, ax + aw - fw))
                    y = max(ay, min(y, ay + ah - fh))
                except Exception:
                    x = ax + (aw - fw) // 2
                    y = ay + (ah - fh) // 3
            else:
                x = ax + (aw - fw) // 2
                y = ay + (ah - fh) // 3
            win.geometry(f"{fw}x{fh}+{int(x)}+{int(y)}")
        else:
            win.geometry(f"{fw}x{fh}")

        return fw, fh
    except Exception as e:
        logging.error(f"nab_ui_scale.fit: {e}")
        try:
            win.geometry(f"{int(w)}x{int(h)}")
        except Exception:
            pass
        return int(w), int(h)


def scaled_font(size, win=None):
    """Point size adjusted for this screen — for raw tk widgets, which
    CustomTkinter's widget scaling does NOT touch."""
    return max(7, int(round(size * ui_scale(win))))
