# Plan — Vista de cámara con overlay (círculo, recuadros y ejes)

Objetivo: ver la cara con ayudas dibujadas encima —círculo que crece al
acercarse, recuadro de la cara dentro de un recuadro que la sigue, y tres
flechas con la orientación de la cabeza— y que eso esté **dentro de la GUI**,
sobre todo durante la calibración, donde saber si estás bien encuadrado es lo
que decide si el rango medido sirve.

Incluye al final la **Fase 6 del plan de refactor**, que quedó sin ejecutar.

---

## Qué tiene OpenCV para esto

Verificado por introspección sobre `cv2` (4.13 en el contenedor de pruebas) y
contra la guía de migración 4 → 5, porque tu entorno tiene OpenCV 5.0.0.93:
**la API de Python de todas estas funciones no cambió en OpenCV 5** (el módulo
`calib3d` se partió en `geometry`/`calib`/`stereo`, pero en Python se siguen
llamando `cv2.<nombre>`).

| Función | Qué aporta aquí |
|---|---|
| `cv2.minEnclosingCircle(pts)` | **El círculo que crece y se achica.** Devuelve centro y radio del círculo mínimo que contiene los landmarks: el radio en píxeles es proporcional al tamaño aparente de la cara, o sea a la distancia. Sin calibrar nada. |
| `cv2.boundingRect(pts)` | El recuadro de la cara. |
| `cv2.arrowedLine(img, p0, p1, color, th, lineType, shift, tipLength)` | **Las flechas de los 3 ejes**, con punta de flecha de verdad. |
| `cv2.drawFrameAxes(img, K, dist, rvec, tvec, length)` | Dibuja los 3 ejes en una sola llamada, pero **exige la matriz de la cámara** (ver más abajo). |
| `cv2.Rodrigues(R)` | Matriz de rotación ↔ vector de rotación, si se usa `drawFrameAxes`. |
| `cv2.projectPoints(...)` | Proyección en perspectiva de puntos 3D, la alternativa manual. |
| `cv2.solvePnP(...)` | **No la necesitamos**: estima la pose desde correspondencias 2D-3D, y MediaPipe ya nos entrega la matriz 4x4 completa. |
| `cv2.circle` / `rectangle` / `line` / `polylines` / `putText` / `getTextSize` | El resto del dibujo. |
| `cv2.LINE_AA` | Antialias: sin esto las diagonales y el círculo se ven escalonados. |
| `cv2.addWeighted` | Transparencias, si algún día se quiere un panel semitransparente. |
| `cv2.clipLine` | Recortar una línea al frame, si una flecha se sale. |
| `cv2.imencode('.ppm', frame)` | Puente a Tk sin Pillow (ver Fase 3). |

### Dos formas de dibujar las flechas, y por qué elijo una

**`cv2.drawFrameAxes` necesita los parámetros internos de la cámara.**
MediaPipe calcula su matriz 4x4 asumiendo una cámara en perspectiva con un
campo de visión vertical de ~63°; si le pasamos a `drawFrameAxes` una matriz
distinta, las flechas no coinciden con la cara que se ve.

**Lo que elijo: proyección ortográfica desde la matriz de rotación.** La
columna *i* de `R` es el eje *i* de la cabeza visto desde la cámara; se dibuja
directamente su componente (x, y) escalada al radio del círculo:

```python
dx = R[0, i] * length
dy = AXIS_Y_SIGN * R[1, i] * length      # la Y de la imagen crece hacia abajo
```

No necesita calibración, siempre queda pegado a la cara y para una flecha la
falta de perspectiva no se nota. Está **probado**: el prototipo del apéndice
genera las 8 poses de la vista previa con esta fórmula.

Si alguna vez se quiere perspectiva real, la matriz se puede construir con el
FOV que asume MediaPipe, y eso también está verificado en el prototipo:

```python
f = (img_h / 2) / math.tan(math.radians(63.0) / 2)
K = np.array([[f, 0, img_w / 2], [0, f, img_h / 2], [0, 0, 1]])
```

---

## Diseño del overlay

Un módulo de dibujo puro: recibe un frame BGR de numpy y lo anota. No abre
ventanas, no lee la cámara, no sabe de Tk. Eso es lo que permite usarlo desde
la ventana de OpenCV y desde la GUI sin duplicar nada, y probarlo sin cámara.

| Elemento | Cómo se calcula | Para qué sirve |
|---|---|---|
| Malla | los landmarks, uno de cada 4 | confirma que la detección está viva |
| Círculo de la cara | `minEnclosingCircle` | **distancia**: crece al acercarse |
| Círculo de referencia | el radio guardado al recentrar | dice si te alejaste de la distancia a la que calibraste |
| Recuadro de la cara | `boundingRect` | posición y tamaño exactos |
| Recuadro de encuadre | el de la cara, +27 % de ancho y +6 % de alto, **estático** y apaisado | **encuadre**: se queda quieto y solo salta cuando la caja blanca se le sale |
| 3 flechas | columnas de `R`, desde la **glabela** (`lm[9]`) | orientación: giro, cabeceo e inclinación |
| Punto | el **centro del cráneo**, por detrás de la glabela | el centro de giro real, no un punto de la piel |
| Texto | yaw/pitch/roll, traslación en cm, distancia vs referencia | los números que hoy hay que adivinar |
| Aviso | color del cuadrado + «muévete a la derecha» | qué corregir, sin interpretar nada |

El recuadro pasa de verde a ámbar a rojo según lo cerca que está la CARA del
borde del frame -- no el cuadrado: lo que importa es si te estás saliendo de
la cámara, no dónde quedó dibujado el recuadro. Contra el borde el recuadro
se recorta al frame y ya no puede seguir a la cara, así que la caja blanca
acaba asomando por fuera: ese es el aviso visual de que te saliste.

**Los colores salen de `frontend/style/colors.py`**, convertidos a BGR: las
flechas usan la misma paleta que las barras de ejes de la GUI y del HUD
(lateral cian, vertical amarillo, profundidad magenta). Así, si la Fase 6
cambia la paleta, el overlay la sigue sin tocarlo.

### Lo que el prototipo ya destapó

1. **La flecha de profundidad casi desaparece cuando miras de frente.** Es
   correcto: apunta a la cámara, y en proyección ortográfica se acorta a
   nada. Aparece al girar. Hay que decirlo en el tooltip o alguien lo va a
   reportar como un fallo.
2. ~~El signo vertical de las flechas no lo puedo determinar desde aquí.~~
   **Resuelto con la cámara real:** `AXIS_Y_SIGN = -1` es el correcto.
   OpenTrack las dibuja invertidas; aquí se conserva este sentido.
3. **El aviso ámbar hay que ajustarlo.** Ver abajo: con una cara real,
   0.15 daba 19 px de aviso. Subido a 0.30.
4. **El margen del 45 % es mucho de cerca**: a 38 cm el ROI ocupaba casi
   todo el frame. Bajado a 28 %.

### Correcciones tras la primera prueba con cámara real

Lo que se vio al correrlo de verdad, y cómo quedó:

| Lo que estaba mal | Cómo quedó |
|---|---|
| Los ejes nacían en la nariz | Nacen en la **glabela**, el landmark **9** |
| El punto estaba sobre la nariz | Marca el **centro del cráneo**: `HEAD_CENTER_DEPTH` (0.85) por detrás de la glabela, sobre el eje de profundidad de la cabeza. De frente cae sobre la glabela; se separa al girar, que es cuando sirve |
| El recuadro exterior perseguía la cara frame a frame | Es **estático**: solo se recalcula cuando la caja blanca se le sale (`framing_box`). Se fue `smooth_box`, que ya no hacía falta |
| El recuadro era desproporcionado (238 px de lado para una cara de 128x153) | Dos pasadas: primero un cuadrado de 189, y después **apaisado**, con margen propio por eje. `MARGIN_X` 0.27 y `MARGIN_Y` 0.06 dan **197x171** (ratio 1.15, 5 % menos de área que el cuadrado) |
| — | **El compromiso a vigilar:** bajar el alto se come la holgura vertical, porque el recuadro tiene que seguir conteniendo la caja de la cara. Quedan ~9 px arriba y abajo contra ~34 a los lados, así que al asentir se recoloca bastante seguido. `MARGIN_Y` es la perilla |
| El aviso ámbar salía demasiado tarde | `FRAME_WARN_RATIO` de 0.15 a 0.30 (~2,5 cm de margen en vez de ~1,5) |
| El sentido de las flechas estaba sin verificar | Verificado: se conserva |
| El círculo blanco y el rojo | Se quedan como están |

**El landmark 9 no se eligió de memoria.** Se corrió el detector de MediaPipe
sobre un frame real y se compararon los candidatos: el 9 cae a la altura del
extremo interno de las cejas (105 y 334) y en la línea media; el 8 y el 168
quedan ya sobre el puente de la nariz, y el 151 y el 10 más arriba, en la
frente. Hay un test que fija el índice para que nadie lo cambie sin querer.

---

## Estructura

```
src/frontend/camera_view/
├── __init__.py            # exporta CameraOverlay y CameraView
├── overlay.py             # el dibujo: puro, sobre un frame de numpy
├── geometry.py            # funciones puras (ROI, suavizado, estado, aviso)
└── widget.py              # el widget de Tk que muestra el frame
```

**Capas.** El overlay es presentación, pero lo alimenta el tracker, que es
backend. Ya hay precedente: `backend/motor.py` importa `frontend.hud`. Así que
`backend/tracker.py` importa `frontend.camera_view.overlay` dentro de la rama
de depuración, igual que el motor importa el HUD. Alternativa descartada:
inyectar el objeto de dibujo desde la GUI; más limpio en el papel, pero el
tracker ya importa `cv2` y dibuja, así que no compra nada.

---

## Fases

### Fase 1 — El módulo de dibujo, sobre la ventana de OpenCV que ya existe ✅

Riesgo bajo y resultado visible enseguida: la ventana `TRACKER DEBUG` ya se
abre cuando la GUI crea el tracker con `show_debug=True`.

- [x] `camera_view/geometry.py`: `roi_box`, `smooth_box`, `roi_state`,
      `nudge_text`, `enclosing_circle`, `bounding_box`, `axis_vectors`,
      `clip_box_to_frame`, `mesh_points`. Puras, sin `cv2`. Nota: el círculo
      no usa `cv2.minEnclosingCircle` -- para el indicador de distancia no
      hace falta el círculo *mínimo*, así que `enclosing_circle` es
      centro=centroide, radio=distancia al punto más lejano, en numpy puro.
      Se documenta la razón en el propio docstring.
- [x] `camera_view/overlay.py`: `CameraOverlay.draw(frame, landmarks, R, ...)`,
      que guarda el ROI suavizado entre frames. Colores desde `style/colors`.
- [x] `tracker.py`: `_draw_debug` pasa a delegar en el overlay. Ya tenía todo
      lo que hacía falta en el sitio de la llamada: `R` (de `matrix_parts`), la
      nariz (`lm[6]`), `rel_yaw/pitch/roll` y `rel_t` en cm.
- [x] `tracker.py`: se guarda `self.ref_radius` al recentrar, junto a
      `ref_x`/`ref_y`, para el círculo de referencia.
- [x] Tests de las funciones puras (13, en `TestCameraViewGeometry`): el
      radio crece cuando los landmarks se separan; el círculo contiene todos
      los puntos; el ROI contiene siempre la caja de la cara; el suavizado
      converge; el estado avisa en ámbar *antes* de salirse y pasa a `out`
      al recortarse; el aviso nombra el lado correcto (también en esquina);
      las flechas rotan lo que dice `R` (con `R = I` la flecha lateral es
      horizontal y la de profundidad se anula; con yaw de 90° la lateral
      también se anula, en vez de quedar fija).

**Aceptación:** con la cámara propia se ven círculo, dos recuadros y tres
flechas, y el aviso aparece al salirse del encuadre. Los tests pasan sin
cámara. **Pendiente de tu parte:** confirmarlo con tu cámara real -- desde
aquí solo pude probar la geometría, sin video. Corre
`uv run python -m unittest tests.test_fixes -q` (136 tests) y
`uv run python tests/gui_snapshot.py` para confirmar que nada más se movió;
ambos ya los corrí y pasan.

**Nota de arnés:** para que las pruebas corrieran sin tkinter instalado,
`tests/test_fixes.py` le hace al nuevo `frontend.camera_view.overlay` el
mismo doble que ya existía para `frontend.hud`, y `tests/gui_snapshot.py`
tuvo que construir el tk falso un poco antes (`take()`), porque ahora
`backend.tracker` también depende de `frontend.style` (tkinter de verdad)
en cuanto se importa. En tu máquina esto no cambia nada: tkinter ya está
instalado, porque la GUI entera ya lo necesitaba.

### Fase 2 — Publicar el frame anotado ✅

- [x] `HeadTracker.latest_frame()`: devuelve `(frame, contador)` del último
      frame anotado, o `(None, n)`. Asignación del objeto entero, como
      `self._axes`: el hilo de la cámara escribe, el de Tk lee, y nunca se
      lee medio frame. No hace falta copiarlo: `cv2.flip` ya devuelve un
      array nuevo cada vuelta.
- [x] `overlay_enabled` + `set_overlay_enabled()`: si nadie mira, no se
      dibuja. Apagarlo además SUELTA el frame, para que la GUI no se quede
      mostrando una imagen congelada que parece una cámara colgada.
      `show_debug` manda por su cuenta: la ventana aparte sigue dibujando.
- [x] Contador de frames, para que la GUI sepa si hay uno nuevo y no
      reconvierta la misma imagen 60 veces por segundo.
- [x] Guardia de `frame is None`: el motor sin GUI llama sin frame.

**Aceptación:** 8 tests con frames sintéticos (`TestLatestFrame`). Las cuatro
mutaciones probadas (no contar, guardar solo el primero, no soltar el frame
al apagar, quitar la guardia de None) fallan como deben.

### Fase 3 — El widget de Tk ✅

- [x] `camera_view/widget.py`: `CameraView`, un `Canvas` que toma el frame de
      `latest_frame()` y lo dibuja.
- [x] Conversión BGR → imagen de Tk. Pillow como camino principal, y
      **declarado en `pyproject.toml`**: ya venía instalado porque matplotlib
      lo arrastra, pero ahora el programa depende de él de verdad.
      Respaldo: `cv2.imencode('.ppm')` en base64. El `try` envuelve la
      conversión entera y no solo el import, porque un Pillow compilado sin
      soporte de Tk tiene `ImageTk` pero falla al USARLO.
- [x] Escalar a 320x240 antes de convertir, **sin deformar y sin agrandar**.
- [x] Refrescar solo cuando el contador de frames cambió.
- [x] La vista vive en el **panel derecho**, junto al preview de ejes
      (`frontend.preview.head_view.HeadView`), justo encima del punto
      yaw/pitch: son la misma lectura, una en imagen y otra en números.
      (Primero se puso dentro de la pestaña Head Tracker; se movió al
      panel a pedido, porque ahí se compara mejor con el resto de las
      lecturas y se ve sin importar qué pestaña esté abierta.)
- [x] La pestaña Head Tracker se queda solo con el botón para mostrar u
      ocultar esa vista compartida (más la rotación del video), a través
      de `ctx.camera_view`.
- [x] Botón para mostrar u ocultar la vista, que además apaga el dibujo en el
      tracker: el coste se va con ella.
- [x] `show_debug=False` al levantar el tracker propio (`launcher.py`): la
      ventana aparte de OpenCV ya no se abre. Es la mitad de la Fase 5,
      adelantada porque sin esto la vista embebida convivía con la
      ventana emergente en vez de reemplazarla.

**Dos trampas que costaron su arreglo:**

1. **La referencia a la imagen.** Si no se guarda, Tk la recoge y el canvas
   se queda en blanco. Es el error clásico de `PhotoImage` y hay un test que
   lo fija.
2. **El orden al volver a mostrarla.** `pack` respeta el orden de llamada, no
   el de creación: quitar el canvas y volver a ponerlo sobre su padre lo
   hacía reaparecer al final de todo. Por eso vive dentro de un contenedor
   propio que nunca se desempaqueta -- primero en la pestaña, y ahora
   dentro de `HeadView`.

**Aceptación:** 16 tests del widget y su integración (12 del widget, 4 de la
sección en la pestaña, 3 de su lugar en el panel derecho, 1 del arreglo de la
ventana emergente). Las mutaciones probadas (no guardar la referencia,
ignorar el contador, no apagar el dibujo al ocultar, quitar el contenedor
propio, desconectar la sección de la vista compartida, volver a
`show_debug=True`) fallan como deben. **Pendiente de tu parte:** verlo con la
cámara real -- desde aquí la vista se construye y se refresca sobre el
tkinter falso, pero nunca se pintó en una pantalla.

### Fase 4 — La vista dentro de los asistentes de calibración

Es el sitio donde más vale: el asistente te pide inclinarte 8 cm a la derecha
y ahora puedes ver si te estás saliendo del encuadre mientras lo haces.

- [ ] `CameraView` dentro de la ventana del asistente, bajo la instrucción.
- [ ] Si el encuadre está en rojo, el asistente **no** acepta la lectura: hoy
      aceptaría un rango medido con media cara fuera. Mensaje propio, con la
      misma mecánica de rechazo que `center` y `axis`.
- [ ] Test: con el ROI en estado `out`, marcar un paso se rechaza con el
      motivo nuevo.

**Aceptación:** los dos asistentes muestran la cara y rechazan las lecturas
mal encuadradas.

### Fase 5 — Limpieza de la ventana de OpenCV

Con la vista embebida, la ventana aparte pasa a ser opcional.

- [x] `show_debug=False` al levantar el tracker propio (movido a la Fase 3:
      sin esto la ventana de OpenCV se seguía abriendo además del widget).
- [ ] **Arreglar que pulsar `q` mate el tracker.** Hoy `cv2.waitKey` con `q`
      hace `self.running = False`, y los ejes de cabeza se quedan en cero
      hasta que cambias la fuente y vuelves. Debe cerrar solo la ventana.
- [ ] Nota: `cv2.imshow` desde un hilo que no es el principal no está
      soportado en todos los backends; es otra razón para que la vista
      embebida sea la principal.

---

### Fase 6 — Decisiones visuales pendientes (del plan de refactor) ✅

Cada punto es independiente y **regenera la instantánea a propósito**.

- [x] **Fuentes con respaldo**: `resolve_fonts()` se llama en `launcher.py`
      (justo después de crear `tk.Tk()`, antes de construir nada) y en
      `frontend/hud/hud.py` (el HUD corre en el proceso del motor, aparte,
      así que tiene que resolver sus propias familias). Bajo el tkinter
      falso de los tests no cambia nada (`tkinter.font.families()` está
      stubbeado a `()`, así que cae al mismo primer candidato de siempre);
      con una pantalla real sí importa, según lo que tengas instalado --
      comprobar con `fc-list | grep -iE "segoe|consolas|cantarell|dejavu"`.
- [x] **Colores sin doble significado**: resuelto antes de la Fase 1 de
      este plan (`AXIS_LATERAL`/`AXIS_DEPTH` dejaron de compartir cian y
      magenta con `THROTTLE`/`STICK_SNAPPED` y `RUDDER`/`RUDDER_PREVIEW`).
      `RUDDER` y `RUDDER_PREVIEW` siguen en magenta, pero es el MISMO
      significado (el timón, en el HUD y en el preview) -- no es el caso
      que este punto señalaba.
- [x] **Un solo verde**: `AXIS_ROLL` pasó de `#88ff88` a `#00ff00`, igual
      que `HUD_HEAD`.
- [x] **Un solo margen** de pestaña: `PAD_TAB_SYSTEM` (20) desapareció:
      Sistema ahora usa `PAD_TAB` (15), como el resto.
- [x] **Una sola familia** en el HUD: `HUD_FAMILIES` (Arial primero)
      desapareció; el HUD ahora resuelve con `UI_FAMILIES` (Segoe UI
      primero), igual que el resto de la GUI.
- [x] **Un solo blanco**: `TEXT` pasó de `#e0e0e0` a `#ffffff`, igual que
      `TEXT_STRONG`. Se conservan los dos nombres (como `DIVIDER`/
      `BUTTON_SECONDARY`) porque siguen siendo decisiones distintas que
      podrían volver a separarse.
- [x] **Selector de mando: Sistema → Botones.** Hecho (era el único punto
      pendiente de esta fase). Ver detalle abajo.

#### Selector de mando, Sistema → Botones ✅

Era más grande que el resto de la Fase 6 porque reordenó cómo se conectan
dos pestañas, no solo un valor de estilo.

**Por qué estaba en Sistema:** `ButtonsTab` necesita saber qué mando está
elegido para dibujar sus filas (`rebuild_rows()` llamaba a
`self.get_controller_id()` y cargaba el perfil de ese mando), pero el
selector había nacido en Sistema junto al resto del hardware.

**Lo que se movió**, de `src/frontend/tabs/system/tab.py` a
`src/frontend/tabs/buttons/tab.py`:

1. [x] La sección **MANDO EMULADO** completa: el `Combobox` de modelo,
   `list_controllers()`, `controller_id_by_name`, `_select_controller()` y
   `controller_id()`.
2. [x] La clave `controller_profile` de `owned_keys`: pasó de `SystemTab` a
   `ButtonsTab`. El test que comprueba que cada clave de configuración
   tenga un solo dueño (`test_every_key_has_exactly_one_owner`) sirvió de
   red de seguridad real: mutado a mano (quitando la clave de `owned_keys`
   de `ButtonsTab`), el conteo de 43 claves falla como debe.
3. [x] El evento `CONTROLLER_CHANGED` completo desapareció: con el
   selector viviendo en `ButtonsTab`, el combobox llama a
   `self.rebuild_rows()` directamente. `AppContext.on`/`.emit()` se
   dejaron (infraestructura genérica, sin uso hoy) pero la constante y sus
   dos usos (`ctx.on(...)` en Botones, `ctx.emit(...)` en Sistema) se
   quitaron.
4. [x] En `launcher.py`: `ButtonsTab(self.ctx)` ya no recibe
   `get_controller_id`; el orden de construcción de las pestañas dejó de
   importar (antes `buttons_tab` se creaba después de `system_tab` por esa
   referencia).
5. [x] En `config_bridge.py`: se actualizó el comentario de `apply_order`
   -- el orden entre Sistema y Botones ya no importa (Botones lee su
   propio combobox); Head Tracker se mantiene al final por la cámara.
6. `AxisOrderSection` no leía `controller_id()` (se verificó al hacer el
   cambio); no había nada más que apuntar.

**Tests actualizados:** golden completo regenerado (el combobox se movió
de árbol -- de paso arrastró varios cambios de fuente/color de esta misma
Fase 6 que habían quedado sin regenerar); `test_controller_change_rebuilds_button_rows`
reescrito sobre el combobox de Botones (ya no hay evento que emitir a
mano); dos tests nuevos: uno confirma que el selector vive en Botones y no
en Sistema, y otro que cargar un perfil sigue seleccionando el mando
correcto en el combobox (descolocándolo a propósito antes de cargar, para
que el test note si `apply_config` dejara de reseleccionarlo -- con un
solo mando en el fixture, comparar solo `controller_id()` no lo hubiera
notado).

**Aceptación:** el combobox aparece en Botones, arriba del mapeo; Sistema
perdió la sección MANDO EMULADO; cambiar el modelo desde Botones sigue
reconstruyendo las filas al instante; cargar un perfil sigue aplicando el
mando guardado. 188 tests, todos verdes.

---

## Resumen

| Fase | Qué | Esfuerzo | Riesgo | Cambia lo que se ve | Estado |
|---|---|---|---|---|---|
| 6 (colores) | Un color, un significado | 1 h | Bajo | **Sí** | ✅ Hecho |
| 1 | Módulo de dibujo + ventana de OpenCV | medio día | Bajo | **Sí** (la ventana de depuración) | ✅ Hecho |
| 2 | Publicar el frame anotado | 2 h | Bajo | No | ✅ Hecho |
| 3 | Widget de Tk en el panel derecho | medio día | Medio | **Sí** | ✅ Hecho |
| 4 | Vista en los asistentes + rechazo por encuadre | medio día | Medio | **Sí** | Pendiente |
| 5 | Ventana de OpenCV opcional y arreglo de `q` | 1 h | Bajo | Sí | Parcial (ya no se abre; falta lo de `q`) |
| 6 (resto) | Fuentes, márgenes, verdes, blancos | a elección | Bajo | **Sí** | ✅ Hecho |
| 6 (mando) | Selector de mando: Sistema → Botones | medio día | Medio | No | ✅ Hecho |

---

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El signo vertical de las flechas está al revés | Una constante, y un paso de verificación en la Fase 1 |
| `PIL.ImageTk` no disponible | Respaldo por PPM con `tk.PhotoImage`, decidido en tiempo de ejecución |
| La conversión de frames ralentiza la GUI | Escalar a 320x240, refrescar solo con frame nuevo, y poder ocultar la vista |
| `cv2.imshow` desde un hilo secundario | La vista embebida pasa a ser la principal (Fase 5) |
| Dos consumidores de la cámara (GUI y motor) | Ya resuelto: la fuente de cabeza es exclusiva, y con fuente externa la vista se oculta |
| El overlay tapa la cara | Malla decimada, líneas finas y poder apagar la malla |
| La escala en cm de MediaPipe no es exacta | El círculo y el ROI son en píxeles, que sí son exactos; los cm solo van en el texto |

---

## Apéndice: el prototipo

La vista previa de 8 poses que acompaña a este plan se generó con una cara
sintética (una nube de puntos proyectada con el FOV de 63° que asume
MediaPipe) y **el mismo código de dibujo que propone la Fase 1**. Sirvió para
descartar dos versiones del recuadro exterior: primero fue un margen fijo del
frame, que no avisaba nunca porque la cara casi no llega al borde; la que
quedó sigue a la cara. También movió el origen de las flechas del centro del
círculo a la nariz.

No sustituye la prueba con tu cámara: falta confirmar el signo vertical, los
valores del margen y el umbral del aviso ámbar.
