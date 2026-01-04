use evdev::{
    uinput::VirtualDevice, AbsInfo, AbsoluteAxisCode, AttributeSet, BusType, InputId, KeyCode,
    UinputAbsSetup,
};
use std::io;

pub fn create_virtual_joystick() -> io::Result<VirtualDevice> {
    // Definimos ejes
    let setup_axis = |code| UinputAbsSetup::new(code, AbsInfo::new(0, -32767, 32767, 0, 0, 0));

    // Definimos botones
    let mut keys = AttributeSet::<KeyCode>::new();
    keys.insert(KeyCode::BTN_TRIGGER);
    keys.insert(KeyCode::BTN_THUMB);
    keys.insert(KeyCode::BTN_TOP);
    keys.insert(KeyCode::BTN_TOP2);
    keys.insert(KeyCode::BTN_PINKIE);

    // --- ARREGLO DEL ERROR DE COMPILACIÓN ---
    // En lugar de una cadena gigante, lo hacemos paso a paso.
    
    // 1. Crear el builder inicial
    let mut builder = VirtualDevice::builder()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;

    // 2. Configurar propiedades básicas (name devuelve Self, no Result)
    builder = builder.name("Thrustmaster T.16000M (Rust Thread)");
    builder = builder.input_id(InputId::new(BusType::BUS_USB, 0x044f, 0xb10a, 0));

    // 3. Configurar Keys (devuelve Result)
    builder = builder.with_keys(&keys)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;

    // 4. Configurar Ejes (devuelven Result)
    // Debemos asignar 'builder' en cada paso porque with_absolute_axis consume self.
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_X))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_Y))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_Z))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RZ))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RX))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;
    builder = builder.with_absolute_axis(&setup_axis(AbsoluteAxisCode::ABS_RY))
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;

    // 5. Construir final
    builder.build()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))
}