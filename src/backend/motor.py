import time
import rust_motor
import threading
from evdev import InputDevice, list_devices, ecodes
import traceback
import os

from backend.tracker import create_head_source
from frontend.hud import JoystickHUD
from utils.config import load_config
from utils.controllers import load_controller, get_button_entry, resolve_code, DEFAULT_CONTROLLER_ID
from utils.telemetry import CsvLogger


def _registered_virtual_codes():
    """Códigos de botón que registra el joystick virtual (device.rs).
    Devuelve None si el módulo Rust es de una versión sin esta función."""
    fn = getattr(rust_motor, "virtual_button_codes", None)
    if fn is None:
        return None
    try:
        return set(int(c) for c in fn())
    except Exception:
        return None


def check_profile_codes(profile, registered=None):
    """Lista de advertencias para botones del perfil cuyo código no está
    registrado en el dispositivo virtual (el kernel los descartaría en
    silencio)."""
    if registered is None:
        registered = _registered_virtual_codes()
    if registered is None:
        return []
    warnings = []
    for entry in profile.get('buttons', []):
        code = resolve_code(entry.get('code'), ecodes)
        if code is None:
            warnings.append(f"Botón {entry.get('id')}: código '{entry.get('code')}' desconocido.")
        elif code not in registered:
            warnings.append(
                f"Botón {entry.get('id')}: el código {entry.get('code')} ({hex(code)}) no está "
                f"registrado en el joystick virtual; el juego no lo verá."
            )
    return warnings


def build_button_map(config, registered=None):
    """Traduce el 'button_map' guardado en config.json (id de botón del
    perfil -> código evdev físico, de teclado o de mouse) al dict
    {físico: virtual} que espera RustEngine.set_button_map(). Cualquier
    entrada inválida se ignora en vez de romper el arranque del motor."""
    controller_id = config.get('controller_profile', DEFAULT_CONTROLLER_ID)
    raw_map = config.get('button_map', {}) or {}

    if not raw_map:
        return {}

    try:
        profile = load_controller(controller_id)
    except Exception as e:
        print(f"[MOTOR] No se pudo cargar el perfil de mando '{controller_id}': {e}")
        return {}

    if registered is None:
        registered = _registered_virtual_codes()
    for w in check_profile_codes(profile, registered):
        print(f"[MOTOR] ⚠ {w}")

    resolved = {}
    for button_id, physical_code in raw_map.items():
        entry = get_button_entry(profile, button_id)
        if not entry:
            print(f"[MOTOR] Botón {button_id} no existe en el perfil '{controller_id}', se ignora.")
            continue
        virtual_code = resolve_code(entry.get('code'), ecodes)
        if virtual_code is None:
            print(f"[MOTOR] Código '{entry.get('code')}' desconocido para evdev, se ignora.")
            continue
        if registered is not None and virtual_code not in registered:
            print(f"[MOTOR] Botón {button_id}: código virtual {hex(virtual_code)} no registrado, se ignora.")
            continue
        try:
            phys = int(physical_code)
        except (TypeError, ValueError):
            print(f"[MOTOR] Código físico inválido para el botón {button_id}: {physical_code}")
            continue
        if phys in resolved and resolved[phys] != virtual_code:
            print(f"[MOTOR] El código físico {phys} está asignado a más de un botón; se usa el último.")
        resolved[phys] = int(virtual_code)

    return resolved


def list_all_devices():
    """Devuelve todos los dispositivos evdev con nombre y path, para
    poblar el selector manual de la GUI."""
    result = []

    try:
        for path in list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                is_kb = ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]
                is_mouse = ecodes.EV_REL in caps and ecodes.REL_X in caps[ecodes.EV_REL]
                if is_kb or is_mouse:
                    result.append({'path': path, 'name': dev.name, 'is_kb': is_kb, 'is_mouse': is_mouse})
            except Exception:
                continue
    except Exception:
        pass
    return result


def find_input_devices(config=None):
    if not config:
        config = load_config()

    target_mouse_phys = config.get('mouse_phys', '')
    target_kb_phys = config.get('keyboard_phys', '')

    mouse_path = None
    kb_path = None

    print("\n--- BUSCANDO HARDWARE ---", flush=True)

    try:
        device_paths = list_devices()
    except Exception as e:
        print(f"Error al listar dispositivos: {e}")
        return None, None

    for path in device_paths:
        try:
            dev = InputDevice(path)
            phys = dev.phys if dev.phys else "RutaFisicaDesconocida"

            if target_mouse_phys and phys == target_mouse_phys:
                mouse_path = path
                print(f"  [OK] Mouse exacto restaurado: {dev.name} -> {path}")

            if target_kb_phys and phys == target_kb_phys:
                kb_path = path
                print(f"  [OK] Teclado exacto restaurado: {dev.name} -> {path}")
        except Exception:
            continue

    if mouse_path and kb_path:
        return mouse_path, kb_path

    print("  [!] Hardware manual no encontrado o incompleto. Usando Heurística...")

    print("\n--- BUSCANDO HARDWARE (HEURÍSTICA V2) ---", flush=True)

    try:
        device_paths = list_devices()
    except Exception as e:
        print(f"❌ Error al listar dispositivos: {e}")
        return None, None

    gaming_brands = ["razer", "logitech", "corsair", "steelseries", "zowie", "benq"]

    found_mice = []

    for path in device_paths:
        try:
            dev = InputDevice(path)
            n = dev.name.lower()

            if "virtual" in n or "rust" in n or "uinput" in n:
                continue

            caps = dev.capabilities()

            if not kb_path:
                if ecodes.EV_KEY in caps and ecodes.KEY_P in caps[ecodes.EV_KEY]:
                    if "mouse" not in n:
                        kb_path = path
                        print(f"  [OK] Teclado Real: {dev.name} -> {path}")

            if ecodes.EV_REL in caps and ecodes.REL_X in caps[ecodes.EV_REL]:
                if ecodes.EV_KEY in caps and ecodes.BTN_LEFT in caps[ecodes.EV_KEY]:
                    score = 0
                    if any(brand in n for brand in gaming_brands):
                        score += 10
                    if "keyboard" in n or "alloy" in n:
                        score -= 5

                    found_mice.append({
                        'path': path,
                        'name': dev.name,
                        'score': score
                    })

        except Exception:
            continue

    if found_mice:
        found_mice.sort(key=lambda x: x['score'], reverse=True)
        best_mouse = found_mice[0]
        mouse_path = best_mouse['path']
        print(f"  [OK] Mouse Seleccionado: {best_mouse['name']} -> {mouse_path} (Score: {best_mouse['score']})")

        if not kb_path:
            kb_path = mouse_path
            print(f"  [!] Usando mouse como fuente de teclado (Fallback)")

    return mouse_path, kb_path


def _print_axis_order():
    """Imprime el orden de los ejes de cada dispositivo virtual.

    El kernel numera los ejes por código ascendente, no por orden de
    registro, así que esta tabla (que viene de Rust) es el orden real que
    va a ver el juego. Sirve de guía al reasignar los controles."""
    for label, fn_name in (("STICK", "stick_axis_order"), ("CABEZA", "head_axis_order")):
        fn = getattr(rust_motor, fn_name, None)
        if fn is None:
            continue
        try:
            axes = fn()
        except Exception:
            continue
        print(f"[MOTOR] Ejes del dispositivo {label}:", flush=True)
        for i, (name, code) in enumerate(axes):
            print(f"          eje {i}: {name} (0x{code:02x})", flush=True)


class JoystickBackend:
    def __init__(self, config):
        self.config = config

        print(f"[MOTOR] Preparando RustEngine asíncrono...", flush=True)
        self.engine = rust_motor.RustEngine()

        self.engine.update_config(
            float(config['radius']),
            float(config['curve']),
            float(config['deadzone']),
            float(config.get('t_snap_axis', 0.1)),
            float(config.get('snap', 0.05)),
            float(config.get('outer', 0.0))
        )

        button_map = build_button_map(config)
        if button_map:
            print(f"[MOTOR] Mapa de botones cargado: {len(button_map)} botón(es) asignado(s).")
        self.engine.set_button_map(button_map)

        self.tracker = None
        self.hud = None
        self._cleaned_up = False

        # Telemetría opcional: salida del motor Rust muestreada desde el
        # lazo de Python (~100 Hz), para cruzarla con la del tracker.
        self._telemetry = CsvLogger(
            "engine",
            ["t_abs", "hy", "hp", "lx", "ly", "lt", "lr", "in_deadzone", "is_snapped"],
            enabled=bool(config.get('telemetry_enabled', False))
        )

        self._kb_dev = None
        self._pressed_keys = set()
        self._kb_lock = threading.Lock()

        # Estado separado para Pausa (CapsLock - Toggle) y Mouse Release (LeftAlt - Clutch)
        self.is_paused = False
        self._pause_was_pressed = False
        self._last_effective_paused = False
        self._last_mouse_released = False

    def find_devices(self):
        return find_input_devices(self.config)

    def _read_kb_loop(self):
        try:
            for ev in self._kb_dev.read_loop():
                if ev.type == ecodes.EV_KEY:
                    with self._kb_lock:
                        if ev.value == 1:
                            self._pressed_keys.add(ev.code)
                        elif ev.value == 0:
                            self._pressed_keys.discard(ev.code)
        except Exception:
            pass

    def _is_pressed(self, *key_codes):
        with self._kb_lock:
            return any(code in self._pressed_keys for code in key_codes)

    def run(self):
        if os.name == 'posix':
            os.system("stty -echo")

        mouse_path, kb_path = self.find_devices()

        if not mouse_path:
            print("❌ ERROR: No se encontró un Mouse compatible.")
            return "EXIT"
        if not kb_path:
            kb_path = mouse_path
        if kb_path == mouse_path:
            print("[MOTOR] ⚠ No hay teclado propio: se usa el mouse también como fuente de botones.")
            print("[MOTOR] ⚠ Como el mouse se captura en exclusiva, los atajos (ALT+P, Bloq Mayús, "
                  "Alt) NO van a funcionar. Usa Ctrl+C en la terminal para salir.")

        try:
            self._kb_dev = InputDevice(kb_path)
            threading.Thread(target=self._read_kb_loop, daemon=True).start()
        except Exception as e:
            print(f"[MOTOR] No se pudo abrir teclado por evdev: {e}")

        try:
            self.hud = JoystickHUD(self.config['radius'])
        except Exception:
            pass
        self.tracker = create_head_source(self.config, show_debug=False, source=0)

        if self.tracker is None:
            print("[MOTOR] Fuente de cabeza externa: no se crea el dispositivo de cabeza. "
                  "Los ejes los publica OpenTrack; el stick y los botones siguen aquí.",
                  flush=True)
        else:
            _print_axis_order()
            if not self.tracker.running:
                # El dispositivo de cabeza se crea igual, pero sus ejes quedan
                # en cero: el juego no lo va a «detectar» al asignar, porque
                # para eso hay que mover el eje.
                print("[MOTOR] ⚠ El tracker de cabeza NO está leyendo la cámara: el "
                      "dispositivo de cabeza existe pero sus ejes no se van a mover.",
                      flush=True)

        print(f"\n>>> INICIANDO HILO DE ALTO RENDIMIENTO (RUST) <<<", flush=True)
        try:
            # Rust abre los dispositivos y crea el joystick virtual ANTES de
            # lanzar su hilo; cualquier fallo llega aquí como excepción.
            # with_head: el dispositivo de cabeza solo se crea si la fuente
            # es la cámara propia. En modo externo lo publica OpenTrack.
            self.engine.start(str(mouse_path), str(kb_path),
                              with_head=self.tracker is not None)
            print("    [HILO RUST LANZADO EXITOSAMENTE]", flush=True)
        except Exception as e:
            print(f"❌ FATAL: Rust rechazó iniciar: {e}", flush=True)
            self.cleanup()
            return "EXIT"

        print("    [ALT+P] Configurar | [ALT+<] Recentrar", flush=True)

        try:
            while True:
                # --- 1. ATAJOS PRINCIPALES ---
                if self._is_pressed(ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT) and self._is_pressed(ecodes.KEY_P):
                    print("[MOTOR] Solicitando salida...", flush=True)
                    self.engine.request_exit()
                    time.sleep(0.2)
                    return "RESTART"

                try:
                    is_alt_win = (
                        self._is_pressed(ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT) or
                        self._is_pressed(ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA)
                    )
                    is_recenter_key = self._is_pressed(ecodes.KEY_COMMA, 86, 43)

                    if is_alt_win and is_recenter_key:
                        self.engine.recenter()
                        if self.tracker:
                            self.tracker.recenter()
                        print("[MOTOR] Recentrado.", flush=True)
                        time.sleep(0.2)
                except Exception:
                    pass

                if not self.engine.is_running():
                    # El hilo Rust terminó (salida pedida o error): volver a la GUI.
                    print("[MOTOR] El hilo Rust se detuvo.", flush=True)
                    return "RESTART"

                # --- 2. PAUSA (CapsLock Toggle) y CLUTCH MOUSE (LeftAlt) ---
                caps_is_pressed = self._is_pressed(ecodes.KEY_CAPSLOCK)
                if caps_is_pressed and not self._pause_was_pressed:
                    self.is_paused = not self.is_paused
                    if self.is_paused:
                        print("[MOTOR] Sistema PAUSADO (Caps Lock activado).")
                    else:
                        print("[MOTOR] Sistema REANUDADO.")
                self._pause_was_pressed = caps_is_pressed

                mouse_released_by_clutch = self._is_pressed(ecodes.KEY_LEFTALT)
                effective_paused = self.is_paused or mouse_released_by_clutch

                if self.is_paused != self._last_effective_paused:
                    self._last_effective_paused = self.is_paused
                    if self.hud:
                        self.hud.set_visible(not self.is_paused)

                if effective_paused != self._last_mouse_released:
                    self._last_mouse_released = effective_paused
                    try:
                        self.engine.set_paused(effective_paused)
                    except AttributeError:
                        pass

                if effective_paused:
                    time.sleep(0.05)
                    continue

                # --- 3. TRACKER -> RUST ---
                hy, hp = 0.0, 0.0
                head_trans = None
                if self.tracker and self.tracker.running:
                    # get_head_axes() entrega los 6 ejes; si la fuente de
                    # cabeza es una que solo publica rotación, se rellena
                    # con 0, que es el centro de cada eje.
                    getter = getattr(self.tracker, "get_head_axes", None) or self.tracker.get_axes
                    axes = list(getter())
                    axes += [0.0] * (6 - len(axes))
                    hy, hp, hr, htx, hty, htz = (float(v) for v in axes[:6])
                    self.engine.update_tracker(hy, hp, hr, htx, hty, htz)
                    head_trans = (htx, hty, htz)

                # --- 4. RUST -> HUD / TELEMETRÍA ---
                if self.hud or self._telemetry.enabled:
                    lx, ly, lt, lr, snap, dead = self.engine.get_hud_data()
                    if self.hud:
                        self.hud.update(lx, ly, lt, lr, hy, hp, dead, snap,
                                        head_trans=head_trans)
                    self._telemetry.log({
                        "t_abs": time.time(),
                        "hy": hy, "hp": hp,
                        "lx": lx, "ly": ly, "lt": lt, "lr": lr,
                        "in_deadzone": dead, "is_snapped": snap,
                    })

                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\n[MOTOR] Interrupción (Ctrl+C)", flush=True)
            return "EXIT"
        except Exception as e:
            print(f"\n[MOTOR ERROR] {e}", flush=True)
            traceback.print_exc()
            return "EXIT"
        finally:
            self.cleanup()

    def cleanup(self):
        # Idempotente: run() la llama en su finally y motor_app.py otra vez.
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if os.name == 'posix':
            os.system("stty echo")
        self._telemetry.close()
        if self.engine:
            self.engine.stop()
        if self.tracker:
            self.tracker.stop()
        if self.hud:
            try:
                self.hud.close()
            except Exception:
                pass
