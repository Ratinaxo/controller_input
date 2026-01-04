import time
import keyboard
import rust_motor 
from evdev import InputDevice, list_devices, ecodes
import sys
import traceback
import pyautogui
import os

from backend.tracker import HeadTracker
from frontend.hud import JoystickHUD

class JoystickBackend:
    def __init__(self, config):
        self.config = config
        self.screen_w, self.screen_h = pyautogui.size()
        
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
        
        self.tracker = None
        self.hud = None 

    def find_devices(self):
        print("\n--- BUSCANDO HARDWARE (HEURÍSTICA V2) ---", flush=True)
        mouse_path = None
        kb_path = None
        
        try:
            device_paths = list_devices()
        except Exception as e:
            print(f"❌ Error al listar dispositivos: {e}")
            return None, None

        # Prioridad de marcas conocidas para el mouse (Gaming)
        gaming_brands = ["razer", "logitech", "corsair", "steelseries", "zowie", "benq"]

        found_mice = []

        for path in device_paths:
            try:
                dev = InputDevice(path)
                n = dev.name.lower()
                
                if "virtual" in n or "rust" in n or "uinput" in n:
                    continue
                
                caps = dev.capabilities()

                # 1. Identificar Teclado REAL (Debe tener teclas estándar y NO ser mouse)
                if not kb_path:
                    if ecodes.EV_KEY in caps and ecodes.KEY_P in caps[ecodes.EV_KEY]:
                        # Si el nombre contiene "mouse", probablemente es la interfaz RGB del teclado, la ignoramos
                        if "mouse" not in n:
                            kb_path = path
                            print(f"  [OK] Teclado Real: {dev.name} -> {path}")

                # 2. Identificar Mouses potenciales
                if ecodes.EV_REL in caps and ecodes.REL_X in caps[ecodes.EV_REL]:
                    if ecodes.EV_KEY in caps and ecodes.BTN_LEFT in caps[ecodes.EV_KEY]:
                        # Puntuamos el mouse: si es de marca gaming, va primero
                        score = 0
                        if any(brand in n for brand in gaming_brands): score += 10
                        if "keyboard" in n or "alloy" in n: score -= 5 # Bajamos puntos a interfaces de teclado
                        
                        found_mice.append({
                            'path': path,
                            'name': dev.name,
                            'score': score
                        })

            except:
                continue

        # Seleccionamos el mejor mouse basado en el score
        if found_mice:
            # Ordenar por score descendente
            found_mice.sort(key=lambda x: x['score'], reverse=True)
            best_mouse = found_mice[0]
            mouse_path = best_mouse['path']
            print(f"  [OK] Mouse Seleccionado: {best_mouse['name']} -> {mouse_path} (Score: {best_mouse['score']})")
            
            # Si el teclado falló, usamos el mouse como respaldo para los eventos
            if not kb_path:
                kb_path = mouse_path
                print(f"  [!] Usando mouse como fuente de teclado (Fallback)")

        return mouse_path, kb_path

    def run(self):
        if os.name == 'posix':
            os.system("stty -echo")

        # Buscamos el mouse (kb_path ya no es necesario aquí)
        mouse_path, _ = self.find_devices()
        
        if not mouse_path:
            print("❌ ERROR: No se encontró un Mouse compatible.")
            return "EXIT"

        # Inicialización de HUD y Tracker
        try: self.hud = JoystickHUD(self.config['radius'])
        except: pass
        self.tracker = HeadTracker(source=0, config=self.config, show_debug=False)

        print(f"\n>>> INICIANDO HILO DE ALTO RENDIMIENTO (RUST) <<<", flush=True)
        try:
            # Iniciamos Rust (asegúrate de que la firma de start en engine.rs coincida)
            self.engine.start(str(mouse_path), float(self.screen_w), float(self.screen_h))
            print("    [HILO RUST LANZADO EXITOSAMENTE]", flush=True)
        except Exception as e:
            print(f"❌ FATAL: Rust rechazó iniciar: {e}")
            return "EXIT"

        print("    [ALT+P] Configurar | [ALT+<] Recentrar", flush=True)
        
        try:
            while True:
                # --- 1. ATAJOS (Gestionados por Python) ---
                
                # Salida: ALT + P
                if keyboard.is_pressed('alt') and keyboard.is_pressed('p'):
                    print("[MOTOR] Solicitando salida...", flush=True)
                    self.engine.request_exit()
                    time.sleep(0.2)
                    return "RESTART"
                
                # Recentrar: (ALT o WIN) + <
                # Usamos scancode 86 (teclado ISO/Español) y 43 (teclado US) como enteros
                try:
                    is_alt_win = keyboard.is_pressed('alt') or keyboard.is_pressed('windows')
                    # Probamos la tecla física directa
                    is_recenter_key = keyboard.is_pressed('<') or keyboard.is_pressed(86) or keyboard.is_pressed(43)
                    
                    if is_alt_win and is_recenter_key:
                        self.engine.recenter()
                        if self.tracker: 
                            self.tracker.recenter()
                        print("[MOTOR] Recentrado.", flush=True)
                        time.sleep(0.2)
                except:
                    pass # Evitar que un error de mapeo de tecla rompa el bucle

                # Verificar si Rust sigue vivo
                if not self.engine.is_running(): 
                    return "RESTART"
                
                # --- 2. TRACKER -> RUST ---
                hy, hp = 0.0, 0.0
                if self.tracker and self.tracker.running:
                    hy, hp = self.tracker.get_axes()
                    self.engine.update_tracker(float(hy), float(hp))

                # --- 3. RUST -> HUD ---
                if self.hud:
                    lx, ly, lt, lr, snap, dead = self.engine.get_hud_data()
                    self.hud.update(lx, ly, lt, lr, hy, hp, dead, snap)
                
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
        if os.name == 'posix':
            os.system("stty echo")
        if self.engine:
            self.engine.stop()
        if self.tracker: 
            self.tracker.stop()
        if self.hud:
            try: self.hud.close()
            except: pass