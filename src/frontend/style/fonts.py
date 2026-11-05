"""Escala tipográfica por ROL, no por tamaño.

Cada rol es (tamaño, peso). La familia sale de una lista de preferencia:
`resolve_fonts()` elige la primera disponible de cada lista (Fase 6 del
plan: antes se usaba siempre la primera preferencia sin comprobar nada,
así que en Linux, sin "Segoe UI" ni "Consolas" instaladas, Tk sustituía
en silencio por lo que fuera).

Ojo: "Segoe UI" y "Consolas" son fuentes de Windows; por eso la lista
sigue por "Cantarell"/"Noto Sans" (GNOME) y "DejaVu" (casi siempre
presente). Para comprobar qué hay instalado:
    fc-list | grep -iE "segoe|consolas|cantarell|dejavu"

El HUD usaba una tercera lista propia (Arial primero) mientras el resto
de la GUI usaba "Segoe UI": dos familias distintas para el mismo look,
sin ninguna razón para que difieran. Ahora el HUD comparte `UI_FAMILIES`
(Fase 6, «una sola familia»).
"""
from types import SimpleNamespace

UI_FAMILIES = ("Segoe UI", "Cantarell", "Noto Sans", "DejaVu Sans")
MONO_FAMILIES = ("Consolas", "DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono")

UI_SCALE = {
    "title": (16, "bold"),        # "CONFIGURACIÓN DE VUELO"
    "cta": (14, "bold"),          # botón INICIAR VUELO
    "instruction": (13, "bold"),  # instrucción del asistente
    "section": (11, "bold"),      # títulos de sección
    "button_lg": (10, "bold"),    # botón «Marcar» del asistente
    "label": (9, "bold"),         # etiquetas en negrita
    "body": (9, "normal"),        # texto normal
    "note": (8, "normal"),        # notas y subtítulos
    "note_bold": (8, "bold"),
    "micro": (7, "bold"),         # etiquetas de las barras de ejes
}
MONO_SCALE = {
    "mono": (9, "normal"),        # lecturas en vivo y tecla asignada
    "mono_bold": (9, "bold"),     # el [?] de ayuda
}
HUD_SCALE = {
    "hud_label": (8, "bold"),     # THR, RUDDER
    "hud_small": (7, "bold"),     # HEAD
    "hud_micro": (6, "bold"),     # etiquetas de las barras de traslación
    "mouse_btn": (8, "normal"),   # botones L/R/M del preview
}


def _build(ui_family, mono_family):
    # El HUD comparte la familia de la UI (Fase 6): antes tenía la suya
    # propia y terminaba con una tipografía distinta al resto sin motivo.
    roles = {}
    for name, (size, weight) in UI_SCALE.items():
        roles[name] = (ui_family, size, weight)
    for name, (size, weight) in MONO_SCALE.items():
        roles[name] = (mono_family, size, weight)
    for name, (size, weight) in HUD_SCALE.items():
        roles[name] = (ui_family, size, weight)
    return roles


# Tuplas listas para usar: font=FONTS.section
FONTS = SimpleNamespace(**_build(UI_FAMILIES[0], MONO_FAMILIES[0]))


def pick_family(preferences, available):
    """Primera familia de `preferences` que esté en `available` (sin
    distinguir mayúsculas). Si ninguna está, la primera de la lista: Tk
    hará su propio reemplazo, como hasta ahora."""
    lower = {a.lower() for a in available}
    for family in preferences:
        if family.lower() in lower:
            return family
    return preferences[0]


def resolve_fonts(root):
    """Elige la familia disponible de cada lista y actualiza FONTS.

    Se llama UNA vez, después de crear tk.Tk() y ANTES de construir
    cualquier widget: Tk evalúa la tupla de fuente al crear el widget. El
    HUD vive en otro proceso (el motor) y tiene que llamarla por su cuenta.
    """
    from tkinter import font as tkfont
    available = tkfont.families(root)
    roles = _build(pick_family(UI_FAMILIES, available),
                   pick_family(MONO_FAMILIES, available))
    for name, value in roles.items():
        setattr(FONTS, name, value)
    return FONTS
