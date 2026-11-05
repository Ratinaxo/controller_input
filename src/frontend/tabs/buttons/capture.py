"""Captura de teclas para asignar botones, sin Tk.

La lógica de «pulsa una tecla para asignarla» no necesita ventana: se
prueba directamente. La pestaña solo muestra lo que esta clase decide.
"""
import queue

from evdev import ecodes

from utils.controllers import code_name

# Teclas que el motor usa para pausa y clutch: no se pueden asignar.
RESERVED_KEYS = {
    ecodes.KEY_CAPSLOCK: "Bloq Mayús (pausa)",
    ecodes.KEY_LEFTALT: "Alt Izquierdo (clutch del mouse)",
}
# Teclas que forman parte de atajos del motor (Alt+P, Alt+coma): se pueden
# asignar, pero se avisa.
SHORTCUT_KEYS = {
    ecodes.KEY_P: "Alt+P (volver a la configuración)",
    ecodes.KEY_COMMA: "Alt+, (recentrar)",
    86: "Alt+< (recentrar)",
    43: "Alt+< (recentrar)",
    ecodes.KEY_RIGHTALT: "Alt+P / Alt+, (atajos)",
    ecodes.KEY_LEFTMETA: "Super+, (recentrar)",
    ecodes.KEY_RIGHTMETA: "Super+, (recentrar)",
}


class ButtonCapture:
    """Mapa botón -> código físico, captura en curso y teclas apretadas.

    button_map:      {id de botón del perfil (str): código evdev}
    labels:          {id de botón: nombre para mostrar}
    capture_id:      botón que está esperando una tecla, o None
    capture_started: instante en que empezó la captura (descarta eventos
                     anteriores, como el propio clic sobre «Asignar»)
    physical_down:   códigos físicos apretados ahora mismo
    """

    def __init__(self, button_map=None, input_queue=None):
        self.button_map = dict(button_map or {})
        self.labels = {}
        self.capture_id = None
        self.capture_started = 0.0
        self.physical_down = set()
        self.queue = input_queue if input_queue is not None else queue.Queue()

    def label(self, bid):
        return self.labels.get(bid, f"Botón {bid}")

    def start(self, bid, now):
        """Empieza a escuchar para `bid`. Devuelve el texto de estado."""
        # Se descartan los eventos que ya estaban en cola (por ejemplo, el
        # propio clic sobre «Asignar») antes de empezar a escuchar.
        self.drain(allow_capture=False)
        self.capture_id = bid
        self.capture_started = now
        return f"Pulsa la tecla o el botón del mouse para «{self.label(bid)}»… (Esc cancela)"

    def clear(self, bid):
        self.button_map.pop(bid, None)
        if self.capture_id == bid:
            self.capture_id = None

    def assign(self, bid, code):
        """Asigna `code` al botón `bid`. Devuelve (ok, mensaje)."""
        if code == ecodes.KEY_ESC:
            return False, "Asignación cancelada."
        if code in RESERVED_KEYS:
            return False, f"{code_name(code, ecodes)} está reservada: {RESERVED_KEYS[code]}. Elige otra."

        notes = []
        for other, c in list(self.button_map.items()):
            if c == code and other != bid:
                del self.button_map[other]
                notes.append(f"estaba asignada a «{self.label(other)}» y se movió")
        self.button_map[bid] = code
        if code in SHORTCUT_KEYS:
            notes.append(f"ojo: también es parte del atajo {SHORTCUT_KEYS[code]}")
        msg = f"«{self.label(bid)}» ← {code_name(code, ecodes)}"
        if notes:
            msg += " (" + "; ".join(notes) + ")"
        return True, msg

    def handle_raw_key(self, code, value, ts, allow_capture=True):
        """Procesa un evento crudo. Devuelve (ok, mensaje) si resolvió una
        captura, o None si no hubo nada que mostrar."""
        if value == 1:
            self.physical_down.add(code)
        else:
            self.physical_down.discard(code)

        if not allow_capture or self.capture_id is None or value != 1:
            return None
        if ts and ts < self.capture_started:
            return None  # evento anterior al inicio de la captura

        ok, msg = self.assign(self.capture_id, code)
        if ok or code == ecodes.KEY_ESC:
            self.capture_id = None
        return ok, msg

    def drain(self, allow_capture=True):
        """Procesa todo lo que hay en la cola. Devuelve (hubo_eventos,
        último (ok, mensaje) o None)."""
        changed = False
        last = None
        while True:
            try:
                code, value, ts = self.queue.get_nowait()
            except queue.Empty:
                break
            result = self.handle_raw_key(code, value, ts, allow_capture)
            if result is not None:
                last = result
            changed = True
        return changed, last
