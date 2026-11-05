"""Paleta de la GUI y del HUD. Única fuente de verdad de los colores.

Los nombres son SEMÁNTICOS: dicen para qué se usa el color, no qué color
es. Por eso algunos valores se repiten (DIVIDER y BUTTON_SECONDARY son el
mismo gris): hoy coinciden, pero son decisiones distintas y tienen que
poder cambiar por separado.

Los valores partieron siendo exactamente los que tenía el código antes del
refactor; tests/golden/gui_tree.json lo verifica. Cambiar uno es una
decisión visual y regenera ese golden a propósito — como el cambio de
AXIS_LATERAL/AXIS_DEPTH de la Fase 6 (un color, un significado).
"""

# --- Superficies -----------------------------------------------------------
BG = "#1e1e1e"                  # fondo de la ventana
PANEL = "#2d2d2d"               # fondo de pestañas y tarjetas
CANVAS = "#000000"              # fondo de los previews
SURFACE_OFF = "#333333"         # indicador inactivo (filas, botones del mouse)
INPUT_BG = "#111111"            # caja numérica del slider
TOOLTIP_BG = "#252526"
CHECK_SELECT = "#222222"        # selectcolor de las casillas
CODE_BG = "#222222"             # fondo de la tecla asignada en Botones

# --- Líneas y rieles -----------------------------------------------------------
DIVIDER = "#444444"             # separador entre secciones
BORDER = "#333333"              # borde de canvas y de barras de ejes
GRID = "#222222"                # cruz central y fondo del gráfico de curva
TROUGH = "#404040"              # riel del slider
TROUGH_OFF = "#2a2a2a"          # riel del slider deshabilitado
DEADZONE_FILL = "#2a2a2a"       # zona muerta en el gráfico de curva
TAB_BG = "#333333"              # pestaña no seleccionada (ttk)

# --- Texto -------------------------------------------------------------------
TEXT = "#e0e0e0"                # texto normal
TEXT_STRONG = "#ffffff"         # blanco puro (etiquetas y botones secundarios)
TEXT_SUBTLE = "#aaaaaa"         # subtítulos y lecturas en vivo
TEXT_MUTED = "#888888"          # notas y etiquetas secundarias
TEXT_DISABLED = "#666666"
TEXT_ON_ACCENT = "#000000"      # texto sobre botones de acento

# --- Estado y acciones ---------------------------------------------------------
ACCENT = "#00e676"
WARN = "#ff3d00"
CAPTURE = "#ffb300"             # esperando una tecla / manteniendo posición
INACTIVE = "#555555"            # punto en zona muerta o fuente externa
BUTTON_SECONDARY = "#444444"
AXIS_CENTER = "#555555"         # línea de cero de las barras de ejes

# --- Ejes: la MISMA paleta en el preview y en el HUD ---------------------------
# LATERAL y DEPTH tenían el mismo color que THROTTLE/STICK_SNAPPED (cian) y
# RUDDER/RUDDER_PREVIEW (magenta). En vuelo se mira el HUD del stick y el de
# la cabeza a la vez, así que un cian o un magenta no decían por sí solos si
# se trataba de gases, de un eje pegado, del timón o de la traslación de la
# cabeza. Se eligieron azul y violeta porque no aparecen en ningún otro
# nombre de este archivo (Fase 6 del plan de refactor).
AXIS_LATERAL = "#3399ff"
AXIS_VERTICAL = "#ffff00"
AXIS_DEPTH = "#aa66ff"
AXIS_ROLL = "#88ff88"

# --- Preview del configurador ------------------------------------------------
RUDDER_PREVIEW = "#ff00ff"      # barra del timón en RAW INPUTS

# --- HUD de vuelo ------------------------------------------------------------
HUD_BG = "#000000"              # fondo de las ventanas del HUD
# Color que el compositor vuelve transparente. Tiene que ser el mismo que
# HUD_BG; va por nombre porque así lo espera el atributo de Tk.
HUD_TRANSPARENT = "black"
HUD_HEAD = "#00ff00"            # cruz, texto y punto de la cabeza
HUD_FRAME = "#ffffff"           # contornos y textos del HUD del stick
HUD_TICK = "#808080"            # marca central de gases y timón
HUD_GUIDE = "#444444"           # cuadrado punteado del recorrido del stick
STICK_INITIAL = "#ff0000"       # color del punto antes del primer update
STICK_OUTLINE = "#ffffff"
STICK_NORMAL = "#ff8800"
STICK_SNAPPED = "#00ffff"
STICK_SATURATED = "#ff0000"
STICK_DEADZONE = "#555555"
THROTTLE = "#00ffff"
THROTTLE_WEP = "#ff0000"
THROTTLE_REVERSE = "#ff5555"
RUDDER = "#ff00ff"
