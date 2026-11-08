# nab_batch.py — Batch Mode engine: staging, sealing, crash-safe resume.
#
# This module is deliberately GUI-free. Every function here works on plain
# data (PIL images, dicts, JSON) so it can be tested without a Tkinter
# display — the Batch tab UI in nab_app.py calls into this, but none of the
# actual persistence logic lives there.
#
# CRASH-SAFETY MODEL (chosen deliberately, not the maximal option):
#   - A clip is durable the INSTANT seal_clip() returns — its images are on
#     disk, its manifest entry is written. If NAB crashes a second later,
#     that clip is completely safe.
#   - The clip you're actively pasting/editing when a crash happens is NOT
#     protected. You redo just that one. This was a deliberate scope choice
#     (see the conversation this was designed in) — full mid-edit undo-
#     history-preserving crash recovery is a much bigger feature for very
#     little real benefit, since you'd rarely want to undo past a crash
#     point anyway.
#
import os
import json
import time
import shutil
import logging
import datetime
import difflib
from PIL import Image

STAGING_ROOT = os.path.join(os.path.expanduser("~"), "Documents", "nab_batch_staging")


def _now_id():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


class BatchSession:
    """One capture-through-review run. `session_dir` holds everything on
    disk; `manifest` (manifest.json inside it) is the single source of
    truth for what's been sealed, in what order, tagged how.

    Manifest shape:
      {
        "session_id": "...",
        "created_at": "...",
        "clips": [
          {
            "clip_id": "clip_0001",
            "paper": "The Daily Star",
            "category_path": ["Beximco", "Media"],   # or [] if unset
            "sealed_at": "...",
            "image_files": ["img_0.png", "img_1.png"],  # continuation order
            "logo_scale": 1.0, "text_scale": 1.0,
            # filled in during Review:
            "status": "pending",   # pending | flagged | done
            "page": null, "position": null, "size": null,
          },
          ...
        ]
      }
    """

    def __init__(self, session_dir):
        self.session_dir = session_dir
        self.manifest_path = os.path.join(session_dir, "manifest.json")
        self.manifest = self._load_manifest()

    # ── lifecycle ────────────────────────────────────────────────────────
    @classmethod
    def create_new(cls):
        session_id = _now_id()
        session_dir = os.path.join(STAGING_ROOT, session_id)
        os.makedirs(session_dir, exist_ok=True)
        session = cls(session_dir)
        session.manifest = {
            "session_id": session_id,
            "created_at": datetime.datetime.now().isoformat(),
            "clips": [],
        }
        session._save_manifest()
        return session

    @staticmethod
    def find_resumable():
        """Returns the most recent incomplete session's dir, or None. A
        session counts as resumable if it has any clip that isn't 'done' —
        an all-done session was already fully processed and just wasn't
        cleaned up yet (or the user finished but didn't hit a final
        "clear session" step)."""
        if not os.path.isdir(STAGING_ROOT):
            return None
        candidates = []
        for name in os.listdir(STAGING_ROOT):
            d = os.path.join(STAGING_ROOT, name)
            mpath = os.path.join(d, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            try:
                with open(mpath, encoding="utf-8") as f:
                    m = json.load(f)
                if any(c.get("status") != "done" for c in m.get("clips", [])):
                    candidates.append((m.get("created_at", ""), d))
            except Exception as e:
                logging.error(f"BatchSession.find_resumable: {e}")
        if not candidates:
            return None
        candidates.sort()
        return candidates[-1][1]

    def _load_manifest(self):
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"BatchSession._load_manifest: {e}")
        return {"session_id": os.path.basename(self.session_dir),
               "created_at": datetime.datetime.now().isoformat(), "clips": []}

    def _save_manifest(self):
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.manifest_path)   # atomic — never a half-written manifest

    def discard(self):
        """Delete the whole session from disk. Only call this after the
        operator has explicitly confirmed everything is saved/handled —
        never automatically."""
        try:
            shutil.rmtree(self.session_dir, ignore_errors=True)
        except Exception as e:
            logging.error(f"BatchSession.discard: {e}")

    # ── sealing a clip ───────────────────────────────────────────────────
    def seal_clip(self, images, paper, category_path=None,
                 logo_scale=1.0, text_scale=1.0):
        """images: list of PIL Images, in the order they should stitch
        (continuations included). Writes them to disk immediately and
        appends a manifest entry — this is the durability point. Returns
        the new clip's id."""
        clips = self.manifest["clips"]
        clip_id = f"clip_{len(clips) + 1:04d}"
        clip_dir = os.path.join(self.session_dir, clip_id)
        os.makedirs(clip_dir, exist_ok=True)

        files = []
        for i, img in enumerate(images):
            fname = f"img_{i}.png"
            img.save(os.path.join(clip_dir, fname), "PNG")
            files.append(fname)

        entry = {
            "clip_id": clip_id,
            "paper": paper,
            "category_path": category_path or [],
            "sealed_at": datetime.datetime.now().isoformat(),
            "image_files": files,
            "logo_scale": logo_scale,
            "text_scale": text_scale,
            "status": "pending",
            "page": None, "position": None, "size": None,
        }
        clips.append(entry)
        self._save_manifest()
        return clip_id

    def reopen_clip(self, clip_id):
        """Load a sealed clip's images back for appending a missed
        continuation. Returns (images, entry) — caller pastes more onto
        `images` and calls update_clip_images() to re-persist."""
        entry = self._find(clip_id)
        if not entry:
            return [], None
        clip_dir = os.path.join(self.session_dir, clip_id)
        images = []
        for fname in entry["image_files"]:
            p = os.path.join(clip_dir, fname)
            if os.path.exists(p):
                images.append(Image.open(p).convert("RGB"))
        return images, entry

    def update_clip_images(self, clip_id, images):
        """Re-persist a clip's images after reopening + appending one.
        Overwrites the clip's image files on disk in the new order."""
        entry = self._find(clip_id)
        if not entry:
            return False
        clip_dir = os.path.join(self.session_dir, clip_id)
        # Clear old files first so a shrink (fewer images than before)
        # doesn't leave a stale extra file lying around.
        for old in entry["image_files"]:
            try:
                os.remove(os.path.join(clip_dir, old))
            except OSError:
                pass
        files = []
        for i, img in enumerate(images):
            fname = f"img_{i}.png"
            img.save(os.path.join(clip_dir, fname), "PNG")
            files.append(fname)
        entry["image_files"] = files
        self._save_manifest()
        return True

    def load_clip_image_paths(self, clip_id):
        entry = self._find(clip_id)
        if not entry:
            return []
        clip_dir = os.path.join(self.session_dir, clip_id)
        return [os.path.join(clip_dir, f) for f in entry["image_files"]]

    def _find(self, clip_id):
        for c in self.manifest["clips"]:
            if c["clip_id"] == clip_id:
                return c
        return None

    # ── review phase ─────────────────────────────────────────────────────
    def clips_grouped_by_paper(self):
        """Ordered list of (paper, [clip_entries]) — papers in first-seen
        order, clips within a paper in capture order."""
        order, groups = [], {}
        for c in self.manifest["clips"]:
            p = c["paper"]
            if p not in groups:
                groups[p] = []
                order.append(p)
            groups[p].append(c)
        return [(p, groups[p]) for p in order]

    def pending_clips_grouped(self):
        """Same as clips_grouped_by_paper but only clips not yet marked
        'done' — flagged clips ARE included (they need revisiting), papers
        with nothing left pending are dropped entirely."""
        out = []
        for paper, clips in self.clips_grouped_by_paper():
            rest = [c for c in clips if c["status"] != "done"]
            if rest:
                out.append((paper, rest))
        return out

    def set_metadata(self, clip_id, page, position, size):
        entry = self._find(clip_id)
        if not entry:
            return False
        entry["page"], entry["position"], entry["size"] = page, position, size
        entry["status"] = "done"
        self._save_manifest()
        return True

    def set_flag(self, clip_id, flagged=True):
        entry = self._find(clip_id)
        if not entry:
            return False
        entry["status"] = "flagged" if flagged else "pending"
        self._save_manifest()
        return True

    def last_metadata_for_paper(self, paper):
        """Most recently completed clip's page/position/size for this
        paper — nothing is auto-filled from this (the operator explicitly
        chose not to auto-increment or repeat values), but it's exposed
        for the duplicate check below."""
        done = [c for c in self.manifest["clips"]
               if c["paper"] == paper and c["status"] == "done"]
        return done[-1] if done else None

    def find_duplicate(self, paper, page, position):
        """Any OTHER clip in this session already saved with the same
        paper+page+position? Returns that clip's entry, or None. Doesn't
        check the on-disk archive — that's a bigger, slower check;
        within-session is the common real mistake (misread notebook row
        twice) and this is instant."""
        for c in self.manifest["clips"]:
            if (c["status"] == "done" and c["paper"] == paper
                    and c["page"] == page and c["position"] == position):
                return c
        return None

    # ── stats ────────────────────────────────────────────────────────────
    def stats(self):
        clips = self.manifest["clips"]
        papers = {c["paper"] for c in clips}
        done = [c for c in clips if c["status"] == "done"]
        flagged = [c for c in clips if c["status"] == "flagged"]
        try:
            started = datetime.datetime.fromisoformat(self.manifest["created_at"])
            elapsed_min = (datetime.datetime.now() - started).total_seconds() / 60
        except Exception:
            elapsed_min = 0
        return {
            "total_clips": len(clips),
            "papers": len(papers),
            "done": len(done),
            "flagged": len(flagged),
            "elapsed_minutes": round(elapsed_min, 1),
        }

    def flagged_summary_text(self):
        """Plain-text export of anything still flagged — for the operator
        to print/keep, not a file format anything else parses."""
        lines = []
        for c in self.manifest["clips"]:
            if c["status"] == "flagged":
                lines.append(f"{c['paper']} — {c['clip_id']} "
                            f"(sealed {c['sealed_at']})")
        return "\n".join(lines) if lines else "(nothing flagged)"


# ── paper name matching for chip/position vocab, reused from clip_scan's
#    normalisation style so results stay consistent with the tracker ──────
def _norm(s):
    import re
    s = (s or "").strip().lower()
    return re.sub(r"[^a-z0-9]", "", s)


import re as _re
_EMOJI_PREFIX_RE = _re.compile(r"^[\U0001F000-\U0001FFFF\u2190-\u2BFF\uFE0F\u200D\s]+")


def strip_emoji_prefix(name):
    """Same rule as nab_constants.strip_emoji_prefix (kept here so this
    module has no dependency on the heavy GUI-side constants module):
    '📰 New Age' -> 'New Age'; a plain 'New Age' is returned untouched."""
    if not name:
        return name
    out = _EMOJI_PREFIX_RE.sub("", name, count=1)
    return out if out else name.strip()


COMMON_POSITIONS = ["Top", "Top-Left", "Top-Right", "Mid", "Mid-Left",
                   "Mid-Right", "Bottom", "Bottom-Left", "Bottom-Right",
                   "Full"]
