"""Graba los ejes de un joystick (real o virtual) a CSV, leyendo evdev.

Sirve para comparar nuestra salida contra la de OpenTrack en igualdad de
condiciones: en vez de comparar la telemetría interna del tracker (que en
modo externo no existe, porque la cámara la usa OpenTrack), se graba lo que
el dispositivo PUBLICA. Mismas unidades, mismo muestreo, misma métrica para
los dos.

Uso:
    uv run python src/experiments/record_axes.py --list
    uv run python src/experiments/record_axes.py --device "Virtual Head" --seconds 60
    uv run python src/experiments/record_axes.py --device "opentrack" --seconds 60 \\
        --out src/logs/axes_opentrack.csv

Protocolo para que la comparación valga: la MISMA secuencia de movimientos
en las dos grabaciones. Por ejemplo 20 s quieto, 5 giros rápidos de lado a
lado, 5 asomadas rápidas a cada lado, y otros 10 s quieto.
"""
import argparse
import csv
import os
import select
import time

from evdev import InputDevice, ecodes, list_devices

# Nombre corto de cada código de eje, para las columnas del CSV.
AXIS_NAMES = {
    ecodes.ABS_X: "x",
    ecodes.ABS_Y: "y",
    ecodes.ABS_Z: "z",
    ecodes.ABS_RX: "rx",
    ecodes.ABS_RY: "ry",
    ecodes.ABS_RZ: "rz",
    ecodes.ABS_THROTTLE: "throttle",
    ecodes.ABS_RUDDER: "rudder",
    ecodes.ABS_HAT0X: "hat_x",
    ecodes.ABS_HAT0Y: "hat_y",
}


def normalize_abs(value, minimum, maximum):
    """Lleva el valor crudo de un eje a -1..1 según su rango declarado.

    Los dispositivos no comparten escala (el nuestro usa ±32767, otro puede
    usar 0..255), así que sin normalizar las métricas no se pueden comparar.
    Un rango degenerado devuelve 0.0 en vez de dividir por cero.
    """
    minimum, maximum = float(minimum), float(maximum)
    span = maximum - minimum
    if span <= 0:
        return 0.0
    # Centro del rango declarado, no 0: hay ejes que van de 0 a 255.
    center = (maximum + minimum) / 2.0
    return max(-1.0, min(1.0, (float(value) - center) / (span / 2.0)))


def pick_device(devices, pattern):
    """Elige el dispositivo cuyo nombre contiene `pattern` (sin distinguir
    mayúsculas). `devices` es una lista de (ruta, nombre).

    Devuelve (ruta, nombre). Si hay varios candidatos se queda con el
    primero; si no hay ninguno, lanza SystemExit con un mensaje útil.
    """
    needle = (pattern or "").lower()
    matches = [(path, name) for path, name in devices if needle in name.lower()]
    if not matches:
        available = "\n".join(f"   {name}  ({path})" for path, name in devices)
        raise SystemExit(f"[ERROR] Ningún dispositivo contiene '{pattern}'.\n"
                         f"Dispositivos visibles:\n{available or '   (ninguno)'}")
    return matches[0]


def _devices():
    out = []
    for path in sorted(list_devices()):
        try:
            dev = InputDevice(path)
        except Exception:
            continue
        out.append((path, dev.name))
        dev.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="lista los dispositivos y sale")
    ap.add_argument("--device", help="parte del nombre del dispositivo a grabar")
    ap.add_argument("--seconds", type=float, default=60.0, help="duración (0 = hasta Ctrl+C)")
    ap.add_argument("--out", help="CSV de salida (por defecto en src/logs/)")
    ap.add_argument("--hz", type=float, default=100.0, help="frecuencia de muestreo")
    args = ap.parse_args()

    devices = _devices()
    if args.list or not args.device:
        print("Dispositivos de entrada visibles:")
        for path, name in devices:
            print(f"   {name}  ({path})")
        if not args.device:
            print("\nPasa --device con parte del nombre para grabar.")
        return

    path, name = pick_device(devices, args.device)
    dev = InputDevice(path)
    print(f"[OK] Grabando '{name}' ({path})")

    capabilities = dev.capabilities().get(ecodes.EV_ABS, [])
    axes = []
    for code, absinfo in capabilities:
        axes.append((code, AXIS_NAMES.get(code, f"abs{code}"), absinfo.min, absinfo.max))
    if not axes:
        raise SystemExit("[ERROR] Ese dispositivo no publica ejes absolutos.")
    print("     Ejes: " + ", ".join(f"{n} [{lo}..{hi}]" for _, n, lo, hi in axes))

    out_path = args.out
    if not out_path:
        logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
        os.makedirs(logs, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in name)[:40]
        out_path = os.path.join(logs, f"axes_{safe}_{time.strftime('%Y%m%d_%H%M%S')}.csv")

    columns = ["t_abs"] + [n for _, n, _, _ in axes]
    values = {n: 0.0 for _, n, _, _ in axes}
    # Estado inicial real del dispositivo: sin esto, los ejes que no se
    # muevan durante la grabación quedarían en 0 aunque estén desplazados.
    for code, n, lo, hi in axes:
        try:
            values[n] = normalize_abs(dev.absinfo(code).value, lo, hi)
        except Exception:
            pass

    by_code = {code: (n, lo, hi) for code, n, lo, hi in axes}
    period = 1.0 / max(args.hz, 1.0)
    deadline = time.time() + args.seconds if args.seconds > 0 else float("inf")
    n_rows = 0
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        print(f"[OK] Escribiendo {out_path}  (Ctrl+C para cortar)")
        try:
            while time.time() < deadline:
                # Drenar todo lo pendiente sin bloquear, y muestrear a ritmo fijo.
                while select.select([dev.fd], [], [], 0)[0]:
                    for event in dev.read():
                        if event.type == ecodes.EV_ABS and event.code in by_code:
                            n, lo, hi = by_code[event.code]
                            values[n] = normalize_abs(event.value, lo, hi)
                row = {"t_abs": time.time()}
                row.update(values)
                writer.writerow(row)
                n_rows += 1
                if n_rows % 500 == 0:
                    f.flush()
                time.sleep(period)
        except KeyboardInterrupt:
            print("\n[OK] Cortado con Ctrl+C.")
    print(f"[OK] {n_rows} muestras en {out_path}")


if __name__ == "__main__":
    main()
