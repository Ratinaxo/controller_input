"""Secciones de traslación (6DOF): respuesta por eje, pivote del cuello y
rango de traslación."""
import tkinter as tk

from backend.tracker import (
    DEFAULT_TRANS_LIMIT_CM, TRANS_CALIB_UNITS, valid_trans_limits,
)
from frontend.components import (
    section_header, divider, note, subtitle, slider_row,
    primary_button, secondary_button, checkbox, help_icon,
)
from frontend.components.calibration_wizard import open_wizard
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS
from frontend.tabs.tracker.help import HELP
from frontend.tabs.tracker.wizards import TRANSLATION_STEPS, translation_spec

DEFAULTS = {
    't_trans_sens_x': 10.0, 't_trans_sens_y': 10.0, 't_trans_sens_z': 10.0,
    't_trans_deadzone_x': 0.03, 't_trans_deadzone_y': 0.03, 't_trans_deadzone_z': 0.06,
    't_trans_curve_x': 1.5, 't_trans_curve_y': 1.5, 't_trans_curve_z': 1.5,
    't_trans_min_cutoff': 0.8, 't_trans_beta': 0.02,
    't_trans_min_cutoff_z': 0.4, 't_trans_beta_z': 0.01,
    't_neck_height_cm': 10.0, 't_neck_depth_cm': 10.0,
}
# 'y' arranca invertido: el eje vertical de la imagen crece hacia abajo.
INVERT_DEFAULTS = {'x': False, 'y': True, 'z': False}

# clave de configuración -> atributo del slider
SLIDER_ATTR = {
    't_trans_sens_x': 't_trans_sens_x', 't_trans_sens_y': 't_trans_sens_y',
    't_trans_sens_z': 't_trans_sens_z',
    't_trans_deadzone_x': 't_trans_dz_x', 't_trans_deadzone_y': 't_trans_dz_y',
    't_trans_deadzone_z': 't_trans_dz_z',
    't_trans_curve_x': 't_trans_curve_x', 't_trans_curve_y': 't_trans_curve_y',
    't_trans_curve_z': 't_trans_curve_z',
    't_trans_min_cutoff': 't_trans_min_cutoff', 't_trans_beta': 't_trans_beta',
    't_trans_min_cutoff_z': 't_trans_min_cutoff_z', 't_trans_beta_z': 't_trans_beta_z',
    't_neck_height_cm': 't_neck_height', 't_neck_depth_cm': 't_neck_depth',
}


def format_trans_calibration_status(limits_cfg):
    limits = valid_trans_limits(limits_cfg or {})
    total = len(TRANSLATION_STEPS)
    if not limits:
        return (f"Sin calibrar -- usando ±{DEFAULT_TRANS_LIMIT_CM:.0f} cm en los 3 ejes "
                f"(0/{total}). Calíbralo: es lo que hace que el tope se alcance "
                "en el recorrido que a ti te resulta cómodo.")
    if len(limits) >= total:
        detail = "  ".join(f"{k}={v:.1f}" for k, v in sorted(limits.items()))
        return f"Calibrado: {total}/{total} sentidos ✓  (cm: {detail})"
    faltan = [step for step, _ in TRANSLATION_STEPS if step not in limits]
    return (f"Calibrado parcialmente: {len(limits)}/{total} sentidos "
            f"(faltan {', '.join(faltan)}) -- los que falten usan "
            f"±{DEFAULT_TRANS_LIMIT_CM:.0f} cm")


class TranslationSection:
    owned_keys = (tuple(DEFAULTS) + tuple(f't_trans_invert_{k}' for k in INVERT_DEFAULTS)
                  + ('head_trans_limits',))

    def __init__(self, ctx):
        self.ctx = ctx

    def build(self, parent):
        cfg = self.ctx.config
        pad = S.PAD_TAB
        get = lambda k: cfg.get(k, DEFAULTS[k])

        # --- TRASLACIÓN (6DOF) ---
        section_header(parent, "TRASLACIÓN (6DOF)")
        note(parent, "Asomarse a los lados, agacharse y acercarse al panel. "
                     "Calibra primero el rango de abajo: la sensibilidad es una "
                     "ganancia sobre él.")

        self.t_trans_sens_x = slider_row(parent, "Lateral — 10 = rango calibrado", 1.0, 50.0, 0.5,
                                         get('t_trans_sens_x'), HELP["t_trans_sens"])
        self.t_trans_sens_y = slider_row(parent, "Vertical — 10 = rango calibrado", 1.0, 50.0, 0.5,
                                         get('t_trans_sens_y'), HELP["t_trans_sens"])
        self.t_trans_sens_z = slider_row(parent, "Profundidad — 10 = rango calibrado", 1.0, 50.0, 0.5,
                                         get('t_trans_sens_z'), HELP["t_trans_sens"])

        subtitle(parent, "Zona muerta por eje (la profundidad necesita más)")
        self.t_trans_dz_x = slider_row(parent, "Zona muerta lateral (%)", 0.0, 0.30, 0.005,
                                       get('t_trans_deadzone_x'), HELP["t_trans_deadzone"])
        self.t_trans_dz_y = slider_row(parent, "Zona muerta vertical (%)", 0.0, 0.30, 0.005,
                                       get('t_trans_deadzone_y'), HELP["t_trans_deadzone"])
        self.t_trans_dz_z = slider_row(parent, "Zona muerta profundidad (%)", 0.0, 0.30, 0.005,
                                       get('t_trans_deadzone_z'), HELP["t_trans_deadzone"])

        subtitle(parent, "Curva de respuesta por eje")
        self.t_trans_curve_x = slider_row(parent, "Curva lateral", 1.0, 4.0, 0.1,
                                          get('t_trans_curve_x'), HELP["t_trans_curve"])
        self.t_trans_curve_y = slider_row(parent, "Curva vertical", 1.0, 4.0, 0.1,
                                          get('t_trans_curve_y'), HELP["t_trans_curve"])
        self.t_trans_curve_z = slider_row(parent, "Curva profundidad", 1.0, 4.0, 0.1,
                                          get('t_trans_curve_z'), HELP["t_trans_curve"])

        # Sentido de cada eje: depende de la cámara, así que se corrige aquí.
        inv_row = tk.Frame(parent, bg=C.PANEL)
        inv_row.pack(fill='x', padx=pad, pady=(10, 0))
        tk.Label(inv_row, text="Invertir sentido:", bg=C.PANEL, fg=C.TEXT_STRONG,
                 font=FONTS.label).pack(side='left')
        self.var_invert = {}
        self.invert_checks = []
        for key, text in (("x", "Lateral"), ("y", "Vertical"), ("z", "Profundidad")):
            var = tk.BooleanVar(value=bool(cfg.get(f't_trans_invert_{key}', INVERT_DEFAULTS[key])))
            chk = checkbox(inv_row, text, var, font=FONTS.note)
            chk.pack(side='left', padx=(8, 0))
            self.var_invert[key] = var
            self.invert_checks.append(chk)
        help_icon(inv_row, HELP["t_trans_invert"]).pack(side='right', padx=(10, 0))

        subtitle(parent, "Filtro de traslación (independiente del de rotación)", pady=(10, 0))
        self.t_trans_min_cutoff = slider_row(parent, "Estabilidad en reposo (Hz)", 0.1, 5.0, 0.1,
                                             get('t_trans_min_cutoff'), HELP["t_trans_filter"])
        self.t_trans_beta = slider_row(parent, "Reacción al movimiento (beta)", 0.0, 0.5, 0.005,
                                       get('t_trans_beta'), HELP["t_trans_filter"])
        self.t_trans_min_cutoff_z = slider_row(parent, "Estabilidad en profundidad (Hz)", 0.1, 5.0, 0.1,
                                               get('t_trans_min_cutoff_z'), HELP["t_trans_filter_z"])
        self.t_trans_beta_z = slider_row(parent, "Reacción en profundidad (beta)", 0.0, 0.5, 0.005,
                                         get('t_trans_beta_z'), HELP["t_trans_filter_z"])
        divider(parent)

        # --- PIVOTE DEL CUELLO ---
        section_header(parent, "PIVOTE DEL CUELLO")
        note(parent, "Girar la cabeza no debería desplazar la cámara. Ajusta estos "
                     "dos valores mirando las barras del preview: gira la cabeza sin "
                     "mover el cuerpo y busca que se queden quietas.")
        self.t_neck_height = slider_row(parent, "Alto del cuello a la cara (cm)", -20.0, 20.0, 0.5,
                                        get('t_neck_height_cm'), HELP["t_neck"])
        self.t_neck_depth = slider_row(parent, "Fondo del cuello a la cara (cm)", -20.0, 20.0, 0.5,
                                       get('t_neck_depth_cm'), HELP["t_neck"])
        divider(parent)

        # --- RANGO DE TRASLACIÓN: asistente de 6 pasos ---
        section_header(parent, "RANGO DE TRASLACIÓN (Calibración guiada)")
        self.lbl_status = note(parent, self.status_text())

        self.btn_calibrate = primary_button(
            parent, "📐 Calibrar rango de traslación (6 pasos)", command=self.open_wizard)
        self.btn_calibrate.pack(fill='x', padx=pad, pady=(0, 5))

        self.btn_reset = secondary_button(
            parent, f"↺ Descartar calibración (volver a ±{DEFAULT_TRANS_LIMIT_CM:.0f} cm)",
            command=self.reset)
        self.btn_reset.pack(fill='x', padx=pad, pady=(0, 5))
        divider(parent)

    # --- controles a atenuar con fuente externa ---
    @property
    def sliders(self):
        return [getattr(self, attr) for attr in SLIDER_ATTR.values()]

    @property
    def buttons(self):
        return [self.btn_calibrate, self.btn_reset] + list(self.invert_checks)

    # --- calibración ---
    def status_text(self):
        return format_trans_calibration_status(self.ctx.config.get("head_trans_limits", {}))

    def refresh_status(self):
        self.lbl_status.config(text=self.status_text())

    def open_wizard(self):
        return open_wizard(self.ctx.root, self.ctx.tracker,
                           translation_spec(self.ctx, self.refresh_status))

    def reset(self):
        fresh = {"units": TRANS_CALIB_UNITS}
        self.ctx.config["head_trans_limits"] = fresh
        if self.ctx.tracker:
            self.ctx.tracker.config["head_trans_limits"] = dict(fresh)
        self.refresh_status()

    # --- configuración ---
    def read_config(self):
        cfg = {key: getattr(self, attr).get() for key, attr in SLIDER_ATTR.items()}
        for key in INVERT_DEFAULTS:
            cfg[f't_trans_invert_{key}'] = bool(self.var_invert[key].get())
        # Se escribe solo vía el asistente de calibración.
        cfg['head_trans_limits'] = self.ctx.config.get(
            'head_trans_limits', {'units': TRANS_CALIB_UNITS})
        return cfg

    def apply_config(self, cfg):
        for key, attr in SLIDER_ATTR.items():
            getattr(self, attr).set(cfg.get(key, DEFAULTS[key]))
        for key, default in INVERT_DEFAULTS.items():
            self.var_invert[key].set(bool(cfg.get(f't_trans_invert_{key}', default)))
        self.ctx.config["head_trans_limits"] = cfg.get(
            "head_trans_limits", {"units": TRANS_CALIB_UNITS})
        if self.ctx.tracker:
            self.ctx.tracker.config["head_trans_limits"] = dict(self.ctx.config["head_trans_limits"])
        self.refresh_status()
