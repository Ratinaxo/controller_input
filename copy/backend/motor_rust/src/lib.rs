use pyo3::prelude::*;

mod state;
mod device;
mod physics;
mod filter;
mod engine;

use physics::RustPhysics;
use filter::RustFilter;
use engine::RustEngine;

#[pymodule]
fn rust_motor(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RustEngine>()?;
    m.add_class::<RustFilter>()?;
    m.add_class::<RustPhysics>()?;
    Ok(())
}