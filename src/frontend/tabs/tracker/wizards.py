"""Los dos asistentes de calibración del Head Tracker, como datos.

La mecánica (captura, estabilidad, tiempo límite, ventana) está una sola
vez en components/calibration_wizard.py. Aquí solo va lo que los distingue:
los pasos, la lectura en vivo, qué se guarda y los textos.
"""
import copy
import math

from backend.tracker import (
    ANGLE_TOLERANCE_DEG, STABLE_SPREAD_DEG, STABLE_TRANS_SPREAD_CM, MIN_CALIB_TRANS_CM,
)
from frontend.components.calibration_wizard import WizardSpec
from frontend.style import spacing as S

# (clave interna, instrucción). El ángulo esperado de cada paso está en
# backend.tracker.EXPECTED_ANGLES.
ROTATION_STEPS = [
    ("up", "Gira la cabeza hacia ARRIBA, al máximo cómodo"),
    ("down", "Gira la cabeza hacia ABAJO, al máximo cómodo"),
    ("left", "Gira la cabeza hacia la IZQUIERDA, al máximo cómodo"),
    ("right", "Gira la cabeza hacia la DERECHA, al máximo cómodo"),
    ("diag_up_left", "Mira hacia la diagonal SUPERIOR IZQUIERDA, al máximo cómodo"),
    ("diag_up_right", "Mira hacia la diagonal SUPERIOR DERECHA, al máximo cómodo"),
    ("diag_down_left", "Mira hacia la diagonal INFERIOR IZQUIERDA, al máximo cómodo"),
    ("diag_down_right", "Mira hacia la diagonal INFERIOR DERECHA, al máximo cómodo"),
]

# (paso interno, instrucción). El eje y el sentido esperados de cada paso
# están en backend.tracker.TRANS_STEPS.
TRANSLATION_STEPS = [
    ("x_pos", "Asómate hacia la DERECHA, hasta donde te resulte cómodo"),
    ("x_neg", "Asómate hacia la IZQUIERDA, hasta donde te resulte cómodo"),
    ("y_pos", "ESTÍRATE hacia arriba, hasta donde te resulte cómodo"),
    ("y_neg", "AGÁCHATE, hasta donde te resulte cómodo"),
    ("z_pos", "ACÉRCATE al monitor, hasta donde te resulte cómodo"),
    ("z_neg", "ALÉJATE del monitor, hasta donde te resulte cómodo"),
]
TRANSLATION_AXIS_NAMES = ("lateral", "vertical", "profundidad")


def angle_text(a):
    return f"{a:.0f}°"


def make_snapshot(ctx, key):
    """Copia de lo calibrado ahora, para poder volver a ella al cancelar."""
    def snapshot():
        return copy.deepcopy(ctx.config.get(key))
    return snapshot


def make_restore(ctx, key, on_status_change):
    """Devuelve la calibración guardada al estado `value`.

    Se escribe en la configuración de la GUI y en la del tracker, que son
    dos dicts distintos: el asistente guarda cada paso en el tracker y lo
    copia a la GUI, así que revertir solo uno dejaría los dos en desacuerdo.
    """
    def restore(tracker, value):
        for target in (ctx.config, getattr(tracker, "config", None)):
            if target is None:
                continue
            if value is None:
                target.pop(key, None)
            else:
                target[key] = copy.deepcopy(value)
        on_status_change()
    return restore


# --- Giro -----------------------------------------------------------------------

def rotation_live_text(tracker):
    ry, rp = tracker.get_relative_degrees()
    mag = math.hypot(ry, rp)
    # La dirección se muestra igual que se valida: en el rango propio si
    # ya se conoce, para que el número de la lectura en vivo y el del
    # rechazo no se contradigan.
    scales = None
    getter = getattr(tracker, "direction_scales", None)
    if callable(getter):
        scales = getter()
    if scales:
        ang = math.degrees(math.atan2(rp / scales[1], ry / scales[0])) % 360.0
    else:
        ang = math.degrees(math.atan2(rp, ry)) % 360.0
    return (f"yaw {ry:+5.1f}°  pitch {rp:+5.1f}°  |  dirección {angle_text(ang)}  "
            f"radio {mag:4.1f}°")


def rotation_reject_message(result):
    if result["reason"] == "center":
        return "Estás muy cerca del centro: gira más la cabeza y reintenta."
    if result.get("detail") == "sign":
        return ("Te moviste hacia el lado contrario al que pide el paso. "
                "Revisa la instrucción y reintenta.")
    if result.get("detail") == "dominance":
        return ("Este paso es de un solo eje, pero el otro se movió casi lo "
                "mismo. Haz el giro más derecho y reintenta.")
    # Ángulo: se muestra el medido EN TU RANGO, no en grados crudos. Con la
    # cámara baja o un cuello que gira más de lado que hacia abajo, los
    # grados crudos de una diagonal honesta no dan 135, y ver ese número
    # solo confunde.
    medida = angle_text(result.get("angle_scaled", result["angle"]))
    en_tu_rango = " (medida en tu propio rango de giro)" if result.get("scaled") else ""
    return (f"La dirección medida ({medida}){en_tu_rango} no corresponde a este paso "
            f"(se esperaba {angle_text(result['expected'])} ± {ANGLE_TOLERANCE_DEG:.0f}°). "
            "Revisa la instrucción y reintenta.")


def rotation_spec(ctx, on_status_change):
    """Asistente de 8 direcciones. Al marcar, espera a que la cabeza esté
    quieta ~0.5 s, valida que la dirección medida corresponda al paso
    (±30°) y recién entonces guarda el punto en grados."""

    def on_saved(tracker):
        ctx.config["head_limit_points"] = list(tracker.config.get("head_limit_points", []))
        on_status_change()

    return WizardSpec(
        geometry_key="rotation",
        window_title="Asistente de calibración de giro",
        dialog_title="Calibración",
        external_message=(
            "La fuente de cabeza está en modo externo (OpenTrack).\n\n"
            "Para calibrar el rango de giro de la cámara propia, cambia la fuente a "
            "«Cámara propia» en esta misma pestaña."),
        steps=ROTATION_STEPS,
        stable_spread=STABLE_SPREAD_DEG,
        stats=lambda tracker: tracker.window_stats(),
        live_text=rotation_live_text,
        calibrate=lambda tracker, label, stats: tracker.calibrate_direction(
            label, stats["mean_yaw"], stats["mean_pitch"]),
        reject_message=rotation_reject_message,
        on_saved=on_saved,
        snapshot=make_snapshot(ctx, "head_limit_points"),
        restore=make_restore(ctx, "head_limit_points", on_status_change),
        ready_message="Pon la cabeza en posición y pulsa «Marcar». Luego quédate quieto.",
        hold_message="Mantén la cabeza quieta…",
        done_message="Listo -- las 8 direcciones quedaron calibradas.",
        wraplength=S.WRAP_DIALOG_ROTATION,
    )


# --- Traslación ---------------------------------------------------------------------

def translation_live_text(tracker):
    tx, ty, tz = tracker.get_relative_cm()
    return f"lateral {tx:+5.1f}  vertical {ty:+5.1f}  profundidad {tz:+5.1f}  cm"


def translation_reject_message(result):
    if result["reason"] == "center":
        return (f"Te moviste menos de {MIN_CALIB_TRANS_CM:.0f} cm: "
                "desplázate más y reintenta.")
    expected = TRANSLATION_AXIS_NAMES[result["expected_axis"]]
    dominant = TRANSLATION_AXIS_NAMES[result["dominant"]]
    if dominant == expected:
        # Eje correcto pero hacia el otro lado: lo que hay que corregir es
        # el sentido, no la calibración.
        return (f"El eje {expected} se movió al revés. Marca «Invertir "
                f"sentido» para ese eje en la pestaña y reintenta.")
    return (f"Esperaba que dominara el eje {expected}, pero el que más "
            f"cambió fue {dominant}. Revisa la instrucción y reintenta.")


def translation_spec(ctx, on_status_change):
    """Asistente de 6 pasos (un sentido por eje). Valida que el eje que más
    cambió sea el del paso, y recién entonces guarda el rango en cm."""

    def on_saved(tracker):
        ctx.config["head_trans_limits"] = dict(tracker.config.get("head_trans_limits", {}))
        on_status_change()

    return WizardSpec(
        geometry_key="translation",
        window_title="Asistente de calibración de traslación",
        dialog_title="Calibración de traslación",
        external_message=(
            "La fuente de cabeza está en modo externo (OpenTrack).\n\n"
            "Para calibrar el rango de traslación de la cámara propia, cambia la "
            "fuente a «Cámara propia» en esta misma pestaña."),
        steps=TRANSLATION_STEPS,
        stable_spread=STABLE_TRANS_SPREAD_CM,
        stats=lambda tracker: tracker.trans_window_stats(),
        live_text=translation_live_text,
        calibrate=lambda tracker, step, stats: tracker.calibrate_translation(step, stats["mean"]),
        reject_message=translation_reject_message,
        on_saved=on_saved,
        snapshot=make_snapshot(ctx, "head_trans_limits"),
        restore=make_restore(ctx, "head_trans_limits", on_status_change),
        ready_message="Ponte en posición y pulsa «Marcar». Luego quédate quieto.",
        hold_message="Quédate quieto…",
        done_message=("Listo -- los 6 sentidos quedaron calibrados.\n\n"
                      "Guarda la configuración para que no se pierda."),
        wraplength=S.WRAP_DIALOG_TRANSLATION,
        hint="Mueve el CUERPO, no solo la cabeza: esto mide posición, no giro.",
        live_pady=(6, 0),
    )
