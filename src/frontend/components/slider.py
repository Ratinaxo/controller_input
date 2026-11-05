"""Slider con caja numérica, y la fila slider + icono de ayuda."""
import tkinter as tk

from frontend.components.tooltip import help_icon
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS


class ModernSlider(tk.Frame):
    """Widget compuesto: etiqueta + slider + caja numérica."""

    def __init__(self, parent, text, from_, to, resolution, initial, command=None):
        super().__init__(parent, bg=C.PANEL)
        self.command = command

        val = float(initial) if initial is not None else from_
        self.var = tk.DoubleVar(value=val)

        self.label = tk.Label(self, text=text, bg=C.PANEL, fg=C.TEXT, font=FONTS.label)
        self.label.pack(anchor='w', padx=5, pady=(5, 0))

        row = tk.Frame(self, bg=C.PANEL)
        row.pack(fill='x', padx=5, pady=5)

        self.scale = tk.Scale(row, from_=from_, to=to, resolution=resolution,
                              variable=self.var, orient='horizontal',
                              bg=C.PANEL, fg=C.TEXT,
                              troughcolor=C.TROUGH, highlightthickness=0,
                              activebackground=C.ACCENT, command=self._on_change,
                              showvalue=False)
        self.scale.pack(side='left', fill='x', expand=True)

        self.entry = tk.Entry(row, textvariable=self.var, width=5,
                              bg=C.INPUT_BG, fg=C.ACCENT, insertbackground=C.TEXT_STRONG,
                              relief="flat", justify="center")
        self.entry.pack(side='right', padx=(10, 0))
        self.entry.bind('<Return>', self._on_entry)

    def _on_change(self, val):
        if self.command:
            self.command()

    def _on_entry(self, event):
        try:
            val = float(self.entry.get())
            self.scale.set(val)
            if self.command:
                self.command()
        except ValueError:
            pass
        self.focus_set()

    def set_enabled(self, enabled):
        """Habilita o atenúa el control. Se usa cuando un parámetro no aplica
        a la configuración actual (por ejemplo, los ajustes del tracker
        cuando la fuente de cabeza es externa)."""
        state = 'normal' if enabled else 'disabled'
        self.scale.config(state=state, fg=C.TEXT if enabled else C.TEXT_DISABLED,
                          troughcolor=C.TROUGH if enabled else C.TROUGH_OFF)
        self.entry.config(state=state, fg=C.ACCENT if enabled else C.TEXT_DISABLED)
        self.label.config(fg=C.TEXT if enabled else C.TEXT_DISABLED)

    def get(self):
        return self.var.get()

    def set(self, val):
        self.var.set(val)


def slider_row(parent, text, min_v, max_v, step, value, help_text, on_change=None):
    """Fila con un ModernSlider y su icono [?]. Devuelve el slider."""
    container = tk.Frame(parent, bg=C.PANEL)
    container.pack(fill='x', padx=S.PAD_TAB, pady=S.SLIDER_ROW_PADY)
    slider = ModernSlider(container, text, min_v, max_v, step, value, on_change)
    slider.pack(side='left', fill='x', expand=True)
    icon = help_icon(container, help_text)
    icon.pack(side='right', padx=(10, 0), anchor='n', pady=5)
    return slider
