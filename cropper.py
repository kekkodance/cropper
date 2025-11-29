
import sys
import os
from pathlib import Path
import tkinter as tk
from tkinter import Canvas, NW, BOTH, Button, Frame, Label
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk

TITLE = "Cropper"
BRAND = "#0047AB"
BG = "#0d0d0d"
CANVAS_BG = "#111111"
BTN_BG = "#1a1a1a"
PADDING = 20

class cropper:
    def __init__(self, root):
        self.root = root
        self.root.title(TITLE)
        self.root.configure(bg=BG)
        self.root.geometry("1200x780")
        self.root.minsize(900, 600)

        # Icon
        icon_path = "icon.ico"
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # Top bar
        top_bar = Frame(root, bg=BG, height=60)
        top_bar.pack(fill="x", pady=(PADDING, 0), padx=PADDING)
        top_bar.pack_propagate(False)

        # Left: buttons container
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
        modes = [
            ("free", "Freeform", BTN_BG),
            ("1:1",  "1:1",      BTN_BG),
            ("4:3",  "4:3",      BTN_BG),
            ("16:9", "16:9",     BTN_BG),
            ("9:16", "9:16",     BTN_BG),
        ]

        for mode, text, default_bg in modes:
            btn = Button(self.left_frame, text=text, bg=default_bg, fg="white",
                         activebackground=default_bg, **base_style)
            btn.pack(side="left", padx=4)
            btn.config(command=lambda m=mode: self.set_mode_with_fade(m))
            self.btns[mode] = btn

        # Right: status text
        self.status_label = Label(top_bar, text="", fg=BG, bg=BG,
                                  font=("Segoe UI", 11, "bold"), anchor="e")
        self.status_label.pack(side="right", fill="y")

        # Canvas — no zoom, just perfect fit
        self.canvas = Canvas(root, bg=CANVAS_BG, highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True, padx=PADDING, pady=PADDING)

        self.original = None
        self.path = None
        self.photo = None
        self.start = None
        self.rect = None
        self.coords = None
        self.mode = "free"
        self.crop_done = False
        self.buttons_shown = False
        self.current_mode = "free"

        self.welcome_items = []
        self.draw_welcome()
        self.root.bind("<Configure>", lambda e: self.redraw_welcome() if not self.original else None)

        self.canvas.bind("<ButtonPress-1>", self.handle_click)
        self.canvas.bind("<B1-Motion>", self.drag_crop)
        self.canvas.bind("<ButtonRelease-1>", self.end_crop)

        self.root.bind("<Return>", self.save_crop)
        self.root.bind("<space>", self.save_crop)
        self.root.bind("<Escape>", self.cancel_crop)

        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        self.root.protocol("WM_DELETE_WINDOW", lambda: (root.quit(), root.destroy(), os._exit(0)))

    def draw_welcome(self):
        for item in self.welcome_items:
            self.canvas.delete(item)
        self.welcome_items = []

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100: return

        cx = w // 2
        cy = h // 2

        self.welcome_items.append(self.canvas.create_text(cx, cy - 80, text="Cropper", fill=BRAND, font=("Segoe UI", 38, "bold")))
        self.welcome_items.append(self.canvas.create_text(cx, cy - 15, text="Crops your Artwork", fill="white", font=("Segoe UI", 22)))
        self.welcome_items.append(self.canvas.create_text(cx, cy + 60, text="Drag & drop your image here\nor drop it on the .exe", fill="#bbbbbb", font=("Segoe UI", 16)))

    def redraw_welcome(self):
        if not self.original:
            self.canvas.delete("all")
            self.draw_welcome()

    def show_buttons_once(self):
        if self.buttons_shown: return
        self.buttons_shown = True
        self.left_frame.pack(side="left", before=self.status_label)
        self._fade_buttons_step(0)

    def _fade_buttons_step(self, step):
        if step > 20:
            for mode, btn in self.btns.items():
                target = BRAND if mode == "free" else BTN_BG
                btn.config(bg=target, fg="white")
            return
        alpha = step / 20.0
        for mode, btn in self.btns.items():
            target_bg = BRAND if mode == "free" else BTN_BG
            r1, g1, b1 = 13, 13, 13
            r2, g2, b2 = int(target_bg[1:3], 16), int(target_bg[3:5], 16), int(target_bg[5:7], 16)
            r = int(13 + (0 - 13) * alpha)
            g = int(13 + (71 - 13) * alpha)
            b = int(13 + (171 - 13) * alpha)
            btn.config(bg=f"#{r:02x}{g:02x}{b:02x}", fg="white")
        self.root.after(15, lambda: self._fade_buttons_step(step + 1))

    def set_mode_with_fade(self, mode):
        if not self.original or self.crop_done or mode == self.current_mode: return
        self.current_mode = mode
        self.mode = mode
        self._fade_mode_change(0, mode)

    def _fade_mode_change(self, step, target_mode):
        if step > 15:
            for m, btn in self.btns.items():
                btn.config(bg=BRAND if m == target_mode else BTN_BG)
            if self.rect:
                self.cancel_crop()
            return
        alpha = step / 15.0
        for m, btn in self.btns.items():
            if m == target_mode:
                r = int(26 + (228 - 26) * alpha)
                g = int(26 + (0 - 26) * alpha)
                b = int(26 + (83 - 26) * alpha)
                color = f"#{r:02x}{g:02x}{b:02x}"
                btn.config(bg=color)
            else:
                btn.config(bg=BTN_BG)
        self.root.after(20, lambda: self._fade_mode_change(step + 1, target_mode))

    def show_status(self, text, duration=3000):
        self.status_label.config(text=text)
        self._fade_status_in(0)
        self.root.after(duration, self.clear_status)

    def _fade_status_in(self, step):
        if step > 20:
            self.status_label.config(fg=BRAND)
            return
        alpha = step / 20.0
        r = int(13 + (228 - 13) * alpha)
        g = int(13 + (0 - 13) * alpha)
        b = int(13 + (83 - 13) * alpha)
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.status_label.config(fg=color)
        self.root.after(15, lambda: self._fade_status_in(step + 1))

    def clear_status(self):
        self.status_label.config(text="", fg=BG)

    def handle_click(self, e):
        if not self.original or self.crop_done: return
        if self.rect and not self.is_inside_rect(e.x, e.y):
            self.cancel_crop()
        self.start = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
            self.rect = None
        self.clear_status()

    def is_inside_rect(self, x, y):
        if not self.rect: return False
        coords = self.canvas.coords(self.rect)
        return (coords[0] <= x <= coords[2]) and (coords[1] <= y <= coords[3])

    def drag_crop(self, e):
        if not self.original or not self.start or self.crop_done: return
        self.canvas.delete(self.rect)
        x0, y0, x1, y1 = *self.start, e.x, e.y

        if self.mode == "1:1":
            s = min(abs(x1-x0), abs(y1-y0))
            x1, y1 = x0 + (s if x1 >= x0 else -s), y0 + (s if y1 >= y0 else -s)
        elif self.mode == "4:3":
            w = abs(x1-x0); h = w*3/4; y1 = y0 + (h if y1 >= y0 else -h)
        elif self.mode == "16:9":
            w = abs(x1-x0); h = w*9/16; y1 = y0 + (h if y1 >= y0 else -h)
        elif self.mode == "9:16":
            h = abs(y1-y0); w = h*9/16; x1 = x0 + (w if x1 >= x0 else -w)

        self.rect = self.canvas.create_rectangle(
            min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1),
            outline=BRAND, width=2
        )

    def end_crop(self, e):
        if not self.original or not self.start or self.crop_done: return
        x0, y0, x1, y1 = *self.start, e.x, e.y

        if self.mode != "free":
            if self.mode == "1:1":
                s = min(abs(x1-x0), abs(y1-y0))
                x1, y1 = x0 + (s if x1 >= x0 else -s), y0 + (s if y1 >= y0 else -s)
            elif self.mode == "4:3":
                w = abs(x1-x0); h = w*3/4; y1 = y0 + (h if y1 >= y0 else -h)
            elif self.mode == "16:9":
                w = abs(x1-x0); h = w*9/16; y1 = y0 + (h if y1 >= y0 else -h)
            elif self.mode == "9:16":
                h = abs(y1-y0); w = h*9/16; x1 = x0 + (w if x1 >= x0 else -w)

        if abs(x1-x0) < 40 or abs(y1-y0) < 40:
            self.cancel_crop()
            return

        self.coords = (int(min(x0,x1)), int(min(y0,y1)), int(max(x0,x1)), int(max(y0,y1)))

        self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1),
            outline=BRAND, width=2
        )

        self.show_status("Press ENTER or SPACE to save • ESC to cancel")

    def save_crop(self, e=None):
        if not self.original or not self.coords or self.crop_done: return
        self.crop_done = True
        cropped = self.original.crop(self.coords)
        out = Path(self.path)
        new_path = out.parent / f"{out.stem}_cropped{out.suffix}"
        i = 1
        while new_path.exists():
            new_path = out.parent / f"{out.stem}_cropped_{i}{out.suffix}"
            i += 1
        cropped.save(new_path, quality=98)
        self.show_status(f"Saved as: {new_path.name}", duration=3000)
        self.root.after(3000, self.reset_for_next_image)

    def cancel_crop(self, e=None):
        if self.crop_done: return
        self.canvas.delete(self.rect)
        self.rect = self.coords = self.start = None
        self.clear_status()

    def reset_for_next_image(self):
        self.original = self.path = self.photo = None
        self.start = self.rect = self.coords = None
        self.crop_done = False
        self.current_mode = "free"
        self.hide_toolbar()
        self.canvas.delete("all")
        self.draw_welcome()

    def hide_toolbar(self):
        self.left_frame.pack_forget()
        self.status_label.config(text="", fg=BG)
        self.buttons_shown = False

    def on_drop(self, e):
        path = e.data.strip("{}")
        if os.path.isfile(path):
            self.load(path)

    def load(self, p):
        try:
            img = Image.open(p).convert("RGB")
            self.original, self.path = img, p
            self.crop_done = False
            self.canvas.delete("all")
            self.display()
            self.show_buttons_once()
        except:
            pass

    def display(self):
        if not self.original: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        ratio = min(cw/self.original.width, ch/self.original.height)
        nw, nh = int(self.original.width * ratio), int(self.original.height * ratio)
        resized = self.original.resize((nw, nh), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized)
        x = (cw - nw) // 2
        y = (ch - nh) // 2
        self.canvas.create_image(x, y, anchor=NW, image=self.photo)


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = cropper(root)
    if len(sys.argv) > 1:
        p = sys.argv[1].strip("{}")
        if os.path.isfile(p):
            root.after(500, lambda: app.load(p))

    root.mainloop()
