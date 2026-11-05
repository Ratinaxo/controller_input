"""Preview de la cabeza: la cámara en vivo, el punto yaw/pitch y las barras
de traslación y roll."""
import tkinter as tk

from frontend.camera_view.widget import CameraView
from frontend.components import AxisBars, secondary_button
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

DOT_RADIUS = 5
# Orden visual de las barras, con la posición de cada valor en la tupla de
# get_head_axes(): (yaw, pitch, roll, tx, ty, tz).
BARS = (
    ("tx", "LAT", C.AXIS_LATERAL, 3),
    ("ty", "VER", C.AXIS_VERTICAL, 4),
    ("tz", "PROF", C.AXIS_DEPTH, 5),
    ("roll", "ROLL", C.AXIS_ROLL, 2),
)


class HeadView:
    def __init__(self, parent, ctx, on_recenter):
        frame = tk.Frame(parent, bg=C.BG)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        tk.Label(frame, text="TRACKER PREVIEW", bg=C.BG, fg=C.TEXT_MUTED, font=FONTS.label).pack()

        # La cámara va justo encima del punto yaw/pitch: son la misma
        # lectura, una en imagen y otra en números. Vive en un contenedor
        # propio que SIEMPRE queda empaquetado -- igual que en la pestaña
        # Head Tracker -- para que ocultarla y volver a mostrarla no la
        # haga saltar al final de este panel (`pack` respeta el orden de
        # llamada, no el de creación).
        self.camera_holder = tk.Frame(frame, bg=C.BG)
        self.camera_holder.pack(fill='x')
        self.camera = CameraView(self.camera_holder, ctx)
        self.camera.pack(pady=(0, 8))
        ctx.camera_view = self.camera

        self.width = S.PREVIEW_SIZE
        self.height = S.HEAD_PREVIEW_H
        self.cx, self.cy = self.width // 2, self.height // 2
        self.canvas = tk.Canvas(frame, width=self.width, height=self.height, bg=C.CANVAS,
                                highlightthickness=1, highlightbackground=C.BORDER)
        self.canvas.pack(pady=5)
        secondary_button(frame, "🎯 RECENTRAR (CABEZA + STICK)", command=on_recenter,
                         font=FONTS.note_bold, relief="flat"
                         ).pack(side='bottom', fill='x', padx=60, pady=(0, 10))
        self.canvas.create_line(self.cx, 0, self.cx, self.height, fill=C.GRID)
        self.canvas.create_line(0, self.cy, self.width, self.cy, fill=C.GRID)
        self.dot = self.canvas.create_oval(0, 0, 0, 0, fill=C.ACCENT)

        # El punto solo muestra yaw/pitch, así que la traslación y el roll
        # necesitan su propia vista. Es también la forma de verificar el
        # pivote del cuello: girar la cabeza sin mover el cuerpo debe dejar
        # las tres primeras barras casi quietas.
        tk.Label(frame, text="EJES (traslación y roll)", bg=C.BG, fg=C.TEXT_MUTED,
                 font=FONTS.note).pack()
        self.canvas_axes = tk.Canvas(frame, width=self.width, height=S.AXIS_BARS_H,
                                     bg=C.CANVAS, highlightthickness=1,
                                     highlightbackground=C.BORDER)
        self.canvas_axes.pack(pady=(2, 5))
        self.bars = AxisBars(self.canvas_axes,
                             [(key, text, color) for key, text, color, _ in BARS],
                             label_x=26, x0=54, x1=self.width - 8, y0=6, row_step=17,
                             font=FONTS.micro)

    def update(self, tracker):
        if tracker:
            yaw, pitch = tracker.get_axes()
            x = self.cx + yaw * S.HEAD_VIS_SCALE
            y = self.cy + pitch * S.HEAD_VIS_SCALE
            self.canvas.coords(self.dot, x - DOT_RADIUS, y - DOT_RADIUS,
                               x + DOT_RADIUS, y + DOT_RADIUS)
            self.canvas.itemconfig(self.dot, fill=C.ACCENT)
            getter = getattr(tracker, "get_head_axes", None)
            axes6 = list(getter()) if getter else []
            axes6 += [0.0] * (6 - len(axes6))
            self.bars.update({key: axes6[idx] for key, _, _, idx in BARS})
        else:
            # Fuente externa: este programa no mide la cabeza.
            self.canvas.coords(self.dot, self.cx - DOT_RADIUS, self.cy - DOT_RADIUS,
                               self.cx + DOT_RADIUS, self.cy + DOT_RADIUS)
            self.canvas.itemconfig(self.dot, fill=C.INACTIVE)
            self.bars.update({key: 0.0 for key, _, _, _ in BARS})
