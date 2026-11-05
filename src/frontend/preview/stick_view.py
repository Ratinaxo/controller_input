"""Preview del stick: el punto se mueve con la misma física que el vuelo."""
import tkinter as tk

from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

DOT_RADIUS = 6


class StickView:
    def __init__(self, parent):
        frame = tk.Frame(parent, bg=C.BG)
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        tk.Label(frame, text="STICK PREVIEW", bg=C.BG, fg=C.TEXT_MUTED, font=FONTS.label).pack()

        self.size = S.PREVIEW_SIZE
        self.center = self.size // 2
        self.scale = S.STICK_VIS_SCALE
        self.canvas = tk.Canvas(frame, width=self.size, height=self.size, bg=C.CANVAS,
                                highlightthickness=1, highlightbackground=C.BORDER)
        self.canvas.pack(pady=5)
        limit = self.scale
        c = self.center
        self.canvas.create_rectangle(c - limit, c - limit, c + limit, c + limit,
                                     outline=C.DIVIDER, dash=(2, 4))
        self.canvas.create_line(c, 0, c, self.size, fill=C.GRID)
        self.canvas.create_line(0, c, self.size, c, fill=C.GRID)
        self.dot = self.canvas.create_oval(0, 0, 0, 0, fill=C.WARN)

    def update(self, fx, fy, in_deadzone):
        x = self.center + fx * self.scale
        y = self.center + fy * self.scale
        self.canvas.coords(self.dot, x - DOT_RADIUS, y - DOT_RADIUS, x + DOT_RADIUS, y + DOT_RADIUS)
        self.canvas.itemconfig(self.dot, fill=C.INACTIVE if in_deadzone else C.WARN)
