"""Panel derecho del configurador: stick, cabeza y entradas crudas."""
from frontend.preview.head_view import HeadView
from frontend.preview.inputs_view import InputsView
from frontend.preview.stick_view import StickView


class PreviewPanel:
    """Arma las tres vistas y las actualiza en cada vuelta del lazo."""

    def __init__(self, parent, ctx, physics, state, on_recenter):
        self.physics = physics
        self.state = state
        self.stick = StickView(parent)
        self.head = HeadView(parent, ctx, on_recenter)
        self.inputs = InputsView(parent)

    def update(self, cfg, tracker):
        # Misma física que el vuelo (rust_motor.RustPhysics).
        self.physics.update_config(
            float(cfg['radius']),
            float(cfg['curve']),
            float(cfg['deadzone']),
            float(cfg.get('t_snap_axis', 0.25)),
            float(cfg['snap']),
            float(cfg['outer']),
        )
        s = self.state
        with s.lock:
            s.hard = float(self.physics.hard_limit())
            s.dx = max(-s.hard, min(s.hard, s.dx))
            s.dy = max(-s.hard, min(s.hard, s.dy))
            dx, dy = s.dx, s.dy

        fx, fy, in_deadzone, _ = self.physics.calculate(float(dx), float(dy))
        self.stick.update(fx, fy, in_deadzone)
        self.head.update(tracker)
        self.inputs.update(s)
