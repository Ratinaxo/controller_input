"""Diagnóstico: ¿por qué el juego no ve un dispositivo virtual?

Revisa los dispositivos de este programa (stick y cabeza) y los de OpenTrack,
y para cada uno informa:

  - cómo lo clasificó udev DE VERDAD (ID_INPUT_JOYSTICK, ID_INPUT_ACCELEROMETER...),
    leído de /run/udev/data/, y cómo lo predice la regla de systemd;
  - si tiene nodo /dev/input/jsN (API de joystick clásica);
  - si este usuario puede abrirlo;
  - con --watch, si sus ejes se mueven de verdad.

Hay que correrlo CON EL MOTOR EN MARCHA (después de «INICIAR VUELO»), porque
los dispositivos virtuales solo existen mientras el motor corre:

    uv run python src/experiments/diagnose_input.py
    uv run python src/experiments/diagnose_input.py --watch 15   # mueve la cabeza

El informe también queda en src/logs/diagnose_<fecha>.txt.
"""
import argparse
import glob
import os
import select
import sys
import time

# Códigos del kernel (linux/input-event-codes.h). Se escriben aquí para que
# las funciones puras no dependan de evdev y se puedan probar sin hardware.
EV_KEY = 0x01
ABS_X, ABS_Y, ABS_Z, ABS_RX = 0x00, 0x01, 0x02, 0x03
ABS_PRESSURE = 0x18
BTN_MOUSE_FIRST, BTN_MOUSE_LAST = 0x110, 0x112      # BTN_LEFT..BTN_MIDDLE
BTN_JOYSTICK, BTN_DIGI = 0x120, 0x140
BTN_TOOL_PEN, BTN_STYLUS, BTN_TOUCH = 0x140, 0x14b, 0x14a
BTN_TRIGGER_HAPPY1, BTN_TRIGGER_HAPPY40 = 0x2c0, 0x2e7
INPUT_PROP_ACCELEROMETER = 0x06

OUR_DEVICES = ("Thrustmaster T.16000M (Rust Thread)", "Virtual Head Tracker (Rust Thread)")
HEAD_DEVICE = OUR_DEVICES[1]
OTHER_HINTS = ("opentrack",)


def predict_udev_class(key_codes, abs_codes, props=()):
    """Réplica de la parte de `udev-builtin-input_id` (systemd) que decide
    entre acelerómetro, joystick, mouse, etc.

    La regla que importa aquí: un dispositivo SIN teclas con ABS_X + ABS_Y
    + ABS_Z es un ACELERÓMETRO, y esa regla se evalúa ANTES que la de
    joystick. Así se veía el dispositivo de cabeza de la Fase A.

    Es una predicción: lo que cuenta es lo que diga udev (read_udev_props).
    """
    keys = set(key_codes)
    axes = set(abs_codes)
    has_keys = bool(keys)
    has_abs = ABS_X in axes and ABS_Y in axes
    has_3d = has_abs and ABS_Z in axes

    if INPUT_PROP_ACCELEROMETER in set(props) or (not has_keys and has_3d):
        return "accelerometer"

    has_joystick = (
        any(BTN_JOYSTICK <= k < BTN_DIGI for k in keys)
        or any(BTN_TRIGGER_HAPPY1 <= k <= BTN_TRIGGER_HAPPY40 for k in keys)
        or any(ABS_RX <= a < ABS_PRESSURE for a in axes)
    )
    if has_abs:
        if BTN_STYLUS in keys or BTN_TOOL_PEN in keys:
            return "tablet"
        if any(BTN_MOUSE_FIRST <= k <= BTN_MOUSE_LAST for k in keys):
            return "mouse"
        if BTN_TOUCH in keys:
            return "touchscreen"
    return "joystick" if has_joystick else "other"


def parse_udev_data(text):
    """Propiedades E:CLAVE=VALOR de un archivo de /run/udev/data/."""
    props = {}
    for line in text.splitlines():
        if line.startswith("E:") and "=" in line:
            key, _, value = line[2:].partition("=")
            props[key] = value
    return props


def udev_verdict(props):
    """Resume las propiedades ID_INPUT_* en una palabra."""
    for key, name in (("ID_INPUT_JOYSTICK", "joystick"),
                      ("ID_INPUT_ACCELEROMETER", "accelerometer"),
                      ("ID_INPUT_MOUSE", "mouse"),
                      ("ID_INPUT_TOUCHSCREEN", "touchscreen"),
                      ("ID_INPUT_TABLET", "tablet"),
                      ("ID_INPUT_KEYBOARD", "keyboard")):
        if props.get(key) == "1":
            return name
    return "sin clasificar" if props else "desconocido"


def read_udev_props(event_path):
    """Propiedades de udev de /dev/input/eventN, o {} si no se pueden leer."""
    try:
        st = os.stat(event_path)
        major, minor = os.major(st.st_rdev), os.minor(st.st_rdev)
        with open(f"/run/udev/data/c{major}:{minor}") as f:
            return parse_udev_data(f.read())
    except OSError:
        return {}


def js_node(event_path):
    event = os.path.basename(event_path)
    nodes = glob.glob(f"/sys/class/input/{event}/device/js*")
    return "/dev/input/" + os.path.basename(nodes[0]) if nodes else None


def code_name(table, code):
    """Nombre de un código evdev (algunos tienen varios alias: el primero)."""
    name = table.get(code, code)
    return name[0] if isinstance(name, (list, tuple)) else name


def describe(dev, ecodes):
    caps = dev.capabilities()
    keys = list(caps.get(ecodes.EV_KEY, []))
    abs_items = caps.get(ecodes.EV_ABS, [])
    abs_codes = [code for code, _ in abs_items]
    try:
        props = list(dev.input_props())
    except Exception:
        props = []
    udev = read_udev_props(dev.path)
    info = dev.info
    return {
        "name": dev.name,
        "path": dev.path,
        "id": f"bus=0x{info.bustype:04x} vendor=0x{info.vendor:04x} product=0x{info.product:04x}",
        "keys": len(keys),
        "abs": [code_name(ecodes.ABS, c) for c in abs_codes],
        "abs_codes": abs_codes,
        "predicted": predict_udev_class(keys, abs_codes, props),
        "udev": udev_verdict(udev),
        "udev_props": {k: v for k, v in udev.items() if k.startswith("ID_INPUT")},
        "js": js_node(dev.path),
        "readable": os.access(dev.path, os.R_OK),
    }


def watch(dev, ecodes, seconds):
    """Mínimo y máximo de cada eje durante `seconds`."""
    ranges = {}
    for code, absinfo in dev.capabilities().get(ecodes.EV_ABS, []):
        ranges[code] = [absinfo.value, absinfo.value, 0]
    deadline = time.time() + seconds
    while time.time() < deadline:
        if select.select([dev.fd], [], [], 0.1)[0]:
            for ev in dev.read():
                if ev.type == ecodes.EV_ABS and ev.code in ranges:
                    r = ranges[ev.code]
                    r[0], r[1], r[2] = min(r[0], ev.value), max(r[1], ev.value), r[2] + 1
    return ranges


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", type=float, default=0.0,
                    help="segundos leyendo el dispositivo de cabeza (mueve la cabeza)")
    args = ap.parse_args()

    from evdev import InputDevice, ecodes, list_devices

    lines = []
    out = lambda s="": (print(s), lines.append(s))

    found = []
    for path in sorted(list_devices()):
        try:
            dev = InputDevice(path)
        except Exception:
            continue
        if dev.name in OUR_DEVICES or any(h in dev.name.lower() for h in OTHER_HINTS):
            found.append(dev)

    out(f"Diagnóstico de dispositivos virtuales — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out()
    if not any(d.name == HEAD_DEVICE for d in found):
        out(f"⚠ NO existe «{HEAD_DEVICE}».")
        out("  ¿Está el motor en marcha (después de INICIAR VUELO) y la fuente de")
        out("  cabeza en «Cámara propia»? Con fuente externa no se crea.")
        out()

    for dev in found:
        d = describe(dev, ecodes)
        out(f"■ {d['name']}  ({d['path']})")
        out(f"    {d['id']}")
        out(f"    ejes: {', '.join(map(str, d['abs']))}   botones: {d['keys']}")
        out(f"    clasificación udev: {d['udev']}   (la regla predice: {d['predicted']})")
        if d["udev_props"]:
            out(f"    propiedades: {' '.join(f'{k}={v}' for k, v in sorted(d['udev_props'].items()))}")
        out(f"    nodo js: {d['js'] or 'ninguno'}   este usuario puede leerlo: "
            f"{'sí' if d['readable'] else 'NO'}")
        if d["udev"] == "accelerometer" or d["predicted"] == "accelerometer":
            out("    ✗ Se ve como ACELERÓMETRO, no como joystick: el juego no lo va a")
            out("      listar. Es el dispositivo de cabeza sin botones de la Fase A:")
            out("      recompila el módulo Rust (ahora declara un botón).")
        elif d["udev"] == "joystick":
            out("    ✓ Es un joystick para el sistema.")
        if not d["readable"]:
            out("    ✗ Este usuario no puede abrirlo: el juego (que corre como este")
            out("      usuario) tampoco. Revisa el grupo 'input' o las reglas uaccess.")
        out()

        if args.watch > 0 and dev.name == HEAD_DEVICE:
            out(f"    Leyendo {args.watch:.0f} s: mueve la cabeza…")
            ranges = watch(dev, ecodes, args.watch)
            moved = False
            for code, (lo, hi, n) in ranges.items():
                name = code_name(ecodes.ABS, code)
                mark = "✓" if hi - lo > 2000 else "·"
                moved |= hi - lo > 2000
                out(f"      {mark} {name:<7} min {lo:>7}  max {hi:>7}  eventos {n}")
            if not moved:
                out("    ✗ Ningún eje se movió de verdad. Si el dispositivo es joystick y")
                out("      aun así no se mueve, el tracker del motor no está leyendo la")
                out("      cámara: revisa la consola del motor.")
            out()

    logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(logs, exist_ok=True)
    report = os.path.join(logs, f"diagnose_{time.strftime('%Y%m%d_%H%M%S')}.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] Informe guardado en {os.path.normpath(report)}")


if __name__ == "__main__":
    sys.exit(main())
