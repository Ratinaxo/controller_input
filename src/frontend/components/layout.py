"""Piezas de diagramación: títulos, separadores, notas y subtítulos.

Son los patrones que más se repetían en la GUI (17 títulos, 14 separadores,
7 notas). Cada función crea el widget, lo empaqueta y lo devuelve.
"""
import tkinter as tk

from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS


def section_header(parent, text, padx=S.PAD_TAB, pady=S.HEADER_PADY, bg=C.PANEL):
    """Título de sección en color de acento."""
    label = tk.Label(parent, text=text, bg=bg, fg=C.ACCENT, font=FONTS.section)
    label.pack(anchor='w', padx=padx, pady=pady)
    return label


def divider(parent, padx=S.PAD_TAB, pady=S.SECTION_GAP):
    """Línea horizontal de 1 px entre secciones."""
    line = tk.Frame(parent, bg=C.DIVIDER, height=1)
    line.pack(fill='x', padx=padx, pady=pady)
    return line


def note(parent, text="", padx=S.PAD_TAB, pady=S.NOTE_PADY, fg=C.TEXT_MUTED,
         wrap=True, pack=True):
    """Texto explicativo pequeño y gris.

    `wrap=True` marca la etiqueta para el auto-ajuste al ancho de la pestaña
    (ver spacing.WRAP_MARKER). `pack=False` la devuelve sin empaquetar, para
    las que se empaquetan después con otros argumentos.
    """
    kw = dict(text=text, bg=C.PANEL, fg=fg, font=FONTS.note, justify='left')
    if wrap:
        kw["wraplength"] = S.WRAP_MARKER
    label = tk.Label(parent, **kw)
    if pack:
        label.pack(anchor='w', padx=padx, pady=pady)
    return label


def subtitle(parent, text, padx=S.PAD_TAB, pady=(8, 0)):
    """Subtítulo dentro de una sección."""
    label = tk.Label(parent, text=text, bg=C.PANEL, fg=C.TEXT_SUBTLE, font=FONTS.note)
    label.pack(anchor='w', padx=padx, pady=pady)
    return label


def field_label(parent, text, padx=S.PAD_TAB):
    """Etiqueta blanca sobre un campo (combobox de dispositivos, modelo)."""
    label = tk.Label(parent, text=text, bg=C.PANEL, fg=C.TEXT_STRONG)
    label.pack(anchor='w', padx=padx)
    return label
