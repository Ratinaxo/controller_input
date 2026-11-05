import json
from pathlib import Path

# src/utils/controllers.py -> sube dos niveles a src/, entra a config/controllers
CONTROLLERS_DIR = Path(__file__).resolve().parent.parent / "config" / "controllers"

DEFAULT_CONTROLLER_ID = "thrustmaster_t16000m"


def list_controllers():
    """Escanea src/config/controllers/*.json y devuelve una lista de
    {'id':..., 'display_name':...} para poblar el selector de la GUI.
    Un perfil roto o ilegible se ignora en vez de tumbar la GUI."""
    result = []
    if not CONTROLLERS_DIR.exists():
        return result

    for path in sorted(CONTROLLERS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            result.append({
                'id': data.get('id', path.stem),
                'display_name': data.get('display_name', path.stem),
            })
        except Exception as e:
            print(f"[CONTROLLERS] Perfil inválido ignorado ({path.name}): {e}")
            continue

    return result


def load_controller(controller_id):
    """Carga el perfil completo (ejes, hat, botones) por su id.
    Lanza FileNotFoundError si el id no corresponde a ningún JSON."""
    path = CONTROLLERS_DIR / f"{controller_id}.json"
    with open(path, 'r') as f:
        return json.load(f)


def get_button_entry(profile, button_id):
    """Busca dentro de profile['buttons'] la entrada con ese id
    (acepta int o str) y devuelve el dict {'id', 'code', 'name'} o None."""
    try:
        button_id = int(button_id)
    except (TypeError, ValueError):
        return None
    for entry in profile.get('buttons', []):
        if entry.get('id') == button_id:
            return entry
    return None


def resolve_code(code, ecodes=None):
    """Convierte el 'code' de un perfil a número evdev.

    Acepta:
      - un entero (0x120 o 288),
      - un string hexadecimal o decimal ("0x12c", "300") para los códigos
        que no tienen nombre en evdev (0x12C–0x12E en el T.16000M),
      - un nombre evdev ("BTN_TRIGGER"), resuelto con el módulo `ecodes`
        de python-evdev.

    Devuelve None si no se puede resolver.
    """
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if not isinstance(code, str):
        return None
    text = code.strip()
    try:
        return int(text, 0)
    except ValueError:
        pass
    if ecodes is None:
        try:
            from evdev import ecodes as _ecodes
            ecodes = _ecodes
        except ImportError:
            return None
    value = getattr(ecodes, text, None)
    return value if isinstance(value, int) else None


def code_name(code, ecodes=None):
    """Nombre legible de un código evdev de tecla/botón (ej. 'KEY_1',
    'BTN_LEFT'). Si no tiene nombre, devuelve el hexadecimal."""
    if ecodes is None:
        try:
            from evdev import ecodes as _ecodes
            ecodes = _ecodes
        except ImportError:
            return hex(code)
    for table in (getattr(ecodes, 'KEY', {}), getattr(ecodes, 'BTN', {})):
        name = table.get(code)
        if name:
            if isinstance(name, (list, tuple)):
                name = name[0]
            return name
    return hex(code)
