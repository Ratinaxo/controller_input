"""Tema global de los widgets ttk (pestañas, paneles)."""
from tkinter import ttk

from frontend.style import colors as C
from frontend.style.fonts import FONTS


def apply_theme():
    """Configura el tema global de TTK. Se llama una vez, con la ventana ya
    creada y antes de construir el layout."""
    style = ttk.Style()
    style.theme_use('clam')

    # Notebook (pestañas)
    style.configure("TNotebook", background=C.BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=C.TAB_BG, foreground=C.TEXT_STRONG,
                    padding=[15, 5], font=FONTS.label, borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", C.PANEL)],
              foreground=[("selected", C.ACCENT)])

    # Frames y barras
    style.configure("Card.TFrame", background=C.PANEL, relief="flat")

    # Panel dividido de la ventana principal
    style.configure("Main.TPanedwindow", background=C.BG)
    return style
