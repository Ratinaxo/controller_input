use pyo3::prelude::*;
use std::sync::{Arc, RwLock};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;
use std::path::PathBuf;
use evdev::{Device, EventType, RelativeAxisCode, InputEvent, AbsoluteAxisCode, SynchronizationCode};
use crate::state::SharedState;
use crate::device::create_virtual_joystick;

#[pyclass]
pub struct RustEngine {
    state: Arc<RwLock<SharedState>>,
    running: Arc<AtomicBool>,
    thread_handle: Option<thread::JoinHandle<()>>,
}

#[pymethods]
impl RustEngine {
    #[new]
    fn new() -> Self {
        RustEngine {
            state: Arc::new(RwLock::new(SharedState::new())),
            running: Arc::new(AtomicBool::new(false)),
            thread_handle: None,
        }
    }

    fn start(&mut self, mouse_path: String, screen_w: f32, screen_h: f32) -> PyResult<()> {
        let state_clone = Arc::clone(&self.state);
        let running_clone = Arc::clone(&self.running);
        running_clone.store(true, Ordering::SeqCst);

        let handle = thread::spawn(move || {
            let mut mouse_dev = Device::open(PathBuf::from(&mouse_path)).expect("Fail mouse");
            let _ = mouse_dev.grab();
            mouse_dev.set_nonblocking(true).ok();
            
            let mut joy_out = create_virtual_joystick().expect("Fail uinput");
            let mut v_x = screen_w / 2.0;
            let mut v_y = screen_h / 2.0;
            let center_x = screen_w / 2.0;
            let center_y = screen_h / 2.0;
            let mut throttle = 0.0f32;
            let mut rudder = 0.0f32;

            while running_clone.load(Ordering::SeqCst) {
                // A. REVISAR PETICIONES DE PYTHON (Lock rápido)
                let (must_recenter, must_exit) = {
                    let mut s = state_clone.write().unwrap();
                    let r = s.recenter_req; s.recenter_req = false;
                    (r, s.exit_req)
                };

                if must_exit { break; }
                if must_recenter { v_x = center_x; v_y = center_y; rudder = 0.0; }

                // B. LEER MOUSE
                if let Ok(events) = mouse_dev.fetch_events() {
                    for ev in events {
                        if ev.event_type() == EventType::RELATIVE {
                            let c = ev.code(); let val = ev.value() as f32;
                            if c == RelativeAxisCode::REL_X.0 { v_x = (v_x + val).clamp(0.0, screen_w); }
                            else if c == RelativeAxisCode::REL_Y.0 { v_y = (v_y + val).clamp(0.0, screen_h); }
                            else if c == RelativeAxisCode::REL_WHEEL.0 { throttle = (throttle + val * 0.05).clamp(-1.0, 1.0); }
                            else if c == RelativeAxisCode::REL_HWHEEL.0 { rudder = (rudder + val * 0.20).clamp(-1.0, 1.0); }
                        }
                    }
                }

                // C. CÁLCULO FÍSICO
                let (radius, curve, deadzone, hy, hp) = {
                    let s = state_clone.read().unwrap();
                    (s.radius, s.curve, s.deadzone, s.head_yaw, s.head_pitch)
                };
                let dx = v_x - center_x; let dy = v_y - center_y;
                let rx = dx / radius; let ry = dy / radius;
                let mag = rx.hypot(ry);
                let in_d = mag < deadzone;
                let mut fx = 0.0; let mut fy = 0.0;
                if !in_d {
                    fx = rx.abs().min(1.0).powf(curve).copysign(rx);
                    fy = ry.abs().min(1.0).powf(curve).copysign(ry);
                }

                // D. EMITIR
                fn raw(v: f32) -> i32 { (v * 32767.0) as i32 }
                let evs = [
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_X.0, raw(fx)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Y.0, raw(fy)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Z.0, raw(throttle)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RZ.0, raw(rudder)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RX.0, raw(hy)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RY.0, raw(hp)),
                    InputEvent::new(EventType::SYNCHRONIZATION.0, SynchronizationCode::SYN_REPORT.0, 0),
                ];
                let _ = joy_out.emit(&evs);

                if let Ok(mut s) = state_clone.try_write() {
                    s.last_x = fx; s.last_y = fy; s.last_throttle = throttle; s.last_rudder = rudder;
                    s.in_deadzone = in_d;
                }
                thread::sleep(Duration::from_micros(900));
            }
            let _ = mouse_dev.ungrab();
            running_clone.store(false, Ordering::SeqCst);
        });
        self.thread_handle = Some(handle);
        Ok(())
    }

    fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        if let Some(handle) = self.thread_handle.take() { let _ = handle.join(); }
    }

    fn update_tracker(&mut self, yaw: f32, pitch: f32) {
        if let Ok(mut s) = self.state.write() { s.head_yaw = yaw; s.head_pitch = pitch; }
    }

    fn update_config(&mut self, r: f32, c: f32, d: f32, sa: f32, st: f32, o: f32) {
        if let Ok(mut s) = self.state.write() {
            s.radius = r; s.curve = c; s.deadzone = d; s.snap_axis = sa; s.snap_threshold = st; s.outer = o;
        }
    }

    fn get_hud_data(&self) -> (f32, f32, f32, f32, bool, bool) {
        let s = self.state.read().unwrap();
        (s.last_x, s.last_y, s.last_throttle, s.last_rudder, s.is_snapped, s.in_deadzone)
    }

    fn recenter(&mut self) {
        if let Ok(mut s) = self.state.write() { s.recenter_req = true; }
    }
    
    fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }
    
    fn request_exit(&mut self) {
        if let Ok(mut s) = self.state.write() { s.exit_req = true; }
    }
}