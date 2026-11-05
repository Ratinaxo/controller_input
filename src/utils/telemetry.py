import csv
import time
from pathlib import Path

# src/utils/telemetry.py -> sube un nivel a src/, guarda en src/logs/
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


class CsvLogger:
    """Logger de telemetría para sesiones reales (no experimentos
    desechables). Escribe en buffer y hace flush cada `flush_every` filas
    para no pegarle un syscall de disco a cada tick del loop de control.

    Se activa/desactiva explícitamente con el parámetro `enabled` -- lo
    controla el checkbox "Grabar telemetría" de la GUI (guardado en
    config.json como 'telemetry_enabled'), no una variable de entorno:
    la idea es poder prenderlo/apagarlo antes de volar sin tener que
    relanzar el proceso desde la terminal con un env var seteado.

    Si enabled=False, todos los métodos son no-ops baratos (un chequeo
    de bool), así que es seguro dejar las llamadas a .log() en el
    código de producción sin preocuparse por el costo cuando está
    apagado.
    """

    def __init__(self, name, fieldnames, enabled=False, flush_every=50):
        self.enabled = bool(enabled)
        self._writer = None
        self._file = None
        self._count = 0
        self._flush_every = flush_every

        if not self.enabled:
            return

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = LOGS_DIR / f"{name}_{ts}.csv"
        self._file = open(path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=fieldnames)
        self._writer.writeheader()
        print(f"[TELEMETRY] Grabando '{name}' en {path}", flush=True)

    def log(self, row):
        if not self.enabled:
            return
        self._writer.writerow(row)
        self._count += 1
        if self._count % self._flush_every == 0:
            self._file.flush()

    def close(self):
        if not self.enabled or self._file is None:
            return
        try:
            self._file.flush()
            self._file.close()
        except Exception:
            pass
