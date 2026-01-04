from pathlib import Path
import sys

# 1. Definir la raíz del código fuente (src/)
# Estructura: src/utils/paths.py
# .parent -> src/utils
# .parent.parent -> src/
SRC_DIR = Path(__file__).resolve().parent.parent

# 2. Definir rutas absolutas a carpetas clave
# Esto ayuda a que Python encuentre los módulos sin importar desde dónde lanzas el script
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# 3. Rutas a los Scripts Ejecutables (Para el Supervisor)
GUI_SCRIPT = SRC_DIR / "gui_app.py"
MOTOR_SCRIPT = SRC_DIR / "motor_app.py"

# 4. Rutas de Datos y Modelos
# Asumimos que models está en src/models/
MODELS_DIR = SRC_DIR / "models"
MODEL_PATH = MODELS_DIR / "face_landmarker.task"

# 5. Ruta del archivo de configuración (JSON)
CONFIG_FILE = SRC_DIR / "config" / "config1.json"

# --- Debug (Opcional, se ejecuta solo si corres este archivo directamente) ---
if __name__ == "__main__":
    print(f"--- PATH DEBUG ---")
    print(f"SRC ROOT:   {SRC_DIR}")
    print(f"GUI Script: {GUI_SCRIPT}")
    print(f"Modelo IA:  {MODEL_PATH}")
    print(f"Existe IA?: {MODEL_PATH.exists()}")