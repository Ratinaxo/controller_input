"""Compara dos grabaciones de ejes: la nuestra contra la de OpenTrack.

Es el criterio de la Fase D del plan: con la traslación propia, el ruido en
reposo no debe ser superior y la profundidad debe sentirse igual o mejor.
Esto lo mide en vez de dejarlo a la impresión.

Las dos grabaciones se hacen con record_axes.py, que lee lo que el
dispositivo PUBLICA, así que los números son comparables aunque una venga
de nuestro tracker y la otra de OpenTrack.

Uso:
    uv run python src/experiments/compare_sessions.py \\
        src/logs/axes_nuestro.csv src/logs/axes_opentrack.csv

Para que la comparación valga, las dos grabaciones tienen que tener la
MISMA secuencia de movimientos. Los ejes se emparejan por nombre de
columna; los que solo estén en una de las dos se informan y se omiten.
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from experiments import metrics

# Cuánto peor puede ser el ruido de la grabación A antes de considerarlo un
# empeoramiento real y no dispersión de la medición.
NOISE_TOLERANCE = 1.15
REST_WINDOW_S = 5.0

# Ventana de suavizado para medir los tiempos de subida. Más estrecha que
# la que usa plot_session sobre la telemetría: una grabación de ejes viene
# ya filtrada por el propio tracker y muestreada a 100 Hz, así que no hace
# falta tanto suavizado y una ventana ancha infla el tiempo medido (con
# 0.15 s el error llega al +15 % en un movimiento de 220 ms; con 0.05 s
# queda en el +1 %).
RISE_SMOOTH_S = 0.05


def load(path):
    df = pd.read_csv(path)
    if "t_abs" not in df.columns:
        raise SystemExit(f"[ERROR] {path} no parece una grabación de record_axes.py "
                         "(falta la columna t_abs).")
    df["t"] = df["t_abs"] - df["t_abs"].min()
    for c in df.columns:
        if c not in ("t_abs", "t"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def axis_report(df, axis):
    rest = metrics.quietest_window(df["t"], df[axis], window_s=REST_WINDOW_S)
    times = metrics.rise_times(df["t"], df[axis], min_amplitude=0.3,
                               smooth_s=RISE_SMOOTH_S)
    return {
        "rest_std": rest["std"], "rest_p2p": rest["p2p"], "rest_jitter": rest["jitter"],
        "n_moves": len(times),
        "rise_median": float(np.median(times)) if times else float("nan"),
        "rise_worst": float(max(times)) if times else float("nan"),
    }


def _fmt(value, unit="", width=7):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return f"{'--':>{width}}"
    return f"{value:{width}.4f}{unit}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    path_a, path_b = sys.argv[1], sys.argv[2]
    name_a = os.path.basename(path_a)
    name_b = os.path.basename(path_b)

    df_a, df_b = load(path_a), load(path_b)
    print(f"[A] {name_a}: {len(df_a)} muestras, {df_a['t'].max():.1f} s")
    print(f"[B] {name_b}: {len(df_b)} muestras, {df_b['t'].max():.1f} s")

    axes_a = {c for c in df_a.columns if c not in ("t_abs", "t")}
    axes_b = {c for c in df_b.columns if c not in ("t_abs", "t")}
    common = sorted(axes_a & axes_b)
    only_a, only_b = sorted(axes_a - axes_b), sorted(axes_b - axes_a)
    if only_a:
        print(f"[AVISO] Ejes solo en A, omitidos: {', '.join(only_a)}")
    if only_b:
        print(f"[AVISO] Ejes solo en B, omitidos: {', '.join(only_b)}")
    if not common:
        raise SystemExit("[ERROR] Las dos grabaciones no comparten ningún eje.")

    print(f"\n{'eje':<10} {'ruido A':>9} {'ruido B':>9}  {'jitter A':>9} {'jitter B':>9}"
          f"  {'subida A':>9} {'subida B':>9}   veredicto")
    print("-" * 92)

    worse = []
    for axis in common:
        ra, rb = axis_report(df_a, axis), axis_report(df_b, axis)
        verdict = ""
        if np.isfinite(ra["rest_std"]) and np.isfinite(rb["rest_std"]) and rb["rest_std"] > 0:
            ratio = ra["rest_std"] / rb["rest_std"]
            if ratio > NOISE_TOLERANCE:
                verdict = f"A tiembla {ratio:.1f}x más"
                worse.append(axis)
            elif ratio < 1 / NOISE_TOLERANCE:
                verdict = f"A es {1/ratio:.1f}x más estable"
            else:
                verdict = "empatan"
        print(f"{axis:<10} {_fmt(ra['rest_std'])} {_fmt(rb['rest_std'])}  "
              f"{_fmt(ra['rest_jitter'])} {_fmt(rb['rest_jitter'])}  "
              f"{_fmt(ra['rise_median'])} {_fmt(rb['rise_median'])}   {verdict}")

    print("\nruido/jitter en unidades de eje (-1..1), en el tramo de "
          f"{REST_WINDOW_S:.0f} s más quieto. Subida = mediana del 10->90 %, en segundos.")
    print("La subida es comparativa, no absoluta: ver la exactitud documentada "
          "en metrics.rise_times.")

    if worse:
        print(f"\n[VEREDICTO] A tiene más ruido en reposo en: {', '.join(worse)}.")
        print("            Sube la zona muerta o baja el min_cutoff de esos ejes; "
              "si no alcanza, el plan B es el puente UDP (OpenTrack hace la visión "
              "y este programa publica los ejes, conservando el control de los límites).")
    else:
        print("\n[VEREDICTO] A no tiene más ruido en reposo que B en ningún eje. "
              "Criterio de la Fase D cumplido en la parte medible; lo que falta es "
              "la sensación en cabina.")

    # --- Gráfico: cada eje común, las dos grabaciones superpuestas ---
    fig, axs = plt.subplots(len(common), 1, figsize=(12, 2.2 * len(common)), squeeze=False)
    for ax, axis in zip(axs[:, 0], common):
        ax.plot(df_a["t"], df_a[axis], linewidth=0.9, label=f"A: {name_a}")
        ax.plot(df_b["t"], df_b[axis], linewidth=0.9, label=f"B: {name_b}")
        ax.set_ylabel(axis)
        ax.set_ylim(-1.05, 1.05)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=7)
    axs[-1, 0].set_xlabel("tiempo (s)")
    fig.suptitle("Los tiempos no están alineados: son sesiones distintas con los "
                 "mismos movimientos", fontsize=9)
    fig.tight_layout()
    out_png = os.path.splitext(path_a)[0] + "_vs_" + os.path.splitext(name_b)[0] + ".png"
    fig.savefig(out_png, dpi=120)
    print(f"\n[OK] Gráfico guardado en '{out_png}'")
    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
