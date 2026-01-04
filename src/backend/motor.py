import time
import math
import keyboard
import rust_motor 
from evdev import InputDevice, list_devices, ecodes
from utils.config import load_config
import sys
from backend.inputs import InputPhysics
from backend.tracker import HeadTracker
from frontend.hud import JoystickHUD

class JoystickBackend:
    def __init__(self, config):
        self.config = config
        
        import pyautogui
        self.screen_w, self.screen_h = pyautogui.size()
        
        self.virtual_x = self.screen_w // 2
        self.virtual_y = self.screen_h // 2
        self.center_x = self.screen_w // 2
        self.center_y = self.screen_h // 2
        
        self.hard_limit = config['radius'] + config['outer']
        self.throttle = 0.0 
        self.rudder = 0.0   
        self.last_rudder_time = 0 
        
        # --- ESTADO DE BOTONES ---
        self.btn_trigger = False # Click Izquierdo
        self.btn_thumb = False   # Click Derecho
        self.btn_top = False     # Click Central
        
        # --- NUEVOS BOTONES ---
        self.btn_side1 = False   # Botón Lateral (Atrás)
        self.btn_side2 = False   # Botón Lateral (Adelante)
        
        self.rust_joy = None 
        self.mouse_dev = None 
        self.tracker = None
        self.hud = None 

    def find_mouse_device(self):
        # ... (Tu código de búsqueda mejorado que ya funciona, NO LO CAMBIES) ...
        # (Copia el método find_mouse_device que te di en el mensaje anterior)
        print("\n--- BUSCANDO MOUSE FÍSICO (FILTRADO ESTRICTO) ---", flush=True)
        try:
            paths = list_devices()
            devices = [InputDevice(path) for path in paths]
        except OSError: return None
        
        candidates = []
        for dev in devices:
            caps = dev.capabilities()
            if ecodes.EV_REL not in caps: continue
            rel_props = caps[ecodes.EV_REL]
            if ecodes.REL_X not in rel_props or ecodes.REL_Y not in rel_props: continue
            if ecodes.EV_KEY in caps and ecodes.BTN_LEFT in caps[ecodes.EV_KEY]:
                candidates.append(dev)

        if not candidates: 
            print("❌ No se encontraron mouses con ejes X/Y.", flush=True)
            return None
        
        best = None
        for dev in candidates:
            n = dev.name.lower()
            if "virtual" in n or "rust" in n: continue
            if "razer" in n:
                best = dev
                break
            if "logitech" in n and best is None: best = dev
            if "mouse" in n and best is None: best = dev

        if best is None and candidates: best = candidates[0]
        if best: print(f"✅ SELECCIONADO PARA SECUESTRO: {best.name}", flush=True)
        return best

    def run(self):
        try: 
            print("[MOTOR] Iniciando dispositivo virtual Rust...", flush=True)
            self.rust_joy = rust_motor.RustJoystick() 
        except Exception as e:
            print(f"[ERROR] Fallo en motor Rust: {e}", flush=True)
            return "EXIT"

        self.mouse_dev = self.find_mouse_device()
        if not self.mouse_dev:
            print("[ERROR] No se encontró mouse válido.", flush=True)
            time.sleep(2)
            return "EXIT"
        
        try:
            self.mouse_dev.grab() 
            print(f"[MOTOR] Mouse {self.mouse_dev.name} SECUESTRADO exitosamente.", flush=True)
        except Exception as e:
            print(f"[ERROR] No se pudo capturar mouse: {e}", flush=True)
            return "RESTART"

        try: self.hud = JoystickHUD(self.config['radius'])
        except: pass

        print("[MOTOR] Iniciando Head Tracker...", flush=True)
        self.tracker = HeadTracker(source=0, config=self.config, show_debug=False) 
        
        print(f"\n--- VUELO INICIADO (MOTOR RUST ACTIVO) ---", flush=True)
        
        try:
            while True:
                if keyboard.is_pressed('alt') and keyboard.is_pressed('p'): return "RESTART"

                if (keyboard.is_pressed('alt') or keyboard.is_pressed('windows')) and \
                   (keyboard.is_pressed('<') or keyboard.is_pressed('|') or keyboard.is_pressed('\\')):
                    self.virtual_x = self.center_x
                    self.virtual_y = self.center_y
                    self.rudder = 0.0 
                    if self.tracker: self.tracker.recenter()

                # --- LECTURA DE EVENTOS ---
                while True:
                    try: event = self.mouse_dev.read_one()
                    except OSError: return "EXIT"
                    if event is None: break 
                    
                    if event.type == ecodes.EV_REL:
                        if event.code == ecodes.REL_X: self.virtual_x += event.value
                        elif event.code == ecodes.REL_Y: self.virtual_y += event.value
                        elif event.code == ecodes.REL_WHEEL:
                            self.throttle = max(min(self.throttle + (event.value * 0.05), 1.0), -1.0)
                        elif event.code == ecodes.REL_HWHEEL:
                            self.last_rudder_time = time.time()
                            self.rudder = max(min(self.rudder + (event.value * 0.20), 1.0), -1.0)
                    
                    # --- AQUÍ AÑADIMOS LOS NUEVOS BOTONES ---
                    elif event.type == ecodes.EV_KEY:
                        is_pressed = (event.value > 0)
                        if event.code == ecodes.BTN_LEFT: self.btn_trigger = is_pressed
                        elif event.code == ecodes.BTN_RIGHT: self.btn_thumb = is_pressed
                        elif event.code == ecodes.BTN_MIDDLE: self.btn_top = is_pressed
                        
                        # Botones laterales (Suelen ser estos códigos)
                        elif event.code == ecodes.BTN_SIDE: self.btn_side1 = is_pressed
                        elif event.code == ecodes.BTN_EXTRA: self.btn_side2 = is_pressed

                # Límites y Física
                self.virtual_x = max(min(self.virtual_x, self.screen_w), 0)
                self.virtual_y = max(min(self.virtual_y, self.screen_h), 0)

                if (time.time() - self.last_rudder_time) > 0.15:
                    if abs(self.rudder) > 0.01:
                        self.rudder -= math.copysign(0.04, self.rudder)
                    else: self.rudder = 0.0

                delta_x = self.virtual_x - self.center_x
                delta_y = self.virtual_y - self.center_y
                
                axis_limit = self.hard_limit
                
                clamped_x = False
                clamped_y = False

                if abs(delta_x) > axis_limit:
                    delta_x = math.copysign(axis_limit, delta_x)
                    self.virtual_x = int(self.center_x + delta_x)
                    clamped_x = True
                
                if abs(delta_y) > axis_limit:
                    delta_y = math.copysign(axis_limit, delta_y)
                    self.virtual_y = int(self.center_y + delta_y)
                    clamped_y = True

                final_x, final_y, stats = InputPhysics.calculate(delta_x, delta_y, self.config)

                head_yaw, head_pitch = (0.0, 0.0)
                if self.tracker and self.tracker.running:
                    head_yaw, head_pitch = self.tracker.get_axes()

                stats['at_limit'] = clamped_x or clamped_y
                
                # --- ENVIAR A RUST (AHORA CON 5 BOTONES) ---
                self.rust_joy.update(
                    final_x, final_y, self.throttle, self.rudder, 
                    head_yaw, head_pitch,
                    self.btn_trigger, self.btn_thumb, self.btn_top,
                    self.btn_side1, self.btn_side2 
                )

                # --- ACTUALIZAR HUD (NUEVO FORMATO) ---
                if self.hud:
                    self.hud.update(
                        final_x, final_y,       # Stick
                        self.throttle,          # Gases
                        self.rudder,            # Timón
                        head_yaw, head_pitch,   # Tracker (NUEVO)
                        stats['in_deadzone'],   # Flags
                        stats['is_snapped']
                    )
                
                time.sleep(0.005)

        except Exception as e:
            import traceback
            print("\n[MOTOR CRASH] DETECTADO:", flush=True)
            traceback.print_exc()
            time.sleep(5)
            return "EXIT"
            
        except KeyboardInterrupt:
            return "EXIT"

    def cleanup(self):
        print("[MOTOR] Liberando recursos...", flush=True)
        if self.tracker: 
            self.tracker.stop()
            self.tracker = None
        if self.mouse_dev:
            try: self.mouse_dev.ungrab()
            except: pass
            self.mouse_dev = None
        if self.hud:
            try: self.hud.close()
            except: pass
            self.hud = None
        self.rust_joy = None
        print("[MOTOR] Limpieza completada.", flush=True)