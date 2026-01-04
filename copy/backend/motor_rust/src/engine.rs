use pyo3::prelude::*;
use std::sync::{Arc, RwLock};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;
use std::path::PathBuf;
use evdev::{Device, EventType, RelativeAxisCode, KeyCode, InputEvent, AbsoluteAxisCode, SynchronizationCode};
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
            eprintln!("[RUST THREAD] Iniciando...");
            
            let mut mouse_dev = match Device::open(PathBuf::from(&mouse_path)) {
                Ok(d) => d,
                Err(e) => { eprintln!("[RUST ERROR] Mouse open fail: {}", e); return; }
            };
            let _ = mouse_dev.grab();

            let mut joy_out = match create_virtual_joystick() {
                Ok(d) => d,
                Err(e) => { eprintln!("[RUST CRITICAL] Uinput fail: {}", e); return; }
            };

            let mut v_x = screen_w / 2.0;
            let mut v_y = screen_h / 2.0;
            let center_x = screen_w / 2.0;
            let center_y = screen_h / 2.0;
            let mut throttle = 0.0f32;
            let mut rudder = 0.0f32;
            let mut btn_trigger = false; let mut btn_thumb = false;
            let mut btn_top = false; let mut btn_side1 = false; let mut btn_side2 = false;

            let must_recenter = {
                    let mut s = state_clone.write().unwrap();
                    if s.recenter_req {
                        s.recenter_req = false;
                        true
                    } else {
                        false
                    }
                };

                if must_recenter {
                    v_x = center_x;
                    v_y = center_y;
                    rudder = 0.0;
                    // (Throttle no se suele recentrar por seguridad)
                }
                
            while running_clone.load(Ordering::SeqCst) {
                // A. LEER MOUSE
                if let Ok(events) = mouse_dev.fetch_events() {
                    for ev in events {
                        if ev.event_type() == EventType::RELATIVE {
                            match RelativeAxisCode(ev.code()) {
                                RelativeAxisCode::REL_X => v_x = (v_x + ev.value() as f32).clamp(0.0, screen_w),
                                RelativeAxisCode::REL_Y => v_y = (v_y + ev.value() as f32).clamp(0.0, screen_h),
                                RelativeAxisCode::REL_WHEEL => throttle = (throttle + (ev.value() as f32 * 0.05)).clamp(-1.0, 1.0),
                                RelativeAxisCode::REL_HWHEEL => rudder = (rudder + (ev.value() as f32 * 0.20)).clamp(-1.0, 1.0),
                                _ => {}
                            }
                        } else if ev.event_type() == EventType::KEY {
                            let val = ev.value() > 0;
                            match KeyCode(ev.code()) {
                                KeyCode::BTN_LEFT => btn_trigger = val,
                                KeyCode::BTN_RIGHT => btn_thumb = val,
                                KeyCode::BTN_MIDDLE => btn_top = val,
                                KeyCode::BTN_SIDE => btn_side1 = val,
                                KeyCode::BTN_EXTRA => btn_side2 = val,
                                _ => {}
                            }
                        }
                    }
                }

                // B. LEER ESTADO
                let (radius, curve, deadzone, snap_axis, snap_thresh, outer, h_yaw, h_pitch) = {
                    let s = state_clone.read().unwrap();
                    (s.radius, s.curve, s.deadzone, s.snap_axis, s.snap_threshold, s.outer, s.head_yaw, s.head_pitch)
                };

                // C. CALCULAR
                let dx = v_x - center_x;
                let dy = v_y - center_y;
                let hard = radius + outer;
                
                let rx = dx.abs().min(hard).copysign(dx) / radius;
                let ry = dy.abs().min(hard).copysign(dy) / radius;
                
                let mut snapped = false;
                let mut rx_s = rx; let mut ry_s = ry;
                if rx.abs() < snap_thresh { rx_s = 0.0; snapped = true; }
                if ry.abs() < snap_thresh { ry_s = 0.0; snapped = true; }
                if rx.abs() < (ry.abs() * snap_axis) { rx_s = 0.0; snapped = true; }
                else if ry.abs() < (rx.abs() * snap_axis) { ry_s = 0.0; snapped = true; }

                let mag = rx_s.hypot(ry_s);
                let in_d = mag < deadzone;
                let mut fx = 0.0; let mut fy = 0.0;
                if !in_d {
                    fx = rx_s.abs().min(1.0).powf(curve).copysign(rx_s);
                    fy = ry_s.abs().min(1.0).powf(curve).copysign(ry_s);
                }

                // D. ESCRIBIR
                fn raw(v: f32) -> i32 { (v * 32767.0) as i32 }
                fn btn(b: bool) -> i32 { if b { 1 } else { 0 } }
                
                let events = [
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_X.0, raw(fx)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Y.0, raw(fy)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Z.0, raw(throttle)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RZ.0, raw(rudder)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RX.0, raw(h_yaw)),
                    InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RY.0, raw(h_pitch)),
                    InputEvent::new(EventType::KEY.0, KeyCode::BTN_TRIGGER.0, btn(btn_trigger)),
                    InputEvent::new(EventType::KEY.0, KeyCode::BTN_THUMB.0, btn(btn_thumb)),
                    InputEvent::new(EventType::KEY.0, KeyCode::BTN_TOP.0, btn(btn_top)),
                    InputEvent::new(EventType::KEY.0, KeyCode::BTN_TOP2.0, btn(btn_side1)),
                    InputEvent::new(EventType::KEY.0, KeyCode::BTN_PINKIE.0, btn(btn_side2)),
                    InputEvent::new(EventType::SYNCHRONIZATION.0, SynchronizationCode::SYN_REPORT.0, 0),
                ];
                let _ = joy_out.emit(&events);

                // E. REPORTE
                if let Ok(mut s) = state_clone.try_write() {
                    s.last_x = fx; s.last_y = fy;
                    s.last_throttle = throttle; s.last_rudder = rudder;
                    s.is_snapped = snapped; s.in_deadzone = in_d;
                }
                thread::sleep(Duration::from_micros(900));
            }
            let _ = mouse_dev.ungrab();
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
        if let Ok(mut s) = self.state.write() {
            s.recenter_req = true;
        }
    }
}