"""Gráfico de la respuesta del stick: zona muerta reescalada + curva."""
import math
import tkinter as tk

from frontend.style import colors as C, spacing as S

FALLBACK_WIDTH = 350    # ancho si el canvas todavía no tiene tamaño real
SAMPLE_STEP_PX = 4


class CurveGraph:
    """Dibuja la misma fórmula que physics.rs sobre un eje."""

    def __init__(self, parent, get_curve, get_deadzone):
        self.get_curve = get_curve
        self.get_deadzone = get_deadzone
        self.canvas = tk.Canvas(parent, height=S.CURVE_GRAPH_H, bg=C.GRID, highlightthickness=0)
        self.canvas.pack(fill='x', padx=S.PAD_TAB, pady=10)
        self.canvas.bind("<Configure>", lambda e: self.draw())

    def draw(self):
        w = self.canvas.winfo_width()
        if w < 10:
            w = FALLBACK_WIDTH
        h = S.CURVE_GRAPH_H
        self.canvas.delete("all")
        curve = self.get_curve()
        dz = max(0.0, min(self.get_deadzone(), 0.95))
        points = []
        for i in range(0, w + 1, SAMPLE_STEP_PX):
            x_norm = i / w
            y_norm = 0.0 if x_norm <= dz else math.pow((x_norm - dz) / (1.0 - dz), curve)
            points.extend([i, h - (y_norm * h)])
        if dz > 0:
            self.canvas.create_rectangle(0, 0, dz * w, h, fill=C.DEADZONE_FILL, outline="")
        self.canvas.create_line(points, fill=C.ACCENT, width=2)
