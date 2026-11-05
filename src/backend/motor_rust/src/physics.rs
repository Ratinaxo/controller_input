use pyo3::prelude::*;

/// Parámetros de la física del stick. Es la ÚNICA definición de la
/// matemática: la usan tanto el motor de vuelo (engine.rs) como la vista
/// previa de la GUI (RustPhysics.calculate), así que lo que se ve en la
/// GUI es exactamente lo que se vuela.
#[derive(Clone, Copy, Debug)]
pub struct StickParams {
    pub radius: f32,
    pub curve: f32,
    pub deadzone: f32,
    pub snap_axis: f32,
    pub snap_threshold: f32,
    pub outer: f32,
}

impl Default for StickParams {
    fn default() -> Self {
        StickParams {
            radius: 300.0,
            curve: 1.0,
            deadzone: 0.05,
            snap_axis: 0.1,
            snap_threshold: 0.05,
            outer: 0.0,
        }
    }
}

impl StickParams {
    /// Radio con valores seguros (evita divisiones por cero).
    fn safe_radius(&self) -> f32 {
        self.radius.max(1.0)
    }

    /// Límite duro del recorrido virtual en píxeles: radio + zona de
    /// saturación extra. El acumulador del mouse se acota a ±este valor,
    /// así que al revertir un movimiento a fondo el stick empieza a volver
    /// tras recorrer como máximo `outer` píxeles.
    pub fn hard_limit(&self) -> f32 {
        self.safe_radius() + self.outer.max(0.0)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StickOutput {
    pub x: f32,
    pub y: f32,
    pub in_deadzone: bool,
    pub is_snapped: bool,
}

/// Aplica una curva simétrica a un valor en [-1, 1].
fn apply_curve(v: f32, curve: f32) -> f32 {
    v.abs().min(1.0).powf(curve.max(0.01)).copysign(v)
}

/// Convierte el desplazamiento del mouse (px, relativo al centro) en la
/// salida del stick en [-1, 1].
///
/// 1. Se acota el desplazamiento al límite duro (radio + outer).
/// 2. Zona muerta RADIAL con reescalado: la magnitud se remapea de
///    [deadzone, ∞) a [0, ∞) conservando la dirección, así la salida parte
///    de 0.0 justo en el borde de la zona muerta (sin salto).
/// 3. Cada eje se satura en ±1 (dominio cuadrado: se puede comandar
///    alabeo y cabeceo máximos a la vez, como en un stick real).
/// 4. La curva de respuesta se aplica por eje.
pub fn compute(dx: f32, dy: f32, p: &StickParams) -> StickOutput {
    let hard = p.hard_limit();
    let radius = p.safe_radius();
    let dz = p.deadzone.clamp(0.0, 0.95);

    let rx = dx.clamp(-hard, hard) / radius;
    let ry = dy.clamp(-hard, hard) / radius;
    let mag = rx.hypot(ry);

    if mag <= dz || mag <= f32::EPSILON {
        return StickOutput { x: 0.0, y: 0.0, in_deadzone: true, is_snapped: false };
    }

    let scale = ((mag - dz) / (1.0 - dz)) / mag;
    let sx = (rx * scale).clamp(-1.0, 1.0);
    let sy = (ry * scale).clamp(-1.0, 1.0);

    StickOutput {
        x: apply_curve(sx, p.curve),
        y: apply_curve(sy, p.curve),
        in_deadzone: false,
        is_snapped: false,
    }
}

#[pyclass]
#[derive(Clone)]
pub struct RustPhysics {
    params: StickParams,
}

#[pymethods]
impl RustPhysics {
    #[new]
    pub fn new(radius: f32, curve: f32, deadzone: f32, snap_axis: f32, snap_threshold: f32, outer: f32) -> Self {
        RustPhysics {
            params: StickParams { radius, curve, deadzone, snap_axis, snap_threshold, outer },
        }
    }

    pub fn update_config(&mut self, r: f32, c: f32, d: f32, sa: f32, st: f32, o: f32) {
        self.params = StickParams {
            radius: r, curve: c, deadzone: d, snap_axis: sa, snap_threshold: st, outer: o,
        };
    }

    /// Límite duro (radio + outer) para que la GUI acote su acumulador
    /// igual que el motor.
    pub fn hard_limit(&self) -> f32 {
        self.params.hard_limit()
    }

    /// Devuelve (x, y, in_deadzone, is_snapped).
    pub fn calculate(&self, dx: f32, dy: f32) -> (f32, f32, bool, bool) {
        let o = compute(dx, dy, &self.params);
        (o.x, o.y, o.in_deadzone, o.is_snapped)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn params(radius: f32, curve: f32, deadzone: f32, outer: f32) -> StickParams {
        StickParams { radius, curve, deadzone, outer, ..Default::default() }
    }

    #[test]
    fn center_is_zero_and_in_deadzone() {
        let o = compute(0.0, 0.0, &params(320.0, 1.0, 0.07, 30.0));
        assert_eq!((o.x, o.y, o.in_deadzone), (0.0, 0.0, true));
    }

    #[test]
    fn deadzone_edge_is_continuous() {
        let p = params(320.0, 1.0, 0.07, 30.0);
        let edge = 0.07 * 320.0;
        let just_out = compute(edge + 0.01, 0.0, &p);
        assert!(!just_out.in_deadzone);
        assert!(just_out.x > 0.0 && just_out.x < 0.001, "salto en el borde: {}", just_out.x);
    }

    #[test]
    fn reaches_full_scale_at_radius() {
        let p = params(320.0, 1.6, 0.07, 30.0);
        let o = compute(320.0, 0.0, &p);
        assert!((o.x - 1.0).abs() < 1e-5, "x = {}", o.x);
        assert_eq!(o.y, 0.0);
    }

    #[test]
    fn corners_reachable() {
        let p = params(320.0, 1.0, 0.07, 30.0);
        let o = compute(320.0, -320.0, &p);
        assert_eq!((o.x, o.y), (1.0, -1.0));
    }

    #[test]
    fn saturates_beyond_radius() {
        let p = params(320.0, 1.0, 0.05, 30.0);
        for d in [320.0, 340.0, 350.0, 5000.0] {
            assert_eq!(compute(d, 0.0, &p).x, 1.0);
            assert_eq!(compute(-d, 0.0, &p).x, -1.0);
        }
    }

    #[test]
    fn hard_limit_is_radius_plus_outer() {
        assert_eq!(params(320.0, 1.0, 0.05, 30.0).hard_limit(), 350.0);
        assert_eq!(params(320.0, 1.0, 0.05, -10.0).hard_limit(), 320.0);
    }

    #[test]
    fn monotonic_and_continuous_along_axis() {
        let p = params(300.0, 2.0, 0.1, 50.0);
        let mut prev = 0.0f32;
        let mut d = 0.0f32;
        while d <= 360.0 {
            let x = compute(d, 0.0, &p).x;
            assert!(x >= prev - 1e-6, "no monótona en {d}");
            assert!(x - prev < 0.02, "salto de {} en {d}", x - prev);
            prev = x;
            d += 0.5;
        }
    }

    #[test]
    fn symmetric() {
        let p = params(300.0, 1.5, 0.05, 0.0);
        let a = compute(120.0, 45.0, &p);
        let b = compute(-120.0, -45.0, &p);
        assert!((a.x + b.x).abs() < 1e-6 && (a.y + b.y).abs() < 1e-6);
    }

    #[test]
    fn degenerate_params_do_not_panic() {
        let p = params(0.0, 0.0, 2.0, -5.0);
        let o = compute(10.0, 10.0, &p);
        assert!(o.x.is_finite() && o.y.is_finite());
    }
}
