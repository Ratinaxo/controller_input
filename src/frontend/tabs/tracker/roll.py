"""Sección Roll: inclinar la cabeza de lado."""
from frontend.components import section_header, divider, slider_row
from frontend.tabs.tracker.help import HELP

DEFAULTS = {'t_sens_roll': 10.0, 't_roll_deadzone': 0.03, 'head_roll_limit_deg': 30.0}


class RollSection:
    owned_keys = tuple(DEFAULTS)

    def __init__(self, ctx):
        self.ctx = ctx

    def build(self, parent):
        cfg = self.ctx.config
        get = lambda k: cfg.get(k, DEFAULTS[k])
        section_header(parent, "ROLL (inclinar la cabeza de lado)")
        self.t_sens_roll = slider_row(parent, "Sensibilidad — 10 = límite de abajo", 1.0, 50.0, 0.5,
                                      get('t_sens_roll'), HELP["t_sens_roll"])
        self.t_roll_deadzone = slider_row(parent, "Zona muerta (%)", 0.0, 0.30, 0.005,
                                          get('t_roll_deadzone'), HELP["t_roll_deadzone"])
        self.head_roll_limit = slider_row(parent, "Límite de inclinación (°)", 5.0, 90.0, 1.0,
                                          get('head_roll_limit_deg'), HELP["head_roll_limit_deg"])
        divider(parent)

    @property
    def sliders(self):
        return [self.t_sens_roll, self.t_roll_deadzone, self.head_roll_limit]

    def read_config(self):
        return {
            't_sens_roll': self.t_sens_roll.get(),
            't_roll_deadzone': self.t_roll_deadzone.get(),
            'head_roll_limit_deg': self.head_roll_limit.get(),
        }

    def apply_config(self, cfg):
        self.t_sens_roll.set(cfg.get('t_sens_roll', DEFAULTS['t_sens_roll']))
        self.t_roll_deadzone.set(cfg.get('t_roll_deadzone', DEFAULTS['t_roll_deadzone']))
        self.head_roll_limit.set(cfg.get('head_roll_limit_deg', DEFAULTS['head_roll_limit_deg']))
