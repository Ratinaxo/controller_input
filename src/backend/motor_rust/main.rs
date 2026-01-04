use evdev::{Device, InputEventKind, RelativeAxisCode};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::{thread, time};

pub struct RustJoystickBackend {
    virtual_x: i32,
    virtual_y: i32,
    throttle: f32,
    rudder: f32,
    running: Arc<AtomicBool>,
}

impl RustJoystickBackend {
    pub fn new() -> Self {
        Self {
            virtual_x: 0,
            virtual_y: 0,
            throttle: 0.0,
            rudder: 0.0,
            running: Arc::new(AtomicBool::new(true)),
        }
    }

    // Configuración de los ejes virtuales para el Kernel
    fn setup_uinput_device() -> uinput::Device {
        uinput::default().unwrap()
            .name("Thrustmaster T.16000M (Virtual Rust)").unwrap()
            .event(uinput::event::Keyboard::All).unwrap()
            .event(uinput::event::controller::Joystick::All).unwrap()
            .event(uinput::event::Absolute::X).unwrap()
            .event(uinput::event::Absolute::Y).unwrap()
            .event(uinput::event::Absolute::Rz).unwrap()
            .create().unwrap()
    }

    pub fn main_loop(&mut self) {
        let mut mouse = self.find_mouse_device().expect("No mouse found");
        let mut uinput_dev = Self::setup_uinput_device();
        
        // Grab del ratón para control exclusivo
        mouse.grab().unwrap();

        while self.running.load(Ordering::SeqCst) {
            // Leer eventos del ratón (no bloqueante o con timeout)
            for event in mouse.fetch_events().unwrap() {
                match event.kind() {
                    InputEventKind::RelAxis(RelativeAxisCode::REL_X) => {
                        self.virtual_x += event.value();
                    }
                    InputEventKind::RelAxis(RelativeAxisCode::REL_Y) => {
                        self.virtual_y += event.value();
                    }
                    _ => {}
                }
            }

            // Aplicar física y enviar al dispositivo uinput
            // final_x = calculate_physics(self.virtual_x, ...)
            uinput_dev.write(0x03, 0x00, self.virtual_x).unwrap(); // ABS_X
            uinput_dev.synchronize().unwrap();

            thread::sleep(time::Duration::from_millis(5));
        }
        mouse.ungrab().unwrap();
    }
}