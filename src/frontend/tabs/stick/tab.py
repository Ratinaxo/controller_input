"""Pestaña Stick / Mouse: geometría y respuesta del stick."""
from frontend.components import section_header, divider, slider_row
from frontend.style import spacing as S
from frontend.tabs.base import Tab
from frontend.tabs.stick.curve_graph import CurveGraph
from frontend.tabs.stick.help import HELP

DEFAULTS = {"radius": 300, "outer": 50, "curve": 1.0, "deadzone": 0.05, "snap": 0.05}


class StickTab(Tab):
    title = "🕹️ Stick / Mouse"
    owned_keys = ("radius", "curve", "deadzone", "snap", "outer")

    def build(self, parent):
        cfg = self.ctx.config
        pad = S.PAD_TAB
        self.graph = None

        section_header(parent, "GEOMETRÍA", pady=(pad, 5))
        self.s_radius = slider_row(parent, "Radio Máximo (px)", 100, 800, 10,
                                   cfg.get('radius', DEFAULTS["radius"]), HELP["radius"],
                                   self.redraw_curve)
        self.s_outer = slider_row(parent, "Zona Saturación Extra (px)", 0, 200, 5,
                                  cfg.get('outer', DEFAULTS["outer"]), HELP["outer"])

        divider(parent)

        section_header(parent, "RESPUESTA")
        self.s_curve = slider_row(parent, "Linealidad (Curva)", 1.0, 4.0, 0.1,
                                  cfg.get('curve', DEFAULTS["curve"]), HELP["curve"],
                                  self.redraw_curve)
        self.s_deadzone = slider_row(parent, "Zona Muerta (%)", 0.0, 0.30, 0.01,
                                     cfg.get('deadzone', DEFAULTS["deadzone"]), HELP["deadzone"],
                                     self.redraw_curve)
        self.s_snap = slider_row(parent, "Magnetismo Ejes (%)", 0.0, 0.20, 0.01,
                                 cfg.get('snap', DEFAULTS["snap"]), HELP["snap"])

        self.graph = CurveGraph(parent, self.s_curve.get, self.s_deadzone.get)
        self.graph.draw()

    def redraw_curve(self):
        if self.graph is not None:
            self.graph.draw()

    def read_config(self):
        return {
            'radius': int(self.s_radius.get()),
            'curve': self.s_curve.get(),
            'deadzone': self.s_deadzone.get(),
            'snap': self.s_snap.get(),
            'outer': int(self.s_outer.get()),
        }

    def apply_config(self, cfg):
        self.s_radius.set(cfg.get('radius', DEFAULTS["radius"]))
        self.s_curve.set(cfg.get('curve', DEFAULTS["curve"]))
        self.s_deadzone.set(cfg.get('deadzone', DEFAULTS["deadzone"]))
        self.s_snap.set(cfg.get('snap', DEFAULTS["snap"]))
        self.s_outer.set(cfg.get('outer', DEFAULTS["outer"]))
        self.redraw_curve()
