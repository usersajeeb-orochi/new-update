# nab_bubble.py — _BubbleStatusProxy (animated status notification)
class _BubbleStatusProxy:
    """Proxy for self.status_label — routes configure() calls to the
    bubble notification widget in the top-right corner of the canvas.

    Colour → dot + bar colour mapping:
      C_ACCENT  (#F59E0B)  → amber  — processing / working
      C_SUCCESS (#22C55E)  → green  — completed / ready
      C_DANGER  (#EF4444)  → red    — error / failed
      default               → grey   — idle / info
    """

    # NOTE: these keys must match the actual values in nab_constants.py.
    # They didn't: C_SUCCESS is #10B981 and C_DANGER is #D32F2F, neither of
    # which was in this map, so every "completed" and "error" bubble fell
    # through to the grey/blue default. Both are now mapped.
    _COLOUR_MAP = {
        "#F59E0B": ("#F59E0B", "#F59E0B"),   # amber accent  (C_ACCENT)
        "#10B981": ("#22C55E", "#22C55E"),   # green success (C_SUCCESS)
        "#D32F2F": ("#EF4444", "#EF4444"),   # red danger    (C_DANGER)
        "#22C55E": ("#22C55E", "#22C55E"),   # green success
        "#EF4444": ("#EF4444", "#EF4444"),   # red danger
        "#EF5350": ("#EF4444", "#EF4444"),   # red variant
        "#43A047": ("#22C55E", "#22C55E"),   # green variant
        "#8E24AA": ("#A855F7", "#A855F7"),   # purple note
        "#888":    ("#6B7280", "#374151"),   # grey dim
        "#555":    ("#6B7280", "#374151"),   # grey dimmer
        "default": ("#6B7280", "#3B82F6"),   # grey dot, blue bar
    }

    # Status text → progress bar value (0-1). None = hide bar.
    _PROGRESS_MAP = {
        "PROCESSING...":    (0.0, True,  True),   # (value, animate, show_bar)
        "POLISHING...":     (0.0, True,  True),
        "PARALLEL SAVING...": (0.0, True, True),
        "QUICK SAVING...":  (0.0, True,  True),
        "AUTO-SAVING...":   (0.0, True,  True),
        "UPSCALING…":       (0.0, True,  True),
        "CLEANING LINES...": (0.0, True, True),
        "PASTED!":          (1.0, False, True),
        "COMPLETED!":       (1.0, False, True),
        "UPSCALED 2x":      (1.0, False, True),
        "POLISHED!":        (1.0, False, True),
        "LINES CLEANED":    (1.0, False, True),
        "READY":            (0.0, False, False),   # hide everything
    }

    def __init__(self, master):
        self._app = master

    def configure(self, text=None, text_color=None, **kw):
        if text is None:
            return
        app = self._app
        try:
            self._update_bubble(app, text, text_color or "default")
        except Exception as e:
            import logging
            logging.error(f"BubbleStatusProxy: {e}")

    def _update_bubble(self, app, text, color_key):
        # Cancel any pending hide job
        if app._bubble_job:
            app.after_cancel(app._bubble_job)
            app._bubble_job = None

        # Resolve dot + bar colours
        dot_clr, bar_clr = self._COLOUR_MAP.get(
            color_key, self._COLOUR_MAP["default"])

        # Look up progress state
        prog_entry = None
        for k, v in self._PROGRESS_MAP.items():
            if text.startswith(k.rstrip("!")):
                prog_entry = v
                break

        if prog_entry is None:
            # Unknown status — treat as info
            prog_entry = (0.0, False, False)

        val, animate, show_bar = prog_entry

        # READY = hide bubble entirely
        if text.strip().upper() == "READY":
            app._bubble_frame.place_forget()
            app._bubble_bar.stop() if hasattr(app._bubble_bar, 'stop') else None
            return

        # Show bubble
        app._bubble_frame.place(relx=0.99, rely=0.02, anchor="ne")
        app._bubble_frame.lift()

        # Update dot colour + text
        app._bubble_dot.configure(text_color=dot_clr)
        app._bubble_text.configure(text=text, text_color="#F9FAFB")

        # Progress bar
        if show_bar:
            app._bubble_bar.pack(fill="x", padx=10, pady=(0, 8))
            app._bubble_bar.configure(progress_color=bar_clr)
            if animate:
                # Indeterminate animation using repeated small increments
                app._bubble_bar.set(0)
                self._animate(app, 0.0, bar_clr)
            else:
                app._bubble_bar.set(val)
                # Auto-hide after 2s on completion states
                app._bubble_job = app.after(2200, lambda: app._bubble_frame.place_forget())
        else:
            app._bubble_bar.pack_forget()

    def _animate(self, app, pos, clr):
        """Smooth looping progress bar animation for indeterminate states."""
        try:
            if not app._bubble_frame.winfo_viewable():
                return
            pos = (pos + 0.014) % 1.05
            app._bubble_bar.set(min(pos, 1.0))
            app._bubble_job = app.after(28, lambda: self._animate(app, pos, clr))
        except Exception:
            pass

    # Tkinter compat methods
    def cget(self, key):
        if key == "text":
            try: return self._app._bubble_text.cget("text")
            except Exception: return ""
        return ""

    def winfo_exists(self):
        return True

    def place(self, **kw): pass
    def pack(self, **kw): pass
    def grid(self, **kw): pass
    def place_forget(self): pass


