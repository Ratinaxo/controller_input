"""Réplica Python de rust_motor para pruebas (misma matemática que filter.rs / physics.rs)."""
import math
BUTTON_CODES = list(range(0x120, 0x130))
def virtual_button_codes(): return list(BUTTON_CODES)
STICK_AXES = [("Alabeo (Stick X)", 0x00), ("Cabeceo (Stick Y)", 0x01),
              ("Timón (Twist)", 0x05), ("Gases (Slider)", 0x06),
              ("POV X", 0x10), ("POV Y", 0x11)]
HEAD_AXES = [("Traslación lateral", 0x00), ("Traslación vertical", 0x01),
             ("Traslación en profundidad", 0x02), ("Yaw", 0x03),
             ("Pitch", 0x04), ("Roll", 0x05)]
def stick_axis_order(): return list(STICK_AXES)
def head_axis_order(): return list(HEAD_AXES)
class RustFilter:
    def __init__(self, m, b, d): self.min_cutoff, self.beta, self.d_cutoff = m, b, d; self.reset()
    def reset(self): self.x_prev = None; self.t_prev = None; self.dx_prev = 0.0
    @staticmethod
    def _a(c, te): r = 2*math.pi*max(c,1e-4)*te; return r/(r+1)
    def filter(self, t, x):
        if self.x_prev is None: self.x_prev, self.t_prev, self.dx_prev = x, t, 0.0; return x
        te = t - self.t_prev
        if te <= 0: return self.x_prev
        dx = (x - self.x_prev)/te; ad = self._a(self.d_cutoff, te)
        dxh = ad*dx + (1-ad)*self.dx_prev; a = self._a(self.min_cutoff + self.beta*abs(dxh), te)
        xh = a*x + (1-a)*self.x_prev; self.x_prev, self.dx_prev, self.t_prev = xh, dxh, t; return xh
class RustPhysics:
    def __init__(self, r, c, d, sa, st, o): self.update_config(r, c, d, sa, st, o)
    def update_config(self, r, c, d, sa, st, o): self.r, self.c, self.d, self.o = r, c, d, o
    def hard_limit(self): return max(self.r, 1.0) + max(self.o, 0.0)
    def calculate(self, dx, dy):
        h = self.hard_limit(); r = max(self.r, 1.0); dz = min(max(self.d, 0), 0.95)
        rx = max(-h, min(h, dx))/r; ry = max(-h, min(h, dy))/r; mag = math.hypot(rx, ry)
        if mag <= dz or mag <= 1e-7: return 0.0, 0.0, True, False
        s = ((mag-dz)/(1-dz))/mag; cl = lambda v: max(-1.0, min(1.0, v))
        cv = lambda v: math.copysign(min(abs(v),1.0)**max(self.c,0.01), v)
        return cv(cl(rx*s)), cv(cl(ry*s)), False, False
class RustEngine: pass
