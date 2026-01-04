import json
import os
# Importamos la ruta absoluta desde paths.py
from utils.utils import CONFIG_FILE 

DEFAULT_CONFIG = {
    'radius': 320, 'curve': 2.0, 'deadzone': 0.05, 'snap': 0.08, 'outer': 60,
    't_sens_x': 7.0, 't_sens_y': 5.0, 't_smooth': 0.5, 't_deadzone': 0.02,
    't_snap_axis': 0.25, 't_snap_diag': 0.15
}

def load_config():
    # Usamos CONFIG_FILE (Path object)
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"[CONFIG] Guardada en: {CONFIG_FILE}")
    except Exception as e:
        print(f"[CONFIG] Error guardando: {e}")