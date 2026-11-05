"""Ventanas superpuestas del HUD: semitransparentes, siempre encima y
arrastrables con el mouse."""
from frontend.style import colors as C

OVERLAY_ALPHA = 0.6


def configure_overlay(window):
    """Configuración común para ventanas transparentes, adaptada a Linux/Wayland."""
    window.attributes('-topmost', True)
    window.attributes('-alpha', OVERLAY_ALPHA)

    window.overrideredirect(False)
    try:
        window.attributes('-type', 'normal')
    except Exception:
        pass

    try:
        # En los sistemas que lo soportan, el fondo negro se vuelve transparente.
        window.wm_attributes('&transparentcolor', C.HUD_TRANSPARENT)
    except Exception:
        pass


class Draggable:
    """Hace que la ventana de `widget` se pueda arrastrar con el clic izquierdo."""

    def __init__(self, widget):
        self.x = 0
        self.y = 0
        widget.bind("<Button-1>", self.start_move)
        widget.bind("<B1-Motion>", self.do_move)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        window = event.widget.winfo_toplevel()
        window.geometry(f"+{window.winfo_x() + deltax}+{window.winfo_y() + deltay}")

