# AeroController — Head Tracking + Mouse a Joystick Virtual

Convierte el movimiento de tu mouse y el tracking facial (MediaPipe) en un
joystick virtual (vía `uinput`) para simuladores de vuelo. El procesamiento
de alto rendimiento corre en Rust (`rust_motor`, compilado con maturin).

## 1. Requerimientos

- Linux (usa `evdev`/`uinput`, no funciona en Windows/Mac).
- Python >= 3.11.
- [`uv`](https://docs.astral.sh/uv/) para gestión de entorno y dependencias.
- Rust + Cargo (para compilar `rust_motor` vía `maturin`).
- Una cámara compatible con V4L2 (webcam, DroidCam, etc.) para el head tracking.
- Tu usuario debe poder leer `/dev/input/event*` y escribir en `/dev/uinput`
  sin `sudo`. Esto requiere pertenecer a los grupos correspondientes
  (típicamente `input`, y `uinput` según tu distro/reglas udev). Si tu
  sistema no tiene esto configurado, hay que agregar reglas udev o usar
  `sudo` como último recurso (no recomendado, puede dar problemas con
  GUIs en sesiones Wayland).

## 2. Instalación

```bash
git clone <este-repo>
cd controller_input-main

# Instala dependencias Python y crea el entorno virtual
uv sync

# Compila el motor en Rust
source .venv/bin/activate
cd src/backend/motor_rust/
maturin develop
cd ../../..
```

### Configuración de permisos (una sola vez, a nivel de sistema)

```bash
# Reemplazá "input" por el grupo que use tu distro si es distinto
sudo usermod -aG input $USER
```

Luego **cerrá sesión y volvé a entrar** (no alcanza con abrir una terminal
nueva) para que el cambio de grupo tome efecto.

Verificá que quedó bien:
```bash
id  # debe listar "input" (o el grupo correspondiente) entre tus grupos
```

Si además necesitás permisos sobre `/dev/uinput` (para el joystick virtual
durante el vuelo), puede requerir una regla udev adicional según tu distro.
Consultá la documentación de tu distribución para `uinput` + grupos.

## 3. Ejecución

```bash
uv run python src/main.py
```

Esto abre primero la GUI de configuración. Ajustá los sliders de
sensibilidad y hacé clic en **"INICIAR VUELO"** para pasar al motor. El
proceso supervisor (`main.py`) alterna automáticamente entre GUI y motor:
saliendo del motor (ALT+P) volvés a la GUI, cerrando la GUI (X) termina
todo.

### Selección de dispositivos (mouse/teclado)

La detección de hardware es automática por heurística, pero puede
confundirse con dispositivos gaming que exponen interfaces secundarias
(macros, DPI, RGB). Si el mouse o el teclado detectados no son los
correctos, andá a la pestaña **"💾 Sistema"** en la GUI y seleccionalos
manualmente del listado — queda guardado en tu perfil de configuración.

### Atajos durante el vuelo

- `ALT + P`: pausar y volver a la configuración.
- `ALT/WIN + ,` (o la tecla `<` en teclados ISO/Español): recentrar stick y cabeza.

### Debug visual

Con la GUI abierta (o el motor en modo debug), se muestra una ventana de
OpenCV con la malla de puntos faciales (MediaPipe) en tiempo real, útil
para verificar que el tracking está funcionando antes de volar.

## Notas

- El registro (`run.log`) se puede generar con:
  ```bash
  uv run python src/main.py 2>&1 | tee run.log
  ```
  útil para depurar sin perder el historial si la terminal se cierra.
- `src/backend/vr_bridge.py` es un módulo borrador (no integrado aún) para
  una futura conexión con `opentrack`/FreeTrack, pensado para usar el head
  tracking nativo de simuladores como War Thunder sin pasar por VR/SteamVR.
