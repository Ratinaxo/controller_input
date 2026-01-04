import cv2
import threading
import time
import os
import numpy as np
import math
import rust_motor # <--- IMPORTAMOS RUST

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

# NOTA: HE BORRADO LA CLASE OneEuroFilter DE PYTHON. YA NO ES NECESARIA.

class HeadTracker:
    def __init__(self, source=0, config=None, show_debug=False):
        self.yaw = 0.0
        self.pitch = 0.0
        self.running = False
        self.cap = None
        self.show_debug = show_debug 
        
        self.config = config if config else load_config()

        default_keys = {
            't_sens_x': 10.0, 't_sens_y': 10.0, 't_smooth': 0.5, 
            't_deadzone': 0.02, 't_snap_axis': 0.20, 't_snap_outer': 0.10,
            't_center_drag': 0.01 
        }
        for k, v in default_keys.items():
            if k not in self.config: self.config[k] = v

        # Referencia dinámica
        self.ref_x = 0.5
        self.ref_y = 0.5
        self.needs_recenter = True
        
        self.landmarker = None
        self.thread = None
        
        # --- FILTROS RUST ---
        beta = float(self.config.get('t_smooth', 0.5))
        # Instanciamos el filtro compilado en Rust (C++)
        self.filter_yaw = rust_motor.RustFilter(0.05, beta, 1.0)
        self.filter_pitch = rust_motor.RustFilter(0.05, beta, 1.0)
        
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
                self.running = False; return 
        except Exception:
            self.running = False; return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def update_config(self, new_config):
        if not new_config: return
        self.config.update(new_config)
        
        # Actualizamos el parámetro Beta directamente en el objeto Rust
        new_beta = float(self.config.get('t_smooth', 0.5))
        self.filter_yaw.beta = new_beta
        self.filter_pitch.beta = new_beta
    
    def _loop(self):
        while self.running and self.cap.isOpened():
            if not self.running: break
            try:
                success, frame = self.cap.read()
                if not success:
                    time.sleep(0.1); continue
                
                frame = cv2.flip(frame, 1)
                img_h, img_w, _ = frame.shape
                
                # Conversión a MediaPipe
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
                
                now = time.time()
                timestamp_ms = int((now - self.start_time) * 1000)
                if timestamp_ms <= self.last_timestamp_ms: timestamp_ms = self.last_timestamp_ms + 1
                self.last_timestamp_ms = timestamp_ms

                if self.landmarker:
                    detection = self.landmarker.detect_for_video(mp_image, timestamp_ms)
                    if detection.face_landmarks:
                        lm = detection.face_landmarks[0]
                        target_pt = lm[152]; eye_l = lm[33]; eye_r = lm[263]

                        dx = (eye_r.x - eye_l.x) * img_w
                        dy = (eye_r.y - eye_l.y) * img_h
                        face_width_px = math.hypot(dx, dy)
                        if face_width_px < 1.0: face_width_px = 1.0

                        # CENTRO DINÁMICO (Esto sigue en Python porque es lógica simple)
                        if self.needs_recenter:
                            self.ref_x = target_pt.x
                            self.ref_y = target_pt.y
                            self.needs_recenter = False
                        else:
                            dist_from_center = math.hypot(target_pt.x - self.ref_x, target_pt.y - self.ref_y)
                            if dist_from_center < 0.15:
                                drag_factor = float(self.config.get('t_center_drag', 0.005))
                                self.ref_x += (target_pt.x - self.ref_x) * drag_factor
                                self.ref_y += (target_pt.y - self.ref_y) * drag_factor

                        delta_x = (target_pt.x - self.ref_x) * img_w
                        delta_y = (target_pt.y - self.ref_y) * img_h
                        
                        raw_yaw = delta_x / face_width_px
                        raw_pitch = delta_y / face_width_px

                        t_relativo = float(now - self.start_time)

                        self.yaw = self.filter_yaw.filter(
                            t_relativo, 
                            float(raw_yaw * self.config.get('t_sens_x', 10.0))
                        )
                        
                        self.pitch = self.filter_pitch.filter(
                            t_relativo, 
                            float(raw_pitch * self.config.get('t_sens_y', 10.0))
                        )
                        
                        if self.show_debug: 
                            self._draw_debug(frame, target_pt, self.ref_x, self.ref_y, img_w, img_h)

                if self.show_debug:
                    cv2.imshow("TRACKER DEBUG (Rust Filter)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'): 
                        self.running = False; break

            except Exception as e:
                print(f"[TRACKER ERROR] {e}")
            
            time.sleep(0.01)

        if self.cap: self.cap.release()
        if self.landmarker: 
            try: self.landmarker.close() 
            except: pass
        if self.show_debug: cv2.destroyAllWindows()

    def _draw_debug(self, frame, point, cx, cy, w, h):
        nx, ny = int(point.x * w), int(point.y * h)
        cv2.circle(frame, (nx, ny), 5, (0, 255, 0), -1) 
        ref_x, ref_y = int(cx * w), int(cy * h)
        cv2.circle(frame, (ref_x, ref_y), 6, (0, 0, 255), 2) 
        cv2.line(frame, (ref_x, ref_y), (nx, ny), (255, 255, 0), 2)

    def get_axes(self):
        if not self.running: return 0.0, 0.0
        # Reutilizamos la lógica del tracker
        return self.yaw, self.pitch

    def recenter(self):
        self.needs_recenter = True

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)