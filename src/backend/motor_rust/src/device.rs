use evdev::{
    uinput::VirtualDevice, AbsInfo, AbsoluteAxisCode, AttributeSet, BusType, InputId, KeyCode,
    UinputAbsSetup,
};
use std::io;

/// Los 16 botones del T.16000M, en el orden en que los numera el mando.
///
/// El driver hid-input del kernel asigna los botones de un joystick HID de
/// forma consecutiva a partir de BTN_JOYSTICK (0x120), así que el mando
/// real reporta 0x120..=0x12F. 0x12C–0x12E no tienen nombre en evdev
/// (en el JSON del perfil van como "0x12c" etc.) y 0x12F es BTN_DEAD.
///
/// Esta tabla es la fuente de verdad: Python la consulta con
/// `rust_motor.virtual_button_codes()` para avisar si el perfil JSON
/// menciona un código que el dispositivo virtual no registra (el kernel
/// descarta en silencio los eventos de códigos no declarados).
pub const BUTTON_CODES: [u16; 16] = [
    0x120, // 1  BTN_TRIGGER
    0x121, // 2  BTN_THUMB
    0x122, // 3  BTN_THUMB2
    0x123, // 4  BTN_TOP
    0x124, // 5  BTN_TOP2
    0x125, // 6  BTN_PINKIE
    0x126, // 7  BTN_BASE
    0x127, // 8  BTN_BASE2
    0x128, // 9  BTN_BASE3
    0x129, // 10 BTN_BASE4
    0x12A, // 11 BTN_BASE5
    0x12B, // 12 BTN_BASE6
    0x12C, // 13 (sin nombre)
    0x12D, // 14 (sin nombre)
    0x12E, // 15 (sin nombre)
    0x12F, // 16 BTN_DEAD
];

fn err<E: std::fmt::Display>(e: E) -> io::Error {
    io::Error::new(io::ErrorKind::Other, e.to_string())
}

/// Nombre y código evdev de cada eje, en el orden en que los numera el
/// kernel (por código ascendente). El índice de la lista es el número de
/// eje que el juego va a mostrar, así que la GUI puede imprimir esta
/// tabla para guiar el reasignado de controles.
pub const STICK_AXES: [(&str, u16); 6] = [
    ("Alabeo (Stick X)", AbsoluteAxisCode::ABS_X.0),
    ("Cabeceo (Stick Y)", AbsoluteAxisCode::ABS_Y.0),
    ("Timón (Twist)", AbsoluteAxisCode::ABS_RZ.0),
    ("Gases (Slider)", AbsoluteAxisCode::ABS_THROTTLE.0),
    ("POV X", AbsoluteAxisCode::ABS_HAT0X.0),
    ("POV Y", AbsoluteAxisCode::ABS_HAT0Y.0),
];

/// Ejes del dispositivo de cabeza, en orden de código (= orden que ve el
/// juego). Son los 6 códigos canónicos de un head-tracker.
pub const HEAD_AXES: [(&str, u16); 6] = [
    ("Traslación lateral", AbsoluteAxisCode::ABS_X.0),
    ("Traslación vertical", AbsoluteAxisCode::ABS_Y.0),
    ("Traslación en profundidad", AbsoluteAxisCode::ABS_Z.0),
    ("Yaw", AbsoluteAxisCode::ABS_RX.0),
    ("Pitch", AbsoluteAxisCode::ABS_RY.0),
    ("Roll", AbsoluteAxisCode::ABS_RZ.0),
];

/// Rango de un eje analógico: -32767..32767 con centro en 0.
fn setup_axis(code: AbsoluteAxisCode) -> UinputAbsSetup {
    UinputAbsSetup::new(code, AbsInfo::new(0, -32767, 32767, 0, 0, 0))
}

/// Construye el joystick virtual con la forma del Thrustmaster T.16000M
/// FCS real: 4 ejes (X, Y, Twist, Slider) + hat POV + 16 botones.
///
/// Los ejes de cabeza NO van aquí: viven en su propio dispositivo
/// (`create_head_device`). Así el stick tiene la misma forma que el mando
/// físico y la cabeza publica los 6 códigos canónicos, y el reasignado en
/// el juego se hace una sola vez.
pub fn create_stick_device() -> io::Result<VirtualDevice> {
    // El hat POV es discreto: -1, 0, 1 por eje (8 direcciones combinando X/Y).
    let setup_hat = |code| UinputAbsSetup::new(code, AbsInfo::new(0, -1, 1, 0, 0, 0));

    let mut keys = AttributeSet::<KeyCode>::new();
    for code in BUTTON_CODES {
        keys.insert(KeyCode(code));
    }

    let mut builder = VirtualDevice::builder().map_err(err)?;
    builder = builder.name("Thrustmaster T.16000M (Rust Thread)");
    builder = builder.input_id(InputId::new(BusType::BUS_USB, 0x044f, 0xb10a, 0));
    builder = builder.with_keys(&keys).map_err(err)?;

    // --- EJES REALES DEL T.16000M ---
    for code in [
        AbsoluteAxisCode::ABS_X,        // Roll / Stick X
        AbsoluteAxisCode::ABS_Y,        // Pitch / Stick Y
        AbsoluteAxisCode::ABS_RZ,       // Twist (Rudder)
        AbsoluteAxisCode::ABS_THROTTLE, // Slider (Throttle)
    ] {
        builder = builder.with_absolute_axis(&setup_axis(code)).map_err(err)?;
    }

    // --- HAT POV (8 direcciones) ---
    for code in [AbsoluteAxisCode::ABS_HAT0X, AbsoluteAxisCode::ABS_HAT0Y] {
        builder = builder.with_absolute_axis(&setup_hat(code)).map_err(err)?;
    }

    builder.build().map_err(err)
}

/// Botón que declara el dispositivo de cabeza. Nunca se pulsa: existe solo
/// para que el sistema lo clasifique como joystick.
///
/// Sin ninguna tecla, un dispositivo con ABS_X + ABS_Y + ABS_Z es para
/// udev un ACELERÓMETRO: `udev-builtin-input_id` de systemd evalúa esa
/// regla ANTES que la de joystick y corta ahí (`!has_keys &&
/// has_3d_coordinates` -> ID_INPUT_ACCELEROMETER). SDL tiene la misma
/// heurística. Resultado: el juego no ve el dispositivo. Con EV_KEY
/// presente esa regla no aplica, y BTN_TRIGGER (el primero del rango de
/// joystick) lo deja como ID_INPUT_JOYSTICK.
///
/// Declarar un botón no cambia la numeración de los ejes en el juego.
pub const HEAD_BUTTON_CODES: [u16; 1] = [
    0x120, // BTN_TRIGGER
];

/// Dispositivo virtual de head-tracking: 6 ejes y un botón que nunca se pulsa.
///
/// Rotación en ABS_RX / ABS_RY / ABS_RZ y traslación en ABS_X / ABS_Y /
/// ABS_Z: los códigos canónicos de un head-tracker. El botón es lo que hace
/// que el sistema lo reconozca como joystick (ver HEAD_BUTTON_CODES).
///
/// El `input_id` es distinto del stick a propósito: si coincidieran, el
/// juego podría tratarlos como el mismo mando y mezclar las asignaciones.
pub fn create_head_device() -> io::Result<VirtualDevice> {
    let mut keys = AttributeSet::<KeyCode>::new();
    for code in HEAD_BUTTON_CODES {
        keys.insert(KeyCode(code));
    }

    let mut builder = VirtualDevice::builder().map_err(err)?;
    builder = builder.name("Virtual Head Tracker (Rust Thread)");
    // Bus virtual + vendor/product propios: nada que ver con el T.16000M.
    builder = builder.input_id(InputId::new(BusType::BUS_VIRTUAL, 0x1d50, 0x6d0f, 1));
    builder = builder.with_keys(&keys).map_err(err)?;

    for code in [
        AbsoluteAxisCode::ABS_X,  // Traslación lateral
        AbsoluteAxisCode::ABS_Y,  // Traslación vertical
        AbsoluteAxisCode::ABS_Z,  // Traslación en profundidad
        AbsoluteAxisCode::ABS_RX, // Yaw
        AbsoluteAxisCode::ABS_RY, // Pitch
        AbsoluteAxisCode::ABS_RZ, // Roll
    ] {
        builder = builder.with_absolute_axis(&setup_axis(code)).map_err(err)?;
    }

    builder.build().map_err(err)
}
