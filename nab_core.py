# nab_core.py — the clip document: layers, edits, undo, page composition.
#
# No Tk, no UI, no Windows calls: pure PIL/numpy, so it is fast, thread-safe
# enough for the engine and testable anywhere.
#
# Model: a Document is an ordered list of Layers (each pasted clip is one).
# The saved page is the layers stacked vertically and centred (exactly what the
# old app produced) under the paper logo + "Page-.., Pos-.., Date-.." header.
# Every edit REPLACES a layer's image with a new one (never mutates in place),
# so an undo snapshot is just a list of references — cheap.
import io
import os
import itertools
import threading

from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageOps, ImageEnhance, ImageFilter
try:
    from PIL import ImageFile as _IF
    _IF.MAXBLOCK = max(_IF.MAXBLOCK, 64 * 1024 * 1024)   # big images + optimize=True need a large JPEG buffer
except Exception:
    pass

try:
    import numpy as np
    import cv2
    HAS_CV = True
except Exception:       # keeps the module importable without OpenCV
    np = None
    cv2 = None
    HAS_CV = False

MAX_UNDO = 25
MIN_PAGE_WIDTH = 400          # old app: final_mw = max(merged.width, 400)

_ids = itertools.count(1)


# ─────────────────────────────────────────────────────────────────────────────
#  fonts
# ─────────────────────────────────────────────────────────────────────────────
_FONT_CACHE = {}


def header_font(size):
    size = max(8, int(size))
    f = _FONT_CACHE.get(size)
    if f:
        return f
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "LiberationSans-Bold.ttf"):
        try:
            f = ImageFont.truetype(name, size)
            break
        except Exception:
            f = None
    if f is None:
        try:
            f = ImageFont.load_default(size)
        except Exception:
            f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


# ─────────────────────────────────────────────────────────────────────────────
#  shapes -> masks.   All coordinates are LAYER pixels (full resolution).
# ─────────────────────────────────────────────────────────────────────────────
def shape_bbox(shape, size):
    """Integer bbox (x1,y1,x2,y2) of a shape, clamped to the layer."""
    w, h = size
    t = shape.get("type", "rect")
    if t == "not":
        return 0, 0, w, h
    if t in ("rect", "ellipse"):
        xs = [shape["x1"], shape["x2"]]
        ys = [shape["y1"], shape["y2"]]
    else:
        pts = shape["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if t == "stroke":
            r = float(shape.get("width", 20)) / 2.0
            xs = [min(xs) - r, max(xs) + r]
            ys = [min(ys) - r, max(ys) + r]
    x1 = max(0, int(min(xs)))
    y1 = max(0, int(min(ys)))
    x2 = min(w, int(max(xs)) + 1)
    y2 = min(h, int(max(ys)) + 1)
    return x1, y1, x2, y2


def make_mask(size, shape):
    """'L' mask (255 inside) the size of the layer for rect/ellipse/poly/stroke."""
    t = shape.get("type", "rect")
    if t == "not":                      # inverted selection: everything except the inner shape
        return ImageOps.invert(make_mask(size, shape["inner"]))
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    if t == "rect":
        x1, x2 = sorted((shape["x1"], shape["x2"]))
        y1, y2 = sorted((shape["y1"], shape["y2"]))
        d.rectangle([x1, y1, x2, y2], fill=255)
    elif t == "ellipse":
        x1, x2 = sorted((shape["x1"], shape["x2"]))
        y1, y2 = sorted((shape["y1"], shape["y2"]))
        d.ellipse([x1, y1, x2, y2], fill=255)
    elif t == "poly":
        pts = [(float(x), float(y)) for x, y in shape["points"]]
        if len(pts) >= 3:
            d.polygon(pts, fill=255)
    elif t == "stroke":
        pts = [(float(x), float(y)) for x, y in shape["points"]]
        w = max(1, int(shape.get("width", 20)))
        r = w / 2.0
        if len(pts) == 1:
            x, y = pts[0]
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        else:
            d.line(pts, fill=255, width=w, joint="curve")
            for x, y in (pts[0], pts[-1]):
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    else:
        raise ValueError(f"unknown shape {t!r}")
    return m


def shape_is_big_enough(shape, size, min_px=5):
    x1, y1, x2, y2 = shape_bbox(shape, size)
    return (x2 - x1) >= min_px and (y2 - y1) >= min_px


# ─────────────────────────────────────────────────────────────────────────────
#  image helpers  (ported 1:1 from the old app so results do not change)
# ─────────────────────────────────────────────────────────────────────────────
def cv_remove_lines(img):
    """Strip uniform-colour edge borders, then thin frame lines at the edge."""
    if not HAS_CV:
        return img
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    max_strip = min(20, int(min(h, w) * 0.04))
    tol = 18
    top = bot = left = right = 0
    for i in range(max_strip):
        if arr[i].max(axis=0).max() - arr[i].min(axis=0).max() <= tol:
            top = i + 1
        else:
            break
    for i in range(max_strip):
        if arr[h - 1 - i].max(axis=0).max() - arr[h - 1 - i].min(axis=0).max() <= tol:
            bot = i + 1
        else:
            break
    for i in range(max_strip):
        col = arr[:, i]
        if col.max(axis=0).max() - col.min(axis=0).max() <= tol:
            left = i + 1
        else:
            break
    for i in range(max_strip):
        col = arr[:, w - 1 - i]
        if col.max(axis=0).max() - col.min(axis=0).max() <= tol:
            right = i + 1
        else:
            break
    if top or bot or left or right:
        arr = arr[top: h - bot if bot else h, left: w - right if right else w]
        h, w = arr.shape[:2]
    img_bgr = arr[:, :, ::-1].copy()
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ex = max(6, int(w * 0.04))
    ey = max(6, int(h * 0.04))
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        is_h = cw > 60 and ch <= 10 and cw > ch * 10
        is_v = ch > 60 and cw <= 10 and ch > cw * 10
        if not (is_h or is_v):
            continue
        if x <= ex or x + cw >= w - ex or y <= ey or y + ch >= h - ey:
            cv2.rectangle(img_bgr, (max(0, x - 1), max(0, y - 1)),
                          (min(w, x + cw + 1), min(h, y + ch + 1)), (255, 255, 255), -1)
    return Image.fromarray(img_bgr[:, :, ::-1])


def auto_trim(img, pad=10):
    bg = Image.new(img.mode, img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, bg)
    diff = ImageChops.add(diff, diff, 2.0, -100)
    bbox = diff.getbbox()
    if bbox:
        x1, y1 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
        x2, y2 = min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad)
        return img.crop((x1, y1, x2, y2))
    return img


def pad_image(img, n=15):
    out = Image.new("RGB", (img.width + 2 * n, img.height + 2 * n), (255, 255, 255))
    out.paste(img, (n, n))
    return out


def polish(img):
    """What 'auto polish' does on paste: trim → remove edge lines → pad."""
    img = auto_trim(img)
    img = cv_remove_lines(img)
    return pad_image(img)


def suggest_crop(img):
    """Rectangle (x1,y1,x2,y2) that would trim borders and empty margin around
    a single news item, or None when the clip is already tight.  Used only as a
    SUGGESTION — the user accepts or adjusts it."""
    try:
        w, h = img.size
        if w < 60 or h < 60:
            return None
        rgb = img.convert("RGB")
        # 1) edge strips of one flat colour (scanner/browser borders)
        x1, y1, x2, y2 = 0, 0, w, h
        if HAS_CV:
            arr = np.asarray(rgb)
            tol = 18
            lim = min(40, int(min(h, w) * 0.06))

            def flat(a):
                return int(a.max(axis=0).max()) - int(a.min(axis=0).max()) <= tol
            while y1 < lim and flat(arr[y1]):
                y1 += 1
            while (h - y2) < lim and flat(arr[y2 - 1]):
                y2 -= 1
            while x1 < lim and flat(arr[:, x1]):
                x1 += 1
            while (w - x2) < lim and flat(arr[:, x2 - 1]):
                x2 -= 1
        inner = rgb.crop((x1, y1, x2, y2))
        # 2) empty margin around the content
        bg = Image.new("RGB", inner.size, inner.getpixel((0, 0)))
        diff = ImageChops.difference(inner, bg)
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bb = diff.getbbox()
        if bb:
            pad = max(22, int(max(w, h) * 0.03))   # keep some breathing room around the letters
            x1, y1, x2, y2 = (x1 + max(0, bb[0] - pad), y1 + max(0, bb[1] - pad),
                              x1 + min(inner.width, bb[2] + pad), y1 + min(inner.height, bb[3] + pad))
        removed = 1.0 - ((x2 - x1) * (y2 - y1)) / float(w * h)
        if removed < 0.02 or (x2 - x1) < 40 or (y2 - y1) < 40:
            return None
        return (int(x1), int(y1), int(x2), int(y2))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Layer / Document
# ─────────────────────────────────────────────────────────────────────────────
class Layer:
    __slots__ = ("id", "img", "name", "visible", "align", "_scaled", "x", "y")

    def __init__(self, img, name="Clip", visible=True, align="center", lid=None, x=0, y=0):
        self.x = x          # canvas position — only used while Document.free is True
        self.y = y
        self.id = lid or next(_ids)
        self.img = img
        self.name = name
        self.visible = visible
        self.align = align
        self._scaled = {}      # scale -> resized PIL (display only)

    def set_img(self, img):
        self.img = img
        self._scaled = {}

    def scaled(self, k):
        if k >= 0.999:
            return self.img
        key = round(k, 4)
        s = self._scaled.get(key)
        if s is None:
            if len(self._scaled) > 4:
                self._scaled.clear()
            w, h = self.img.size
            s = self.img.resize((max(1, int(round(w * k))), max(1, int(round(h * k)))),
                                Image.Resampling.BILINEAR if k < 0.5 else Image.Resampling.LANCZOS)
            self._scaled[key] = s
        return s

    def info(self):
        return {"id": self.id, "name": self.name, "visible": self.visible,
                "align": self.align, "w": self.img.width, "h": self.img.height, "x": self.x, "y": self.y}


class _Snap(list):
    free = False


class Document:
    def __init__(self):
        self.free = False                # False: clips stack top-to-bottom; True: layers sit at their own x,y
        self.layers = []
        self.rev = 0
        self._undo = []
        self._redo = []
        self.lock = threading.RLock()
        self.clipboard = None            # internal copy/cut buffer (RGBA PIL)

    # ---- bookkeeping --------------------------------------------------------
    def _snap(self):
        s = _Snap((l.id, l.img, l.name, l.visible, l.align, l.x, l.y) for l in self.layers)
        s.free = self.free
        return s

    def _restore(self, snap):
        old = {l.id: l for l in self.layers}
        out = []
        for lid, img, name, vis, al, x, y in snap:
            l = old.get(lid)
            if l is None:
                l = Layer(img, name, vis, al, lid=lid)
            else:
                if l.img is not img:
                    l.set_img(img)
                l.name, l.visible, l.align = name, vis, al
            l.x, l.y = x, y
            out.append(l)
        self.layers = out
        self.free = bool(getattr(snap, "free", False))

    def frozen_copy(self):
        """Independent copy of the visible layers (image objects are shared — edits replace, never mutate)."""
        d = Document()
        d.free = self.free
        d.layers = [Layer(l.img, l.name, True, l.align, x=l.x, y=l.y) for l in self.layers if l.visible]
        return d

    # ---- free canvas ----------------------------------------------------------
    def _bbox_abs(self):
        vis = self.visible_layers()
        if not vis:
            return 0, 0, 0, 0
        return (min(l.x for l in vis), min(l.y for l in vis),
                max(l.x + l.img.width for l in vis), max(l.y + l.img.height for l in vis))

    def freeze(self):
        """Switch from stacked flow to explicit positions (current look is kept exactly)."""
        if self.free:
            return
        rects, _, _ = self._rects(1.0)
        for l in self.layers:
            l.x = l.y = 0
        for l, p, x, y in rects:
            l.x, l.y = x, y
        self.free = True

    def restack(self):
        with self.lock:
            if not self.free:
                return False
            self.checkpoint()
            self.free = False
            self.touch()
            return True

    def op_move_layer(self, lid, dx, dy):
        with self.lock:
            l = self.get(lid)
            dx, dy = int(round(dx)), int(round(dy))
            if dx == 0 and dy == 0:
                return False
            self.checkpoint()
            self.freeze()
            l.x += dx
            l.y += dy
            self.touch()
            return True

    def op_resize_to(self, lid, w, h, dx=0, dy=0):
        """Resample a layer to w×h px (Lanczos); dx,dy shift its top-left (for left/top handles)."""
        with self.lock:
            l = self.get(lid)
            w, h = int(round(w)), int(round(h))
            if w < 8 or h < 8 or w > 20000 or h > 40000:
                return False
            if (w, h) == l.img.size and not dx and not dy:
                return False
            self.checkpoint()
            self.freeze()
            if (w, h) != l.img.size:
                l.set_img(l.img.resize((w, h), Image.Resampling.LANCZOS))
            l.x += int(round(dx))
            l.y += int(round(dy))
            self.touch()
            return True

    def op_match_width(self):
        """Resample every visible layer to the width of the widest one (typical after stitching clips taken at different zoom levels)."""
        with self.lock:
            vis = self.visible_layers()
            if len(vis) < 2:
                return False
            mw = max(l.img.width for l in vis)
            todo = [l for l in vis if abs(l.img.width - mw) > 1]
            if not todo:
                return False
            self.checkpoint()
            for l in todo:
                f = mw / float(l.img.width)
                l.set_img(l.img.resize((mw, max(1, int(round(l.img.height * f)))), Image.Resampling.LANCZOS))
                if self.free:
                    l.x = min(l2.x for l2 in vis)
            self.touch()
            return True

    def canvas_size(self):
        _, mw, mh = self._rects(1.0)
        return mw, mh

    def checkpoint(self):
        self._undo.append(self._snap())
        if len(self._undo) > MAX_UNDO:
            del self._undo[0]
        self._redo.clear()

    def undo(self):
        with self.lock:
            if not self._undo:
                return False
            self._redo.append(self._snap())
            self._restore(self._undo.pop())
            self.rev += 1
            return True

    def redo(self):
        with self.lock:
            if not self._redo:
                return False
            self._undo.append(self._snap())
            self._restore(self._redo.pop())
            self.rev += 1
            return True

    def touch(self):
        self.rev += 1

    def history_depth(self):
        return len(self._undo), len(self._redo)

    # ---- lookups ------------------------------------------------------------
    def get(self, lid):
        for l in self.layers:
            if l.id == lid:
                return l
        raise KeyError(f"no layer {lid}")

    def index(self, lid):
        for i, l in enumerate(self.layers):
            if l.id == lid:
                return i
        raise KeyError(f"no layer {lid}")

    def visible_layers(self):
        return [l for l in self.layers if l.visible]

    def is_empty(self):
        return not self.layers

    def info(self):
        return [l.info() for l in self.layers]

    # ---- adding / removing / ordering --------------------------------------
    def add(self, img, name="Clip", checkpoint=True, index=None):
        with self.lock:
            if checkpoint:
                self.checkpoint()
            l = Layer(img.convert("RGB"), name)
            if self.free:
                x0, y0, x1, y1 = self._bbox_abs()
                l.x = int(round((x0 + x1) / 2.0 - l.img.width / 2.0)) if self.visible_layers() else 0
                l.y = y1 if self.visible_layers() else 0
            if index is None:
                self.layers.append(l)
            else:
                self.layers.insert(index, l)
            self.touch()
            return l

    def clear(self, checkpoint=True):
        with self.lock:
            if checkpoint and self.layers:
                self.checkpoint()
            self.layers = []
            self.free = False
            self.touch()

    def delete(self, lid):
        with self.lock:
            i = self.index(lid)
            self.checkpoint()
            del self.layers[i]
            self.touch()

    def duplicate(self, lid):
        with self.lock:
            i = self.index(lid)
            self.checkpoint()
            src = self.layers[i]
            n = Layer(src.img, src.name + " copy", src.visible, src.align,
                      x=src.x + (24 if self.free else 0), y=src.y + (24 if self.free else 0))
            self.layers.insert(i + 1, n)
            self.touch()
            return n

    def set_visible(self, lid, vis):
        with self.lock:
            self.checkpoint()
            self.get(lid).visible = bool(vis)
            self.touch()

    def rename(self, lid, name):
        with self.lock:
            self.checkpoint()
            self.get(lid).name = str(name)[:60]
            self.touch()

    def set_align(self, lid, align):
        if align not in ("left", "center", "right"):
            raise ValueError("align")
        with self.lock:
            self.checkpoint()
            self.get(lid).align = align
            self.touch()

    def reorder(self, lid, new_index):
        with self.lock:
            i = self.index(lid)
            new_index = max(0, min(len(self.layers) - 1, int(new_index)))
            if i == new_index:
                return
            self.checkpoint()
            l = self.layers.pop(i)
            self.layers.insert(new_index, l)
            self.touch()

    def move_last(self, direction):
        """Ctrl+Up / Ctrl+Down: the old 'move last clip up/down' shortcut."""
        with self.lock:
            if len(self.layers) < 2:
                return
            self.checkpoint()
            if direction < 0:
                self.layers.insert(-1, self.layers.pop())
            else:
                self.layers.append(self.layers.pop(-2))
            self.touch()

    def swap_last_two(self):
        with self.lock:
            if len(self.layers) < 2:
                return
            self.checkpoint()
            self.layers[-1], self.layers[-2] = self.layers[-2], self.layers[-1]
            self.touch()

    def merge_down(self, lid):
        with self.lock:
            i = self.index(lid)
            if i == 0:
                return None
            self.checkpoint()
            a, b = self.layers[i - 1], self.layers[i]
            self._merge_into(a, [a, b])
            del self.layers[i]
            self.touch()
            return a

    def merge_visible(self):
        with self.lock:
            vis = self.visible_layers()
            if len(vis) < 2:
                return None
            self.checkpoint()
            first = vis[0]
            self._merge_into(first, vis)
            keep = {first.id}
            self.layers = [l for l in self.layers if (l.id in keep) or not l.visible]
            self.touch()
            return first

    def merge_side_by_side(self):
        """Last two layers → one wide layer (tops aligned, white gap-free)."""
        with self.lock:
            if len(self.layers) < 2:
                return None
            self.checkpoint()
            a, b = self.layers[-2], self.layers[-1]
            if self.free:
                b.x, b.y = a.x + a.img.width, a.y
                self._merge_into(a, [a, b])
                del self.layers[-1]
                self.touch()
                return a
            w = a.img.width + b.img.width
            h = max(a.img.height, b.img.height)
            out = Image.new("RGB", (w, h), (255, 255, 255))
            out.paste(a.img, (0, 0))
            out.paste(b.img, (a.img.width, 0))
            a.set_img(out)
            del self.layers[-1]
            self.touch()
            return a

    def _merge_into(self, target, layers):
        """Flatten `layers` into `target` (stack flow: stacked; free canvas: at their positions)."""
        if not self.free:
            target.set_img(self._flatten(layers))
            return
        x0 = min(l.x for l in layers)
        y0 = min(l.y for l in layers)
        x1 = max(l.x + l.img.width for l in layers)
        y1 = max(l.y + l.img.height for l in layers)
        out = Image.new("RGB", (x1 - x0, y1 - y0), (255, 255, 255))
        for l in layers:
            out.paste(l.img, (l.x - x0, l.y - y0))
        target.set_img(out)
        target.x, target.y = x0, y0

    @staticmethod
    def _flatten(layers):
        mw = max(l.img.width for l in layers)
        th = sum(l.img.height for l in layers)
        out = Image.new("RGB", (mw, th), (255, 255, 255))
        y = 0
        for l in layers:
            out.paste(l.img, (_x_for(l.align, mw, l.img.width), y))
            y += l.img.height
        return out

    # ---- composition --------------------------------------------------------
    def _rects(self, k=1.0):
        """[(layer, pil, x, y)] on a canvas whose top-left is (0,0), plus canvas w,h — all at scale k."""
        vis = self.visible_layers()
        parts = [(l, l.scaled(k) if k < 0.999 else l.img) for l in vis]
        if not parts:
            return [], 0, 0
        if not self.free:
            mw = max(p.width for _, p in parts)
            y = 0
            out = []
            for l, p in parts:
                out.append((l, p, _x_for(l.align, mw, p.width), y))
                y += p.height
            return out, mw, y
        pos = [(l, p, int(round(l.x * k)), int(round(l.y * k))) for l, p in parts]
        mx = min(x for _, _, x, _ in pos)
        my = min(y for _, _, _, y in pos)
        out = [(l, p, x - mx, y - my) for l, p, x, y in pos]
        return out, max(x + p.width for _, p, x, _ in out), max(y + p.height for _, p, _, y in out)

    def stack_size(self):
        return self.canvas_size()

    def stitched(self, k=1.0):
        """The raw canvas (no logo/header) at scale k."""
        rects, mw, mh = self._rects(k)
        if not rects:
            return Image.new("RGB", (100, 100), "white")
        out = Image.new("RGB", (mw, mh), (255, 255, 255))
        for l, p, x, y in rects:
            out.paste(p, (x, y))
        return out

    def layout(self, k=1.0, header_h=0, page_w=None):
        """Where each visible layer sits on the composed page (pixels at scale k)
        so the UI can map a mouse position to a layer."""
        rects, mw, mh = self._rects(k)
        if not rects:
            return []
        pw = page_w or max(mw, int(MIN_PAGE_WIDTH * k))
        off = (pw - mw) // 2
        return [{"id": l.id, "x": off + x, "y": header_h + y, "w": p.width, "h": p.height,
                 "sx": l.img.width / float(p.width), "sy": l.img.height / float(p.height)}
                for l, p, x, y in rects]

    def compose(self, k, paper_logo, logo_scale, text_scale, show_header, header_text):
        """Page = logo + optional header line + stacked clips.  k=1 reproduces the
        old _build_full_page byte-for-byte in layout; k<1 is a faithful preview.
        Returns (canvas, header_height, page_width)."""
        merged = self.stitched(k)
        final_mw = max(merged.width, int(round(MIN_PAGE_WIDTH * k)))
        logo_img = None
        if paper_logo is not None:
            try:
                tw = max(1, int(final_mw * logo_scale))
                th = max(1, int(paper_logo.height * (tw / paper_logo.width)))
                logo_img = paper_logo.resize(
                    (tw, th), Image.Resampling.BILINEAR if k < 0.999 else Image.Resampling.LANCZOS)
            except Exception:
                logo_img = None
        lh = logo_img.size[1] if logo_img else int(round(40 * k))
        fs = max(int(round(12 * k)), int((final_mw * 0.03) * text_scale))
        hh = (lh + fs + int(round(25 * k))) if show_header else (lh + int(round(15 * k)))
        canvas = Image.new("RGB", (final_mw, merged.height + hh + int(round(10 * k))), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        if logo_img:
            canvas.paste(logo_img, ((final_mw - logo_img.size[0]) // 2, int(round(10 * k))))
        if show_header:
            font = header_font(fs)
            tw = draw.textbbox((0, 0), header_text, font=font)[2]
            draw.text(((final_mw - tw) // 2, lh + int(round(12 * k))), header_text, fill="black", font=font)
        canvas.paste(merged, ((final_mw - merged.width) // 2, hh))
        return canvas, hh, final_mw

    # ---- edits (all take LAYER-pixel coordinates) --------------------------
    def _layer_edit(self, lid):
        l = self.get(lid)
        return l, l.img.copy()

    def op_crop(self, lid, shape):
        with self.lock:
            l = self.get(lid)
            if not shape_is_big_enough(shape, l.img.size):
                return False
            x1, y1, x2, y2 = shape_bbox(shape, l.img.size)
            self.checkpoint()
            if shape.get("type", "rect") in ("poly", "ellipse"):
                # non-rectangular crop: keep the shape, white outside
                m = make_mask(l.img.size, shape).crop((x1, y1, x2, y2))
                piece = l.img.crop((x1, y1, x2, y2))
                white = Image.new("RGB", piece.size, (255, 255, 255))
                piece = Image.composite(piece, white, m)
            else:
                piece = l.img.crop((x1, y1, x2, y2))
            l.set_img(piece)
            if self.free:
                l.x += x1
                l.y += y1
            self.touch()
            return True

    def _paint(self, lid, shape, color, alpha=255):
        l, img = self._layer_edit(lid)
        if not shape_is_big_enough(shape, img.size, 1):
            return False
        self.checkpoint()
        mask = make_mask(img.size, shape)
        if alpha < 255:
            mask = mask.point(lambda v, a=alpha: v * a // 255)
        solid = Image.new("RGB", img.size, color)
        l.set_img(Image.composite(solid, img, mask))
        self.touch()
        return True

    def op_clone(self, lid, shape, dx, dy):
        """Clone stamp: paint with pixels taken from (dx, dy) away."""
        with self.lock:
            l, img = self._layer_edit(lid)
            if not shape_is_big_enough(shape, img.size, 1):
                return False
            self.checkpoint()
            mask = make_mask(img.size, shape)
            src = img.transform(img.size, Image.AFFINE, (1, 0, dx, 0, 1, dy), resample=Image.BILINEAR, fillcolor=(255, 255, 255))
            l.set_img(Image.composite(src, img, mask))
            self.touch()
            return True

    def op_erase(self, lid, shape):
        with self.lock:
            return self._paint(lid, shape, (255, 255, 255))

    def op_redact(self, lid, shape):
        with self.lock:
            return self._paint(lid, shape, (0, 0, 0))

    def op_highlight(self, lid, shape, color=(255, 235, 59), alpha=100):
        with self.lock:
            return self._paint(lid, shape, tuple(color), alpha)

    def op_fill(self, lid, shape, color):
        with self.lock:
            return self._paint(lid, shape, tuple(color))

    def op_copy(self, lid, shape):
        """Selection → internal clipboard (RGBA, transparent outside the shape)."""
        with self.lock:
            l = self.get(lid)
            x1, y1, x2, y2 = shape_bbox(shape, l.img.size)
            if x2 - x1 < 2 or y2 - y1 < 2:
                return False
            mask = make_mask(l.img.size, shape).crop((x1, y1, x2, y2))
            piece = l.img.crop((x1, y1, x2, y2)).convert("RGBA")
            piece.putalpha(mask)
            self.clipboard = piece
            return True

    def op_cut(self, lid, shape):
        with self.lock:
            if not self.op_copy(lid, shape):
                return False
            return self._paint(lid, shape, (255, 255, 255))

    def op_extract(self, lid, shape, cut=True, name="Selection"):
        """Layer via copy/cut: the selection becomes its own layer (above the
        source); with cut=True the source is whited-out underneath."""
        with self.lock:
            if not self.op_copy(lid, shape):
                return None
            self.checkpoint()
            i = self.index(lid)
            src = self.layers[i]
            piece = self.clipboard
            flat = Image.new("RGB", piece.size, (255, 255, 255))
            flat.paste(piece, (0, 0), piece)
            if cut:
                m = make_mask(src.img.size, shape)
                solid = Image.new("RGB", src.img.size, (255, 255, 255))
                src.set_img(Image.composite(solid, src.img, m))
            n = Layer(flat, name)
            if self.free:
                bx1, by1, _, _ = shape_bbox(shape, src.img.size)
                n.x, n.y = src.x + bx1, src.y + by1
            self.layers.insert(i + 1, n)
            self.touch()
            return n

    def op_paste_clipboard(self, name="Pasted"):
        with self.lock:
            if self.clipboard is None:
                return None
            piece = self.clipboard
            flat = Image.new("RGB", piece.size, (255, 255, 255))
            flat.paste(piece, (0, 0), piece)
            return self.add(flat, name)

    def op_move_selection(self, lid, shape, dx, dy, scale=1.0, cut=True):
        """Lift the selected pixels and drop them dx,dy away (optionally scaled
        about their centre).  Paper-white is left behind when cut=True.  Content
        pushed past the layer edge grows the layer instead of being lost."""
        with self.lock:
            l = self.get(lid)
            x1, y1, x2, y2 = shape_bbox(shape, l.img.size)
            if x2 - x1 < 2 or y2 - y1 < 2:
                return False
            mask_full = make_mask(l.img.size, shape)
            piece = l.img.crop((x1, y1, x2, y2)).convert("RGBA")
            piece.putalpha(mask_full.crop((x1, y1, x2, y2)))
            self.checkpoint()
            base = l.img.copy()
            if cut:
                base = Image.composite(Image.new("RGB", base.size, (255, 255, 255)), base, mask_full)
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            if abs(scale - 1.0) > 1e-3:
                nw = max(1, int(round(piece.width * scale)))
                nh = max(1, int(round(piece.height * scale)))
                piece = piece.resize((nw, nh), Image.Resampling.LANCZOS)
            px = int(round(cx + dx - piece.width / 2.0))
            py = int(round(cy + dy - piece.height / 2.0))
            # grow canvas (white) if the piece leaves the layer
            gl = max(0, -px)
            gt = max(0, -py)
            gr = max(0, px + piece.width - base.width)
            gb = max(0, py + piece.height - base.height)
            if gl or gt or gr or gb:
                grown = Image.new("RGB", (base.width + gl + gr, base.height + gt + gb), (255, 255, 255))
                grown.paste(base, (gl, gt))
                base = grown
                px += gl
                py += gt
                if self.free:
                    l.x -= gl
                    l.y -= gt
            base.paste(piece, (px, py), piece)
            l.set_img(base)
            self.touch()
            return True

    def op_stamp(self, lid, x, y, rgba):
        """Paste a client-rendered RGBA bitmap (text tool: the browser shapes
        Bangla text correctly, PIL without raqm does not)."""
        with self.lock:
            l, img = self._layer_edit(lid)
            self.checkpoint()
            rgba = rgba.convert("RGBA")
            img.paste(rgba, (int(x), int(y)), rgba)
            l.set_img(img)
            self.touch()
            return True

    def op_resize_layer(self, lid, factor):
        with self.lock:
            l = self.get(lid)
            factor = float(factor)
            if factor <= 0 or abs(factor - 1) < 1e-3:
                return False
            self.checkpoint()
            nw, nh = max(1, int(l.img.width * factor)), max(1, int(l.img.height * factor))
            l.set_img(l.img.resize((nw, nh), Image.Resampling.LANCZOS))
            self.touch()
            return True

    # filters ---------------------------------------------------------------
    def op_filter(self, lid, name, **kw):
        """Whole-layer filters: trim, clean, pad, sharpen, upscale, levels,
        rotate, flip, grayscale, invert, autocontrast."""
        with self.lock:
            l = self.get(lid)
            src = l.img
            if name == "trim":
                out = auto_trim(src)
            elif name == "clean":
                out = cv_remove_lines(src)
            elif name == "pad":
                out = pad_image(src, int(kw.get("n", 15)))
            elif name == "polish":
                out = polish(src)
            elif name == "sharpen":
                out = ImageEnhance.Contrast(ImageEnhance.Sharpness(src).enhance(2.0)).enhance(1.1)
            elif name == "upscale":
                up = src.resize((src.width * 2, src.height * 2), Image.Resampling.LANCZOS)
                out = up.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
            elif name == "levels":
                out = src
                b, c, g = float(kw.get("brightness", 1.0)), float(kw.get("contrast", 1.0)), float(kw.get("gamma", 1.0))
                if abs(b - 1) > 1e-3:
                    out = ImageEnhance.Brightness(out).enhance(b)
                if abs(c - 1) > 1e-3:
                    out = ImageEnhance.Contrast(out).enhance(c)
                if abs(g - 1) > 1e-3:
                    lut = [int(255 * ((i / 255.0) ** (1.0 / g))) for i in range(256)] * 3
                    out = out.point(lut)
            elif name == "rotate":
                out = src.rotate(-int(kw.get("deg", 90)), expand=True, fillcolor=(255, 255, 255))
            elif name == "flip":
                out = ImageOps.mirror(src) if kw.get("axis", "h") == "h" else ImageOps.flip(src)
            elif name == "grayscale":
                out = ImageOps.grayscale(src).convert("RGB")
            elif name == "invert":
                out = ImageOps.invert(src)
            elif name == "autocontrast":
                out = ImageOps.autocontrast(src, cutoff=1)
            elif name == "deskew":
                out = src.rotate(float(kw.get("deg", 0)), resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))
                out = auto_trim(out) if kw.get("trim", True) else out
            else:
                raise ValueError(f"unknown filter {name!r}")
            if out.size == src.size and out is src:
                return False
            self.checkpoint()
            if self.free and out.size != src.size:
                l.x += (src.width - out.width) // 2
                l.y += (src.height - out.height) // 2
            l.set_img(out)
            self.touch()
            return True


def _x_for(align, page_w, w):
    if align == "left":
        return 0
    if align == "right":
        return page_w - w
    return (page_w - w) // 2


# ─────────────────────────────────────────────────────────────────────────────
#  small helpers shared by the engine
# ─────────────────────────────────────────────────────────────────────────────
def jpeg_bytes(img, quality=82):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _enc(img, q, sub):
    from PIL import ImageFile
    if ImageFile.MAXBLOCK < 64 * 1024 * 1024:      # big, noisy images overflow PIL's default buffer with optimize=True
        ImageFile.MAXBLOCK = 64 * 1024 * 1024
    buf = io.BytesIO()
    try:
        img.save(buf, "JPEG", quality=int(q), optimize=True, subsampling=sub)
    except OSError:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=int(q), optimize=False, subsampling=sub)
    return buf.getvalue()


def fit_jpeg(img, target_kb=500, big_src_kb=4096, big_target_kb=780, q_floor=60, q_ceiling=92):
    """Smart quality fitter. Finds the HIGHEST JPEG quality that still lands under the
    size target, so a clip is as sharp as the limit allows.
      * normal clips      -> under target_kb (default 500)
      * very heavy clips (a near-lossless encode above big_src_kb) -> under big_target_kb
        (700-800 KB) — squeezing those to 500 KB would smear the text
      * if even q_floor is too big, the picture is scaled down in small steps (never below
        55% width) while keeping quality at the floor + 8, which keeps text readable
    Returns (jpeg_bytes, info dict)."""
    img = img.convert("RGB")
    sub = lambda q: 2 if q < 90 else 0           # 4:2:0 saves ~30% with no visible text loss
    ref_kb = len(_enc(img, 95, 0)) / 1024.0 if img.width * img.height > 1_500_000 else None
    if ref_kb is None:
        ref_kb = len(_enc(img, 95, 0)) / 1024.0
    target = float(big_target_kb if ref_kb > big_src_kb else target_kb)
    info = {"target_kb": int(target), "src_kb": int(ref_kb), "scaled": 1.0}

    def best_q(im):
        lo, hi, best = q_floor, q_ceiling, None
        data = _enc(im, hi, sub(hi))
        if len(data) / 1024.0 <= target:
            return hi, data
        while lo <= hi:
            mid = (lo + hi) // 2
            d = _enc(im, mid, sub(mid))
            if len(d) / 1024.0 <= target:
                best = (mid, d); lo = mid + 1
            else:
                hi = mid - 1
        return best if best else (None, None)

    q, data = best_q(img)
    scale = 1.0
    if data is None:
        # size at the floor quality tells how much smaller the picture must get (size ~ area)
        floor_kb = len(_enc(img, q_floor, sub(q_floor))) / 1024.0
        scale = max(0.55, min(0.97, (target / floor_kb) ** 0.5 * 0.97))
        for _ in range(4):
            im = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
            q, data = best_q(im)
            if data is not None or scale <= 0.55:
                break
            scale = max(0.55, round(scale - 0.05, 2))
        if data is None:
            q = q_floor
            data = _enc(im, q, sub(q))
        scale = round(scale, 2)
    info.update(q=int(q), kb=int(len(data) / 1024), scaled=scale)
    return data, info


def estimate_skew(img, max_deg=6.0):
    """Skew of scanned text in degrees (PIL rotate() sign: pass this value to rotate to
    straighten). Projection-profile search: the right angle makes text lines line up, so the
    row-sum profile has its sharpest peaks. Returns None if there is no clear text."""
    g = ImageOps.grayscale(img)
    if g.width > 900:
        g = g.resize((900, max(1, int(g.height * 900 / g.width))), Image.Resampling.BILINEAR)
    a = np.asarray(g, dtype=np.float32)
    if a.size == 0 or a.std() < 8:
        return None
    thr = a.mean() - 0.35 * a.std()
    bw = Image.fromarray(((a < thr) * 255).astype("uint8"))

    def score(deg):
        r = np.asarray(bw.rotate(deg, resample=Image.Resampling.NEAREST, fillcolor=0), dtype=np.float32) / 255.0
        p = r.sum(axis=1)
        return float(np.sum(np.diff(p) ** 2))

    best, bs = 0.0, -1.0
    d = -max_deg
    while d <= max_deg + 1e-6:
        s = score(d)
        if s > bs:
            best, bs = d, s
        d += 0.5
    d = best - 0.5
    while d <= best + 0.5 + 1e-6:
        s = score(d)
        if s > bs:
            best, bs = d, s
        d += 0.1
    base = score(0.0)
    if bs <= base * 1.03:            # no real improvement over "as is"
        return None
    return round(best, 2)
