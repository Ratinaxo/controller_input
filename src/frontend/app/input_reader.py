"""Lectura cruda de mouse y teclado (evdev) para el preview y la captura
de botones. No hace grab(): el sistema sigue recibiendo los eventos."""
import threading

from evdev import InputDevice, ecodes

from backend.motor import find_input_devices

# Botones del mouse -> etiquetas del panel RAW INPUTS
EVDEV_BUTTON_MAP = {
    ecodes.BTN_LEFT: "Button.left",
    ecodes.BTN_RIGHT: "Button.right",
    ecodes.BTN_MIDDLE: "Button.middle",
    ecodes.BTN_SIDE: "Button.x1",
    ecodes.BTN_EXTRA: "Button.x2",
}

THROTTLE_PER_WHEEL_STEP = 0.05
RUDDER_PER_WHEEL_STEP = 0.2


class InputState:
    """Lo que los hilos de evdev dejan para el hilo de Tk.

    El desplazamiento del stick (dx, dy) se acota a ±hard, igual que en el
    motor de vuelo (ver physics.rs); lo protege `lock` porque lo escriben
    los hilos y lo lee el lazo de la GUI. Gases, timón y botones son
    valores simples que se leen sin lock.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.dx = 0.0
        self.dy = 0.0
        self.hard = 350.0
        self.throttle = 0.0
        self.rudder = 0.0
        self.pressed_buttons = set()
        self.running = True

    def move(self, code, value):
        with self.lock:
            h = self.hard
            if code == ecodes.REL_X:
                self.dx = max(-h, min(h, self.dx + value))
            else:
                self.dy = max(-h, min(h, self.dy + value))

    def scroll(self, dx=0, dy=0):
        if dy != 0:
            self.throttle = max(min(self.throttle + dy * THROTTLE_PER_WHEEL_STEP, 1.0), -1.0)
        if dx != 0:
            self.rudder = max(min(self.rudder + dx * RUDDER_PER_WHEEL_STEP, 1.0), -1.0)

    def click(self, button, pressed):
        if pressed:
            self.pressed_buttons.add(button)
        else:
            self.pressed_buttons.discard(button)

    def recenter_stick(self):
        with self.lock:
            self.dx = 0.0
            self.dy = 0.0


class InputReader:
    """Abre mouse y teclado y los lee en dos hilos."""

    def __init__(self, state, input_queue):
        self.state = state
        self.queue = input_queue
        self.mouse_dev = None
        self.kb_dev = None

    def start(self, config):
        mouse_path, kb_path = find_input_devices(config)
        if mouse_path:
            try:
                self.mouse_dev = InputDevice(mouse_path)
                threading.Thread(target=self._mouse_loop, daemon=True).start()
                print(f"[GUI] Preview de mouse vía evdev: {mouse_path}")
            except Exception as e:
                print(f"[GUI ERROR] No se pudo abrir el mouse por evdev: {e}")
        else:
            print("[GUI ERROR] No se encontró un mouse compatible para el preview.")

        if kb_path and kb_path != mouse_path:
            try:
                self.kb_dev = InputDevice(kb_path)
                threading.Thread(target=self._kb_loop, daemon=True).start()
                print(f"[GUI] Teclado vía evdev (para asignar botones): {kb_path}")
            except Exception as e:
                print(f"[GUI ERROR] No se pudo abrir el teclado por evdev: {e}")

    def close(self):
        self.state.running = False
        for dev in (self.mouse_dev, self.kb_dev):
            if dev:
                try:
                    dev.close()
                except Exception:
                    pass

    def _mouse_loop(self):
        """Hilo dedicado: lee el mouse crudo (evdev) sin hacer grab()."""
        try:
            for ev in self.mouse_dev.read_loop():
                if not self.state.running:
                    break
                if ev.type == ecodes.EV_REL:
                    if ev.code in (ecodes.REL_X, ecodes.REL_Y):
                        self.state.move(ev.code, ev.value)
                    elif ev.code == ecodes.REL_WHEEL:
                        self.state.scroll(dx=0, dy=ev.value)
                    elif ev.code == ecodes.REL_HWHEEL:
                        self.state.scroll(dx=ev.value, dy=0)
                elif ev.type == ecodes.EV_KEY and ev.value in (0, 1):
                    if ev.code in EVDEV_BUTTON_MAP:
                        self.state.click(EVDEV_BUTTON_MAP[ev.code], ev.value == 1)
                    self.queue.put((ev.code, ev.value, ev.timestamp()))
        except OSError:
            pass  # dispositivo desconectado / cerrado al salir
        except Exception as e:
            print(f"[GUI] Preview de mouse detenido: {e}")

    def _kb_loop(self):
        """Hilo dedicado: lee el teclado crudo (evdev) sin hacer grab()."""
        try:
            for ev in self.kb_dev.read_loop():
                if not self.state.running:
                    break
                if ev.type == ecodes.EV_KEY and ev.value in (0, 1):
                    self.queue.put((ev.code, ev.value, ev.timestamp()))
        except OSError:
            pass
        except Exception as e:
            print(f"[GUI] Lectura de teclado detenida: {e}")
