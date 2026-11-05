use pyo3::exceptions::{PyIOError, PyRuntimeError};
use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock, RwLockReadGuard, RwLockWriteGuard};
use std::thread;
use std::time::Duration;

use evdev::{
    uinput::VirtualDevice, AbsoluteAxisCode, Device, EventType, InputEvent, RelativeAxisCode,
    SynchronizationCode,
};

use crate::device::{create_head_device, create_stick_device};
use crate::physics::{self, StickParams};
use crate::state::SharedState;

/// Lock de escritura que no hace panic si otro hilo envenenó el lock.
fn wlock<T>(l: &RwLock<T>) -> RwLockWriteGuard<'_, T> {
    l.write().unwrap_or_else(|e| e.into_inner())
}

/// Lock de lectura que no hace panic si otro hilo envenenó el lock.
fn rlock<T>(l: &RwLock<T>) -> RwLockReadGuard<'_, T> {
    l.read().unwrap_or_else(|e| e.into_inner())
}

/// Pone `running = false` al salir del hilo, INCLUSO si el hilo hace
/// panic. Así `is_running()` nunca queda en true con el hilo muerto.
struct RunningGuard(Arc<AtomicBool>);

impl Drop for RunningGuard {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

/// Descarta todo lo que el kernel tenga encolado en el dispositivo.
/// Se usa al salir de la pausa: mientras el mouse está liberado, el
/// descriptor sigue recibiendo eventos, y si no se vacían se aplicarían
/// de golpe al reanudar (el stick "salta").
fn drain(dev: &mut Device) {
    for _ in 0..256 {
        match dev.fetch_events() {
            Ok(events) => {
                if events.count() == 0 {
                    break;
                }
            }
            Err(_) => break, // WouldBlock = cola vacía
        }
    }
}

/// Códigos de los ejes del dispositivo de cabeza, en el mismo orden en que
/// el hilo arma el array `head`: [tx, ty, tz, yaw, pitch, roll].
const HEAD_AXIS_CODES: [u16; 6] = [
    AbsoluteAxisCode::ABS_X.0,
    AbsoluteAxisCode::ABS_Y.0,
    AbsoluteAxisCode::ABS_Z.0,
    AbsoluteAxisCode::ABS_RX.0,
    AbsoluteAxisCode::ABS_RY.0,
    AbsoluteAxisCode::ABS_RZ.0,
];

fn raw(v: f32) -> i32 {
    (v.clamp(-1.0, 1.0) * 32767.0) as i32
}

/// Emite todos los botones virtuales en 0 y marca el estado local.
fn release_all(joy: &mut VirtualDevice, pressed: &mut HashMap<u16, bool>) {
    let mut evs: Vec<InputEvent> = Vec::with_capacity(pressed.len() + 1);
    for (code, state) in pressed.iter_mut() {
        *state = false;
        evs.push(InputEvent::new(EventType::KEY.0, *code, 0));
    }
    evs.push(InputEvent::new(EventType::SYNCHRONIZATION.0, SynchronizationCode::SYN_REPORT.0, 0));
    let _ = joy.emit(&evs);
}

/// Procesa un evento de tecla/botón físico contra el mapa físico -> virtual.
fn apply_key(ev: &InputEvent, map: &HashMap<u16, u16>, pressed: &mut HashMap<u16, bool>) {
    if ev.event_type() == EventType::KEY && ev.value() != 2 {
        // value 2 = autorepeat, se ignora
        if let Some(virtual_code) = map.get(&ev.code()) {
            pressed.insert(*virtual_code, ev.value() == 1);
        }
    }
}

#[pyclass]
pub struct RustEngine {
    state: Arc<RwLock<SharedState>>,
    // Mapa físico -> virtual: código evdev de tecla o botón de mouse real
    // (ej. KEY_1, BTN_LEFT) -> código del botón del joystick virtual.
    // Python lo arma a partir de config.json + el perfil JSON del mando.
    button_map: Arc<RwLock<HashMap<u16, u16>>>,
    // Snapshot de qué botones virtuales están presionados AHORA MISMO.
    button_state: Arc<RwLock<HashMap<u16, bool>>>,
    running: Arc<AtomicBool>,
    thread_handle: Option<thread::JoinHandle<()>>,
}

#[pymethods]
impl RustEngine {
    #[new]
    fn new() -> Self {
        RustEngine {
            state: Arc::new(RwLock::new(SharedState::new())),
            button_map: Arc::new(RwLock::new(HashMap::new())),
            button_state: Arc::new(RwLock::new(HashMap::new())),
            running: Arc::new(AtomicBool::new(false)),
            thread_handle: None,
        }
    }

    /// Reemplaza el mapa de botones. Debe llamarse ANTES de start(): el
    /// hilo toma un snapshot del mapa al arrancar para no pagar un lock en
    /// cada ciclo.
    fn set_button_map(&mut self, map: HashMap<u16, u16>) {
        *wlock(&self.button_map) = map;
    }

    /// Snapshot de qué botones virtuales están presionados en este instante.
    fn get_button_state(&self) -> HashMap<u16, bool> {
        rlock(&self.button_state).clone()
    }

    /// Abre los dispositivos, crea el joystick virtual y lanza el hilo.
    ///
    /// Todo lo que puede fallar (abrir mouse/teclado, crear uinput, grab
    /// exclusivo del mouse) se hace ANTES de lanzar el hilo, y el error se
    /// devuelve a Python como IOError con un mensaje claro.
    ///
    /// `screen_w` / `screen_h` se aceptan por compatibilidad pero ya no se
    /// usan: el recorrido del stick depende solo de radio + outer.
    ///
    /// `with_head` decide si se crea el segundo dispositivo virtual (el de
    /// head-tracking). Con la fuente de cabeza en modo externo hay que
    /// pasarlo en false: OpenTrack publica su propio joystick y dos
    /// dispositivos de cabeza a la vez solo confundirían al juego.
    #[pyo3(signature = (mouse_path, kb_path, screen_w=None, screen_h=None, with_head=true))]
    fn start(
        &mut self,
        mouse_path: String,
        kb_path: String,
        screen_w: Option<f32>,
        screen_h: Option<f32>,
        with_head: bool,
    ) -> PyResult<()> {
        let _ = (screen_w, screen_h);

        if self.running.load(Ordering::SeqCst) {
            return Err(PyRuntimeError::new_err("El motor ya está en marcha"));
        }
        if let Some(h) = self.thread_handle.take() {
            let _ = h.join();
        }

        let mut mouse_dev = Device::open(&mouse_path)
            .map_err(|e| PyIOError::new_err(format!("No se pudo abrir el mouse {mouse_path}: {e}")))?;

        // Si no hay teclado propio (fallback teclado = mouse), no se abre
        // dos veces: los botones del mouse ya pasan por el mapa.
        let mut kb_dev = if kb_path == mouse_path {
            None
        } else {
            Some(Device::open(&kb_path).map_err(|e| {
                PyIOError::new_err(format!("No se pudo abrir el teclado {kb_path}: {e}"))
            })?)
        };

        let mut joy_out = create_stick_device().map_err(|e| {
            PyIOError::new_err(format!(
                "No se pudo crear el joystick virtual (/dev/uinput): {e}. \
                 ¿Tu usuario tiene permiso de escritura sobre /dev/uinput?"
            ))
        })?;

        // Mismo trato que el stick: si falla, se sabe ANTES de lanzar el
        // hilo y el mensaje llega a Python como IOError.
        let mut head_out = if with_head {
            Some(create_head_device().map_err(|e| {
                PyIOError::new_err(format!(
                    "No se pudo crear el dispositivo de cabeza (/dev/uinput): {e}. \
                     ¿Tu usuario tiene permiso de escritura sobre /dev/uinput?"
                ))
            })?)
        } else {
            None
        };

        mouse_dev.set_nonblocking(true)
            .map_err(|e| PyIOError::new_err(format!("Mouse en modo no bloqueante: {e}")))?;
        if let Some(kb) = kb_dev.as_mut() {
            kb.set_nonblocking(true)
                .map_err(|e| PyIOError::new_err(format!("Teclado en modo no bloqueante: {e}")))?;
        }

        // Captura exclusiva SOLO del mouse. El teclado no se agarra: Python
        // sigue leyendo sus atajos y el sistema operativo sigue viendo las teclas.
        mouse_dev.grab().map_err(|e| {
            PyIOError::new_err(format!(
                "No se pudo capturar el mouse en exclusiva: {e}. \
                 ¿Otro programa lo tiene agarrado?"
            ))
        })?;
        drain(&mut mouse_dev);

        // Estado limpio para esta sesión.
        {
            let mut s = wlock(&self.state);
            s.exit_req = false;
            s.recenter_req = false;
        }

        let local_map: HashMap<u16, u16> = rlock(&self.button_map).clone();
        let state = Arc::clone(&self.state);
        let button_state = Arc::clone(&self.button_state);
        let running = Arc::clone(&self.running);
        running.store(true, Ordering::SeqCst);

        let handle = thread::Builder::new()
            .name("rust_motor".into())
            .spawn(move || {
                let _guard = RunningGuard(Arc::clone(&running));

                // Desplazamiento virtual del stick respecto al centro (px),
                // acotado a ±(radio + outer).
                let mut dx = 0.0f32;
                let mut dy = 0.0f32;
                let mut throttle = 0.0f32;
                let mut rudder = 0.0f32;

                let unique_virtual: HashSet<u16> = local_map.values().cloned().collect();
                let mut pressed: HashMap<u16, bool> =
                    unique_virtual.iter().map(|c| (*c, false)).collect();

                let mut local_paused = false;

                while running.load(Ordering::SeqCst) {
                    // A. PETICIONES DE PYTHON + PARÁMETROS (un solo lock)
                    // head = [tx, ty, tz, yaw, pitch, roll], en el mismo
                    // orden que los ejes del dispositivo de cabeza.
                    let (must_recenter, must_exit, must_pause, params, head): (
                        bool, bool, bool, StickParams, [f32; 6],
                    ) = {
                        let mut s = wlock(&state);
                        let r = s.recenter_req;
                        s.recenter_req = false;
                        (
                            r,
                            s.exit_req,
                            s.is_paused,
                            s.params,
                            [s.head_tx, s.head_ty, s.head_tz, s.head_yaw, s.head_pitch, s.head_roll],
                        )
                    };

                    if must_exit {
                        break;
                    }
                    if must_recenter {
                        dx = 0.0;
                        dy = 0.0;
                        rudder = 0.0;
                    }

                    // B. PAUSA / CLUTCH (solo afecta al mouse)
                    if must_pause != local_paused {
                        if must_pause {
                            // Soltar todos los botones virtuales: si no, el
                            // juego los vería presionados durante la pausa.
                            release_all(&mut joy_out, &mut pressed);
                            let _ = mouse_dev.ungrab();
                        } else {
                            if let Err(e) = mouse_dev.grab() {
                                eprintln!("[RUST] No se pudo recuperar el mouse: {e}");
                            }
                            // Descartar lo que se movió/presionó durante la pausa.
                            drain(&mut mouse_dev);
                            if let Some(kb) = kb_dev.as_mut() {
                                drain(kb);
                            }
                        }
                        local_paused = must_pause;
                    }

                    if local_paused {
                        thread::sleep(Duration::from_millis(20));
                        continue;
                    }

                    let hard = params.hard_limit();

                    // C. MOUSE: ejes relativos + botones
                    if let Ok(events) = mouse_dev.fetch_events() {
                        for ev in events {
                            if ev.event_type() == EventType::RELATIVE {
                                let c = ev.code();
                                let val = ev.value() as f32;
                                if c == RelativeAxisCode::REL_X.0 {
                                    dx = (dx + val).clamp(-hard, hard);
                                } else if c == RelativeAxisCode::REL_Y.0 {
                                    dy = (dy + val).clamp(-hard, hard);
                                } else if c == RelativeAxisCode::REL_WHEEL.0 {
                                    throttle = (throttle + val * 0.05).clamp(-1.0, 1.0);
                                } else if c == RelativeAxisCode::REL_HWHEEL.0 {
                                    rudder = (rudder + val * 0.20).clamp(-1.0, 1.0);
                                }
                            } else {
                                apply_key(&ev, &local_map, &mut pressed);
                            }
                        }
                    }

                    // Si el radio/outer cambió en vivo, re-acotar.
                    dx = dx.clamp(-hard, hard);
                    dy = dy.clamp(-hard, hard);

                    // C.2 TECLADO -> BOTONES DEL JOYSTICK VIRTUAL
                    if let Some(kb) = kb_dev.as_mut() {
                        if let Ok(events) = kb.fetch_events() {
                            for ev in events {
                                apply_key(&ev, &local_map, &mut pressed);
                            }
                        }
                    }

                    // D. FÍSICA (misma función que la vista previa de la GUI)
                    let out = physics::compute(dx, dy, &params);

                    // E. EMITIR
                    let mut evs: Vec<InputEvent> = vec![
                        InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_X.0, raw(out.x)),
                        InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_Y.0, raw(out.y)),
                        InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_THROTTLE.0, raw(throttle)),
                        InputEvent::new(EventType::ABSOLUTE.0, AbsoluteAxisCode::ABS_RZ.0, raw(rudder)),
                    ];
                    for (code, is_down) in pressed.iter() {
                        evs.push(InputEvent::new(EventType::KEY.0, *code, i32::from(*is_down)));
                    }
                    evs.push(InputEvent::new(
                        EventType::SYNCHRONIZATION.0,
                        SynchronizationCode::SYN_REPORT.0,
                        0,
                    ));
                    let _ = joy_out.emit(&evs);

                    // Dispositivo de cabeza: paquete propio con su propio
                    // SYN_REPORT, para que el juego lo vea como un mando
                    // aparte y no mezcle los ejes con los del stick.
                    if let Some(head_dev) = head_out.as_mut() {
                        let mut head_evs: Vec<InputEvent> = Vec::with_capacity(HEAD_AXIS_CODES.len() + 1);
                        for (code, value) in HEAD_AXIS_CODES.iter().zip(head.iter()) {
                            head_evs.push(InputEvent::new(EventType::ABSOLUTE.0, *code, raw(*value)));
                        }
                        head_evs.push(InputEvent::new(
                            EventType::SYNCHRONIZATION.0,
                            SynchronizationCode::SYN_REPORT.0,
                            0,
                        ));
                        let _ = head_dev.emit(&head_evs);
                    }

                    if let Ok(mut s) = state.try_write() {
                        s.last_x = out.x;
                        s.last_y = out.y;
                        s.last_throttle = throttle;
                        s.last_rudder = rudder;
                        s.in_deadzone = out.in_deadzone;
                        s.is_snapped = out.is_snapped;
                    }
                    if let Ok(mut bs) = button_state.try_write() {
                        *bs = pressed.clone();
                    }

                    thread::sleep(Duration::from_micros(900));
                }

                release_all(&mut joy_out, &mut pressed);
                let _ = mouse_dev.ungrab();
            })
            .map_err(|e| {
                self.running.store(false, Ordering::SeqCst);
                PyRuntimeError::new_err(format!("No se pudo lanzar el hilo del motor: {e}"))
            })?;

        self.thread_handle = Some(handle);
        Ok(())
    }

    fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        if let Some(handle) = self.thread_handle.take() {
            let _ = handle.join();
        }
    }

    /// Ejes de cabeza ya normalizados a -1.0..1.0.
    ///
    /// Solo yaw y pitch son obligatorios: mientras la Fase B del 6DOF no
    /// esté lista, el tracker entrega dos valores y el resto queda en 0,
    /// que es el centro de cada eje.
    #[pyo3(signature = (yaw, pitch, roll=0.0, tx=0.0, ty=0.0, tz=0.0))]
    fn update_tracker(&mut self, yaw: f32, pitch: f32, roll: f32, tx: f32, ty: f32, tz: f32) {
        let mut s = wlock(&self.state);
        s.head_yaw = yaw;
        s.head_pitch = pitch;
        s.head_roll = roll;
        s.head_tx = tx;
        s.head_ty = ty;
        s.head_tz = tz;
    }

    fn update_config(&mut self, r: f32, c: f32, d: f32, sa: f32, st: f32, o: f32) {
        wlock(&self.state).params = StickParams {
            radius: r, curve: c, deadzone: d, snap_axis: sa, snap_threshold: st, outer: o,
        };
    }

    fn get_hud_data(&self) -> (f32, f32, f32, f32, bool, bool) {
        let s = rlock(&self.state);
        (s.last_x, s.last_y, s.last_throttle, s.last_rudder, s.is_snapped, s.in_deadzone)
    }

    fn recenter(&mut self) {
        wlock(&self.state).recenter_req = true;
    }

    fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    fn request_exit(&mut self) {
        wlock(&self.state).exit_req = true;
    }

    fn set_paused(&mut self, paused: bool) {
        wlock(&self.state).is_paused = paused;
    }
}

impl Drop for RustEngine {
    fn drop(&mut self) {
        self.stop();
    }
}
