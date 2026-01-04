use pyo3::prelude::*;
use evdev::{
    uinput::VirtualDevice, 
    AbsoluteAxisCode, UinputAbsSetup, AbsInfo, InputEvent, EventType,
    AttributeSet, KeyCode, InputId, BusType, SynchronizationCode
};
use std::io::Write;

#[pyclass]
struct RustJoystick {
    device: VirtualDevice,
    frame_count: u64,
}

#[pymethods]
impl RustJoystick {
    #[new]
    fn new() -> PyResult<Self> {
        eprintln!("[RUST] > Iniciando constructor RustJoystick (evdev 0.13.2)...");
        let _ = std::io::stderr().flush();

        let setup_axis = |code| {
            UinputAbsSetup::new(code, AbsInfo::new(0, -32767, 32767, 0, 0, 0))
        };

        // --- 1. DECLARAMOS LOS NUEVOS BOTONES AQUÍ ---
        let mut keys = AttributeSet::<KeyCode>::new();
        keys.insert(KeyCode::BTN_TRIGGER); // Click Izquierdo
        keys.insert(KeyCode::BTN_THUMB);   // Click Derecho
        keys.insert(KeyCode::BTN_TOP);     // Click Central
        keys.insert(KeyCode::BTN_TOP2);    // NUEVO: Lateral 1
        keys.insert(KeyCode::BTN_PINKIE);  // NUEVO: Lateral 2

        let device = VirtualDevice::builder()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Builder: {}", e)))?
            .name("Thrustmaster T.16000M (Virtual Rust)")
            .input_id(InputId::new(BusType::BUS_USB, 0x044f, 0xb10a, 0))
            .with_keys(&keys)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Keys: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_X))
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis X: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_Y))
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis Y: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_Z))  
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis Z: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RZ)) 
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis RZ: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RX)) 
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis RX: {}", e)))?
            .with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RY)) 
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("Error Axis RY: {}", e)))?
            .build()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(format!("FALLO CRÍTICO uinput: {}", e)))?;

        eprintln!("[RUST] > Dispositivo creado EXITOSAMENTE.");
        let _ = std::io::stderr().flush();

        Ok(RustJoystick { device, frame_count: 0 })
    }

    // --- 2. ACTUALIZAMOS LA FIRMA DE LA FUNCIÓN ---
    fn update(
        &mut self,
        x: f32, y: f32, throttle: f32, rudder: f32,
        head_yaw: f32, head_pitch: f32,
        btn_trigger: bool,
        btn_thumb: bool,
        btn_top: bool,
        btn_side1: bool, // NUEVO ARGUMENTO
        btn_side2: bool  // NUEVO ARGUMENTO
    ) -> PyResult<()> {
        self.frame_count += 1;

        if !x.is_finite() || !y.is_finite() { return Ok(()); }

        fn to_raw(val: f32) -> i32 { (val * 32767.0) as i32 }
        fn btn_val(pressed: bool) -> i32 { if pressed { 1 } else { 0 } }

        let events = [
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_X.0, to_raw(x)),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Y.0, to_raw(y)),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Z.0, to_raw(throttle)),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RZ.0, to_raw(rudder)),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RX.0, to_raw(head_yaw)),
            InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RY.0, to_raw(head_pitch)),
            
            InputEvent::new(EventType::KEY.0, KeyCode::BTN_TRIGGER.0, btn_val(btn_trigger)),
            InputEvent::new(EventType::KEY.0, KeyCode::BTN_THUMB.0, btn_val(btn_thumb)),
            InputEvent::new(EventType::KEY.0, KeyCode::BTN_TOP.0, btn_val(btn_top)),
            
            // --- 3. ENVIAMOS LOS NUEVOS EVENTOS ---
            InputEvent::new(EventType::KEY.0, KeyCode::BTN_TOP2.0, btn_val(btn_side1)),
            InputEvent::new(EventType::KEY.0, KeyCode::BTN_PINKIE.0, btn_val(btn_side2)),
            
            InputEvent::new(EventType::SYNCHRONIZATION.0, SynchronizationCode::SYN_REPORT.0, 0),
        ];

        self.device.emit(&events)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyOSError, _>(e.to_string()))?;

        Ok(())
    }
}

#[pymodule]
fn rust_motor(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RustJoystick>()?;
    Ok(())
}