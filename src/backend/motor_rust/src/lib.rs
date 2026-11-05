use pyo3::prelude::*;

mod device;
mod engine;
mod filter;
mod physics;
mod state;

use engine::RustEngine;
use filter::RustFilter;
use physics::RustPhysics;

/// Códigos evdev de los 16 botones que registra el joystick virtual, en
/// orden (botón 1 primero). Python lo usa para validar el perfil JSON.
#[pyfunction]
fn virtual_button_codes() -> Vec<u16> {
    device::BUTTON_CODES.to_vec()
}

/// Orden de los ejes de cada dispositivo virtual, como (nombre, código
/// evdev). El índice en la lista es el número de eje que va a mostrar el
/// juego, así que la GUI lo puede imprimir para guiar el reasignado.
#[pyfunction]
fn stick_axis_order() -> Vec<(String, u16)> {
    device::STICK_AXES.iter().map(|(n, c)| (n.to_string(), *c)).collect()
}

#[pyfunction]
fn head_axis_order() -> Vec<(String, u16)> {
    device::HEAD_AXES.iter().map(|(n, c)| (n.to_string(), *c)).collect()
}

#[pymodule]
fn rust_motor(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RustEngine>()?;
    m.add_class::<RustFilter>()?;
    m.add_class::<RustPhysics>()?;
    m.add_function(wrap_pyfunction!(virtual_button_codes, m)?)?;
    m.add_function(wrap_pyfunction!(stick_axis_order, m)?)?;
    m.add_function(wrap_pyfunction!(head_axis_order, m)?)?;
    Ok(())
}
