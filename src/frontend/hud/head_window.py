"""Ventana del HUD con la cabeza y la traslación (abajo a la izquierda)."""
import tkinter as tk

from frontend.components.axis_bars import AxisBars
from frontend.hud.overlay import Draggable
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

DOT_RADIUS = 4


class HeadWindow:
    def __init__(self, window, screen_h):
        self.size = S.HUD_HEAD_SIZE
        self.center = self.size // 2
        # Alto extra para las barras de traslación (6DOF) debajo del punto.
        self.height = self.size + S.HUD_TRANS_PANEL_H

        x_pos = S.HUD_MARGIN
        y_pos = screen_h - self.height - S.HUD_MARGIN
        window.geometry(f"{self.size}x{self.height}+{x_pos}+{y_pos}")

        self.canvas = tk.Canvas(window, width=self.size, height=self.height, bg=C.HUD_BG,
                                highlightthickness=0)
        self.canvas.pack()
        self.drag = Draggable(self.canvas)

        c = self.center
        self.canvas.create_line(c, 10, c, 140, fill=C.HUD_HEAD, dash=(2, 4))
        self.canvas.create_line(10, c, 140, c, fill=C.HUD_HEAD, dash=(2, 4))
        self.canvas.create_text(c, 10, text="HEAD", fill=C.HUD_HEAD, font=FONTS.hud_small)
        self.head_dot = self.canvas.create_oval(0, 0, 0, 0, fill=C.HUD_HEAD, outline='')

        # Barras de traslación: sirven para ver en vuelo si un eje deriva
        # solo. Si estás quieto y una barra se va de cero, ese eje necesita
        # más zona muerta o el pivote del cuello está mal ajustado.
        self.trans_bars = AxisBars(
            self.canvas,
            [("x", "LAT", C.AXIS_LATERAL), ("y", "VER", C.AXIS_VERTICAL),
             ("z", "PRO", C.AXIS_DEPTH)],
            label_x=14, x0=28, x1=self.size - 10, y0=self.size + 8, row_step=16,
            font=FONTS.hud_micro)

    def update(self, head_yaw, head_pitch, head_trans=None):
        hx = self.center + (head_yaw * S.HUD_HEAD_SCALE)
        hy = self.center + (head_pitch * S.HUD_HEAD_SCALE)
        self.canvas.coords(self.head_dot, hx - DOT_RADIUS, hy - DOT_RADIUS,
                           hx + DOT_RADIUS, hy + DOT_RADIUS)
        values = head_trans if head_trans else (0.0, 0.0, 0.0)
        self.trans_bars.update(dict(zip(("x", "y", "z"), values)))
