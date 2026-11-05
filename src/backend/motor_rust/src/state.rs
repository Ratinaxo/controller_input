use crate::physics::StickParams;

pub struct SharedState {
    /// Ejes de cabeza normalizados a -1.0..1.0, listos para emitir.
    /// Rotación: yaw / pitch / roll. Traslación: tx (lateral),
    /// ty (vertical), tz (profundidad). La Fase B del 6DOF llena los
    /// cuatro últimos; hasta entonces el tracker solo mueve yaw/pitch.
    pub head_yaw: f32,
    pub head_pitch: f32,
    pub head_roll: f32,
    pub head_tx: f32,
    pub head_ty: f32,
    pub head_tz: f32,
    /// Parámetros del stick (los mismos que usa la vista previa de la GUI).
    pub params: StickParams,
    pub last_x: f32,
    pub last_y: f32,
    pub last_throttle: f32,
    pub last_rudder: f32,
    pub is_snapped: bool,
    pub in_deadzone: bool,
    pub recenter_req: bool,
    pub exit_req: bool,
    pub is_paused: bool,
}

impl SharedState {
    pub fn new() -> Self {
        Self {
            head_yaw: 0.0,
            head_pitch: 0.0,
            head_roll: 0.0,
            head_tx: 0.0,
            head_ty: 0.0,
            head_tz: 0.0,
            params: StickParams::default(),
            last_x: 0.0,
            last_y: 0.0,
            last_throttle: 0.0,
            last_rudder: 0.0,
            is_snapped: false,
            in_deadzone: false,
            recenter_req: false,
            exit_req: false,
            is_paused: false,
        }
    }
}
