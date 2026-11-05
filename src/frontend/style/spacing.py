"""Márgenes y tamaños fijos de la GUI y del HUD."""

# Margen lateral de las pestañas. Sistema usaba 20 y las demás 15, sin
# ninguna razón para que su margen fuera distinto al del resto -- se
# unificó a 15 (Fase 6, «un solo margen»).
PAD_TAB = 15

SPACE_XS, SPACE_S, SPACE_M, SPACE_L = 2, 5, 8, 10

SECTION_GAP = 10               # pady del separador entre secciones
HEADER_PADY = (5, 5)           # título de sección
NOTE_PADY = (0, 8)             # nota bajo un título
SLIDER_ROW_PADY = 2

# Marca para el auto-ajuste de texto: _enable_auto_wrap ajusta al ancho real
# las etiquetas largas y TAMBIÉN las cortas que declaren un wraplength. No es
# un ancho que se use tal cual, pero sin ella una nota corta no se ajusta.
WRAP_MARKER = 400
WRAP_DIALOG_ROTATION = 420
WRAP_DIALOG_TRANSLATION = 440
WRAP_BUTTON_WARNING = 380

# Ventana principal
WINDOW_MAX = (1200, 780)
WINDOW_MIN = (720, 460)
WINDOW_SCREEN_FRACTION = (0.92, 0.88)

# Preview
PREVIEW_SIZE = 250             # canvas del stick (cuadrado)
HEAD_PREVIEW_H = 150           # canvas de yaw/pitch
AXIS_BARS_H = 76               # canvas de barras de traslación y roll
STICK_VIS_SCALE = 70
HEAD_VIS_SCALE = 40
CURVE_GRAPH_H = 100

# Asistentes de calibración
WIZARD_GEOMETRY = {"rotation": "460x300", "translation": "480x330"}
WIZARD_PROGRESS_LENGTH = 320

# HUD
HUD_STICK_SIZE = 260
HUD_STICK_RADIUS = 80
HUD_HEAD_SIZE = 150
HUD_HEAD_SCALE = 50
HUD_TRANS_PANEL_H = 54
HUD_MARGIN = 20
