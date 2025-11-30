import sys
import os
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import Canvas, NW, BOTH, Button, Frame, Label, IntVar, StringVar
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk, ImageFilter, ImageDraw

TITLE = "Cropper"
BRAND = "#0047AB"
BG = "#0d0d0d"
CANVAS_BG = "#111111"
BTN_BG = "#1a1a1a"
BTN_ACTIVE_BG = "#2a2a2a"
TEXT_INACTIVE = "#888888"
TEXT_ACTIVE = "#ffffff"
PADDING = 20

# --- CUSTOM MODERN SLIDER CLASS ---
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
        
        self.w = 0
        self.h = 30
        self.padding = 10

    def get(self):
        return self.value

    def set_value(self, val):
        self.value = max(self.from_, min(self.to, val))
        self.draw()

    def val_to_x(self, val):
        available_w = self.w - (self.padding * 2)
        ratio = (val - self.from_) / (self.to - self.from_)
        return self.padding + (available_w * ratio)

    def x_to_val(self, x):
        available_w = self.w - (self.padding * 2)
        relative_x = x - self.padding
        ratio = max(0, min(1, relative_x / available_w))
        return int(self.from_ + (ratio * (self.to - self.from_)))

    def draw(self, event=None):
        if event:
            self.w = event.width
            self.h = event.height
        
        self.delete("all")
        if self.w < 20: return

        # Draw Track
        cy = self.h // 2
        self.create_line(self.padding, cy, self.w - self.padding, cy, fill="#333333", width=4, capstyle="round")
        
        # Draw Active Track (Left of handle)
        cx = self.val_to_x(self.value)
        self.create_line(self.padding, cy, cx, cy, fill=BRAND, width=4, capstyle="round")

        # Draw Circular Handle
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
        self.root.geometry("1200x820")
        self.root.minsize(900, 650)

        # 1. Load Window Icon (.ico)
        icon_path = "icon.ico"
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # 2. Load Welcome Image (.png)
        self.welcome_icon_photo = None
        png_path = "icon.png"
        if getattr(sys, 'frozen', False):
            png_path = os.path.join(sys._MEIPASS, "icon.png")
        
        if os.path.exists(png_path):
            try:
                img = Image.open(png_path).convert("RGBA")
                img.thumbnail((128, 128), Image.Resampling.LANCZOS)
                self.welcome_icon_photo = ImageTk.PhotoImage(img)
            except Exception:
                pass

        # --- TOP BAR ---
        top_bar = Frame(root, bg=BG, height=60)
        top_bar.pack(fill="x", pady=(PADDING, 0), padx=PADDING)
        top_bar.pack_propagate(False)

        self.left_frame = Frame(top_bar, bg=BG)
        
        base_style = {
            "font": ("Segoe UI", 11, "bold"),
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 18,
            "pady": 12,
            "width": 10
        }

        self.btns = {}
        self.is_compact = False
        self.anim_job = None 
        
        modes = [
            ("free", "Freeform"),
            ("1:1",  "1:1"),
            ("4:3",  "4:3"),
            ("16:9", "16:9"),
            ("9:16", "9:16"),
        ]
        
        for mode, text in modes:
            btn = Button(self.left_frame, text=text, bg=BTN_BG, fg=BG,
                         activebackground=BTN_BG, **base_style)
            btn.pack(side="left", padx=4, pady=(0, PADDING))
            btn.config(command=lambda m=mode: self.set_mode_with_fade(m))
            self.btns[mode] = btn

        self.status_label = Label(top_bar, text="", fg=BG, bg=BG,
                                  font=("Segoe UI", 11, "bold"), anchor="e")
        self.status_label.pack(side="right", fill="y", padx=(0, 5), pady=(0, 15))

        # --- CANVAS ---
        self.canvas = Canvas(root, bg=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True, padx=PADDING, pady=(0, PADDING))
        self.canvas.bind("<Configure>", lambda e: self.on_resize())

        # --- BOTTOM BAR ---
        bottom_bar = Frame(root, bg=BG, height=80)
        bottom_bar.pack(fill="x", pady=(0, PADDING), padx=PADDING)
        bottom_bar.pack_propagate(False)

        # Variables
        self.effect_mode = StringVar(value="none")
        self.effect_enabled = IntVar(value=0)
        self.strength = IntVar(value=25)

        # Controls Container
        controls_frame = Frame(bottom_bar, bg=BG)
        controls_frame.pack(side="left", fill="y")

        control_btn_style = {
            "font": ("Segoe UI", 10, "bold"),
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 15,
            "pady": 8
        }

        # Effect Buttons
        self.btn_blur = Button(controls_frame, text="Blur", **control_btn_style,
                               command=lambda: self.set_effect_type("blur"))
        self.btn_pixel = Button(controls_frame, text="Pixelate", **control_btn_style,
                                command=lambda: self.set_effect_type("pixelate"))
        
        self.btn_blur.pack(side="left", padx=(0, 5))
        self.btn_pixel.pack(side="left", padx=(0, 20))

        # Full Image Toggle
        self.btn_full_img = Button(controls_frame, text="Save Crop", **control_btn_style,
                                   command=self.toggle_full_image_mode)
        self.btn_full_img.pack(side="left", padx=(0, 20))

        # Slider Container
        slider_container = Frame(bottom_bar, bg=BG)
        slider_container.pack(side="right", fill="x", expand=True, padx=(20, 0))
        
        # Numeric Value Label
        self.lbl_val = Label(slider_container, text="25", bg=BG, fg="#666666", width=3, font=("Segoe UI", 10))
        self.lbl_val.pack(side="right", padx=(10, 0))

        # Custom Slider Widget
        self.slider = ModernSlider(slider_container, from_=0, to=50, initial=25,
                                   command=self.on_slider_move,
                                   release_command=self.update_preview_delayed)
        self.slider.pack(side="right", fill="x", expand=True)

        # Intensity Label
        lbl_intensity = Label(slider_container, text="Intensity", bg=BG, fg="#888888", font=("Segoe UI", 10, "bold"))
        lbl_intensity.pack(side="right", padx=(0, 15))

        self.update_bottom_ui_state()
        
        # --- APPLY WINDOWS DARK MODE ---
        self.apply_windows_dark_mode()

        # --- LOGIC INIT ---
        self.preview_after_id = None
        self.original = None
        self.path = None
        self.displayed_photo = None
        self.displayed_size = (0, 0)
        self.start = None
        self.rect = None
        self.coords = None
        self.original_coords = None 
        self.mode = "free"
        self.buttons_shown = False
        self.current_mode = "free"
        self.welcome_items = []
        self.draw_welcome()

        self.canvas.bind("<ButtonPress-1>", self.handle_click)
        self.canvas.bind("<B1-Motion>", self.drag_crop)
        self.canvas.bind("<ButtonRelease-1>", self.end_crop)

        self.root.bind("<Return>", self.save_crop)
        self.root.bind("<space>", self.save_crop)
        self.root.bind("<Escape>", self.cancel_crop)

        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        self.root.protocol("WM_DELETE_WINDOW", lambda: (root.quit(), root.destroy(), os._exit(0)))

    def apply_windows_dark_mode(self):
        """Forces the Windows OS title bar to use Dark Mode."""
        try:
            self.root.update()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            get_parent = ctypes.windll.user32.GetParent
            hwnd = get_parent(self.root.winfo_id())
            rendering_policy = DWMWA_USE_IMMERSIVE_DARK_MODE
            value = ctypes.c_int(2)
            set_window_attribute(hwnd, rendering_policy, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    # --- RESPONSIVE ANIMATION LOGIC ---
    def animate_layout_transition(self, target_compact, step=0, steps=12):
        start_w, end_w = (10, 6) if target_compact else (6, 10)
        start_px, end_px = (18, 8) if target_compact else (8, 18)
        start_pp, end_pp = (4, 1) if target_compact else (1, 4)
        start_fs, end_fs = (11, 10) if target_compact else (10, 11)

        if step == 0:
            if self.anim_job:
                self.root.after_cancel(self.anim_job)
            self.is_compact = target_compact
            if target_compact:
                self.btns["free"].config(text="Free")

        ratio = step / steps
        curr_w = int(start_w + (end_w - start_w) * ratio)
        curr_px = int(start_px + (end_px - start_px) * ratio)
        curr_pp = int(start_pp + (end_pp - start_pp) * ratio)
        curr_fs = int(start_fs + (end_fs - start_fs) * ratio)

        font_cfg = ("Segoe UI", curr_fs, "bold")

        for mode, btn in self.btns.items():
            btn.config(width=curr_w, padx=curr_px, font=font_cfg)
            btn.pack_configure(padx=curr_pp)

        if step < steps:
            self.anim_job = self.root.after(15, lambda: self.animate_layout_transition(target_compact, step + 1, steps))
        else:
            self.anim_job = None
            if not target_compact:
                self.btns["free"].config(text="Freeform")

    # --- FADE ANIMATION HELPERS ---
    def hex_to_rgb(self, hex_col):
        hex_col = hex_col.lstrip('#')
        return tuple(int(hex_col[i:i+2], 16) for i in (0, 2, 4))

    def rgb_to_hex(self, rgb):
        return '#%02x%02x%02x' % rgb

    def fade_in(self, widget, target_hex, steps=20, step=0):
        if step == 0: widget.config(fg=BG)
        start_rgb = self.hex_to_rgb(BG)
        end_rgb = self.hex_to_rgb(target_hex)
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * (step / steps))
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * (step / steps))
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * (step / steps))
        current_hex = self.rgb_to_hex((r, g, b))
        try: widget.config(fg=current_hex)
        except Exception: return
        if step < steps:
            self.root.after(25, lambda: self.fade_in(widget, target_hex, steps, step+1))

    # --- UI STATE HELPERS ---

    def on_slider_move(self, val):
        self.strength.set(int(val))
        self.lbl_val.config(text=str(int(val)))
        self.cancel_pending_preview()

    def set_effect_type(self, mode):
        current = self.effect_mode.get()
        if current == mode:
            self.effect_mode.set("none")
        else:
            self.effect_mode.set(mode)
        self.update_bottom_ui_state()
        self.update_preview_delayed()

    def toggle_full_image_mode(self):
        curr = self.effect_enabled.get()
        self.effect_enabled.set(1 if curr == 0 else 0)
        self.update_bottom_ui_state()

    def update_bottom_ui_state(self):
        mode = self.effect_mode.get()
        if mode == "blur":
            self.btn_blur.config(bg=BRAND, fg=TEXT_ACTIVE)
            self.btn_pixel.config(bg=BTN_BG, fg=TEXT_INACTIVE)
        elif mode == "pixelate":
            self.btn_blur.config(bg=BTN_BG, fg=TEXT_INACTIVE)
            self.btn_pixel.config(bg=BRAND, fg=TEXT_ACTIVE)
        else:
            self.btn_blur.config(bg=BTN_BG, fg=TEXT_INACTIVE)
            self.btn_pixel.config(bg=BTN_BG, fg=TEXT_INACTIVE)

        if self.effect_enabled.get() == 1:
            self.btn_full_img.config(text="Save Image", bg=BRAND, fg=TEXT_ACTIVE)
        else:
            self.btn_full_img.config(text="Save Crop", bg=BTN_BG, fg=TEXT_INACTIVE)

    # --- REST OF APP LOGIC ---

    def draw_welcome(self):
        for item in self.welcome_items:
            self.canvas.delete(item)
        self.welcome_items = []
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100: return
        cx = w // 2
        cy = (h // 2) + 40

        # DRAW ICON AND SHIFT TEXT IF EXISTS
        if self.welcome_icon_photo:
            self.welcome_items.append(self.canvas.create_image(cx, cy - 170, image=self.welcome_icon_photo))
            title_y = cy - 70
            sub_y = cy
            hint_y = cy + 80
        else:
            title_y = cy - 80
            sub_y = cy - 15
            hint_y = cy + 60

        self.welcome_items.append(self.canvas.create_text(cx, title_y, text="Cropper", fill=BRAND, font=("Segoe UI", 38, "bold")))
        self.welcome_items.append(self.canvas.create_text(cx, sub_y, text="Crops your Artwork", fill="white", font=("Segoe UI", 22)))
        self.welcome_items.append(self.canvas.create_text(cx, hint_y, text="Drag & drop your image here\nor drop it on the .exe", fill="#bbbbbb", font=("Segoe UI", 16), justify="center"))

    def redraw_welcome(self):
        if not self.original:
            self.canvas.delete("all")
            self.draw_welcome()

    def show_buttons_once(self):
        if self.buttons_shown: return
        self.buttons_shown = True
        self.left_frame.pack(side="left", fill="y")
        
        w = self.root.winfo_width()
        if w < 1050: 
            self.animate_layout_transition(True, step=12)

        for mode in self.btns:
            btn = self.btns[mode]
            is_active = (mode == self.current_mode)
            btn.config(bg=BRAND if is_active else BTN_BG)
            target_col = TEXT_ACTIVE if is_active else TEXT_INACTIVE
            self.fade_in(btn, target_col)

    def set_mode_with_fade(self, mode):
        if not self.original or mode == self.current_mode: return
        self.current_mode = mode
        self.mode = mode
        for m, btn in self.btns.items():
            if m == mode:
                btn.config(bg=BRAND, fg=TEXT_ACTIVE)
            else:
                btn.config(bg=BTN_BG, fg=TEXT_INACTIVE)

        if self.rect:
            self.cancel_crop()
        if self.effect_mode.get() != "none":
            self.update_preview_delayed()

    def show_status(self, text):
        current_text = self.status_label.cget("text")
        if text != current_text:
            self.status_label.config(text=text)
            self.fade_in(self.status_label, BRAND)

    def show_enter_message_status(self):
        self.show_status("Press ENTER or SPACE to save • ESC to cancel")

    def handle_click(self, e):
        if not self.original: return
        if self.rect and not self.is_inside_rect(e.x, e.y):
            self.cancel_crop()
        self.start = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
            self.rect = None
            self.original_coords = None
        self.show_enter_message_status()

    def is_inside_rect(self, x, y):
        if not self.rect: return False
        coords = self.canvas.coords(self.rect)
        return (coords[0] <= x <= coords[2]) and (coords[1] <= y <= coords[3])

    def _apply_aspect_to_coords(self, x0, y0, x1, y1, mode):
        if mode == "free": return (x0, y0, x1, y1)
        dx = x1 - x0
        dy = y1 - y0
        if mode == "1:1": target = 1.0
        elif mode == "4:3": target = 4.0/3.0
        elif mode == "16:9": target = 16.0/9.0
        elif mode == "9:16": target = 9.0/16.0
        else: return (x0, y0, x1, y1)
        sign_x = 1 if dx >= 0 else -1
        sign_y = 1 if dy >= 0 else -1
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        if abs_dx == 0 and abs_dy == 0: return (x0, y0, x1, y1)
        if abs_dx/max(1e-6,abs_dy) > target:
            new_w = target*abs_dy
            new_h = abs_dy
        else:
            new_w = abs_dx
            new_h = abs_dx/max(1e-6,target)
        new_dx = new_w*sign_x
        new_dy = new_h*sign_y
        return (x0, y0, x0+new_dx, y0+new_dy)

    def drag_crop(self, e):
        if not self.original or not self.start: return
        x0, y0 = self.start
        x1, y1 = e.x, e.y
        x0c, y0c, x1c, y1c = self._apply_aspect_to_coords(x0, y0, x1, y1, self.mode)
        if abs(x1c-x0c)<2 or abs(y1c-y0c)<2: return
        self.coords = (int(min(x0c,x1c)), int(min(y0c,y1c)), int(max(x0c,x1c)), int(max(y0c,y1c)))
        if self.rect: self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)

    def end_crop(self, e):
        if not self.original or not self.start: return
        x0, y0 = self.start
        x1, y1 = e.x, e.y
        x0c, y0c, x1c, y1c = self._apply_aspect_to_coords(x0, y0, x1, y1, self.mode)
        
        if abs(x1c-x0c)<40 or abs(y1c-y0c)<40:
            self.cancel_crop()
            return
        
        self.coords = (int(min(x0c,x1c)), int(min(y0c,y1c)), int(max(x0c,x1c)), int(max(y0c,y1c)))
        
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        disp_w, disp_h = self.displayed_size
        if disp_w > 0:
            img_x = (cw - disp_w) // 2
            img_y = (ch - disp_h) // 2
            scale = disp_w / self.original.width
            
            ox0 = (self.coords[0] - img_x) / scale
            oy0 = (self.coords[1] - img_y) / scale
            ox1 = (self.coords[2] - img_x) / scale
            oy1 = (self.coords[3] - img_y) / scale
            self.original_coords = (ox0, oy0, ox1, oy1)

        if self.rect: self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)
        self.show_enter_message_status()
        if self.effect_mode.get() != "none":
            self.update_preview_delayed()

    def cancel_pending_preview(self):
        if self.preview_after_id:
            self.root.after_cancel(self.preview_after_id)
            self.preview_after_id = None

    def update_preview_delayed(self):
        self.cancel_pending_preview()
        self.preview_after_id = self.root.after(50, self.update_preview)

    def on_resize(self):
        if self.original:
            w = self.root.winfo_width()
            if w < 1050 and not self.is_compact:
                self.animate_layout_transition(True)
            elif w >= 1050 and self.is_compact:
                self.animate_layout_transition(False)

            self.display()
            if self.original_coords:
                cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
                disp_w, disp_h = self.displayed_size
                if disp_w > 0:
                    img_x = (cw - disp_w) // 2
                    img_y = (ch - disp_h) // 2
                    scale = disp_w / self.original.width
                    ox0, oy0, ox1, oy1 = self.original_coords
                    nx0 = int(img_x + (ox0 * scale))
                    ny0 = int(img_y + (oy0 * scale))
                    nx1 = int(img_x + (ox1 * scale))
                    ny1 = int(img_y + (oy1 * scale))
                    self.coords = (nx0, ny0, nx1, ny1)
                    if self.rect: self.canvas.delete(self.rect)
                    self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)
            elif self.coords and self.rect:
                 self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)
            if self.effect_mode.get() != "none":
                self.update_preview_delayed()
        else:
            self.redraw_welcome()

    def update_preview(self):
        if not self.original or not self.coords: return
        
        if self.effect_mode.get() == "none":
            self.display()
            if self.rect: self.canvas.delete(self.rect)
            self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)
            return

        cw,ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        disp_w, disp_h = self.displayed_size
        if disp_w==0 or disp_h==0: self.display()
        disp_w, disp_h = self.displayed_size
        img_x = (cw-disp_w)//2
        img_y = (ch-disp_h)//2
        scale_x = self.original.width/disp_w
        scale_y = self.original.height/disp_h
        x0, y0, x1, y1 = self.coords
        ox0 = int(max(0,min(self.original.width,(x0-img_x)*scale_x)))
        oy0 = int(max(0,min(self.original.height,(y0-img_y)*scale_y)))
        ox1 = int(max(0,min(self.original.width,(x1-img_x)*scale_x)))
        oy1 = int(max(0,min(self.original.height,(y1-img_y)*scale_y)))
        preview = self.original.copy()
        strength = max(0,int(self.strength.get()))
        mask = Image.new("L", preview.size, 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((ox0,oy0,ox1,oy1), fill=0)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=20))
        if self.effect_mode.get()=="blur" and strength>0:
            effect = preview.filter(ImageFilter.GaussianBlur(radius=strength))
        elif self.effect_mode.get()=="pixelate" and strength>0:
            w,h = preview.size
            small_w = max(1,w//max(1,strength))
            small_h = max(1,h//max(1,strength))
            small = preview.resize((small_w,small_h), Image.Resampling.NEAREST)
            effect = small.resize(preview.size, Image.Resampling.NEAREST)
        else:
            effect = preview.copy()
        preview.paste(effect, mask=mask)
        ratio = min(cw/preview.width,ch/preview.height)
        new_w = int(preview.width*ratio)
        new_h = int(preview.height*ratio)
        resized = preview.resize((new_w,new_h), Image.Resampling.LANCZOS)
        self.displayed_photo = ImageTk.PhotoImage(resized)
        self.displayed_size = (new_w,new_h)
        self.canvas.delete("image")
        self.canvas.create_image((cw-new_w)//2,(ch-new_h)//2, anchor=NW, image=self.displayed_photo, tags="image")
        if self.rect:
            self.canvas.delete(self.rect)
            self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)

    def save_crop(self, e=None):
        if not self.original or not self.coords: return
        cw,ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        disp_w, disp_h = self.displayed_size
        img_x = (cw-disp_w)//2
        img_y = (ch-disp_h)//2
        scale_x = self.original.width/max(1,disp_w)
        scale_y = self.original.height/max(1,disp_h)
        x0,y0,x1,y1 = self.coords
        ox0 = int(max(0,min(self.original.width,(x0-img_x)*scale_x)))
        oy0 = int(max(0,min(self.original.height,(y0-img_y)*scale_y)))
        ox1 = int(max(0,min(self.original.width,(x1-img_x)*scale_x)))
        oy1 = int(max(0,min(self.original.height,(y1-img_y)*scale_y)))

        if self.effect_enabled.get() == 1 and self.effect_mode.get() != "none":
            full_img = self.original.copy()
            strength = max(0,int(self.strength.get()))
            
            if self.effect_mode.get()=="blur" and strength>0:
                effect_img = full_img.filter(ImageFilter.GaussianBlur(radius=strength))
            elif self.effect_mode.get()=="pixelate" and strength>0:
                w,h = full_img.size
                small_w = max(1,w//max(1,strength))
                small_h = max(1,h//max(1,strength))
                small = full_img.resize((small_w,small_h), Image.Resampling.NEAREST)
                effect_img = small.resize(full_img.size, Image.Resampling.NEAREST)
            else:
                effect_img = full_img.copy()

            mask = Image.new("L", full_img.size, 255)
            draw = ImageDraw.Draw(mask)
            draw.rectangle((ox0,oy0,ox1,oy1), fill=0)
            mask = mask.filter(ImageFilter.GaussianBlur(radius=20))

            full_img.paste(effect_img, mask=mask)
            to_save = full_img
        else:
            to_save = self.original.crop((ox0,oy0,ox1,oy1))

        out = Path(self.path)
        new_path = out.parent/f"{out.stem}_cropped{out.suffix}"
        i=1
        while new_path.exists():
            new_path = out.parent/f"{out.stem}_cropped_{i}{out.suffix}"
            i+=1
        to_save.save(new_path, quality=98)
        self.show_status(f"Saved as: {new_path.name}")

    def cancel_crop(self, e=None):
        if self.rect:
            try: self.canvas.delete(self.rect)
            except Exception: pass
        self.rect = None
        self.coords = None
        self.original_coords = None
        self.start = None
        self.show_enter_message_status()
        self.redraw_image()

    def reset_for_next_image(self):
        self.original = None
        self.path = None
        self.displayed_photo = None
        self.displayed_size = (0,0)
        self.start = None
        self.rect = None
        self.coords = None
        self.original_coords = None
        self.buttons_shown = False
        self.current_mode = "free"
        self.hide_toolbar()
        self.canvas.delete("all")
        self.draw_welcome()
        self.root.title(TITLE)

    def hide_toolbar(self):
        self.left_frame.pack_forget()
        self.status_label.config(text="", fg=BG)

    def on_drop(self, e):
        path = e.data.strip("{}")
        if os.path.isfile(path):
            self.load(path)

    def load(self, p):
        try:
            img = Image.open(p).convert("RGB")
            self.original = img
            self.path = p
            self.canvas.delete("all")
            self.display()
            self.show_buttons_once()
            self.show_enter_message_status()
            filename = Path(p).name
            self.root.title(f"{TITLE} - {filename}")
        except Exception:
            pass

    def display(self):
        if not self.original: return
        cw,ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw<=1 or ch<=1: self.root.after(50, self.display); return
        ratio = min(cw/self.original.width,ch/self.original.height)
        nw,nh = int(self.original.width*ratio), int(self.original.height*ratio)
        resized = self.original.resize((nw,nh), Image.Resampling.LANCZOS)
        self.displayed_photo = ImageTk.PhotoImage(resized)
        self.displayed_size = (nw,nh)
        x = (cw-nw)//2
        y = (ch-nh)//2
        self.canvas.delete("image")
        self.canvas.create_image(x,y, anchor=NW, image=self.displayed_photo, tags="image")

    def redraw_image(self):
        if not self.original: return
        self.display()
        if self.coords and self.rect:
            self.rect = self.canvas.create_rectangle(*self.coords, outline=BRAND, width=2)

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = Cropper(root)
    if len(sys.argv)>1:
        p = sys.argv[1].strip("{}")
        if os.path.isfile(p):
            root.after(500, lambda: app.load(p))
    root.mainloop()
