"""
Fase 0 - Graficador de la sonda de profundidad (desechable, fuera de src/).

Lee el CSV que genera depth_probe.py y grafica tz (traslación Z de la
matriz) y depth_proxy (fallback por tamaño de cara) contra el tiempo,
junto con yaw/pitch para poder ver visualmente si hay "contaminación
cruzada" (que girar la cabeza mueva la señal de profundidad).

Requiere matplotlib y pandas (no son dependencias del proyecto, son solo
para este análisis puntual):
    uv pip install matplotlib pandas

Uso:
    python3 experiments/plot_depth_probe.py depth_probe.csv
"""
import sys

import pandas as pd
import matplotlib.pyplot as plt


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 plot_depth_probe.py <archivo.csv>")
        return

    path = sys.argv[1]
    df = pd.read_csv(path)

    if df.empty:
        print(f"[ERROR] '{path}' está vacío (¿se detectó algún rostro durante la grabación?)")
        return

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    axes[0].plot(df["t"], df["tz"], label="tz (traslación Z, matriz MediaPipe)", color="tab:blue")
    axes[0].set_ylabel("tz (unidades del modelo)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.3)

    axes[1].plot(df["t"], df["depth_proxy"], label="depth_proxy (1000 / ancho interocular px)", color="tab:orange")
    axes[1].set_ylabel("depth_proxy")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.3)

    axes[2].plot(df["t"], df["yaw_deg"], label="yaw (grados)", color="tab:green")
    axes[2].plot(df["t"], df["pitch_deg"], label="pitch (grados)", color="tab:red")
    axes[2].set_ylabel("grados")
    axes[2].set_xlabel("tiempo (s)")
    axes[2].legend(loc="upper right")
    axes[2].grid(alpha=0.3)

    fig.suptitle("Fase 0 - ¿tz o depth_proxy sirven como señal de profundidad?")
    fig.tight_layout()

    out_png = path.rsplit(".", 1)[0] + ".png"
    fig.savefig(out_png, dpi=120)
    print(f"[OK] Gráfico guardado en '{out_png}'")

    # Estadísticas rápidas para no depender solo de mirar el gráfico
    print("\n--- Resumen ---")
    for col in ["tz", "depth_proxy"]:
        print(f"{col}: min={df[col].min():.4f}  max={df[col].max():.4f}  "
              f"rango={df[col].max() - df[col].min():.4f}  std={df[col].std():.4f}")

    try:
        plt.show()
    except Exception:
        pass  # entorno sin display interactivo: el PNG ya quedó guardado


if __name__ == "__main__":
    main()
