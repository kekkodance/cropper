import sys
import os
import ctypes
import math
from pathlib import Path
import tkinter as tk
from tkinter import Canvas, NW, BOTH, Button, Frame, Label, IntVar, StringVar, Entry
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageGrab

# --- CONFIGURATION ---
TITLE = "Cropper"
BRAND = "#0047AB"
BG = "#0d0d0d"
CANVAS_BG = "#111111"
BTN_BG = "#1a1a1a"
BTN_ACTIVE_BG = "#2a2a2a"
TEXT_INACTIVE = "#888888"
TEXT_ACTIVE = "#ffffff"
HIGHLIGHT_COLOR = "#FFD700" 
PADDING = 20 
DEFAULT_BANNER_THICKNESS_RATIO = 0.25 
HANDLE_SIZE = 8 # Size of resize handles

# --- HELPER CLASSES ---

class GridTile:
    def __init__(self, path=None, img_obj=None):
        self.path = path if path else "clipboard_image"
        if img_obj:
            self.original = img_obj.convert("RGB")
        elif path and os.path.exists(path):
            self.original = Image.open(path).convert("RGB")
        else:
            self.original = Image.new("RGB", (100, 100), "#333333")
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
        # Tracks the last rendered size to keep zoom position relative during layout changes
        self.last_render_w = 0 
        self.last_render_h = 0
        self.tk_ref = None

    def reset(self):
        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
        self.last_render_w = 0
        self.last_render_h = 0

class ModernSlider(Canvas):
    def __init__(self, master, from_=0, to=100, initial=25, command=None, release_command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.from_ = from_
        self.to = to
        self.value = initial
        self.command = command
        self.release_command = release_command
        self.configure(bg=BG, highlightthickness=0, height=30)
        self.bind("<Configure>", self.draw)
        self.bind("<Button-1>", self.move_to_click)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.w = 0; self.h = 30; self.padding = 10

    def get(self): return self.value
    def set_value(self, val):
        self.value = max(self.from_, min(self.to, val))
        self.draw()

    def val_to_x(self, val):
        available_w = self.w - (self.padding * 2)
        if self.to == self.from_: return self.padding
        ratio = (val - self.from_) / (self.to - self.from_)
        return self.padding + (available_w * ratio)

    def x_to_val(self, x):
        available_w = self.w - (self.padding * 2)
        relative_x = x - self.padding
        if available_w <= 0: return self.from_
        ratio = max(0, min(1, relative_x / available_w))
        return int(self.from_ + (ratio * (self.to - self.from_)))

    def draw(self, event=None):
        if event: self.w, self.h = event.width, event.height
        self.delete("all")
        if self.w < 20: return
        cy = self.h // 2
        self.create_line(self.padding, cy, self.w - self.padding, cy, fill="#333333", width=4, capstyle="round")
        cx = self.val_to_x(self.value)
        self.create_line(self.padding, cy, cx, cy, fill=BRAND, width=4, capstyle="round")
        r = 8
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=BRAND, outline=BG, width=2)

    def move_to_click(self, event):
        self.value = self.x_to_val(event.x)
        self.draw()
        if self.command: self.command(self.value)

    def drag(self, event):
        self.value = self.x_to_val(event.x)
        self.draw()
        if self.command: self.command(self.value)

    def release(self, event):
        if self.release_command: self.release_command()

# --- MAIN APP ---

class Cropper:
    def __init__(self, root):
        self.root = root
        self.root.title(TITLE)
        self.root.configure(bg=BG)
        self.root.geometry("1400x850") 
        self.root.minsize(950, 650)

        # Variables
        self.preview_after_id = None
        self.original = None
        self.processed_image = None # Cache for Single Mode effects
        self.path = None
        self.displayed_photo = None
        self.displayed_size = (0, 0)
        
        # Single Mode State
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.base_scale = 1.0 # Scale to fit window initially
        
        self.start = None
        self.rect = None
        self.coords = None # Screen coords (x0, y0, x1, y1)
        self.original_coords = None # Absolute pixel coords on original image
        
        self.crop_action = None 
        self.crop_drag_start = None
        self.crop_start_coords = None
        
        self.mode = "free"
        self.buttons_shown = False
        self.current_mode = "free"
        self.welcome_items = []
        
        self.mode_type = "single" 
        self.effect_mode = StringVar(value="none")
        self.effect_enabled = IntVar(value=0)
        self.strength = IntVar(value=25)
        
        self.grid_cols = IntVar(value=2)
        self.grid_gap = IntVar(value=10)
        self.grid_bg_var = StringVar(value="#0d0d0d") 
        self.banner_gap_enabled = IntVar(value=1) 
        self.grid_tiles = []
        self.active_tile_index = -1
        self.drag_start_pos = None
        self.swap_source_index = -1
        
        self.banners_active = {'top': False, 'bottom': False, 'left': False, 'right': False}
        self.banner_images = {'top': None, 'bottom': None, 'left': None, 'right': None}

        self.load_assets()

        # UI Setup
        top_bar = Frame(root, bg=BG, height=60)
        top_bar.pack(fill="x", pady=(PADDING, 0), padx=PADDING)
        top_bar.pack_propagate(False)

        self.left_frame = Frame(top_bar, bg=BG)
        base_style = {"font": ("Segoe UI", 11, "bold"), "relief": "flat", "bd": 0, "highlightthickness": 0, "padx": 18, "pady": 12, "width": 10}
        self.btns = {}
        self.is_compact = False
        self.anim_job = None 
        
        for mode, text in [("free", "Freeform"), ("1:1", "1:1"), ("3:4", "3:4"), ("4:3", "4:3"), ("16:9", "16:9"), ("9:16", "9:16")]:
            btn = Button(self.left_frame, text=text, bg=BTN_BG, fg=BG, activebackground=BTN_BG, **base_style)
            btn.pack(side="left", padx=4, pady=(0, PADDING))
            btn.config(command=lambda m=mode: self.set_mode_with_fade(m))
            self.btns[mode] = btn

        self.status_label = Label(top_bar, text="", fg=BG, bg=BG, font=("Segoe UI", 11, "bold"), anchor="e")
        self.status_label.pack(side="right", fill="y", padx=(0, 5), pady=(0, 15))

        self.canvas = Canvas(root, bg=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True, padx=0, pady=0) 
        self.canvas.bind("<Configure>", lambda e: self.on_resize())

        self.bottom_bar = Frame(root, bg=BG, height=80)
        self.bottom_bar.pack(fill="x", pady=(0, PADDING), padx=PADDING)
        self.bottom_bar.pack_propagate(False)

        self.single_controls = Frame(self.bottom_bar, bg=BG)
        control_btn_style = {"font": ("Segoe UI", 10, "bold"), "relief": "flat", "bd": 0, "highlightthickness": 0, "padx": 15, "pady": 8}
        
        self.btn_blur = Button(self.single_controls, text="Blur", **control_btn_style, command=lambda: self.set_effect_type("blur"))
        self.btn_pixel = Button(self.single_controls, text="Pixelate", **control_btn_style, command=lambda: self.set_effect_type("pixelate"))
        self.btn_full_img = Button(self.single_controls, text="Save Crop", **control_btn_style, command=self.toggle_full_image_mode)
        
        self.btn_blur.pack(side="left", padx=(0, 5))
        self.btn_pixel.pack(side="left", padx=(0, 20))
        self.btn_full_img.pack(side="left", padx=(0, 20))

        # --- GRID CONTROLS ---
        self.grid_controls = Frame(self.bottom_bar, bg=BG)
        
        Label(self.grid_controls, text="Columns:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0,5))
        self.lbl_cols_val = Label(self.grid_controls, text="2", bg=BG, fg="#666666", width=2, font=("Segoe UI", 10))
        self.lbl_cols_val.pack(side="left", padx=(0, 0))
        self.slider_cols = ModernSlider(self.grid_controls, from_=1, to=5, initial=2, width=80, command=self.update_grid_cols)
        self.slider_cols.pack(side="left", padx=(10, 15))

        Label(self.grid_controls, text="Gap:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0,5))
        self.lbl_gap_val = Label(self.grid_controls, text="10", bg=BG, fg="#666666", width=2, font=("Segoe UI", 10))
        self.lbl_gap_val.pack(side="left", padx=(0,0))
        self.slider_gap = ModernSlider(self.grid_controls, from_=0, to=50, initial=10, width=80, command=self.update_grid_gap)
        self.slider_gap.pack(side="left", padx=(10, 15))

        # --- BACKGROUND COLOR CONTROLS ---
        Label(self.grid_controls, text="Background:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(5, 5))
        
        self.bg_preview = Canvas(self.grid_controls, width=22, height=22, bg=BG, highlightthickness=0)
        self.bg_preview.pack(side="left", padx=(0, 5))
        self.draw_bg_preview()
        
        self.entry_bg = Entry(self.grid_controls, textvariable=self.grid_bg_var, width=8, font=("Segoe UI", 10), 
                              bg=BTN_BG, fg=TEXT_ACTIVE, insertbackground="white", relief="flat")
        self.entry_bg.pack(side="left", ipady=4)
        self.entry_bg.bind("<KeyRelease>", self.update_grid_bg)

        Label(self.grid_controls, text="Banners:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(15,5))
        self.banner_btns = {}
        
        for side in ['left', 'top', 'bottom', 'right']:
            btn = Button(self.grid_controls, text=side.capitalize(), **control_btn_style, bg=BTN_BG, fg=TEXT_INACTIVE, width=6, command=lambda s=side: self.toggle_banner(s))
            btn.pack(side="left", padx=2)
            self.banner_btns[side] = btn

        self.btn_banner_gap = Button(self.grid_controls, text="Banner Gap", **control_btn_style, 
                                     bg=BRAND, fg=TEXT_ACTIVE,
                                     command=self.toggle_banner_gap_state)
        self.btn_banner_gap.pack(side="left", padx=(10, 0))

        self.slider_container = Frame(self.bottom_bar, bg=BG)
        self.lbl_val = Label(self.slider_container, text="25", bg=BG, fg="#666666", width=3, font=("Segoe UI", 10))
        self.lbl_val.pack(side="right", padx=(10, 0))
        self.slider = ModernSlider(self.slider_container, from_=0, to=50, initial=25, command=self.on_slider_move, release_command=self.update_preview_delayed)
        self.slider.pack(side="right", fill="x", expand=True)
        self.lbl_intensity = Label(self.slider_container, text="Intensity", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_intensity.pack(side="right", padx=(0, 15))

        self.apply_windows_dark_mode()
        self.draw_welcome()

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.handle_click)
        self.canvas.bind("<Double-Button-1>", self.handle_double_click)
        self.canvas.bind("<B1-Motion>", self.handle_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_release)
        self.canvas.bind("<ButtonPress-3>", self.handle_right_click)
        self.canvas.bind("<B3-Motion>", self.handle_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.handle_right_release)
        self.canvas.bind("<MouseWheel>", self.handle_wheel)
        self.canvas.bind("<Motion>", self.handle_motion) 
        
        self.root.bind("<Return>", self.save_action)
        self.root.bind("<space>", self.save_action)
        self.root.bind("<Escape>", self.cancel_action)
        self.root.bind("<Control-v>", self.paste_from_clipboard)
        self.root.bind("<Control-V>", self.paste_from_clipboard)
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)
        self.root.protocol("WM_DELETE_WINDOW", lambda: (root.quit(), root.destroy(), os._exit(0)))

    def load_assets(self):
        icon_path = "icon.ico"
        png_path = "icon.png"
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
            png_path = os.path.join(sys._MEIPASS, "icon.png")
        if os.path.exists(icon_path):
            try: self.root.iconbitmap(icon_path)
            except: pass
        self.welcome_icon_photo = None
        if os.path.exists(png_path):
            try:
                img = Image.open(png_path).convert("RGBA")
                img.thumbnail((128, 128), Image.Resampling.LANCZOS)
                self.welcome_icon_photo = ImageTk.PhotoImage(img)
            except: pass

    def apply_windows_dark_mode(self):
        try:
            self.root.update()
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            get_parent = ctypes.windll.user32.GetParent
            hwnd = get_parent(self.root.winfo_id())
            value = ctypes.c_int(2)
            set_window_attribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except: pass

    def toggle_banner(self, side):
        self.banners_active[side] = not self.banners_active[side]
        btn = self.banner_btns[side]
        is_active = self.banners_active[side]
        btn.config(bg=BRAND if is_active else BTN_BG, fg=TEXT_ACTIVE if is_active else TEXT_INACTIVE)
        self.display_grid()

    def toggle_banner_gap_state(self):
        new_state = 1 - self.banner_gap_enabled.get()
        self.banner_gap_enabled.set(new_state)
        if new_state == 1:
            self.btn_banner_gap.config(bg=BRAND, fg=TEXT_ACTIVE)
        else:
            self.btn_banner_gap.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        self.display_grid()

    # --- BG Color Logic ---
    def draw_bg_preview(self):
        self.bg_preview.delete("all")
        color = self.grid_bg_var.get()
        try:
            self.bg_preview.create_oval(2, 2, 20, 20, fill=color, outline="#555555", width=1)
        except:
            self.bg_preview.create_oval(2, 2, 20, 20, fill=BG, outline="red", width=1)

    def update_grid_bg(self, event=None):
        val = self.grid_bg_var.get()
        if len(val) == 7 and val.startswith("#"):
            try:
                self.root.winfo_rgb(val)
                self.draw_bg_preview()
                self.display_grid()
            except: pass

    # --- LAYOUT SOLVER ---
    def get_layout_metrics(self, container_w, container_h, is_save=False):
        # Calculate gaps
        gap = self.grid_gap.get() if not is_save else int(self.grid_gap.get() * (container_w/1000))
        # Logic: If banner gap enabled, use 'gap', else 0
        b_gap = gap if self.banner_gap_enabled.get() == 1 else 0

        # Ratios
        def get_ratio(side, is_vertical_banner):
            img = self.banner_images[side]
            if img and img.original:
                w, h = img.original.width, img.original.height
                if is_vertical_banner: return w / h
                else: return h / w
            return DEFAULT_BANNER_THICKNESS_RATIO

        r_l = get_ratio('left', True) if self.banners_active['left'] else 0
        r_r = get_ratio('right', True) if self.banners_active['right'] else 0
        r_t = get_ratio('top', False) if self.banners_active['top'] else 0
        r_b = get_ratio('bottom', False) if self.banners_active['bottom'] else 0

        # Banner gaps use b_gap
        gap_w_total = (b_gap if self.banners_active['left'] else 0) + (b_gap if self.banners_active['right'] else 0)
        gap_h_total = (b_gap if self.banners_active['top'] else 0) + (b_gap if self.banners_active['bottom'] else 0)

        avail_w = container_w - gap_w_total
        avail_h = container_h - gap_h_total
        
        if avail_w <= 0 or avail_h <= 0: return {'grid':{'x':0,'y':0,'w':1,'h':1}, 'banners':{}}

        # Added 3:4 (0.75) to targets
        targets = {"1:1":1.0, "4:3":1.333, "3:4":0.75, "16:9":1.777, "9:16":0.5625}
        grid_ar = targets.get(self.mode, None)

        if grid_ar:
            h_based_on_w = avail_w / (r_l + r_r + grid_ar)
            h_based_on_h = avail_h / (1 + grid_ar * (r_t + r_b))
            h_grid = min(h_based_on_w, h_based_on_h)
            w_grid = h_grid * grid_ar
        else:
            sum_x = r_l + r_r
            sum_y = r_t + r_b
            denom = 1 - (sum_x * sum_y)
            if abs(denom) < 0.001:
                w_grid = avail_w / (1 + sum_x)
                h_grid = avail_h / (1 + sum_y)
            else:
                h_grid = (avail_h - avail_w * sum_y) / denom
                w_grid = avail_w - h_grid * sum_x
                
            if h_grid <= 0 or w_grid <= 0:
                 h_grid = avail_h / (1 + sum_y)
                 w_grid = avail_w / (1 + sum_x)

        w_grid = int(w_grid); h_grid = int(h_grid)
        w_left = int(h_grid * r_l); w_right = int(h_grid * r_r)
        h_top = int(w_grid * r_t); h_bot = int(w_grid * r_b)
        
        total_used_w = w_left + w_grid + w_right + gap_w_total
        total_used_h = h_top + h_grid + h_bot + gap_h_total
        
        start_x = (container_w - total_used_w) // 2
        start_y = (container_h - total_used_h) // 2
        
        metrics = {'banners': {}, 'grid': {}}
        
        if self.banners_active['top']:
            metrics['banners']['top'] = {'x': start_x + (w_left + (b_gap if self.banners_active['left'] else 0)), 
                                         'y': start_y, 
                                         'w': w_grid, 'h': h_top}
        
        grid_y = start_y + h_top + (b_gap if self.banners_active['top'] else 0)
        
        if self.banners_active['left']:
            metrics['banners']['left'] = {'x': start_x, 
                                          'y': grid_y, 
                                          'w': w_left, 'h': h_grid}
                                          
        grid_x = start_x + w_left + (b_gap if self.banners_active['left'] else 0)
        
        metrics['grid'] = {'x': grid_x, 'y': grid_y, 'w': w_grid, 'h': h_grid}
        
        if self.banners_active['right']:
            metrics['banners']['right'] = {'x': grid_x + w_grid + b_gap, 
                                           'y': grid_y, 
                                           'w': w_right, 'h': h_grid}
        
        if self.banners_active['bottom']:
            metrics['banners']['bottom'] = {'x': grid_x, 
                                            'y': grid_y + h_grid + b_gap, 
                                            'w': w_grid, 'h': h_bot}
                                            
        return metrics

    def on_drop(self, e):
        try: files = self.root.tk.splitlist(e.data)
        except: files = e.data.split()
        files = [f for f in files if os.path.isfile(f)]
        if not files: return

        if self.mode_type == "grid":
            mx = e.x_root - self.canvas.winfo_rootx()
            my = e.y_root - self.canvas.winfo_rooty()
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            metrics = self.get_layout_metrics(cw, ch)
            dropped = False
            for side, rect in metrics['banners'].items():
                if rect['x'] <= mx <= rect['x']+rect['w'] and rect['y'] <= my <= rect['y']+rect['h']:
                    self.banner_images[side] = GridTile(path=files[0])
                    dropped = True; break
            if dropped: self.display_grid(); return
            self.grid_tiles.extend([GridTile(path=f) for f in files])
            self.update_window_title() # Update Title
            self.show_status(f"Added {len(files)} images to grid")
            self.display_grid()
        elif len(files) > 1:
            self.set_ui_mode("grid"); self.setup_grid(files)
        else:
            self.set_ui_mode("single"); self.load(files[0])

    def paste_from_clipboard(self, e=None):
        try:
            data = self.root.clipboard_get()
            if os.path.exists(data) or "\n" in data:
                paths = [p.strip() for p in data.split('\n') if os.path.exists(p.strip())]
                if paths:
                    if self.mode_type=="grid": 
                        self.grid_tiles.extend([GridTile(path=p) for p in paths])
                        self.update_window_title()
                        self.display_grid()
                    elif len(paths)>1: self.set_ui_mode("grid"); self.setup_grid(paths)
                    else: self.set_ui_mode("single"); self.load(paths[0])
                    return
        except: pass
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            if self.mode_type=="grid": 
                self.grid_tiles.append(GridTile(img_obj=img))
                self.update_window_title()
                self.display_grid()
            else: self.set_ui_mode("single"); self.load_image_object(img)

    def update_window_title(self):
        if self.mode_type == "grid":
            count = len(self.grid_tiles)
            self.root.title(f"{TITLE} - {count} Image{'s' if count != 1 else ''}")
        elif self.path:
            self.root.title(f"{TITLE} - {Path(self.path).name}")
        else:
            self.root.title(TITLE)

    # --- INPUT HANDLING ---

    def handle_click(self, e):
        if self.mode_type == "single":
            if not self.original: return
            
            # Check for resize handles if rect exists
            handle = self.get_handle_at(e.x, e.y)
            if handle:
                self.crop_action = handle
                self.crop_drag_start = (e.x, e.y)
                self.crop_start_coords = self.coords
                return

            # Check if clicking inside rect to move
            if self.rect and self.is_inside_rect(e.x, e.y):
                self.crop_action = "move"
                self.crop_drag_start = (e.x, e.y)
                self.crop_start_coords = self.coords
                return

            # Otherwise, start new crop
            if self.rect:
                self.canvas.delete(self.rect)
                self.canvas.delete("handle")
                self.rect = None
                self.original_coords = None
                self.processed_image = None # Clear cache
                self.update_preview() # Force update to clear effect
            
            self.start = (e.x, e.y)
            self.crop_action = "create"
            self.coords = None 
            self.show_status("Drag to Crop • Right-Click to Pan")
        else:
            self.active_tile_index = self.get_tile_at_pos(e.x, e.y)
            if self.active_tile_index != -1:
                self.drag_start_pos = (e.x, e.y)
                self.show_status("Drag: Pan • Right-Drag: Swap • Dbl-Click: Reset")

    def handle_double_click(self, e):
        if self.mode_type == "grid":
            idx = self.get_tile_at_pos(e.x, e.y)
            if idx != -1: self.grid_tiles[idx].reset(); self.display_grid(only_index=idx)

    def handle_motion(self, e):
        if self.mode_type == "single" and self.rect:
            handle = self.get_handle_at(e.x, e.y)
            if handle:
                cursor_map = {
                    "nw": "size_nw_se", "se": "size_nw_se",
                    "ne": "size_ne_sw", "sw": "size_ne_sw",
                    "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                    "w": "sb_h_double_arrow", "e": "sb_h_double_arrow"
                }
                self.canvas.config(cursor=cursor_map.get(handle, "arrow"))
            elif self.is_inside_rect(e.x, e.y):
                self.canvas.config(cursor="fleur")
            else:
                self.canvas.config(cursor="")
        elif self.mode_type == "single":
            self.canvas.config(cursor="")

    def handle_drag(self, e):
        if self.mode_type == "single":
            if not self.original: return
            
            if self.crop_action == "create":
                self.drag_crop_create(e)
            elif self.crop_action == "move":
                self.drag_crop_move(e)
            elif self.crop_action in ["n", "s", "e", "w", "nw", "ne", "sw", "se"]:
                self.drag_crop_resize(e)
                
        elif self.active_tile_index != -1 and self.drag_start_pos:
            dx = e.x - self.drag_start_pos[0]; dy = e.y - self.drag_start_pos[1]
            t = self.grid_tiles[self.active_tile_index]
            self.apply_pan_constraint(t, dx, dy, self.active_tile_index)
            self.drag_start_pos = (e.x, e.y)
            self.display_grid(only_index=self.active_tile_index)

    def handle_release(self, e):
        if self.mode_type == "single": 
            if self.crop_action:
                self.end_crop(e)
                self.crop_action = None
        else: self.active_tile_index = -1; self.drag_start_pos = None

    def handle_right_click(self, e):
        if self.mode_type == "grid":
            idx = self.get_tile_at_pos(e.x, e.y)
            if idx != -1: self.swap_source_index = idx; self.canvas.config(cursor="fleur")
        elif self.mode_type == "single":
            self.drag_start_pos = (e.x, e.y)
            self.canvas.config(cursor="fleur")

    def handle_right_drag(self, e):
        if self.mode_type == "grid":
            if self.swap_source_index == -1: return
            target = self.get_tile_at_pos(e.x, e.y)
            self.canvas.delete("swap_highlight")
            if target != -1 and target != self.swap_source_index:
                cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
                metrics = self.get_layout_metrics(cw, ch)
                gr = metrics['grid']
                cx, cy, cw, ch = self.get_cell_rect(target, gr['x'], gr['y'], gr['w'], gr['h'])
                self.canvas.create_rectangle(cx+2, cy+2, cx+cw-2, cy+ch-2, outline=HIGHLIGHT_COLOR, width=4, tags="swap_highlight")
        elif self.mode_type == "single":
            if not self.drag_start_pos: return
            dx = e.x - self.drag_start_pos[0]
            dy = e.y - self.drag_start_pos[1]
            
            # Pan logic for single mode
            self.single_offset_x += dx
            self.single_offset_y += dy
            
            # Constraint logic for single mode (keep image visible)
            self.apply_single_pan_constraint()
            
            self.drag_start_pos = (e.x, e.y)
            self.update_preview()

    def handle_right_release(self, e):
        if self.mode_type == "grid":
            target = self.get_tile_at_pos(e.x, e.y)
            if target != -1 and target != self.swap_source_index and self.swap_source_index != -1:
                self.grid_tiles[self.swap_source_index], self.grid_tiles[target] = self.grid_tiles[target], self.grid_tiles[self.swap_source_index]
                self.display_grid()
            self.swap_source_index = -1
            self.canvas.delete("swap_highlight")
            self.canvas.config(cursor="")
        elif self.mode_type == "single":
            self.drag_start_pos = None
            self.canvas.config(cursor="")

    def handle_wheel(self, e):
        if self.mode_type == "grid":
            idx = self.get_tile_at_pos(e.x, e.y)
            if idx != -1:
                t = self.grid_tiles[idx]
                delta = 1 if e.delta > 0 else -1
                scale_factor = 1.1 if delta > 0 else 0.9
                new_scale = max(1.0, min(5.0, t.scale * scale_factor))
                t.scale = new_scale
                self.apply_pan_constraint(t, 0, 0, idx) 
                self.display_grid(only_index=idx)
        elif self.mode_type == "single":
            delta = 1 if e.delta > 0 else -1
            scale_factor = 1.1 if delta > 0 else 0.9
            new_scale = max(1.0, min(10.0, self.single_scale * scale_factor))
            self.single_scale = new_scale
            self.apply_single_pan_constraint()
            self.update_preview()

    # --- SINGLE MODE CROP LOGIC ---

    def drag_crop_create(self, e):
        x0, y0 = self.start
        c = self._apply_aspect_to_coords(x0, y0, e.x, e.y, self.mode)
        self.coords = (int(min(c[0],c[2])), int(min(c[1],c[3])), int(max(c[0],c[2])), int(max(c[1],c[3])))
        self.draw_crop_rect()

    def drag_crop_move(self, e):
        dx = e.x - self.crop_drag_start[0]
        dy = e.y - self.crop_drag_start[1]
        x0, y0, x1, y1 = self.crop_start_coords
        self.coords = (x0+dx, y0+dy, x1+dx, y1+dy)
        self.draw_crop_rect()

    def drag_crop_resize(self, e):
        x0, y0, x1, y1 = self.crop_start_coords
        handle = self.crop_action
        
        if "w" in handle: x0 = e.x
        if "e" in handle: x1 = e.x
        if "n" in handle: y0 = e.y
        if "s" in handle: y1 = e.y
        
        nx0, nx1 = min(x0, x1), max(x0, x1)
        ny0, ny1 = min(y0, y1), max(y0, y1)
        
        if self.mode != "free" and len(handle) == 2:
            current_w = nx1 - nx0
            current_h = ny1 - ny0
            targets = {"1:1":1.0, "4:3":1.333, "3:4":0.75, "16:9":1.777, "9:16":0.5625}
            target_ar = targets.get(self.mode, 1.0)
            
            anchor_x = self.crop_start_coords[2] if "w" in handle else self.crop_start_coords[0]
            anchor_y = self.crop_start_coords[3] if "n" in handle else self.crop_start_coords[1]
            
            new_w = abs(e.x - anchor_x)
            new_h = abs(e.y - anchor_y)
            
            if new_w / max(1, new_h) > target_ar:
                calc_h = new_w / target_ar
                if "n" in handle: ny0 = anchor_y - calc_h
                else: ny1 = anchor_y + calc_h
                if "w" in handle: nx0 = anchor_x - new_w
                else: nx1 = anchor_x + new_w
            else:
                calc_w = new_h * target_ar
                if "n" in handle: ny0 = anchor_y - new_h
                else: ny1 = anchor_y + new_h
                if "w" in handle: nx0 = anchor_x - calc_w
                else: nx1 = anchor_x + calc_w
            
            nx0, nx1 = min(nx0, nx1), max(nx0, nx1)
            ny0, ny1 = min(ny0, ny1), max(ny0, ny1)

        self.coords = (int(nx0), int(ny0), int(nx1), int(ny1))
        self.draw_crop_rect()

    def draw_crop_rect(self):
        if self.rect: self.canvas.delete(self.rect)
        self.canvas.delete("handle")
        if not self.coords: return
        
        self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)
        
        x0, y0, x1, y1 = self.coords
        xm, ym = (x0+x1)//2, (y0+y1)//2
        handles = [
            (x0, y0, "nw"), (xm, y0, "n"), (x1, y0, "ne"),
            (x1, ym, "e"), (x1, y1, "se"), (xm, y1, "s"),
            (x0, y1, "sw"), (x0, ym, "w")
        ]
        
        if self.mode != "free":
            handles = [h for h in handles if len(h[2]) == 2]

        r = HANDLE_SIZE // 2
        for hx, hy, tag in handles:
            self.canvas.create_rectangle(hx-r, hy-r, hx+r, hy+r, fill=BRAND, outline=BG, tags=("handle", tag))

    def get_handle_at(self, x, y):
        if not self.coords: return None
        x0, y0, x1, y1 = self.coords
        xm, ym = (x0+x1)//2, (y0+y1)//2
        
        targets = [
            (x0, y0, "nw"), (xm, y0, "n"), (x1, y0, "ne"),
            (x1, ym, "e"), (x1, y1, "se"), (xm, y1, "s"),
            (x0, y1, "sw"), (x0, ym, "w")
        ]
        
        if self.mode != "free":
            targets = [t for t in targets if len(t[2]) == 2]
            
        r = HANDLE_SIZE 
        for hx, hy, name in targets:
            if hx-r <= x <= hx+r and hy-r <= y <= hy+r:
                return name
        return None

    def is_inside_rect(self, x, y):
        if not self.coords: return False
        x0, y0, x1, y1 = self.coords
        return x0+PADDING < x < x1-PADDING and y0+PADDING < y < y1-PADDING

    def end_crop(self, e):
        if not self.coords: 
            self.start = None
            return
            
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        disp_w, disp_h = self.displayed_size
        
        img_x = (cw - disp_w) // 2 + self.single_offset_x
        img_y = (ch - disp_h) // 2 + self.single_offset_y
        
        scale = disp_w / self.original.width
        
        cx0, cy0, cx1, cy1 = self.coords
        
        ox0 = (cx0 - img_x) / scale
        oy0 = (cy0 - img_y) / scale
        ox1 = (cx1 - img_x) / scale
        oy1 = (cy1 - img_y) / scale
        
        self.original_coords = (ox0, oy0, ox1, oy1)
        
        if self.effect_mode.get() != "none": self.update_preview_delayed()
        self.show_status("Press ENTER to save")
        self.start = None

    # --- SINGLE MODE PANNING CONSTRAINT ---
    def apply_single_pan_constraint(self):
        render_w, render_h = self.displayed_size
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        
        if not self.original: return
        
        ratio = min(cw/self.original.width, ch/self.original.height)
        base_w = int(self.original.width * ratio)
        base_h = int(self.original.height * ratio)
        
        render_w = base_w * self.single_scale
        render_h = base_h * self.single_scale
        
        max_off_x = (render_w - cw) / 2 if render_w > cw else (cw - render_w) / 2
        max_off_y = (render_h - ch) / 2 if render_h > ch else (ch - render_h) / 2
        
        if render_w <= cw:
            self.single_offset_x = 0 # Force center
        else:
            self.single_offset_x = max(-max_off_x, min(max_off_x, self.single_offset_x))
            
        if render_h <= ch:
            self.single_offset_y = 0
        else:
            self.single_offset_y = max(-max_off_y, min(max_off_y, self.single_offset_y))

    # --- GRID PANNING CONSTRAINT ---
    def apply_pan_constraint(self, tile, dx, dy, idx):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        gx, gy, gw, gh = metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']
        _, _, cell_w, cell_h = self.get_cell_rect(idx, gx, gy, gw, gh)
        
        img_ratio = tile.original.width / tile.original.height
        cell_ratio = cell_w / cell_h
        
        if img_ratio > cell_ratio: 
            base_h = cell_h; base_w = base_h * img_ratio
        else: 
            base_w = cell_w; base_h = base_w / img_ratio
            
        render_w = base_w * tile.scale
        render_h = base_h * tile.scale
        
        max_off_x = (render_w - cell_w) / 2
        max_off_y = (render_h - cell_h) / 2
        
        new_off_x = tile.offset_x + dx
        new_off_y = tile.offset_y + dy
        
        if render_w < cell_w: new_off_x = 0
        else: new_off_x = max(-max_off_x, min(max_off_x, new_off_x))
        
        if render_h < cell_h: new_off_y = 0
        else: new_off_y = max(-max_off_y, min(max_off_y, new_off_y))
        
        tile.offset_x = new_off_x
        tile.offset_y = new_off_y

    def save_action(self, e=None):
        if self.mode_type == "single": self.save_crop()
        else: self.save_grid()

    def cancel_action(self, e=None):
        if self.mode_type == "single":
            if self.rect:
                self.canvas.delete(self.rect)
                self.canvas.delete("handle")
                self.rect = None
                self.coords = None
                self.original_coords = None
                self.processed_image = None # clear effect cache
                self.display()
            else: self.reset_app()
        else: self.reset_app()

    def reset_app(self):
        self.original = None
        self.grid_tiles = []
        self.canvas.delete("all")
        self.status_label.config(text="") 
        self.draw_welcome()
        self.left_frame.pack_forget()
        self.set_ui_mode("single")
        self.single_controls.pack_forget()
        self.slider_container.pack_forget()
        self.root.title(TITLE)
        self.buttons_shown = False
        self.banners_active = {k:False for k in self.banners_active}
        self.banner_images = {k:None for k in self.banner_images}
        for btn in self.banner_btns.values(): btn.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        
        # Reset Single Mode
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.coords = None
        self.original_coords = None
        self.rect = None
        self.processed_image = None

    def set_ui_mode(self, mode_type):
        self.mode_type = mode_type
        self.single_controls.pack_forget(); self.grid_controls.pack_forget(); self.slider_container.pack_forget()
        if mode_type == "single":
            self.single_controls.pack(side="left", fill="y")
            self.slider_container.pack(side="right", fill="x", expand=True, padx=(20, 0))
        else: self.grid_controls.pack(side="left", fill="y")

    def update_bottom_ui_state(self):
        if self.mode_type == "grid": return
        mode = self.effect_mode.get()
        self.btn_blur.config(bg=BRAND if mode=="blur" else BTN_BG, fg=TEXT_ACTIVE if mode=="blur" else TEXT_INACTIVE)
        self.btn_pixel.config(bg=BRAND if mode=="pixelate" else BTN_BG, fg=TEXT_ACTIVE if mode=="pixelate" else TEXT_INACTIVE)
        if self.effect_enabled.get() == 1: self.btn_full_img.config(text="Save Full", bg=BRAND, fg=TEXT_ACTIVE)
        else: self.btn_full_img.config(text="Save Cropped", bg=BTN_BG, fg=TEXT_INACTIVE)

    def set_mode_with_fade(self, mode):
        self.current_mode = mode; self.mode = mode
        for m, btn in self.btns.items():
            btn.config(bg=BRAND if m==mode else BTN_BG, fg=TEXT_ACTIVE if m==mode else TEXT_INACTIVE)
        if self.mode_type == "single":
            if self.rect: 
                self.draw_crop_rect()
            
            if self.effect_mode.get() != "none": self.update_preview_delayed()
        else: self.display_grid()

    def animate_layout_transition(self, target_compact, step=0, steps=12):
        start_w, end_w = (10, 6) if target_compact else (6, 10)
        ratio = step / steps
        curr_w = int(start_w + (end_w - start_w) * ratio)
        font_cfg = ("Segoe UI", 10 if target_compact else 11, "bold")
        for mode, btn in self.btns.items(): btn.config(width=curr_w, font=font_cfg)
        if step < steps: self.anim_job = self.root.after(15, lambda: self.animate_layout_transition(target_compact, step+1, steps))

    def fade_in(self, widget, target_hex, steps=20, step=0):
        if step == 0: widget.config(fg=BG)
        def h2r(h): return tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        def r2h(r): return '#%02x%02x%02x' % r
        s, e = h2r(BG), h2r(target_hex)
        c = tuple(int(s[i] + (e[i] - s[i]) * (step / steps)) for i in range(3))
        try: widget.config(fg=r2h(c))
        except: return
        if step < steps: self.root.after(25, lambda: self.fade_in(widget, target_hex, steps, step+1))

    def load(self, p):
        try:
            img = Image.open(p).convert("RGB")
            self.original = img; self.path = p
            
            # Reset view & crop when loading new image
            self.single_scale = 1.0
            self.single_offset_x = 0
            self.single_offset_y = 0
            self.coords = None
            self.original_coords = None
            self.rect = None
            self.processed_image = None
            self.effect_mode.set("none") 
            
            # Reset mode to free
            self.mode = "free"
            self.current_mode = "free"

            self.canvas.delete("all"); self.display(); 
            
            if not self.buttons_shown:
                self.show_toolbar()
            else:
                self.set_mode_with_fade("free")
            
            self.update_bottom_ui_state()
            self.update_window_title()
            self.show_status("Drag to Crop • Right-Click to Pan")
        except: pass

    def load_image_object(self, img_obj):
        self.original = img_obj.convert("RGB"); self.path = "clipboard_image.png"
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.coords = None
        self.original_coords = None
        self.rect = None
        self.processed_image = None
        self.effect_mode.set("none")
        
        # Reset mode to free
        self.mode = "free"
        self.current_mode = "free"

        self.canvas.delete("all"); self.display(); 
        
        if not self.buttons_shown:
            self.show_toolbar()
        else:
            self.set_mode_with_fade("free")
            
        self.update_bottom_ui_state()
        self.update_window_title()
        self.show_status("Drag to Crop • Right-Click to Pan")

    def generate_processed_image(self):
        if not self.original or not self.original_coords: 
            self.processed_image = None
            return

        if self.effect_mode.get() == "none":
            self.processed_image = None
            return

        ox0, oy0, ox1, oy1 = self.original_coords
        ox0 = int(max(0, ox0)); oy0 = int(max(0, oy0))
        ox1 = int(min(self.original.width, ox1)); oy1 = int(min(self.original.height, oy1))
        
        strength = max(0, int(self.strength.get()))
        
        # 1. Create Effect Layer on FULL image
        full_img = self.original.copy()
        
        if self.effect_mode.get() == "blur":
            effect_layer = full_img.filter(ImageFilter.GaussianBlur(radius=strength))
        elif self.effect_mode.get() == "pixelate" and strength > 0:
            w, h = full_img.size
            small = full_img.resize((max(1, w//strength), max(1, h//strength)), Image.Resampling.NEAREST)
            effect_layer = small.resize((w, h), Image.Resampling.NEAREST)
        else:
            effect_layer = full_img

        # 2. Create Mask (White = Effect, Black = Original/Clean)
        # We want effect everywhere EXCEPT the crop box.
        mask = Image.new("L", full_img.size, 255) # White base (Effect everywhere)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((ox0, oy0, ox1, oy1), fill=0) # Black box (Clean inside)

        # --- SOFT EDGE (FEATHERING) LOGIC ---
        # Blur the mask so the transition from Black (Clean) to White (Effect) is soft
        feather_radius = max(5, int(min(self.original.width, self.original.height) * 0.01))
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))
        # ------------------------------------
        
        # 3. Paste Effect Layer onto Original using Mask
        base = self.original.copy()
        base.paste(effect_layer, mask=mask)
        
        self.processed_image = base

    def display(self):
        if not self.original: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw<=1: self.root.after(100, self.display); return
        
        # Determine which source image to render
        source_img = self.original
        
        # Logic fix: If coords exist and mode != none, allow processed_image.
        # BUT if user cleared selection (coords=None), force original.
        if self.coords and self.processed_image and self.effect_mode.get() != "none":
            source_img = self.processed_image

        # Calculate Base Fit
        ratio = min(cw/source_img.width, ch/source_img.height)
        nw = int(source_img.width * ratio * self.single_scale)
        nh = int(source_img.height * ratio * self.single_scale)
        
        try:
            resized = source_img.resize((nw, nh), Image.Resampling.LANCZOS)
            self.displayed_photo = ImageTk.PhotoImage(resized)
            self.displayed_size = (nw, nh)
            
            # Center with offset
            x = (cw-nw)//2 + self.single_offset_x
            y = (ch-nh)//2 + self.single_offset_y
            
            self.canvas.delete("image")
            self.canvas.create_image(x, y, anchor=NW, image=self.displayed_photo, tags="image")
            
            # Redraw Crop Rect if it exists (mapped from original coords to new view)
            if self.original_coords:
                ox0, oy0, ox1, oy1 = self.original_coords
                total_scale = nw / source_img.width
                
                cx0 = (ox0 * total_scale) + x
                cy0 = (oy0 * total_scale) + y
                cx1 = (ox1 * total_scale) + x
                cy1 = (oy1 * total_scale) + y
                
                self.coords = (int(cx0), int(cy0), int(cx1), int(cy1))
                self.draw_crop_rect()
        except: pass

    def _apply_aspect_to_coords(self, x0, y0, x1, y1, mode):
        if mode == "free": return (x0, y0, x1, y1)
        dx = x1 - x0; dy = y1 - y0
        targets = {"1:1":1.0, "4:3":1.333, "3:4":0.75, "16:9":1.777, "9:16":0.5625}
        target = targets.get(mode, 1.0)
        sign_x = 1 if dx >= 0 else -1; sign_y = 1 if dy >= 0 else -1
        abs_dx = abs(dx); abs_dy = abs(dy)
        if abs_dx/max(1e-6, abs_dy) > target: new_w = target * abs_dy; new_h = abs_dy
        else: new_w = abs_dx; new_h = abs_dx / max(1e-6, target)
        return (x0, y0, x0 + new_w*sign_x, y0 + new_h*sign_y)

    def update_preview_delayed(self):
        if self.preview_after_id: self.root.after_cancel(self.preview_after_id)
        self.preview_after_id = self.root.after(50, self.update_preview)

    def update_preview(self):
        if self.mode_type != "single" or not self.original: return
        
        if not self.coords: # If no selection, clear effects
            self.processed_image = None
        
        # Regenerate effects cache if needed
        if self.effect_mode.get() != "none" and self.original_coords:
            self.generate_processed_image()
        
        self.display()

    def save_crop(self):
        if not self.original or not self.original_coords: return
        
        ox0, oy0, ox1, oy1 = self.original_coords
        ox0 = max(0, ox0); oy0 = max(0, oy0)
        ox1 = min(self.original.width, ox1); oy1 = min(self.original.height, oy1)
        
        crop_box = (int(ox0), int(oy0), int(ox1), int(oy1))
        
        is_effect_save = self.effect_enabled.get() == 1 and self.effect_mode.get() != "none"
        
        if is_effect_save:
            full_img = self.original.copy()
            strength = max(0, int(self.strength.get()))
            
            # Apply effect to FULL image
            if self.effect_mode.get() == "blur": 
                effect_layer = full_img.filter(ImageFilter.GaussianBlur(radius=strength))
            elif self.effect_mode.get() == "pixelate":
                w, h = full_img.size
                small = full_img.resize((max(1, w//strength), max(1, h//strength)), Image.Resampling.NEAREST)
                effect_layer = small.resize((w, h), Image.Resampling.NEAREST)
            else: 
                effect_layer = full_img

            # Create Mask (White everywhere, Black inside crop)
            mask = Image.new("L", full_img.size, 255)
            draw = ImageDraw.Draw(mask)
            draw.rectangle(crop_box, fill=0)

            # --- SOFT EDGE (FEATHERING) LOGIC FOR SAVE ---
            feather_radius = max(5, int(min(self.original.width, self.original.height) * 0.01))
            mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))
            # ---------------------------------------------
            
            # Paste effect onto clean image
            base = self.original.copy()
            base.paste(effect_layer, mask=mask)
            
            final = base
        else: 
            final = self.original.crop(crop_box) 
            
        p = Path(self.path)
        
        suffix_str = "_effect" if is_effect_save else "_crop"
        
        if p.name == "clipboard_image.png":
            base_name = "clipboard"
        else:
            base_name = p.stem
            
        out = p.parent / f"{base_name}{suffix_str}{p.suffix}"
        
        i = 1
        while out.exists():
            out = p.parent / f"{base_name}{suffix_str}_{i}{p.suffix}"
            i += 1
            
        final.save(out, quality=98)
        self.show_status(f"Saved: {out.name}")

    def toggle_full_image_mode(self):
        self.effect_enabled.set(1 - self.effect_enabled.get())
        self.update_bottom_ui_state()

    def on_slider_move(self, val):
        self.strength.set(int(val)); self.lbl_val.config(text=str(int(val)))
        if self.mode_type == "single": self.cancel_pending_preview()

    def cancel_pending_preview(self):
        if self.preview_after_id: self.root.after_cancel(self.preview_after_id); self.preview_after_id = None

    def set_effect_type(self, mode):
        # Toggle effect mode
        new_mode = "none" if self.effect_mode.get() == mode else mode
        self.effect_mode.set(new_mode)
        
        # Auto-toggle "Save Full" based on whether an effect is active
        if new_mode != "none":
            self.effect_enabled.set(1)
        else:
            self.effect_enabled.set(0)
            
        self.update_bottom_ui_state()
        if self.mode_type == "single": self.update_preview_delayed()

    def setup_grid(self, files):
        self.grid_tiles = [GridTile(path=f) for f in files]
        self.show_toolbar()
        n = len(files); cols = 2 if n < 5 else 3; 
        if n == 1: cols = 1
        self.slider_cols.set_value(cols); self.grid_cols.set(cols); self.lbl_cols_val.config(text=str(cols))
        self.show_status("Drag: Pan • Right-Drag: Swap • Dbl-Click: Reset")
        self.update_window_title()
        self.display_grid()

    def get_grid_dimensions(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        return metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']

    def render_banner_image(self, side, rect):
        tile = self.banner_images[side]
        x, y, w, h = rect['x'], rect['y'], rect['w'], rect['h']
        if not tile:
            self.canvas.create_rectangle(x, y, x+w, y+h, fill="#151515", outline="")
            self.canvas.create_text(x + w/2, y + h/2, text=side.upper(), fill="#333333", font=("Segoe UI", 14, "bold"))
            return
        try:
            small = tile.original.resize((w, h), Image.Resampling.BILINEAR)
            tk_img = ImageTk.PhotoImage(small)
            tile.tk_ref = tk_img 
            self.canvas.create_image(x, y, anchor=NW, image=tk_img)
        except: pass

    def display_grid(self, only_index=-1):
        if not self.grid_tiles and not any(self.banner_images.values()): return
        if only_index == -1: self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        
        # --- DRAW BACKGROUND RECTANGLE ---
        if only_index == -1:
            min_x, min_y = 99999, 99999
            max_x, max_y = -99999, -99999
            
            gx, gy, gw, gh = metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']
            min_x = min(min_x, gx); min_y = min(min_y, gy)
            max_x = max(max_x, gx+gw); max_y = max(max_y, gy+gh)
            
            for _, r in metrics['banners'].items():
                min_x = min(min_x, r['x']); min_y = min(min_y, r['y'])
                max_x = max(max_x, r['x']+r['w']); max_y = max(max_y, r['y']+r['h'])

            bg_color = self.grid_bg_var.get()
            try:
                self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=bg_color, outline="")
            except: 
                self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=BG, outline="")

            for side, rect in metrics['banners'].items(): self.render_banner_image(side, rect)
        
        # Draw Grid Tiles
        gx, gy, gw, gh = metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']
        indices = range(len(self.grid_tiles)) if only_index == -1 else [only_index]
        for i in indices:
            tile = self.grid_tiles[i]
            cx, cy, cw, ch = self.get_cell_rect(i, gx, gy, gw, gh)
            img_ratio = tile.original.width / tile.original.height
            cell_ratio = cw / ch
            if img_ratio > cell_ratio: base_h = ch; base_w = base_h * img_ratio
            else: base_w = cw; base_h = base_w / img_ratio
            
            # Calculate current render size
            render_w = int(base_w * tile.scale)
            render_h = int(base_h * tile.scale)
            
            # --- FIX: PROPORTIONAL OFFSET ADJUSTMENT ---
            # If the render size changed due to layout shift or fitting strategy change,
            # scale the offset to keep the visual center stable.
            if tile.last_render_w > 0 and tile.last_render_h > 0:
                if render_w != tile.last_render_w:
                    tile.offset_x = tile.offset_x * (render_w / tile.last_render_w)
                if render_h != tile.last_render_h:
                    tile.offset_y = tile.offset_y * (render_h / tile.last_render_h)
            
            # Update last known size
            tile.last_render_w = render_w
            tile.last_render_h = render_h
            # -------------------------------------------
            
            # --- SAFETY CLAMP: Ensure image is not out of bounds when layout changes ---
            max_off_x = (render_w - cw) / 2
            max_off_y = (render_h - ch) / 2
            
            if render_w < cw: tile.offset_x = 0
            else: tile.offset_x = max(-max_off_x, min(max_off_x, tile.offset_x))
            
            if render_h < ch: tile.offset_y = 0
            else: tile.offset_y = max(-max_off_y, min(max_off_y, tile.offset_y))
            # --------------------------------------------------------------------------

            try:
                small = tile.original.resize((render_w, render_h), Image.Resampling.BILINEAR)
                img_cx = render_w // 2; img_cy = render_h // 2
                left = img_cx - (cw // 2) - tile.offset_x; top = img_cy - (ch // 2) - tile.offset_y
                right = left + cw; bottom = top + ch
                
                # Use int() to ensure crop box coordinates are valid
                cropped = small.crop((int(left), int(top), int(right), int(bottom)))
                
                tk_img = ImageTk.PhotoImage(cropped)
                tile.tk_ref = tk_img 
                self.canvas.delete(f"tile_{i}")
                self.canvas.create_image(cx, cy, anchor=NW, image=tk_img, tags=f"tile_{i}")
            except: pass

    def save_grid(self):
        base_grid_w = 3000
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics_disp = self.get_layout_metrics(cw, ch)
        
        disp_gw = metrics_disp['grid']['w']; disp_gh = metrics_disp['grid']['h']
        if disp_gw == 0: return
        grid_ar = disp_gh / disp_gw
        base_grid_h = int(base_grid_w * grid_ar)
        
        # Scale gaps for high res
        gap = int(self.grid_gap.get() * (base_grid_w / disp_gw))
        b_gap = gap if self.banner_gap_enabled.get() == 1 else 0
        
        banners_save = {}
        
        def get_ratio(side, is_vertical_banner):
            img = self.banner_images[side]
            if img and img.original:
                w, h = img.original.width, img.original.height
                if is_vertical_banner: return w / h
                else: return h / w
            return DEFAULT_BANNER_THICKNESS_RATIO

        final_w = base_grid_w
        final_h = base_grid_h
        grid_x = 0; grid_y = 0
        
        if self.banners_active['left']:
            ar = get_ratio('left', True)
            w = int(base_grid_h * ar)
            final_w += (w + b_gap)
            grid_x += (w + b_gap)
            banners_save['left'] = {'x':0, 'y':0, 'w':w, 'h':base_grid_h} 
            
        if self.banners_active['right']:
            ar = get_ratio('right', True)
            w = int(base_grid_h * ar)
            final_w += (w + b_gap)
            banners_save['right'] = {'x':0, 'y':0, 'w':w, 'h':base_grid_h} 
            
        row_w = final_w
        
        if self.banners_active['top']:
            ar = get_ratio('top', False)
            h = int(row_w * ar)
            final_h += (h + b_gap)
            grid_y += (h + b_gap)
            banners_save['top'] = {'x':0, 'y':0, 'w':row_w, 'h':h}
            
        if self.banners_active['bottom']:
            ar = get_ratio('bottom', False)
            h = int(row_w * ar)
            final_h += (h + b_gap)
            banners_save['bottom'] = {'x':0, 'y':0, 'w':row_w, 'h':h} 

        if 'left' in banners_save: banners_save['left']['y'] = grid_y
        if 'right' in banners_save:
            banners_save['right']['x'] = final_w - banners_save['right']['w']
            banners_save['right']['y'] = grid_y
        if 'bottom' in banners_save:
            banners_save['bottom']['y'] = final_h - banners_save['bottom']['h']

        bg_color = self.grid_bg_var.get()
        try:
            master = Image.new("RGB", (final_w, final_h), bg_color)
        except:
            master = Image.new("RGB", (final_w, final_h), BG)
        
        for side, r in banners_save.items():
            tile = self.banner_images[side]
            if not tile: 
                draw = ImageDraw.Draw(master); draw.rectangle((r['x'], r['y'], r['x']+r['w'], r['y']+r['h']), fill="#151515")
            else:
                res = tile.original.resize((r['w'], r['h']), Image.Resampling.LANCZOS)
                master.paste(res, (r['x'], r['y']))

        cols = self.grid_cols.get(); rows = math.ceil(len(self.grid_tiles)/cols)
        cw_standard = (base_grid_w - (gap*(cols-1)))//cols
        ch = (base_grid_h - (gap*(rows-1)))//rows
        
        for i, tile in enumerate(self.grid_tiles):
            row = i//cols; col = i%cols
            
            # --- LAST ROW FILL LOGIC (SAVE) ---
            if row == rows - 1 and len(self.grid_tiles) % cols != 0:
                items_in_row = len(self.grid_tiles) % cols
                cw = (base_grid_w - (gap * (items_in_row - 1))) // items_in_row
            else:
                cw = cw_standard
            # ----------------------------------

            tx = grid_x + col*(cw+gap); ty = grid_y + row*(ch+gap)
            
            ir = tile.original.width / tile.original.height
            cr = cw / ch
            if ir > cr: bh = ch; bw = int(ch*ir)
            else: bw = cw; bh = int(cw/ir)
            
            scale = (base_grid_w / disp_gw) * tile.scale
            
            if ir > cr: bh_save = ch; bw_save = int(ch*ir)
            else: bw_save = cw; bh_save = int(cw/ir)
            
            rw_save = int(bw_save * tile.scale); rh_save = int(bh_save * tile.scale)
            res = tile.original.resize((rw_save, rh_save), Image.Resampling.LANCZOS)
            
            screen_scale = base_grid_w / disp_gw
            off_x = int(tile.offset_x * screen_scale)
            off_y = int(tile.offset_y * screen_scale)
            
            icx = rw_save//2; icy = rh_save//2
            l = icx - (cw//2) - off_x
            t = icy - (ch//2) - off_y
            crop = res.crop((l, t, l+cw, t+ch))
            master.paste(crop, (tx, ty))

        if self.grid_tiles and os.path.exists(self.grid_tiles[0].path):
            p = Path(self.grid_tiles[0].path)
            out = p.parent / f"collage_{p.stem}.jpg"
        else: out = Path("collage_saved.jpg")
        master.save(out, quality=95)
        self.show_status(f"Saved: {out.name}")

    def update_grid_cols(self, val):
        if int(val) != self.grid_cols.get():
            self.grid_cols.set(int(val)); self.lbl_cols_val.config(text=str(int(val))); self.display_grid()

    def update_grid_gap(self, val):
        if int(val) != self.grid_gap.get():
            self.grid_gap.set(int(val)); self.lbl_gap_val.config(text=str(int(val))); self.display_grid()

    def get_cell_rect(self, index, off_x, off_y, total_w, total_h):
        cols = self.grid_cols.get()
        count = len(self.grid_tiles)
        rows = math.ceil(count/cols)
        gap = self.grid_gap.get()
        
        # Standard Height is consistent across all rows
        ch = (total_h - (gap*(rows-1)))//rows

        row = index // cols
        col = index % cols

        # --- LAST ROW FILL LOGIC (DISPLAY) ---
        # If we are in the last row AND the number of items doesn't perfectly fill columns
        if row == rows - 1 and count % cols != 0:
            items_in_row = count % cols
            # Calculate special width for items in this row
            cw = (total_w - (gap * (items_in_row - 1))) // items_in_row
        else:
            # Standard calculation
            cw = (total_w - (gap*(cols-1)))//cols
        # -------------------------------------

        x = off_x + col*(cw+gap)
        y = off_y + row*(ch+gap)
        return x, y, cw, ch

    def get_tile_at_pos(self, x, y):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        gr = metrics['grid']
        gx, gy, gw, gh = gr['x'], gr['y'], gr['w'], gr['h']
        for i in range(len(self.grid_tiles)):
            cx, cy, cw, ch = self.get_cell_rect(i, gx, gy, gw, gh)
            if cx <= x <= cx+cw and cy <= y <= cy+ch: return i
        return -1

    def draw_welcome(self):
        self.canvas.delete("all"); w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w<100: return
        cx, cy = w//2, h//2+40
        if self.welcome_icon_photo: self.canvas.create_image(cx, cy-170, image=self.welcome_icon_photo)
        self.canvas.create_text(cx, cy-80, text="Cropper", fill=BRAND, font=("Segoe UI", 38, "bold"))
        self.canvas.create_text(cx, cy-15, text="Single or Collage", fill="white", font=("Segoe UI", 22))
        self.canvas.create_text(cx, cy+60, text="Drop one image to Crop\nDrop multiple to Tile\nCtrl+V to Paste", fill="#bbbbbb", font=("Segoe UI", 16), justify="center")

    def show_toolbar(self):
        if not self.buttons_shown:
            self.buttons_shown = True; self.left_frame.pack(side="left", fill="y")
            self.animate_layout_transition(self.root.winfo_width()<1050)
            for m in self.btns:
                # Fix: Correct colors for active vs inactive
                if m == self.mode:
                    self.btns[m].config(bg=BRAND)
                    self.fade_in(self.btns[m], TEXT_ACTIVE)
                else:
                    self.btns[m].config(bg=BTN_BG)
                    self.fade_in(self.btns[m], TEXT_INACTIVE)

    def show_status(self, text):
        if self.status_label.cget("text")==text: return
        self.status_label.config(text=text); self.fade_in(self.status_label, BRAND)

    def on_resize(self):
        w = self.root.winfo_width()
        if self.original or self.grid_tiles:
            if w<1050 and not self.is_compact: self.animate_layout_transition(True)
            elif w>=1050 and self.is_compact: self.animate_layout_transition(False)
        if self.mode_type == "single": self.display()
        else: self.display_grid()
        if not self.original and not self.grid_tiles: self.draw_welcome()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = Cropper(root)
    root.mainloop()
