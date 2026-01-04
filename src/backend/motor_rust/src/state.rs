// Datos compartidos entre Python (GUI/Tracker) y el Hilo de Rust
pub struct SharedState {
    pub head_yaw: f32,
    pub head_pitch: f32,
    pub radius: f32,
    pub curve: f32,
    pub deadzone: f32,
    pub snap_axis: f32,
    pub snap_threshold: f32,
    pub outer: f32,
    pub last_x: f32,
    pub last_y: f32,
    pub last_throttle: f32,
    pub last_rudder: f32,
    pub is_snapped: bool,
    pub in_deadzone: bool,
    pub recenter_req: bool,
    pub exit_req: bool,
}

impl SharedState {
    pub fn new() -> Self {
        Self {
            head_yaw: 0.0, head_pitch: 0.0,
            radius: 300.0, curve: 1.0, deadzone: 0.05, 
            snap_axis: 0.1, snap_threshold: 0.05, outer: 0.0,
            last_x: 0.0, last_y: 0.0, last_throttle: 0.0, last_rudder: 0.0,
            is_snapped: false, in_deadzone: false,
            recenter_req: false,
            exit_req: false,
        }
    }
}