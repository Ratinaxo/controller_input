# Revisión profunda del proyecto — qué falta y en qué orden atacarlo

Auditoría de todo el repo (backend Python, motor en Rust, frontend Tkinter,
empaquetado y documentación) hecha para responder "¿qué parece faltar?".
Se hizo con tres revisiones paralelas (backend+Rust, frontend+HUD,
proyecto/empaquetado/docs) y luego se verificó cada hallazgo contra tu
máquina real antes de escribirlo acá -- el entorno de este agente tiene una
copia parcial del repo (le faltaban `main.py`, `gui_app.py`, `motor_app.py`,
`pyproject.toml`, `uv.lock`, `LICENSE`), así que dos alarmas iniciales
("no existe `main.py`", "no hay `pyproject.toml`") eran falsas -- ambos
archivos existen y funcionan bien en tu máquina. Quedan corregidas y no
aparecen abajo como hallazgos.

No se tocó ningún archivo durante esta revisión. Todo lo de acá es
diagnóstico; las fases de abajo son la propuesta de qué hacer con eso.

---

## Resumen ejecutivo

El proyecto **funciona y está mejor probado que la mayoría de los
side-projects de este tamaño** (188 tests, snapshot dorado de la GUI,
tests unitarios del motor de físicas en Rust, migraciones de config con
red de seguridad). Lo que falta no es "terminar de construirlo": es
higiene de repo, una red de CI, manejo de fallas en caliente (cámara o
mouse que se desconectan a mitad de vuelo) y algunas features a medio
camino que quedaron documentadas como pendientes en tus propios planes
(`docs/plan_vista_camara.md`) pero nunca se retomaron.

Nada de lo encontrado es un blocker para volar hoy. La prioridad real es:
1. Cosas de 10 minutos que evitan sustos (`.gitignore`, dependencia
   muerta, `uv.lock` no versionado).
2. Manejo de fallas en caliente (cámara/mouse desconectado a mitad de
   vuelo hoy se congela en silencio -- es lo más "raro" que te puede pasar
   volando).
3. Terminar lo que ya empezaste y quedó a medio camino (Fase 4/5 de la
   vista de cámara, el snap de ejes en Rust, el puente a OpenTrack).
4. Todo lo demás (cobertura de tests, limpieza de código muerto, CI) es
   importante pero no urgente.

---

## Fase 0 — Higiene de repo (∼30 min, riesgo nulo)

- [ ] **`config.json` de la raíz es un fósil.** La app lee y escribe
  `src/config/config1.json` (`src/utils/utils.py:CONFIG_FILE`); el
  `config.json` de la raíz (433 bytes) tiene un esquema viejo -- le
  faltan `t_min_cutoff`, `t_beta`, `head_trans_limits`, `button_map`,
  `head_limit_points`, todo lo que se agregó después. No está en
  `.gitignore`, así que si alguna vez se edita "pensando que es la
  config real" o se sube con un `git add .`, confunde a cualquiera que
  clone el repo. Borrarlo, o si tiene algún propósito que no veo desde
  acá, renombrarlo y agregarlo a `.gitignore`.
- [ ] **`run.log`, `depth_probe.csv`, `depth_probe.png` en la raíz no
  están en `.gitignore`.** El propio README sugiere generar `run.log`
  con `... | tee run.log`, y `tests/depth_probe.py` genera los otros
  dos ahí mismo -- son artefactos de trabajo, no algo para versionar.
  Agregar `run.log`, `depth_probe.csv`, `depth_probe.png` (o `*.log`,
  `depth_probe.*`) a `.gitignore`.
- [ ] **`uv.lock` y `Cargo.lock` están en `.gitignore` (`*.lock` en la
  línea 23, más `Cargo.lock` explícito en la línea 15).** Para una
  *aplicación* (no una librería) esto es al revés de lo recomendable:
  el lockfile es justamente lo que te garantiza que `uv sync`/`cargo
  build` en otra máquina (o en CI, ver Fase 2) instale las mismas
  versiones que probaste vos. Hoy, cada `uv sync` en un clon nuevo
  puede resolver versiones distintas de `evdev`/`mediapipe`/etc. sin
  que nadie se entere hasta que algo se comporta distinto. Sacar
  `*.lock`/`Cargo.lock` del `.gitignore` y commitear ambos lockfiles.
- [ ] **`keyboard` en `pyproject.toml` no se usa en ningún lado.**
  Grep completo a `src/` no encuentra ningún `import keyboard` -- los
  atajos (ALT+P, recentrar) están implementados con `evdev`. Es
  probablemente un resto de una versión anterior. Sacarlo de
  `dependencies` (una librería menos, y una menos que en Linux a veces
  pide permisos raros sin necesidad).
- [ ] **`pyproject.toml` no declara licencia.** Hay un `LICENSE` (GPLv3)
  en la raíz pero el `[project]` no tiene `license = "GPL-3.0-or-later"`
  (o el clasificador correspondiente). Cosmético, pero si alguna vez se
  empaqueta o se sube a algún índice, hoy no lo reflejaría.

**Aceptación:** `git status` en un clon limpio no muestra archivos de
trabajo sueltos; `uv.lock`/`Cargo.lock` versionados; sin dependencias sin
usar.

---

## Fase 1 — Manejo de fallas en caliente (medio día, prioridad real)

Esto es lo más importante de toda la revisión: **hoy, si la cámara se
desconecta o el mouse/teclado desaparece a mitad de vuelo, la app no te
avisa -- se congela en silencio.**

- [ ] **Cámara perdida durante el vuelo (`src/backend/tracker.py:467-473`).**
  Si `cap.read()` falla, el lazo hace `time.sleep(0.1); continue` para
  siempre, sin límite de reintentos, sin marcar ningún estado, y sin
  volver a intentar abrir el dispositivo. Como `_axes`/`_head_axes` solo
  se pisan cuando hay un frame+cara detectados con éxito, el último
  valor calculado queda congelado indefinidamente -- si estabas girando
  la cabeza cuando la cámara murió, el avión se queda girando para
  siempre. Ni un print seguido avisa (los prints de error son solo para
  excepciones, no para "success=False" repetido). Que se marque un
  estado de "tracker caído" (visible en la vista embebida, que ya tiene
  `MSG_WAITING` para esto -- solo falta que dejar de esperar después de
  N intentos y decir "cámara perdida" en vez de esperar para siempre), y
  que decida qué hacer con los ejes: lo más seguro en un contexto de
  vuelo es recentrar a cero, no mantener la última lectura.
- [ ] **Mouse/teclado que se desconecta a mitad de vuelo
  (`motor_rust/src/engine.rs:297,322-323`).** Cualquier error de
  `fetch_events()` que no sea "no hay eventos todavía" se trata igual
  que "no pasó nada este tick" -- un error de permisos, un dispositivo
  removido, todo se ve igual desde adentro del lazo caliente. El stick
  se queda clavado en su última posición, sin ningún aviso.
  `motor.py`/`engine.rs` deberían distinguir "cola vacía" de "el
  dispositivo ya no está" y, en el segundo caso, volver a la GUI con un
  mensaje en vez de quedarse corriendo con datos muertos.
- [ ] **Apertura de cámara fallida: invisible para el usuario.** Si
  `cap.isOpened()` da `False`, `tracker.py` solo hace `print()`. La vista
  embebida entonces muestra "Esperando a la cámara…" **para siempre**, sin
  botón de reintentar ni indicación de que nunca va a resolver. Mismo
  arreglo que el punto anterior: después de un tiempo, cambiar el mensaje
  a algo como "no se pudo abrir la cámara -- revisá la consola" en vez de
  seguir esperando.
- [ ] **`rust_motor` no carga: la GUI se cierra sin explicar nada**
  (`launcher.py:40-45`). Si `RustPhysics(...)` tira excepción, hoy es
  `print` a consola + `sys.exit(1)` **antes de que exista ninguna
  ventana**. Para alguien que abre esto desde un ícono y no mira la
  terminal, la app "simplemente se cierra". Como mínimo, si se puede
  abrir una ventana de error de Tk antes de salir (un `messagebox` sin
  depender del resto de la app), sería mucho más claro que un cierre
  silencioso.
- [ ] **Config corrupta al arrancar: sin manejo en el lanzador.**
  `load_config()` se llama en `launcher.py:34` sin `try/except` --si el
  JSON está roto, la GUI ni siquiera llega a abrir una ventana antes de
  reventar con traceback crudo. Comparar con `tabs/system/profiles.py`,
  que sí muestra un `messagebox.showerror` al cargar un perfil roto --
  ese mismo patrón debería aplicar al arranque.

**Aceptación:** desconectar la cámara o el mouse durante una sesión de
prueba produce un mensaje visible en la GUI (no solo en consola) y el
avión no queda "congelado" en una posición peligrosa.

---

## Fase 2 — CI básica (medio día)

Hoy no hay ningún `.github/` ni config de CI. Con un motor en Rust, una
suite de 188 tests y un snapshot dorado de la GUI, esto es exactamente el
tipo de proyecto donde una regresión se cuela fácil si nadie corre todo a
mano antes de cada cambio (te pasó esta misma sesión: la Fase 6 de colores
llevaba un tiempo aplicada en el código sin que el snapshot se hubiera
regenerado -- CI lo hubiera marcado en rojo el mismo día).

- [ ] Un workflow de GitHub Actions (o el que uses) que en cada push/PR:
  1. `uv sync` + `uv run python -m unittest tests.test_fixes` (no
     necesita hardware real: los stubs de `tests/stubs/` ya cubren
     `evdev` y `rust_motor` para esto).
  2. `cargo test` dentro de `src/backend/motor_rust/` (ya hay tests
     reales en `physics.rs` y `filter.rs` -- correrlos en CI es gratis).
  3. Opcional: `cargo build` (sin `maturin develop`, no hace falta un
     entorno gráfico) para detectar que el crate compila con la versión
     de Rust del runner.
- [ ] Documentar en el README cómo correr los tests localmente (ver
  Fase 6 más abajo) -- hoy no hay ninguna sección de "cómo testear esto".

**Aceptación:** un PR con un test roto o un `cargo build` roto se marca
en rojo antes de mergear, no después de que alguien lo note volando.

---

## Fase 3 — Terminar lo que ya quedó documentado como pendiente

Estas no son cosas nuevas que yo esté proponiendo -- son puntos que tus
propios planes (`docs/plan_vista_camara.md`) ya dejaron anotados y nunca
se retomaron. Los repito acá con una estimación de cuánto trabajo son de
verdad, mirando el código actual.

- [ ] **Fase 4 de `plan_vista_camara.md`: vista de cámara dentro de los
  asistentes de calibración + rechazar una lectura si el encuadre está
  mal.** Es la que más vale de las pendientes: hoy podés calibrar con
  media cara fuera de cuadro y el asistente lo acepta igual. Es trabajo
  medio, no trivial: el overlay ya calcula el estado ok/warn/out
  (`camera_view/overlay.py`), pero nada lo expone como propiedad
  consultable del tracker, y el asistente (`components/calibration_wizard.py`)
  no tiene ningún gancho para embeber un widget ni para rechazar una
  captura por otro motivo que no sea el ángulo. Hay que: exponer el
  estado del encuadre en el tracker, embeber una segunda `CameraView`
  en la ventana del asistente (agrandar `WIZARD_GEOMETRY`), y agregar un
  motivo de rechazo nuevo en `finish_capture`.
- [ ] **Fase 5 de `plan_vista_camara.md`: la tecla `q` mata el tracker
  entero en vez de solo cerrar la ventana de depuración de OpenCV**
  (`tracker.py:513-516`, `self.running = False` en vez de cerrar solo la
  ventana). Hoy es inofensivo porque `show_debug` está en `False` siempre
  en la GUI real -- pero el día que alguien reactive esa ventana para
  depurar, el bug vuelve a aparecer y no hay ningún test que lo cubra.
  Arreglo de 10 minutos: una bandera local en vez de tocar `self.running`.
- [ ] **El puente a OpenTrack/FreeTrack (`vr_bridge.py`) directamente no
  existe** -- el README lo describe como "borrador, no integrado", pero
  no hay ningún archivo, ni borrador ni terminado. Esto es justo lo que
  faltaría para que la fuente "externa" (OpenTrack) pudiera un día hablar
  el protocolo TrackIR/FreeTrack hacia el juego en vez de depender de que
  el juego soporte ejes de joystick crudos (la pregunta que hiciste sobre
  cómo configurar la profundidad in-game). Si te interesa retomarlo, lo
  que falta es concreto: un receptor UDP del formato de salida de
  OpenTrack (6 doubles por paquete), un modo `"udp"` nuevo en
  `create_head_source()`, y wiring en la pestaña Fuente. Si no te
  interesa, vale la pena borrar la mención en el README o marcarla
  explícitamente como "no se va a hacer" para que no quede como promesa
  eterna.
- [ ] **El "snap" de ejes está a medio camino en Rust y es config muerta
  hoy.** `StickParams.snap_axis`/`snap_threshold` viajan desde
  `config.json` hasta `physics.rs` (`motor.py` → `engine.rs` →
  `StickParams`), pero `physics::compute()` nunca los lee --
  `StickOutput.is_snapped` está hardcodeado en `false` en los dos
  `return` de la función. El HUD y la telemetría tienen una columna
  `is_snapped` que nunca va a ser `true`. O se termina de implementar
  (parece pensado para "pegar" el stick a un eje puro cerca de nivel,
  típico en HOTAS), o se saca el config/plumbing muerto para no confundir
  a quien lo lea después.

**Aceptación:** cada punto de `plan_vista_camara.md` queda marcado ✅ con
su test, o explícitamente descartado con una nota de por qué.

---

## Fase 4 — Cobertura de tests que falta

No es que el proyecto esté mal probado (188 tests, muy por encima del
promedio) -- pero hay zonas concretas sin ningún test:

- [ ] **El lazo principal de `motor.py` no se ejercita nunca.**
  `tests/stubs/rust_motor.py` define `class RustEngine: pass` -- un stub
  vacío. Nada prueba `JoystickBackend.run()`: apertura de dispositivos,
  el hilo de teclado, pausa/reanudación, recentrar/salir por atajo. Hoy
  la única forma de probar esa lógica es volar de verdad.
- [ ] **`engine.rs` y `device.rs` (Rust) no tienen ni un `#[cfg(test)]`.**
  `physics.rs` y `filter.rs` sí tienen tests sólidos (continuidad,
  monotonía, simetría) -- vale la pena el mismo nivel para el manejo de
  hilos (`start`/`stop`/`drain`/recentrar) y el mapeo de botones.
- [ ] **HUD (`frontend/hud/*`) sin ningún test.** Corre en otro proceso,
  tiene matemática de geometría de pantalla nada trivial
  (`x_pos = screen_w - size - margin`), y no hay ni un `TestHud*` en toda
  la suite. Lo más barato: los `@staticmethod` de color por umbral
  (`stick_color`/`throttle_color`) son puro cálculo, se prueban en dos
  minutos.
- [ ] Zonas más chicas sin test dedicado: `SystemTab` (dispositivos,
  guardar/cargar perfil), `StickTab`/`CurveGraph`, `AxisOrderSection`
  (el texto que arma con `rust_motor.stick_axis_order`/`head_axis_order`,
  incluyendo el camino "no disponible: recompilá el módulo Rust"),
  `InputReader` (qué pasa si no hay mouse/teclado).

**Aceptación:** ninguno de estos módulos aparece como "cubierto solo por
inspección manual" en una futura revisión.

---

## Fase 5 — Limpieza de código muerto

- [ ] **Cuatro archivos ya marcados para borrar, con el comentario
  puesto y todo:** `src/frontend/theme.py`, `widgets.py`, `tooltips.py`,
  `hud.py` (el archivo plano, no la carpeta `frontend/hud/`). Cada uno
  dice literalmente "se puede borrar" / "BORRA ESTE ARCHIVO" en su propio
  docstring desde hace rato. Nadie los borró todavía.
- [ ] **`device_mouse_path`/`device_kb_path` en `motor.py:166-171`** son
  un mecanismo de selección manual más viejo que `mouse_phys`/
  `keyboard_phys`, no están en `DEFAULT_CONFIG` ni en la lista de
  migración (`LEGACY_KEYS` de `utils/config.py`), así que si algún
  config viejo los tiene, se quedan ahí para siempre sin que nada los
  limpie ni los documente.
- [ ] **`AppContext.on`/`.emit()`** quedaron sin ningún uso después de
  sacar el evento `CONTROLLER_CHANGED` la sesión pasada -- infraestructura
  genérica sin nada que la use hoy. Usarla para algo o sacarla.
- [ ] **`docs/plan_refactor_gui.md` quedó desincronizado**: su "Fase 6"
  tiene los mismos checkboxes sin marcar que `plan_vista_camara.md` ya
  completó y marcó ✅. Vale la pena cerrar ese doc con una nota de "esto
  se completó en plan_vista_camara.md" para que nadie lo lea y piense
  que sigue pendiente.

**Aceptación:** `grep -rn "se puede borrar\|BORRA ESTE"` no encuentra nada.

---

## Fase 6 — Documentación

- [ ] **README sin sección de tests.** Nada le dice a alguien nuevo cómo
  correr la suite, ni que existen stubs para no necesitar hardware real.
- [ ] **El modelo de MediaPipe (`src/models/face_landmarker.task`, 3.6 MB)
  está commiteado pero el README no lo menciona.** Funciona de una, pero
  nadie que clone el repo entiende por qué hay un binario de ese tamaño
  ahí ni qué pasa si falta/se corrompe.
- [ ] **No hay una descripción del flujo de datos en ningún lado**
  (cámara → tracker → config → motor Rust → uinput → juego). Hoy hay que
  reconstruirlo leyendo `motor_app.py`, `motor.py` y `tracker.py` a mano.
  Un diagrama chico o un párrafo en el README ahorraría eso.
- [ ] Los tres `docs/plan_*.md` son bitácoras de refactor, no
  documentación para quien llega nuevo -- están bien como historial, pero
  no reemplazan un README con la arquitectura.

---

## Fase 7 — Pulido menor (opcional, sin apuro)

- [ ] Build de Rust en modo debug por defecto (`maturin develop`, sin
  `--release`) -- el README nunca menciona `--release` para lo que se
  describe como el motor "de alto rendimiento". Si en vuelo real notás
  algo de latencia, esto es lo primero para probar.
- [ ] HUD posicionado con `xrandr --current`, que en un setup
  multi-monitor da el tamaño de pantalla *combinado*, no el del monitor
  donde corre el juego -- el HUD podría terminar en la esquina del
  monitor equivocado. Solo importa si volás con más de una pantalla.
- [ ] El test de "sin colores/fuentes literales fuera de `style/`" no
  atrapa nombres como `"cyan"`/`"blue"`/`"orange"` ni las familias de
  respaldo (`"Cantarell"`, `"DejaVu Sans"`) como literales -- cubre bien
  el caso "Segoe UI a mano", no todos los casos.
- [ ] Cobertura de tooltips despareja: hay tooltips ricos en la cámara y
  en los sliders, pero ninguno en "Guardar/Cargar Perfil", el checkbox de
  telemetría, o los combos de mouse/teclado en Sistema.
- [ ] Tamaños de ventana fijos (`WINDOW_MIN`, tamaños del HUD) sin
  ningún ajuste por DPI -- no se probó si es un problema real, solo que
  no hay ningún manejo explícito.

---

## Resumen

| Fase | Qué | Esfuerzo | Urgencia |
|---|---|---|---|
| 0 | Higiene de repo (.gitignore, dependencia muerta, lockfiles) | 30 min | Alta (barato, evita sustos) |
| 1 | Manejo de fallas en caliente (cámara/mouse desconectados en vuelo) | medio día | **Alta** (afecta el uso real) |
| 2 | CI básica (tests + cargo test en cada push) | medio día | Media-alta |
| 3 | Terminar lo ya documentado como pendiente (Fase 4/5 cámara, snap, vr_bridge) | variable, por punto | Media |
| 4 | Cobertura de tests faltante (motor.py, engine.rs, HUD) | 1-2 días | Media |
| 5 | Limpieza de código muerto | 1-2 horas | Baja |
| 6 | Documentación (README, arquitectura) | medio día | Media |
| 7 | Pulido menor (release build, multi-monitor, DPI, tooltips) | a elección | Baja |

Nada de esto es urgente en el sentido de "se rompe si no lo tocás" --
salvo la Fase 1, que es la única que cambia lo que pasa si algo falla
mientras estás volando de verdad.
