import time
import keyboard
import rust_motor 
from evdev import InputDevice, list_devices, ecodes
from utils.config import load_config
import sys
import traceback
import pyautogui

from backend.tracker import HeadTracker
from frontend.hud import JoystickHUD

class JoystickBackend:
    def __init__(self, config):
        self.config = config
        self.screen_w, self.screen_h = pyautogui.size()
        
        # 1. Instanciamos el Motor Multihilo de Rust
        print(f"[MOTOR] Preparando RustEngine asíncrono...", flush=True)
        self.engine = rust_motor.RustEngine()
        
        # Actualizamos config inicial en Rust
        self.engine.update_config(
            float(config['radius']), 
            float(config['curve']), 
            float(config['deadzone']),
            float(config.get('t_snap_axis', 0.1)), 
            float(config.get('snap', 0.05)), 
            float(config.get('outer', 0.0))
        )
        
        self.mouse_dev_path = None
        self.tracker = None
        self.hud = None 

    def find_mouse_path(self):
        # Buscamos SOLO el path, Rust lo abrirá
        print("\n--- BUSCANDO MOUSE PARA RUST ---", flush=True)
        try:
            paths = list_devices()
            devices = [InputDevice(path) for path in paths]
        except OSError: return None
        
        candidates = []
        for dev in devices:
            n = dev.name.lower()
            if "virtual" in n or "rust" in n or "keyboard" in n: continue
            
            caps = dev.capabilities()
            if ecodes.EV_REL in caps and ecodes.REL_X in caps[ecodes.EV_REL]:
                 if ecodes.EV_KEY in caps and ecodes.BTN_LEFT in caps[ecodes.EV_KEY]:
                    candidates.append(dev)

        if not candidates: return None
        
        best = candidates[0]
        for dev in candidates:
            n = dev.name.lower()
            if "razer" in n or "logitech" in n: 
                best = dev
                break
            
        print(f"✅ PATH ENCONTRADO: {best.path} ({best.name})", flush=True)
        return str(best.path)

    def run(self):
        # 1. Buscar Mouse
        self.mouse_dev_path = self.find_mouse_path()
        if not self.mouse_dev_path:
            print("[ERROR] No mouse found.")
            return "EXIT"

        # 2. Iniciar HUD y Tracker (Python)
        try: 
            self.hud = JoystickHUD(self.config['radius'])
        except: 
            pass
            
        self.tracker = HeadTracker(source=0, config=self.config, show_debug=False) 

        # 3. ¡ARRANCAR MOTOR RUST! (El hilo se separa aquí)
        print(f"\n>>> INICIANDO HILO DE ALTO RENDIMIENTO (RUST) <<<", flush=True)
        try:
            self.engine.start(self.mouse_dev_path, float(self.screen_w), float(self.screen_h))
        except Exception as e:
            print(f"[FATAL] Rust rechazó iniciar: {e}")
            return "EXIT"

        print("    [ALT+P] Configurar | [ALT+<] Recentrar", flush=True)
        
        try:
            while True:
                # Loop lento de Python (60Hz aprox es suficiente para UI/Tracker)
                
                # A. Gestión de Salida
                if keyboard.is_pressed('alt') and keyboard.is_pressed('p'): 
                    self.engine.stop()
                    return "RESTART"
                
                # --- NUEVO: RESTAURAR ATAJOS DE RECENTRADO ---
                if (keyboard.is_pressed('alt') or keyboard.is_pressed('windows')) and \
                   (keyboard.is_pressed('<') or keyboard.is_pressed('|') or keyboard.is_pressed('\\')):
                    
                    self.engine.recenter() # Le avisa a Rust
                    if self.tracker: 
                        self.tracker.recenter()
                
                # B. Tracker -> Rust
                head_yaw, head_pitch = (0.0, 0.0)
                if self.tracker and self.tracker.running:
                    head_yaw, head_pitch = self.tracker.get_axes()
                    # Enviamos datos al hilo de Rust
                    self.engine.update_tracker(head_yaw, head_pitch)

                # C. Rust -> HUD
                if self.hud:
                    # Leemos el estado real desde Rust para dibujarlo
                    # get_hud_data devuelve tupla: (x, y, throttle, rudder, snapped, deadzone)
                    lx, ly, lt, lr, snap, dead = self.engine.get_hud_data()
                    self.hud.update(lx, ly, lt, lr, head_yaw, head_pitch, dead, snap)
                
                time.sleep(0.016) # 60 FPS update rate para Python

        except KeyboardInterrupt:
            self.engine.stop()
            return "EXIT"
        except Exception as e:
            traceback.print_exc()
            self.engine.stop()
            return "EXIT"

    def cleanup(self):
        # Aquí estaba el error de sintaxis. Lo corregimos con indentación adecuada.
        if self.tracker: 
            self.tracker.stop()
        
        if self.hud:
            try: 
                self.hud.close()
            except: 
                pass