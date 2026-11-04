"""
Indie Now · MusoSoup — interfaz (estética IndieDL), AUTOCONTENIDA
================================================================
Incluye el kit visual (antes `indie_ui.py`), así que MusoSoup no depende de
ningún otro archivo de la carpeta. Solo necesita Pillow.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
from tkinter import filedialog, messagebox

import math
import time
import tkinter as tk
from collections import OrderedDict
from tkinter import font as tkfont

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    PIL_OK = True
except Exception:  # pragma: no cover - sin Pillow la app sigue funcionando
    PIL_OK = False

# ─────────────────────────────────────────────────────────────
# PALETA / TIPOGRAFÍA
# ─────────────────────────────────────────────────────────────
BG = "#0D1116"          # fondo de ventana (IndieDL)
BG_DEEP = "#0A0F14"     # consola / insets
BLACK = "#0A0D10"
SURFACE = "#151B21"     # tarjetas
SURFACE_2 = "#1A2129"
FIELD = "#20272E"       # inputs / botones oscuros
FIELD_H = "#2B333C"
BORDER = "#303942"
BORDER_SOFT = "#262F38"
BORDER_FIELD = "#39434D"
TEXT = "#F4F6F8"
MUTED = "#AAB4BE"
DIM = "#6E7A87"
YEL = "#FFF333"
YEL_H = "#FFE600"
YEL_DIM = "#C9BE2A"
GREEN = "#4ADE80"
GREEN_BG = "#10231A"
RED = "#FF5B65"
RED_BG = "#241114"
AMBER = "#FFC24B"
AMBER_BG = "#241E10"

F_BLACK = "Segoe UI Black"
F_SEMI = "Segoe UI Semibold"
F_BODY = "Segoe UI"
F_MONO = "Consolas"


def init_fonts(root):
    """Ajusta las familias a lo que realmente tenga el sistema."""
    global F_BLACK, F_SEMI, F_BODY, F_MONO
    try:
        fams = set(tkfont.families(root))
    except Exception:
        return

    def pick(*cands):
        for c in cands:
            if c in fams:
                return c
        return "Arial"

    F_BLACK = pick("Segoe UI Black", "Arial Black", "Segoe UI", "Arial")
    F_SEMI = pick("Segoe UI Semibold", "Segoe UI", "Arial")
    F_BODY = pick("Segoe UI", "Arial")
    F_MONO = pick("Consolas", "Cascadia Mono", "Courier New")


# ─────────────────────────────────────────────────────────────
# COLOR / IMAGEN
# ─────────────────────────────────────────────────────────────
def _rgb(color):
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Mezcla dos colores hex (t=0 → a, t=1 → b)."""
    t = max(0.0, min(1.0, t))
    ca, cb = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def spaced(text):
    """Texto con aire entre letras, como la banda del banner de IndieDL."""
    return "   ".join(" ".join(w) for w in text.split())


_CACHE = OrderedDict()
_CACHE_MAX = 220


def _cached(key, builder):
    try:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    except Exception:
        pass
    value = builder()
    _CACHE[key] = value
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return value


def rounded_image(w, h, radius, fill, border=None, border_w=1, glow=None,
                  bgcolor=None):
    """Rectángulo redondeado antialias (2x + LANCZOS).

    Si se pasa `bgcolor`, la imagen se genera OPACA con ese color en las
    esquinas: Tk dibuja mucho más rápido y sin fantasmas al scrollear.
    """
    w, h = max(2, int(w)), max(2, int(h))
    radius = max(0, min(int(radius), min(w, h) // 2))
    key = ("round", w, h, radius, fill, border, border_w, glow, bgcolor)

    def build():
        if not PIL_OK:
            return None
        s = 2 if w * h <= 1_200_000 else 1
        if bgcolor:
            img = Image.new("RGB", (w * s, h * s), bgcolor)
        else:
            img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [0, 0, w * s - 1, h * s - 1],
            radius=radius * s,
            fill=fill,
            outline=border or fill,
            width=max(1, border_w * s),
        )
        if glow:
            d.line([(radius * s, s), (w * s - radius * s, s)], fill=glow, width=s)
        if s > 1:
            img = img.resize((w, h), Image.LANCZOS)
        return img

    return _cached(key, build)


def card_image(w, h, radius=12, fill=SURFACE, border=BORDER, bgcolor=None):
    return rounded_image(w, h, radius, fill, border, 1,
                         glow=None if fill == BLACK else "#1E262E",
                         bgcolor=bgcolor)


def rounded_photo(w, h, radius, fill, border=None, border_w=1, glow=None,
                  bgcolor=None):
    img = rounded_image(w, h, radius, fill, border, border_w, glow, bgcolor)
    if img is None:
        return None
    return ImageTk.PhotoImage(img)


# ─────────────────────────────────────────────────────────────
# ARTE DE MARCA
# ─────────────────────────────────────────────────────────────
def _font_file(*names):
    for name in names:
        path = "C:/Windows/Fonts/" + name
        try:
            with open(path, "rb"):
                return path
        except Exception:
            continue
    return None


def banner_image(width, height=104):
    """Banner halftone 'INDIE NOW' con banda amarilla, como IndieDL."""
    width = max(320, int(width))
    height = int(height)
    key = ("banner", width, height)

    def build():
        if not PIL_OK:
            return None
        s = 2
        W, H = width * s, height * s
        img = Image.new("RGB", (W, H), "#F8F8F4")
        d = ImageDraw.Draw(img)

        path = _font_file("seguibl.ttf", "ariblk.ttf", "arialbd.ttf")
        size = int(H * 0.62)
        font = None
        target = W * 0.63
        while size > 12:
            try:
                font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()
            bbox = d.textbbox((0, 0), "INDIE NOW", font=font)
            if bbox[2] - bbox[0] <= target:
                break
            size -= 4
        text = "INDIE NOW"
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (W - tw) // 2 - bbox[0]
        ty = (H - th) // 2 - bbox[1]
        # Zona libre de trama alrededor del logo (knockout de imprenta).
        kx1 = tx + bbox[0] - int(16 * s)
        ky1 = ty + bbox[1] - int(8 * s)
        kx2 = tx + bbox[2] + int(16 * s)
        ky2 = ty + bbox[3] + int(9 * s)

        step = max(8, int(13 * s / 2))
        for row, y in enumerate(range(0, H, step)):
            for x in range(0, W, step):
                xx = x + (step // 2 if row % 2 else 0)
                if kx1 <= xx <= kx2 and ky1 <= y <= ky2:
                    continue
                il = max(0.0, 1 - math.hypot(xx, y) / (0.40 * W))
                ir = max(0.0, 1 - math.hypot(W - xx, y) / (0.26 * W))
                inten = max(il, ir) ** 1.15
                r = inten * step * 0.60
                if r > 0.8:
                    d.ellipse([xx - r, y - r, xx + r, y + r], fill="black")
        d.polygon([(int(W * .095), 0), (int(W * .145), 0),
                   (int(W * .095), int(H * .60)), (int(W * .055), int(H * .60))],
                  fill="black")

        d.rectangle([tx + bbox[0] - int(12 * s), ty + bbox[1] + int(th * .54),
                     tx + bbox[2] + int(12 * s), ty + bbox[3] + int(4 * s)],
                    fill="#FFF333")
        d.text((tx, ty), text, font=font, fill="#0A0D10")
        img = img.resize((width, height), Image.LANCZOS)
        return img

    return _cached(key, build)


def banner_photo(width, height=104):
    img = banner_image(width, height)
    return ImageTk.PhotoImage(img) if img is not None else None


def icon_image(size=64):
    """Icono de ventana: cuadrado negro con 'IN' amarillo."""
    def build():
        if not PIL_OK:
            return None
        s = 4
        S = size * s
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * .22), fill=BLACK,
                            outline=YEL, width=max(2, int(S * .045)))
        path = _font_file("seguibl.ttf", "ariblk.ttf", "arialbd.ttf")
        try:
            font = ImageFont.truetype(path, int(S * .50)) if path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        text = "IN"
        bb = d.textbbox((0, 0), text, font=font)
        d.text(((S - (bb[2] - bb[0])) // 2 - bb[0], (S - (bb[3] - bb[1])) // 2 - bb[1] - int(S * .03)),
               text, font=font, fill=YEL)
        d.rectangle([int(S * .20), int(S * .80), int(S * .80), int(S * .86)], fill=YEL)
        return img.resize((size, size), Image.LANCZOS)

    return _cached(("icon", size), build)


def apply_window_icon(root):
    try:
        img = icon_image(64)
        if img is not None:
            photo = ImageTk.PhotoImage(img)
            root.iconphoto(True, photo)
            root._indie_icon = photo
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# UTILIDADES DE LAYOUT
# ─────────────────────────────────────────────────────────────
def round_rect_item(cv, x1, y1, x2, y2, r, **kw):
    """Rectángulo redondeado dibujado en un Canvas (bordes suaves)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


def autowrap(widget, extra=24, minimum=140):
    host = widget.master
    def update(_=None):
        try:
            w = host.winfo_width()
            if w > 60:
                widget.configure(wraplength=max(minimum, w - extra))
        except tk.TclError:
            pass
    host.bind("<Configure>", update, add="+")
    try:
        widget.after(40, update)
    except Exception:
        pass


def hline(parent, color=BORDER_SOFT, pady=0):
    line = tk.Frame(parent, bg=color, height=1)
    line.pack(fill="x", pady=pady)
    return line


# ─────────────────────────────────────────────────────────────
# TARJETA REDONDEADA
# ─────────────────────────────────────────────────────────────
class Rounded(tk.Frame):
    """Panel redondeado con un `body` normal para meter contenido."""

    def __init__(self, master, fill=SURFACE, border=BORDER, radius=12, pad=14,
                 bg=None, **kw):
        base = bg or master.cget("bg")
        super().__init__(master, bg=base, bd=0, highlightthickness=0, **kw)
        self._base = base
        self.fill = fill
        self.border = border
        self.radius = radius
        self.pad = pad
        self.canvas = tk.Canvas(self, bg=base, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=fill)
        self._win = self.canvas.create_window(pad, pad, window=self.body, anchor="nw")
        self._img = None
        self._item = None
        self._job = None
        self._photo_cache = None
        self._size = (0, 0)
        self._body_size = (0, 0)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)

    def _on_canvas(self, event):
        # OJO: <Configure> también llega cuando el widget se MUEVE (scroll).
        # Si el tamaño no cambió, no hay que regenerar la imagen de fondo.
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        try:
            self.canvas.itemconfigure(self._win, width=max(1, event.width - self.pad * 2))
        except tk.TclError:
            return
        self._schedule_paint()

    def _on_body(self, event):
        size = (event.width, event.height)
        if size == self._body_size:
            return
        self._body_size = size
        target = int(event.height) + self.pad * 2
        try:
            if int(self.canvas.cget("height") or 0) != target:
                self.canvas.configure(height=target)
        except (tk.TclError, ValueError):
            pass

    def _schedule_paint(self):
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        try:
            self._job = self.after(20, self._paint)
        except tk.TclError:
            pass

    def _paint(self):
        self._job = None
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
        except tk.TclError:
            return
        if w < 4 or h < 4:
            return
        photo = rounded_photo(w, h, self.radius, self.fill, self.border,
                              bgcolor=self._base)
        if photo is None:
            self.delete("all")
            round_rect_item(self.canvas, 1, 1, w - 1, h - 1, self.radius,
                            fill=self.fill, outline=self.border)
            return
        self._photo_cache = photo
        if self._item is None:
            self._item = self.canvas.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.canvas.itemconfigure(self._item, image=photo)
        self.canvas.tag_lower(self._item)

    def set_border(self, color):
        if color != self.border:
            self.border = color
            self._schedule_paint()


# ─────────────────────────────────────────────────────────────
# BOTÓN
# ─────────────────────────────────────────────────────────────
class BrandButton(tk.Canvas):
    PALETTE = {
        "primary": dict(fill=YEL, hover=YEL_H, press="#E4D400", fg=BLACK, border=None),
        "dark": dict(fill=FIELD, hover=FIELD_H, press="#192027", fg=TEXT, border=BORDER_FIELD),
        "chip": dict(fill="#252C33", hover="#343D46", press="#1D242B", fg=YEL, border=BORDER),
        "ghost": dict(fill=SURFACE, hover=SURFACE_2, press=FIELD, fg=MUTED, border=BORDER_SOFT),
        "danger": dict(fill="#2A1417", hover="#3A1A1E", press="#201013", fg=RED, border="#4A2226"),
    }

    def __init__(self, master, text="", command=None, kind="primary", height=44,
                 radius=10, font=None, bg=None, icon="", padx=12, cursor="hand2", **kw):
        base = bg or master.cget("bg")
        super().__init__(master, height=height, bg=base, bd=0, highlightthickness=0,
                         cursor=cursor, **kw)
        self._base = base
        self._kind = kind if kind in self.PALETTE else "primary"
        self._text = text
        self._icon = icon
        self._enabled = True
        self._radius = radius
        self._font = font or (F_BLACK, 12)
        self._padx = padx
        self._command = command
        self._job = None
        self._anim = None
        self._photo = None
        self._hover = False
        self._press = False
        self._size = (0, 0)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        self._draw()

    # -- estado -------------------------------------------------
    def _fill(self):
        pal = self.PALETTE[self._kind]
        if not self._enabled:
            return "#1B222A", "#39434D", "#5B6672"
        if self._press:
            return pal["press"], pal["border"], pal["fg"]
        if self._hover:
            return pal["hover"], pal["border"], pal["fg"]
        return pal["fill"], pal["border"], pal["fg"]

    def _draw(self):
        try:
            w, h = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        if w < 4 or h < 4:
            return
        fill, border, fg = self._fill()
        photo = rounded_photo(w, h, self._radius, fill, border,
                              1 if border else 0, None, bgcolor=self._base)
        self._photo = photo
        self.delete("all")
        if photo is not None:
            self.create_image(0, 0, anchor="nw", image=photo)
        else:
            round_rect_item(self, 1, 1, w - 1, h - 1, self._radius,
                            fill=fill, outline=border or fill)
        label = (self._icon + "  " + self._text).strip() if self._icon else self._text
        self.create_text(w // 2, h // 2 - 1, text=label, fill=fg,
                         font=self._font, anchor="center")
        if not self._enabled:
            try:
                self.configure(cursor="arrow")
            except tk.TclError:
                pass
        else:
            try:
                self.configure(cursor="hand2")
            except tk.TclError:
                pass

    def _set_hover(self, on):
        if not self._enabled:
            return
        self._hover = on
        self._draw()

    def _on_press(self, _=None):
        if not self._enabled:
            return
        self._press = True
        self._draw()

    def _on_release(self, _=None):
        if not self._enabled:
            return
        was = self._press
        self._press = False
        self._draw()
        if was and self._command:
            try:
                self._command()
            except Exception:
                pass

    # -- API ----------------------------------------------------
    def set_text(self, text, icon=None):
        self._text = text
        if icon is not None:
            self._icon = icon
        self._draw()

    def set_kind(self, kind):
        if kind in self.PALETTE and kind != self._kind:
            self._kind = kind
            self._draw()

    def set_enabled(self, enabled):
        if self._enabled != bool(enabled):
            self._enabled = bool(enabled)
            self._draw()

    def is_enabled(self):
        return self._enabled


# ─────────────────────────────────────────────────────────────
# CHECKBOX
# ─────────────────────────────────────────────────────────────
_CHECK_CACHE = {}


def _check_img(size, checked, hover, disabled=False):
    key = ("chk", size, checked, hover, disabled)
    if key in _CHECK_CACHE:
        return _CHECK_CACHE[key]
    if not PIL_OK:
        return None
    s = 4
    S = size * s
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(S * 0.28)
    if disabled:
        fill, edge = "#161C23", "#333C46"
    elif checked:
        fill, edge = YEL, YEL
    else:
        fill, edge = ("#1B232B" if hover else "#161D24"), (YEL if hover else "#3B4652")
    d.rounded_rectangle([2, 2, S - 3, S - 3], radius=r, fill=fill, outline=edge,
                        width=int(S * 0.10))
    if checked:
        d.line([(S * .26, S * .52), (S * .44, S * .70), (S * .76, S * .33)],
               fill=BLACK if not disabled else "#6B7683", width=int(S * 0.13),
               joint="curve")
    img = img.resize((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _CHECK_CACHE[key] = photo
    return photo


def check_photo(size, checked, hover=False, disabled=False):
    """Foto de casilla para usar en filas propias."""
    return _check_img(size, checked, hover, disabled)


class BrandCheck(tk.Frame):
    """Fila seleccionable con caja amarilla y etiqueta."""

    def __init__(self, master, text, variable, command=None, bg=None,
                 font=None, size=21, pad=(0, 3), disabled=False):
        base = bg or master.cget("bg")
        super().__init__(master, bg=base)
        self.variable = variable
        self.command = command
        self._bg = base
        self._hover = False
        self._disabled = disabled
        self.box = tk.Canvas(self, width=size, height=size, bg=base, bd=0,
                             highlightthickness=0, cursor="hand2")
        self.box.pack(side="left", pady=pad)
        self.lbl = tk.Label(self, text=text, bg=base, fg=TEXT,
                            font=font or (F_SEMI, 11), anchor="w", justify="left",
                            cursor="hand2")
        self.lbl.pack(side="left", padx=(10, 0), fill="x", expand=True, pady=pad)
        self._size = size
        self._photo = None
        self._disabled = disabled
        for w in (self.box, self.lbl):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", lambda e: self._hovering(True))
            w.bind("<Leave>", lambda e: self._hovering(False))
        try:
            self.variable.trace_add("write", lambda *_: self._paint())
        except Exception:
            pass
        self._paint()

    def _hovering(self, on):
        if self._disabled:
            return
        self._hover = on
        self.lbl.configure(fg=YEL if on else TEXT)
        self._paint()

    def _toggle(self, _=None):
        if self._disabled:
            return
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def _paint(self):
        checked = bool(self.variable.get())
        photo = _check_img(self._size, checked, self._hover, self._disabled)
        self._photo = photo
        self.box.delete("all")
        if photo is not None:
            self.box.create_image(0, 0, anchor="nw", image=photo)
        else:
            self.box.create_rectangle(1, 1, self._size - 1, self._size - 1,
                                      outline=YEL if checked else "#3B4652",
                                      fill=YEL if checked else "", width=2)
        self.lbl.configure(fg=(DIM if self._disabled else
                               (YEL if self._hover else TEXT)))

    def set_enabled(self, enabled):
        self._disabled = not enabled
        for w in (self.box, self.lbl):
            try:
                w.configure(cursor="hand2" if enabled else "arrow")
            except tk.TclError:
                pass
        self._paint()


# ─────────────────────────────────────────────────────────────
# SELECTOR SEGMENTADO
# ─────────────────────────────────────────────────────────────
class Segmented(tk.Frame):
    def __init__(self, master, options, variable, command=None, height=38,
                 bg=None, font=None, gap=6):
        base = bg or master.cget("bg")
        super().__init__(master, bg=base)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for i, (value, label) in enumerate(options):
            btn = BrandButton(self, text=label, kind="dark", height=height,
                              radius=9, font=font or (F_BLACK, 10), bg=base,
                              command=lambda v=value: self._choose(v))
            btn.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else gap, 0))
            self.grid_columnconfigure(i, weight=1, uniform="seg")
            self.buttons[value] = btn
        try:
            variable.trace_add("write", lambda *_: self.refresh())
        except Exception:
            pass
        self.refresh()

    def _choose(self, value):
        if value == self.variable.get():
            return
        self.variable.set(value)
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def refresh(self):
        current = self.variable.get()
        for value, btn in self.buttons.items():
            btn.set_kind("primary" if value == current else "dark")

    def set_enabled(self, enabled):
        for btn in self.buttons.values():
            btn.set_enabled(enabled)


# ─────────────────────────────────────────────────────────────
# SELECT (menú oscuro propio)
# ─────────────────────────────────────────────────────────────
class BrandSelect(tk.Canvas):
    def __init__(self, master, values, variable, command=None, height=42,
                 bg=None, font=None):
        base = bg or master.cget("bg")
        super().__init__(master, height=height, bg=base, bd=0,
                         highlightthickness=0, cursor="hand2")
        self._base = base
        self._values = list(values)
        self.variable = variable
        self.command = command
        self._font = font or (F_BODY, 11)
        self._photo = None
        self._popup = None
        self._hover = False
        self._enabled = True
        self._size = (0, 0)
        
        # IDs de los eventos para poder limpiarlos luego
        self._root_click_id = None
        self._root_config_id = None
        self._root_wheel_id = None
        self._root_unmap_id = None
        
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<ButtonRelease-1>", self._open)
        
        try:
            variable.trace_add("write", lambda *_: self._draw())
        except Exception:
            pass

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        self._draw()

    def set_values(self, values):
        self._values = list(values)
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        try:
            self.configure(cursor="hand2" if self._enabled else "arrow")
        except tk.TclError:
            pass
        if not self._enabled:
            self._close()
        self._draw()

    def _hov(self, on):
        if not self._enabled:
            return
        self._hover = on
        self._draw()

    def _draw(self):
        try:
            w, h = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        if w < 4 or h < 4:
            return
        if not self._enabled:
            fill, border, fg, arrow = "#131A20", BORDER_SOFT, DIM, "#4A5560"
        else:
            fill, border = (FIELD_H if self._hover else FIELD), BORDER_FIELD
            fg, arrow = TEXT, YEL
        photo = rounded_photo(w, h, 9, fill, border, 1, None,
                              bgcolor=self._base)
        self._photo = photo
        self.delete("all")
        if photo is not None:
            self.create_image(0, 0, anchor="nw", image=photo)
        else:
            round_rect_item(self, 1, 1, w - 1, h - 1, 9, fill=fill, outline=border)
        text = self.variable.get() or "—"
        if len(text) > 46:
            text = text[:45] + "…"
        self.create_text(14, h // 2 - 1, text=text, anchor="w", fill=fg, font=self._font)
        self.create_text(w - 16, h // 2 - 2, text="▾", anchor="e", fill=arrow,
                         font=(F_BODY, 12, "bold"))

    def _close(self, event=None):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            
            # Desvincular todos los eventos que agregamos a la ventana raíz
            root = self.winfo_toplevel()
            for event_name, bind_id in [
                ("<Button-1>", self._root_click_id),
                ("<Configure>", self._root_config_id),
                ("<Unmap>", self._root_unmap_id)
            ]:
                if bind_id:
                    try:
                        root.unbind(event_name, bind_id)
                    except Exception:
                        pass
            # Ojo: NUNCA unbind_all("<MouseWheel>"), borraría el scroll global.
            try:
                _WHEEL_CLOSERS.remove(self)
            except ValueError:
                pass
            
            self._root_click_id = None
            self._root_config_id = None
            self._root_wheel_id = None
            self._root_unmap_id = None

    def _global_click(self, event):
        if self._popup:
            w = event.widget
            if w != self._popup and w.winfo_toplevel() != self._popup and w != self:
                self._close()

    def _open(self, event=None):
        if self._popup is not None or not self._values or not self._enabled:
            return

        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True) 
        self._popup.attributes("-topmost", True)
        self._popup.configure(bg=BORDER_FIELD) 
        
        frame = tk.Frame(self._popup, bg=SURFACE, bd=1, relief="solid")
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        for value in self._values:
            selected = value == self.variable.get()
            label = ("●  " if selected else "    ") + str(value)
            
            lbl = tk.Label(frame, text=label, bg=SURFACE, fg=TEXT, anchor="w",
                           padx=10, pady=6, font=(F_SEMI, 10), cursor="hand2")
            lbl.pack(fill="x")
            
            lbl.bind("<Enter>", lambda e, l=lbl: l.configure(bg=FIELD, fg=YEL))
            lbl.bind("<Leave>", lambda e, l=lbl, v=selected: l.configure(bg=SURFACE, fg=YEL if v else TEXT))
            lbl.bind("<Button-1>", lambda e, v=value: self._choose(v))

        self.update_idletasks()
        self._popup.update_idletasks()

        w = max(self.winfo_width(), self._popup.winfo_reqwidth())
        h = self._popup.winfo_reqheight()
        
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        
        if y + h > self.winfo_screenheight() - 8:
            y = max(8, self.winfo_rooty() - h)

        self._popup.geometry(f"{w}x{h}+{x}+{y}")
        
        # Si el menú pierde el foco (ej. clic en otra app), se cierra
        self._popup.bind("<FocusOut>", lambda e: self._close())
        
        # --- NUEVOS BINDS PARA EVITAR EL "BUGEo" ---
        root = self.winfo_toplevel()
        
        # 1. Cerrar si se hace clic en otro lado de la app
        self._root_click_id = root.bind("<Button-1>", self._global_click, add="+")
        
        # 2. Cerrar si la ventana principal se mueve o redimensiona
        self._root_config_id = root.bind("<Configure>", self._close, add="+")
        
        # 3. Cerrar si se hace scroll en cualquier parte de la app. Se registra
        # en el despachador global: así no se toca el binding de la rueda.
        if self not in _WHEEL_CLOSERS:
            _WHEEL_CLOSERS.append(self)
        self._root_wheel_id = None
        
        # 4. Cerrar si la ventana principal se minimiza
        self._root_unmap_id = root.bind("<Unmap>", self._close, add="+")

    def _choose(self, value):
        self._close()
        self.variable.set(value)
        if self.command:
            try:
                self.command()
            except Exception:
                pass

# ─────────────────────────────────────────────────────────────
# PROGRESO
# ─────────────────────────────────────────────────────────────
class Meter(tk.Canvas):
    def __init__(self, master, height=8, bg=None, fill=YEL, track="#222B33"):
        base = bg or master.cget("bg")
        super().__init__(master, height=height, bg=base, bd=0, highlightthickness=0)
        self._fill = fill
        self._track = track
        self._target = 0.0
        self._value = 0.0
        self._job = None
        self._bar = None
        self._size = (0, 0)
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        self._draw()

    def set(self, value, animate=True):
        try:
            value = max(0.0, min(1.0, float(value)))
        except Exception:
            value = 0.0
        self._target = value
        if not animate:
            self._value = value
            self._draw()
            return
        if self._job is None:
            self._step()

    def _step(self):
        diff = self._target - self._value
        if abs(diff) < 0.004:
            self._value = self._target
            self._job = None
            self._draw()
            return
        self._value += diff * 0.18
        self._draw()
        try:
            self._job = self.after(16, self._step)
        except tk.TclError:
            self._job = None

    def _draw(self):
        try:
            w, h = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        self.delete("all")
        if w < 4:
            return
        round_rect_item(self, 0, 0, w, h, h / 2, fill=self._track, outline="")
        fill_w = max(0, int(w * self._value))
        if fill_w > 2:
            round_rect_item(self, 0, 0, fill_w, h, h / 2, fill=self._fill, outline="")


class Spinner(tk.Canvas):
    def __init__(self, master, size=16, bg=None, color=YEL):
        base = bg or master.cget("bg")
        super().__init__(master, width=size, height=size, bg=base, bd=0,
                         highlightthickness=0)
        self._size = size
        self._color = color
        self._angle = 0
        self._job = None
        self._running = False
        self._arc = None

    def _draw(self):
        self.delete("all")
        m = 2
        self._arc = self.create_arc(m, m, self._size - m, self._size - m,
                                    start=self._angle, extent=250, style="arc",
                                    outline=self._color, width=2)

    def start(self):
        if self._running:
            return
        self._running = True
        self._tick()

    def stop(self):
        self._running = False
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.delete("all")

    def _tick(self):
        if not self._running:
            return
        self._angle = (self._angle + 28) % 360
        self.delete("all")
        m = 2
        self.create_arc(m, m, self._size - m, self._size - m, start=self._angle,
                        extent=250, style="arc", outline=self._color, width=2)
        try:
            self._job = self.after(55, self._tick)
        except tk.TclError:
            self._running = False


class PulseDot(tk.Canvas):
    def __init__(self, master, size=12, bg=None, color=GREEN):
        base = bg or master.cget("bg")
        super().__init__(master, width=size, height=size, bg=base, bd=0,
                         highlightthickness=0)
        self._size = size
        self._color = color
        self._t = 0.0
        self._dir = 1
        self._job = None
        self._tick()

    def _tick(self):
        self.delete("all")
        c = self._size / 2
        r = 2.2 + self._t * 2.1
        self.create_oval(c - r, c - r, c + r, c + r,
                         fill=mix(self._color, "#1A2A20", self._t * 0.55), outline="")
        self._t += 0.06 * self._dir
        if self._t >= 1:
            self._t, self._dir = 1.0, -1
        elif self._t <= 0:
            self._t, self._dir = 0.0, 1
        try:
            self._job = self.after(45, self._tick)
        except tk.TclError:
            self._job = None


# ─────────────────────────────────────────────────────────────
# SCROLL
# ─────────────────────────────────────────────────────────────
_WHEEL_ROOTS = set()
_WHEEL_CLOSERS = []


def _ensure_wheel(root):
    """Instala un único despachador de rueda por intérprete Tk.

    Antes cada widget agregaba y quitaba su propio `bind_all("<MouseWheel>")`;
    al cerrar un desplegable se hacía `unbind_all` y se borraban TODOS los
    enlaces globales, incluido el del área de scroll: la rueda dejaba de
    funcionar hasta reiniciar. Con un solo despachador eso no puede pasar.
    """
    key = str(root)
    if key in _WHEEL_ROOTS:
        return
    try:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_all(seq, _wheel_dispatch, add="+")
        _WHEEL_ROOTS.add(key)
    except tk.TclError:
        pass


def _wheel_dispatch(event):
    # 1) Cerrar menús desplegables abiertos.
    for widget in list(_WHEEL_CLOSERS):
        try:
            widget._close()
        except Exception:
            pass
    # 2) Desplazar el área que está debajo del puntero (la última creada gana).
    for area in reversed(list(ScrollArea._AREAS)):
        try:
            if area._wheel(event) == "break":
                return "break"
        except Exception:
            continue
    return None


class SlimScrollbar(tk.Canvas):
    """Barra vertical fina, estilo IndieDL.

    Sólo aparece cuando hay contenido para desplazar. El riel se dibuja tenue y
    la pastilla se engorda al pasar el puntero: da feedback sin mover nada de
    lugar (el ancho de la barra queda reservado siempre).
    """

    def __init__(self, master, command, width=10, bg=BG):
        super().__init__(master, width=width, height=1, bg=bg, bd=0,
                         highlightthickness=0, takefocus=0)
        self.command = command
        self._first, self._last = 0.0, 1.0
        self._drag = None
        self._hover = False
        self._size = (0, 0)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, on):
        if on == self._hover:
            return
        self._hover = on
        self._draw()

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        self._draw()

    def set(self, first, last):
        try:
            self._first, self._last = float(first), float(last)
        except Exception:
            self._first, self._last = 0.0, 1.0
        self._draw()

    def _geometry(self):
        h = self.winfo_height()
        top = self._first * h
        bottom = self._last * h
        if bottom - top < 36:
            bottom = min(h, top + 36)
            top = max(0, bottom - 36)
        return h, top, bottom

    def _draw(self):
        self.delete("all")
        try:
            w, h = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        if h < 10 or w < 2:
            return
        if (self._last - self._first) >= 0.999:
            return  # todo el contenido visible: no ocupamos lugar visual
        cx = w / 2
        round_rect_item(self, cx - 1, 2, cx + 1, h - 2, 1,
                        fill="#1A222A", outline="")
        _, top, bottom = self._geometry()
        thumb_w = 6 if self._hover else 4
        round_rect_item(self, cx - thumb_w / 2, top, cx + thumb_w / 2, bottom,
                        thumb_w / 2,
                        fill="#5C6A77" if self._hover else "#46525E", outline="")

    # ---- arrastre ----
    def _press(self, event):
        h, top, bottom = self._geometry()
        if top <= event.y <= bottom:
            self._drag = event.y - top
        else:
            self._drag = (bottom - top) / 2
            self._jump(event.y)
            self._motion(event)

    def _motion(self, event):
        if self._drag is None:
            return
        try:
            self.command("moveto", max(0.0, min(
                1.0, (event.y - self._drag) / max(1, self.winfo_height()))))
        except Exception:
            pass

    def _jump(self, y):
        try:
            self.command("moveto", max(0.0, min(1.0, y / max(1, self.winfo_height()))))
        except Exception:
            pass


class ScrollArea(tk.Frame):
    """Área de scroll propia, con rueda suave y siempre activa.

    Tk mueve un `Canvas` de golpe: un diente de rueda salta 120 px y se siente
    tosco. Acá el desplazamiento se anima con la misma curva corta que usa
    IndieDL (cubic ease-out, 120-190 ms) y el manejador de rueda busca el área
    que está debajo del puntero, así funciona también sobre tarjetas, canvas y
    etiquetas anidadas. Los `Text`/`Listbox` conservan su scroll nativo.
    """

    _AREAS = []

    def __init__(self, master, bg=BG, pad=22):
        super().__init__(master, bg=bg, bd=0, highlightthickness=0)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0,
                                takefocus=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(pad, 18, window=self.inner,
                                              anchor="nw")
        self.bar = SlimScrollbar(self, command=self._scrollbar_command, bg=bg)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        # La barra ocupa siempre el mismo ancho: si aparece/desaparece, el
        # contenido cambia de ancho y se generan todos los fondos (parpadeo).
        self.bar.pack(side="right", fill="y", padx=(0, 4))
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.bind("<Destroy>", self._on_destroy, add="+")

        self._content_h = 0
        self._visible_frac = 1.0
        self._anim_job = None
        self._anim_start = 0.0
        self._anim_target = 0.0
        self._anim_t0 = 0.0
        self._anim_dur = 0.18
        self._animating = False

        ScrollArea._AREAS.append(self)
        _ensure_wheel(self.winfo_toplevel())

    # ---- geometría ----
    def _on_inner(self, event=None):
        if event is not None:
            size = (event.width, event.height)
        else:
            size = (self.inner.winfo_width(), self.inner.winfo_height())
        if size == getattr(self, "_inner_size", None):
            return
        self._inner_size = size
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            region = self.canvas.bbox("all")
            self._content_h = max(1, region[3] - region[1]) if region else 1
        except tk.TclError:
            pass

    def _on_canvas(self, event):
        size = (event.width, event.height)
        if size == getattr(self, "_canvas_size", None):
            return
        self._canvas_size = size
        try:
            self.canvas.itemconfigure(self._win, width=max(1, event.width - 44))
        except tk.TclError:
            pass
        self._on_inner()

    def _on_scroll(self, first, last):
        try:
            first, last = float(first), float(last)
        except Exception:
            first, last = 0.0, 1.0
        self.bar.set(first, last)
        self._visible_frac = max(0.0, last - first)
        if self._animating or self._anim_job is not None:
            # El movimiento lo produce la animación: no reescribir el destino
            # con la posición intermedia (realimentación que frena el scroll).
            return
        self._anim_start = self._anim_target = first

    def _scrollbar_command(self, *args):
        self._cancel_anim()
        try:
            self.canvas.yview(*args)
        except tk.TclError:
            return
        pos = float(self.canvas.yview()[0])
        self._anim_start = self._anim_target = pos

    # ---- rueda ----
    def _wheel(self, event):
        try:
            x, y = self.winfo_pointerxy()
            if not self.winfo_ismapped():
                return None
            if not (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                    and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()):
                return None
            widget = self.winfo_containing(x, y)
            if widget is not None and widget.winfo_class() in (
                    "Text", "Listbox", "TCombobox", "Spinbox", "TSpinbox"):
                return None  # ese widget conserva su scroll nativo
        except Exception:
            return None
        if getattr(event, "num", None) in (4, 5):
            px = -60.0 if event.num == 4 else 60.0
        else:
            delta = float(getattr(event, "delta", 0) or 0)
            if delta == 0:
                return None
            px = -delta * 0.50
        self.scroll_pixels(px)
        return "break"

    # ---- animación ----
    def _cancel_anim(self):
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        self._animating = False

    def scroll_pixels(self, px):
        if not self.winfo_ismapped():
            return
        height = self.canvas.winfo_height()
        if self._content_h <= height + 2:
            return
        now = time.perf_counter()
        current = float(self.canvas.yview()[0])
        if self._anim_job is None or now > self._anim_t0 + self._anim_dur + 0.05:
            self._anim_target = current
        frac = float(px) / max(1.0, float(self._content_h))
        self._anim_target = max(0.0, min(1.0, self._anim_target + frac))
        self._anim_start = current
        self._anim_t0 = now
        self._anim_dur = 0.12 if abs(px) < 40 else 0.19
        if self._anim_job is None:
            self._anim_job = self.after(8, self._anim_tick)

    def to_top(self):
        self._cancel_anim()
        try:
            self.canvas.yview_moveto(0.0)
            self._anim_start = self._anim_target = 0.0
        except tk.TclError:
            pass

    def scroll_to(self, px):
        """Lleva el contenido a una posición absoluta (px) con la misma curva."""
        if not self.winfo_ismapped():
            return
        frac = max(0.0, min(1.0, float(px) / max(1.0, float(self._content_h))))
        self._cancel_anim()
        self._anim_start = float(self.canvas.yview()[0])
        self._anim_target = frac
        self._anim_t0 = time.perf_counter()
        self._anim_dur = 0.22
        self._anim_job = self.after(8, self._anim_tick)

    def to_bottom(self):
        if not self.winfo_ismapped():
            return
        self._cancel_anim()
        self._anim_start = float(self.canvas.yview()[0])
        self._anim_target = 1.0
        self._anim_t0 = time.perf_counter()
        self._anim_dur = 0.22
        self._anim_job = self.after(8, self._anim_tick)

    def at_bottom(self, tolerance=0.02):
        try:
            return float(self.canvas.yview()[1]) >= 1.0 - tolerance
        except tk.TclError:
            return True

    def _anim_tick(self):
        self._anim_job = None
        try:
            elapsed = time.perf_counter() - self._anim_t0
            p = 1.0 if self._anim_dur <= 0 else min(1.0, elapsed / self._anim_dur)
            eased = 1.0 - (1.0 - p) ** 3  # cubic ease-out
            pos = self._anim_start + (self._anim_target - self._anim_start) * eased
            self._animating = True
            try:
                self.canvas.yview_moveto(max(0.0, min(1.0, pos)))
            finally:
                self._animating = False
            if p < 1.0:
                self._anim_job = self.after(8, self._anim_tick)
            else:
                # Si el lienzo recortó el destino, se sincroniza para que el
                # próximo gesto arranque desde donde realmente quedó.
                real = float(self.canvas.yview()[0])
                self._anim_start = self._anim_target = real
        except tk.TclError:
            self._animating = False
            self._anim_job = None

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self:
            return
        self._cancel_anim()
        try:
            ScrollArea._AREAS.remove(self)
        except ValueError:
            pass


# ═════════════════════════════════════════════════════════════
#  MUSOSOUP · INTERFAZ
# ═════════════════════════════════════════════════════════════
iu = sys.modules[__name__]   # el kit visual vive en este mismo archivo

import os
import queue
import subprocess
import sys
import threading
import traceback


ESTADOS = {
    "idle":    dict(color=iu.MUTED, title="EN ESPERA", glyph="·"),
    "working": dict(color=iu.YEL, title="TRABAJANDO", glyph="…"),
    "success": dict(color=iu.GREEN, title="LISTO", glyph="✓"),
    "error":   dict(color=iu.RED, title="ERROR", glyph="!"),
    "warn":    dict(color=iu.AMBER, title="AVISO", glyph="!"),
}

ORDENES = [("zip", "ORDEN DE LOS ZIP"), ("artista", "A – Z POR ARTISTA")]


def _corto(texto, limite=46):
    texto = str(texto or "")
    if len(texto) <= limite:
        return texto
    return texto[:limite - 1].rstrip() + "…"


def _abrir(ruta):
    """Abre un archivo o carpeta con el programa del sistema."""
    try:
        if os.name == "nt":
            os.startfile(ruta)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# WIDGETS PROPIOS
# ─────────────────────────────────────────────────────────────
class StateIcon(tk.Canvas):
    """Círculo de estado que gira mientras se trabaja."""

    def __init__(self, master, bg, size=26):
        super().__init__(master, width=size, height=size, bg=bg, bd=0,
                         highlightthickness=0)
        self._size = size
        self._bg = bg
        self._kind = "idle"
        self._angle = 0
        self._job = None
        self._spin = False
        self.draw("idle")

    def draw(self, kind):
        self._kind = kind
        self._spin = kind == "working"
        if not self._spin and self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._render()
        if self._spin and self._job is None:
            self.tick()

    def _render(self):
        self.delete("all")
        size = self._size
        m = 2
        conf = ESTADOS.get(self._kind, ESTADOS["idle"])
        color = conf["color"]
        if self._kind == "working":
            self.create_arc(m, m, size - m, size - m, start=self._angle,
                            extent=250, style="arc", outline=color, width=2)
        else:
            self.create_oval(m + 1, m + 1, size - m - 1, size - m - 1,
                             outline=iu.mix(color, self._bg, 0.55), width=1)
            glyph = conf["glyph"]
            font = (iu.F_BLACK, 12 if glyph != "·" else 14)
            self.create_text(size / 2, size / 2 - 1, text=glyph, fill=color,
                             font=font)

    def tick(self):
        if not self._spin:
            return
        self._angle = (self._angle + 28) % 360
        self._render()
        try:
            self._job = self.after(55, self.tick)
        except tk.TclError:
            self._job = None


class ItemRow(tk.Frame):
    """Fila seleccionable: casilla + badge + título/detalle + estado a la derecha."""

    def __init__(self, master, badge, titulo, detalle, derecha, color_derecha,
                 var, on_change):
        super().__init__(master, bg=iu.SURFACE_2, cursor="hand2")
        self.var = var
        self.on_change = on_change
        self._hover = False
        self._photo = None
        self._fit_avail = -1
        self.grid_columnconfigure(2, weight=1)

        self.box = tk.Canvas(self, width=20, height=20, bg=iu.SURFACE_2, bd=0,
                             highlightthickness=0, cursor="hand2")
        self.box.grid(row=0, column=0, rowspan=2, padx=(12, 0), pady=11)

        self.badge = tk.Label(self, text=badge, bg=iu.FIELD, fg=iu.YEL,
                              font=(iu.F_BLACK, 9), padx=8, pady=3)
        self.badge.grid(row=0, column=1, rowspan=2, padx=(10, 12), pady=9)

        self._full_name = str(titulo)
        self._name_font = tkfont.Font(font=(iu.F_SEMI, 10))
        self.name = tk.Label(self, text=self._full_name, bg=iu.SURFACE_2,
                             fg=iu.TEXT, font=(iu.F_SEMI, 10), anchor="w",
                             justify="left")
        self.name.grid(row=0, column=2, sticky="ew", pady=(8, 1))
        self.name.bind("<Configure>", self._fit_name, add="+")

        self.meta = tk.Label(self, text=detalle, bg=iu.SURFACE_2, fg=iu.DIM,
                             font=(iu.F_BODY, 8), anchor="w", justify="left")
        self.meta.grid(row=1, column=2, sticky="ew", pady=(0, 8))

        self.right = tk.Label(self, text=derecha, bg=iu.SURFACE_2,
                              fg=color_derecha, font=(iu.F_BLACK, 8), anchor="e")
        self.right.grid(row=0, column=3, rowspan=2, padx=(8, 14))

        for w in (self, self.box, self.badge, self.name, self.meta, self.right):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", lambda e: self._set_hover(True))
            w.bind("<Leave>", lambda e: self._set_hover(False))
        try:
            self.var.trace_add("write", lambda *_: self._paint())
        except Exception:
            pass
        self._paint()

    def _fit_name(self, event=None):
        try:
            avail = int(event.width if event is not None else self.name.winfo_width()) - 2
        except Exception:
            return
        if avail < 40 or avail == self._fit_avail:
            return
        self._fit_avail = avail
        try:
            self.meta.configure(wraplength=avail)
        except tk.TclError:
            pass
        texto = self._full_name
        try:
            if self._name_font.measure(texto) <= avail:
                self.name.configure(text=texto)
                return
            while texto and self._name_font.measure(texto + "…") > avail:
                texto = texto[:-1]
        except tk.TclError:
            return
        self.name.configure(text=(texto.rstrip() + "…") if texto else "…")

    def _set_hover(self, on):
        self._hover = on
        bg = "#1F2831" if on else iu.SURFACE_2
        for w in (self, self.box, self.name, self.meta, self.right):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass
        self._paint()

    def _toggle(self, _=None):
        self.var.set(not bool(self.var.get()))
        if self.on_change:
            self.on_change()

    def _paint(self):
        checked = bool(self.var.get())
        self._photo = iu.check_photo(20, checked, self._hover, False)
        self.box.delete("all")
        if self._photo is not None:
            self.box.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.box.create_rectangle(1, 1, 19, 19, outline=iu.YEL, width=2,
                                      fill=iu.YEL if checked else "")
        self.name.configure(fg=iu.TEXT if checked else iu.DIM)


# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────
class MusoSoupApp:
    def __init__(self, root, backend):
        self.root = root
        self.backend = backend
        self.cfg = dict(backend.config() or {})
        self.analisis = None
        self.sel_launch = {}
        self.sel_unm = {}
        self.rows_launch = []
        self.rows_unm = []
        self.resumen = None
        self._busy = False
        self._modo = ""
        self._closing = False
        self._revealed = False
        self._alpha_ok = True
        self._cancelando = False
        self._banner_w = 0
        self._job_reveal = None
        self._job_header = None
        self._ultimo_doc = ""
        self._ultimo_log = None
        self._log_counter = 0
        self._log_open = False
        self._cola_obj = queue.Queue()
        self._lab_orden = {c: e for c, e in ORDENES}
        self._cod_orden = {e: c for c, e in ORDENES}

        self.v_carpeta = tk.StringVar(value=self.cfg.get("carpeta", "") or "")
        self.v_destino = tk.StringVar(value=self.cfg.get("destino", "") or "")
        self.v_indice = tk.BooleanVar(value=bool(self.cfg.get("indice", True)))
        self.v_texto = tk.BooleanVar(value=bool(self.cfg.get("texto_completo", True)))
        self.v_sinasoc = tk.BooleanVar(value=bool(self.cfg.get("sin_asociar", True)))
        self.v_abrir = tk.BooleanVar(value=bool(self.cfg.get("abrir", True)))
        self.v_orden = tk.StringVar(
            value=self._lab_orden.get(self.cfg.get("orden", "zip"), ORDENES[0][1]))

        self._config_root()
        self._build_header()
        self._build_footer()
        self._build_scroll()
        self._build_carpeta()
        self._build_cifras()
        self._build_opciones()
        self._build_salida()
        self._build_lista()
        self._build_sin_asociar()
        self._build_estado()
        self._build_log()

        self._set_estado("idle", "Listo. Elegí la carpeta del día para empezar.")
        self.root.after(0, self._arranque)

    # ---- arranque visual ----
    def _arranque(self):
        self._refrescar_carpeta()
        self._actualizar_salida()
        self._log("Aplicación iniciada · estética IndieDL", "info")
        self._poll()
        self.root.after(20, self._reveal)
        carpeta = self.v_carpeta.get()
        if carpeta and self.backend.existe(carpeta):
            self._escanear(carpeta)

    def _reveal(self):
        if self._closing:
            return
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self._draw_banner(max(320, self.root.winfo_width()))
        try:
            self.root.update_idletasks()
            self.root.deiconify()
            self._apply_dark_titlebar()
            self.root.lift()
            self.root.update()
        except Exception:
            pass
        if self._alpha_ok:
            self._fade_in(0)
        else:
            self._finish_reveal()

    def _fade_in(self, step):
        steps = 3
        p = min(1.0, float(step) / steps)
        alpha = 1.0 - (1.0 - p) ** 2.2
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            self._alpha_ok = False
        if step < steps:
            self.root.after(18, lambda: self._fade_in(step + 1))
        else:
            self._finish_reveal()

    def _finish_reveal(self):
        if self._revealed:
            return
        self._revealed = True
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.focus_force()
        except tk.TclError:
            pass

    def _apply_dark_titlebar(self):
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) \
                or self.root.winfo_id()
            value = ctypes.c_int(1)
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def _config_root(self):
        r = self.root
        r.title("Indie Now · MusoSoup")
        r.configure(bg=iu.BG)
        r.minsize(900, 620)
        ancho, alto = 1180, 820
        try:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            ancho = min(ancho, sw - 80)
            alto = min(alto, sh - 90)
            x = max(0, (sw - ancho) // 2)
            y = max(0, (sh - alto) // 2 - 10)
            r.geometry(f"{ancho}x{alto}+{x}+{y}")
        except tk.TclError:
            r.geometry("1180x820")
        iu.apply_window_icon(r)

    # ---- cabecera / pie ----
    def _build_header(self):
        self.header = tk.Frame(self.root, bg=iu.BG)
        self.header.pack(side="top", fill="x")
        self.banner = tk.Label(self.header, bg=iu.BG, bd=0, highlightthickness=0)
        self.banner.pack(fill="x")
        band = tk.Frame(self.header, bg=iu.BLACK, height=40)
        band.pack(fill="x")
        band.pack_propagate(False)
        tk.Label(band, text="MUSOSOUP   ·   LANZAMIENTOS DEL DÍA   ·   CONSOLIDADOR",
                 bg=iu.BLACK, fg=iu.YEL, font=(iu.F_BLACK, 11)).pack(expand=True)
        tk.Frame(self.header, bg=iu.YEL, height=4).pack(fill="x")
        self.root.bind("<Configure>", self._on_root_resize, add="+")

    def _on_root_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        width = -(-max(320, self.root.winfo_width()) // 32) * 32
        if width == self._banner_w:
            return
        if self._job_header:
            try:
                self.root.after_cancel(self._job_header)
            except Exception:
                pass
        self._job_header = self.root.after(90, lambda: self._draw_banner(width))

    def _draw_banner(self, width):
        self._job_header = None
        width = max(320, int(width))
        width = -(-width // 32) * 32
        if width == self._banner_w and getattr(self, "_banner_photo", None):
            self.banner.configure(image=self._banner_photo)
            return
        try:
            photo = iu.banner_photo(width, 104)
        except Exception:
            photo = None
        if photo is None:
            return
        self._banner_w = width
        self._banner_photo = photo
        self.banner.configure(image=photo)
        self.banner._photo = photo

    def _build_footer(self):
        self.footer = tk.Frame(self.root, bg="#0B1015")
        self.footer.pack(side="bottom", fill="x")
        tk.Frame(self.footer, bg=iu.BORDER, height=1).pack(fill="x")
        self.meter = iu.Meter(self.footer, height=6, bg="#0B1015")
        self.meter.pack(fill="x")
        row = tk.Frame(self.footer, bg="#0B1015", padx=22, pady=12)
        row.pack(fill="x")
        self.footer_txt = tk.Label(row, text="En espera", bg="#0B1015", fg=iu.DIM,
                                   font=(iu.F_BODY, 9), anchor="w", justify="left")
        self.footer_txt.pack(side="left", fill="x", expand=True)
        row.bind("<Configure>", lambda e: self.footer_txt.configure(
            wraplength=max(160, e.width - 360)), add="+")
        self.cta = iu.BrandButton(row, text=self._texto_boton(), kind="primary",
                                  height=54, font=(iu.F_BLACK, 15), radius=11,
                                  icon="▶", command=self._go)
        self.cta.pack(side="right", padx=(16, 0))
        self.cta.configure(width=320)
        self.btn_cancel = iu.BrandButton(row, text="CANCELAR", kind="danger",
                                         height=54, font=(iu.F_BLACK, 12),
                                         radius=11, icon="■", command=self._cancelar)
        self.btn_cancel.configure(width=170)

    def _build_scroll(self):
        self.scroll = iu.ScrollArea(self.root, bg=iu.BG, pad=22)
        self.scroll.pack(fill="both", expand=True)
        self.content = self.scroll.inner
        self.content.grid_columnconfigure(0, weight=1, uniform="layout_columns")
        self.content.grid_columnconfigure(1, weight=1, uniform="layout_columns")
        self.host_carpeta = tk.Frame(self.content, bg=iu.BG)
        self.host_carpeta.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.host_cifras = tk.Frame(self.content, bg=iu.BG)
        self.host_cifras.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.col_left = tk.Frame(self.content, bg=iu.BG)
        self.col_left.grid(row=2, column=0, sticky="new", padx=(0, 7))
        self.col_right = tk.Frame(self.content, bg=iu.BG)
        self.col_right.grid(row=2, column=1, sticky="new", padx=(7, 0))
        self.host_lista = tk.Frame(self.content, bg=iu.BG)
        self.host_lista.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.host_unm = tk.Frame(self.content, bg=iu.BG)
        self.host_unm.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.host_state = tk.Frame(self.content, bg=iu.BG)
        self.host_state.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.host_log = tk.Frame(self.content, bg=iu.BG)
        self.host_log.grid(row=6, column=0, columnspan=2, sticky="ew")

    def _card(self, parent, pady=(0, 12)):
        card = iu.Rounded(parent)
        card.pack(fill="x", pady=pady)
        return card

    def _section(self, parent, numero, titulo, hint="", pady=(0, 12)):
        card = iu.Rounded(parent)
        card.pack(fill="x", pady=pady)
        body = card.body
        head = tk.Frame(body, bg=iu.SURFACE)
        head.pack(fill="x", pady=(0, 10))
        badge = tk.Canvas(head, width=26, height=26, bg=iu.SURFACE, bd=0,
                          highlightthickness=0)
        if numero is None:
            badge.create_rectangle(11, 4, 15, 22, fill=iu.YEL, outline="")
        else:
            badge.create_oval(0, 0, 25, 25, fill=iu.YEL, outline="")
            badge.create_text(13, 12, text=str(numero), fill=iu.BLACK,
                              font=(iu.F_BLACK, 11))
        badge.pack(side="left")
        tk.Label(head, text=titulo, bg=iu.SURFACE, fg=iu.TEXT,
                 font=(iu.F_BLACK, 12)).pack(side="left", padx=(10, 0))
        hint_lbl = tk.Label(head, text=hint, bg=iu.SURFACE, fg=iu.DIM,
                            font=(iu.F_BLACK, 8))
        hint_lbl.pack(side="right", pady=(4, 0))
        return card, body, hint_lbl

    # ---- tarjetas ----
    def _build_carpeta(self):
        card = self._card(self.host_carpeta, pady=(0, 12))
        body = card.body
        top = tk.Frame(body, bg=iu.SURFACE)
        top.pack(fill="x")
        left = tk.Frame(top, bg=iu.SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="CARPETA DE LA TANDA DE HOY", bg=iu.SURFACE, fg=iu.DIM,
                 font=(iu.F_BLACK, 8)).pack(anchor="w")
        self.lbl_carpeta = tk.Label(left, text="Ninguna carpeta elegida", bg=iu.SURFACE,
                                    fg=iu.DIM, font=(iu.F_BLACK, 19), anchor="w",
                                    justify="left")
        self.lbl_carpeta.pack(anchor="w", pady=(2, 0))
        self.lbl_carpeta_sub = tk.Label(
            left, text="Elegí la carpeta COMPLETA del día: con los ZIP de MusoSoup "
                       "y los documentos sueltos.",
            bg=iu.SURFACE, fg=iu.MUTED, font=(iu.F_BODY, 9), anchor="w",
            justify="left")
        self.lbl_carpeta_sub.pack(anchor="w", fill="x")
        iu.autowrap(self.lbl_carpeta_sub, extra=420)
        right = tk.Frame(top, bg=iu.SURFACE)
        right.pack(side="right", anchor="ne")
        self.dot = iu.PulseDot(right, bg=iu.SURFACE)
        self.dot.pack(side="left", padx=(0, 6))
        self.lbl_live = tk.Label(right, text="SIN CARPETA", bg=iu.SURFACE, fg=iu.DIM,
                                 font=(iu.F_BLACK, 8))
        self.lbl_live.pack(side="left")

        btns = tk.Frame(body, bg=iu.SURFACE)
        btns.pack(fill="x", pady=(14, 0))
        self.btn_elegir = iu.BrandButton(btns, text="ELEGIR CARPETA…", kind="dark",
                                         height=40, font=(iu.F_BLACK, 10), width=210,
                                         radius=9, icon="▤", command=self._elegir_carpeta)
        self.btn_elegir.pack(side="left")
        self.btn_analizar = iu.BrandButton(btns, text="ANALIZAR", kind="chip", height=40,
                                           font=(iu.F_BLACK, 9), width=132, radius=9,
                                           icon="↻", command=self._analizar)
        self.btn_analizar.pack(side="left", padx=(8, 0))
        self.btn_abrir_carpeta = iu.BrandButton(
            btns, text="ABRIR", kind="chip", height=40, font=(iu.F_BLACK, 9),
            width=90, radius=9, command=self._abrir_carpeta)
        self.btn_abrir_carpeta.pack(side="left", padx=(8, 0))

    def _build_cifras(self):
        card = self._card(self.host_cifras, pady=(0, 12))
        body = card.body
        fila = tk.Frame(body, bg=iu.SURFACE)
        fila.pack(fill="x")
        self.cifras = {}
        datos = [("zip", "ZIP", iu.TEXT), ("lanz", "LANZAMIENTOS", iu.YEL),
                 ("cand", "CANDIDATOS", iu.AMBER), ("ok", "VERIFICADOS", iu.GREEN),
                 ("rev", "A REVISAR", iu.AMBER), ("sin", "PENDIENTES", iu.MUTED)]
        for i, (clave, titulo, color) in enumerate(datos):
            fila.grid_columnconfigure(i, weight=1, uniform="cifras")
            cel = tk.Frame(fila, bg=iu.SURFACE)
            cel.grid(row=0, column=i, sticky="ew")
            num = tk.Label(cel, text="—", bg=iu.SURFACE, fg=iu.DIM,
                           font=(iu.F_BLACK, 24))
            num.pack()
            tk.Label(cel, text=titulo, bg=iu.SURFACE, fg=iu.DIM,
                     font=(iu.F_BLACK, 8)).pack()
            self.cifras[clave] = (num, color)

    def _build_opciones(self):
        card, body, hint = self._section(self.col_left, 1, "QUÉ INCLUIR EN EL WORD", "OPCIONES")
        self.chk_indice = iu.BrandCheck(body, "Índice resumen al inicio del documento",
                                        self.v_indice, command=self._guardar)
        self.chk_indice.pack(fill="x", pady=(0, 6))
        self.chk_texto = iu.BrandCheck(
            body, "Texto completo de cada fuente (apagado: solo fichas)",
            self.v_texto, command=self._guardar)
        self.chk_texto.pack(fill="x", pady=6)
        self.chk_sin = iu.BrandCheck(body, "Documentos pendientes de clasificar al final",
                                     self.v_sinasoc, command=self._sinasoc_changed)
        self.chk_sin.pack(fill="x", pady=6)
        self.chk_abrir = iu.BrandCheck(body, "Abrir el documento al terminar",
                                       self.v_abrir, command=self._guardar)
        self.chk_abrir.pack(fill="x", pady=(6, 0))
        iu.hline(body, pady=(12, 10))
        tk.Label(body, text="Orden de los lanzamientos", bg=iu.SURFACE, fg=iu.MUTED,
                 font=(iu.F_SEMI, 9)).pack(anchor="w", pady=(0, 6))
        self.seg_orden = iu.Segmented(body, [(e, e) for _, e in ORDENES], self.v_orden,
                                      command=self._orden_changed, height=36,
                                      font=(iu.F_BLACK, 8))
        self.seg_orden.pack(fill="x")

    def _build_salida(self):
        card, body, hint = self._section(self.col_right, 2, "DÓNDE GUARDAR", "DOCX")
        self.lbl_out = tk.Label(body, text="", bg=iu.SURFACE, fg=iu.TEXT,
                                font=(iu.F_SEMI, 11), anchor="w", justify="left")
        self.lbl_out.pack(fill="x")
        self.lbl_out_dir = tk.Label(body, text="", bg=iu.SURFACE, fg=iu.DIM,
                                    font=(iu.F_BODY, 8), anchor="w", justify="left")
        self.lbl_out_dir.pack(fill="x", pady=(2, 0))
        iu.autowrap(self.lbl_out_dir, extra=10)
        self.lbl_out_note = tk.Label(
            body, text="Si el Word de hoy está abierto, se guarda como _2, _3… "
                       "sin pisarlo.", bg=iu.SURFACE, fg=iu.DIM, font=(iu.F_BODY, 8),
            anchor="w", justify="left")
        self.lbl_out_note.pack(fill="x", pady=(8, 0))
        iu.autowrap(self.lbl_out_note, extra=10)
        row = tk.Frame(body, bg=iu.SURFACE)
        row.pack(fill="x", pady=(14, 0))
        self.btn_destino = iu.BrandButton(row, text="CAMBIAR DESTINO…", kind="dark",
                                          height=36, font=(iu.F_BLACK, 9), width=180,
                                          radius=8, icon="▣", command=self._elegir_destino)
        self.btn_destino.pack(side="left")
        self.btn_auto = iu.BrandButton(row, text="AUTOMÁTICO", kind="chip", height=36,
                                       font=(iu.F_BLACK, 8), width=106, radius=8,
                                       command=self._destino_auto)
        self.btn_auto.pack(side="left", padx=(8, 0))
        self.btn_abrir_out = iu.BrandButton(row, text="ABRIR", kind="chip", height=36,
                                            font=(iu.F_BLACK, 8), width=76, radius=8,
                                            command=self._abrir_destino)
        self.btn_abrir_out.pack(side="left", padx=(8, 0))

    def _build_lista(self):
        card, body, hint = self._section(self.host_lista, 3, "LANZAMIENTOS DETECTADOS", "—")
        self.hint_lista = hint
        top = tk.Frame(body, bg=iu.SURFACE)
        top.pack(fill="x")
        tk.Label(top, text="Desmarcá los que no quieras en el documento.",
                 bg=iu.SURFACE, fg=iu.MUTED, font=(iu.F_SEMI, 9)).pack(side="left")
        self.btn_todos = iu.BrandButton(top, text="TODOS", kind="chip", height=26,
                                        font=(iu.F_BLACK, 8), width=64, radius=7,
                                        command=lambda: self._marcar(self.sel_launch, True))
        self.btn_todos.pack(side="right")
        self.btn_ninguno = iu.BrandButton(top, text="NINGUNO", kind="chip", height=26,
                                          font=(iu.F_BLACK, 8), width=76, radius=7,
                                          command=lambda: self._marcar(self.sel_launch, False))
        self.btn_ninguno.pack(side="right", padx=(0, 6))
        panel = iu.Rounded(body, fill=iu.SURFACE_2, border=iu.BORDER_SOFT, radius=10, pad=6)
        panel.pack(fill="x", pady=(8, 0))
        self.lista_box = panel.body
        self._lista_vacia("Elegí una carpeta y tocá ANALIZAR para ver los lanzamientos.")

    def _build_sin_asociar(self):
        card = iu.Rounded(self.host_unm)
        self.card_unm = card
        body = card.body
        head = tk.Frame(body, bg=iu.SURFACE)
        head.pack(fill="x", pady=(0, 10))
        badge = tk.Canvas(head, width=26, height=26, bg=iu.SURFACE, bd=0,
                          highlightthickness=0)
        badge.create_oval(0, 0, 25, 25, fill=iu.AMBER, outline="")
        badge.create_text(13, 12, text="!", fill=iu.BLACK, font=(iu.F_BLACK, 11))
        badge.pack(side="left")
        tk.Label(head, text="DOCUMENTOS PENDIENTES DE CLASIFICAR", bg=iu.SURFACE, fg=iu.TEXT,
                 font=(iu.F_BLACK, 12)).pack(side="left", padx=(10, 0))
        self.hint_unm = tk.Label(head, text="", bg=iu.SURFACE, fg=iu.DIM,
                                 font=(iu.F_BLACK, 8))
        self.hint_unm.pack(side="right", pady=(4, 0))
        self.lbl_unm_note = tk.Label(
            body, text="No hubo evidencia suficiente para asignarlos a un lanzamiento "
                       "sin mezclar información. Se agregan completos al final.",
            bg=iu.SURFACE, fg=iu.DIM, font=(iu.F_BODY, 8), anchor="w", justify="left")
        self.lbl_unm_note.pack(fill="x", pady=(0, 8))
        iu.autowrap(self.lbl_unm_note, extra=10)
        panel = iu.Rounded(body, fill=iu.SURFACE_2, border=iu.BORDER_SOFT, radius=10, pad=6)
        panel.pack(fill="x")
        self.unm_box = panel.body

    def _build_estado(self):
        card = self._card(self.host_state, pady=(0, 12))
        body = card.body
        row = tk.Frame(body, bg=iu.SURFACE)
        row.pack(fill="x")
        self.stripe_estado = tk.Frame(row, bg=iu.MUTED, width=3)
        self.stripe_estado.pack(side="left", fill="y", padx=(0, 12))
        self.btn_doc = iu.BrandButton(row, text="ABRIR DOCUMENTO", kind="dark", height=36,
                                      font=(iu.F_BLACK, 9), width=176, radius=8,
                                      icon="▤", command=self._abrir_documento)
        content = tk.Frame(row, bg=iu.SURFACE)
        content.pack(side="left", fill="both", expand=True)
        self._estado_content = content
        self.icono_estado = StateIcon(content, bg=iu.SURFACE)
        self.icono_estado.pack(side="left", anchor="n", padx=(0, 10), pady=1)
        text = tk.Frame(content, bg=iu.SURFACE)
        text.pack(side="left", fill="x", expand=True)
        self.lbl_estado_titulo = tk.Label(text, text="EN ESPERA", bg=iu.SURFACE,
                                          fg=iu.MUTED, font=(iu.F_BLACK, 9), anchor="w")
        self.lbl_estado_titulo.pack(fill="x")
        self.lbl_estado = tk.Label(text, text="", bg=iu.SURFACE, fg=iu.TEXT,
                                   font=(iu.F_BODY, 9), anchor="w", justify="left")
        self.lbl_estado.pack(fill="x", pady=(2, 0))
        iu.autowrap(self.lbl_estado, extra=240)

    def _build_log(self):
        card, body, hint = self._section(self.host_log, None, "REGISTRO EN TIEMPO REAL", "LOG")
        top = tk.Frame(body, bg=iu.SURFACE)
        top.pack(fill="x", pady=(0, 6))
        tk.Label(top, text="Todo lo que hace la app, paso a paso.", bg=iu.SURFACE,
                 fg=iu.DIM, font=(iu.F_BODY, 8)).pack(side="left")
        self.btn_log_toggle = iu.BrandButton(top, text="VER REGISTRO", kind="chip", height=26,
                                             font=(iu.F_BLACK, 8), width=140, radius=7,
                                             command=self._toggle_log)
        self.btn_log_toggle.pack(side="right", padx=(6, 0))
        self.btn_log = iu.BrandButton(top, text="LIMPIAR", kind="chip", height=26,
                                      font=(iu.F_BLACK, 8), width=76, radius=7,
                                      command=self._limpiar_log)
        self.btn_log.pack(side="right")
        console = tk.Frame(body, bg=iu.BG_DEEP)
        self.log_console = console
        self.log = tk.Text(console, height=7, wrap="word", state="disabled",
                           font=(iu.F_MONO, 8), relief="flat", borderwidth=0,
                           bg=iu.BG_DEEP, fg="#C7D2DD", insertbackground="#FFFFFF",
                           padx=12, pady=10, selectbackground="#2B333C",
                           highlightthickness=1, highlightbackground=iu.BORDER_SOFT)
        self.log.pack(side="left", fill="both", expand=True)
        self.log_bar = iu.SlimScrollbar(console, command=self.log.yview, bg=iu.BG_DEEP)
        self.log_bar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=lambda a, b: self.log_bar.set(a, b))
        for tag, color in (("ts", iu.DIM), ("info", "#C7D2DD"), ("ok", iu.GREEN),
                           ("err", iu.RED), ("cmd", iu.YEL)):
            self.log.tag_configure(tag, foreground=color)

    # ---- log / estado ----
    def _toggle_log(self):
        self._log_open = not self._log_open
        if self._log_open:
            self.log_console.pack(fill="x")
            self.btn_log_toggle.set_text("OCULTAR REGISTRO")
            self.root.after(90, self._scroll_to_log)
        else:
            self.log_console.pack_forget()
            self.btn_log_toggle.set_text("VER REGISTRO")

    def _scroll_to_log(self):
        if not self._log_open or self._closing:
            return
        try:
            top = self.log_console.winfo_rooty()
            bottom = top + self.log_console.winfo_height()
            vtop = self.scroll.canvas.winfo_rooty()
            vbottom = vtop + self.scroll.canvas.winfo_height()
            delta = top - self.content.winfo_rooty()
        except tk.TclError:
            return
        if vtop <= top and bottom <= vbottom:
            return
        self.scroll.scroll_to(max(0, delta - 90))

    def _set_estado(self, kind, mensaje, titulo=None):
        conf = ESTADOS.get(kind, ESTADOS["idle"])
        self.icono_estado.draw(kind)
        self.lbl_estado_titulo.configure(text=titulo or conf["title"], fg=conf["color"])
        self.lbl_estado.configure(text=mensaje or "")
        try:
            self.stripe_estado.configure(bg=conf["color"])
            primera = (mensaje or "").splitlines()[0] if mensaje else ""
            self.footer_txt.configure(text=_corto(primera, 140))
        except tk.TclError:
            pass

    def _log(self, mensaje, kind="info"):
        if not hasattr(self, "log"):
            return
        texto = str(mensaje).strip()
        if kind == "info" and texto == self._ultimo_log:
            return
        self._ultimo_log = texto if kind == "info" else None
        try:
            self.log.configure(state="normal")
            self.log.insert("end", time.strftime("%H:%M:%S  "), "ts")
            self.log.insert("end", texto + "\n", kind)
            self.log.see("end")
            self._log_counter += 1
            if self._log_counter > 500:
                self.log.delete("1.0", "100.0")
                self._log_counter -= 99
            self.log.configure(state="disabled")
        except tk.TclError:
            pass

    def _limpiar_log(self):
        try:
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            self._ultimo_log = None
        except tk.TclError:
            pass

    # ---- configuración ----
    def _guardar(self, *_):
        cfg = {
            "carpeta": self.v_carpeta.get(),
            "destino": self.v_destino.get(),
            "indice": self.v_indice.get(),
            "texto_completo": self.v_texto.get(),
            "sin_asociar": self.v_sinasoc.get(),
            "abrir": self.v_abrir.get(),
            "orden": self._cod_orden.get(self.v_orden.get(), "zip"),
        }
        self.cfg.update(cfg)
        try:
            self.backend.guardar(cfg)
        except Exception:
            pass

    def _cfg_trabajo(self):
        return dict(self.cfg, **{
            "carpeta": self.v_carpeta.get(),
            "destino": self.v_destino.get(),
            "indice": self.v_indice.get(),
            "texto_completo": self.v_texto.get(),
            "sin_asociar": self.v_sinasoc.get(),
            "abrir": self.v_abrir.get(),
            "orden": self._cod_orden.get(self.v_orden.get(), "zip"),
        })

    # ---- carpeta ----
    def _elegir_carpeta(self):
        if self._busy:
            return
        inicial = self.v_carpeta.get()
        if not (inicial and os.path.isdir(inicial)):
            inicial = os.path.expanduser("~")
        carpeta = filedialog.askdirectory(
            parent=self.root, initialdir=inicial,
            title="Selecciona la carpeta COMPLETA de la tanda/día de MusoSoup")
        if not carpeta:
            return
        carpeta = os.path.normpath(carpeta)
        self.v_carpeta.set(carpeta)
        self._reset_analisis()
        self._guardar()
        self._refrescar_carpeta()
        self._actualizar_salida()
        self._log(f"Carpeta elegida: {carpeta}", "cmd")
        self._escanear(carpeta, luego_analizar=True)

    def _refrescar_carpeta(self):
        carpeta = self.v_carpeta.get()
        if not carpeta:
            self.lbl_carpeta.configure(text="Ninguna carpeta elegida", fg=iu.DIM)
            self.lbl_carpeta_sub.configure(
                text="Elegí la carpeta COMPLETA del día: con los ZIP de MusoSoup "
                     "y los documentos sueltos.")
            self.lbl_live.configure(text="SIN CARPETA", fg=iu.DIM)
        elif not self.backend.existe(carpeta):
            self.lbl_carpeta.configure(text=_corto(os.path.basename(carpeta) or carpeta, 40),
                                       fg=iu.RED)
            self.lbl_carpeta_sub.configure(text=f"{carpeta}\nLa carpeta ya no existe.")
            self.lbl_live.configure(text="NO ENCONTRADA", fg=iu.RED)
        else:
            self.lbl_carpeta.configure(text=_corto(os.path.basename(carpeta) or carpeta, 40),
                                       fg=iu.TEXT)
            r = self.resumen
            if r:
                detalle = (f"{r['zips']} ZIP · {r['docs']} documentos sueltos  ·  "
                           f"{carpeta}")
            else:
                detalle = carpeta
            self.lbl_carpeta_sub.configure(text=detalle)
            self.lbl_live.configure(text="LISTA", fg=iu.GREEN)
        self._actualizar_botones()

    def _escanear(self, carpeta, luego_analizar=False):
        """Conteo rápido en segundo plano."""
        def leer():
            try:
                r = self.backend.resumen(carpeta)
                err = None
            except Exception as exc:
                r, err = None, f"No pude leer la carpeta: {exc}"
            self._cola.put(("resumen", carpeta, r, err, luego_analizar))
        threading.Thread(target=leer, daemon=True).start()

    def _reset_analisis(self):
        self.analisis = None
        self.resumen = None
        self.sel_launch.clear()
        self.sel_unm.clear()
        self._poblar_lista()
        self._poblar_unm()
        self._cifras_vacias()
        self.cta.set_text(self._texto_boton())

    def _abrir_carpeta(self):
        c = self.v_carpeta.get()
        if c and self.backend.existe(c):
            _abrir(c)

    # ---- salida ----
    def _actualizar_salida(self):
        carpeta = self.v_carpeta.get()
        destino = self.v_destino.get()
        try:
            ruta = self.backend.salida_prevista(carpeta or ".", destino)
        except Exception:
            ruta = ""
        nombre = os.path.basename(ruta) if ruta else "LANZAMIENTOS.docx"
        self.lbl_out.configure(text=nombre)
        if destino:
            self.lbl_out_dir.configure(text=os.path.dirname(ruta))
        elif carpeta:
            self.lbl_out_dir.configure(
                text=f"Automático · {os.path.dirname(ruta)}")
        else:
            self.lbl_out_dir.configure(
                text="Automático · carpeta INFO COMPLETA dentro de la carpeta del día.")

    def _elegir_destino(self):
        inicial = self.v_destino.get() or self.v_carpeta.get()
        if not (inicial and os.path.isdir(inicial)):
            inicial = os.path.expanduser("~")
        d = filedialog.askdirectory(parent=self.root, initialdir=inicial,
                                    title="¿Dónde guardo el Word?")
        if not d:
            return
        self.v_destino.set(os.path.normpath(d))
        self._guardar()
        self._actualizar_salida()

    def _destino_auto(self):
        self.v_destino.set("")
        self._guardar()
        self._actualizar_salida()

    def _abrir_destino(self):
        carpeta = self.v_carpeta.get()
        try:
            ruta = self.backend.salida_prevista(carpeta or ".", self.v_destino.get())
        except Exception:
            return
        d = os.path.dirname(ruta)
        if os.path.isdir(d):
            _abrir(d)
        elif os.path.isdir(carpeta or ""):
            _abrir(carpeta)

    def _abrir_documento(self):
        if self._ultimo_doc and os.path.exists(self._ultimo_doc):
            _abrir(self._ultimo_doc)

    # ---- opciones ----
    def _sinasoc_changed(self):
        self._guardar()
        self._poblar_unm()

    def _orden_changed(self, *_):
        self._guardar()
        if self.analisis:
            self._poblar_lista()

    # ---- cifras ----
    def _cifras_vacias(self):
        for num, _color in self.cifras.values():
            num.configure(text="—", fg=iu.DIM)

    def _set_cifra(self, clave, valor):
        num, color = self.cifras[clave]
        num.configure(text=str(valor), fg=color if valor else iu.DIM)

    def _actualizar_cifras(self):
        a = self.analisis
        if not a:
            self._cifras_vacias()
            if self.resumen:
                self._set_cifra("zip", self.resumen["zips"])
            return
        reg = [l for l in a["launches"] if not l.get("candidate_review")]
        cand = len(a["launches"]) - len(reg)
        ok = sum(1 for l in reg if l["verification_status"] == "VERIFICADO")
        self._set_cifra("zip", a["zips"])
        self._set_cifra("lanz", len(reg))
        self._set_cifra("cand", cand)
        self._set_cifra("ok", ok)
        self._set_cifra("rev", len(reg) - ok)
        self._set_cifra("sin", len(a["unmatched"]))

    # ---- listas ----
    def _ordenados(self):
        ls = list(self.analisis["launches"]) if self.analisis else []
        if self._cod_orden.get(self.v_orden.get(), "zip") == "artista":
            ls.sort(key=lambda l: (l["verified_artist"] or "").lower())
        return ls

    def _lista_vacia(self, texto):
        tk.Label(self.lista_box, text=texto, bg=iu.SURFACE_2, fg=iu.DIM,
                 font=(iu.F_BODY, 9)).pack(pady=14)

    def _limpiar_box(self, box):
        for child in box.winfo_children():
            child.destroy()

    def _poblar_lista(self):
        self._limpiar_box(self.lista_box)
        self.rows_launch = []
        if not self.analisis:
            self.hint_lista.configure(text="—")
            self._lista_vacia("Elegí una carpeta y tocá ANALIZAR para ver los lanzamientos.")
            return
        ls = self._ordenados()
        if not ls:
            self.hint_lista.configure(text="0")
            self._lista_vacia("No encontré ningún ZIP en esta carpeta.")
            return
        for n, l in enumerate(ls, 1):
            var = self.sel_launch.setdefault(l["id"], tk.BooleanVar(value=True))
            ok = l["verification_status"] == "VERIFICADO"
            cand = bool(l.get("candidate_review"))
            titulo = l["verified_artist"]
            if l["verified_release"] != "No especificado":
                titulo += f"  ·  {l['verified_release']}"
            checks = " · ".join(
                f"{nom} {'✓' if c == '✓' else '!'}"
                for nom, c in zip(("Artista", "Lanzamiento", "Proyecto", "Tipo"),
                                  l["verification_checks"]))
            partes = [x for x in (l["verified_release_type"], l["verified_project_type"])
                      if x != "No especificado"] or ["Tipo sin detectar"]
            partes += [f"{len(l['sources'])} fuente{'s' if len(l['sources']) != 1 else ''}",
                       checks]
            partes.append(l["zip_name"] if l.get("zip_name") else "Documento suelto")
            row = ItemRow(self.lista_box, f"{n:02d}", titulo, "   ·   ".join(partes),
                          "CANDIDATO" if cand else ("VERIFICADO" if ok else "REVISAR"),
                          iu.GREEN if ok else iu.AMBER, var, self._seleccion_changed)
            row.pack(fill="x", padx=2, pady=1)
            self.rows_launch.append(row)
            if n < len(ls):
                tk.Frame(self.lista_box, bg=iu.BORDER_SOFT, height=1).pack(fill="x", padx=12)
        self._resumen_seleccion()

    def _poblar_unm(self):
        self._limpiar_box(self.unm_box)
        self.rows_unm = []
        a = self.analisis
        if not a or not a["unmatched"] or not self.v_sinasoc.get():
            self.card_unm.pack_forget()
            return
        self.card_unm.pack(fill="x", pady=(0, 12))
        un = a["unmatched"]
        for n, u in enumerate(un, 1):
            var = self.sel_unm.setdefault(u["id"], tk.BooleanVar(value=True))
            palabras = len((u.get("text") or "").split())
            detalle = (f"{palabras} palabras" if palabras
                       else "sin texto extraíble")
            row = ItemRow(self.unm_box, f"{n:02d}", u["name"], detalle, "PENDIENTE",
                          iu.AMBER, var, self._seleccion_changed)
            row.pack(fill="x", padx=2, pady=1)
            self.rows_unm.append(row)
            if n < len(un):
                tk.Frame(self.unm_box, bg=iu.BORDER_SOFT, height=1).pack(fill="x", padx=12)
        self._resumen_seleccion()

    def _marcar(self, vars_, on):
        for v in vars_.values():
            v.set(on)
        self._seleccion_changed()

    def _seleccion_changed(self):
        self._resumen_seleccion()

    def _resumen_seleccion(self):
        total = len(self.sel_launch)
        marc = sum(1 for v in self.sel_launch.values() if v.get())
        self.hint_lista.configure(text=f"{marc} DE {total}" if total else "—")
        if self.analisis and self.analisis["unmatched"]:
            t = len(self.sel_unm)
            m = sum(1 for v in self.sel_unm.values() if v.get())
            self.hint_unm.configure(text=f"{m} DE {t}")

    # ---- botón principal ----
    def _texto_boton(self):
        return "GENERAR DOCUMENTO" if self.analisis is not None else "ANALIZAR Y GENERAR"

    def _actualizar_botones(self):
        hay = bool(self.v_carpeta.get()) and self.backend.existe(self.v_carpeta.get())
        libre = hay and not self._busy
        self.btn_analizar.set_enabled(libre)
        self.btn_abrir_carpeta.set_enabled(hay)
        self.btn_elegir.set_enabled(not self._busy)

    def _validar_carpeta(self):
        c = self.v_carpeta.get()
        if not c:
            messagebox.showwarning("Falta la carpeta",
                                   "Elegí primero la carpeta del día con «ELEGIR CARPETA…».",
                                   parent=self.root)
            return None
        if not self.backend.existe(c):
            messagebox.showerror("Carpeta no encontrada",
                                 "La carpeta seleccionada ya no existe.", parent=self.root)
            return None
        return c

    def _analizar(self):
        if self._busy:
            return
        if self._validar_carpeta() is None:
            return
        self._iniciar("analizar")

    def _go(self):
        if self._busy:
            return
        if self._validar_carpeta() is None:
            return
        if self.analisis is not None:
            sel = {i for i, v in self.sel_launch.items() if v.get()}
            sel_u = {i for i, v in self.sel_unm.items() if v.get()}
            if not sel and not (sel_u and self.v_sinasoc.get()):
                messagebox.showwarning("Nada seleccionado",
                                       "Marcá al menos un lanzamiento para el documento.",
                                       parent=self.root)
                return
            self._iniciar("generar", sel, sel_u)
        else:
            self._iniciar("todo")

    def _iniciar(self, modo, sel=None, sel_u=None):
        carpeta = self.v_carpeta.get()
        self._guardar()
        cfg = self._cfg_trabajo()
        self._busy = True
        self._modo = modo
        self._cancelando = False
        self._ultimo_doc = ""
        self.btn_doc.pack_forget()
        self.cta.set_enabled(False)
        self.cta.set_text("PROCESANDO…")
        self.btn_cancel.set_enabled(True)
        self.btn_cancel.set_text("CANCELAR")
        self.btn_cancel.pack(side="right", padx=(12, 0))
        self._actualizar_botones()
        self.meter.set(0, animate=False)
        etiqueta = {"analizar": "Analizando", "generar": "Generando el documento de",
                    "todo": "Analizando y generando"}[modo]
        self._set_estado("working", f"{etiqueta} «{os.path.basename(carpeta) or carpeta}»…")
        self._log(f"── Inicio · {modo} · {carpeta}", "cmd")

        def trabajo():
            try:
                analisis = self.analisis
                if modo in ("analizar", "todo"):
                    esc = 0.6 if modo == "todo" else 1.0
                    analisis = self.backend.analizar(
                        carpeta, lambda p, m: self._progreso(p * esc, m))
                    self._cola.put(("analisis", analisis))
                if modo in ("generar", "todo"):
                    if modo == "todo":
                        ids = {l["id"] for l in analisis["launches"]}
                        ids_u = {u["id"] for u in analisis["unmatched"]}
                    else:
                        ids, ids_u = sel, sel_u
                    base = 60 if modo == "todo" else 0
                    esc = 0.4 if modo == "todo" else 1.0
                    ruta = self.backend.generar(
                        analisis, ids, ids_u, cfg,
                        lambda p, m: self._progreso(base + p * esc, m))
                    n_u = len(ids_u) if cfg.get("sin_asociar", True) else 0
                    self._cola.put(("fin", ruta, len(ids), n_u))
                else:
                    self._cola.put(("fin", None, 0, 0))
            except Exception as exc:
                tb = traceback.format_exc()
                try:
                    self.backend.registrar_error(exc, tb)
                except Exception:
                    pass
                self._cola.put(("error", f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=trabajo, daemon=True).start()

    def _progreso(self, porcentaje, mensaje):
        self._cola.put(("prog", float(porcentaje), str(mensaje)))

    # ---- eventos del hilo ----
    def _poll(self):
        try:
            while True:
                ev = self._cola.get_nowait()
                tipo = ev[0]
                if tipo == "prog":
                    _, p, msg = ev
                    self.meter.set(min(0.99, p / 100.0))
                    self._set_estado("working", msg)
                    self._log(msg, "info")
                elif tipo == "resumen":
                    self._on_resumen(*ev[1:])
                elif tipo == "analisis":
                    self._on_analisis(ev[1])
                elif tipo == "fin":
                    self._on_fin(*ev[1:])
                elif tipo == "error":
                    if self._cancelando:
                        self._set_estado("warn", "Proceso cancelado. No se escribió ningún "
                                                 "documento nuevo.")
                        self._log("Proceso cancelado por el usuario.", "cmd")
                    else:
                        self._set_estado("error", ev[1])
                        self._log("ERROR · " + ev[1], "err")
                    self.meter.set(0, animate=False)
                    self._fin_trabajo()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            self.root.after(90, self._poll)
        except tk.TclError:
            pass

    def _on_resumen(self, carpeta, r, err, luego_analizar):
        if carpeta != self.v_carpeta.get():
            return
        if err:
            self._log(err, "err")
            self._set_estado("error", err)
            return
        self.resumen = r
        self._refrescar_carpeta()
        self._actualizar_cifras()
        self._log(f"{r['zips']} ZIP y {r['docs']} documentos sueltos en la carpeta.", "info")
        if r["zips"] == 0 and r["docs"] == 0:
            self._set_estado("warn", "No encontré ZIP ni documentos en esa carpeta. "
                                     "¿Es la carpeta correcta?")
        elif not self._busy:
            if luego_analizar:
                self._analizar()
            else:
                self._set_estado("idle", f"Listo: {r['zips']} ZIP y {r['docs']} "
                                         "documentos. Tocá ANALIZAR o GENERAR.")

    def _on_analisis(self, a):
        self.analisis = a
        self.sel_launch.clear()
        self.sel_unm.clear()
        self._poblar_lista()
        self._poblar_unm()
        self._actualizar_cifras()
        for nombre, error in a.get("errores", []):
            self._log(f"No pude leer «{nombre}»: {error}", "err")
        ls = a["launches"]
        for l in ls:
            marca = ("CANDIDATO" if l.get("candidate_review")
                     else "OK" if l["verification_status"] == "VERIFICADO" else "REVISAR")
            self._log(f"{l['verified_artist']} | {l['verified_release']} | "
                      f"{l['verified_release_type']} · {marca}", "ok" if marca == "OK" else "info")
        if a["unmatched"]:
            self._log(f"{len(a['unmatched'])} documento(s) pendientes de clasificar.", "info")

    def _on_fin(self, ruta, n_l, n_u):
        a = self.analisis or {}
        errores = a.get("errores", [])
        self.meter.set(1.0, animate=False)
        if ruta:
            self._ultimo_doc = ruta
            partes = [f"{n_l} lanzamiento{'s' if n_l != 1 else ''}"]
            if n_u:
                partes.append(f"{n_u} documento{'s' if n_u != 1 else ''} pendiente{'s' if n_u != 1 else ''}")
            msg = f"Documento listo · {' · '.join(partes)}\n{ruta}"
            if errores:
                msg += f"\n{len(errores)} archivo(s) no se pudieron leer (ver registro)."
            self._set_estado("warn" if errores else "success", msg)
            self._log(f"Documento: {ruta}", "ok")
            self.btn_doc.pack(side="right", padx=(12, 0), before=self._estado_content)
            if self.v_abrir.get():
                _abrir(ruta)
        else:
            ls = a.get("launches", [])
            reg = [l for l in ls if not l.get("candidate_review")]
            ok = sum(1 for l in reg if l["verification_status"] == "VERIFICADO")
            msg = (f"Análisis listo · {len(reg)} lanzamientos · {ok} verificados · "
                   f"{len(reg) - ok} a revisar · {len(ls) - len(reg)} candidatos · "
                   f"{len(a.get('unmatched', []))} pendientes.\n"
                   "Revisá la lista y tocá GENERAR DOCUMENTO.")
            if not ls:
                msg = "No encontré ZIP ni lanzamientos en esa carpeta."
            self._set_estado("warn" if errores or not ls else "success", msg)
            self._log(msg.splitlines()[0], "ok")
        self._fin_trabajo()

    def _fin_trabajo(self):
        self._busy = False
        self._cancelando = False
        self.btn_cancel.pack_forget()
        self.cta.set_enabled(True)
        self.cta.set_text(self._texto_boton())
        self._actualizar_botones()

    def _cancelar(self):
        if not self._busy or self._cancelando:
            return
        if not messagebox.askyesno(
                "Cancelar el proceso",
                "¿Detener el proceso en curso?\n\nNo se escribirá ningún documento nuevo.",
                parent=self.root):
            return
        if not self._busy:
            return
        self._cancelando = True
        self.btn_cancel.set_enabled(False)
        self.btn_cancel.set_text("CANCELANDO…")
        self._set_estado("warn", "Cancelando el proceso…")
        self._log("Cancelación pedida por el usuario.", "cmd")
        threading.Thread(target=self.backend.cancelar, daemon=True).start()

    def cerrar(self):
        if self._closing:
            return
        self._closing = True
        self._guardar()
        for nombre in ("_job_header", "_job_reveal"):
            job = getattr(self, nombre, None)
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        threading.Thread(target=self.backend.cancelar, daemon=True).start()

    @property
    def _cola(self):
        return self._cola_obj
