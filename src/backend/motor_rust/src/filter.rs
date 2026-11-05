use pyo3::prelude::*;
use std::f32::consts::PI;

/// Filtro One Euro (Casiez et al., 2012).
///
/// - `min_cutoff` (Hz): suavizado en reposo. Más bajo = más estable
///   quieto, pero más lento.
/// - `beta`: cuánto sube el corte con la velocidad. Más alto = MENOS lag
///   en los giros rápidos.
/// - `d_cutoff` (Hz): suavizado de la derivada.
#[pyclass]
pub struct RustFilter {
    min_cutoff: f32,
    beta: f32,
    d_cutoff: f32,
    x_prev: Option<f32>,
    dx_prev: f32,
    t_prev: Option<f32>,
}

fn alpha(cutoff: f32, t_e: f32) -> f32 {
    let r = 2.0 * PI * cutoff.max(1e-4) * t_e;
    r / (r + 1.0)
}

#[pymethods]
impl RustFilter {
    #[new]
    pub fn new(m: f32, b: f32, d: f32) -> Self {
        RustFilter { min_cutoff: m, beta: b, d_cutoff: d, x_prev: None, dx_prev: 0.0, t_prev: None }
    }

    #[setter]
    pub fn set_beta(&mut self, b: f32) {
        self.beta = b;
    }

    #[getter]
    pub fn get_beta(&self) -> f32 {
        self.beta
    }

    #[setter]
    pub fn set_min_cutoff(&mut self, m: f32) {
        self.min_cutoff = m;
    }

    #[getter]
    pub fn get_min_cutoff(&self) -> f32 {
        self.min_cutoff
    }

    /// Olvida el estado: la próxima muestra se devuelve tal cual.
    pub fn reset(&mut self) {
        self.x_prev = None;
        self.t_prev = None;
        self.dx_prev = 0.0;
    }

    pub fn filter(&mut self, t: f32, x: f32) -> f32 {
        let (x_prev, t_prev) = match (self.x_prev, self.t_prev) {
            (Some(xp), Some(tp)) => (xp, tp),
            _ => {
                self.x_prev = Some(x);
                self.t_prev = Some(t);
                self.dx_prev = 0.0;
                return x;
            }
        };
        let t_e = t - t_prev;
        if t_e <= 0.0 {
            return x_prev;
        }
        let dx = (x - x_prev) / t_e;
        let a_d = alpha(self.d_cutoff, t_e);
        let dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev;
        let cutoff = self.min_cutoff + self.beta * dx_hat.abs();
        let a = alpha(cutoff, t_e);
        let x_hat = a * x + (1.0 - a) * x_prev;
        self.x_prev = Some(x_hat);
        self.dx_prev = dx_hat;
        self.t_prev = Some(t);
        x_hat
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_sample_passthrough_and_reset() {
        let mut f = RustFilter::new(1.0, 0.05, 1.0);
        assert_eq!(f.filter(0.0, 5.0), 5.0);
        let _ = f.filter(0.033, 10.0);
        f.reset();
        assert_eq!(f.filter(1.0, -3.0), -3.0);
    }

    #[test]
    fn step_settles_within_reasonable_time() {
        // Con min_cutoff = 1 Hz, un escalón debe llegar al ~90% en < 0.5 s a 30 fps.
        let mut f = RustFilter::new(1.0, 0.0, 1.0);
        f.filter(0.0, 0.0);
        let mut t = 0.0;
        let mut y = 0.0;
        while t < 0.5 {
            t += 1.0 / 30.0;
            y = f.filter(t, 10.0);
        }
        assert!(y > 9.0, "demasiado lento: {y}");
    }

    #[test]
    fn higher_beta_means_less_lag() {
        let run = |beta: f32| {
            let mut f = RustFilter::new(1.0, beta, 1.0);
            let mut t = 0.0;
            let mut y = 0.0;
            // rampa de 100 unidades/s durante 0.3 s
            for i in 0..10 {
                t = i as f32 / 30.0;
                y = f.filter(t, 100.0 * t);
            }
            100.0 * t - y
        };
        assert!(run(0.1) < run(0.0));
    }
}
