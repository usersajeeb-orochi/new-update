# nab_batch_ui.py — Batch Mode UI.
#
# ARCHITECTURE (rewritten from the first version — read this before editing)
# ----------------------------------------------------------------------------
# v1 gave Batch Mode its own separate canvas for capture, with an "Open in
# Full Editor" handoff button for anything needing the full toolbar. That
# was a deliberate risk-avoidance choice — but it's exactly what caused
# every bug reported after the first real test: a duplicate paper dropdown
# that didn't share state properly, no Auto Snatch, no full toolbar, a
# capture filmstrip with no click handlers, no live header preview.
# Splitting "the same canvas" into two different canvases guaranteed it
# would stop being the same canvas.
#
# v2 (this version) doesn't have a separate capture canvas at all. Capturing
# a clip just means using the Clip tab exactly as you always do — paste,
# Auto Snatch, full toolbar, everything unchanged, zero duplication. What
# Batch Mode actually adds is a slim STRIP injected into the Clip tab
# (_inject_batch_strip) that appears only while a batch session is active:
# live progress, a filmstrip of what's sealed so far, and the one new
# action — "Seal Clip" — which takes whatever's currently on the canvas
# (app.orig_images, unmodified — same state GENERATE already reads) and
# queues it, then clears the canvas for the next one.
#
# The "📦 Batch" tab itself is now just: the Start Batch / Start Entering
# Metadata launcher, a live mirror of the same status the strip shows (so
# switching tabs to check progress works too), and the Review view.
#
import os
import time
import logging
import datetime
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw, ImageFont, ImageTk, ImageGrab

import nab_batch
import nab_ui_scale


# ─────────────────────────────────────────────────────────────────────────
# RESUME ON LAUNCH
# ─────────────────────────────────────────────────────────────────────────
def check_resume_on_launch(app):
    try:
        found = nab_batch.BatchSession.find_resumable()
    except Exception as e:
        logging.error(f"check_resume_on_launch: {e}")
        return
    if not found:
        return
    session = nab_batch.BatchSession(found)
    stats = session.stats()
    if stats["total_clips"] == 0:
        session.discard()
        return

    def _resume():
        app._batch_session = session
        _inject_batch_strip(app)
        _update_batch_strip(app)
        _update_batch_badge(app)

    def _discard():
        if messagebox.askyesno(
                "Discard batch?",
                f"This will permanently delete {stats['total_clips']} "
                f"already-sealed clip(s) from the interrupted session. "
                f"This cannot be undone.\n\nDiscard?"):
            session.discard()

    app.after(1500, lambda: _ask_resume(app, stats, _resume, _discard))


def _ask_resume(app, stats, on_resume, on_discard):
    win = ctk.CTkToplevel(app)
    win.title("Resume batch session?")
    win.configure(fg_color="#08080E")
    nab_ui_scale.fit(win, 420, 260, min_w=280, min_h=200, parent=app)
    win.attributes("-topmost", True)
    win.grab_set()

    ctk.CTkLabel(win, text="📦 A batch session was interrupted",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="#F59E0B").pack(pady=(20, 6), padx=16)
    ctk.CTkLabel(win,
                text=f"{stats['total_clips']} clip(s) sealed before NAB "
                     f"closed unexpectedly ({stats['papers']} paper(s)).\n"
                     f"Nothing you'd already sealed was lost.",
                font=ctk.CTkFont(size=12), text_color="#AAA",
                wraplength=360, justify="center").pack(pady=6, padx=16)

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(pady=18)
    ctk.CTkButton(btns, text="▶ Resume", width=130, fg_color="#22C55E",
                 command=lambda: [win.destroy(), on_resume()]
                 ).pack(side="left", padx=6)
    ctk.CTkButton(btns, text="🗑 Discard", width=130, fg_color="#D32F2F",
                 command=lambda: [win.destroy(), on_discard()]
                 ).pack(side="left", padx=6)


# ─────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────
def _flatten_categories(app):
    out = []
    try:
        tree = app.cat_tree
        for root_id in tree.get_children(""):
            root_txt = tree.item(root_id)["text"]
            children = tree.get_children(root_id)
            if not children:
                out.append((root_txt, [root_txt]))
            for child_id in children:
                child_txt = tree.item(child_id)["text"]
                out.append((f"{root_txt} / {child_txt}", [root_txt, child_txt]))
    except Exception as e:
        logging.error(f"_flatten_categories: {e}")
    return out


def _selected_category_path(app):
    """Whatever's currently highlighted in the REAL category tree — same
    widget the Clip tab always uses, so there's no separate Batch category
    picker to fall out of sync."""
    try:
        sel = app.cat_tree.selection()
        if not sel:
            return []
        item = sel[0]
        parent = app.cat_tree.parent(item)
        if parent:
            return [app.cat_tree.item(parent)["text"], app.cat_tree.item(item)["text"]]
        return [app.cat_tree.item(item)["text"]]
    except Exception as e:
        logging.error(f"_selected_category_path: {e}")
        return []


def _load_paper_logo(app, paper, size=48):
    for d in (getattr(app, "logo_dir", None), getattr(app, "logo_dir_bundled", None)):
        if not d:
            continue
        p = os.path.join(d, f"{paper}.png")
        if os.path.exists(p):
            try:
                img = Image.open(p).convert("RGBA")
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(img)
            except Exception:
                pass
    return None


def _strip_emoji(app, name):
    return nab_batch.strip_emoji_prefix(name)


def _composite_final(images, paper, page, position, logo_scale, text_scale,
                     logo_dir, logo_dir_bundled):
    """Same formula as _build_full_page in nab_app.py (logo scale, header
    font size) — kept faithful so a batch-saved clip looks identical to one
    saved through the normal single-clip flow. Operates on a plain image
    list rather than the live canvas, since these images are already fully
    edited pixels by the time they're sealed."""
    total_w = max((im.width for im in images), default=400)
    total_h = sum(im.height for im in images)
    merged = Image.new("RGB", (total_w, total_h), "white")
    y = 0
    for im in images:
        merged.paste(im, ((total_w - im.width) // 2, y))
        y += im.height

    final_mw = max(merged.width, 400)
    lp = os.path.join(logo_dir, f"{paper}.png")
    if not os.path.exists(lp) and logo_dir_bundled:
        lp = os.path.join(logo_dir_bundled, f"{paper}.png")

    logo_img = None
    if os.path.exists(lp):
        try:
            temp_logo = Image.open(lp)
            tw = int(final_mw * logo_scale)
            th = int(temp_logo.height * (tw / temp_logo.width))
            logo_img = temp_logo.resize((tw, th), Image.Resampling.LANCZOS)
        except Exception:
            pass

    lh = logo_img.size[1] if logo_img else 40
    fs = max(12, int((final_mw * 0.03) * text_scale))
    hh = lh + fs + 25
    canvas = Image.new("RGB", (final_mw, merged.height + hh + 10), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    if logo_img:
        canvas.paste(logo_img, ((final_mw - logo_img.size[0]) // 2, 10))
    info = f"Page-{page}, Pos-{position}, Date-{datetime.datetime.now().strftime('%d-%m-%Y')}"
    try:
        font = ImageFont.truetype("arialbd.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    tw = draw.textbbox((0, 0), info, font=font)[2]
    draw.text(((final_mw - tw) // 2, lh + 12), info, fill="black", font=font)
    canvas.paste(merged, ((final_mw - merged.width) // 2, hh))
    return canvas, (lp if os.path.exists(lp) else None)


def _save_clip_to_archive(app, entry, images):
    try:
        now = datetime.datetime.now()
        parts = entry.get("category_path") or []
        fd = os.path.join(app.base_root, now.strftime("%Y"), now.strftime("%B"),
                          now.strftime("%d-%m-%Y"), *parts)
        os.makedirs(fd, exist_ok=True)

        canvas, logo_path = _composite_final(
            images, entry["paper"], entry["page"], entry["position"],
            entry.get("logo_scale", 1.0), entry.get("text_scale", 1.0),
            getattr(app, "logo_dir", ""), getattr(app, "logo_dir_bundled", ""))

        if not logo_path:
            try:
                app.after(0, lambda p=entry["paper"]: app._flag_missing_logo(p))
            except Exception:
                pass

        fname = (f"{entry['paper']}, Page-{entry['page']}, Pos-{entry['position']}, "
                f"S-{entry['size']}, Date-{now.strftime('%d-%m-%Y')}.jpg")
        full_path = os.path.join(fd, fname)
        canvas.convert("RGB").save(full_path, "JPEG", quality=92)
        return True, full_path
    except Exception as e:
        logging.error(f"_save_clip_to_archive: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────
# BATCH STRIP — injected into the Clip tab, visible only while a batch
# session is active. THIS is where capturing actually happens now.
# ─────────────────────────────────────────────────────────────────────────
def _inject_batch_strip(app):
    if hasattr(app, "_batch_strip") and app._batch_strip.winfo_exists():
        app._batch_strip.place(relx=0.5, rely=0.0, anchor="n", y=4)
        app._batch_strip.lift()
        return

    strip = ctk.CTkFrame(app.right_container, fg_color="#0D0D14", corner_radius=12,
                         border_width=1, border_color="#F59E0B")
    app._batch_strip = strip

    row = ctk.CTkFrame(strip, fg_color="transparent")
    row.pack(padx=10, pady=8)

    app._batch_strip_status = ctk.CTkLabel(row, text="📦 Batch active",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#F59E0B")
    app._batch_strip_status.pack(side="left", padx=(0, 10))

    ctk.CTkButton(row, text="➡ Seal Clip  (Ctrl+Enter)", height=32,
                 fg_color="#22C55E", hover_color="#1ca34e",
                 font=ctk.CTkFont(size=12, weight="bold"),
                 command=lambda: seal_current_clip(app)).pack(side="left", padx=4)
    ctk.CTkButton(row, text="✍ Enter Metadata", height=32,
                 fg_color="#F59E0B", hover_color="#cc7700", text_color="#000",
                 command=lambda: _go_to_review(app)).pack(side="left", padx=4)
    ctk.CTkButton(row, text="✕ End Batch", height=32, width=36,
                 fg_color="#333", hover_color="#444",
                 command=lambda: _confirm_end_batch(app)).pack(side="left", padx=4)

    app._batch_strip_filmstrip = ctk.CTkFrame(strip, fg_color="transparent")
    app._batch_strip_filmstrip.pack(fill="x", padx=10, pady=(0, 8))

    strip.place(relx=0.5, rely=0.0, anchor="n", y=4)
    strip.lift()

    # Ctrl+Enter to seal — bound at the root window so it works no matter
    # which widget currently has focus (canvas, an entry, anything).
    app.bind_all("<Control-Return>", lambda e: seal_current_clip(app))


def _hide_batch_strip(app):
    if hasattr(app, "_batch_strip"):
        app._batch_strip.place_forget()
    try:
        app.unbind_all("<Control-Return>")
    except Exception:
        pass


def _update_batch_strip(app):
    """One tile per SEALED CLIP (not one per paper) — this was the "can't
    edit a previous image, can't see its category" bug. Grouping by paper
    only ever let you reopen the MOST RECENT clip for that paper, and never
    showed what category it was tagged with. Each tile now shows the paper,
    a short category label, and reopens that exact clip."""
    session = getattr(app, "_batch_session", None)
    if not session or not hasattr(app, "_batch_strip_status"):
        return
    stats = session.stats()
    app._batch_strip_status.configure(
        text=f"📦 {stats['total_clips']} sealed · {stats['papers']} papers")

    for w in app._batch_strip_filmstrip.winfo_children():
        w.destroy()
    for paper, clips in session.clips_grouped_by_paper():
        for c in clips:
            logo = _load_paper_logo(app, paper, size=24)
            cat = " / ".join(c.get("category_path") or []) or "(no category)"
            label = f"{paper[:14]}\n{cat[:16]}"
            btn = ctk.CTkButton(
                app._batch_strip_filmstrip, text=label,
                image=logo, fg_color="#151520", hover_color="#222",
                anchor="w", font=ctk.CTkFont(size=9), height=38, width=120,
                compound="left",
                command=lambda cid=c["clip_id"]: _reopen_clip(app, cid))
            btn.pack(side="left", padx=2)
            if logo:
                btn.image = logo


def seal_current_clip(app):
    """The core Batch action. Reads app.orig_images EXACTLY as GENERATE
    does — same state, same edits, same everything the operator just did
    with the full toolbar — seals it to the batch queue, then clears the
    canvas for the next clip."""
    session = getattr(app, "_batch_session", None)
    if not session:
        return
    if not app.orig_images:
        messagebox.showinfo("Nothing to seal", "Paste and edit a clip first.")
        return
    paper = _strip_emoji(app, app.paper_var.get())
    if not paper:
        messagebox.showwarning("No paper selected", "Pick a paper first.")
        return

    try:
        session.seal_clip(
            list(app.orig_images), paper=paper,
            category_path=_selected_category_path(app),
            logo_scale=app.logo_slider.get() if hasattr(app, "logo_slider") else 1.0,
            text_scale=app.text_slider.get() if hasattr(app, "text_slider") else 1.0,
        )
    except Exception as e:
        logging.error(f"seal_current_clip: {e}")
        messagebox.showerror("Could not seal clip", str(e))
        return

    app.orig_images = []
    app.proxy_images = []
    try:
        app.force_update_preview()
    except Exception:
        pass
    _update_batch_strip(app)
    _update_batch_badge(app)
    try:
        cat_display = " / ".join(_selected_category_path(app)) or "no category"
        app.status_label.configure(text=f"SEALED — {cat_display}", text_color="#22C55E")
        app.after(1800, lambda: app.status_label.configure(text="READY", text_color="#6B7280"))
    except Exception:
        pass


def seal_current_clip_with_category(app, cat_path):
    """Called from the existing quick-save hotkey system (execute_quick_save
    in nab_app.py) when a batch session is active — same category hotkeys
    you already use, they just seal to the batch instead of opening the
    metadata dialog while one's running."""
    session = getattr(app, "_batch_session", None)
    if not session or not app.orig_images:
        return
    paper = _strip_emoji(app, app.paper_var.get())
    if not paper:
        return
    parts = cat_path.split("/") if isinstance(cat_path, str) else list(cat_path)
    try:
        session.seal_clip(
            list(app.orig_images), paper=paper, category_path=parts,
            logo_scale=app.logo_slider.get() if hasattr(app, "logo_slider") else 1.0,
            text_scale=app.text_slider.get() if hasattr(app, "text_slider") else 1.0,
        )
    except Exception as e:
        logging.error(f"seal_current_clip_with_category: {e}")
        return
    app.orig_images = []
    app.proxy_images = []
    try:
        app.force_update_preview()
    except Exception:
        pass
    _update_batch_strip(app)
    _update_batch_badge(app)


def _reopen_clip(app, clip_id):
    """Click ANY sealed clip's tile in the strip -> load that exact clip
    back onto the canvas for editing/appending, with its paper AND its
    category both restored — not just the most recent clip for a paper,
    and not silently dropping which category it was filed under."""
    session = app._batch_session
    if app.orig_images:
        if not messagebox.askyesno(
                "Replace current clip?",
                "The canvas has an unsealed clip on it. Loading a sealed "
                "clip to edit will replace it — the unsealed one will be "
                "lost. Continue?"):
            return
    images, entry = session.reopen_clip(clip_id)
    if not entry:
        return
    app._batch_reopened_clip_id = clip_id
    try:
        app.save_state()
    except Exception:
        pass
    app.orig_images = images
    app.proxy_images = [app.create_proxy(im) for im in images]
    app._rebuild_default_offsets()
    app.force_update_preview()
    try:
        app.paper_var.set(entry["paper"])
    except Exception:
        pass
    _restore_category_selection(app, entry.get("category_path") or [])
    cat_display = " / ".join(entry.get("category_path") or []) or "no category set"
    try:
        app.status_label.configure(
            text=f"EDITING: {entry['paper']} — {cat_display}", text_color="#F59E0B")
    except Exception:
        pass


def _restore_category_selection(app, category_path):
    """Re-selects the same node in the real cat_tree a sealed clip was
    tagged with, so re-sealing after editing keeps the same category by
    default instead of silently losing it or needing it re-picked."""
    if not category_path:
        return
    try:
        tree = app.cat_tree
        for root_id in tree.get_children(""):
            if tree.item(root_id)["text"] == category_path[0]:
                if len(category_path) == 1:
                    tree.selection_set(root_id)
                    tree.see(root_id)
                    return
                for child_id in tree.get_children(root_id):
                    if tree.item(child_id)["text"] == category_path[1]:
                        tree.selection_set(child_id)
                        tree.see(child_id)
                        return
    except Exception as e:
        logging.error(f"_restore_category_selection: {e}")


def _go_to_review(app):
    if not app._batch_session:
        return
    if app.orig_images:
        if not messagebox.askyesno(
                "Unsealed clip on canvas",
                "There's a pasted clip that hasn't been sealed yet — it "
                "will be lost if you continue to metadata entry. Continue?"):
            return
        app.orig_images = []
        app.proxy_images = []
        try:
            app.force_update_preview()
        except Exception:
            pass
    app.main_tabs.set("📦 Batch")
    _show_review_view(app)


def _confirm_end_batch(app):
    session = app._batch_session
    if not session:
        return
    stats = session.stats()
    if stats["total_clips"] == 0:
        session.discard()
        app._batch_session = None
        _hide_batch_strip(app)
        _update_batch_badge(app)
        return
    if messagebox.askyesno(
            "End batch session?",
            f"{stats['total_clips']} sealed clip(s), {stats['done']} already "
            f"typed. Ending now keeps everything you've done — you can "
            f"resume entering metadata for the rest later from the Batch tab."):
        _hide_batch_strip(app)
        app.main_tabs.set("📦 Batch")


# ─────────────────────────────────────────────────────────────────────────
# MAIN TAB — launcher + live mirror + Review
# ─────────────────────────────────────────────────────────────────────────
def build_batch_tab(app, tab_batch):
    app._batch_session = None

    root = ctk.CTkFrame(tab_batch, fg_color="#08080E")
    root.pack(fill="both", expand=True)

    top = ctk.CTkFrame(root, fg_color="#0D0D14", height=54, corner_radius=0)
    top.pack(fill="x")
    top.pack_propagate(False)

    app._batch_badge = ctk.CTkLabel(top, text="Batch: not started",
                                    font=ctk.CTkFont(size=13, weight="bold"),
                                    text_color="#888")
    app._batch_badge.pack(side="left", padx=16)

    def _start_batch():
        if app._batch_session is not None:
            app.main_tabs.set("✂️ Clip")
            return
        app._batch_session = nab_batch.BatchSession.create_new()
        _inject_batch_strip(app)
        _update_batch_strip(app)
        _update_batch_badge(app)
        app.main_tabs.set("✂️ Clip")

    ctk.CTkButton(top, text="▶ Start Batch", width=110, height=32,
                 fg_color="#22C55E", hover_color="#1ca34e",
                 command=_start_batch).pack(side="left", padx=6)
    ctk.CTkButton(top, text="✍ Start Entering Metadata", width=190, height=32,
                 fg_color="#F59E0B", hover_color="#cc7700", text_color="#000",
                 command=lambda: _go_to_review(app)).pack(side="left", padx=6)

    body = ctk.CTkFrame(root, fg_color="transparent")
    body.pack(fill="both", expand=True)

    app._batch_mirror_frame = ctk.CTkFrame(body, fg_color="transparent")
    app._batch_review_frame = ctk.CTkFrame(body, fg_color="transparent")
    _build_mirror_view(app, app._batch_mirror_frame)
    _build_review_view(app, app._batch_review_frame)
    app._batch_mirror_frame.pack(fill="both", expand=True)


def _build_mirror_view(app, parent):
    """Just a live status readout — capturing itself happens on the Clip
    tab via the injected strip. This exists so switching to the Batch tab
    always shows something useful even before you've opened Review."""
    ctk.CTkLabel(parent, text="Capturing happens on the ✂️ Clip tab — this "
                            "tab just tracks progress until you're ready "
                            "for metadata entry.",
                font=ctk.CTkFont(size=12), text_color="#666",
                wraplength=500, justify="center").pack(pady=(30, 10))
    app._batch_mirror_strip = ctk.CTkFrame(parent, fg_color="transparent")
    app._batch_mirror_strip.pack(pady=10)


def _update_batch_badge(app):
    s = app._batch_session
    if not s:
        app._batch_badge.configure(text="Batch: not started", text_color="#888")
        return
    stats = s.stats()
    app._batch_badge.configure(
        text=f"📦 {stats['total_clips']} sealed · {stats['papers']} papers "
            f"· {stats['done']} typed · {stats['flagged']} flagged",
        text_color="#F59E0B")


def _show_review_view(app):
    app._batch_mirror_frame.pack_forget()
    app._batch_review_frame.pack(fill="both", expand=True)
    _load_review_queue(app)


def _show_mirror_view(app):
    app._batch_review_frame.pack_forget()
    app._batch_mirror_frame.pack(fill="both", expand=True)


# ─────────────────────────────────────────────────────────────────────────
# REVIEW VIEW
# ─────────────────────────────────────────────────────────────────────────
def _build_review_view(app, parent):
    app._review_queue = []
    app._review_index = 0

    strip_wrap = ctk.CTkFrame(parent, fg_color="#0D0D14", width=170)
    strip_wrap.pack(side="left", fill="y")
    strip_wrap.pack_propagate(False)
    ctk.CTkLabel(strip_wrap, text="QUEUE", font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#666").pack(anchor="w", padx=10, pady=(12, 4))
    app._review_strip = ctk.CTkScrollableFrame(strip_wrap, fg_color="transparent")
    app._review_strip.pack(fill="both", expand=True, padx=6, pady=6)

    center = ctk.CTkFrame(parent, fg_color="#08080E")
    center.pack(side="left", fill="both", expand=True)

    app._review_paper_lbl = ctk.CTkLabel(center, text="", font=ctk.CTkFont(size=15, weight="bold"),
                                         text_color="#F59E0B")
    app._review_paper_lbl.pack(pady=(10, 0))

    img_frame = ctk.CTkFrame(center, fg_color="#000")
    img_frame.pack(fill="both", expand=True, padx=16, pady=10)
    app._review_canvas = tk.Canvas(img_frame, bg="#000", highlightthickness=0)
    app._review_canvas.pack(fill="both", expand=True)
    app._review_canvas.bind("<Configure>", lambda e: _render_review_image(app))

    form = ctk.CTkFrame(center, fg_color="#0D0D14")
    form.pack(fill="x", padx=16, pady=(0, 12))

    row1 = ctk.CTkFrame(form, fg_color="transparent")
    row1.pack(fill="x", padx=12, pady=(12, 4))
    ctk.CTkLabel(row1, text="Page", width=60, anchor="w",
                font=ctk.CTkFont(size=12)).pack(side="left")
    app._review_page_entry = ctk.CTkEntry(row1, height=34, font=ctk.CTkFont(size=13))
    app._review_page_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

    row2 = ctk.CTkFrame(form, fg_color="transparent")
    row2.pack(fill="x", padx=12, pady=4)
    ctk.CTkLabel(row2, text="Position", width=60, anchor="w",
                font=ctk.CTkFont(size=12)).pack(side="left")
    app._review_position_entry = ctk.CTkEntry(row2, height=34, font=ctk.CTkFont(size=13))
    app._review_position_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

    chips = ctk.CTkFrame(form, fg_color="transparent")
    chips.pack(fill="x", padx=12, pady=(0, 4))
    ctk.CTkLabel(chips, text="", width=60).pack(side="left")
    chip_holder = ctk.CTkFrame(chips, fg_color="transparent")
    chip_holder.pack(side="left", fill="x", expand=True)
    for i, pos in enumerate(nab_batch.COMMON_POSITIONS):
        ctk.CTkButton(chip_holder, text=f"{pos}", height=24, width=1,
                     fg_color="#1A1A1A", hover_color="#333",
                     font=ctk.CTkFont(size=10),
                     command=lambda p=pos: _set_position_chip(app, p)
                     ).pack(side="left", padx=2, pady=2)
        # Alt+1..Alt+9, Alt+0 for the 10th — avoids colliding with typing
        # digits directly into the Page field.
        app.bind_all(f"<Alt-Key-{(i + 1) % 10}>",
                    lambda e, p=pos: _set_position_chip(app, p) if _review_visible(app) else None)

    row3 = ctk.CTkFrame(form, fg_color="transparent")
    row3.pack(fill="x", padx=12, pady=4)
    ctk.CTkLabel(row3, text="Size", width=60, anchor="w",
                font=ctk.CTkFont(size=12)).pack(side="left")
    app._review_size_entry = ctk.CTkEntry(row3, height=34, font=ctk.CTkFont(size=13))
    app._review_size_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

    app._review_dup_warning = ctk.CTkLabel(
        form, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#EF4444")
    app._review_dup_warning.pack(fill="x", padx=12, pady=(4, 0))

    btn_row = ctk.CTkFrame(form, fg_color="transparent")
    btn_row.pack(fill="x", padx=12, pady=10)
    ctk.CTkButton(btn_row, text="◀ Back (PgUp)", width=110,
                 fg_color="#333", command=lambda: _review_nav(app, -1)
                 ).pack(side="left", padx=2)
    ctk.CTkButton(btn_row, text="⚑ Flag/Skip (Ctrl+F)", width=150,
                 fg_color="#7C4A00", hover_color="#9c5f00",
                 command=lambda: _review_flag(app)
                 ).pack(side="left", padx=2)
    ctk.CTkButton(btn_row, text="✅ Save & Next ▶  (Enter)", fg_color="#22C55E",
                 hover_color="#1ca34e", font=ctk.CTkFont(size=13, weight="bold"),
                 command=lambda: _review_submit(app)
                 ).pack(side="left", fill="x", expand=True, padx=2)

    for entry in (app._review_page_entry, app._review_position_entry, app._review_size_entry):
        entry.bind("<Return>", lambda e: _review_submit(app))
        entry.bind("<Prior>", lambda e: _review_nav(app, -1))
        entry.bind("<Next>", lambda e: _review_nav(app, 1))
        # Live header preview — this was the "not showing metadata live"
        # bug: the header text only redrew on <Configure> before, never as
        # you actually typed.
        entry.bind("<KeyRelease>", lambda e: _render_review_image(app))

    app.bind_all("<Control-f>", lambda e: _review_flag(app) if _review_visible(app) else None)
    app.bind_all("<Control-F>", lambda e: _review_flag(app) if _review_visible(app) else None)


def _review_visible(app):
    try:
        return app._batch_review_frame.winfo_ismapped()
    except Exception:
        return False


def _set_position_chip(app, pos):
    app._review_position_entry.delete(0, "end")
    app._review_position_entry.insert(0, pos)
    _render_review_image(app)


def _load_review_queue(app):
    session = app._batch_session
    if not session:
        return
    app._review_queue = []
    for paper, clips in session.pending_clips_grouped():
        for c in clips:
            app._review_queue.append(c["clip_id"])
    app._review_index = 0
    _refresh_review_strip(app)
    if app._review_queue:
        _load_review_item(app, 0)
    else:
        _show_batch_summary(app)


def _refresh_review_strip(app):
    for w in app._review_strip.winfo_children():
        w.destroy()
    session = app._batch_session
    if not session:
        return
    for i, clip_id in enumerate(app._review_queue):
        entry = session._find(clip_id)
        if not entry:
            continue
        logo = _load_paper_logo(app, entry["paper"], size=28)
        status_icon = {"pending": "⏳", "flagged": "⚑", "done": "✅"}.get(entry["status"], "")
        # A real CTkButton, not a Frame with manually bound clicks — the
        # Frame+bind version was the "clicking thumbnails does nothing" bug:
        # CTkFrame draws its background through an internal canvas layer
        # that doesn't reliably forward <Button-1> the way a plain Frame
        # would. A button's command always fires.
        btn = ctk.CTkButton(
            app._review_strip,
            text=f"{status_icon} {entry['paper']}", image=logo,
            fg_color="#2A2200" if i == app._review_index else "#151520",
            hover_color="#3A3000", anchor="w",
            font=ctk.CTkFont(size=10), height=44,
            compound="left",
            command=lambda idx=i: _load_review_item(app, idx))
        btn.pack(fill="x", pady=3)
        if logo:
            btn.image = logo


def _load_review_item(app, index):
    if not (0 <= index < len(app._review_queue)):
        return
    app._review_index = index
    clip_id = app._review_queue[index]
    session = app._batch_session
    entry = session._find(clip_id)
    if not entry:
        return

    app._review_current_clip_id = clip_id
    paths = session.load_clip_image_paths(clip_id)
    app._review_current_images = []
    for p in paths:
        try:
            app._review_current_images.append(Image.open(p).convert("RGB"))
        except Exception as e:
            logging.error(f"_load_review_item: {e}")

    app._review_paper_lbl.configure(text=entry["paper"])
    app._review_page_entry.delete(0, "end")
    app._review_position_entry.delete(0, "end")
    app._review_size_entry.delete(0, "end")
    if entry["page"] is not None:
        app._review_page_entry.insert(0, str(entry["page"]))
    if entry["position"]:
        app._review_position_entry.insert(0, entry["position"])
    if entry["size"]:
        app._review_size_entry.insert(0, entry["size"])
    app._review_dup_warning.configure(text="")

    _render_review_image(app)
    _refresh_review_strip(app)
    app._review_page_entry.focus_set()


def _render_review_image(app):
    cv = app._review_canvas
    cv.delete("all")
    images = getattr(app, "_review_current_images", [])
    if not images:
        return
    cw = max(cv.winfo_width(), 100)
    ch = max(cv.winfo_height(), 100)

    total_w = max(im.width for im in images)
    total_h = sum(im.height for im in images)
    merged = Image.new("RGB", (total_w, total_h), "white")
    y = 0
    for im in images:
        merged.paste(im, ((total_w - im.width) // 2, y))
        y += im.height

    page = app._review_page_entry.get().strip() or "?"
    pos = app._review_position_entry.get().strip() or "?"
    header_h = 40
    canvas_img = Image.new("RGB", (total_w, total_h + header_h), "white")
    draw = ImageDraw.Draw(canvas_img)
    info = f"Page-{page}, Pos-{pos}"
    try:
        font = ImageFont.truetype("arialbd.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    tw = draw.textbbox((0, 0), info, font=font)[2]
    draw.text(((total_w - tw) // 2, 8), info, fill="black", font=font)
    canvas_img.paste(merged, (0, header_h))

    scale = min(cw / canvas_img.width, ch / canvas_img.height, 1.0)
    disp = canvas_img.resize((max(1, int(canvas_img.width * scale)),
                              max(1, int(canvas_img.height * scale))),
                             Image.Resampling.BILINEAR)
    photo = ImageTk.PhotoImage(disp)
    app._review_photo_ref = photo
    cv.create_image(cw // 2, ch // 2, image=photo, anchor="center")


def _review_nav(app, delta):
    new_index = app._review_index + delta
    if 0 <= new_index < len(app._review_queue):
        _load_review_item(app, new_index)


def _review_flag(app):
    clip_id = getattr(app, "_review_current_clip_id", None)
    if not clip_id:
        return
    app._batch_session.set_flag(clip_id, True)
    _update_batch_badge(app)
    _advance_or_finish(app)


def _review_submit(app):
    clip_id = getattr(app, "_review_current_clip_id", None)
    if not clip_id:
        return
    page = app._review_page_entry.get().strip()
    pos = app._review_position_entry.get().strip()
    size = app._review_size_entry.get().strip()
    if not (page and pos and size):
        app._review_dup_warning.configure(
            text="⚠ Page, Position and Size are all required.", text_color="#EF4444")
        return

    entry = app._batch_session._find(clip_id)
    dup = app._batch_session.find_duplicate(entry["paper"], page, pos)
    if dup and dup["clip_id"] != clip_id:
        if not messagebox.askyesno(
                "Possible duplicate",
                f"{entry['paper']} already has a clip saved as "
                f"Page-{page}, Pos-{pos} ({dup['clip_id']}).\n\n"
                f"Save this one anyway?"):
            return

    app._batch_session.set_metadata(clip_id, page, pos, size)
    entry = app._batch_session._find(clip_id)
    images = getattr(app, "_review_current_images", [])
    ok, result = _save_clip_to_archive(app, entry, images)
    if not ok:
        app._batch_session.set_flag(clip_id, True)
        messagebox.showerror(
            "Save failed",
            f"Couldn't write the file for {entry['paper']} — this clip has "
            f"been flagged so you can retry it.\n\n{result}")
        _update_batch_badge(app)
        _advance_or_finish(app)
        return

    _update_batch_badge(app)
    _advance_or_finish(app)


def _advance_or_finish(app):
    prev_index = app._review_index
    _load_review_queue(app)
    if app._review_queue:
        _load_review_item(app, min(prev_index, len(app._review_queue) - 1))


# ─────────────────────────────────────────────────────────────────────────
# END OF BATCH
# ─────────────────────────────────────────────────────────────────────────
def _show_batch_summary(app):
    session = app._batch_session
    if not session:
        return
    stats = session.stats()

    win = ctk.CTkToplevel(app)
    win.title("Batch complete")
    win.configure(fg_color="#08080E")
    nab_ui_scale.fit(win, 480, 480, min_w=320, min_h=340, parent=app)
    win.attributes("-topmost", True)
    win.grab_set()

    ctk.CTkLabel(win, text="✅ Batch review finished",
                font=ctk.CTkFont(size=17, weight="bold"),
                text_color="#22C55E").pack(pady=(20, 6))
    ctk.CTkLabel(win,
                text=f"{stats['total_clips']} clips · {stats['papers']} papers · "
                     f"{stats['elapsed_minutes']} min",
                font=ctk.CTkFont(size=12), text_color="#AAA").pack(pady=(0, 12))

    body = ctk.CTkScrollableFrame(win, fg_color="#0D0D14")
    body.pack(fill="both", expand=True, padx=16, pady=8)
    for paper, clips in session.clips_grouped_by_paper():
        ctk.CTkLabel(body, text=paper, font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#F59E0B", anchor="w").pack(fill="x", pady=(8, 2))
        for c in clips:
            icon = {"done": "✅", "flagged": "⚑", "pending": "⏳"}.get(c["status"], "")
            detail = (f"Page-{c['page']}, Pos-{c['position']}, S-{c['size']}"
                      if c["status"] == "done" else c["status"])
            ctk.CTkLabel(body, text=f"  {icon} {detail}", font=ctk.CTkFont(size=11),
                        text_color="#CCC", anchor="w").pack(fill="x")

    if stats["flagged"]:
        ctk.CTkLabel(win, text=f"⚑ {stats['flagged']} still flagged — see list above.",
                    font=ctk.CTkFont(size=11), text_color="#F59E0B").pack(pady=(4, 0))

    def _finish_session():
        session.discard()
        app._batch_session = None
        _hide_batch_strip(app)
        _update_batch_badge(app)
        win.destroy()
        _show_mirror_view(app)

    def _export_flagged():
        text = session.flagged_summary_text()
        path = os.path.join(os.path.expanduser("~"), "Desktop",
                            f"nab_batch_flagged_{session.manifest['session_id']}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            messagebox.showinfo("Exported", f"Saved to:\n{path}", parent=win)
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=win)

    foot = ctk.CTkFrame(win, fg_color="transparent")
    foot.pack(pady=12)
    if stats["flagged"]:
        ctk.CTkButton(foot, text="📄 Export flagged list", width=180,
                     fg_color="#333", command=_export_flagged).pack(side="left", padx=4)
    ctk.CTkButton(foot, text="Done — clear session", width=160,
                 fg_color="#22C55E", command=_finish_session).pack(side="left", padx=4)
