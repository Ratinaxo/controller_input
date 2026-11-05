"""Métricas de una sesión grabada. Funciones puras, sin pandas ni
matplotlib, para que se puedan probar con tests.

Las usan plot_session.py (una sesión) y compare_sessions.py (dos
grabaciones de ejes, típicamente la nuestra contra la de OpenTrack).

Todas aceptan listas o arrays de numpy y devuelven float o dict; ninguna
dibuja nada ni lee archivos.
"""
import numpy as np


def _clean(values):
    """Array de float con los NaN fuera. Los CSV de telemetría dejan la
    celda vacía en los frames sin detección, y pandas los trae como NaN."""
    a = np.asarray(values, dtype=float)
    return a[np.isfinite(a)]


def rest_noise(values):
    """Ruido de una señal que debería estar quieta.

    Devuelve {'n', 'std', 'p2p', 'jitter'}:
      - std:    desviación estándar (cuánto se va del promedio).
      - p2p:    recorrido pico a pico (el peor caso visible).
      - jitter: cambio medio de un frame al siguiente. Es la métrica que
                corresponde a "qué tan tembloroso se ve": una deriva lenta
                grande puede dar std alta con jitter bajo, y se ve quieta.
    """
    a = _clean(values)
    if a.size == 0:
        return {"n": 0, "std": float("nan"), "p2p": float("nan"), "jitter": float("nan")}
    if a.size == 1:
        return {"n": 1, "std": 0.0, "p2p": 0.0, "jitter": 0.0}
    return {
        "n": int(a.size),
        "std": float(np.std(a)),
        "p2p": float(np.max(a) - np.min(a)),
        "jitter": float(np.mean(np.abs(np.diff(a)))),
    }


def quietest_window(t, values, window_s=5.0):
    """Encuentra el tramo de `window_s` segundos más quieto de la señal.

    Sirve para medir el ruido en reposo sin pedirle al usuario que marque
    dónde estuvo quieto: se busca la ventana de menor desviación estándar.

    Devuelve {'start', 'end', 'std', 'p2p', 'jitter', 'n'}, o n=0 si la
    señal es más corta que la ventana.
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    if t.size < 2 or (t[-1] - t[0]) < window_s:
        return {"start": float("nan"), "end": float("nan"), "n": 0,
                "std": float("nan"), "p2p": float("nan"), "jitter": float("nan")}

    best = None
    for i in range(t.size):
        j = int(np.searchsorted(t, t[i] + window_s, side="right"))
        if j > t.size:
            break
        if j - i < 2 or t[j - 1] - t[i] < window_s * 0.9:
            continue
        chunk = v[i:j]
        std = float(np.std(chunk))
        if best is None or std < best[0]:
            best = (std, i, j)
    if best is None:
        return {"start": float("nan"), "end": float("nan"), "n": 0,
                "std": float("nan"), "p2p": float("nan"), "jitter": float("nan")}

    _, i, j = best
    stats = rest_noise(v[i:j])
    stats.update({"start": float(t[i]), "end": float(t[j - 1])})
    return stats


def smooth_centered(values, width):
    """Media móvil CENTRADA de `width` muestras.

    Centrada a propósito: no desplaza los flancos en el tiempo, así que se
    puede medir un tiempo de subida sobre la señal suavizada sin que el
    suavizado añada retraso. Los bordes se extienden con el primer y el
    último valor para no inventar rampas.
    """
    v = np.asarray(values, dtype=float)
    width = int(width)
    if width < 3 or v.size < width:
        return v.copy()
    if width % 2 == 0:
        width += 1
    pad = width // 2
    ext = np.concatenate([np.full(pad, v[0]), v, np.full(pad, v[-1])])
    return np.convolve(ext, np.ones(width) / width, mode="valid")


def rise_times(t, values, lo=0.1, hi=0.9, min_amplitude=0.3,
               smooth_s=0.15, reversal_tol=None):
    """Tiempos de subida (10->90 % por defecto) de los movimientos rápidos.

    Para cada tramo en que la señal se desplaza al menos `min_amplitude`
    sin darse la vuelta, mide cuánto tarda en pasar del `lo` al `hi` de ese
    recorrido. No depende de cuándo empezaste a moverte, solo de cuánto
    tarda la señal en seguirte.

    La señal se suaviza antes de segmentarla con una ventana CENTRADA de
    `smooth_s` segundos. Es imprescindible: sin suavizar, el ruido en
    reposo se parte en decenas de tramos espurios y el tiempo medido sale
    hasta un 40 % corto. Al ser centrada, el suavizado no añade retraso.

    Exactitud medida contra un escalón de respuesta conocida (un filtro de
    primer orden sube del 10 al 90 % en tau*ln(9)), a 30 fps:

        ruido en reposo    error de la mediana
        ninguno                       +3 %
        1 % del recorrido              +2 %
        3 % del recorrido             -10 %

    O sea: es una métrica COMPARATIVA (nuestra sesión contra la de
    OpenTrack, con los mismos movimientos), no una medida absoluta. Si los
    ejes tienen mucho ruido en reposo, primero sube la zona muerta.

    Devuelve una lista de floats (segundos), uno por transición.
    """
    t = np.asarray(t, dtype=float)
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    if t.size < 3:
        return []

    dt = float(np.median(np.diff(t))) if t.size > 1 else 0.0
    width = int(round(smooth_s / dt)) if dt > 0 else 0
    v = smooth_centered(v, width)

    if reversal_tol is None:
        step = np.median(np.abs(np.diff(v))) if v.size > 1 else 0.0
        # 3 veces el paso típico: por encima del temblor residual y muy por
        # debajo de un movimiento real, con un piso por si la señal es
        # perfectamente limpia.
        reversal_tol = max(3.0 * float(step), min_amplitude * 0.02)

    out = []
    i = 0
    n = v.size
    while i < n - 1:
        # Dirección del tramo: el primer movimiento que supera el ruido.
        k = i + 1
        while k < n and abs(v[k] - v[i]) <= reversal_tol:
            k += 1
        if k >= n:
            break
        rising = v[k] > v[i]

        # Extender mientras no retroceda más que la tolerancia desde el
        # extremo alcanzado. El tramo termina EN ese extremo.
        extreme_idx = k
        j = k
        while j + 1 < n:
            j += 1
            better = v[j] > v[extreme_idx] if rising else v[j] < v[extreme_idx]
            if better:
                extreme_idx = j
            elif abs(v[j] - v[extreme_idx]) > reversal_tol:
                break

        seg_t, seg_v = t[i:extreme_idx + 1], v[i:extreme_idx + 1]
        if abs(seg_v[-1] - seg_v[0]) >= min_amplitude and seg_v.size >= 3:
            # La línea base viene de las muestras ANTERIORES al movimiento:
            # en una señal que ya está subiendo, las primeras del tramo no
            # son reposo, y usarlas acorta el tiempo medido.
            m = max(1, min(5, seg_v.size // 4))
            v0 = float(np.median(v[max(0, i - m + 1):i + 1]))
            v1 = float(np.median(seg_v[-m:]))
            if abs(v1 - v0) >= min_amplitude:
                t_lo = _first_crossing(seg_t, seg_v, v0 + (v1 - v0) * lo, rising)
                t_hi = _first_crossing(seg_t, seg_v, v0 + (v1 - v0) * hi, rising)
                if t_lo is not None and t_hi is not None and t_hi >= t_lo:
                    out.append(float(t_hi - t_lo))
        i = max(extreme_idx, i + 1)
    return out


def _median3(v):
    """Filtro de mediana de 3 muestras: quita picos aislados de ruido sin
    desplazar los flancos en el tiempo (a diferencia de un promedio)."""
    v = np.asarray(v, dtype=float)
    if v.size < 3:
        return v.copy()
    out = v.copy()
    out[1:-1] = np.median(np.stack([v[:-2], v[1:-1], v[2:]]), axis=0)
    return out


def _first_crossing(t, v, level, rising):
    """Instante en que `v` cruza `level` por primera vez, interpolando
    linealmente entre las dos muestras que lo rodean."""
    for k in range(1, len(v)):
        a, b = v[k - 1], v[k]
        crossed = (a < level <= b) if rising else (a > level >= b)
        if crossed:
            if b == a:
                return float(t[k])
            frac = (level - a) / (b - a)
            return float(t[k - 1] + frac * (t[k] - t[k - 1]))
    return None


def correlation(a, b):
    """Coeficiente de correlación de Pearson, tolerando NaN y series
    constantes (en cuyo caso no hay correlación definida: devuelve 0.0)."""
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 2 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def neck_compensation_report(yaw, tx, ty, tz):
    """Qué tan bien está ajustado el pivote del cuello.

    Si la compensación es correcta, girar la cabeza no traslada nada, así
    que la correlación entre el yaw y cada eje de traslación debe ser
    cercana a cero. Una correlación alta en el eje lateral es la firma
    exacta de un pivote mal ajustado.

    Devuelve {'lateral', 'vertical', 'profundidad', 'worst', 'worst_axis'}
    con las correlaciones en valor absoluto.
    """
    values = {
        "lateral": abs(correlation(yaw, tx)),
        "vertical": abs(correlation(yaw, ty)),
        "profundidad": abs(correlation(yaw, tz)),
    }
    worst_axis = max(values, key=lambda k: values[k])
    return {**values, "worst": values[worst_axis], "worst_axis": worst_axis}
