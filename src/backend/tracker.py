import cv2
import threading
import time
import os
import numpy as np
import math

# --- IMPORTS DE UTILIDADES ---
try:
    from utils.paths import MODEL_PATH
    from utils.config_manager import load_config
except ImportError:
    try:
        from utils.utils import MODEL_PATH
    except: pass
    def load_config(): return {}

HAS_MEDIAPIPE = False
try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    HAS_MEDIAPIPE = True
except ImportError: pass

class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = min_cutoff 
        self.beta = beta             
        self.d_cutoff = d_cutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def smoothing_factor(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def exponential_smoothing(self, a, x, x_prev):
        return a * x + (1 - a) * x_prev

    def filter(self, t, x):
        if self.x_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x
        t_e = t - self.t_prev
        if t_e <= 0: return self.x_prev
        a_d = self.smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = self.exponential_smoothing(a_d, dx, self.dx_prev)
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self.smoothing_factor(t_e, cutoff)
        x_hat = self.exponential_smoothing(a, x, self.x_prev)
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat

class HeadTracker:
    def __init__(self, source=0, config=None, show_debug=False):
        self.yaw = 0.0
        self.pitch = 0.0
        self.running = False
        self.cap = None
        self.show_debug = show_debug 
        
        self.config = config if config else load_config()

        default_keys = {
            't_sens_x': 10.0, 
            't_sens_y': 10.0, 
            't_smooth': 0.5, 
            't_deadzone': 0.02,
            't_snap_axis': 0.20, 
            't_snap_outer': 0.10,
            # NUEVO: Velocidad a la que el centro persigue al mentón (0.001 a 0.01 es bueno)
            't_center_drag': 0.01 
        }
        for k, v in default_keys.items():
            if k not in self.config:
                self.config[k] = v

        # Variables de Referencia (Ahora son dinámicas)
        self.ref_x = 0.5
        self.ref_y = 0.5
        self.needs_recenter = True
        
        self.landmarker = None
        self.thread = None
        
        beta = self.config.get('t_smooth', 0.5)
        self.filter_yaw = OneEuroFilter(min_cutoff=0.05, beta=beta)
        self.filter_pitch = OneEuroFilter(min_cutoff=0.05, beta=beta)
        
        self.start_time = time.time()
        self.last_timestamp_ms = 0

        if not HAS_MEDIAPIPE: 
            print("[TRACKER] Error: MediaPipe no instalado.")
            return
        if not os.path.exists(MODEL_PATH): 
            print(f"[TRACKER] Error: Modelo no encontrado en {MODEL_PATH}")
            return

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, 
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False
        )
        
        try:
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[TRACKER] Error al iniciar MediaPipe: {e}")
            return

        try:
            self.cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            if not self.cap.isOpened():
                print("[TRACKER] ADVERTENCIA: No se pudo abrir la cámara.")
                self.running = False
                return 
        except Exception as e:
            print(f"[TRACKER] Error HW: {e}")
            self.running = False
            return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def update_config(self, new_config):
        if not new_config: return
        self.config.update(new_config)
        new_beta = self.config.get('t_smooth', 0.5)
        self.filter_yaw.beta = new_beta
        self.filter_pitch.beta = new_beta
    
    def _loop(self):
        while self.running and self.cap.isOpened():
            if not self.running: break
            
            try:
                success, frame = self.cap.read()
                if not success:
                    time.sleep(0.1)
                    continue
                
                frame = cv2.flip(frame, 1)
                img_h, img_w, _ = frame.shape
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frame_rgb))
                
                now = time.time()
                timestamp_ms = int((now - self.start_time) * 1000)
                if timestamp_ms <= self.last_timestamp_ms: timestamp_ms = self.last_timestamp_ms + 1
                self.last_timestamp_ms = timestamp_ms

                if self.landmarker:
                    detection = self.landmarker.detect_for_video(mp_image, timestamp_ms)
                    if detection.face_landmarks:
                        lm = detection.face_landmarks[0]
                        
                        target_pt = lm[152] # Mentón
                        eye_l = lm[33]
                        eye_r = lm[263]

                        # Escala basada en distancia de ojos
                        dx = (eye_r.x - eye_l.x) * img_w
                        dy = (eye_r.y - eye_l.y) * img_h
                        face_width_px = math.hypot(dx, dy)
                        if face_width_px < 1.0: face_width_px = 1.0

                        # --- LÓGICA DE CENTRO DINÁMICO ---
                        if self.needs_recenter:
                            # Recentrado brusco (Reset manual)
                            self.ref_x = target_pt.x
                            self.ref_y = target_pt.y
                            self.needs_recenter = False
                            continue
                        else:
                            # Recentrado Suave (Ancla con peso)
                            # Calculamos qué tan lejos está el mentón del centro actual
                            dist_from_center = math.hypot(target_pt.x - self.ref_x, target_pt.y - self.ref_y)
                            
                            # SAFETY GATE: Solo movemos el centro si el usuario está mirando 
                            # relativamente al frente (dist < 0.15 en coord normalizadas).
                            # Si mira muy lejos (queriendo ver atrás), congelamos el centro 
                            # para que no "persiga" la mirada extrema.
                            if dist_from_center < 0.15:
                                drag_factor = self.config.get('t_center_drag', 0.005)
                                # Fórmula de Interpolación Lineal (LERP)
                                self.ref_x = self.ref_x + (target_pt.x - self.ref_x) * drag_factor
                                self.ref_y = self.ref_y + (target_pt.y - self.ref_y) * drag_factor

                        # Desplazamiento del MENTÓN respecto al centro (que ahora es dinámico)
                        delta_x = (target_pt.x - self.ref_x) * img_w
                        delta_y = (target_pt.y - self.ref_y) * img_h
                        
                        raw_yaw = delta_x / face_width_px
                        raw_pitch = delta_y / face_width_px

                        val_yaw = raw_yaw * self.config.get('t_sens_x', 10.0)
                        val_pitch = raw_pitch * self.config.get('t_sens_y', 10.0)

                        self.yaw = self.filter_yaw.filter(now, val_yaw)
                        self.pitch = self.filter_pitch.filter(now, val_pitch)
                        
                        if self.show_debug: 
                            self._draw_debug(frame, target_pt, self.ref_x, self.ref_y, img_w, img_h)

                if self.show_debug:
                    cv2.imshow("TRACKER DEBUG (Dynamic Anchor)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): 
                        self.running = False
                        break

            except Exception as e:
                print(f"[TRACKER ERROR] Loop: {e}")
            
            time.sleep(0.01)

        print("[TRACKER] Hilo finalizando, liberando recursos...")
        if self.cap:
            self.cap.release()
            self.cap = None 
        if self.landmarker:
            try: self.landmarker.close()
            except: pass
        if self.show_debug:
            try: cv2.destroyAllWindows(); cv2.waitKey(1)
            except: pass

    def _draw_debug(self, frame, point, cx, cy, w, h):
        # Punto Actual (Mentón) - VERDE
        nx, ny = int(point.x * w), int(point.y * h)
        cv2.circle(frame, (nx, ny), 5, (0, 255, 0), -1) 
        
        # Referencia (Centro Dinámico) - ROJO
        # Verás que este punto ROJO persigue lentamente al VERDE
        ref_x, ref_y = int(cx * w), int(cy * h)
        cv2.circle(frame, (ref_x, ref_y), 6, (0, 0, 255), 2) 
        
        # Vector
        cv2.line(frame, (ref_x, ref_y), (nx, ny), (255, 255, 0), 2)

    def get_axes(self):
        """
        Calcula los ejes finales con física radial
        """
        if not self.running: return 0.0, 0.0
        
        raw_x, raw_y = self.yaw, self.pitch
        magnitude = math.hypot(raw_x, raw_y)
        
        if magnitude < 0.0001: return 0.0, 0.0

        DEADZONE = self.config.get('t_deadzone', 0.02)
        if magnitude < DEADZONE:
            return 0.0, 0.0
        
        smooth_mag = (magnitude - DEADZONE) / (1.0 - DEADZONE)
        
        SNAP_AXIS = self.config.get('t_snap_axis', 0.25)
        out_x, out_y = raw_x, raw_y
        
        if abs(raw_y) < (abs(raw_x) * SNAP_AXIS):
            out_y = 0.0
        elif abs(raw_x) < (abs(raw_y) * SNAP_AXIS):
            out_x = 0.0
            
        curr_mag = math.hypot(out_x, out_y)
        if curr_mag > 0.0001:
            unit_x = out_x / curr_mag
            unit_y = out_y / curr_mag
        else:
            return 0.0, 0.0

        final_mag = min(smooth_mag, 1.0)
        
        SNAP_OUTER = self.config.get('t_snap_outer', 0.10)
        if final_mag > (1.0 - SNAP_OUTER):
            final_mag = 1.0

        final_x = unit_x * final_mag
        final_y = unit_y * final_mag

        return final_x, final_y

    def recenter(self):
        self.needs_recenter = True

    def stop(self):
        print("[TRACKER] Solicitud de parada enviada...")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)