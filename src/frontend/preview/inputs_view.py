"""RAW INPUTS: gases (rueda), timón (rueda horizontal) y botones del mouse."""
import tkinter as tk
from tkinter import ttk

from frontend.style import colors as C
from frontend.style.fonts import FONTS

RUDDER_H = 15
RUDDER_DECAY = 0.01      # el timón del preview vuelve solo al centro
MOUSE_BUTTONS = [("L", "Button.left"), ("R", "Button.right"), ("M", "Button.middle"),
                 ("S1", "Button.x1"), ("S2", "Button.x2")]


class InputsView:
    def __init__(self, parent):
        tk.Label(parent, text="RAW INPUTS", bg=C.BG, fg=C.TEXT_MUTED,
                 font=FONTS.label).pack(pady=(10, 0))
        self.pb_throttle = ttk.Progressbar(parent, orient="horizontal", mode="determinate")
        self.pb_throttle.pack(fill='x', padx=30, pady=5)
        self.canvas_rudder = tk.Canvas(parent, height=RUDDER_H, bg=C.SURFACE_OFF,
                                       highlightthickness=0)
        self.canvas_rudder.pack(fill='x', padx=30, pady=5)
        self.rudder_ind = self.canvas_rudder.create_rectangle(0, 0, 0, 0, fill=C.RUDDER_PREVIEW)

        container = tk.Frame(parent, bg=C.BG)
        container.pack(pady=10)
        self.buttons = {}
        for text, code in MOUSE_BUTTONS:
            lbl = tk.Label(container, text=text, bg=C.SURFACE_OFF, fg=C.TEXT_STRONG,
                           font=FONTS.mouse_btn, width=6, pady=4)
            lbl.pack(side='left', padx=2)
            self.buttons[code] = lbl

    def update(self, state):
        self.pb_throttle['value'] = ((state.throttle + 1) / 2) * 100
        if abs(state.rudder) > RUDDER_DECAY:
            state.rudder += RUDDER_DECAY if state.rudder < 0 else -RUDDER_DECAY
        rw = self.canvas_rudder.winfo_width()
        rc = rw // 2
        rlen = state.rudder * (rw // 2 - 5)
        self.canvas_rudder.coords(self.rudder_ind, rc, 0, rc + rlen, RUDDER_H)

        for code, widget in self.buttons.items():
            pressed = any(code in p for p in state.pressed_buttons)
            widget.configure(bg=C.ACCENT if pressed else C.SURFACE_OFF,
                             fg=C.TEXT_ON_ACCENT if pressed else C.TEXT_STRONG)
