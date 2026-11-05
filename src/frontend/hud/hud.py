"""HUD de vuelo: dos ventanas superpuestas que abre el motor."""
import tkinter as tk

from frontend.hud.head_window import HeadWindow
from frontend.hud.overlay import configure_overlay
from frontend.hud.stick_window import StickWindow
from frontend.style import resolve_fonts
from utils.display import get_screen_size


class JoystickHUD:
    """Stick (abajo a la derecha) y cabeza (abajo a la izquierda).

    `radius_px` se acepta por compatibilidad con motor.py, pero el dibujo
    usa un radio fijo (spacing.HUD_STICK_RADIUS): el HUD muestra la salida
    normalizada -1..1, no píxeles del mouse.
    """

    def __init__(self, radius_px=None):
        self.screen_w, self.screen_h = get_screen_size()

        # --- Ventana 1: stick ---
        self.root = tk.Tk()
        # El HUD corre en el proceso del motor, aparte de la GUI: tiene que
        # resolver sus propias familias, antes de construir ningún widget
        # (Fase 6, «fuentes con respaldo»).
        resolve_fonts(self.root)
        self.root.title("Stick HUD")
        configure_overlay(self.root)
        self.stick = StickWindow(self.root, self.screen_w, self.screen_h)

        # --- Ventana 2: cabeza ---
        self.win_tracker = tk.Toplevel(self.root)
        self.win_tracker.title("Head HUD")
        configure_overlay(self.win_tracker)
        self.head = HeadWindow(self.win_tracker, self.screen_h)

    def update(self, x_norm, y_norm, throttle_val, rudder_val, head_yaw, head_pitch,
               is_deadzone, is_snapped, head_trans=None):
        """
        x_norm, y_norm:         -1..1 (stick)
        head_yaw, head_pitch:   -1..1 (cabeza)
        head_trans:             (tx, ty, tz) en -1..1, o None si la fuente de
                                cabeza no publica traslación (barras a cero)
        """
        self.stick.update(x_norm, y_norm, throttle_val, rudder_val, is_deadzone, is_snapped)
        self.head.update(head_yaw, head_pitch, head_trans)
        self.root.update()

    def set_visible(self, visible):
        """Oculta o muestra las dos ventanas (pausa)."""
        if visible:
            self.root.deiconify()
            self.win_tracker.deiconify()
        else:
            self.root.withdraw()
            self.win_tracker.withdraw()

    def close(self):
        try:
            self.win_tracker.destroy()
            self.root.destroy()
        except Exception:
            pass
