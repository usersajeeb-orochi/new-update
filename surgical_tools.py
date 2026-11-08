import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageChops, ImageGrab, ImageOps, ImageEnhance
import math
import os
import zlib
# Windows are sized through nab_ui_scale.fit() instead of hardcoded
# pixels — see nab_ui_scale.py for why (small monitors / DPI).
import nab_ui_scale

try:
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:
    HAS_CV = False

# --- THEME ---
C_BG = "#050505"
C_SURFACE = "#121212"
C_ACCENT = "#ff9500"
C_ACCENT_HOVER = "#1E45BB"
C_TEXT_MAIN = "#FF3131"
C_TEXT_DIM = "#915e10"
C_BORDER = "#2A2A2A"
C_DANGER = "#D32F2F"
C_SUCCESS = "#10B981"

# --- DEEP MEMORY COMPRESSION ---
def compress_img(img):
    if not img: return None
    return {"size": img.size, "mode": img.mode, "data": zlib.compress(img.tobytes(), level=1)}

def decompress_img(c_img):
    if not c_img: return None
    return Image.frombytes(c_img["mode"], c_img["size"], zlib.decompress(c_img["data"]))

class SurgicalWorkspace(ctk.CTkToplevel):
    def __init__(self, parent, on_commit_callback):
        super().__init__(parent)
        self.title("Surgical Workspace - PRO TOOLS")
        nab_ui_scale.fit(self, 1450, 900, min_w=899, min_h=558, parent=self.master)
        self.configure(fg_color="#0A0A0A")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.parent = parent
        self.on_commit = on_commit_callback

        # Viewport State
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0

        # Image & Mask State
        self.base_img = None
        self.working_img = None
        self.selection_mask = None
        self.tk_img = None
        self.rotation_angle = 0.0

        # Memory Stack (Compressed)
        self.undo_stack = []
        self.redo_stack = []

        # Tool State
        self.current_tool = "marquee"
        self.grid_active = False
        self.space_pressed = False
        self.mod_shift = False
        self.mod_alt = False
        self.brush_size = 40
        self.wand_tolerance = 15

        # Dragging State
        self.marquee_mode = "replace"
        self.marquee_start_img_pt = None
        self.marquee_start_screen_pt = None
        self.start_x = 0
        self.start_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.last_brush_pt = None
        self.lasso_points = []
        self.lasso_screen_points = []

        # Clone Stamp State
        self.stamp_src = None

        # FIX 10: Image ref storage to prevent GC
        self._brush_tk_ref = None
        self._stamp_tk_ref = None

        self.build_toolbar()

        self.canvas = tk.Canvas(self, bg="#111", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        # FIX 10: Brightness/Contrast panel
        self.adj_frame = ctk.CTkFrame(self, fg_color="#121212", height=40, corner_radius=0)
        self.adj_frame.pack(side="bottom", fill="x")

        ctk.CTkLabel(self.adj_frame, text="Brightness:", font=("Segoe UI", 10), text_color="#888").pack(side="left", padx=(10,2), pady=5)
        self.brightness_var = ctk.DoubleVar(value=1.0)
        self.brightness_slider = ctk.CTkSlider(self.adj_frame, variable=self.brightness_var, from_=0.2, to=2.5,
                                                width=120, button_color=C_ACCENT, progress_color=C_ACCENT,
                                                command=self.apply_adjustments)
        self.brightness_slider.pack(side="left", pady=5)

        ctk.CTkLabel(self.adj_frame, text="Contrast:", font=("Segoe UI", 10), text_color="#888").pack(side="left", padx=(15,2))
        self.contrast_var = ctk.DoubleVar(value=1.0)
        self.contrast_slider = ctk.CTkSlider(self.adj_frame, variable=self.contrast_var, from_=0.2, to=3.0,
                                              width=120, button_color=C_ACCENT, progress_color=C_ACCENT,
                                              command=self.apply_adjustments)
        self.contrast_slider.pack(side="left", pady=5)

        ctk.CTkButton(self.adj_frame, text="Apply", width=60, height=28, fg_color=C_ACCENT,
                      font=("Segoe UI", 10, "bold"), command=self.commit_adjustments).pack(side="left", padx=5)
        ctk.CTkButton(self.adj_frame, text="Reset", width=60, height=28, fg_color="#333",
                      font=("Segoe UI", 10, "bold"), command=self.reset_adjustments).pack(side="left", padx=2)

        # FIX 11: Zoom to fit button in adj bar
        ctk.CTkButton(self.adj_frame, text="⊡ Fit", width=60, height=28, fg_color="#333",
                      font=("Segoe UI", 10, "bold"), command=self.zoom_to_fit).pack(side="right", padx=10)
        ctk.CTkLabel(self.adj_frame, text="Zoom to Fit (F)", font=("Segoe UI", 9), text_color="#555").pack(side="right")

        self.info_label = ctk.CTkLabel(
            self,
            text="TOOL: MARQUEE | [ and ] to resize brush/wand | Ctrl+Shift+I: Invert Mask | Del: Erase Inside",
            font=("Consolas", 12, "bold"), text_color="#FF3131"
        )
        self.info_label.place(relx=0.02, rely=0.93)

        self.setup_bindings()
        self.set_tool("marquee")
        self.after(100, self.focus_force)

    def build_toolbar(self):
        self.toolbar = ctk.CTkFrame(self, fg_color="#121212", height=50, corner_radius=0,
                                    border_color="#2A2A2A", border_width=1)
        self.toolbar.pack(side="top", fill="x")

        self.btn_paste = ctk.CTkButton(self.toolbar, text="📋 Paste", width=80, fg_color="#2A2A2A",
                                       hover_color="#444", font=("Segoe UI", 12, "bold"),
                                       command=self.grab_from_clipboard)
        self.btn_paste.pack(side="left", padx=(10, 5), pady=8)

        ctk.CTkLabel(self.toolbar, text="|", text_color="#444").pack(side="left", padx=5)

        self.btn_marquee = ctk.CTkButton(self.toolbar, text="⬚ Marq (M)", width=85,
                                          font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("marquee"))
        self.btn_marquee.pack(side="left", padx=3, pady=8)

        self.btn_lasso = ctk.CTkButton(self.toolbar, text="⌇ Lasso (L)", width=85,
                                        font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("lasso"))
        self.btn_lasso.pack(side="left", padx=3, pady=8)

        self.btn_wand = ctk.CTkButton(self.toolbar, text="🪄 Wand (W)", width=80,
                                       font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("wand"))
        self.btn_wand.pack(side="left", padx=3, pady=8)

        self.btn_brush = ctk.CTkButton(self.toolbar, text="🖌 Brush (B)", width=80,
                                        font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("brush"))
        self.btn_brush.pack(side="left", padx=3, pady=8)

        self.btn_stamp = ctk.CTkButton(self.toolbar, text="◎ Stamp (S)", width=80,
                                        font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("stamp"))
        self.btn_stamp.pack(side="left", padx=3, pady=8)

        self.btn_eraser = ctk.CTkButton(self.toolbar, text="▤ Fill (E)", width=80,
                                         font=("Segoe UI", 11, "bold"), command=lambda: self.set_tool("eraser"))
        self.btn_eraser.pack(side="left", padx=3, pady=8)

        ctk.CTkLabel(self.toolbar, text="|", text_color="#444").pack(side="left", padx=5)

        self.btn_undo = ctk.CTkButton(self.toolbar, text="⟲ (Ctrl+Z)", width=80, fg_color="#333",
                                       font=("Segoe UI", 11, "bold"), command=self.undo)
        self.btn_undo.pack(side="left", padx=2, pady=8)

        self.btn_redo = ctk.CTkButton(self.toolbar, text="⟳ (Ctrl+Y)", width=80, fg_color="#333",
                                       font=("Segoe UI", 11, "bold"), command=self.redo)
        self.btn_redo.pack(side="left", padx=2, pady=8)

        ctk.CTkLabel(self.toolbar, text="|", text_color="#444").pack(side="left", padx=5)

        self.btn_grid = ctk.CTkButton(self.toolbar, text="# Grid (G)", width=70, fg_color="#333",
                                       font=("Segoe UI", 11, "bold"), command=self.toggle_grid)
        self.btn_grid.pack(side="left", padx=5, pady=8)

        self.btn_commit = ctk.CTkButton(self.toolbar, text="Commit to Main (Ctrl+F)", width=160,
                                         fg_color="#10B981", hover_color="#059669",
                                         font=("Impact", 14), command=self.commit_to_main)
        self.btn_commit.pack(side="right", padx=10, pady=8)

        self.btn_crop = ctk.CTkButton(self.toolbar, text="Local Crop (Enter)", width=120,
                                       fg_color="#FF9500", hover_color="#CC7A00",
                                       font=("Segoe UI", 11, "bold"), command=self.local_crop_and_clean)
        self.btn_crop.pack(side="right", padx=5, pady=8)

        self.btn_clear = ctk.CTkButton(self.toolbar, text="Clear (Esc)", width=80,
                                        fg_color="#D32F2F", hover_color="#B71C1C",
                                        font=("Segoe UI", 11, "bold"), command=self.clear_workspace)
        self.btn_clear.pack(side="right", padx=5, pady=8)

    def grab_from_clipboard(self, event=None):
        try:
            img_data = ImageGrab.grabclipboard()
            if isinstance(img_data, Image.Image):
                self.paste_to_workspace(img_data)
            elif isinstance(img_data, list) and len(img_data) > 0:
                if os.path.isfile(img_data[0]):
                    img_file = ImageOps.exif_transpose(Image.open(img_data[0]))
                    self.paste_to_workspace(img_file)
        except Exception:
            pass

    # --- COORDINATE MATH ---
    def get_img_coords(self, screen_x, screen_y):
        return (screen_x - self.pan_x) / self.zoom_level, (screen_y - self.pan_y) / self.zoom_level

    def get_screen_coords(self, img_x, img_y):
        return (img_x * self.zoom_level) + self.pan_x, (img_y * self.zoom_level) + self.pan_y

    def snap_to_grid(self, val, step=50):
        if not self.grid_active: return val
        return round(val / step) * step

    # --- ZLIB COMPRESSED STACK ---
    def save_state(self):
        if not self.working_img: return
        if len(self.undo_stack) > 20: self.undo_stack.pop(0)
        self.undo_stack.append({
            "img": compress_img(self.working_img),
            "mask": compress_img(self.selection_mask) if self.selection_mask else None,
            "rot": self.rotation_angle
        })
        if len(self.redo_stack) > 20: self.redo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self, event=None):
        if not self.undo_stack: return
        self.redo_stack.append({
            "img": compress_img(self.working_img),
            "mask": compress_img(self.selection_mask) if self.selection_mask else None,
            "rot": self.rotation_angle
        })
        state = self.undo_stack.pop()
        self.working_img = decompress_img(state["img"])
        self.base_img = self.working_img.copy()
        self.selection_mask = decompress_img(state["mask"]) if state["mask"] else None
        if not self.selection_mask: self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.rotation_angle = state["rot"]
        self.render()

    def redo(self, event=None):
        if not self.redo_stack: return
        self.undo_stack.append({
            "img": compress_img(self.working_img),
            "mask": compress_img(self.selection_mask) if self.selection_mask else None,
            "rot": self.rotation_angle
        })
        state = self.redo_stack.pop()
        self.working_img = decompress_img(state["img"])
        self.base_img = self.working_img.copy()
        self.selection_mask = decompress_img(state["mask"]) if state["mask"] else None
        if not self.selection_mask: self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.rotation_angle = state["rot"]
        self.render()

    # --- BINDINGS ---
    def setup_bindings(self):
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)

        self.bind("<KeyPress>", self.on_key_press)
        self.bind("<KeyRelease>", self.on_key_release)

        self.bind("<Control-f>", self.commit_to_main); self.bind("<Control-F>", self.commit_to_main)
        self.bind("<Control-v>", self.grab_from_clipboard); self.bind("<Control-V>", self.grab_from_clipboard)
        self.bind("<Return>", self.local_crop_and_clean)
        self.bind("<Delete>", self.delete_selection); self.bind("<BackSpace>", self.delete_selection)
        self.bind("<Control-d>", self.deselect); self.bind("<Control-D>", self.deselect)
        self.bind("<Control-Shift-I>", self.invert_selection); self.bind("<Control-Shift-i>", self.invert_selection)
        self.bind("<Control-z>", self.undo); self.bind("<Control-Z>", self.undo)
        self.bind("<Control-y>", self.redo); self.bind("<Control-Y>", self.redo)
        self.bind("<Escape>", lambda e: self.clear_workspace())

        self.bind("m", lambda e: self.set_tool("marquee")); self.bind("M", lambda e: self.set_tool("marquee"))
        self.bind("l", lambda e: self.set_tool("lasso")); self.bind("L", lambda e: self.set_tool("lasso"))
        self.bind("w", lambda e: self.set_tool("wand")); self.bind("W", lambda e: self.set_tool("wand"))
        self.bind("b", lambda e: self.set_tool("brush")); self.bind("B", lambda e: self.set_tool("brush"))
        self.bind("s", lambda e: self.set_tool("stamp")); self.bind("S", lambda e: self.set_tool("stamp"))
        self.bind("e", lambda e: self.set_tool("eraser")); self.bind("E", lambda e: self.set_tool("eraser"))
        self.bind("g", lambda e: self.toggle_grid()); self.bind("G", lambda e: self.toggle_grid())
        self.bind("a", lambda e: self.auto_snap()); self.bind("A", lambda e: self.auto_snap())
        self.bind("r", lambda e: self.rotate_image(0.5)); self.bind("R", lambda e: self.rotate_image(-0.5))
        self.bind("f", lambda e: self.zoom_to_fit()); self.bind("F", lambda e: self.zoom_to_fit())

        self.bind("bracketleft", lambda e: self.adjust_tool_size(-5))
        self.bind("bracketright", lambda e: self.adjust_tool_size(5))

    def on_key_press(self, event):
        if event.keysym == 'space':
            self.space_pressed = True
            self.canvas.configure(cursor="fleur")
        if event.keysym in ("Shift_L", "Shift_R"): self.mod_shift = True
        if event.keysym in ("Alt_L", "Alt_R", "Option_L", "Option_R"): self.mod_alt = True

    def on_key_release(self, event):
        if event.keysym == 'space':
            self.space_pressed = False
            self.set_tool(self.current_tool)
        if event.keysym in ("Shift_L", "Shift_R"): self.mod_shift = False
        if event.keysym in ("Alt_L", "Alt_R", "Option_L", "Option_R"): self.mod_alt = False

    # --- STATE MANAGEMENT ---
    def paste_to_workspace(self, img):
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.base_img = img.convert("RGB")
        self.working_img = self.base_img.copy()
        self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.zoom_level = 1.0
        self.rotation_angle = 0.0
        self.brightness_var.set(1.0)
        self.contrast_var.set(1.0)
        self.update_idletasks()
        self.zoom_to_fit()
        self.render()

    def zoom_to_fit(self, event=None):
        if not self.working_img: return
        c_w = self.canvas.winfo_width()
        c_h = self.canvas.winfo_height()
        if c_w < 10 or c_h < 10:
            self.after(100, self.zoom_to_fit)
            return
        i_w, i_h = self.working_img.size
        self.zoom_level = min(c_w / i_w, c_h / i_h) * 0.95
        self.pan_x = (c_w - int(i_w * self.zoom_level)) // 2
        self.pan_y = (c_h - int(i_h * self.zoom_level)) // 2
        self.render()

    def set_tool(self, tool_name):
        self.current_tool = tool_name
        self.canvas.delete("tool_cursor")
        if tool_name == "lasso":
            self.lasso_points = []
            self.lasso_screen_points = []

        active_col = "#FF9500"
        default_col = "#333"
        self.btn_marquee.configure(fg_color=active_col if tool_name == "marquee" else default_col)
        self.btn_lasso.configure(fg_color=active_col if tool_name == "lasso" else default_col)
        self.btn_wand.configure(fg_color=active_col if tool_name == "wand" else default_col)
        self.btn_brush.configure(fg_color=active_col if tool_name == "brush" else default_col)
        self.btn_stamp.configure(fg_color=active_col if tool_name == "stamp" else default_col)
        self.btn_eraser.configure(fg_color=active_col if tool_name == "eraser" else default_col)

        if not self.space_pressed:
            if tool_name in ["marquee", "wand", "lasso"]: self.canvas.configure(cursor="crosshair")
            elif tool_name in ["stamp", "brush"]: self.canvas.configure(cursor="none")
            elif tool_name == "eraser": self.canvas.configure(cursor="tcross")

        self.update_status()

    def update_status(self):
        size_metric = self.wand_tolerance if self.current_tool == "wand" else self.brush_size
        size_label = "Tolerance" if self.current_tool == "wand" else "Brush Size"
        self.info_label.configure(
            text=f"TOOL: {self.current_tool.upper()} | [ ] adjust {size_label}: {size_metric} | Ctrl+Shift+I: Invert | Del: Erase | F: Fit"
        )

    def toggle_grid(self):
        self.grid_active = not self.grid_active
        self.btn_grid.configure(fg_color="#1E45BB" if self.grid_active else "#333")
        self.render()

    def rotate_image(self, angle):
        if not self.base_img: return
        self.save_state()
        self.rotation_angle += angle
        self.working_img = self.base_img.rotate(-self.rotation_angle, expand=True,
                                                  fillcolor="white", resample=Image.Resampling.BICUBIC)
        self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.render()

    def adjust_tool_size(self, delta):
        if self.current_tool == "wand":
            self.wand_tolerance = max(1, min(255, self.wand_tolerance + delta))
        else:
            self.brush_size = max(2, min(500, self.brush_size + delta))
        self.update_status()

    # FIX 10: Brightness/Contrast in Surgical
    def apply_adjustments(self, *_):
        if not self.base_img: return
        img = ImageEnhance.Brightness(self.base_img).enhance(self.brightness_var.get())
        img = ImageEnhance.Contrast(img).enhance(self.contrast_var.get())
        self.working_img = img
        self.render()

    def commit_adjustments(self):
        if not self.working_img: return
        self.save_state()
        self.base_img = self.working_img.copy()
        self.brightness_var.set(1.0)
        self.contrast_var.set(1.0)

    def reset_adjustments(self):
        self.brightness_var.set(1.0)
        self.contrast_var.set(1.0)
        if self.base_img:
            self.working_img = self.base_img.copy()
            self.render()

    # --- RENDERING ---
    def render(self):
        if not self.working_img: return
        w, h = self.working_img.size
        new_w, new_h = max(1, int(w * self.zoom_level)), max(1, int(h * self.zoom_level))

        display_img = self.working_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        self.tk_img = ImageTk.PhotoImage(display_img)

        self.canvas.delete("img_layer", "grid_layer", "ants", "temp_ants", "fast_update", "fast_stamp")
        self.canvas.create_image(self.pan_x, self.pan_y, image=self.tk_img, anchor="nw", tags="img_layer")

        if self.grid_active: self.draw_grid(new_w, new_h)
        self.draw_ants()

        self.canvas.tag_lower("grid_layer")
        self.canvas.tag_lower("img_layer")

    def draw_grid(self, w, h):
        step = int(50 * self.zoom_level)
        if step < 10: return
        for x in range(0, w, step):
            self.canvas.create_line(self.pan_x + x, self.pan_y, self.pan_x + x, self.pan_y + h,
                                    fill="#333", tags="grid_layer")
        for y in range(0, h, step):
            self.canvas.create_line(self.pan_x, self.pan_y + y, self.pan_x + w, self.pan_y + y,
                                    fill="#333", tags="grid_layer")

    def draw_ants(self):
        if not self.selection_mask or not self.selection_mask.getbbox(): return

        if HAS_CV:
            mask_np = np.array(self.selection_mask)
            contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                cnt = cv2.approxPolyDP(cnt, 1.0, True)
                pts = []
                for pt in cnt:
                    sx, sy = self.get_screen_coords(pt[0][0], pt[0][1])
                    pts.extend([sx, sy])
                if len(pts) >= 6:
                    self.canvas.create_polygon(pts, outline="white", fill="", dash=(4, 4), tags="ants", width=1.5)
                    self.canvas.create_polygon(pts, outline="black", fill="", dash=(4, 4), dashoffset=4, tags="ants", width=1.5)
        else:
            bbox = self.selection_mask.getbbox()
            sx1, sy1 = self.get_screen_coords(bbox[0], bbox[1])
            sx2, sy2 = self.get_screen_coords(bbox[2], bbox[3])
            self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="white", dash=(4, 4), tags="ants", width=1.5)
            self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="black", dash=(4, 4), dashoffset=4, tags="ants", width=1.5)

    # --- VIEWPORT NAVIGATION ---
    def on_mouse_wheel(self, event):
        if not self.working_img: return
        factor = 1 / 1.15 if (event.num == 5 or event.delta < 0) else 1.15
        new_zoom = self.zoom_level * factor
        if new_zoom < 0.05 or new_zoom > 30.0: return

        mx, my = event.x, event.y
        ix, iy = self.get_img_coords(mx, my)

        self.zoom_level = new_zoom
        self.pan_x = mx - (ix * self.zoom_level)
        self.pan_y = my - (iy * self.zoom_level)

        self.render()
        self.on_mouse_move(event)

    # --- TOOL LOGIC ---
    def on_press(self, event):
        if not self.working_img: return

        if self.space_pressed:
            self.pan_start_x, self.pan_start_y = event.x, event.y
            return

        ix, iy = self.get_img_coords(event.x, event.y)

        if self.current_tool == "marquee":
            is_inside = False
            if self.selection_mask and self.selection_mask.getbbox():
                try: is_inside = self.selection_mask.getpixel((int(ix), int(iy))) > 0
                except: pass

            if is_inside and not self.mod_shift and not self.mod_alt:
                self.marquee_mode = "move"
                self.marquee_start_screen_pt = (event.x, event.y)
                self.start_mask = self.selection_mask.copy()
            else:
                self.marquee_start_img_pt = (ix, iy)
                self.start_x, self.start_y = event.x, event.y
                if self.mod_shift: self.marquee_mode = "add"
                elif self.mod_alt: self.marquee_mode = "subtract"
                else:
                    self.marquee_mode = "replace"
                    self.selection_mask = Image.new("L", self.working_img.size, 0)
                    self.render()

        elif self.current_tool == "lasso":
            if self.mod_shift: self.marquee_mode = "add"
            elif self.mod_alt: self.marquee_mode = "subtract"
            else:
                self.marquee_mode = "replace"
                self.selection_mask = Image.new("L", self.working_img.size, 0)
            self.lasso_points = [(ix, iy)]
            self.lasso_screen_points = [(event.x, event.y)]

        elif self.current_tool == "wand":
            self.save_state()
            if not self.mod_shift and not self.mod_alt:
                self.selection_mask = Image.new("L", self.working_img.size, 0)

            if HAS_CV:
                cv_img = cv2.cvtColor(np.array(self.working_img), cv2.COLOR_RGB2BGR)
                h, w = cv_img.shape[:2]
                mask = np.zeros((h + 2, w + 2), np.uint8)
                seed_pt = (int(ix), int(iy))
                if 0 <= seed_pt[0] < w and 0 <= seed_pt[1] < h:
                    tolerance = (self.wand_tolerance, self.wand_tolerance, self.wand_tolerance)
                    cv2.floodFill(cv_img, mask, seed_pt, (255, 255, 255), tolerance, tolerance,
                                  cv2.FLOODFILL_MASK_ONLY | (255 << 8))
                    wand_mask_np = mask[1:-1, 1:-1]
                    wand_mask_pil = Image.fromarray(wand_mask_np)

                    if self.mod_alt:
                        inv_wand = ImageChops.invert(wand_mask_pil)
                        self.selection_mask = ImageChops.darker(self.selection_mask, inv_wand)
                    else:
                        self.selection_mask = ImageChops.lighter(self.selection_mask, wand_mask_pil)
                self.render()

        elif self.current_tool == "brush":
            self.save_state()
            self.last_brush_pt = (ix, iy)
            self.apply_brush(ix, iy, ix, iy)

        elif self.current_tool == "eraser":
            self.save_state()
            temp_img = self.working_img.copy()
            ImageDraw.floodfill(temp_img, (int(ix), int(iy)), (255, 255, 255), thresh=30)
            if self.selection_mask and self.selection_mask.getbbox():
                self.working_img = Image.composite(temp_img, self.working_img, self.selection_mask)
            else:
                self.working_img = temp_img
            self.base_img = self.working_img.copy()
            self.render()

        elif self.current_tool == "stamp":
            if self.mod_alt:
                self.stamp_src = (ix, iy)
            elif self.stamp_src:
                self.save_state()
                self.apply_stamp(ix, iy)

    def on_drag(self, event):
        if not self.working_img: return

        if self.space_pressed:
            dx, dy = event.x - self.pan_start_x, event.y - self.pan_start_y
            self.pan_x += dx
            self.pan_y += dy
            self.pan_start_x, self.pan_start_y = event.x, event.y
            self.canvas.move("img_layer", dx, dy)
            self.canvas.move("grid_layer", dx, dy)
            self.canvas.move("ants", dx, dy)
            return

        ix, iy = self.get_img_coords(event.x, event.y)

        if self.current_tool == "marquee":
            if self.marquee_mode == "move":
                dx = int((event.x - self.marquee_start_screen_pt[0]) / self.zoom_level)
                dy = int((event.y - self.marquee_start_screen_pt[1]) / self.zoom_level)
                new_mask = Image.new("L", self.start_mask.size, 0)
                new_mask.paste(self.start_mask, (dx, dy))
                self.selection_mask = new_mask
                self.render()
            else:
                snap_ix, snap_iy = self.snap_to_grid(ix), self.snap_to_grid(iy)
                cur_sx, cur_sy = self.get_screen_coords(snap_ix, snap_iy)
                self.canvas.delete("temp_ants")
                self.canvas.create_rectangle(self.start_x, self.start_y, cur_sx, cur_sy,
                                             outline="white", dash=(4, 4), tags="temp_ants")
                self.canvas.create_rectangle(self.start_x, self.start_y, cur_sx, cur_sy,
                                             outline="black", dash=(4, 4), dashoffset=4, tags="temp_ants")

        elif self.current_tool == "lasso":
            self.lasso_points.append((ix, iy))
            self.lasso_screen_points.append((event.x, event.y))
            self.canvas.delete("temp_ants")
            if len(self.lasso_screen_points) >= 2:
                flat = [coord for pt in self.lasso_screen_points for coord in pt]
                self.canvas.create_line(flat, fill="white", dash=(4, 4), tags="temp_ants", width=1.5)

        elif self.current_tool == "brush" and self.last_brush_pt:
            self.apply_brush(self.last_brush_pt[0], self.last_brush_pt[1], ix, iy)
            self.last_brush_pt = (ix, iy)
            self.on_mouse_move(event)

        elif self.current_tool == "stamp" and self.stamp_src and not self.mod_alt:
            self.apply_stamp(ix, iy)
            self.on_mouse_move(event)

    def on_release(self, event):
        if self.current_tool == "marquee":
            self.canvas.delete("temp_ants")
            if self.marquee_mode == "move":
                self.save_state()
            else:
                ix, iy = self.get_img_coords(event.x, event.y)
                if self.marquee_start_img_pt and abs(ix - self.marquee_start_img_pt[0]) > 2 and abs(iy - self.marquee_start_img_pt[1]) > 2:
                    if self.marquee_mode in ["add", "subtract"]: self.save_state()
                    x1, x2 = min(ix, self.marquee_start_img_pt[0]), max(ix, self.marquee_start_img_pt[0])
                    y1, y2 = min(iy, self.marquee_start_img_pt[1]), max(iy, self.marquee_start_img_pt[1])
                    x1, y1 = self.snap_to_grid(x1), self.snap_to_grid(y1)
                    x2, y2 = self.snap_to_grid(x2), self.snap_to_grid(y2)
                    draw = ImageDraw.Draw(self.selection_mask)
                    fill_val = 255 if self.marquee_mode in ["add", "replace"] else 0
                    draw.rectangle([x1, y1, x2, y2], fill=fill_val)
            self.render()

        elif self.current_tool == "lasso":
            self.canvas.delete("temp_ants")
            if len(self.lasso_points) >= 3:
                self.save_state()
                lasso_mask = Image.new("L", self.working_img.size, 0)
                draw = ImageDraw.Draw(lasso_mask)
                int_pts = [(int(x), int(y)) for x, y in self.lasso_points]
                fill_val = 255 if self.marquee_mode in ["add", "replace"] else 0
                draw.polygon(int_pts, fill=fill_val)
                if self.marquee_mode == "add":
                    self.selection_mask = ImageChops.lighter(self.selection_mask, lasso_mask)
                elif self.marquee_mode == "subtract":
                    inv = ImageChops.invert(lasso_mask)
                    self.selection_mask = ImageChops.darker(self.selection_mask, inv)
                else:
                    self.selection_mask = lasso_mask
            self.lasso_points = []
            self.lasso_screen_points = []
            self.render()

        elif self.current_tool in ["stamp", "brush"] and not self.mod_alt:
            self.base_img = self.working_img.copy()
            self.render()

    # --- ADVANCED MECHANICS ---
    def apply_brush(self, x1, y1, x2, y2):
        color = (0, 0, 0) if self.mod_alt else (255, 255, 255)
        temp_img = self.working_img.copy()
        draw = ImageDraw.Draw(temp_img)
        draw.line([x1, y1, x2, y2], fill=color, width=self.brush_size, joint="curve")
        draw.ellipse([x2 - self.brush_size / 2, y2 - self.brush_size / 2,
                      x2 + self.brush_size / 2, y2 + self.brush_size / 2], fill=color)

        if self.selection_mask and self.selection_mask.getbbox():
            self.working_img = Image.composite(temp_img, self.working_img, self.selection_mask)
        else:
            self.working_img = temp_img

        # FIX 3: Store ref on self to prevent GC
        sx1, sy1 = self.get_screen_coords(min(x1, x2) - self.brush_size, min(y1, y2) - self.brush_size)
        patch = self.working_img.crop((
            max(0, int(min(x1, x2) - self.brush_size)),
            max(0, int(min(y1, y2) - self.brush_size)),
            min(self.working_img.width, int(max(x1, x2) + self.brush_size)),
            min(self.working_img.height, int(max(y1, y2) + self.brush_size))
        ))
        try:
            self._brush_tk_ref = ImageTk.PhotoImage(
                patch.resize((max(1, int(patch.width * self.zoom_level)),
                               max(1, int(patch.height * self.zoom_level))))
            )
            self.canvas.delete("fast_update")
            self.canvas.create_image(sx1, sy1, image=self._brush_tk_ref, anchor="nw", tags="fast_update")
        except Exception:
            pass

    def apply_stamp(self, dest_x, dest_y):
        if not self.stamp_src: return
        sx, sy = self.stamp_src
        box = (int(sx - self.brush_size // 2), int(sy - self.brush_size // 2),
               int(sx + self.brush_size // 2), int(sy + self.brush_size // 2))
        try:
            patch = self.base_img.crop(box)
            dest_box = (int(dest_x - self.brush_size // 2), int(dest_y - self.brush_size // 2))

            brush_mask = Image.new("L", patch.size, 0)
            ImageDraw.Draw(brush_mask).ellipse([0, 0, patch.width, patch.height], fill=255)

            if self.selection_mask and self.selection_mask.getbbox():
                # FIX 4: Use numpy bitwise AND instead of non-existent logical_and
                if HAS_CV:
                    mask_layer = Image.new("L", self.working_img.size, 0)
                    mask_layer.paste(brush_mask, dest_box)
                    sel_np = np.array(self.selection_mask)
                    mask_np = np.array(mask_layer)
                    combined = Image.fromarray(np.minimum(sel_np, mask_np))
                    self.working_img.paste(patch, dest_box, combined)
                else:
                    self.working_img.paste(patch, dest_box, brush_mask)
            else:
                self.working_img.paste(patch, dest_box, brush_mask)

            # FIX 3: Store ref on self
            self._stamp_tk_ref = ImageTk.PhotoImage(
                patch.resize((max(1, int(self.brush_size * self.zoom_level)),
                               max(1, int(self.brush_size * self.zoom_level))))
            )
            screen_dest = self.get_screen_coords(*dest_box)
            self.canvas.delete("fast_stamp")
            self.canvas.create_image(screen_dest[0], screen_dest[1], image=self._stamp_tk_ref,
                                     anchor="nw", tags="fast_stamp")
        except Exception:
            pass

    def on_mouse_move(self, event):
        if not hasattr(event, 'x') or not hasattr(event, 'y'):
            return
        self.last_move_event = event
        self.canvas.delete("tool_cursor")
        if self.current_tool in ["stamp", "brush"]:
            r = int((self.brush_size / 2) * self.zoom_level)
            color = "#FF9500" if (self.current_tool == "stamp" and self.stamp_src) else "white"
            self.canvas.create_oval(event.x - r, event.y - r, event.x + r, event.y + r,
                                    outline=color, tags="tool_cursor")

    def auto_snap(self):
        if not HAS_CV or not self.working_img or not self.selection_mask: return
        bbox = self.selection_mask.getbbox()
        if not bbox: return
        self.save_state()
        crop = self.working_img.crop(bbox)
        gray = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cx, cy, cw, ch = cv2.boundingRect(np.vstack(contours))
            pad = 10
            new_ix1 = max(0, bbox[0] + cx - pad)
            new_iy1 = max(0, bbox[1] + cy - pad)
            new_ix2 = min(self.working_img.width, bbox[0] + cx + cw + pad)
            new_iy2 = min(self.working_img.height, bbox[1] + cy + ch + pad)
            self.selection_mask.paste(0, (0, 0, self.working_img.width, self.working_img.height))
            ImageDraw.Draw(self.selection_mask).rectangle([new_ix1, new_iy1, new_ix2, new_iy2], fill=255)
            self.render()

    def invert_selection(self, event=None):
        if not self.working_img or not self.selection_mask: return
        self.save_state()
        self.selection_mask = ImageChops.invert(self.selection_mask)
        self.render()

    def deselect(self, event=None):
        if not self.working_img: return
        self.save_state()
        self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.render()

    def delete_selection(self, event=None):
        if not self.working_img or not self.selection_mask or not self.selection_mask.getbbox(): return
        self.save_state()
        white_bg = Image.new("RGB", self.working_img.size, (255, 255, 255))
        self.working_img = Image.composite(white_bg, self.working_img, self.selection_mask)
        self.base_img = self.working_img.copy()
        self.render()

    def local_crop_and_clean(self, event=None):
        if not self.working_img or not self.selection_mask or not self.selection_mask.getbbox(): return
        self.save_state()
        bbox = self.selection_mask.getbbox()
        white_bg = Image.new("RGB", self.working_img.size, (255, 255, 255))
        masked_img = Image.composite(self.working_img, white_bg, self.selection_mask)
        self.working_img = masked_img.crop(bbox)
        self.base_img = self.working_img.copy()
        self.selection_mask = Image.new("L", self.working_img.size, 0)
        self.rotation_angle = 0.0
        self.zoom_to_fit()
        self.render()

    def commit_to_main(self, event=None):
        if not self.working_img: return
        img_to_send = self.working_img
        if self.selection_mask and self.selection_mask.getbbox():
            bbox = self.selection_mask.getbbox()
            white_bg = Image.new("RGB", self.working_img.size, (255, 255, 255))
            masked_img = Image.composite(self.working_img, white_bg, self.selection_mask)
            img_to_send = masked_img.crop(bbox)
        self.on_commit(img_to_send)
        self.clear_workspace()

    def clear_workspace(self, event=None):
        self.base_img = None
        self.working_img = None
        self.selection_mask = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._brush_tk_ref = None
        self._stamp_tk_ref = None
        self.canvas.delete("all")

    def on_close(self):
        self.parent.workspace_instance = None
        self.destroy()
