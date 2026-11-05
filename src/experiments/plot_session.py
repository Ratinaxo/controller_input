"""
Analiza una sesión real grabada con AEROCTRL_LOG=1 (ver utils/telemetry.py).

Busca automáticamente el par de logs más reciente en src/logs/
(tracker_*.csv + engine_*.csv) salvo que se le pasen rutas explícitas.

Uso:
    uv run python src/experiments/plot_session.py
    uv run python src/experiments/plot_session.py src/logs/tracker_XXXX.csv src/logs/engine_XXXX.csv

pandas y matplotlib ya son dependencias del proyecto (pyproject.toml),
así que basta con `uv run`.

Los logs anteriores a la traslación (6DOF) no tienen las columnas nuevas:
en ese caso se grafica solo la rotación y se avisa, en vez de fallar.
"""
import sys
import glob
import os

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from experiments import metrics

# Este archivo vive en src/experiments/, así que los logs están un nivel
# arriba, en src/logs/ (antes apuntaba a src/src/logs, que no existe: la
# búsqueda automática no encontraba nada y había que pasar rutas a mano).
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

# Columnas que agregó la Fase B. Si faltan, el log es de antes.
TRANS_COLUMNS = ("rel_tx_cm", "rel_ty_cm", "rel_tz_cm",
                 "out_tx", "out_ty", "out_tz")
AXIS_LABELS = (("tx", "lateral"), ("ty", "vertical"), ("tz", "profundidad"))


def _has_translation(df):
    return all(c in df.columns for c in TRANS_COLUMNS)


def _numeric(df, *columns):
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def _report_translation(df_ok):
    """Resumen de los 3 ejes: ruido en reposo, tiempos de subida y el
    estado del pivote del cuello."""
    print("\n[TRASLACIÓN] Ruido en el tramo de 5 s más quieto de la sesión:")
    print("   eje            std      pico-a-pico   jitter   (cm, y salida -1..1)")
    for key, name in AXIS_LABELS:
        cm = metrics.quietest_window(df_ok["t"], df_ok[f"rel_{key}_cm"], window_s=5.0)
        out = metrics.quietest_window(df_ok["t"], df_ok[f"out_{key}"], window_s=5.0)
        if cm["n"] == 0:
            print(f"   {name:<13} (sesión demasiado corta para medir)")
            continue
        print(f"   {name:<13} {cm['std']:7.3f} cm  {cm['p2p']:7.3f} cm  "
              f"{cm['jitter']:7.4f} cm   |  salida std {out['std']:.4f}")
        if abs(out["p2p"]) > 0.02:
            print(f"      ⚠ la salida se mueve {out['p2p']:.3f} estando quieto: "
                  f"sube la zona muerta de {name}")

    print("\n[TRASLACIÓN] Tiempos de subida (10->90 %) de los movimientos rápidos:")
    for key, name in AXIS_LABELS:
        times = metrics.rise_times(df_ok["t"], df_ok[f"out_{key}"], min_amplitude=0.3)
        if not times:
            print(f"   {name:<13} sin movimientos grandes en esta sesión")
        else:
            print(f"   {name:<13} n={len(times):<3} mediana {np.median(times)*1000:5.0f} ms  "
                  f"peor {max(times)*1000:5.0f} ms")

    # Compensación de cuello: si está bien, girar no traslada, así que la
    # correlación entre yaw y traslación tiene que ser baja.
    report = metrics.neck_compensation_report(
        df_ok["rel_yaw_deg"], df_ok["rel_tx_cm"], df_ok["rel_ty_cm"], df_ok["rel_tz_cm"])
    print("\n[PIVOTE DEL CUELLO] Correlación |yaw vs traslación| "
          "(cerca de 0 = girar no desplaza):")
    for _, name in AXIS_LABELS:
        print(f"   {name:<13} {report[name]:.3f}")
    if report["worst"] > 0.5:
        print(f"   ⚠ el eje {report['worst_axis']} sigue al yaw ({report['worst']:.2f}): "
              "ajusta el pivote del cuello en la GUI.")
    elif report["worst"] > 0.25:
        print(f"   El eje {report['worst_axis']} está algo acoplado al yaw "
              f"({report['worst']:.2f}); se puede afinar.")
    else:
        print("   ✓ Los tres ejes están desacoplados del giro.")
    return report


def _latest(pattern):
    files = sorted(glob.glob(os.path.join(LOGS_DIR, pattern)))
    return files[-1] if files else None


def main():
    if len(sys.argv) >= 3:
        tracker_path, engine_path = sys.argv[1], sys.argv[2]
    else:
        tracker_path = _latest("tracker_*.csv")
        engine_path = _latest("engine_*.csv")

    if not tracker_path or not engine_path:
        print(f"[ERROR] No se encontraron logs en {LOGS_DIR}")
        print("        Corré una sesión con AEROCTRL_LOG=1 primero.")
        return

    print(f"[OK] Tracker: {tracker_path}")
    print(f"[OK] Motor:   {engine_path}")

    df_t = pd.read_csv(tracker_path)
    df_e = pd.read_csv(engine_path)

    if df_t.empty or df_e.empty:
        print("[ERROR] Alguno de los dos logs está vacío.")
        return

    # Alinear ambos timelines a un mismo origen (t=0 = el primer timestamp
    # absoluto entre los dos archivos), ya que tracker.py y motor.py
    # arrancan sus relojes en momentos ligeramente distintos.
    t0 = min(df_t["t_abs"].min(), df_e["t_abs"].min())
    df_t["t"] = df_t["t_abs"] - t0
    df_e["t"] = df_e["t_abs"] - t0

    detected_mask = df_t["detected"].astype(str) == "True"
    pct_lost = 100 * (~detected_mask).sum() / len(df_t)
    print(f"\n[RESUMEN] Frames sin detección: {(~detected_mask).sum()} de {len(df_t)} ({pct_lost:.1f}%)")

    # "Jitter" = cuánto salta el valor filtrado de un frame al siguiente.
    # Es la métrica objetiva de "qué tan temblorosa se ve la vista en el
    # sim al mirar los instrumentos" -- cuanto más alto, más se sacude.
    df_ok = df_t[detected_mask].copy()
    df_ok["yaw"] = pd.to_numeric(df_ok["yaw"])
    df_ok["pitch"] = pd.to_numeric(df_ok["pitch"])
    df_ok["raw_yaw"] = pd.to_numeric(df_ok["raw_yaw"])
    df_ok["raw_pitch"] = pd.to_numeric(df_ok["raw_pitch"])
    # 'recentered' no existe en los logs más viejos: sin la columna, se
    # asume que no hubo recentrados en vez de fallar.
    if "recentered" in df_ok.columns:
        recentered_mask = df_ok["recentered"].astype(str) == "True"
    else:
        recentered_mask = pd.Series(False, index=df_ok.index)
    n_recenters = int(recentered_mask.sum())
    if n_recenters:
        print(f"[RESUMEN] {n_recenters} recentrado(s) detectado(s) -- excluidos del cálculo de jitter"
              " (el salto de referencia no es jitter real).")

    # yaw/pitch (ya centrados/filtrados) saltan artificialmente en el frame
    # de un recenter -- ese salto NO es jitter real, es que cambió el cero.
    # raw_yaw/raw_pitch son ángulos absolutos y no se ven afectados por
    # recenter, así que su jitter se calcula normal.
    yaw_diff = df_ok["yaw"].diff()
    pitch_diff = df_ok["pitch"].diff()
    yaw_diff[recentered_mask] = np.nan
    pitch_diff[recentered_mask] = np.nan

    jitter_yaw_raw = df_ok["raw_yaw"].diff().abs().mean()
    jitter_yaw_filt = yaw_diff.abs().mean()
    jitter_pitch_raw = df_ok["raw_pitch"].diff().abs().mean()
    jitter_pitch_filt = pitch_diff.abs().mean()
    print(f"[RESUMEN] Jitter promedio yaw   -> raw: {jitter_yaw_raw:.5f}  filtrado: {jitter_yaw_filt:.5f}")
    print(f"[RESUMEN] Jitter promedio pitch -> raw: {jitter_pitch_raw:.5f}  filtrado: {jitter_pitch_filt:.5f}")
    if jitter_yaw_filt > 0:
        print(f"          (el filtro redujo el jitter de yaw un {100*(1 - jitter_yaw_filt/max(jitter_yaw_raw,1e-9)):.0f}%)")

    # Detectar "rachas" sin deteccion y ver que tan cerca del limite
    # estaba el yaw/pitch justo ANTES de cada una -- confirma o descarta
    # la hipotesis de "se pierde al ponerse de perfil".
    df_t["gap"] = (~detected_mask).astype(int)
    df_t["gap_id"] = (df_t["gap"].diff() == 1).cumsum() * df_t["gap"]
    gaps = df_t[df_t["gap"] == 1].groupby("gap_id")["t"].agg(["min", "max", "count"])
    if len(gaps) > 0:
        print(f"\n[RESUMEN] {len(gaps)} hueco(s) de detección encontrados. Yaw/pitch justo antes de cada uno:")
        for gap_id, row in gaps.iterrows():
            idx_before = df_t[(df_t["t"] < row["min"]) & detected_mask].index
            if len(idx_before) > 0:
                last_ok = df_t.loc[idx_before[-1]]
                dur = row["max"] - row["min"]
                print(f"  t={row['min']:.1f}s  dur={dur:.2f}s  yaw_previo={float(last_ok['yaw']):.2f}  pitch_previo={float(last_ok['pitch']):.2f}")

    has_trans = _has_translation(df_t)
    if has_trans:
        _numeric(df_ok, *TRANS_COLUMNS, "raw_tx", "raw_ty", "raw_tz",
                 "comp_tx", "comp_ty", "comp_tz", "rel_yaw_deg", "out_roll")
        neck_report = _report_translation(df_ok)
    else:
        neck_report = None
        print("\n[AVISO] Este log no tiene las columnas de traslación (es de antes "
              "del 6DOF): se grafica solo la rotación.")

    # --- Gráficos ---
    n_rows = 4 + (4 if has_trans else 0)
    fig, axes = plt.subplots(n_rows, 1, figsize=(12, 3 * n_rows), sharex=True)

    axes[0].plot(df_ok["t"], df_ok["raw_yaw"], color="lightgray", label="yaw raw", linewidth=0.8)
    axes[0].plot(df_ok["t"], df_ok["yaw"], color="tab:green", label="yaw filtrado")
    for _, row in gaps.iterrows():
        axes[0].axvspan(row["min"], row["max"], color="red", alpha=0.15)
    for t_rec in df_ok.loc[recentered_mask, "t"]:
        axes[0].axvline(t_rec, color="tab:blue", linestyle="--", alpha=0.6, linewidth=1)
    axes[0].set_ylabel("yaw")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)
    axes[0].set_title("Rojo = sin detección (perfil) | Línea azul punteada = recentrado manual")

    axes[1].plot(df_ok["t"], df_ok["raw_pitch"], color="lightgray", label="pitch raw", linewidth=0.8)
    axes[1].plot(df_ok["t"], df_ok["pitch"], color="tab:red", label="pitch filtrado")
    for _, row in gaps.iterrows():
        axes[1].axvspan(row["min"], row["max"], color="red", alpha=0.15)
    for t_rec in df_ok.loc[recentered_mask, "t"]:
        axes[1].axvline(t_rec, color="tab:blue", linestyle="--", alpha=0.6, linewidth=1)
    axes[1].set_ylabel("pitch")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.3)

    axes[2].plot(df_e["t"], df_e["lx"], label="stick X", color="tab:orange")
    axes[2].plot(df_e["t"], df_e["ly"], label="stick Y", color="tab:blue")
    axes[2].set_ylabel("stick (-1..1)")
    axes[2].legend(loc="upper right")
    axes[2].grid(alpha=0.3)

    axes[3].plot(df_e["t"], df_e["lt"], label="throttle", color="tab:cyan")
    axes[3].plot(df_e["t"], df_e["lr"], label="rudder", color="tab:pink")
    axes[3].set_ylabel("throttle / rudder")
    if not has_trans:
        axes[3].set_xlabel("tiempo (s)")
    axes[3].legend(loc="upper right")
    axes[3].grid(alpha=0.3)

    if has_trans:
        # Un panel por eje: crudo, compensado de cuello, y la salida final.
        # Ver los tres juntos es lo que dice DÓNDE se ensucia la señal.
        for i, (key, name) in enumerate(AXIS_LABELS):
            ax = axes[4 + i]
            ax.plot(df_ok["t"], df_ok[f"raw_{key}"] - df_ok[f"raw_{key}"].iloc[0],
                    color="lightgray", linewidth=0.8, label="crudo (cm, centrado)")
            ax.plot(df_ok["t"], df_ok[f"comp_{key}"] - df_ok[f"comp_{key}"].iloc[0],
                    color="tab:olive", linewidth=0.9, label="compensado (cm)")
            ax.plot(df_ok["t"], df_ok[f"rel_{key}_cm"], color="tab:blue",
                    label="filtrado y centrado (cm)")
            ax2 = ax.twinx()
            ax2.plot(df_ok["t"], df_ok[f"out_{key}"], color="tab:red", linewidth=1.2,
                     label="salida (-1..1)")
            ax2.set_ylim(-1.05, 1.05)
            ax2.set_ylabel("salida", color="tab:red")
            ax.set_ylabel(f"{name} (cm)")
            ax.grid(alpha=0.3)
            lines = ax.get_lines() + ax2.get_lines()
            ax.legend(lines, [l.get_label() for l in lines], loc="upper right", fontsize=7)

        # Yaw contra traslación: el gráfico que verifica el pivote del
        # cuello de un vistazo. Si las curvas se mueven juntas, está mal.
        ax = axes[7]
        ax.plot(df_ok["t"], df_ok["rel_yaw_deg"], color="tab:green", label="yaw (°)")
        ax.set_ylabel("yaw (°)")
        ax2 = ax.twinx()
        for key, name in AXIS_LABELS:
            ax2.plot(df_ok["t"], df_ok[f"rel_{key}_cm"], linewidth=0.9, label=name)
        ax2.set_ylabel("traslación (cm)")
        ax.grid(alpha=0.3)
        lines = ax.get_lines() + ax2.get_lines()
        ax.legend(lines, [l.get_label() for l in lines], loc="upper right", fontsize=7)
        title = "Yaw contra traslación: si se mueven juntas, el pivote del cuello está mal"
        if neck_report:
            title += f"  |  peor correlación: {neck_report['worst_axis']} {neck_report['worst']:.2f}"
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("tiempo (s)")

    fig.tight_layout()
    out_png = os.path.splitext(tracker_path)[0] + "_session.png"
    fig.savefig(out_png, dpi=120)
    print(f"\n[OK] Gráfico guardado en '{out_png}'")

    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
