use pyo3::prelude::*;
use std::f32::consts::PI;

#[pyclass]
pub struct RustFilter {
    min_cutoff: f32, beta: f32, d_cutoff: f32,
    x_prev: Option<f32>, dx_prev: f32, t_prev: Option<f32>,
}

#[pymethods]
impl RustFilter {
    #[new]
    pub fn new(m: f32, b: f32, d: f32) -> Self {
        RustFilter { min_cutoff: m, beta: b, d_cutoff: d, x_prev: None, dx_prev: 0.0, t_prev: None }
    }
    
    #[setter]
    pub fn set_beta(&mut self, b: f32) { self.beta = b; }

    pub fn filter(&mut self, t: f32, x: f32) -> f32 {
        if self.t_prev.is_none() { self.x_prev = Some(x); self.t_prev = Some(t); return x; }
        let t_e = t - self.t_prev.unwrap();
        if t_e <= 0.0 { return self.x_prev.unwrap(); }
        let r = 2.0 * PI * self.d_cutoff * t_e; let a_d = r / (r + 1.0);
        let dx = (x - self.x_prev.unwrap()) / t_e;
        let dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev;
        let cutoff = self.min_cutoff + self.beta * dx_hat.abs();
        let r2 = 2.0 * PI * cutoff * t_e; let a = r2 / (r2 + 1.0);
        let x_hat = a * x + (1.0 - a) * self.x_prev.unwrap();
        self.x_prev = Some(x_hat); self.dx_prev = dx_hat; self.t_prev = Some(t);
        x_hat
    }
}