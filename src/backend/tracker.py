import cv2
import threading
import time
import os
import math
from collections import deque

import numpy as np
import rust_motor
from utils.telemetry import CsvLogger
from utils.utils import MODEL_PATH
from utils.config import load_config
from frontend.camera_view import geometry as camera_geometry
from frontend.camera_view.overlay import CameraOverlay

HAS_MEDIAPIPE = False
try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    pass


# --- Constantes de calibración y centrado ---------------------------------

# Unidades de los puntos de calibración. Los puntos guardados por versiones
# anteriores no tienen este campo (estaban en unidades escaladas por la
# sensibilidad) y se ignoran: hay que recalibrar.
CALIB_UNITS = "deg"

# Límite de giro (grados) cuando no hay calibración válida: rectángulo
# simétrico de ±35° en yaw y pitch.
DEFAULT_LIMIT_DEG = 35.0

# Ángulo esperado (grados) de cada paso del asistente, en el plano
# (yaw, pitch) con yaw+ = derecha y pitch+ = abajo:
# 0° derecha, 90° abajo, 180° izquierda, 270° arriba.
EXPECTED_ANGLES = {
    "right": 0.0,
    "diag_down_right": 45.0,
    "down": 90.0,
    "diag_down_left": 135.0,
    "left": 180.0,
    "diag_up_left": 225.0,
    "up": 270.0,
    "diag_up_right": 315.0,
}
ANGLE_TOLERANCE_DEG = 30.0     # desvío máximo aceptado respecto al esperado
MIN_CALIB_MAGNITUDE_DEG = 5.0  # por debajo, la cabeza está casi al centro

# Signo esperado de cada componente en cada paso; 0 = da igual.
EXPECTED_SIGNS = {
    "right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1),
    "diag_down_right": (1, 1), "diag_down_left": (-1, 1),
    "diag_up_right": (1, -1), "diag_up_left": (-1, -1),
}
DIAGONAL_LABELS = frozenset(
    label for label, s in EXPECTED_SIGNS.items() if s[0] and s[1])

# El rango de giro NO es isótropo: el cuello gira mucho más de lado que
# hacia abajo, y con la cámara mirando desde abajo la diferencia se
# acentúa. Con un rango de yaw de 35° y uno de pitch de 6°, una diagonal
# inferior izquierda honesta se mide en 170° crudos y no en los 135°
# nominales, y el asistente la rechazaba.
#
# La solución no es ensanchar la tolerancia (los 8 pasos están a 45°,
# ensancharla los solapa) sino medir la dirección en el rango PROPIO:
# dividir cada eje por lo que ya midió ese usuario en las cardinales.
# En ese espacio, la misma diagonal cae en 142° y entra sin problema.
MIN_DIRECTION_SCALE_DEG = 3.0    # por debajo no se fía de la escala medida

# Para las cardinales se usa dominancia de eje en vez del ángulo, igual
# que ya hace el asistente de traslación: es indiferente a la anisotropía
# y dice algo más útil cuando falla ("dominó el otro eje").
CARDINAL_MIN_MAGNITUDE_DEG = 3.0   # una cardinal puede ser legítimamente corta
DIAGONAL_MIN_MAGNITUDE_DEG = 5.0   # una diagonal necesita las dos componentes
MIN_CALIB_NORM_FRACTION = 0.35     # ...o un 35 % del rango propio, si se conoce

STABLE_WINDOW_S = 0.5          # ventana para decidir si la cabeza está quieta
STABLE_SPREAD_DEG = 2.0        # dispersión máxima dentro de esa ventana

CENTER_DRAG_RADIUS_DEG = 8.0   # el auto-centrado solo actúa cerca del centro
GAP_RESET_S = 0.3              # tras un hueco de detección, reiniciar filtros


# --- Constantes de traslación (6DOF) -------------------------------------

# Unidades de head_trans_limits. Mismo mecanismo que CALIB_UNITS: si algún
# día cambia la escala, los valores viejos se ignoran en vez de leerse mal.
TRANS_CALIB_UNITS = "cm"

# Rango por eje y sentido (cm) cuando no hay calibración válida. La escala
# de MediaPipe es aproximada (depende del campo de visión que asume para la
# cámara), así que esto es solo un punto de partida razonable: el asistente
# mide TU rango real y normaliza contra él.
DEFAULT_TRANS_LIMIT_CM = 10.0

# Pasos del asistente de calibración de traslación: para cada uno, el eje
# que debe dominar (0=lateral, 1=vertical, 2=profundidad) y el signo
# esperado. Si te inclinas a la izquierda y lo que más cambia es la
# profundidad, el paso se rechaza.
TRANS_STEPS = {
    "x_pos": (0, +1), "x_neg": (0, -1),
    "y_pos": (1, +1), "y_neg": (1, -1),
    "z_pos": (2, +1), "z_neg": (2, -1),
}
MIN_CALIB_TRANS_CM = 2.0       # por debajo, la cabeza no se movió de verdad
DOMINANT_AXIS_RATIO = 1.5      # el eje esperado debe superar a los otros x1.5
STABLE_TRANS_SPREAD_CM = 0.7   # dispersión máxima para considerarla quieta


# --- Fuentes de datos de cabeza -------------------------------------------
# 'internal' es la cámara propia; 'external' significa que otro programa
# (OpenTrack) publica su propio joystick y aquí no se toca la cámara.
# Cuando se migre la traslación (6DOF) desde OpenTrack por UDP, se agrega
# un modo 'udp' aquí y un objeto con la misma interfaz mínima que usa el
# motor: get_axes(), recenter(), update_config(), stop() y .running.
HEAD_SOURCES = {
    "internal": "Cámara propia (MediaPipe)",
    "external": "Externa: OpenTrack u otro (libera la cámara)",
}


def create_head_source(config, show_debug=False, source=0):
    """Devuelve el proveedor de ejes de cabeza según config['head_source'],
    o None si otro programa se encarga. Todos los usos en el motor y la GUI
    ya toleran None, así que 'external' simplemente deja los ejes de cabeza
    centrados y no abre la cámara."""
    mode = str(config.get("head_source", "internal")).lower()
    if mode != "internal":
        print(f"[TRACKER] Fuente de cabeza '{mode}': no se abre la cámara aquí.")
        return None
    return HeadTracker(source=source, config=config, show_debug=show_debug)


def matrix_to_euler(matrix):
    R = np.array(matrix)[:3, :3]
    yaw = np.degrees(np.arctan2(-R[2, 0], np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)))
    pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    return float(yaw), float(pitch)


def matrix_to_euler3(matrix):
    """Como matrix_to_euler pero también el roll, con la misma
    descomposición (yaw primero). MediaPipe ya lo entrega: es gratis."""
    R = np.array(matrix)[:3, :3]
    yaw = np.degrees(np.arctan2(-R[2, 0], np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)))
    pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    roll = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    return float(yaw), float(pitch), float(roll)


def matrix_parts(matrix):
    """(R, t) de la matriz de MediaPipe: rotación 3x3 y traslación en cm.

    La escala de `t` es aproximada -- depende del campo de visión que
    MediaPipe asume para la cámara -- y la profundidad es la menos fiable
    de las tres. No importa para el resultado: la calibración por eje mide
    el rango real y normaliza contra él, así que los cm son solo la unidad
    interna.
    """
    M = np.array(matrix, dtype=float)
    return M[:3, :3], M[:3, 3].copy()


def compensate_neck(R, t, neck_height_cm, neck_depth_cm):
    """Quita de la traslación medida el desplazamiento que produce girar
    la cabeza sobre el cuello.

    El pivote está en el cuello, no en la cara: al girar, la cara se
    traslada aunque el cuerpo no se mueva, y sin corregirlo mirar a un
    lado desplaza la cámara lateralmente.

    Si `d` es el vector del pivote a la cara en coordenadas de la cabeza
    (la cara está por encima y por delante del cuello), la posición de la
    cara es `t_cara = t_pivote + R @ d`. Se resta `(R - I) @ d` en vez de
    `R @ d` para no mover el cero: en reposo (R = I) el resultado es la
    lectura original.

    Si al girar la cabeza el error EMPEORA en vez de mejorar, el signo del
    sistema de coordenadas es el opuesto: usa alturas negativas.
    """
    d = np.array([0.0, float(neck_height_cm), float(neck_depth_cm)], dtype=float)
    return np.asarray(t, dtype=float) - (np.asarray(R, dtype=float) - np.eye(3)) @ d


def valid_trans_limits(limits):
    """Devuelve los límites por eje en cm como dict, o {} si no hay
    calibración utilizable (sin calibrar, o guardada con otras unidades)."""
    if not isinstance(limits, dict):
        return {}
    if limits.get("units") != TRANS_CALIB_UNITS:
        return {}
    out = {}
    for key in TRANS_STEPS:
        try:
            v = float(limits.get(key, 0.0))
        except (TypeError, ValueError):
            continue
        if v > 0:
            out[key] = v
    return out


def _clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, float(v)))


def _deadzone(value, dz):
    """Zona muerta con reescalado, en una dimensión: la magnitud se remapea
    de [dz, 1] a [0, 1], así la salida parte de 0.0 justo en el borde y no
    hay salto. Misma idea que la zona muerta radial de physics.rs."""
    dz = max(0.0, min(0.95, float(dz)))
    a = abs(float(value))
    if a <= dz:
        return 0.0
    return math.copysign((a - dz) / (1.0 - dz), value)


def _curve(value, exponent):
    """Curva de respuesta simétrica, la misma del stick: exponente > 1 da
    precisión cerca del centro sin perder el tope al final."""
    return math.copysign(min(abs(float(value)), 1.0) ** max(float(exponent), 0.01), value)


def wrap180(a):
    """Lleva un ángulo a [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


def angle_distance(a, b):
    """Distancia angular absoluta entre dos ángulos en grados."""
    return abs(wrap180(a - b))


def direction_scales(points):
    """`(yaw_scale, pitch_scale)` en grados, sacados de las cardinales ya
    calibradas, o `None` si todavía no hay una de cada eje.

    Es el rango propio de quien está calibrando. Sirve para que las
    diagonales se validen en fracciones de ESE rango y no en grados
    crudos: el cuello gira mucho más de lado que hacia abajo, así que en
    grados crudos una diagonal honesta no cae en los 135° nominales.

    El asistente pide las cuatro cardinales antes que las diagonales, así
    que para cuando hacen falta ya están medidas.
    """
    horizontal, vertical = [], []
    for point in valid_limit_points(points):
        label = point.get("label")
        try:
            magnitude = float(point.get("magnitude", 0.0))
        except (TypeError, ValueError):
            continue
        if label in ("left", "right"):
            horizontal.append(magnitude)
        elif label in ("up", "down"):
            vertical.append(magnitude)
    if not horizontal or not vertical:
        return None
    yaw_scale = sum(horizontal) / len(horizontal)
    pitch_scale = sum(vertical) / len(vertical)
    if yaw_scale < MIN_DIRECTION_SCALE_DEG or pitch_scale < MIN_DIRECTION_SCALE_DEG:
        return None
    return yaw_scale, pitch_scale


def valid_limit_points(points):
    """Puntos de calibración utilizables (en grados, magnitud positiva)."""
    return [
        p for p in (points or [])
        if p.get("units") == CALIB_UNITS and float(p.get("magnitude", 0)) > 0
    ]


def has_legacy_calibration(points):
    """True si hay puntos guardados por una versión anterior (sin unidades)."""
    return any(p.get("units") != CALIB_UNITS for p in (points or []))


class HeadTracker:
    def __init__(self, source=0, config=None, show_debug=False):
        # Salida normalizada [-1, 1] como tupla: una sola asignación, así
        # otro hilo nunca lee yaw de un frame y pitch de otro.
        self._axes = (0.0, 0.0)
        # Los 6 ejes normalizados, en el orden que emite el motor:
        # (yaw, pitch, roll, tx, ty, tz).
        self._head_axes = (0.0,) * 6
        # Ángulo relativo al centro, filtrado, en grados.
        self._rel_deg = (0.0, 0.0)
        # Traslación relativa al centro, compensada y filtrada, en cm.
        self._rel_cm = (0.0, 0.0, 0.0)
        self.running = False
        self.cap = None
        self.show_debug = show_debug

        self.config = config if config is not None else load_config()

        default_keys = {
            't_sens_x': 10.0, 't_sens_y': 10.0,
            # Filtro One Euro (en grados):
            #  - t_min_cutoff (Hz): suavizado en reposo; más bajo = más estable quieto.
            #  - t_beta: reacción al movimiento; más alto = menos lag al girar.
            't_min_cutoff': 1.0, 't_beta': 0.05,
            't_center_drag': 0.0, 'cam_rotation': 0,
            # Límites de giro como octágono (8 puntos ángulo+magnitud en
            # GRADOS, medidos con el asistente guiado). Lista vacía o sin
            # puntos válidos -> rectángulo de ±35°.
            'head_limit_points': [],
            # --- Traslación (6DOF) y roll ---
            'head_trans_limits': {'units': TRANS_CALIB_UNITS},
            't_trans_sens_x': 10.0, 't_trans_sens_y': 10.0, 't_trans_sens_z': 10.0,
            't_trans_deadzone_x': 0.03, 't_trans_deadzone_y': 0.03,
            't_trans_deadzone_z': 0.06,
            't_trans_curve_x': 1.5, 't_trans_curve_y': 1.5, 't_trans_curve_z': 1.5,
            't_trans_invert_x': False, 't_trans_invert_y': True,
            't_trans_invert_z': False,
            't_trans_min_cutoff': 0.8, 't_trans_beta': 0.02,
            't_trans_min_cutoff_z': 0.4, 't_trans_beta_z': 0.01,
            't_neck_height_cm': 10.0, 't_neck_depth_cm': 10.0,
            't_sens_roll': 10.0, 't_roll_deadzone': 0.03,
            'head_roll_limit_deg': 30.0,
        }
        for k, v in default_keys.items():
            if k not in self.config:
                self.config[k] = v

        # Referencia angular (grados) y referencia de la nariz (solo para el debug).
        self.ref_yaw = None
        self.ref_pitch = None
        self.ref_roll = None
        # Referencia de traslación (cm, ya compensada y filtrada).
        self.ref_t = None
        self.ref_x = 0.5
        self.ref_y = 0.5
        # Radio (px) de la cara guardado al recentrar, para el círculo de
        # referencia del overlay: "¿me alejé de la distancia a la que
        # calibré?". 0 hasta el primer recentrado.
        self.ref_radius = 0
        self.needs_recenter = True
        # Overlay de la vista de cámara. Se crea una sola vez para que su
        # recuadro de encuadre persista entre frames.
        self._overlay = CameraOverlay()
        # Último frame anotado, para que la GUI lo muestre embebido. Se
        # reemplaza el objeto entero de una sola asignación, igual que
        # `_axes`: el hilo de la cámara escribe y el de Tk lee, y así
        # nunca se lee medio frame. El contador le dice al lector si hay
        # uno nuevo, para no reconvertir la misma imagen 60 veces por
        # segundo.
        self._frame = None
        self._frame_count = 0
        # Nadie mira todavía: dibujar 478 puntos cuesta poco, pero cuesta
        # cero si no se hace. La GUI lo enciende al mostrar la vista.
        self.overlay_enabled = bool(show_debug)
        self._last_detect_t = None

        # Historial reciente de ángulos relativos para detectar "quieto".
        self._hist = deque(maxlen=240)
        self._hist_lock = threading.Lock()
        # Historial de traslación relativa (cm), para el asistente.
        self._hist_t = deque(maxlen=240)

        self.landmarker = None
        self.thread = None

        # --- FILTROS RUST (One Euro sobre el ángulo absoluto en grados) ---
        mc = float(self.config.get('t_min_cutoff', 1.0))
        beta = float(self.config.get('t_beta', 0.05))
        self.filter_yaw = rust_motor.RustFilter(mc, beta, 1.0)
        self.filter_pitch = rust_motor.RustFilter(mc, beta, 1.0)
        self.filter_roll = rust_motor.RustFilter(mc, beta, 1.0)

        # --- FILTROS DE TRASLACIÓN (One Euro sobre los cm compensados) ---
        # Parámetros propios, y más suavizado en profundidad: es el eje más
        # ruidoso de los tres.
        tmc = float(self.config.get('t_trans_min_cutoff', 0.8))
        tbeta = float(self.config.get('t_trans_beta', 0.02))
        zmc = float(self.config.get('t_trans_min_cutoff_z', 0.4))
        zbeta = float(self.config.get('t_trans_beta_z', 0.01))
        self.filter_tx = rust_motor.RustFilter(tmc, tbeta, 1.0)
        self.filter_ty = rust_motor.RustFilter(tmc, tbeta, 1.0)
        self.filter_tz = rust_motor.RustFilter(zmc, zbeta, 1.0)

        self._telemetry = CsvLogger(
            "tracker",
            ["t_abs", "detected", "recentered", "raw_yaw", "raw_pitch", "yaw", "pitch",
             "rel_yaw_deg", "rel_pitch_deg", "face_width_px",
             # Traslación: en crudo (antes de cualquier proceso, para medir
             # el ruido real), compensada de cuello, filtrada+relativa al
             # centro, y normalizada [-1, 1] tal como sale al juego.
             "raw_tx", "raw_ty", "raw_tz",
             "comp_tx", "comp_ty", "comp_tz",
             "rel_tx_cm", "rel_ty_cm", "rel_tz_cm",
             "out_tx", "out_ty", "out_tz",
             "raw_roll", "rel_roll_deg", "out_roll"],
            enabled=bool(self.config.get('telemetry_enabled', False))
        )

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
            output_facial_transformation_matrixes=True
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
                print(f"[TRACKER] ⚠ No se pudo abrir la cámara {source}: los ejes de cabeza "
                      "quedan centrados. ¿La está usando otro programa (OpenTrack, el "
                      "navegador)?", flush=True)
                self.running = False
                return
        except Exception as e:
            print(f"[TRACKER] ⚠ Error al abrir la cámara {source}: {e}. Los ejes de cabeza "
                  "quedan centrados.", flush=True)
            self.running = False
            return

        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def update_config(self, new_config):
        if not new_config:
            return
        self.config.update(new_config)
        mc = float(self.config.get('t_min_cutoff', 1.0))
        beta = float(self.config.get('t_beta', 0.05))
        for f in (self.filter_yaw, self.filter_pitch, self.filter_roll):
            f.min_cutoff = mc
            f.beta = beta

        tmc = float(self.config.get('t_trans_min_cutoff', 0.8))
        tbeta = float(self.config.get('t_trans_beta', 0.02))
        for f in (self.filter_tx, self.filter_ty):
            f.min_cutoff = tmc
            f.beta = tbeta
        self.filter_tz.min_cutoff = float(self.config.get('t_trans_min_cutoff_z', 0.4))
        self.filter_tz.beta = float(self.config.get('t_trans_beta_z', 0.01))

    # ------------------------------------------------------------------
    # Lazo de captura
    # ------------------------------------------------------------------
    def _loop(self):
        while self.running and self.cap.isOpened():
            try:
                success, frame = self.cap.read()
                if not success:
                    time.sleep(0.1)
                    continue

                # Corrección de rotación (cámaras IP tipo DroidCam). Antes
                # del espejo y antes de leer width/height.
                rotation = int(self.config.get('cam_rotation', 0)) % 360
                if rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                frame = cv2.flip(frame, 1)
                img_h, img_w, _ = frame.shape

                # OpenCV entrega BGR; MediaPipe espera RGB.
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

                now = time.time()
                timestamp_ms = int((now - self.start_time) * 1000)
                if timestamp_ms <= self.last_timestamp_ms:
                    timestamp_ms = self.last_timestamp_ms + 1
                self.last_timestamp_ms = timestamp_ms

                if self.landmarker:
                    detection = self.landmarker.detect_for_video(mp_image, timestamp_ms)
                    if detection.face_landmarks and detection.facial_transformation_matrixes:
                        lm = detection.face_landmarks[0]
                        self._process_detection(
                            now, lm, detection.facial_transformation_matrixes[0], img_w, img_h, frame
                        )
                    else:
                        # Sin detección este frame (típicamente de perfil).
                        self._telemetry.log({
                            "t_abs": now, "detected": False, "recentered": False,
                            "raw_yaw": "", "raw_pitch": "", "yaw": "", "pitch": "",
                            "rel_yaw_deg": "", "rel_pitch_deg": "", "face_width_px": "",
                        })

                if self.show_debug:
                    cv2.imshow("TRACKER DEBUG (Rust Filter)", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.running = False
                        break

            except Exception as e:
                print(f"[TRACKER ERROR] {e}")

            time.sleep(0.01)

        if self.cap:
            self.cap.release()
        if self.landmarker:
            try:
                self.landmarker.close()
            except Exception:
                pass
        if self.show_debug:
            cv2.destroyAllWindows()

    def _process_detection(self, now, lm, matrix, img_w, img_h, frame):
        target_pt = lm[6]

        # Ancho interocular en px: dato de diagnóstico para la telemetría
        # (se achica cuando la cara gira de perfil).
        eye_l, eye_r = lm[33], lm[263]
        face_width_px = max(math.hypot((eye_r.x - eye_l.x) * img_w, (eye_r.y - eye_l.y) * img_h), 1.0)

        raw_yaw, raw_pitch, raw_roll = matrix_to_euler3(matrix)
        R, raw_t = matrix_parts(matrix)
        t = float(now - self.start_time)

        # Tras un hueco largo de detección, no interpolar desde un valor viejo.
        if self._last_detect_t is not None and t - self._last_detect_t > GAP_RESET_S:
            for f in (self.filter_yaw, self.filter_pitch, self.filter_roll,
                      self.filter_tx, self.filter_ty, self.filter_tz):
                f.reset()
        self._last_detect_t = t

        # Se filtra el ángulo ABSOLUTO en grados (independiente de la
        # sensibilidad). Así recentrar o arrastrar el centro no pasa por el
        # filtro: el cero cambia al instante, sin deslizamiento.
        f_yaw = self.filter_yaw.filter(t, raw_yaw)
        f_pitch = self.filter_pitch.filter(t, raw_pitch)
        f_roll = self.filter_roll.filter(t, raw_roll)

        # TRASLACIÓN: primero se quita el efecto del giro sobre el cuello
        # (necesita la rotación en crudo, que es la que corresponde a esta
        # lectura de posición), y después se filtra, igual que la rotación:
        # sobre el valor ABSOLUTO, para que recentrar no pase por el filtro.
        comp_t = compensate_neck(
            R, raw_t,
            self.config.get('t_neck_height_cm', 10.0),
            self.config.get('t_neck_depth_cm', 10.0),
        )
        f_t = (
            self.filter_tx.filter(t, float(comp_t[0])),
            self.filter_ty.filter(t, float(comp_t[1])),
            self.filter_tz.filter(t, float(comp_t[2])),
        )

        just_recentered = self.needs_recenter
        if self.needs_recenter or self.ref_yaw is None or self.ref_t is None:
            self.ref_yaw, self.ref_pitch, self.ref_roll = f_yaw, f_pitch, f_roll
            self.ref_t = f_t
            self.ref_x, self.ref_y = target_pt.x, target_pt.y
            _, _, self.ref_radius = camera_geometry.enclosing_circle(
                camera_geometry.mesh_points(lm, img_w, img_h))
            self.needs_recenter = False
            self._overlay.reset()

        rel_yaw = wrap180(f_yaw - self.ref_yaw)
        rel_pitch = wrap180(f_pitch - self.ref_pitch)
        rel_roll = wrap180(f_roll - self.ref_roll)
        rel_t = tuple(f_t[i] - self.ref_t[i] for i in range(3))

        # AUTO-CENTRADO: cerca del centro, la referencia angular persigue
        # lentamente a la pose actual (corrige los cambios de postura).
        drag = float(self.config.get('t_center_drag', 0.0))
        if drag > 0 and math.hypot(rel_yaw, rel_pitch) < CENTER_DRAG_RADIUS_DEG:
            self.ref_yaw = wrap180(self.ref_yaw + rel_yaw * drag)
            self.ref_pitch = wrap180(self.ref_pitch + rel_pitch * drag)

        self._rel_deg = (rel_yaw, rel_pitch)
        self._rel_cm = rel_t
        with self._hist_lock:
            self._hist.append((now, rel_yaw, rel_pitch))
            self._hist_t.append((now,) + rel_t)

        yaw, pitch = self.compute_output(rel_yaw, rel_pitch, self.config)
        roll = self.compute_roll_output(rel_roll, self.config)
        out_t = self.compute_translation_output(rel_t, self.config)
        self._axes = (yaw, pitch)
        self._head_axes = (yaw, pitch, roll) + out_t

        self._telemetry.log({
            "t_abs": now, "detected": True, "recentered": just_recentered,
            "raw_yaw": raw_yaw, "raw_pitch": raw_pitch, "yaw": yaw, "pitch": pitch,
            "rel_yaw_deg": rel_yaw, "rel_pitch_deg": rel_pitch, "face_width_px": face_width_px,
            "raw_tx": raw_t[0], "raw_ty": raw_t[1], "raw_tz": raw_t[2],
            "comp_tx": comp_t[0], "comp_ty": comp_t[1], "comp_tz": comp_t[2],
            "rel_tx_cm": rel_t[0], "rel_ty_cm": rel_t[1], "rel_tz_cm": rel_t[2],
            "out_tx": out_t[0], "out_ty": out_t[1], "out_tz": out_t[2],
            "raw_roll": raw_roll, "rel_roll_deg": rel_roll, "out_roll": roll,
        })

        if (self.show_debug or self.overlay_enabled) and frame is not None:
            self._draw_debug(frame, lm, R, (rel_yaw, rel_pitch, rel_roll), rel_t)
            self._publish_frame(frame)

    def _draw_debug(self, frame, landmarks, R, rel_deg, rel_cm):
        """Delega el dibujo en `CameraOverlay` (plan_vista_camara.md, Fase 1):
        malla, círculo de distancia, círculo de referencia, recuadro de la
        cara, recuadro de encuadre con aviso, y los 3 ejes desde la glabela.
        El overlay saca la glabela de los propios landmarks."""
        self._overlay.draw(
            frame, landmarks, R,
            self.ref_x, self.ref_y, self.ref_radius,
            rel_deg, rel_cm,
        )

    def _publish_frame(self, frame):
        """Deja el frame anotado a disposición de quien lo mire.

        Una sola asignación del objeto entero: el lector se lleva el
        frame de un momento concreto, nunca uno a medio dibujar. No hace
        falta copiarlo porque cada vuelta del lazo trae un array nuevo:
        `cv2.flip` siempre devuelve uno recién asignado.
        """
        self._frame = frame
        self._frame_count += 1

    def latest_frame(self):
        """`(frame, contador)` del último frame anotado, o `(None, n)` si
        todavía no hay ninguno. El contador solo avanza cuando hubo
        detección nueva, así que quien dibuja compara y se ahorra
        reconvertir la misma imagen una y otra vez."""
        return self._frame, self._frame_count

    def set_overlay_enabled(self, enabled):
        """Enciende o apaga el dibujo del overlay. Apagado no se dibuja
        nada y `latest_frame` deja de avanzar; el seguimiento sigue igual.
        La ventana aparte de depuración manda por su cuenta: si está
        abierta, se dibuja de todos modos."""
        self.overlay_enabled = bool(enabled)
        if not self.overlay_enabled and not self.show_debug:
            self._frame = None
            self._overlay.reset()
        return self.overlay_enabled

    # ------------------------------------------------------------------
    # Matemática de salida (funciones puras, testeables)
    # ------------------------------------------------------------------
    @staticmethod
    def compute_output(rel_yaw_deg, rel_pitch_deg, config):
        """Grados relativos -> salida [-1, 1] por eje.

        1. Se normaliza por el límite calibrado (octágono en grados): en el
           límite de tu rango cómodo la magnitud vale 1.
        2. La sensibilidad es una ganancia posterior: t_sens = 10 -> x1.0
           (el límite calibrado da salida completa); 20 -> x2.0 (salida
           completa a mitad de recorrido). Cambiarla NO obliga a recalibrar.
        """
        n_yaw, n_pitch = HeadTracker._normalize_polygon(
            rel_yaw_deg, rel_pitch_deg, config.get('head_limit_points', [])
        )
        gx = float(config.get('t_sens_x', 10.0)) / 10.0
        gy = float(config.get('t_sens_y', 10.0)) / 10.0
        clamp = lambda v: max(-1.0, min(1.0, v))
        return clamp(n_yaw * gx), clamp(n_pitch * gy)

    @staticmethod
    def compute_roll_output(rel_roll_deg, config):
        """Roll relativo en grados -> salida [-1, 1].

        Límite simétrico en grados (inclinar la cabeza de lado no necesita
        un octágono), zona muerta reescalada y la misma convención de
        ganancia que el resto: t_sens_roll = 10 -> x1.0.
        """
        limit = float(config.get('head_roll_limit_deg', 30.0))
        if limit <= 0:
            limit = 30.0
        n = _clamp(rel_roll_deg / limit)
        g = _clamp(n * float(config.get('t_sens_roll', 10.0)) / 10.0)
        return _deadzone(g, float(config.get('t_roll_deadzone', 0.03)))

    @staticmethod
    def compute_translation_output(rel_cm, config):
        """Traslación relativa en cm -> (tx, ty, tz) en [-1, 1].

        Por eje, en este orden:
        1. Normalización contra el rango calibrado, separando sentido
           positivo y negativo: en TU límite cómodo la salida vale 1.0.
        2. Ganancia (t_trans_sens_*), misma convención que la rotación:
           10 = el rango calibrado da salida completa, 20 = salida completa
           a mitad de recorrido. Cambiarla no obliga a recalibrar.
        3. Zona muerta reescalada, para que no haya salto al salir de ella
           (misma fórmula que physics.rs, en una dimensión).
        4. Curva de respuesta: precisión cerca del centro, tope al final.
        5. Inversión de sentido si el eje va al revés.
        """
        limits = valid_trans_limits(config.get('head_trans_limits', {}))
        out = []
        for i, name in enumerate(("x", "y", "z")):
            value = float(rel_cm[i])
            sense = "pos" if value >= 0 else "neg"
            limit = limits.get(f"{name}_{sense}", DEFAULT_TRANS_LIMIT_CM)

            n = _clamp(value / limit)
            n = _clamp(n * float(config.get(f"t_trans_sens_{name}", 10.0)) / 10.0)
            n = _deadzone(n, float(config.get(f"t_trans_deadzone_{name}", 0.03)))
            n = _curve(n, float(config.get(f"t_trans_curve_{name}", 1.5)))
            if config.get(f"t_trans_invert_{name}", False):
                n = -n
            out.append(n)
        return tuple(out)

    @staticmethod
    def _normalize_polygon(yaw_deg, pitch_deg, points):
        """Normaliza (yaw, pitch) en grados a magnitud <= 1 usando como
        límite radial el octágono calibrado. El límite en un ángulo
        intermedio se interpola linealmente entre los dos puntos
        calibrados más cercanos.

        Con menos de 3 puntos válidos (sin calibrar, o calibración de una
        versión anterior) se usa un rectángulo simétrico de ±35°.
        """
        magnitude = math.hypot(yaw_deg, pitch_deg)
        if magnitude < 1e-9:
            return 0.0, 0.0

        theta_deg = math.degrees(math.atan2(pitch_deg, yaw_deg)) % 360.0
        pts = valid_limit_points(points)

        limit = None
        if len(pts) >= 3:
            pts = sorted(pts, key=lambda p: float(p["angle_deg"]))
            n = len(pts)
            for i in range(n):
                a0 = float(pts[i]["angle_deg"])
                a1 = float(pts[(i + 1) % n]["angle_deg"])
                span = (a1 - a0) % 360.0
                if span <= 1e-6:
                    continue
                offset = (theta_deg - a0) % 360.0
                if offset <= span:
                    m0 = float(pts[i]["magnitude"])
                    m1 = float(pts[(i + 1) % n]["magnitude"])
                    limit = m0 + (m1 - m0) * (offset / span)
                    break

        if not limit or limit <= 0:
            denom = max(abs(math.cos(math.radians(theta_deg))),
                        abs(math.sin(math.radians(theta_deg))), 1e-6)
            limit = DEFAULT_LIMIT_DEG / denom

        scale = min(magnitude / limit, 1.0) / magnitude
        return float(yaw_deg * scale), float(pitch_deg * scale)

    # ------------------------------------------------------------------
    # Calibración
    # ------------------------------------------------------------------
    def window_stats(self, window_s=STABLE_WINDOW_S):
        """Estadística de los últimos `window_s` segundos de ángulo relativo:
        {'n', 'span_s', 'mean_yaw', 'mean_pitch', 'spread', 'stable'}.
        'spread' = distancia máxima (grados) de una muestra a la media.
        """
        now = time.time()
        with self._hist_lock:
            samples = [s for s in self._hist if s[0] >= now - window_s]
        if not samples:
            return {"n": 0, "span_s": 0.0, "mean_yaw": 0.0, "mean_pitch": 0.0,
                    "spread": float("inf"), "stable": False}
        my = sum(s[1] for s in samples) / len(samples)
        mp_ = sum(s[2] for s in samples) / len(samples)
        spread = max(math.hypot(s[1] - my, s[2] - mp_) for s in samples)
        span = samples[-1][0] - samples[0][0]
        stable = (len(samples) >= 5 and span >= window_s * 0.8
                  and spread <= STABLE_SPREAD_DEG and now - samples[-1][0] < 0.2)
        return {"n": len(samples), "span_s": span, "mean_yaw": my, "mean_pitch": mp_,
                "spread": spread, "stable": stable}

    @staticmethod
    def validate_calibration_point(label, yaw_deg, pitch_deg, scales=None):
        """Valida una lectura para el paso `label`. Devuelve un dict:
        {'ok', 'reason': None|'center'|'direction', 'detail', 'angle',
         'angle_scaled', 'magnitude', 'expected', 'scaled'}.

        `angle` SIEMPRE va en grados crudos: es el que se guarda en el
        octágono, y `_normalize_polygon` trabaja en grados crudos. El que
        se valida y se le muestra al usuario es `angle_scaled`, medido en
        el rango propio (ver `direction_scales`).

        Las cardinales no se validan por ángulo sino por dominancia del
        eje esperado, que es indiferente a la anisotropía del cuello.
        """
        magnitude = math.hypot(yaw_deg, pitch_deg)
        angle = math.degrees(math.atan2(pitch_deg, yaw_deg)) % 360.0
        expected = EXPECTED_ANGLES.get(label)
        sign_yaw, sign_pitch = EXPECTED_SIGNS.get(label, (0, 0))
        is_diagonal = label in DIAGONAL_LABELS

        if scales:
            yaw_scale, pitch_scale = scales
            ny, np_ = yaw_deg / yaw_scale, pitch_deg / pitch_scale
            angle_scaled = math.degrees(math.atan2(np_, ny)) % 360.0
            norm = math.hypot(ny, np_)
        else:
            angle_scaled, norm = angle, None

        result = {"ok": False, "reason": None, "detail": None,
                  "angle": angle, "angle_scaled": angle_scaled,
                  "magnitude": magnitude, "expected": expected,
                  "scaled": bool(scales)}

        # 1. ¿Se movió de verdad? Si se conoce el rango propio, el umbral
        #    es una fracción de ese rango: para quien tiene 6° de recorrido
        #    hacia abajo, exigirle 5° absolutos era pedirle casi el tope.
        floor = DIAGONAL_MIN_MAGNITUDE_DEG if is_diagonal else CARDINAL_MIN_MAGNITUDE_DEG
        if norm is not None:
            moved = norm >= MIN_CALIB_NORM_FRACTION and magnitude >= floor
        else:
            moved = magnitude >= (MIN_CALIB_MAGNITUDE_DEG if is_diagonal else floor)
        if not moved:
            result["reason"] = "center"
            return result

        # 2. ¿Hacia el lado correcto? Vale para cardinales y diagonales.
        for value, sign in ((yaw_deg, sign_yaw), (pitch_deg, sign_pitch)):
            if sign and value * sign <= 0:
                result["reason"] = "direction"
                result["detail"] = "sign"
                return result

        # 3. La forma del movimiento.
        if is_diagonal:
            if expected is not None and \
                    angle_distance(angle_scaled, expected) > ANGLE_TOLERANCE_DEG:
                result["reason"] = "direction"
                result["detail"] = "angle"
                return result
        else:
            main, other = (abs(yaw_deg), abs(pitch_deg)) if sign_yaw \
                else (abs(pitch_deg), abs(yaw_deg))
            if main < other * DOMINANT_AXIS_RATIO:
                result["reason"] = "direction"
                result["detail"] = "dominance"
                return result

        result["ok"] = True
        return result

    def direction_scales(self):
        """El rango propio ya medido, para validar las diagonales."""
        return direction_scales(self.config.get("head_limit_points", []))

    def calibrate_direction(self, label, yaw_deg=None, pitch_deg=None):
        """Guarda el límite para la dirección `label` a partir de una lectura
        en grados (por defecto, la media de la ventana de estabilidad).
        Rechaza lecturas demasiado cerca del centro o en una dirección que
        no corresponde al paso. Devuelve el dict de validate_calibration_point.
        """
        if yaw_deg is None or pitch_deg is None:
            stats = self.window_stats()
            yaw_deg, pitch_deg = stats["mean_yaw"], stats["mean_pitch"]

        result = self.validate_calibration_point(
            label, yaw_deg, pitch_deg, self.direction_scales())
        if not result["ok"]:
            return result

        # Se descartan los puntos de la misma etiqueta y los de versiones
        # anteriores (otras unidades): no se pueden mezclar.
        points = [
            p for p in self.config.get("head_limit_points", [])
            if p.get("label") != label and p.get("units") == CALIB_UNITS
        ]
        points.append({
            "label": label,
            "angle_deg": result["angle"],
            "magnitude": result["magnitude"],
            "units": CALIB_UNITS,
        })
        self.config["head_limit_points"] = points
        return result

    # ------------------------------------------------------------------
    # Calibración de traslación
    # ------------------------------------------------------------------
    def trans_window_stats(self, window_s=STABLE_WINDOW_S):
        """Igual que window_stats() pero sobre la traslación relativa en cm:
        {'n', 'span_s', 'mean' (3 valores), 'spread', 'stable'}.
        'spread' = distancia máxima (cm) de una muestra a la media."""
        now = time.time()
        with self._hist_lock:
            samples = [s for s in self._hist_t if s[0] >= now - window_s]
        if not samples:
            return {"n": 0, "span_s": 0.0, "mean": (0.0, 0.0, 0.0),
                    "spread": float("inf"), "stable": False}
        mean = tuple(sum(s[i + 1] for s in samples) / len(samples) for i in range(3))
        spread = max(
            math.sqrt(sum((s[i + 1] - mean[i]) ** 2 for i in range(3)))
            for s in samples
        )
        span = samples[-1][0] - samples[0][0]
        stable = (len(samples) >= 5 and span >= window_s * 0.8
                  and spread <= STABLE_TRANS_SPREAD_CM and now - samples[-1][0] < 0.2)
        return {"n": len(samples), "span_s": span, "mean": mean,
                "spread": spread, "stable": stable}

    @staticmethod
    def validate_trans_calibration_point(step, rel_cm):
        """Valida una lectura de traslación para el paso `step` del
        asistente ('x_pos', 'z_neg', ...). Devuelve un dict:
        {'ok', 'reason': None|'center'|'axis'|'step', 'magnitude',
         'dominant', 'expected_axis'}.

        Se rechaza si la cabeza casi no se movió, o si el eje que más
        cambió no es el del paso: si te inclinas a la izquierda y lo que
        más cambia es la profundidad, la lectura no sirve.
        """
        spec = TRANS_STEPS.get(step)
        values = [float(v) for v in rel_cm]
        magnitudes = [abs(v) for v in values]
        dominant = max(range(3), key=lambda i: magnitudes[i])
        result = {"ok": False, "reason": None, "magnitude": 0.0,
                  "dominant": dominant, "expected_axis": None}
        if spec is None:
            result["reason"] = "step"
            return result

        axis, sign = spec
        result["expected_axis"] = axis
        result["magnitude"] = magnitudes[axis]

        others = max(magnitudes[i] for i in range(3) if i != axis)
        if magnitudes[axis] < MIN_CALIB_TRANS_CM:
            result["reason"] = "center"
        elif magnitudes[axis] < others * DOMINANT_AXIS_RATIO:
            result["reason"] = "axis"
        elif (values[axis] >= 0) != (sign > 0):
            # El eje correcto pero hacia el otro lado: la lectura es
            # válida en magnitud, y lo que hay que corregir es el sentido
            # del eje (t_trans_invert_*), no la calibración.
            result["reason"] = "axis"
        else:
            result["ok"] = True
        return result

    def calibrate_translation(self, step, rel_cm=None):
        """Guarda el límite del paso `step` a partir de una lectura en cm
        (por defecto, la media de la ventana de estabilidad). Devuelve el
        dict de validate_trans_calibration_point."""
        if rel_cm is None:
            rel_cm = self.trans_window_stats()["mean"]

        result = self.validate_trans_calibration_point(step, rel_cm)
        if not result["ok"]:
            return result

        limits = self.config.get("head_trans_limits")
        # Si venía de otra versión (otras unidades), se empieza de cero:
        # mezclar escalas daría un rango sin sentido.
        if not isinstance(limits, dict) or limits.get("units") != TRANS_CALIB_UNITS:
            limits = {"units": TRANS_CALIB_UNITS}
        else:
            limits = dict(limits)
        limits[step] = result["magnitude"]
        self.config["head_trans_limits"] = limits
        return result

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def get_head_axes(self):
        """Los 6 ejes normalizados en el orden que emite el motor:
        (yaw, pitch, roll, tx, ty, tz)."""
        if not self.running:
            return (0.0,) * 6
        return self._head_axes

    def get_relative_cm(self):
        """Traslación relativa al centro, compensada y filtrada, en cm.
        Es lo que consume el asistente de calibración."""
        return self._rel_cm

    def get_axes(self):
        """Solo la rotación (yaw, pitch), como siempre: la usa la vista
        previa de la GUI. El motor usa get_head_axes()."""
        if not self.running:
            return 0.0, 0.0
        return self._axes

    def get_relative_degrees(self):
        return self._rel_deg

    def recenter(self):
        self.needs_recenter = True

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self._telemetry.close()
