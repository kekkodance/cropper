import sys
import os
import gc
import ctypes
import math
import json
from pathlib import Path
import tkinter as tk
from tkinter import Canvas, NW, BOTH, Button, Frame, Label, IntVar, StringVar, Entry, Toplevel, messagebox, colorchooser, filedialog
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk, ImageFilter, ImageDraw, ImageGrab
import cv2
import numpy as np
import webbrowser

TITLE = "Cropper"
DEFAULT_BRAND = "#0047AB"
BG = "#0d0d0d"
CANVAS_BG = "#111111"
BTN_BG = "#1a1a1a"
BTN_ACTIVE_BG = "#2a2a2a"
TEXT_INACTIVE = "#888888"
TEXT_ACTIVE = "#ffffff"
HIGHLIGHT_COLOR = "#FFD700" 
PADDING = 20 
DEFAULT_BANNER_THICKNESS_RATIO = 0.25 
HANDLE_SIZE = 8 
SETTINGS_FILE = "cropper_settings.json"


class TitleBarButton(Canvas):
    def __init__(self, master, btn_type="min", command=None, hover_color="#2a2a2a", **kwargs):
        super().__init__(master, bg="#0d0d0d", width=46, height=32, highlightthickness=0, **kwargs)
        self.btn_type = btn_type
        self.command = command
        self.hover_color = hover_color
        self.default_bg = "#0d0d0d"
        self.icon_color = "#ffffff"
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Configure>", self.on_resize)
        
        self.draw_icon()

    def on_resize(self, event):
        self.draw_icon()

    def draw_icon(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        
        if w <= 1: w = 46
        if h <= 1: h = 32
        
        cx, cy = w / 2, h / 2
        
        if self.btn_type == "close":
            pad = 5.8
            self.create_line(cx-pad, cy-pad, cx+pad, cy+pad, width=1, fill=self.icon_color)
            self.create_line(cx+pad, cy-pad, cx-pad, cy+pad, width=1, fill=self.icon_color)
            
        elif self.btn_type == "max":
            pad = 5
            self.create_rectangle(cx-pad, cy-pad, cx+pad, cy+pad, outline=self.icon_color, width=1)
            
        elif self.btn_type == "restore":
            pad = 4
            off = 2
            self.create_line(cx-pad+off, cy-pad-off, cx+pad+off, cy-pad-off, 
                             cx+pad+off, cy+pad-off, cx+pad-off, cy+pad-off, 
                             fill=self.icon_color, width=1)
            self.create_rectangle(cx-pad-off, cy-pad+off, cx+pad-off, cy+pad+off, outline=self.icon_color, width=1)

        elif self.btn_type == "min":
            self.create_line(cx-5, cy, cx+5, cy, width=1, fill=self.icon_color)

    def on_enter(self, e):
        self.config(bg=self.hover_color)

    def on_leave(self, e):
        self.config(bg=self.default_bg)

    def on_click(self, e):
        if self.command:
            self.command()

class CustomTitleBar(Frame):
    def __init__(self, master, title_text="Cropper", brand_color="#0047AB", close_cmd=None, is_dialog=False, icon_path=None, **kwargs):
        super().__init__(master, bg="#0d0d0d", height=35, **kwargs)
        self.master = master
        self.pack_propagate(False)
        self._drag_data = {"x": 0, "y": 0}
        
        self.maximized = False
        self.pre_max_geometry = None
        
        self.separator = Frame(self, bg="#333333", height=1)
        self.separator.pack(side="bottom", fill="x")

        self.content_frame = Frame(self, bg="#0d0d0d")
        self.content_frame.pack(side="top", fill="both", expand=True)

        self.icon_lbl = None
        if icon_path and os.path.exists(icon_path):
            try:
                pil_icon = Image.open(icon_path).resize((20, 20), Image.Resampling.LANCZOS)
                self.icon_photo = ImageTk.PhotoImage(pil_icon)
                
                self.icon_lbl = Label(self.content_frame, image=self.icon_photo, bg="#0d0d0d")
                self.icon_lbl.pack(side="left", padx=(12, 0))
            except Exception as e:
                print(f"Icon load error: {e}")

        text_pad = (6, 0) if self.icon_lbl else (12, 0)
        self.title_lbl = Label(self.content_frame, text=title_text, bg="#0d0d0d", fg="#cccccc", font=("Segoe UI", 9, "bold"))
        self.title_lbl.pack(side="left", padx=text_pad)

        self.btn_close = TitleBarButton(self.content_frame, btn_type="close", hover_color="#E81123", 
                                        command=lambda: close_cmd() if close_cmd else master.destroy())
        self.btn_close.pack(side="right", fill="y")
        
        if not is_dialog:
            self.btn_max = TitleBarButton(self.content_frame, btn_type="max", command=self.toggle_maximize)
            self.btn_max.pack(side="right", fill="y")
            
            self.btn_min = TitleBarButton(self.content_frame, btn_type="min", command=self.minimize)
            self.btn_min.pack(side="right", fill="y")

        drag_widgets = [self, self.content_frame, self.title_lbl]
        if self.icon_lbl: drag_widgets.append(self.icon_lbl)

        for widget in drag_widgets:
            widget.bind("<Button-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)
            if not is_dialog:
                widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

    def start_move(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def do_move(self, event):
        if self.maximized: return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.master.winfo_x() + dx
        y = self.master.winfo_y() + dy
        self.master.geometry(f"+{x}+{y}")

    def toggle_maximize(self):
        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long),
                        ('top', ctypes.c_long),
                        ('right', ctypes.c_long),
                        ('bottom', ctypes.c_long)]

        if self.maximized:
            self.maximized = False
            self.btn_max.btn_type = "max"
            if self.pre_max_geometry:
                self.master.geometry(self.pre_max_geometry)
        else:
            self.maximized = True
            self.btn_max.btn_type = "restore"
            self.pre_max_geometry = self.master.geometry()
            user32 = ctypes.windll.user32
            rect = RECT()
            user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            self.master.geometry(f"{width}x{height}+{rect.left}+{rect.top}")
        self.btn_max.draw_icon()

    def minimize(self):
        hwnd = ctypes.windll.user32.GetParent(self.master.winfo_id())
        if hwnd == 0: hwnd = self.master.winfo_id()
        ctypes.windll.user32.ShowWindow(hwnd, 6)

class Resizer(Frame):
    def __init__(self, master, app_instance, **kwargs):
        super().__init__(master, bg="#0d0d0d", cursor="size_nw_se", width=16, height=16, **kwargs)
        self.master = master
        self.app = app_instance
        
        self.canvas = Canvas(self, bg="#0d0d0d", width=16, height=16, highlightthickness=0)
        self.canvas.pack()
        
        self.canvas.create_line(4, 12, 12, 4, fill="#444444", width=1)
        self.canvas.create_line(8, 12, 12, 8, fill="#444444", width=1)
        self.canvas.create_line(12, 12, 12, 12, fill="#444444", width=1)
        
        self.bind("<ButtonPress-1>", self.start_native_resize)
        self.canvas.bind("<ButtonPress-1>", self.start_native_resize)

    def start_native_resize(self, event):
        
        hwnd = ctypes.windll.user32.GetParent(self.master.winfo_id())
        
        ctypes.windll.user32.ReleaseCapture()
        
        ctypes.windll.user32.PostMessageW(hwnd, 0x0112, 0xF008, 0)
        
        self.check_resize_end()

    def check_resize_end(self):
        if ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000:
            self.master.after(50, self.check_resize_end)
        else:
            if self.app.mode_type == "single":
                self.app.display()
            else:
                self.app.display_grid()

def set_appwindow(root):
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    if hwnd == 0:
        hwnd = root.winfo_id()

    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    
    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ex_style = ex_style & ~WS_EX_TOOLWINDOW
    ex_style = ex_style | WS_EX_APPWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    GWL_STYLE = -16
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = style | WS_SYSMENU | WS_MINIMIZEBOX
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

    root.wm_withdraw()
    root.after(10, lambda: root.wm_deiconify())

class GridTile:
    def __init__(self, path=None, img_obj=None):
        self.path = path if path else "clipboard_image"
        
        if img_obj:
            pil_image = img_obj.convert("RGB")
            self.original = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        elif path and os.path.exists(path):
            with open(path, "rb") as f:
                bytes_data = bytearray(f.read())
                numpy_array = np.asarray(bytes_data, dtype=np.uint8)
                self.original = cv2.imdecode(numpy_array, cv2.IMREAD_COLOR)
        else:
            self.original = np.zeros((100, 100, 3), dtype=np.uint8)

        self.h, self.w = self.original.shape[:2]

        self.proxy = self.original
        scale = 2048 / max(self.h, self.w)
        if scale < 1:
            new_w, new_h = int(self.w * scale), int(self.h * scale)
            self.proxy = cv2.resize(self.original, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        self.offset_x = 0
        self.offset_y = 0
        self.scale = 1.0
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
    def __init__(self, master, from_=0, to=100, initial=25, brand_color=DEFAULT_BRAND, command=None, release_command=None, **kwargs):
        super().__init__(master, **kwargs)
        self.from_ = from_
        self.to = to
        self.value = initial
        self.brand_color = brand_color
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
        
    def set_brand_color(self, color):
        self.brand_color = color
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
        self.create_line(self.padding, cy, cx, cy, fill=self.brand_color, width=4, capstyle="round")
        r = 8
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.brand_color, outline=BG, width=2)

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

class ModernToggle(Canvas):
    def __init__(self, master, variable=None, brand_color=DEFAULT_BRAND, width=44, height=24, **kwargs):
        super().__init__(master, width=width, height=height, bg=BG, highlightthickness=0, **kwargs)
        self.variable = variable
        self.brand_color = brand_color
        self.width = width
        self.height = height
        self.bind("<Button-1>", self.toggle)
        self.draw()

    def set_brand_color(self, color):
        self.brand_color = color
        self.draw()

    def toggle(self, event=None):
        if self.variable:
            new_val = 0 if self.variable.get() == 1 else 1
            self.variable.set(new_val)
            self.draw()

    def draw(self):
        self.delete("all")
        on = self.variable.get() == 1 if self.variable else False
        
        bg_color = self.brand_color if on else "#333333"
        
        pad = 2
        r = (self.height - 2*pad) // 2
        
        x_start = self.height // 2
        x_end = self.width - (self.height // 2)
        cy = self.height // 2
        
        self.create_line(x_start, cy, x_end, cy, width=self.height, capstyle="round", fill=bg_color)
        
        cx = self.width - r - pad if on else r + pad
        thumb_r = r - 2
        self.create_oval(cx - thumb_r, cy - thumb_r, cx + thumb_r, cy + thumb_r, fill="#ffffff", outline="")


class Cropper:
    def __init__(self, root):
        self.root = root
        
        self.root.configure(bg="#0d0d0d") 
        
        self.root.title(TITLE)
        
        s_width = self.root.winfo_screenwidth()
        s_height = self.root.winfo_screenheight()
        
        target_w, target_h = 1400, 850
        
        w_width = min(target_w, s_width - 50)
        w_height = min(target_h, s_height - 80) 
        
        x = int((s_width / 2) - (w_width / 2))
        y = int((s_height / 2) - (w_height / 2))
        
        if x < 0: x = 0
        if y < 0: y = 0
        
        self.root.geometry(f"{w_width}x{w_height}+{x}+{y}")

        self.settings = {
            "brand_color": DEFAULT_BRAND,
            "save_gap_bg": False,
            "last_gap_bg": "#0d0d0d",
            "collage_prefix": "collage_",
            "crop_suffix": "_crop",
            "output_folder": ""
        }
        self.load_settings()
        self.brand_color = self.settings["brand_color"]
        
        self.root.overrideredirect(True) 
        
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        
        self.icon_path = os.path.join(base_path, "icon.ico")
        
        self.title_bar = CustomTitleBar(
            root, 
            title_text=TITLE, 
            brand_color=self.brand_color, 
            close_cmd=self.on_close,
            icon_path=self.icon_path
        )
        self.title_bar.pack(side="top", fill="x")
        
        self.resizer = Resizer(root,self)
        self.resizer.place(relx=1.0, rely=1.0, x=-16, y=-16)
        
        self.root.after(10, lambda: set_appwindow(self.root))
    

        self.preview_after_id = None
        self.original = None
        self.processed_image = None
        self.path = None
        self.displayed_photo = None
        self.displayed_size = (0, 0)
        
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.single_gap = IntVar(value=10)
        
        self.start = None
        self.rect = None
        self.coords = None 
        self.original_coords = None
        
        self.crop_action = None 
        self.crop_drag_start = None
        self.crop_start_coords = None
        
        self.mode = "free"
        self.buttons_shown = False
        self.current_mode = "free"
        
        self.mode_type = "single" 
        self.effect_mode = StringVar(value="none")
        self.effect_enabled = IntVar(value=0)
        self.strength = IntVar(value=25)
        
        self.grid_cols = IntVar(value=2)
        self.grid_gap = IntVar(value=10)
        
        initial_bg = self.settings["last_gap_bg"] if self.settings["save_gap_bg"] else "#0d0d0d"
        self.grid_bg_var = StringVar(value=initial_bg)
        
        self.banner_gap_enabled = IntVar(value=1) 
        self.grid_tiles = []
        self.active_tile_index = -1
        self.drag_start_pos = None
        self.swap_source_index = -1
        
        self.banners_active = {'top': False, 'bottom': False, 'left': False, 'right': False}
        self.banner_images = {'top': None, 'bottom': None, 'left': None, 'right': None}

        self.load_assets()

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

        btn_fit = Button(self.left_frame, text="Fit", bg=BTN_BG, fg=BG, activebackground=BTN_BG, **base_style)
        btn_fit.config(command=lambda: self.set_mode_with_fade("fit"))
        self.btns["fit"] = btn_fit

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
        
        self.btn_blur.pack(side="left", padx=(0, 5))
        self.btn_pixel.pack(side="left", padx=(0, 5))

        self.lbl_intensity = Label(self.single_controls, text="Intensity", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_intensity.pack(side="left", padx=(10, 5))
        
        self.slider = ModernSlider(self.single_controls, from_=0, to=50, initial=25, width=100, brand_color=self.brand_color, command=self.on_slider_move, release_command=self.update_preview_delayed)
        self.slider.pack(side="left", padx=(0, 5))
        
        self.lbl_val = Label(self.single_controls, text="25", bg=BG, fg="#666666", width=3, font=("Segoe UI", 10))
        self.lbl_val.pack(side="left", padx=(0, 15))

        self.lbl_banners_single = Label(self.single_controls, text="Banners:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_banners_single.pack(side="left", padx=(5,5))
        self.single_banner_btns = {}
        
        small_btn_style = control_btn_style.copy()
        small_btn_style["padx"] = 5
        
        for side in ['left', 'top', 'bottom', 'right']:
            btn = Button(self.single_controls, text=side.capitalize(), **small_btn_style, bg=BTN_BG, fg=TEXT_INACTIVE, width=6, 
                         command=lambda s=side: self.toggle_banner(s))
            btn.pack(side="left", padx=2)
            self.single_banner_btns[side] = btn

        self.lbl_gap_single = Label(self.single_controls, text="Gap:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_gap_single.pack(side="left", padx=(15,5))
        
        self.single_slider_gap = ModernSlider(self.single_controls, from_=0, to=100, initial=10, width=80, brand_color=self.brand_color, command=self.update_single_gap)
        self.single_slider_gap.pack(side="left", padx=(5, 5))

        self.lbl_gap_single_val = Label(self.single_controls, text="10", bg=BG, fg="#666666", width=3, font=("Segoe UI", 10))
        self.lbl_gap_single_val.pack(side="left", padx=(0, 15))
        
        self.lbl_bg_single_text = Label(self.single_controls, text="Background:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_bg_single_text.pack(side="left", padx=(5, 5))
        
        self.bg_preview_single = Canvas(self.single_controls, width=22, height=22, bg=BG, highlightthickness=0, cursor="hand2")
        self.bg_preview_single.pack(side="left", padx=(0, 5))
        self.bg_preview_single.bind("<Button-1>", self.open_bg_picker)
        
        self.entry_bg_single = Entry(self.single_controls, textvariable=self.grid_bg_var, width=8, font=("Segoe UI", 10), 
                              bg=BTN_BG, fg=TEXT_ACTIVE, insertbackground="white", relief="flat")
        self.entry_bg_single.pack(side="left", ipady=4)
        self.entry_bg_single.bind("<KeyRelease>", self.update_grid_bg)


        self.grid_controls = Frame(self.bottom_bar, bg=BG)
        
        self.lbl_cols_text = Label(self.grid_controls, text="Columns:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_cols_val = Label(self.grid_controls, text="2", bg=BG, fg="#666666", width=2, font=("Segoe UI", 10))
        self.slider_cols = ModernSlider(self.grid_controls, from_=1, to=5, initial=2, width=80, brand_color=self.brand_color, command=self.update_grid_cols)

        self.lbl_gap_text = Label(self.grid_controls, text="Gap:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.lbl_gap_val = Label(self.grid_controls, text="10", bg=BG, fg="#666666", width=2, font=("Segoe UI", 10))
        self.slider_gap = ModernSlider(self.grid_controls, from_=0, to=50, initial=10, width=80, brand_color=self.brand_color, command=self.update_grid_gap)

        self.lbl_bg_grid_text = Label(self.grid_controls, text="Background:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        
        self.bg_preview = Canvas(self.grid_controls, width=22, height=22, bg=BG, highlightthickness=0, cursor="hand2")
        self.bg_preview.bind("<Button-1>", self.open_bg_picker)
        
        self.entry_bg = Entry(self.grid_controls, textvariable=self.grid_bg_var, width=8, font=("Segoe UI", 10), 
                              bg=BTN_BG, fg=TEXT_ACTIVE, insertbackground="white", relief="flat")
        self.entry_bg.bind("<KeyRelease>", self.update_grid_bg)

        self.lbl_banners_text = Label(self.grid_controls, text="Banners:", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        self.banner_btns = {}
        
        for side in ['left', 'top', 'bottom', 'right']:
            btn = Button(self.grid_controls, text=side.capitalize(), **control_btn_style, bg=BTN_BG, fg=TEXT_INACTIVE, width=6, command=lambda s=side: self.toggle_banner(s))
            self.banner_btns[side] = btn

        self.btn_banner_gap = Button(self.grid_controls, text="Banner Gap", **control_btn_style, 
                                     bg=self.brand_color, fg=TEXT_ACTIVE,
                                     command=self.toggle_banner_gap_state)
        
        self.refresh_grid_controls_layout()


        self.bottom_right_area = Frame(self.bottom_bar, bg=BG)
        self.bottom_right_area.pack(side="right")

        self.btn_settings = Button(self.bottom_right_area, text="⚙", font=("Segoe UI", 16), bg=BG, fg="#666666", 
                                   activebackground=BG, activeforeground="white", relief="flat", bd=0, 
                                   command=self.open_settings_window)
        self.btn_settings.pack(side="right", padx=(10, 0))

        self.lbl_save_status = Label(self.bottom_right_area, text="Will save crop selection", bg=BG, fg="#888888", font=("Segoe UI", 10, "italic"))

        self.apply_windows_dark_mode()
        self.draw_bg_preview() 
        self.draw_welcome()

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
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.on_close())

    def on_close(self):
        if self.settings["save_gap_bg"]:
            self.settings["last_gap_bg"] = self.grid_bg_var.get()
            self.save_settings()
        self.root.destroy()
        sys.exit(0)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.settings.update(data)
            except: pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=4)
        except: pass

    def open_settings_window(self):
        win = Toplevel(self.root)
        win.title("Settings")
        win.geometry("400x440")
        win.configure(bg=BG)
        win.resizable(False, False)
        
        win.overrideredirect(True)
        
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + (root_w // 2) - 200
        y = root_y + (root_h // 2) - 220 
        win.geometry(f"400x440+{x}+{y}")

        container = Frame(win, bg=BG, highlightthickness=1, highlightbackground="#333333")
        container.pack(fill="both", expand=True)

        tb = CustomTitleBar(win, title_text="Settings", brand_color=self.brand_color, 
                            close_cmd=win.destroy, is_dialog=True)
        tb.pack(in_=container, side="top", fill="x")

        content = Frame(container, bg=BG)
        content.pack(fill="both", expand=True, padx=20)

        f_brand = Frame(content, bg=BG)
        f_brand.pack(fill="x", pady=(20, 10)) 
        Label(f_brand, text="Brand Color:", bg=BG, fg="#aaaaaa", font=("Segoe UI", 11)).pack(side="left")
        
        sv_brand = StringVar(value=self.settings["brand_color"])
        entry_brand = Entry(f_brand, textvariable=sv_brand, bg=BTN_BG, fg="white", font=("Segoe UI", 11), width=10, relief="flat")
        entry_brand.pack(side="right")
        
        preview_canv = Canvas(f_brand, width=26, height=26, bg=self.settings["brand_color"], highlightthickness=0, cursor="hand2")
        preview_canv.pack(side="right", padx=(0, 10))
        preview_canv.create_rectangle(0,0,25,25, outline="#555555", width=1)

        def open_picker(event=None):
            try:
                init_c = sv_brand.get()
                if len(init_c) != 7 or not init_c.startswith("#"): init_c = self.brand_color
                color = colorchooser.askcolor(color=init_c, title="Select Brand Color", parent=win)
                if color and color[1]: sv_brand.set(color[1])
            except: pass

        preview_canv.bind("<Button-1>", open_picker)
        
        def on_entry_change(*args):
            c = sv_brand.get()
            if len(c) == 7 and c.startswith("#"):
                try: preview_canv.config(bg=c)
                except: pass
        sv_brand.trace("w", on_entry_change)

        f_output = Frame(content, bg=BG)
        f_output.pack(fill="x", pady=5)
        
        Label(f_output, text="Output Location (Leave empty for default)", bg=BG, fg="#aaaaaa", font=("Segoe UI", 11)).pack(anchor="w")
        
        f_out_inner = Frame(f_output, bg=BG)
        f_out_inner.pack(fill="x", pady=(5, 0))
        
        sv_output = StringVar(value=self.settings.get("output_folder", ""))
        entry_output = Entry(f_out_inner, textvariable=sv_output, bg=BTN_BG, fg="white", font=("Segoe UI", 10), relief="flat")
        entry_output.pack(side="left", fill="x", expand=True, ipady=4)
        
        def browse_folder():
            d = filedialog.askdirectory(parent=win, title="Select Output Folder")
            if d:
                sv_output.set(d)

        btn_browse = Button(f_out_inner, text="...", bg=BTN_BG, fg="white", relief="flat", command=browse_folder, font=("Segoe UI", 10, "bold"), width=4)
        btn_browse.pack(side="right", padx=(5, 0))

        f_naming = Frame(content, bg=BG)
        f_naming.pack(fill="x", pady=15)
        
        Label(f_naming, text="Naming Convention", bg=BG, fg=self.brand_color, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(5,5))
        
        f_cp = Frame(f_naming, bg=BG)
        f_cp.pack(fill="x", pady=5)
        Label(f_cp, text="Collage Prefix:", bg=BG, fg="#aaaaaa", font=("Segoe UI", 11)).pack(side="left")
        sv_c_prefix = StringVar(value=self.settings.get("collage_prefix", "collage_"))
        Entry(f_cp, textvariable=sv_c_prefix, bg=BTN_BG, fg="white", font=("Segoe UI", 11), width=15, relief="flat").pack(side="right")

        f_cs = Frame(f_naming, bg=BG)
        f_cs.pack(fill="x", pady=5)
        Label(f_cs, text="Crop Suffix:", bg=BG, fg="#aaaaaa", font=("Segoe UI", 11)).pack(side="left")
        sv_c_suffix = StringVar(value=self.settings.get("crop_suffix", "_crop"))
        Entry(f_cs, textvariable=sv_c_suffix, bg=BTN_BG, fg="white", font=("Segoe UI", 11), width=15, relief="flat").pack(side="right")

        f_toggle = Frame(content, bg=BG)
        f_toggle.pack(fill="x", pady=15)
        Label(f_toggle, text="Save Gap Background Color", bg=BG, fg="#aaaaaa", font=("Segoe UI", 11)).pack(side="left")
        iv_save_gap = IntVar(value=1 if self.settings["save_gap_bg"] else 0)
        toggle = ModernToggle(f_toggle, variable=iv_save_gap, brand_color=self.brand_color)
        toggle.pack(side="right")

        lbl_link = Label(content, text="github.com/kekkodance/cropper", 
                         bg=BG, fg="#555555", font=("Segoe UI", 8), cursor="hand2")
        lbl_link.pack(side="bottom", pady=(0, 15))
        
        lbl_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/kekkodance/cropper"))
        lbl_link.bind("<Enter>", lambda e: lbl_link.config(fg="#888888"))
        lbl_link.bind("<Leave>", lambda e: lbl_link.config(fg="#555555"))

        f_btns = Frame(content, bg=BG)
        f_btns.pack(side="bottom", fill="x", pady=(10, 5))
        
        def save_and_close():
            new_color = sv_brand.get()
            valid = True
            if len(new_color) != 7 or not new_color.startswith("#"): valid = False
            else:
                try: win.winfo_rgb(new_color)
                except: valid = False
            
            if not valid:
                messagebox.showerror("Error", "Invalid Hex Color code.", parent=win)
                return

            self.settings["brand_color"] = new_color
            self.settings["save_gap_bg"] = bool(iv_save_gap.get())
            self.settings["collage_prefix"] = sv_c_prefix.get()
            self.settings["crop_suffix"] = sv_c_suffix.get()
            self.settings["output_folder"] = sv_output.get().strip()
            
            if self.settings["save_gap_bg"]: self.settings["last_gap_bg"] = self.grid_bg_var.get()
            self.save_settings()
            
            self.brand_color = new_color

            try:
                self.refresh_ui_colors()
            except Exception as e:
                print(f"UI Refresh Error: {e}")

            win.destroy()

        Button(f_btns, text="Save", bg=self.brand_color, fg="white", relief="flat", padx=20, pady=5, font=("Segoe UI", 10, "bold"), command=save_and_close).pack(side="right")
        Button(f_btns, text="Cancel", bg=BTN_BG, fg="#aaaaaa", relief="flat", padx=20, pady=5, font=("Segoe UI", 10), command=win.destroy).pack(side="right", padx=10)

    def refresh_ui_colors(self):
        self.slider.set_brand_color(self.brand_color)
        self.single_slider_gap.set_brand_color(self.brand_color)
        self.slider_cols.set_brand_color(self.brand_color)
        self.slider_gap.set_brand_color(self.brand_color)
        
        for mode, btn in self.btns.items():
            if mode == self.mode: btn.config(bg=self.brand_color)
        
        mode = self.effect_mode.get()
        if mode == "blur": self.btn_blur.config(bg=self.brand_color)
        if mode == "pixelate": self.btn_pixel.config(bg=self.brand_color)
        if self.effect_enabled.get() == 1: self.lbl_save_status.config(fg=self.brand_color)
        
        for side, active in self.banners_active.items():
            if active: 
                self.banner_btns[side].config(bg=self.brand_color)
                self.single_banner_btns[side].config(bg=self.brand_color)
            
        if self.banner_gap_enabled.get() == 1: self.btn_banner_gap.config(bg=self.brand_color)
        self.status_label.config(fg=self.brand_color)
        if self.mode_type == "single" and self.rect: self.draw_crop_rect()
        elif not self.original and not self.grid_tiles: self.draw_welcome()

        
    def load_assets(self):
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base_path = os.path.dirname(os.path.abspath(sys.argv[0]))

        icon_path = os.path.join(base_path, "icon.ico")
        png_path = os.path.join(base_path, "icon.png")

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
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except: pass

    def toggle_banner(self, side):
        self.banners_active[side] = not self.banners_active[side]
        is_active = self.banners_active[side]
        
        color = self.brand_color if is_active else BTN_BG
        fg = TEXT_ACTIVE if is_active else TEXT_INACTIVE
        
        self.banner_btns[side].config(bg=color, fg=fg)
        self.single_banner_btns[side].config(bg=color, fg=fg)
        
        self.update_bottom_ui_state()
        
        if self.mode_type == "single":
            self.display()
        else:
            self.display_grid()

    def toggle_banner_gap_state(self):
        new_state = 1 - self.banner_gap_enabled.get()
        self.banner_gap_enabled.set(new_state)
        if new_state == 1: self.btn_banner_gap.config(bg=self.brand_color, fg=TEXT_ACTIVE)
        else: self.btn_banner_gap.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        self.display_grid()

    def update_single_gap(self, val):
        self.single_gap.set(int(val))
        self.lbl_gap_single_val.config(text=str(int(val)))
        if self.mode_type == "single": self.display()

    def draw_bg_preview(self):
        self.bg_preview.delete("all")
        self.bg_preview_single.delete("all")
        color = self.grid_bg_var.get()
        try: 
            self.bg_preview.create_oval(2, 2, 20, 20, fill=color, outline="#555555", width=1)
            self.bg_preview_single.create_oval(2, 2, 20, 20, fill=color, outline="#555555", width=1)
        except: 
            self.bg_preview.create_oval(2, 2, 20, 20, fill=BG, outline="red", width=1)
            self.bg_preview_single.create_oval(2, 2, 20, 20, fill=BG, outline="red", width=1)

    def open_bg_picker(self, event=None):
        try:
            init_c = self.grid_bg_var.get()
            if len(init_c) != 7 or not init_c.startswith("#"): init_c = "#0d0d0d"
            color = colorchooser.askcolor(color=init_c, title="Select Background Color", parent=self.root)
            if color and color[1]:
                self.grid_bg_var.set(color[1])
                self.update_grid_bg()
        except: pass

    def update_grid_bg(self, event=None):
        val = self.grid_bg_var.get()
        if len(val) == 7 and val.startswith("#"):
            try:
                self.root.winfo_rgb(val)
                self.draw_bg_preview()
                if self.mode_type == "grid": self.display_grid()
                else: self.display()
                if self.settings["save_gap_bg"]:
                    self.settings["last_gap_bg"] = val
                    self.save_settings()
            except: pass

    def refresh_single_controls_layout(self):
        for widget in self.single_controls.winfo_children():
            widget.pack_forget()

        self.btn_blur.pack(side="left", padx=(0, 5))
        self.btn_pixel.pack(side="left", padx=(0, 5))

        self.lbl_intensity.pack(side="left", padx=(10, 5))
        self.slider.pack(side="left", padx=(0, 5))
        
        if not self.is_compact:
            self.lbl_val.pack(side="left", padx=(0, 15))

        self.lbl_banners_single.pack(side="left", padx=(5,5))
        for side in ['left', 'top', 'bottom', 'right']:
            self.single_banner_btns[side].pack(side="left", padx=2)

        self.lbl_gap_single.pack(side="left", padx=(15,5))
        self.single_slider_gap.pack(side="left", padx=(5, 5))
        
        if not self.is_compact:
            self.lbl_gap_single_val.pack(side="left", padx=(0, 15))
        
        if not self.is_compact:
            self.lbl_bg_single_text.pack(side="left", padx=(5, 5))
        
        self.bg_preview_single.pack(side="left", padx=(0, 5))
        
        if not self.is_compact:
            self.entry_bg_single.pack(side="left", ipady=4)

    def refresh_grid_controls_layout(self):
        for widget in self.grid_controls.winfo_children():
            widget.pack_forget()

        self.lbl_cols_text.pack(side="left", padx=(0,5))
        self.lbl_cols_val.pack(side="left")
        self.slider_cols.pack(side="left", padx=(10, 15))

        self.lbl_gap_text.pack(side="left", padx=(0,5))
        self.lbl_gap_val.pack(side="left")
        self.slider_gap.pack(side="left", padx=(10, 15))

        self.lbl_bg_grid_text.config(text="BG:" if self.is_compact else "Background:")
        self.lbl_bg_grid_text.pack(side="left", padx=(5, 5))
        
        self.bg_preview.pack(side="left", padx=(0, 5))
        
        if not self.is_compact:
            self.entry_bg.pack(side="left", ipady=4)

        self.lbl_banners_text.pack(side="left", padx=(15,5))
        for side in ['left', 'top', 'bottom', 'right']:
            self.banner_btns[side].pack(side="left", padx=2)
            
        self.btn_banner_gap.pack(side="left", padx=(10, 0))

    def get_single_layout_metrics(self, container_w, container_h, is_save=False):
        if self.original is None: return {'banners': {}, 'center': {'x':0, 'y':0, 'w':100, 'h':100}}

        has_banners = any(self.banners_active.values())
        
        if self.original_coords and has_banners:
            ox0, oy0, ox1, oy1 = self.original_coords
            W0 = abs(ox1 - ox0)
            H0 = abs(oy1 - oy0)
            if W0 < 1: W0 = 1
            if H0 < 1: H0 = 1
        elif isinstance(self.original, Image.Image):
            W0, H0 = self.original.size
        else:
            H0, W0 = self.original.shape[:2]

        gap = self.single_gap.get() if not is_save else int(self.single_gap.get() * (container_w / 1000.0 if is_save else 1)) 

        def get_banner_dim(side, adj_dim):
            img = self.banner_images[side]
            if img and img.original is not None:
                w, h = img.w, img.h
                ratio = h / w if side in ['top', 'bottom'] else w / h
                return adj_dim * ratio
            return adj_dim * DEFAULT_BANNER_THICKNESS_RATIO

        R_t = 0; R_b = 0; R_l = 0; R_r = 0
        
        if self.banners_active['top']:
            img = self.banner_images['top']
            if img and img.original is not None: R_t = img.h / img.w
            else: R_t = DEFAULT_BANNER_THICKNESS_RATIO
            
        if self.banners_active['bottom']:
            img = self.banner_images['bottom']
            if img and img.original is not None: R_b = img.h / img.w
            else: R_b = DEFAULT_BANNER_THICKNESS_RATIO

        if self.banners_active['left']:
            img = self.banner_images['left']
            if img and img.original is not None: R_l = img.w / img.h
            else: R_l = DEFAULT_BANNER_THICKNESS_RATIO
            
        if self.banners_active['right']:
            img = self.banner_images['right']
            if img and img.original is not None: R_r = img.w / img.h
            else: R_r = DEFAULT_BANNER_THICKNESS_RATIO

        gap_cnt_x = (1 if self.banners_active['left'] else 0) + (1 if self.banners_active['right'] else 0)
        gap_total_x = gap_cnt_x * gap
        
        gap_cnt_y = (1 if self.banners_active['top'] else 0) + (1 if self.banners_active['bottom'] else 0)
        gap_total_y = gap_cnt_y * gap
        
        term_w = W0 + H0 * (R_l + R_r)
        term_h = H0 + W0 * (R_t + R_b)
        
        avail_w = container_w - gap_total_x
        avail_h = container_h - gap_total_y
        
        if avail_w <= 0 or avail_h <= 0: return {'banners': {}, 'center': {'x':0,'y':0,'w':1,'h':1}}

        s_w = avail_w / term_w
        s_h = avail_h / term_h
        s = min(s_w, s_h)
        
        main_w = int(s * W0)
        main_h = int(s * H0)
        
        w_l = int(main_h * R_l)
        w_r = int(main_h * R_r)
        h_t = int(main_w * R_t)
        h_b = int(main_w * R_b)
        
        total_w = main_w + w_l + w_r + gap_total_x
        total_h = main_h + h_t + h_b + gap_total_y
        
        start_x = (container_w - total_w) // 2
        start_y = (container_h - total_h) // 2
        
        metrics = {'banners': {}, 'center': {}}
        
        curr_y = start_y
        if self.banners_active['top']:
            top_x = start_x + w_l + (gap if self.banners_active['left'] else 0)
            metrics['banners']['top'] = {'x': top_x, 'y': curr_y, 'w': main_w, 'h': h_t}
            curr_y += h_t + gap
            
        center_y = curr_y
        
        curr_x = start_x
        if self.banners_active['left']:
            metrics['banners']['left'] = {'x': curr_x, 'y': center_y, 'w': w_l, 'h': main_h}
            curr_x += w_l + gap
            
        metrics['center'] = {'x': curr_x, 'y': center_y, 'w': main_w, 'h': main_h}
        
        if self.banners_active['right']:
            right_x = curr_x + main_w + gap
            metrics['banners']['right'] = {'x': right_x, 'y': center_y, 'w': w_r, 'h': main_h}
            
        if self.banners_active['bottom']:
            bot_x = start_x + w_l + (gap if self.banners_active['left'] else 0)
            bot_y = center_y + main_h + gap
            metrics['banners']['bottom'] = {'x': bot_x, 'y': bot_y, 'w': main_w, 'h': h_b}

        return metrics

    def calculate_natural_grid_ar(self):
        cols = self.grid_cols.get()
        if not self.grid_tiles: return 1.0
        
        total_normalized_height = 0
        
        idx = 0
        while idx < len(self.grid_tiles):
            row_tiles = self.grid_tiles[idx : idx + cols]
            if not row_tiles: break
            
            row_aspect_sum = 0
            for t in row_tiles:
                if not hasattr(t, 'w') or not hasattr(t, 'h'):
                    if isinstance(t.original, np.ndarray):
                        h, w = t.original.shape[:2]
                    else:
                        w, h = t.original.size
                    t.w, t.h = w, h
                row_aspect_sum += (t.w / t.h)
            
            if row_aspect_sum > 0:
                total_normalized_height += (1.0 / row_aspect_sum)
                
            idx += cols
            
        if total_normalized_height == 0: return 1.0
        return 1.0 / total_normalized_height

    def get_layout_metrics(self, container_w, container_h, is_save=False):
        gap = self.grid_gap.get() if not is_save else int(self.grid_gap.get() * (container_w/1000))
        b_gap = gap if self.banner_gap_enabled.get() == 1 else 0

        def get_ratio(side, is_vertical_banner):
            img = self.banner_images[side]
            if img and img.original is not None:
                w, h = img.w, img.h
                if is_vertical_banner: return w / h
                else: return h / w
            return DEFAULT_BANNER_THICKNESS_RATIO

        r_l = get_ratio('left', True) if self.banners_active['left'] else 0
        r_r = get_ratio('right', True) if self.banners_active['right'] else 0
        r_t = get_ratio('top', False) if self.banners_active['top'] else 0
        r_b = get_ratio('bottom', False) if self.banners_active['bottom'] else 0

        gap_w_total = (b_gap if self.banners_active['left'] else 0) + (b_gap if self.banners_active['right'] else 0)
        gap_h_total = (b_gap if self.banners_active['top'] else 0) + (b_gap if self.banners_active['bottom'] else 0)

        avail_w = container_w - gap_w_total
        avail_h = container_h - gap_h_total
        
        if avail_w <= 0 or avail_h <= 0: return {'grid':{'x':0,'y':0,'w':1,'h':1}, 'banners':{}}

        targets = {"1:1":1.0, "4:3":1.333, "3:4":0.75, "16:9":1.777, "9:16":0.5625}
        grid_ar = targets.get(self.mode, None)
        
        if self.mode == "fit":
            grid_ar = self.calculate_natural_grid_ar()

        if grid_ar:
            h_based_on_w = avail_w / (r_l + r_r + grid_ar)
            h_based_on_h = avail_h / (1 + grid_ar * (r_t + r_b))
            h_grid = min(h_based_on_w, h_based_on_h)
            w_grid = h_grid * grid_ar
        else:
            sum_x = r_l + r_r; sum_y = r_t + r_b
            denom = 1 - (sum_x * sum_y)
            if abs(denom) < 0.001:
                w_grid = avail_w / (1 + sum_x); h_grid = avail_h / (1 + sum_y)
            else:
                h_grid = (avail_h - avail_w * sum_y) / denom
                w_grid = avail_w - h_grid * sum_x
                
            if h_grid <= 0 or w_grid <= 0:
                 h_grid = avail_h / (1 + sum_y); w_grid = avail_w / (1 + sum_x)

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
                                         'y': start_y, 'w': w_grid, 'h': h_top}
        
        grid_y = start_y + h_top + (b_gap if self.banners_active['top'] else 0)
        
        if self.banners_active['left']:
            metrics['banners']['left'] = {'x': start_x, 'y': grid_y, 'w': w_left, 'h': h_grid}
                                             
        grid_x = start_x + w_left + (b_gap if self.banners_active['left'] else 0)
        
        metrics['grid'] = {'x': grid_x, 'y': grid_y, 'w': w_grid, 'h': h_grid}
        
        if self.banners_active['right']:
            metrics['banners']['right'] = {'x': grid_x + w_grid + b_gap, 'y': grid_y, 'w': w_right, 'h': h_grid}
        
        if self.banners_active['bottom']:
            metrics['banners']['bottom'] = {'x': grid_x, 'y': grid_y + h_grid + b_gap, 'w': w_grid, 'h': h_bot}
                                             
        return metrics

    def cv2_to_imagetk(self, cv_img):
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        img = Image.frombuffer("RGB", (cv_img.shape[1], cv_img.shape[0]), rgb, 'raw', 'RGB', 0, 1)
        return ImageTk.PhotoImage(image=img)

    def on_drop(self, e):
        try: files = self.root.tk.splitlist(e.data)
        except: files = e.data.split()
        files = [f for f in files if os.path.isfile(f)]
        if not files: return
        
        mx = e.x_root - self.canvas.winfo_rootx()
        my = e.y_root - self.canvas.winfo_rooty()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()

        banner_metrics = None
        if self.mode_type == "grid":
             m = self.get_layout_metrics(cw, ch)
             banner_metrics = m['banners']
        else:
             m = self.get_single_layout_metrics(cw, ch)
             banner_metrics = m['banners']

        dropped_on_banner = False
        if banner_metrics:
            for side, rect in banner_metrics.items():
                if rect['x'] <= mx <= rect['x']+rect['w'] and rect['y'] <= my <= rect['y']+rect['h']:
                    self.banner_images[side] = GridTile(path=files[0])
                    dropped_on_banner = True
                    break
        
        if dropped_on_banner:
            if self.mode_type == "grid": self.display_grid()
            else: self.display()
            return

        if self.mode_type == "grid":
            self.grid_tiles.extend([GridTile(path=f) for f in files])
            self.update_window_title()
            self.show_status(f"Added {len(files)} images to grid")
            self.display_grid()
        
        elif self.original is not None:
            self.ask_replace_or_collage(files)
            
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
    
    def ask_replace_or_collage(self, files_list):
        dialog = Toplevel(self.root)
        dialog.title("Action")
        dialog.geometry("350x180")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        
        dialog.withdraw()
        
        dialog.overrideredirect(True)
        
        dialog.attributes("-topmost", True)

        
        container = Frame(dialog, bg=BG, highlightthickness=1, highlightbackground="#333333")
        container.pack(fill="both", expand=True)

        tb = CustomTitleBar(dialog, title_text="Action", brand_color=self.brand_color, 
                            close_cmd=dialog.destroy, is_dialog=True)
        tb.pack(in_=container, side="top", fill="x")

        content = Frame(container, bg=BG)
        content.pack(fill="both", expand=True, padx=20)

        Label(content, text="Add to Grid or Replace?", bg=BG, fg="white", 
              font=("Segoe UI", 12, "bold")).pack(pady=(15, 5))
        Label(content, text="You already have an image open.", bg=BG, fg="#888888", 
              font=("Segoe UI", 10)).pack(pady=(0, 20))

        btn_frame = Frame(content, bg=BG)
        btn_frame.pack(fill="x", pady=(0, 20))

        def do_replace():
            dialog.destroy()
            if len(files_list) > 1:
                self.set_ui_mode("grid")
                self.setup_grid(files_list)
            else:
                self.load(files_list[0])

        def do_collage():
            dialog.destroy()
            self.convert_to_collage(files_list)

        Button(btn_frame, text="Replace", bg=BTN_BG, fg="white", relief="flat", 
               font=("Segoe UI", 10), padx=15, pady=6, command=do_replace).pack(side="left", expand=True)
               
        Button(btn_frame, text="Create Collage", bg=self.brand_color, fg="white", relief="flat", 
               font=("Segoe UI", 10, "bold"), padx=15, pady=6, command=do_collage).pack(side="right", expand=True)

        
        dialog.update_idletasks() 

        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 90
        dialog.geometry(f"+{x}+{y}")
        
        dialog.deiconify()
        dialog.lift()
        
        dialog.focus_force() 
        
        dialog.after(10, dialog.grab_set) 
        
        self.root.wait_window(dialog)

    def convert_to_collage(self, new_files_list):
        current_path = self.path if self.path else "clipboard_img"
        
        if self.original is not None:
            rgb = cv2.cvtColor(self.original, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            base_tile = GridTile(path=current_path, img_obj=pil_img)
        else:
            base_tile = GridTile(path=current_path)
        
        self.grid_tiles = [base_tile]
        
        self.grid_tiles.extend([GridTile(path=p) for p in new_files_list])
        
        self.original = None
        self.processed_image = None
        self.rect = None
        self.coords = None
        
        self.set_ui_mode("grid")
        self.show_toolbar()
        
        count = len(self.grid_tiles)
        cols = 2 if count < 5 else 3
        self.slider_cols.set_value(cols)
        self.grid_cols.set(cols)
        self.lbl_cols_val.config(text=str(cols))
        
        self.update_window_title()
        self.show_status("Mode switched to Grid")
        self.display_grid()

    def update_window_title(self):
        if self.mode_type == "grid":
            count = len(self.grid_tiles)
            txt = f"{TITLE} - {count} Image{'s' if count != 1 else ''}"
        elif self.path:
            txt = f"{TITLE} - {Path(self.path).name}"
        else:
            txt = TITLE
            
        self.title_bar.title_lbl.config(text=txt)
        self.root.title(txt)


    def handle_click(self, e):
        if self.mode_type == "single":
            if self.original is None: return
            
            handle = self.get_handle_at(e.x, e.y)
            if handle:
                self.crop_action = handle
                self.crop_drag_start = (e.x, e.y)
                self.crop_start_coords = self.coords
                return

            if self.rect and self.is_inside_rect(e.x, e.y):
                self.crop_action = "move"
                self.crop_drag_start = (e.x, e.y)
                self.crop_start_coords = self.coords
                return

            if self.rect:
                self.canvas.delete(self.rect)
                self.canvas.delete("handle")
                self.rect = None
                self.original_coords = None
                self.processed_image = None 
                self.update_preview()
                self.update_bottom_ui_state()
            
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
            if self.original is None: return
            if self.crop_action == "create": self.drag_crop_create(e)
            elif self.crop_action == "move": self.drag_crop_move(e)
            elif self.crop_action in ["n", "s", "e", "w", "nw", "ne", "sw", "se"]: self.drag_crop_resize(e)     
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
            
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            
            is_outside = e.x < 0 or e.x > cw or e.y < 0 or e.y > ch
            
            self.canvas.delete("swap_highlight")
            self.canvas.delete("remove_indicator")
            
            if is_outside:
                self.canvas.config(cursor="X_cursor")
                self.canvas.create_text(e.x, e.y, text="🗑 Remove", fill="#FF4444", 
                                      font=("Segoe UI", 14, "bold"), tags="remove_indicator", anchor="s")
                metrics = self.get_layout_metrics(cw, ch)
                gr = metrics['grid']
                gx, gy, gw, gh = gr['x'], gr['y'], gr['w'], gr['h']
                sx, sy, sw, sh = self.get_cell_rect(self.swap_source_index, gx, gy, gw, gh)
                self.canvas.create_rectangle(sx+2, sy+2, sx+sw-2, sy+sh-2, outline="#FF4444", width=4, tags="swap_highlight")
                
            else:
                self.canvas.config(cursor="fleur")
                target = self.get_tile_at_pos(e.x, e.y)
                if target != -1 and target != self.swap_source_index:
                    metrics = self.get_layout_metrics(cw, ch)
                    gr = metrics['grid']
                    cx, cy, cw_rect, ch_rect = self.get_cell_rect(target, gr['x'], gr['y'], gr['w'], gr['h'])
                    self.canvas.create_rectangle(cx+2, cy+2, cx+cw_rect-2, cy+ch_rect-2, outline=HIGHLIGHT_COLOR, width=4, tags="swap_highlight")
                    
        elif self.mode_type == "single":
            if not self.drag_start_pos: return
            dx = e.x - self.drag_start_pos[0]
            dy = e.y - self.drag_start_pos[1]
            self.single_offset_x += dx
            self.single_offset_y += dy
            self.apply_single_pan_constraint()
            self.drag_start_pos = (e.x, e.y)
            self.display()

    def handle_right_release(self, e):
        if self.mode_type == "grid":
            self.canvas.delete("swap_highlight")
            self.canvas.delete("remove_indicator")
            self.canvas.config(cursor="")
            
            if self.swap_source_index == -1: return

            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            is_outside = e.x < 0 or e.x > cw or e.y < 0 or e.y > ch

            if is_outside:
                try:
                    del self.grid_tiles[self.swap_source_index]
                    self.show_status("Image removed")
                    
                    if not self.grid_tiles:
                        self.reset_app()
                    else:
                        count = len(self.grid_tiles)
                        if count == 1: 
                            self.slider_cols.set_value(1)
                            self.grid_cols.set(1)
                            self.lbl_cols_val.config(text="1")
                        
                        self.update_window_title()
                        self.display_grid()
                except: pass
            else:
                target = self.get_tile_at_pos(e.x, e.y)
                if target != -1 and target != self.swap_source_index:
                    self.grid_tiles[self.swap_source_index], self.grid_tiles[target] = self.grid_tiles[target], self.grid_tiles[self.swap_source_index]
                    self.display_grid()
            
            self.swap_source_index = -1

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
            self.display()


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
        
        self.rect = self.canvas.create_rectangle(*self.coords, outline=self.brand_color, width=2)
        
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
            self.canvas.create_rectangle(hx-r, hy-r, hx+r, hy+r, fill=self.brand_color, outline=BG, tags=("handle", tag))
        self.update_bottom_ui_state()

    def get_handle_at(self, x, y):
        if not self.coords: return None
        x0, y0, x1, y1 = self.coords
        xm, ym = (x0+x1)//2, (y0+y1)//2
        targets = [
            (x0, y0, "nw"), (xm, y0, "n"), (x1, y0, "ne"),
            (x1, ym, "e"), (x1, y1, "se"), (xm, y1, "s"),
            (x0, y1, "sw"), (x0, ym, "w")
        ]
        if self.mode != "free": targets = [t for t in targets if len(t[2]) == 2]
        r = HANDLE_SIZE 
        for hx, hy, name in targets:
            if hx-r <= x <= hx+r and hy-r <= y <= hy+r: return name
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
        metrics = self.get_single_layout_metrics(cw, ch)
        c_x, c_y, c_w, c_h = metrics['center']['x'], metrics['center']['y'], metrics['center']['w'], metrics['center']['h']
        
        disp_w, disp_h = self.displayed_size
        
        img_x = c_x + (c_w - disp_w) // 2 + self.single_offset_x
        img_y = c_y + (c_h - disp_h) // 2 + self.single_offset_y
        
        h, w = self.original.shape[:2]
        scale = disp_w / w
        
        cx0, cy0, cx1, cy1 = self.coords
        
        ox0 = (cx0 - img_x) / scale
        oy0 = (cy0 - img_y) / scale
        ox1 = (cx1 - img_x) / scale
        oy1 = (cy1 - img_y) / scale
        
        self.original_coords = (ox0, oy0, ox1, oy1)
        
        if self.effect_mode.get() != "none": self.update_preview_delayed()
        self.show_status("Press ENTER to save")
        self.start = None

    def apply_single_pan_constraint(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_single_layout_metrics(cw, ch)
        c_w, c_h = metrics['center']['w'], metrics['center']['h']
        
        render_w, render_h = self.displayed_size
        
        if self.original is None: return
        
        h, w = self.original.shape[:2]
        
        ratio = min(c_w / w, c_h / h)
        base_w = int(w * ratio)
        base_h = int(h * ratio)
        
        render_w = base_w * self.single_scale
        render_h = base_h * self.single_scale
        
        max_off_x = (render_w - c_w) / 2 if render_w > c_w else (c_w - render_w) / 2
        max_off_y = (render_h - c_h) / 2 if render_h > c_h else (c_h - render_h) / 2
        
        if render_w <= c_w: self.single_offset_x = 0
        else: self.single_offset_x = max(-max_off_x, min(max_off_x, self.single_offset_x))
            
        if render_h <= c_h: self.single_offset_y = 0
        else: self.single_offset_y = max(-max_off_y, min(max_off_y, self.single_offset_y))

    def apply_pan_constraint(self, tile, dx, dy, idx):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        gx, gy, gw, gh = metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']
        _, _, cell_w, cell_h = self.get_cell_rect(idx, gx, gy, gw, gh)
        
        img_ratio = tile.w / tile.h
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
        self.root.config(cursor="wait")
        self.canvas.config(cursor="wait")
        
        self.root.update()
        
        try:
            if self.mode_type == "single": 
                self.save_crop()
            else: 
                self.save_grid()
        except Exception as ex:
            print(f"Error saving: {ex}")
        finally:
            self.root.config(cursor="")
            self.canvas.config(cursor="")

    def cancel_action(self, e=None):
        if self.mode_type == "single":
            if self.rect:
                self.canvas.delete(self.rect)
                self.canvas.delete("handle")
                self.rect = None
                self.coords = None
                self.original_coords = None
                self.processed_image = None
                self.update_preview()
                self.update_bottom_ui_state()
            else: self.reset_app()
        else: self.reset_app()

    def reset_app(self):
        self.original = None
        self.path = None
        self.grid_tiles = []
        self.canvas.delete("all")
        gc.collect()
        self.status_label.config(text="") 
        self.draw_welcome()
        self.left_frame.pack_forget()
        self.set_ui_mode("single")
        self.lbl_save_status.pack_forget()
        self.single_controls.pack_forget()
        self.slider.pack_forget() 
        self.root.title(TITLE)
        self.update_window_title()
        self.buttons_shown = False
        self.banners_active = {k:False for k in self.banners_active}
        self.banner_images = {k:None for k in self.banner_images}
        for btn in self.banner_btns.values(): btn.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        for btn in self.single_banner_btns.values(): btn.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.coords = None
        self.original_coords = None
        self.rect = None
        self.processed_image = None

    def set_ui_mode(self, mode_type):
        self.mode_type = mode_type
        self.single_controls.pack_forget()
        self.grid_controls.pack_forget()
        
        if mode_type == "single":
            self.single_controls.pack(side="left", fill="y")
            self.lbl_save_status.pack(side="left", padx=(0, 15))
            self.refresh_single_controls_layout()
            
            if "fit" in self.btns:
                self.btns["fit"].pack_forget()
                if self.mode == "fit": 
                    self.set_mode_with_fade("free")
        else:
            self.grid_controls.pack(side="left", fill="y")
            self.lbl_save_status.pack_forget()
            
            if "fit" in self.btns:
                self.btns["fit"].pack(side="left", padx=4, pady=(0, PADDING))

    def update_bottom_ui_state(self):
        if self.mode_type == "grid": return
        mode = self.effect_mode.get()
        
        self.btn_blur.config(bg=self.brand_color if mode=="blur" else BTN_BG, fg=TEXT_ACTIVE if mode=="blur" else TEXT_INACTIVE)
        self.btn_pixel.config(bg=self.brand_color if mode=="pixelate" else BTN_BG, fg=TEXT_ACTIVE if mode=="pixelate" else TEXT_INACTIVE)
        
        banners_on = any(self.banners_active.values())
        effect_on = mode != "none"
        has_crop = self.original_coords is not None
        
        if banners_on:
            self.effect_enabled.set(1)
            if has_crop:
                self.lbl_save_status.config(text="Will save crop and banner/s", fg=self.brand_color)
            else:
                self.lbl_save_status.config(text="Will save full image", fg=self.brand_color)
        elif effect_on:
            self.effect_enabled.set(1)
            self.lbl_save_status.config(text="Will save full image", fg=self.brand_color)
        elif self.rect:
            self.effect_enabled.set(0)
            self.lbl_save_status.config(text="Will save crop selection", fg="#888888")
        else:
            self.effect_enabled.set(0)
            self.lbl_save_status.config(text="", fg="#888888")

    def set_mode_with_fade(self, mode):
        self.current_mode = mode; self.mode = mode
        for m, btn in self.btns.items():
            btn.config(bg=self.brand_color if m==mode else BTN_BG, fg=TEXT_ACTIVE if m==mode else TEXT_INACTIVE)
        if self.mode_type == "single":
            if self.rect: self.draw_crop_rect()
            if self.effect_mode.get() != "none": self.update_preview_delayed()
        else: self.display_grid()

    def animate_layout_transition(self, target_compact, step=0, steps=12):
        if step == 0 and self.anim_job:
            try: self.root.after_cancel(self.anim_job)
            except: pass

        start_w, end_w = (10, 6) if target_compact else (6, 10)
        ratio = step / steps
        curr_w = int(start_w + (end_w - start_w) * ratio)
        
        b_start_w, b_end_w = (6, 2) if target_compact else (2, 6)
        b_curr_w = int(b_start_w + (b_end_w - b_start_w) * ratio)

        font_cfg = ("Segoe UI", 10 if target_compact else 11, "bold")
        for mode, btn in self.btns.items(): btn.config(width=curr_w, font=font_cfg)
        
        if step == 0:
            def get_text(side): return side.capitalize()[0] if target_compact else side.capitalize()
            
            for side, btn in self.single_banner_btns.items():
                btn.config(text=get_text(side))
            
            for side, btn in self.banner_btns.items():
                btn.config(text=get_text(side))
        
        for btn in self.single_banner_btns.values():
            btn.config(width=b_curr_w)
            
        for btn in self.banner_btns.values():
            btn.config(width=b_curr_w)

        if step < steps: 
            self.anim_job = self.root.after(15, lambda: self.animate_layout_transition(target_compact, step+1, steps))
        else:
            self.anim_job = None

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
            with open(p, "rb") as f:
                arr = np.asarray(bytearray(f.read()), dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            
            self.original = img
            self.path = p
            self.single_scale = 1.0
            self.single_offset_x = 0
            self.single_offset_y = 0
            self.coords = None
            self.original_coords = None
            self.rect = None
            self.processed_image = None
            self.effect_mode.set("none") 
            self.mode = "free"
            self.current_mode = "free"
            self.canvas.delete("all")
            self.display()
            if not self.buttons_shown: self.show_toolbar()
            else: self.set_mode_with_fade("free")
            self.update_bottom_ui_state()
            self.update_window_title()
            self.show_status("Drag to Crop • Right-Click to Pan")
        except Exception as e:
            print(f"Load error: {e}")

    def load_image_object(self, img_obj):
        self.original = cv2.cvtColor(np.array(img_obj.convert("RGB")), cv2.COLOR_RGB2BGR)
        self.path = "clipboard_image.png"
        self.single_scale = 1.0
        self.single_offset_x = 0
        self.single_offset_y = 0
        self.coords = None
        self.original_coords = None
        self.rect = None
        self.processed_image = None
        self.effect_mode.set("none")
        self.mode = "free"
        self.current_mode = "free"
        self.canvas.delete("all")
        self.display()
        if not self.buttons_shown: self.show_toolbar()
        else: self.set_mode_with_fade("free")
        self.update_bottom_ui_state()
        self.update_window_title()
        self.show_status("Drag to Crop • Right-Click to Pan")

    def generate_processed_image(self):
        if self.original is None: 
            self.processed_image = None
            return

        if self.effect_mode.get() == "none":
            self.processed_image = None
            return

        val = int(self.strength.get())
        
        gpu_src = self.original
        
        if self.effect_mode.get() == "blur":
            h, w = self.original.shape[:2]
            max_dim = max(h, w)
            
            scale_factor = max_dim / 1000.0 
            
            k = int(val * 4 * scale_factor) + 1
            if k % 2 == 0: k += 1
            
            gpu_processed = cv2.GaussianBlur(gpu_src, (k, k), 0)
            
        elif self.effect_mode.get() == "pixelate" and val > 0:
            h, w = self.original.shape[:2]
            
            block_size = max(2, val * 2) 
            
            small_w = max(1, w // block_size)
            small_h = max(1, h // block_size)
            
            gpu_small = cv2.resize(gpu_src, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
            
            gpu_processed = cv2.resize(gpu_small, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            gpu_processed = gpu_src

        effect_layer = gpu_processed 
        
        if self.original_coords:
            ox0, oy0, ox1, oy1 = map(int, self.original_coords)
            h, w = self.original.shape[:2]
            
            mask = np.ones((h, w), dtype=np.uint8) * 255
            cv2.rectangle(mask, (ox0, oy0), (ox1, oy1), 0, -1)
            
            feather = max(5, int(min(w, h) * 0.01))
            if feather % 2 == 0: feather += 1
            mask = cv2.GaussianBlur(mask, (feather, feather), 0)
            
            mask_float = mask.astype(float) / 255.0
            mask_float = np.stack([mask_float]*3, axis=2)
            
            blended = (self.original * (1.0 - mask_float) + effect_layer * mask_float).astype(np.uint8)
            self.processed_image = blended
        else:
            self.processed_image = effect_layer

    def display(self):
        if self.original is None: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1: self.root.after(100, self.display); return
        self.canvas.delete("all")
        
        self.canvas.create_rectangle(0, 0, cw, ch, fill=CANVAS_BG, outline="")
        
        metrics = self.get_single_layout_metrics(cw, ch)
        
        center = metrics['center']
        min_x, min_y = center['x'], center['y']
        max_x, max_y = center['x'] + center['w'], center['y'] + center['h']
        
        for side, rect in metrics['banners'].items():
            min_x = min(min_x, rect['x']); min_y = min(min_y, rect['y'])
            max_x = max(max_x, rect['x'] + rect['w']); max_y = max(max_y, rect['y'] + rect['h'])
            
        gap_bg_color = self.grid_bg_var.get()
        try:
            self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=gap_bg_color, outline="")
        except:
            self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=BG, outline="")
        
        for side, rect in metrics['banners'].items():
            self.render_banner_image(side, rect)

        c_x, c_y, c_w, c_h = metrics['center']['x'], metrics['center']['y'], metrics['center']['w'], metrics['center']['h']
        
        source_img = self.original
        if self.processed_image is not None and self.effect_mode.get() != "none":
            source_img = self.processed_image

        banners_on = any(self.banners_active.values())

        if banners_on and self.original_coords:
            ox0, oy0, ox1, oy1 = map(int, self.original_coords)
            h, w = source_img.shape[:2]
            ox0 = max(0, ox0); oy0 = max(0, oy0)
            ox1 = min(w, ox1); oy1 = min(h, oy1)
            
            if ox1 > ox0 and oy1 > oy0:
                source_img = source_img[oy0:oy1, ox0:ox1]

        sh, sw = source_img.shape[:2]

        ratio = min(c_w/sw, c_h/sh)
        nw = int(sw * ratio * self.single_scale)
        nh = int(sh * ratio * self.single_scale)
        
        x = c_x + (c_w-nw)//2 + self.single_offset_x
        y = c_y + (c_h-nh)//2 + self.single_offset_y
        
        self.displayed_size = (nw, nh)

        try:
            final_img_tk = None
            draw_x, draw_y = x, y
            
            is_zoomed_heavily = (nw > cw * 3) or (nh > ch * 3)

            if is_zoomed_heavily:
                view_x1 = max(0, x)
                view_y1 = max(0, y)
                view_x2 = min(cw, x + nw)
                view_y2 = min(ch, y + nh)
                
                view_w = view_x2 - view_x1
                view_h = view_y2 - view_y1
                
                if view_w > 0 and view_h > 0:
                    current_scale = ratio * self.single_scale
                    
                    src_x = (view_x1 - x) / current_scale
                    src_y = (view_y1 - y) / current_scale
                    src_w = view_w / current_scale
                    src_h = view_h / current_scale
                    
                    pad = 2
                    sx1 = int(src_x) - pad
                    sy1 = int(src_y) - pad
                    sx2 = int(src_x + src_w) + pad + 1
                    sy2 = int(src_y + src_h) + pad + 1
                    
                    sx1 = max(0, sx1); sy1 = max(0, sy1)
                    sx2 = min(sw, sx2); sy2 = min(sh, sy2)
                    
                    if sx2 > sx1 and sy2 > sy1:
                        source_crop = source_img[sy1:sy2, sx1:sx2]
                        
                        target_crop_w = int((sx2 - sx1) * current_scale)
                        target_crop_h = int((sy2 - sy1) * current_scale)
                        
                        if target_crop_w > 0 and target_crop_h > 0:
                            resized = cv2.resize(source_crop, (target_crop_w, target_crop_h), interpolation=cv2.INTER_LINEAR)
                            final_img_tk = self.cv2_to_imagetk(resized)
                            draw_x = int(x + sx1 * current_scale)
                            draw_y = int(y + sy1 * current_scale)
            else:
                resized = cv2.resize(source_img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
                final_img_tk = self.cv2_to_imagetk(resized)
                draw_x, draw_y = x, y

            if final_img_tk:
                self.displayed_photo = final_img_tk
                self.canvas.create_rectangle(draw_x, draw_y, draw_x+final_img_tk.width(), draw_y+final_img_tk.height(), fill=CANVAS_BG, outline="")
                self.canvas.create_image(draw_x, draw_y, anchor=NW, image=final_img_tk, tags="image")
            
            if self.original_coords and not banners_on:
                ox0, oy0, ox1, oy1 = self.original_coords
                total_scale = nw / sw
                
                cx0 = (ox0 * total_scale) + x
                cy0 = (oy0 * total_scale) + y
                cx1 = (ox1 * total_scale) + x
                cy1 = (oy1 * total_scale) + y
                
                self.coords = (int(cx0), int(cy0), int(cx1), int(cy1))
                self.draw_crop_rect()
            elif banners_on and self.rect:
                self.canvas.delete(self.rect)
                self.canvas.delete("handle")
                self.rect = None
                
        except Exception as e: 
            print(f"Display Error: {e}")

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
        if self.mode_type != "single" or self.original is None: return
        
        if not self.coords and self.effect_mode.get() == "none":
            self.processed_image = None
        else:
            self.generate_processed_image()
            
        self.display()

    def save_crop(self):
        if self.original is None: return
        
        rgb_original = cv2.cvtColor(self.original, cv2.COLOR_BGR2RGB)
        pil_original = Image.fromarray(rgb_original)
        
        backup_original = self.original
        self.original = pil_original
        
        backup_banners = {}
        for side, tile in self.banner_images.items():
            if tile:
                backup_banners[side] = tile.original
                if isinstance(tile.original, np.ndarray):
                    rgb_tile = cv2.cvtColor(tile.original, cv2.COLOR_BGR2RGB)
                    tile.original = Image.fromarray(rgb_tile)

        try:
            has_banners = any(self.banners_active.values())
            is_effect_save = (self.effect_enabled.get() == 1) or has_banners

            if is_effect_save:
                
                img_w, img_h = self.original.size
                
                target_dim = max(img_w, img_h, 2500)
                container_size = int(target_dim * 1.5)

                metrics = self.get_single_layout_metrics(container_size, container_size, is_save=True)
                
                center = metrics['center']
                min_x = center['x']; min_y = center['y']
                max_x = center['x']+center['w']; max_y = center['y']+center['h']
                
                for side, rect in metrics['banners'].items():
                    min_x = min(min_x, rect['x']); min_y = min(min_y, rect['y'])
                    max_x = max(max_x, rect['x']+rect['w']); max_y = max(max_y, rect['y']+rect['h'])
                    
                final_w = max_x - min_x
                final_h = max_y - min_y
                
                bg_color = self.grid_bg_var.get()
                try: master = Image.new("RGB", (final_w, final_h), bg_color)
                except: master = Image.new("RGB", (final_w, final_h), BG)
                
                for side, rect in metrics['banners'].items():
                    tile = self.banner_images[side]
                    rw = rect['w']; rh = rect['h']
                    rx = rect['x'] - min_x
                    ry = rect['y'] - min_y
                    
                    if not tile:
                        draw = ImageDraw.Draw(master); draw.rectangle((rx, ry, rx+rw, ry+rh), fill="#151515")
                    else:
                        res = tile.original.resize((rw, rh), Image.Resampling.LANCZOS)
                        master.paste(res, (rx, ry))

                cx = center['x'] - min_x
                cy = center['y'] - min_y
                cw_save = center['w']
                ch_save = center['h']
                
                to_paste = self.original.copy()
                
                if self.original_coords:
                    ox0, oy0, ox1, oy1 = map(int, self.original_coords)
                    ox0 = max(0, ox0); oy0 = max(0, oy0)
                    ox1 = min(to_paste.width, ox1); oy1 = min(to_paste.height, oy1)
                    to_paste = to_paste.crop((ox0, oy0, ox1, oy1))
                
                if self.effect_mode.get() != "none":
                    full_img = to_paste.copy() 
                    val = int(self.strength.get())
                    
                    effect_layer = None

                    if self.effect_mode.get() == "blur": 
                        w, h = full_img.size
                        max_dim = max(w, h)
                        scale_factor = max_dim / 1000.0
                        radius = val * 2 * scale_factor
                        effect_layer = full_img.filter(ImageFilter.GaussianBlur(radius=radius))
                        
                    elif self.effect_mode.get() == "pixelate":
                        w, h = full_img.size
                        block_size = max(2, val * 2)
                        small = full_img.resize((max(1, w//block_size), max(1, h//block_size)), Image.Resampling.BILINEAR)
                        effect_layer = small.resize((w, h), Image.Resampling.NEAREST)
                    
                    if effect_layer is not None:
                        to_paste = effect_layer

                res_main = to_paste.resize((cw_save, ch_save), Image.Resampling.LANCZOS)
                master.paste(res_main, (cx, cy))
                
                final = master
                suffix_str = "_full"
            else: 
                if not self.original_coords: return
                ox0, oy0, ox1, oy1 = self.original_coords
                ox0 = max(0, ox0); oy0 = max(0, oy0)
                ox1 = min(self.original.width, ox1); oy1 = min(self.original.height, oy1)
                final = self.original.crop((int(ox0), int(oy0), int(ox1), int(oy1)))
                suffix_str = self.settings.get("crop_suffix", "_crop")

            p = Path(self.path)
            if p.name == "clipboard_image.png": base_name = "clipboard"
            else: base_name = p.stem
            
            custom_out = self.settings.get("output_folder", "")
            if custom_out and os.path.isdir(custom_out):
                parent_dir = Path(custom_out)
            else:
                parent_dir = p.parent

            out = parent_dir / f"{base_name}{suffix_str}{p.suffix}"
            i = 1
            while out.exists():
                out = parent_dir / f"{base_name}{suffix_str}_{i}{p.suffix}"
                i += 1
                
            final.save(out, quality=100)
            self.show_status(f"Saved: {out.name}")
        finally:
            self.original = backup_original
            for side, tile in self.banner_images.items():
                if tile and side in backup_banners:
                    tile.original = backup_banners[side]
                    
    def on_slider_move(self, val):
        self.strength.set(int(val)); self.lbl_val.config(text=str(int(val)))
        if self.mode_type == "single": self.cancel_pending_preview()

    def cancel_pending_preview(self):
        if self.preview_after_id: self.root.after_cancel(self.preview_after_id); self.preview_after_id = None

    def set_effect_type(self, mode):
        new_mode = "none" if self.effect_mode.get() == mode else mode
        self.effect_mode.set(new_mode)
        if new_mode != "none": self.effect_enabled.set(1)
        else: self.effect_enabled.set(0)
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
        
        self.canvas.create_rectangle(x, y, x+w, y+h, fill=CANVAS_BG, outline="")

        if not tile:
            self.canvas.create_rectangle(x, y, x+w, y+h, fill="#151515", outline="")
            self.canvas.create_text(x + w/2, y + h/2, text=side.upper(), fill="#333333", font=("Segoe UI", 14, "bold"))
            return
        try:
            small = cv2.resize(tile.original, (w, h), interpolation=cv2.INTER_LANCZOS4)
            tk_img = self.cv2_to_imagetk(small)
            tile.tk_ref = tk_img 
            self.canvas.create_image(x, y, anchor=NW, image=tk_img)
        except: pass

    def display_grid(self, only_index=-1):
        if not self.grid_tiles and not any(self.banner_images.values()): return
        if only_index == -1: self.canvas.delete("all")
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        metrics = self.get_layout_metrics(cw, ch)
        
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
            try: self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=bg_color, outline="")
            except: self.canvas.create_rectangle(min_x, min_y, max_x, max_y, fill=BG, outline="")
            
            for side, rect in metrics['banners'].items(): self.render_banner_image(side, rect)
        
        gx, gy, gw, gh = metrics['grid']['x'], metrics['grid']['y'], metrics['grid']['w'], metrics['grid']['h']
        indices = range(len(self.grid_tiles)) if only_index == -1 else [only_index]
        
        fit_mode = self.mode == "fit"
        cols = self.grid_cols.get()
        gap = self.grid_gap.get()

        for i in indices:
            tile = self.grid_tiles[i]
            
            if fit_mode:
                row = i // cols
                col = i % cols
                
                row_start = row * cols
                row_end = min(row_start + cols, len(self.grid_tiles))
                row_tiles = self.grid_tiles[row_start:row_end]
                
                row_ar_sum = 0
                for t in row_tiles:
                    if not hasattr(t, 'w') or not hasattr(t, 'h'):
                        if isinstance(t.original, np.ndarray): t.h, t.w = t.original.shape[:2]
                        else: t.w, t.h = t.original.size
                    row_ar_sum += (t.w / t.h)
                
                gap_space = (len(row_tiles) - 1) * gap
                available_w_for_images = gw - gap_space
                
                if row_ar_sum == 0: continue
                
                row_h = int(available_w_for_images / row_ar_sum)
                
                img_ar = tile.w / tile.h
                img_w = int(row_h * img_ar)
                
                current_x = gx
                for k in range(col):
                    prev_t = row_tiles[k]
                    prev_w = int(row_h * (prev_t.w / prev_t.h))
                    current_x += prev_w + gap
                
                current_y = gy
                for r_idx in range(row):
                    prev_row_start = r_idx * cols
                    prev_row_end = min(prev_row_start + cols, len(self.grid_tiles))
                    prev_row_tiles = self.grid_tiles[prev_row_start:prev_row_end]
                    prev_row_ar_sum = sum([(t.w/t.h) for t in prev_row_tiles])
                    prev_gap_space = (len(prev_row_tiles) - 1) * gap
                    prev_avail_w = gw - prev_gap_space
                    if prev_row_ar_sum > 0:
                        current_y += int(prev_avail_w / prev_row_ar_sum) + gap

                cx, cy, cw, ch = current_x, current_y, img_w, row_h
                
                render_w, render_h = img_w, row_h
                tile.offset_x, tile.offset_y = 0, 0
                
            else:
                cx, cy, cw, ch = self.get_cell_rect(i, gx, gy, gw, gh)
                
                if not hasattr(tile, 'w'): tile.h, tile.w = tile.original.shape[:2]
                
                img_ratio = tile.w / tile.h
                cell_ratio = cw / ch
                
                if img_ratio > cell_ratio: 
                    base_h = ch
                    base_w = int(base_h * img_ratio)
                else: 
                    base_w = cw
                    base_h = int(base_w / img_ratio)
                    
                render_w = int(base_w * tile.scale)
                render_h = int(base_h * tile.scale)
                
                max_off_x = (render_w - cw) / 2
                max_off_y = (render_h - ch) / 2
                
                if render_w < cw: tile.offset_x = 0
                else: tile.offset_x = max(-max_off_x, min(max_off_x, tile.offset_x))
                
                if render_h < ch: tile.offset_y = 0
                else: tile.offset_y = max(-max_off_y, min(max_off_y, tile.offset_y))

            try:
                self.canvas.create_rectangle(cx, cy, cx+cw, cy+ch, fill=CANVAS_BG, outline="")
                
                interpolation = cv2.INTER_LANCZOS4
                if render_w <= 0 or render_h <= 0: continue
                
                if fit_mode:
                    small = cv2.resize(tile.proxy, (render_w, render_h), interpolation=interpolation)
                    tk_img = self.cv2_to_imagetk(small)
                    tile.tk_ref = tk_img
                    self.canvas.delete(f"tile_{i}")
                    self.canvas.create_image(cx, cy, anchor=NW, image=tk_img, tags=f"tile_{i}")
                else:
                    small = cv2.resize(tile.proxy, (render_w, render_h), interpolation=interpolation)
                    img_cx = render_w // 2
                    img_cy = render_h // 2
                    left = img_cx - (cw // 2) - int(tile.offset_x)
                    top = img_cy - (ch // 2) - int(tile.offset_y)
                    right = left + cw
                    bottom = top + ch
                    
                    src_x_start = max(0, left)
                    src_y_start = max(0, top)
                    src_x_end = min(render_w, right)
                    src_y_end = min(render_h, bottom)
                    
                    dst_w = src_x_end - src_x_start
                    dst_h = src_y_end - src_y_start
                    
                    if dst_w > 0 and dst_h > 0:
                        cropped = small[src_y_start:src_y_end, src_x_start:src_x_end]
                        tk_img = self.cv2_to_imagetk(cropped)
                        tile.tk_ref = tk_img 
                        dest_x = cx + (src_x_start - left)
                        dest_y = cy + (src_y_start - top)
                        self.canvas.delete(f"tile_{i}")
                        self.canvas.create_image(dest_x, dest_y, anchor=NW, image=tk_img, tags=f"tile_{i}")

            except Exception as e: 
                print(f"Grid Render Error: {e}")

    def save_grid(self):
        backup_tiles = []
        for tile in self.grid_tiles:
            backup_tiles.append(tile.original)
            rgb = cv2.cvtColor(tile.original, cv2.COLOR_BGR2RGB)
            tile.original = Image.fromarray(rgb)
            
        backup_banners = {}
        for side, tile in self.banner_images.items():
            if tile:
                backup_banners[side] = tile.original
                rgb_tile = cv2.cvtColor(tile.original, cv2.COLOR_BGR2RGB)
                tile.original = Image.fromarray(rgb_tile)
                
        try:
            base_grid_w = 3000
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            metrics_disp = self.get_layout_metrics(cw, ch)
            
            disp_gw = metrics_disp['grid']['w']; disp_gh = metrics_disp['grid']['h']
            if disp_gw == 0: return
            grid_ar = disp_gh / disp_gw
            base_grid_h = int(base_grid_w * grid_ar)
            
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
            try: master = Image.new("RGB", (final_w, final_h), bg_color)
            except: master = Image.new("RGB", (final_w, final_h), BG)
            
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
            
            fit_mode = self.mode == "fit"

            for i, tile in enumerate(self.grid_tiles):
                
                if fit_mode:
                    row = i // cols
                    col = i % cols
                    row_start = row * cols
                    row_end = min(row_start + cols, len(self.grid_tiles))
                    row_tiles = self.grid_tiles[row_start:row_end]
                    
                    row_ar_sum = 0
                    for t in row_tiles:
                        w, h = t.original.width, t.original.height
                        row_ar_sum += (w / h)
                    
                    gap_space = (len(row_tiles) - 1) * gap
                    avail_w = base_grid_w - gap_space
                    
                    if row_ar_sum == 0: continue
                    
                    row_h = int(avail_w / row_ar_sum)
                    
                    img_w, img_h = tile.original.width, tile.original.height
                    target_w = int(row_h * (img_w / img_h))
                    
                    tx = grid_x
                    for k in range(col):
                        pt = row_tiles[k]
                        pw = int(row_h * (pt.original.width / pt.original.height))
                        tx += pw + gap
                        
                    ty = grid_y
                    for r_idx in range(row):
                        pr_start = r_idx * cols
                        pr_end = min(pr_start + cols, len(self.grid_tiles))
                        pr_tiles = self.grid_tiles[pr_start:pr_end]
                        pr_sum = sum([t.original.width/t.original.height for t in pr_tiles])
                        p_gap = (len(pr_tiles)-1)*gap
                        if pr_sum > 0:
                            ty += int((base_grid_w - p_gap)/pr_sum) + gap
                            
                    res = tile.original.resize((target_w, row_h), Image.Resampling.LANCZOS)
                    master.paste(res, (tx, ty))
                    
                else:
                    row = i//cols; col = i%cols
                    if row == rows - 1 and len(self.grid_tiles) % cols != 0:
                        items_in_row = len(self.grid_tiles) % cols
                        cw = (base_grid_w - (gap * (items_in_row - 1))) // items_in_row
                    else: cw = cw_standard

                    tx = grid_x + col*(cw+gap); ty = grid_y + row*(ch+gap)
                    
                    ir = tile.original.width / tile.original.height
                    cr = cw / ch
                    
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

            prefix = self.settings.get("collage_prefix", "collage_")
            
            custom_out = self.settings.get("output_folder", "")
            
            if custom_out and os.path.isdir(custom_out):
                parent_dir = Path(custom_out)
                if self.grid_tiles and os.path.exists(self.grid_tiles[0].path):
                    p = Path(self.grid_tiles[0].path)
                    base_name = f"{prefix}{p.stem}"
                else:
                    base_name = f"{prefix}saved"
            else:
                if self.grid_tiles and os.path.exists(self.grid_tiles[0].path):
                    p = Path(self.grid_tiles[0].path)
                    parent_dir = p.parent
                    base_name = f"{prefix}{p.stem}"
                else: 
                    parent_dir = Path(".")
                    base_name = f"{prefix}saved"
            
            out = parent_dir / f"{base_name}.jpg"
            
            i = 1
            while out.exists():
                out = parent_dir / f"{base_name}_{i}.jpg"
                i += 1

            master.save(out, quality=100)
            self.show_status(f"Saved: {out.name}")
            
        finally:
            for i, tile in enumerate(self.grid_tiles):
                tile.original = backup_tiles[i]
            for side, tile in self.banner_images.items():
                if tile and side in backup_banners:
                    tile.original = backup_banners[side]

    def update_grid_cols(self, val):
        if int(val) != self.grid_cols.get():
            self.grid_cols.set(int(val)); self.lbl_cols_val.config(text=str(int(val))); self.display_grid()

    def update_grid_gap(self, val):
        if int(val) != self.grid_gap.get():
            self.grid_gap.set(int(val)); self.lbl_gap_val.config(text=str(int(val))); self.display_grid()

    def get_cell_rect(self, index, off_x, off_y, total_w, total_h):
        cols = self.grid_cols.get()
        count = len(self.grid_tiles)
        rows = math.ceil(count / cols)
        gap = self.grid_gap.get()

        row = index // cols
        col = index % cols

        if row == rows - 1 and count % cols != 0:
            items_in_this_row = count % cols
        else:
            items_in_this_row = cols

        cw_this_row = (total_w - (gap * (items_in_this_row - 1))) // items_in_this_row
        
        x = off_x + col * (cw_this_row + gap)

        is_last_visual_item = (col == items_in_this_row - 1)
        
        if is_last_visual_item:
            cw = (off_x + total_w) - x
        else:
            cw = cw_this_row

        ch_standard = (total_h - (gap * (rows - 1))) // rows
        y = off_y + row * (ch_standard + gap)

        if row == rows - 1:
            ch = (off_y + total_h) - y
        else:
            ch = ch_standard

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
        self.canvas.create_text(cx, cy-80, text="Cropper", fill=self.brand_color, font=("Segoe UI", 38, "bold"))
        self.canvas.create_text(cx, cy-15, text="Single or Collage", fill="white", font=("Segoe UI", 22))
        self.canvas.create_text(cx, cy+60, text="Drop one image to Crop\nDrop multiple to Tile\nCtrl+V to Paste", fill="#bbbbbb", font=("Segoe UI", 16), justify="center")

    def show_toolbar(self):
        if not self.buttons_shown:
            self.buttons_shown = True; self.left_frame.pack(side="left", fill="y")
            self.animate_layout_transition(self.root.winfo_width()<1050)
            for m in self.btns:
                if m == self.mode:
                    self.btns[m].config(bg=self.brand_color)
                    self.fade_in(self.btns[m], TEXT_ACTIVE)
                else:
                    self.btns[m].config(bg=BTN_BG)
                    self.fade_in(self.btns[m], TEXT_INACTIVE)

    def show_status(self, text):
        if self.status_label.cget("text")==text: return
        self.status_label.config(text=text); self.fade_in(self.status_label, self.brand_color)

    def on_resize(self):
        w = self.root.winfo_width()
        if self.original is not None or self.grid_tiles:
            if w<1300 and not self.is_compact: 
                self.is_compact = True
                self.animate_layout_transition(True)
                self.refresh_single_controls_layout() 
                self.refresh_grid_controls_layout()
            elif w>=1300 and self.is_compact: 
                self.is_compact = False
                self.animate_layout_transition(False)
                self.refresh_single_controls_layout() 
                self.refresh_grid_controls_layout()
        
        if self.mode_type == "single": self.display()
        else: self.display_grid()
        
        if self.original is None and not self.grid_tiles: self.draw_welcome()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = Cropper(root)
    root.mainloop()
