# nab_loading.py — a reusable "this is working on it" overlay for CTk windows
#
# WHY THIS EXISTS
# ----------------
# Several places in NAB do real work (a recursive folder scan, a Drive/Sheets
# round-trip, a page-by-page PDF build) and, until now, either blocked the Tk
# main thread while they did it — freezing the whole window — or ran on a
# background thread with NOTHING shown until it finished, which looks
# identical to "the app is frozen" from the operator's side. Both read as
# lag/buffering even when the work itself is fast.
#
# LoadingOverlay is the fix for the second case: a small animated panel you
# drop over any frame right before starting background work, and dismiss the
# moment it's done. It does no threading itself — it's purely visual — so the
# caller is still responsible for doing the actual work off the main thread.
#
# Usage:
#     ov = LoadingOverlay(some_frame, text="Scanning your clips…")
#     ov.show()
#     def _work():
#         result = slow_thing()
#         some_frame.after(0, lambda: [ov.hide(), render(result)])
#     threading.Thread(target=_work, daemon=True).start()
#
import itertools
import customtkinter as ctk

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class LoadingOverlay:
    """Semi-transparent panel that covers `parent` with a spinner + message.

    `parent` should be the frame whose content is being replaced/loaded —
    not necessarily the whole window — so the rest of the UI (a header, a
    Cancel button, nav tabs) can stay interactive while this shows.
    """

    def __init__(self, parent, text="Loading…", bg="#0A0A0A", fg="#F59E0B",
                 sub_fg="#666"):
        self.parent = parent
        self._frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
        self._spin_lbl = ctk.CTkLabel(
            self._frame, text=_SPINNER_FRAMES[0],
            font=ctk.CTkFont(family="Consolas", size=28), text_color=fg)
        self._spin_lbl.pack(pady=(0, 6))
        self._text_lbl = ctk.CTkLabel(
            self._frame, text=text, font=ctk.CTkFont(size=13),
            text_color=fg)
        self._text_lbl.pack()
        self._sub_lbl = ctk.CTkLabel(
            self._frame, text="", font=ctk.CTkFont(size=11),
            text_color=sub_fg)
        self._sub_lbl.pack(pady=(4, 0))

        self._cycle = itertools.cycle(_SPINNER_FRAMES)
        self._job = None
        self._visible = False

    def show(self, text=None, sub=""):
        if text is not None:
            self._text_lbl.configure(text=text)
        self._sub_lbl.configure(text=sub)
        if not self._visible:
            self._visible = True
            self._frame.place(relx=0.5, rely=0.5, anchor="center",
                              relwidth=1, relheight=1)
            self._frame.lift()
            self._animate()

    def set_text(self, text=None, sub=None):
        """Update the message on an already-visible overlay (e.g. progress:
        "Scanning… 40/120 folders")."""
        if text is not None:
            self._text_lbl.configure(text=text)
        if sub is not None:
            self._sub_lbl.configure(text=sub)

    def hide(self):
        self._visible = False
        if self._job:
            try:
                self.parent.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        try:
            self._frame.place_forget()
        except Exception:
            pass

    def _animate(self):
        if not self._visible:
            return
        try:
            if not self._frame.winfo_exists():
                return
            self._spin_lbl.configure(text=next(self._cycle))
            self._job = self.parent.after(90, self._animate)
        except Exception:
            pass

    def destroy(self):
        self.hide()
        try:
            self._frame.destroy()
        except Exception:
            pass
