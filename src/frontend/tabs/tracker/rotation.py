"""Secciones de rotación: sensibilidad, filtro, magnetismo y límites de giro."""
import tkinter as tk

from backend.tracker import valid_limit_points, has_legacy_calibration
from frontend.components import (
    section_header, divider, note, slider_row, primary_button, secondary_button,
)
from frontend.components.calibration_wizard import open_wizard
from frontend.style import colors as C, spacing as S
from frontend.tabs.tracker.help import HELP
from frontend.tabs.tracker.wizards import ROTATION_STEPS, rotation_spec

DEFAULTS = {
    't_sens_x': 10.0, 't_sens_y': 10.0, 't_min_cutoff': 1.0, 't_beta': 0.05,
    't_center_drag': 0.0, 't_deadzone': 0.02, 't_snap_axis': 0.25, 't_snap_outer': 0.10,
}


def format_calibration_status(points):
    """Texto de estado de la calibración de giro (octágono)."""
    points = points or []
    valid = valid_limit_points(points)
    done = {p.get("label") for p in valid}
    total = len(ROTATION_STEPS)
    if not valid:
        if has_legacy_calibration(points):
            return ("Calibración de una versión anterior (otras unidades): hay que recalibrar. "
                    "Mientras tanto se usa el límite fijo de ±35°.")
        return f"Sin calibrar -- usando límite fijo de ±35° en todas direcciones (0/{total})"
    faltan = [label for label, _ in ROTATION_STEPS if label not in done]
    if not faltan:
        return f"Calibrado: {total}/{total} direcciones ✓"
    extra = "" if len(valid) >= 3 else " -- con menos de 3 se sigue usando ±35°"
    return f"Calibrado parcialmente: {len(done)}/{total} direcciones (faltan {len(faltan)}){extra}"


class RotationSection:
    owned_keys = tuple(DEFAULTS) + ('head_limit_points',)

    def __init__(self, ctx):
        self.ctx = ctx

    def build(self, parent):
        cfg = self.ctx.config
        get = lambda k: cfg.get(k, DEFAULTS[k])

        section_header(parent, "SENSIBILIDAD")
        self.t_sens_x = slider_row(parent, "Yaw (X)  — 10 = rango calibrado", 1.0, 50.0, 0.5,
                                   get('t_sens_x'), HELP["t_sens_x"])
        self.t_sens_y = slider_row(parent, "Pitch (Y) — 10 = rango calibrado", 1.0, 50.0, 0.5,
                                   get('t_sens_y'), HELP["t_sens_y"])
        divider(parent)

        section_header(parent, "FILTRO Y CENTRADO")
        self.t_min_cutoff = slider_row(parent, "Estabilidad en reposo (Hz)", 0.1, 5.0, 0.1,
                                       get('t_min_cutoff'), HELP["t_min_cutoff"])
        self.t_beta = slider_row(parent, "Reacción al movimiento (beta)", 0.0, 0.5, 0.005,
                                 get('t_beta'), HELP["t_beta"])
        self.t_center_drag = slider_row(parent, "Auto-Centrado (Peso)", 0.0, 0.02, 0.001,
                                        get('t_center_drag'), HELP["t_center_drag"])
        self.t_deadzone = slider_row(parent, "Deadzone Central", 0.0, 0.1, 0.005,
                                     get('t_deadzone'), HELP["t_deadzone_t"])
        divider(parent)

        section_header(parent, "MAGNETISMO (Snap)")
        self.t_snap_axis = slider_row(parent, "Fuerza Ejes", 0.0, 0.5, 0.05,
                                      get('t_snap_axis'), HELP["t_snap_axis"])
        self.t_snap_outer = slider_row(parent, "Fuerza Bordes", 0.0, 0.3, 0.01,
                                       get('t_snap_outer'), HELP["t_snap_outer"])
        divider(parent)

        # --- Límites de giro: asistente guiado de 8 direcciones ---
        section_header(parent, "LÍMITES DE GIRO (Calibración guiada)")
        self.lbl_status = note(parent, self.status_text())

        calib_row = tk.Frame(parent, bg=C.PANEL)
        calib_row.pack(fill='x', padx=S.PAD_TAB, pady=(0, 5))
        self.btn_calibrate = primary_button(
            calib_row, "🧭 Calibrar rango de giro (asistente guiado)", command=self.open_wizard)
        self.btn_calibrate.pack(side='left', fill='x', expand=True)

        self.btn_reset = secondary_button(
            parent, "↺ Descartar calibración (volver a límite fijo de 35°)", command=self.reset)
        self.btn_reset.pack(fill='x', padx=S.PAD_TAB, pady=(5, 0))
        divider(parent)

    # --- controles a atenuar con fuente externa ---
    @property
    def sliders(self):
        return [self.t_sens_x, self.t_sens_y, self.t_min_cutoff, self.t_beta,
                self.t_center_drag, self.t_deadzone, self.t_snap_axis, self.t_snap_outer]

    @property
    def buttons(self):
        return [self.btn_calibrate, self.btn_reset]

    # --- calibración ---
    def status_text(self):
        return format_calibration_status(self.ctx.config.get("head_limit_points", []))

    def refresh_status(self):
        self.lbl_status.config(text=self.status_text())

    def open_wizard(self):
        return open_wizard(self.ctx.root, self.ctx.tracker,
                           rotation_spec(self.ctx, self.refresh_status))

    def reset(self):
        self.ctx.config["head_limit_points"] = []
        if self.ctx.tracker:
            self.ctx.tracker.config["head_limit_points"] = []
        self.refresh_status()

    # --- configuración ---
    def read_config(self):
        return {
            't_sens_x': self.t_sens_x.get(),
            't_sens_y': self.t_sens_y.get(),
            't_min_cutoff': self.t_min_cutoff.get(),
            't_beta': self.t_beta.get(),
            't_deadzone': self.t_deadzone.get(),
            't_snap_axis': self.t_snap_axis.get(),
            't_snap_outer': self.t_snap_outer.get(),
            't_center_drag': self.t_center_drag.get(),
            # Se escribe solo vía el asistente de calibración.
            'head_limit_points': self.ctx.config.get('head_limit_points', []),
        }

    def apply_config(self, cfg):
        for key in DEFAULTS:
            getattr(self, key).set(cfg.get(key, DEFAULTS[key]))
        self.ctx.config["head_limit_points"] = cfg.get("head_limit_points", [])
        if self.ctx.tracker:
            self.ctx.tracker.config["head_limit_points"] = self.ctx.config["head_limit_points"]
        self.refresh_status()
