"""Botones y casillas con el estilo de la GUI.

No empaquetan: cada llamada decide su propio pack(), porque los botones de
la GUI se colocan de formas muy distintas (llenando la fila, a un lado,
con relleno interno).
"""
import tkinter as tk

from frontend.style import colors as C
from frontend.style.fonts import FONTS


def primary_button(parent, text, command=None, font=None, **extra):
    """Botón de acento: la acción principal de una sección."""
    kw = dict(text=text, bg=C.ACCENT, fg=C.TEXT_ON_ACCENT,
              font=font if font is not None else FONTS.label)
    if command is not None:
        kw["command"] = command
    kw.update(extra)
    return tk.Button(parent, **kw)


def secondary_button(parent, text, command=None, **extra):
    """Botón gris: acciones secundarias (descartar, perfiles, filas)."""
    kw = dict(text=text, bg=C.BUTTON_SECONDARY, fg=C.TEXT_STRONG)
    if command is not None:
        kw["command"] = command
    kw.update(extra)
    return tk.Button(parent, **kw)


def checkbox(parent, text, variable, **extra):
    """Casilla sobre el fondo del panel."""
    kw = dict(text=text, variable=variable, bg=C.PANEL, fg=C.TEXT_STRONG,
              selectcolor=C.CHECK_SELECT, activebackground=C.PANEL,
              activeforeground=C.TEXT_STRONG)
    kw.update(extra)
    return tk.Checkbutton(parent, **kw)
