"""Ventana del HUD con el stick, los gases y el timón (abajo a la derecha)."""
import tkinter as tk

from frontend.hud.overlay import Draggable
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

DOT_RADIUS = 6
# Geometría fija del dibujo (px dentro del canvas de 260x260).
THROTTLE_TOP, THROTTLE_BOTTOM = 40, 218
THROTTLE_SPAN = THROTTLE_BOTTOM - THROTTLE_TOP     # 178
RUDDER_CENTER, RUDDER_HALF = 130, 90


class StickWindow:
    def __init__(self, window, screen_w, screen_h):
        self.size = S.HUD_STICK_SIZE
        self.center = self.size // 2
        self.radius_vis = S.HUD_STICK_RADIUS

        x_pos = screen_w - self.size - S.HUD_MARGIN
        y_pos = screen_h - self.size - S.HUD_MARGIN
        window.geometry(f"{self.size}x{self.size}+{x_pos}+{y_pos}")

        self.canvas = tk.Canvas(window, width=self.size, height=self.size, bg=C.HUD_BG,
                                highlightthickness=0)
        self.canvas.pack()
        self.drag = Draggable(self.canvas)

        c, r = self.center, self.radius_vis
        self.canvas.create_rectangle(c - r, c - r, c + r, c + r,
                                     outline=C.HUD_GUIDE, width=2, dash=(4, 4))
        # Cruz central
        self.canvas.create_line(c, 40, c, 220, fill=C.GRID)
        self.canvas.create_line(40, c, 220, c, fill=C.GRID)

        # 1. Punto del stick
        self.stick_dot = self.canvas.create_oval(0, 0, 0, 0, fill=C.STICK_INITIAL,
                                                 outline=C.STICK_OUTLINE)

        # 2. Barra de gases
        self.canvas.create_rectangle(10, THROTTLE_TOP, 25, THROTTLE_BOTTOM, outline=C.HUD_FRAME)
        self.canvas.create_line(8, 129, 27, 129, fill=C.HUD_TICK, width=1)
        self.throttle_bar = self.canvas.create_rectangle(12, THROTTLE_BOTTOM, 23, THROTTLE_BOTTOM,
                                                         fill=C.THROTTLE, outline="")
        self.canvas.create_text(18, 30, text="THR", fill=C.HUD_FRAME, font=FONTS.hud_label)

        # 3. Barra de timón
        self.canvas.create_rectangle(40, 235, 220, 250, outline=C.HUD_FRAME)
        self.canvas.create_line(RUDDER_CENTER, 235, RUDDER_CENTER, 250, fill=C.HUD_TICK)
        self.rudder_bar = self.canvas.create_rectangle(RUDDER_CENTER, 237, RUDDER_CENTER, 248,
                                                       fill=C.RUDDER, outline="")
        self.canvas.create_text(RUDDER_CENTER, 225, text="RUDDER", fill=C.HUD_FRAME,
                                font=FONTS.hud_label)

    @staticmethod
    def stick_color(x_norm, y_norm, is_deadzone, is_snapped):
        if is_deadzone:
            return C.STICK_DEADZONE
        if is_snapped:
            return C.STICK_SNAPPED                   # pegado al eje
        if abs(x_norm) > 0.99 or abs(y_norm) > 0.99:
            return C.STICK_SATURATED                 # al máximo
        return C.STICK_NORMAL

    @staticmethod
    def throttle_color(throttle):
        if throttle > 0.95:
            return C.THROTTLE_WEP
        if throttle < 0:
            return C.THROTTLE_REVERSE
        return C.THROTTLE

    def update(self, x_norm, y_norm, throttle, rudder, is_deadzone, is_snapped):
        vis_x = self.center + (x_norm * self.radius_vis)
        vis_y = self.center + (y_norm * self.radius_vis)
        self.canvas.coords(self.stick_dot, vis_x - DOT_RADIUS, vis_y - DOT_RADIUS,
                           vis_x + DOT_RADIUS, vis_y + DOT_RADIUS)
        self.canvas.itemconfig(self.stick_dot,
                               fill=self.stick_color(x_norm, y_norm, is_deadzone, is_snapped))

        # Gases: -1..1 -> altura de la barra (el eje Y de pantalla va al revés).
        normalized = (throttle + 1.0) / 2.0
        top = THROTTLE_BOTTOM - (normalized * THROTTLE_SPAN)
        self.canvas.coords(self.throttle_bar, 12, THROTTLE_BOTTOM, 23, top)
        self.canvas.itemconfig(self.throttle_bar, fill=self.throttle_color(throttle))

        # Timón: 90 px por lado desde el centro.
        self.canvas.coords(self.rudder_bar, RUDDER_CENTER, 237,
                           RUDDER_CENTER + rudder * RUDDER_HALF, 248)
