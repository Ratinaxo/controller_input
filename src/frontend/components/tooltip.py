"""Tooltips y el icono [?] de ayuda.

El texto se pasa directamente: cada pestaña es dueña de sus textos de ayuda
(tabs/*/help.py), en vez de un diccionario global.
"""
import tkinter as tk

from frontend.style import colors as C
from frontend.style.fonts import FONTS

TOOLTIP_DELAY_MS = 300   # espera para no molestar si pasas el mouse rápido


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None

        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self._unschedule()
        self.id = self.widget.after(TOOLTIP_DELAY_MS, self._show)

    def leave(self, event=None):
        self._unschedule()
        self._hide()

    def _unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def _show(self):
        if not self.widget.winfo_exists():
            return

        # Posición ligeramente desplazada del mouse.
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 30
        y = y + self.widget.winfo_rooty() + 20

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)          # sin bordes del sistema
        tw.wm_geometry(f"+{x}+{y}")

        # Contenedor con borde.
        main_frame = tk.Frame(tw, bg=C.TOOLTIP_BG, highlightthickness=1,
                              highlightbackground=C.DIVIDER)
        main_frame.pack()

        # Franja lateral de acento.
        accent_strip = tk.Frame(main_frame, bg=C.ACCENT, width=3)
        accent_strip.pack(side='left', fill='y')

        label = tk.Label(main_frame, text=self.text, justify='left',
                         background=C.TOOLTIP_BG, fg=C.TEXT,
                         relief='flat', borderwidth=0,
                         font=FONTS.body, padx=10, pady=8)
        label.pack(side='left')

    def _hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


def help_icon(parent, text):
    """Icono [?] que muestra `text` al pasar el mouse. No se empaqueta."""
    icon = tk.Label(parent, text="?", bg=C.SURFACE_OFF, fg=C.TEXT_SUBTLE,
                    font=FONTS.mono_bold, width=3, cursor="hand2")

    def on_enter(e):
        icon.config(bg=C.ACCENT, fg=C.TEXT_ON_ACCENT)

    def on_leave(e):
        icon.config(bg=C.SURFACE_OFF, fg=C.TEXT_SUBTLE)

    icon.bind("<Enter>", on_enter, add="+")
    icon.bind("<Leave>", on_leave, add="+")
    ToolTip(icon, text)
    return icon
