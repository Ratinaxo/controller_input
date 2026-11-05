"""Constantes y estilos de la GUI: la única fuente de verdad visual.

    from frontend.style import colors as C, FONTS, spacing as S
    tk.Label(parent, bg=C.PANEL, fg=C.TEXT_MUTED, font=FONTS.note)

Ningún archivo fuera de este paquete debería escribir un color o una
fuente literal.
"""
from frontend.style import colors, spacing
from frontend.style.fonts import FONTS, resolve_fonts
from frontend.style.ttk_theme import apply_theme

__all__ = ["colors", "spacing", "FONTS", "resolve_fonts", "apply_theme"]
