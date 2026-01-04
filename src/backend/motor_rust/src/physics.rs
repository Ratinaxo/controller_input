use pyo3::prelude::*;

#[pyclass]
#[derive(Clone)]
pub struct RustPhysics {
    radius: f32, curve: f32, deadzone: f32,
    snap_axis: f32, snap_threshold: f32, outer: f32,
}

#[pymethods]
impl RustPhysics {
    #[new]
    pub fn new(radius: f32, curve: f32, deadzone: f32, snap_axis: f32, snap_threshold: f32, outer: f32) -> Self {
        RustPhysics { radius, curve, deadzone, snap_axis, snap_threshold, outer }
    }

    pub fn update_config(&mut self, r: f32, c: f32, d: f32, sa: f32, st: f32, o: f32) {
        self.radius = r; self.curve = c; self.deadzone = d; 
        self.snap_axis = sa; self.snap_threshold = st; self.outer = o;
    }

    pub fn calculate(&self, dx: f32, dy: f32) -> (f32, f32, bool, bool) {
        let hard = self.radius + self.outer;
        let rx = dx.abs().min(hard).copysign(dx) / self.radius;
        let ry = dy.abs().min(hard).copysign(dy) / self.radius;
        let mag = rx.hypot(ry);
        let in_d = mag < self.deadzone;
        let mut fx = 0.0; let mut fy = 0.0;
        if !in_d {
            fx = rx.abs().min(1.0).powf(self.curve).copysign(rx);
            fy = ry.abs().min(1.0).powf(self.curve).copysign(ry);
        }
        (fx.clamp(-1.0, 1.0), fy.clamp(-1.0, 1.0), in_d, false)
    }
}