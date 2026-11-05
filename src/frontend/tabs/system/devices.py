"""Lista de dispositivos de entrada para elegir mouse y teclado."""
import re


def get_device_list():
    """Dispositivos de entrada, etiquetados por tipo, con su ruta física.

    Formato de cada entrada:  [TAG] Nombre (ruta_física) [/dev/input/...]
    Los de tipo «botones/sistema» van al final.
    """
    import evdev
    devices_info = []

    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            caps = dev.capabilities()

            is_mouse = False
            is_keyboard = False

            if evdev.ecodes.EV_REL in caps:
                rel_caps = caps[evdev.ecodes.EV_REL]
                if evdev.ecodes.REL_X in rel_caps and evdev.ecodes.REL_Y in rel_caps:
                    is_mouse = True

            if evdev.ecodes.EV_KEY in caps:
                key_caps = caps[evdev.ecodes.EV_KEY]
                if evdev.ecodes.KEY_A in key_caps or evdev.ecodes.KEY_ENTER in key_caps:
                    is_keyboard = True

            if is_mouse and is_keyboard:
                tag = "[SENSOR + TECLAS] "
            elif is_mouse:
                tag = "[SENSOR MOUSE] "
            elif is_keyboard:
                tag = "[TECLADO FÍSICO] "
            else:
                tag = "[BOTONES/SISTEMA] "

            phys = dev.phys if dev.phys else "RutaFisicaDesconocida"
            devices_info.append(f"{tag}{dev.name} ({phys}) [{path}]")
        except Exception:
            pass

    return sorted(devices_info, key=lambda x: "[BOTONES" in x)


def phys_from_entry(entry):
    """Extrae la ruta física (lo que está entre paréntesis) de una entrada
    de get_device_list(), o None si no tiene."""
    match = re.search(r'\((.*?)\)', entry or "")
    return match.group(1).strip() if match else None


def select_by_phys(combo, phys):
    """Selecciona en `combo` la entrada cuya ruta física es `phys`."""
    if not phys:
        return
    for val in combo['values']:
        if f"({phys})" in val:
            combo.set(val)
            break
