import json
from utils.utils import CONFIG_FILE

DEFAULT_CONFIG = {
    'radius': 320,
    'curve': 2.0,
    'deadzone': 0.05,
    'snap': 0.08,
    'outer': 60,
    't_sens_x': 10.0,
    't_sens_y': 10.0,
    # Filtro One Euro del tracker (en grados)
    't_min_cutoff': 1.0,
    't_beta': 0.05,
    't_deadzone': 0.02,
    't_snap_axis': 0.25,
    't_snap_outer': 0.10,
    't_center_drag': 0.0,
    'cam_rotation': 0,

    # --- TRASLACIÓN (6DOF) -------------------------------------------
    # Rango real de cada eje y sentido, en cm, medido con el asistente de
    # calibración. 0 = sin calibrar -> se usa DEFAULT_TRANS_LIMIT_CM.
    # 'units' marca las unidades igual que head_limit_points: si cambian,
    # los valores viejos se ignoran en vez de interpretarse mal.
    'head_trans_limits': {
        'units': 'cm',
        'x_pos': 0.0, 'x_neg': 0.0,
        'y_pos': 0.0, 'y_neg': 0.0,
        'z_pos': 0.0, 'z_neg': 0.0,
    },
    # Ganancia posterior, misma convención que t_sens_x/y:
    # 10 = el rango calibrado da salida completa; 20 = salida completa a
    # mitad de recorrido. Cambiarla NO obliga a recalibrar.
    't_trans_sens_x': 10.0, 't_trans_sens_y': 10.0, 't_trans_sens_z': 10.0,
    # Zona muerta por eje, en fracción de la salida (se reescala, sin salto).
    # La profundidad necesita más: respirar ya mueve el valor.
    't_trans_deadzone_x': 0.03, 't_trans_deadzone_y': 0.03, 't_trans_deadzone_z': 0.06,
    # Curva de respuesta por eje (exponente, como la del stick): >1 da
    # precisión cerca del centro y llega al tope al final del recorrido.
    't_trans_curve_x': 1.5, 't_trans_curve_y': 1.5, 't_trans_curve_z': 1.5,
    # Sentido de cada eje. Depende de la orientación de la cámara y del
    # sistema de coordenadas de MediaPipe, así que se verifica en el
    # asistente: si al inclinarte a la derecha el eje va al revés, se
    # invierte aquí. 'y' arranca invertido porque el eje vertical de la
    # imagen crece hacia abajo.
    't_trans_invert_x': False, 't_trans_invert_y': True, 't_trans_invert_z': False,
    # Filtro One Euro propio de la traslación (sobre los cm), separado del
    # de la rotación. La profundidad va más suavizada: es el eje más ruidoso.
    't_trans_min_cutoff': 0.8, 't_trans_beta': 0.02,
    't_trans_min_cutoff_z': 0.4, 't_trans_beta_z': 0.01,
    # Pivote del cuello respecto a la cara, en cm (alto y fondo). Sirve
    # para que girar la cabeza no desplace la cámara: ver compensate_neck().
    't_neck_height_cm': 10.0, 't_neck_depth_cm': 10.0,

    # --- ROLL --------------------------------------------------------
    # MediaPipe ya entrega el roll; el límite es simétrico en grados
    # (inclinar la cabeza de lado no necesita un octágono).
    't_sens_roll': 10.0,
    't_roll_deadzone': 0.03,
    'head_roll_limit_deg': 30.0,
    # Fuente de los ejes de cabeza que emite ESTE programa:
    #   'internal' -> la cámara propia (MediaPipe), como hasta ahora.
    #   'external' -> otro programa (OpenTrack) publica su propio joystick;
    #                 aquí no se abre la cámara y los ejes de cabeza quedan
    #                 centrados. Es lo que permite que ambos convivan.
    'head_source': 'internal',
    'controller_profile': 'thrustmaster_t16000m',
    'button_map': {},
    'telemetry_enabled': False,
    'head_limit_points': [],
    'keyboard_phys': '',
    'mouse_phys': '',
}

# Claves de versiones anteriores que ya no se usan. Se eliminan al cargar
# para que no se sigan arrastrando en cada guardado.
#  - t_smooth: era el 'beta' del filtro en unidades escaladas por la
#    sensibilidad; se reemplazó por t_min_cutoff + t_beta (en grados).
#    No se copia su valor porque las unidades cambiaron.
#  - *_limit_pos/neg: límites rectangulares del sistema de calibración viejo.
LEGACY_KEYS = (
    't_smooth',
    'yaw_limit_pos', 'yaw_limit_neg', 'pitch_limit_pos', 'pitch_limit_neg',
)


def _migrate(cfg):
    for k in LEGACY_KEYS:
        cfg.pop(k, None)
    merged = DEFAULT_CONFIG.copy()
    merged['button_map'] = {}
    merged['head_limit_points'] = []
    # Copia propia: si no, todas las configuraciones cargadas comparten el
    # mismo dict y calibrar una modificaría las demás.
    merged['head_trans_limits'] = dict(DEFAULT_CONFIG['head_trans_limits'])
    merged.update(cfg)
    return merged


def load_config():
    if not CONFIG_FILE.exists():
        return _migrate({})
    try:
        with open(CONFIG_FILE, 'r') as f:
            return _migrate(json.load(f))
    except Exception as e:
        print(f"[CONFIG] No se pudo leer {CONFIG_FILE} ({e}); usando valores por defecto.")
        return _migrate({})


def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"[CONFIG] Guardada en: {CONFIG_FILE}")
    except Exception as e:
        print(f"[CONFIG] Error guardando: {e}")
