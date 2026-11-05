# Plan de refactor — GUI por módulos

Objetivo: partir `gui_app.py` en módulos pequeños dentro de `src/frontend/`,
con una sola fuente de verdad para colores, tipografías y espaciados, **sin
cambiar nada de lo que se ve** hasta la fase final, donde los cambios visuales
se deciden uno por uno.

Todo lo que sigue sale de un inventario del código actual (Fases A–D del 6DOF
incluidas), no de una estructura genérica: los nombres, valores y conteos son
los reales.

> **Nota (28-09-2026):** este documento quedó desactualizado. La Fase 6 que
> describe más abajo (fuentes con fallback, colores del HUD, mover el
> selector de mando de Sistema a Botones, etc.) ya se completó -- está
> registrada y marcada como hecha en `docs/plan_vista_camara.md`. Se
> conserva este archivo como historial del refactor, no como lista de
> pendientes activa; sus checkboxes de la Fase 6 no se actualizaron cuando
> ese trabajo se hizo.

## Estado (27-09-2026)

**Fases 0 a 5 hechas. La 6 (decisiones visuales) queda pendiente, a elección.**

- La instantánea de la Fase 0 (`tests/golden/gui_tree.json`) se generó con el
  código **original** y la GUI refactorizada es idéntica: 407 widgets, sus
  colores, fuentes, empaquetado e ítems de canvas, los dos asistentes, el
  diálogo de orden de ejes, el tooltip, los 32 textos de ayuda, los estilos
  ttk y las dos ventanas del HUD.
- `gui_app.py`: 1.683 → 19 líneas. Archivo más grande de `frontend/`: 221.
- 107 tests (antes 95), incluidos lint de colores y fuentes literales, y el
  viaje de ida y vuelta de las 43 claves por las 4 pestañas.
- Los asistentes no bajaron a ~150 líneas como estimaba el plan: la mecánica
  está una sola vez, pero el controlador sin Tk y la especificación de cada
  asistente suman 368 líneas entre `calibration_wizard.py` y `wizards.py`.
  A cambio, la lógica se prueba sin ventana.
- Los módulos viejos `theme.py`, `widgets.py`, `tooltips.py` y `hud.py` quedan
  como reexportaciones marcadas OBSOLETO (no se pudieron borrar a distancia).
  Nada los importa: se pueden borrar.

---

## Estado actual

| Archivo | Líneas | Qué tiene |
|---|---|---|
| `src/gui_app.py` | 1.683 | Una sola clase, `ConfigLauncher`, con 50 métodos |
| `src/frontend/hud.py` | 223 | Las dos ventanas del HUD en vuelo |
| `src/frontend/tooltips.py` | 306 | Textos de ayuda de todas las pestañas + la clase `ToolTip` |
| `src/frontend/widgets.py` | 60 | `ModernSlider` |
| `src/frontend/theme.py` | 29 | 6 colores, 3 fuentes y `apply_theme()` |

Los métodos más grandes de `ConfigLauncher`:

| Método | Líneas | Nota |
|---|---|---|
| `_build_tab_tracker` | 215 | Creció al doble con la Fase C |
| `_open_trans_calibration_wizard` | 148 | Casi idéntico al de abajo |
| `_open_calibration_wizard` | 131 | Casi idéntico al de arriba |
| `_load_profile_dialog` | 91 | Escribe en los widgets de las 4 pestañas |
| `_get_current_config` | 74 | Lee los widgets de las 4 pestañas |
| `_build_visualization_panel` | 73 | Panel derecho completo |
| `update_ui` | 67 | Bucle de ~60 Hz que dibuja todo el panel derecho |

---

## Restricciones

Estas no se negocian; cada fase las respeta.

1. **`src/gui_app.py` sigue existiendo y ejecutándose.** `utils.GUI_SCRIPT`
   lo lanza por ruta, así que no se puede mover. Al final queda como un
   lanzador de unas 10 líneas.
2. **`from frontend.hud import JoystickHUD` sigue funcionando.** Lo importa
   `backend/motor.py`. Si `hud` pasa a ser un paquete, su `__init__.py`
   exporta `JoystickHUD` y la ruta de importación no cambia.
3. **Los 94 tests pasan al final de cada fase.** Varios llaman métodos
   privados de `ConfigLauncher` directamente (ver *Compatibilidad con los
   tests*), así que esos métodos se mantienen como delegaciones hasta la
   Fase 5.
4. **Fases 0 a 5: cero cambios visibles.** Es un refactor. Todo cambio de lo
   que se ve (fuentes, colores, márgenes) va a la Fase 6, cada uno como
   decisión aparte.
5. **Todo se corre con `uv run`**, igual que el resto del proyecto.

---

## Hallazgos del inventario

Cosas que el refactor destapa y que conviene saber antes de empezar.

1. **Las fuentes del código probablemente no existen en Linux.** Se usan
   `"Segoe UI"` (fuente de Windows) y `"Consolas"` (fuente de Windows). Si no
   están instaladas, Tk usa silenciosamente otra fuente por defecto, así que
   la escala tipográfica que describe el código no es la que se dibuja.
   Verificar con `fc-list | grep -iE "segoe|consolas"`. Se corrige en la
   Fase 6 con una lista de familias de respaldo.
2. **Constantes definidas y nunca usadas.** `FONT_MAIN` y `COLOR_ACCENT_DIM`
   existen en `theme.py` y no los usa nadie, mientras el literal
   `("Segoe UI", 9)` —que es exactamente `FONT_MAIN`— aparece 7 veces.
3. **`wraplength=400` no es un ancho, es una marca.** Aparece 7 veces y
   `_enable_auto_wrap` lo reescribe según el ancho real de la pestaña, pero
   ese mismo método lo usa para decidir qué etiquetas **cortas** ajustar
   (las largas se ajustan siempre). Quitarlo haría que una nota corta deje
   de ajustarse. *(Corregido al ejecutar el plan: la primera versión decía
   que era código muerto.)* Queda como `spacing.WRAP_MARKER`.
4. **Colores con dos significados en el HUD.** Magenta es a la vez *timón*
   (ventana del stick) y *profundidad* (ventana de cabeza); cian es *gases*,
   *stick pegado al eje* y *traslación lateral*. En vuelo miras las dos
   ventanas a la vez.
5. **Dos verdes distintos.** El roll usa `#88ff88` en el preview y la cabeza
   usa `#00ff00` en el HUD.
6. **Márgenes inconsistentes.** Tres pestañas usan `pad = 15` y Sistema usa
   `pad = 20`.
7. **Dos familias en el HUD.** El HUD y los botones del mouse usan `Arial`;
   el resto, `Segoe UI`.
8. **Los dos asistentes de calibración son el mismo código dos veces**
   (131 + 148 líneas). Cambian los pasos, la lectura en vivo, la función que
   guarda y los mensajes de error; la mecánica es idéntica.
9. **Acoplamiento central en la configuración.** `_get_current_config` y
   `_load_profile_dialog` meten la mano en los widgets de las cuatro
   pestañas. Mientras eso siga así, ninguna pestaña se puede mover sola.
10. **Acoplamiento entre pestañas.** El selector de mando (`cb_controller`) se
    construye en **Sistema**, pero las filas de **Botones** dependen de él:
    `_build_tab_system` termina llamando a `_rebuild_button_rows()`.

---

## Constantes y estilos

Tokens **semánticos**: el nombre dice para qué se usa, no qué color es. Por
eso `#444` tiene dos nombres (`DIVIDER` y `BUTTON_SECONDARY`): hoy coinciden,
pero son decisiones distintas y deben poder cambiar por separado.

En las Fases 1–5 **todos los valores son idénticos a los actuales**. Los
cambios van a la Fase 6.

### `frontend/style/colors.py`

```python
# --- Superficies -----------------------------------------------------
BG               = "#1e1e1e"   # fondo de la ventana
PANEL            = "#2d2d2d"   # fondo de pestañas y tarjetas
CANVAS           = "#000000"   # fondo de los previews
SURFACE_OFF      = "#333333"   # indicador inactivo (botones del mouse)
INPUT_BG         = "#111111"   # caja numérica del slider
TOOLTIP_BG       = "#252526"
CHECK_SELECT     = "#222222"   # selectcolor de los Checkbutton

# --- Líneas y rieles --------------------------------------------------
DIVIDER          = "#444444"   # separador entre secciones (14 usos)
BORDER           = "#333333"   # borde de canvas (highlightbackground)
GRID             = "#222222"   # cruz central de los previews
TROUGH           = "#404040"   # riel del slider
TROUGH_OFF       = "#2a2a2a"   # riel del slider deshabilitado
DEADZONE_FILL    = "#2a2a2a"   # zona muerta en el gráfico de curva

# --- Texto -------------------------------------------------------------
TEXT             = "#e0e0e0"   # texto normal
TEXT_STRONG      = "#ffffff"   # fg="white" (23 usos)
TEXT_SUBTLE      = "#aaaaaa"   # subtítulos y lecturas en vivo
TEXT_MUTED       = "#888888"   # notas y etiquetas secundarias (15 usos)
TEXT_DISABLED    = "#666666"
TEXT_ON_ACCENT   = "#000000"   # fg="black" sobre botones de acento

# --- Estado y acciones ----------------------------------------------------
ACCENT           = "#00e676"
WARN             = "#ff3d00"
CAPTURE          = "#ffb300"   # esperando una tecla / manteniendo posición
INACTIVE         = "#555555"   # punto en zona muerta o fuente externa
BUTTON_SECONDARY = "#444444"   # botones secundarios (8 usos)

# --- Ejes: la MISMA paleta en el preview y en el HUD ---------------------
AXIS_LATERAL     = "#00ffff"
AXIS_VERTICAL    = "#ffff00"
AXIS_DEPTH       = "#ff00ff"
AXIS_ROLL        = "#88ff88"
HEAD_DOT_HUD     = "#00ff00"

# --- Stick y controles del HUD ------------------------------------------
STICK_NORMAL     = "#ff8800"
STICK_SNAPPED    = "#00ffff"
STICK_SATURATED  = "#ff0000"
THROTTLE         = "#00ffff"
THROTTLE_WEP     = "#ff0000"
THROTTLE_REVERSE = "#ff5555"
RUDDER           = "#ff00ff"
```

`COLOR_ACCENT_DIM` no se migra: no lo usa nadie.

### `frontend/style/fonts.py`

La escala se define por **rol**, no por tamaño. La familia se resuelve una
vez, al arrancar, eligiendo la primera disponible de la lista (Fase 6).
Mientras tanto, cada rol usa la primera familia de la lista, que es lo que
hay hoy.

```python
UI_FAMILIES   = ("Segoe UI", "Cantarell", "Noto Sans", "DejaVu Sans")
MONO_FAMILIES = ("Consolas", "DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono")
HUD_FAMILIES  = ("Arial", "Liberation Sans", "DejaVu Sans")   # se unifica en la Fase 6

# rol: (tamaño, peso)                          hoy
UI_SCALE = {
    "title":       (16, "bold"),   # "CONFIGURACIÓN DE VUELO"
    "cta":         (14, "bold"),   # botón INICIAR VUELO
    "instruction": (13, "bold"),   # instrucción del asistente
    "section":     (11, "bold"),   # FONT_HEADER (19 usos)
    "button_lg":   (10, "bold"),   # botón «Marcar» del asistente
    "label":       (9,  "bold"),   # FONT_BOLD (10 usos)
    "body":        (9,  "normal"), # FONT_MAIN — hoy literal, 7 usos
    "note":        (8,  "normal"), # notas y subtítulos (14 usos)
    "note_bold":   (8,  "bold"),
    "micro":       (7,  "bold"),   # etiquetas de las barras de ejes
}
MONO_SCALE = {
    "mono":      (9, "normal"),    # lecturas en vivo del asistente
    "mono_bold": (9, "bold"),
}
HUD_SCALE = {
    "hud_label": (8, "bold"),
    "hud_small": (7, "bold"),
    "hud_micro": (6, "bold"),
    "mouse_btn": (8, "normal"),    # botones L/R/M del preview
}

def resolve_fonts(root):
    """Elige la familia disponible y construye FONTS. Se llama UNA vez,
    después de crear tk.Tk() y ANTES de construir cualquier widget: Tk
    evalúa la tupla de fuente al crear el widget. El HUD vive en otro
    proceso (el motor) y la llama por su cuenta."""
```

`FONTS` expone cada rol como tupla lista para usar: `font=FONTS.section`.
Sin display (los tests con `faketk`) se usa la primera familia de cada lista.

### `frontend/style/spacing.py`

```python
PAD_TAB        = 15        # margen lateral de las pestañas (Sistema usa 20: Fase 6)
PAD_TAB_SYSTEM = 20        # se conserva hasta la Fase 6 para no mover nada

SPACE_XS, SPACE_S, SPACE_M, SPACE_L = 2, 5, 8, 10

SECTION_GAP    = 10          # pady del separador (19 usos de pady=10)
HEADER_PADY    = (5, 5)      # título de sección (11 usos)
NOTE_PADY      = (0, 8)      # nota bajo un título
BUTTON_PADY    = (0, 5)

# Tamaños fijos
WINDOW_MAX       = (1200, 780)
WINDOW_MIN       = (720, 460)
PREVIEW_SIZE     = 250       # canvas del stick
HEAD_PREVIEW_H   = 150       # canvas de yaw/pitch
AXIS_BARS_H      = 76        # canvas de barras de traslación y roll
STICK_VIS_SCALE  = 70
WIZARD_GEOMETRY  = {"rotation": "460x300", "translation": "480x330"}
```

### Tabla de migración de literales

Para que la Fase 1 sea mecánica: cada literal tiene **un** token según dónde
se usa.

| Literal | Usos | Token según contexto |
|---|---|---|
| `"#444"` | 23 | `DIVIDER` (Frame de 1 px) · `BUTTON_SECONDARY` (bg de Button) |
| `"#888"` | 15 | `TEXT_MUTED` |
| `"#333"` | 11 | `BORDER` (highlightbackground) · `SURFACE_OFF` (bg de indicador) |
| `"#222"` | 8 | `GRID` (líneas de canvas) · `CHECK_SELECT` (selectcolor) |
| `"#aaa"` | 5 | `TEXT_SUBTLE` |
| `"#555"` | 3 | `INACTIVE` |
| `"#000"` | 3 | `CANVAS` |
| `fg="white"` | 23 | `TEXT_STRONG` |
| `fg="black"` | 7 | `TEXT_ON_ACCENT` |
| `("Segoe UI", 8)` | 14 | `FONTS.note` |
| `("Segoe UI", 9)` | 7 | `FONTS.body` |
| `("Consolas", 9)` | 3 | `FONTS.mono` |

---

## Componentes

Los patrones que más se repiten se vuelven funciones. Una línea en vez de
cuatro, y el estilo en un solo lugar.

| Componente | Reemplaza | Usos hoy |
|---|---|---|
| `section_header(parent, text)` | `tk.Label(..., fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', ...)` | 17 |
| `divider(parent)` | `tk.Frame(tab, bg="#444", height=1).pack(fill='x', ...)` | 14 |
| `secondary_button(parent, text, command)` | `tk.Button(..., bg="#444", fg="white")` | 8 |
| `note(parent, text)` | `tk.Label(..., fg="#888", font=("Segoe UI", 8), justify='left', wraplength=400)` | 7 |
| `primary_button(parent, text, command, size="md")` | `tk.Button(..., bg=COLOR_ACCENT, fg="black", font=...)` | 5 |
| `subtitle(parent, text)` | `tk.Label(..., fg="#aaa", font=("Segoe UI", 8))` | 3 |
| `slider_row(parent, text, lo, hi, step, value, help_text)` | `_add_slider_row` (recibe el texto de ayuda, no una clave global) | 31 |
| `AxisBars(canvas, axes)` con `.update(values)` | barras duplicadas en `gui_app.py` y `hud.py` | 2 |
| `CalibrationWizard(root, spec)` | los dos asistentes | 2 |

**El asistente genérico se parte en dos**: un `WizardController` sin Tk (pasos,
captura, reintentos, tiempo límite, qué mensaje mostrar) y una vista delgada
que solo dibuja. Así la lógica se prueba sin ventana. Cada asistente pasa a
ser un `WizardSpec`: la lista de pasos, cómo leer la posición en vivo, cómo
formatearla, cómo medir la estabilidad, qué función guarda, y los textos de
cada motivo de rechazo.

---

## Estructura de directorios

```
src/
├── gui_app.py                        # lanzador (~10 líneas); utils.GUI_SCRIPT apunta aquí
└── frontend/
    ├── __init__.py
    │
    ├── style/                        # CONSTANTES Y ESTILOS: única fuente de verdad visual
    │   ├── __init__.py               # reexporta COLORS, FONTS, SPACE, apply_theme, resolve_fonts
    │   ├── colors.py
    │   ├── fonts.py
    │   ├── spacing.py
    │   └── ttk_theme.py              # apply_theme() — hoy theme.py
    │
    ├── components/                   # piezas reutilizables, sin lógica del dominio
    │   ├── __init__.py
    │   ├── layout.py                 # section_header, divider, note, subtitle
    │   ├── buttons.py                # primary_button, secondary_button, checkbox
    │   ├── slider.py                 # ModernSlider + slider_row — hoy widgets.py
    │   ├── tooltip.py                # ToolTip + help_icon (sin textos) — hoy tooltips.py
    │   ├── scrollable.py             # pestaña con scroll, auto-ajuste de texto, rueda
    │   ├── axis_bars.py              # barras bipolares (preview y HUD)
    │   └── calibration_wizard.py     # WizardController + vista
    │
    ├── tabs/                         # una carpeta por pestaña
    │   ├── __init__.py
    │   ├── base.py                   # contrato Tab
    │   ├── stick/
    │   │   ├── __init__.py
    │   │   ├── tab.py                # hoy _build_tab_stick
    │   │   ├── curve_graph.py        # hoy _update_curve_graph
    │   │   └── help.py               # radius, outer, curve, deadzone, snap
    │   ├── tracker/
    │   │   ├── __init__.py
    │   │   ├── tab.py                # orquesta las secciones en el orden actual
    │   │   ├── source.py             # selector de fuente de cabeza + atenuado
    │   │   ├── rotation.py           # sensibilidad, filtro, snap, octágono
    │   │   ├── translation.py        # 6DOF, pivote del cuello, rango de traslación
    │   │   ├── roll.py
    │   │   ├── camera.py             # rotación del video
    │   │   ├── axis_order.py         # diálogo «orden de los ejes»
    │   │   ├── wizards.py            # los dos WizardSpec (datos, no interfaz)
    │   │   └── help.py
    │   ├── buttons/
    │   │   ├── __init__.py
    │   │   ├── tab.py
    │   │   ├── capture.py            # captura de tecla sin Tk — hoy _handle_raw_key y cía.
    │   │   └── help.py
    │   └── system/
    │       ├── __init__.py
    │       ├── tab.py
    │       ├── devices.py            # hoy _get_device_list, _preload_device_selection
    │       ├── profiles.py           # guardar / cargar perfil
    │       └── help.py
    │
    ├── preview/                      # panel derecho del configurador
    │   ├── __init__.py
    │   ├── panel.py                  # hoy _build_visualization_panel
    │   ├── stick_view.py
    │   ├── head_view.py              # punto yaw/pitch + AxisBars
    │   └── inputs_view.py            # gases, timón y botones del mouse
    │
    ├── hud/                          # ventanas en vuelo (las abre el motor)
    │   ├── __init__.py               # exporta JoystickHUD: la importación de motor.py no cambia
    │   ├── hud.py                    # JoystickHUD: orquesta las dos ventanas
    │   ├── stick_window.py
    │   └── head_window.py
    │
    └── app/
        ├── __init__.py
        ├── context.py                # AppContext: lo que comparten las pestañas
        ├── launcher.py               # ConfigLauncher delgado: ventana, notebook, bucle, vuelo
        ├── input_reader.py           # hilos de evdev + cola hacia Tk
        └── config_bridge.py          # junta read_config() / reparte apply_config()
```

Los textos de ayuda se reparten entre los `help.py` de cada pestaña: cada una
es dueña de lo que explica. `help_icon` recibe el texto directamente, así
desaparece el diccionario global de 306 líneas.

---

## Contrato de pestaña

```python
class Tab(Protocol):
    title: str
    def build(self, parent) -> None: ...
    def read_config(self) -> dict: ...          # SOLO las claves que posee
    def apply_config(self, cfg: dict) -> None: ...
    def set_enabled(self, enabled: bool) -> None: ...   # opcional
```

**Las pestañas nunca importan el lanzador.** Reciben un `AppContext` con lo
mínimo que comparten: la configuración cargada, un acceso al tracker actual
(cambia en vivo al cambiar la fuente), la raíz de Tk para los diálogos, y
eventos. Eso evita importaciones circulares y permite probar cada pestaña con
un contexto falso.

El acoplamiento Sistema → Botones (hallazgo 10) se resuelve con un evento del
contexto, `on_controller_changed`: Sistema lo emite y Botones reconstruye sus
filas. El selector se queda donde está hasta la Fase 6.

### Propiedad de las claves de configuración

Cada clave tiene una sola pestaña dueña. `config_bridge` junta los
`read_config()`, y un test verifica que la unión sea exactamente el conjunto
de claves de `DEFAULT_CONFIG` que se editan desde la GUI: ni faltan ni se
pisan.

| Pestaña | Claves | Cant. |
|---|---|---|
| Stick | `radius`, `curve`, `deadzone`, `snap`, `outer` | 5 |
| Head Tracker — fuente, rotación y cámara | `head_source`, `t_sens_x`, `t_sens_y`, `t_min_cutoff`, `t_beta`, `t_deadzone`, `t_snap_axis`, `t_snap_outer`, `t_center_drag`, `cam_rotation`, `head_limit_points`\* | 11 |
| Head Tracker — traslación y roll | los 21 `t_trans_*`, `t_neck_*`, `t_sens_roll`, `t_roll_deadzone`, `head_roll_limit_deg`, más `head_trans_limits`\* | 22 |
| Botones | `button_map` | 1 |
| Sistema | `controller_profile`, `telemetry_enabled`, `mouse_phys`, `keyboard_phys` | 4 |
| **Total** | | **43** |

\* Las escribe solo el asistente de calibración; la pestaña las conserva, no
las edita.

---

## Compatibilidad con los tests

Los tests llaman directamente estos métodos privados de `ConfigLauncher`:

`_handle_raw_key` · `_refresh_head_source_state` · `_reset_trans_limits` ·
`_on_head_source_change` · `_update_axis_bars` · `_show_axis_order` ·
`_get_current_config` · `_format_trans_calibration_status` ·
`_drain_input_queue` · `_build_tab_tracker`

Durante las Fases 1–4 siguen existiendo en `ConfigLauncher` como
delegaciones de una línea hacia el módulo nuevo. En la Fase 5 los tests pasan
a importar los módulos nuevos y las delegaciones se borran.

Además, `import_gui()` en modo liviano reemplaza `frontend.theme`,
`frontend.widgets` y `frontend.tooltips` por módulos vacíos. En cuanto esos
módulos se muevan, los tests estarían probando reemplazos que ya no
corresponden a nada. Por eso la Fase 0 elimina el modo liviano: `faketk` ya
permite usar los módulos reales.

---

## Fases

### Fase 0 — Red de seguridad

**No empezar el refactor sin esto.** Es lo que demuestra que las fases
siguientes no cambian nada visible.

- [ ] **Instantánea del árbol de widgets.** Construir `ConfigLauncher`
      completo sobre `faketk` y recorrer el árbol registrando, en orden, el
      tipo de cada widget, su texto, `bg`, `fg`, `font`, y los argumentos de
      `pack`. Guardarlo en `tests/golden/gui_tree.json`. Un test compara
      contra ese archivo: **cualquier cambio visible hace fallar el test**.
- [ ] Ampliar `faketk` con lo que pide el `__init__` real: `Tk.title`,
      `geometry`, `minsize`, `protocol`, `after`, `after_cancel`, `bind_all`,
      `winfo_screenwidth/height`; `ttk.PanedWindow.add`; `ttk.Notebook.add`;
      y que `pack` guarde sus argumentos.
- [ ] Parchear `_init_hardware` en el test (abre dispositivos evdev reales).
- [ ] Eliminar el modo liviano de `import_gui()`: siempre `faketk` y los
      módulos reales.
- [ ] En tu máquina: `fc-list | grep -iE "segoe|consolas"` para confirmar el
      hallazgo 1.

**Aceptación:** la instantánea existe, el test que la compara pasa, y los 94
tests siguen verdes.

### Fase 1 — Constantes y estilos

- [ ] Crear `frontend/style/` con `colors.py`, `fonts.py`, `spacing.py` y
      `ttk_theme.py`, con los valores de arriba.
- [ ] `frontend/theme.py` queda como reexportación de `frontend.style`
      (compatibilidad), marcado como obsoleto.
- [ ] Reemplazar todos los literales de color y fuente de `gui_app.py`,
      `hud.py`, `widgets.py` y `tooltips.py` según la tabla de migración.
- [ ] **Todavía no** resolver familias de fuente: eso cambia lo que se ve.

**Aceptación:**
- Fuera de `frontend/style/` no queda ningún color. Ojo: `hud.py` usa
  comillas simples, así que la búsqueda tiene que cubrir ambas, y también
  los colores por nombre:
  ```
  grep -rnE "['\"]#[0-9a-fA-F]{3,6}['\"]" src/gui_app.py src/frontend --include=*.py | grep -v frontend/style/
  grep -rnE "(fg|bg|fill|outline)=['\"](white|black|red|gray)['\"]" src/gui_app.py src/frontend --include=*.py
  ```
- Ídem para las tuplas `("Segoe UI", ...)`, `("Consolas", ...)` y `("Arial", ...)`.
- La instantánea es **idéntica**.

### Fase 2 — Componentes

- [ ] `components/layout.py` y `components/buttons.py`; reemplazar los 17
      títulos, 14 separadores, 8 botones secundarios, 7 notas, 5 botones
      primarios y 3 subtítulos.
- [ ] Mover `ModernSlider` a `components/slider.py` y `_add_slider_row` a
      `slider_row`; `widgets.py` queda como reexportación.
- [ ] Mover `ToolTip` y `create_help_icon` a `components/tooltip.py`; los
      textos se quedan por ahora en `tooltips.py`.
- [ ] `components/scrollable.py`: `_make_scrollable_tab`,
      `_enable_auto_wrap`, `_on_mousewheel`.
- [ ] `components/axis_bars.py` y usarlo en el preview y en el HUD.

**Aceptación:** instantánea idéntica; `gui_app.py` baja de 1.683 a unas
1.300 líneas; tests de cada componente con `faketk`.

### Fase 3 — Pestañas

Orden de menor a mayor riesgo: **Stick → Botones → Sistema → Head Tracker**.

- [ ] `tabs/base.py` y `app/context.py`.
- [ ] Mover cada pestaña a su carpeta, con su `help.py`, `read_config()` y
      `apply_config()`.
- [ ] `app/config_bridge.py` reemplaza el cuerpo de `_get_current_config` y
      la parte de `_load_profile_dialog` que escribe widgets.
- [ ] Resolver Sistema → Botones con `on_controller_changed`.
- [ ] Head Tracker se parte en `source`, `rotation`, `translation`, `roll`,
      `camera` y `axis_order`, ensamblados por `tab.py` en el orden actual.
- [ ] Borrar `tooltips.py` cuando el último texto se haya movido.

**Aceptación:**
- `_get_current_config` queda en unas 10 líneas.
- El test de ida y vuelta, que hoy cubre solo las 22 claves de traslación y
  roll, se amplía a **las 43 claves de las 4 pestañas**.
- Un test verifica que ninguna clave tenga dos dueños.
- Instantánea idéntica.

### Fase 4 — Asistente genérico

- [ ] `WizardController` (sin Tk) + vista, en `components/calibration_wizard.py`.
- [ ] Los dos asistentes pasan a ser dos `WizardSpec` en `tabs/tracker/wizards.py`.
- [ ] Mismos textos, mismos tiempos (`_CAPTURE_TIMEOUT_S = 6.0`), mismos
      umbrales de estabilidad.
- [ ] Tests del controlador sin ventana: avanza al guardar, se queda en el
      paso al rechazar, muestra el mensaje de cada motivo (`center`, `axis`,
      eje correcto con sentido invertido), agota el tiempo, y cierra al
      terminar.

**Aceptación:** las 279 líneas de los dos asistentes quedan en unas 150; la
instantánea del asistente abierto es idéntica para ambos.

### Fase 5 — Preview, HUD y lanzador

- [ ] `preview/`: cada vista con su propio `update(estado)`; `update_ui` pasa
      a ser un bucle que junta el estado y llama las vistas.
- [ ] `hud/`: `stick_window.py` y `head_window.py`; `hud/__init__.py`
      exporta `JoystickHUD`.
- [ ] `app/launcher.py`, `app/input_reader.py`.
- [ ] `src/gui_app.py` queda como lanzador.
- [ ] Los tests importan los módulos nuevos; se borran las delegaciones.

**Aceptación:** `gui_app.py` ≤ 15 líneas; ningún archivo de `frontend/` pasa
de 300 líneas; `from frontend.hud import JoystickHUD` sigue funcionando;
instantánea idéntica.

### Fase 6 — Decisiones visuales

La única fase que cambia lo que se ve. Cada punto es independiente, opcional,
y **regenera la instantánea a propósito**, en un commit propio.

- [ ] **Fuentes con respaldo**: activar `resolve_fonts()` (hallazgo 1).
- [ ] **Colores del HUD sin doble significado**: separar magenta
      timón/profundidad y cian gases/lateral (hallazgo 4).
- [ ] **Un solo verde** para la cabeza en preview y HUD (hallazgo 5).
- [ ] **Un solo margen** de pestaña: 15 o 20 (hallazgo 6).
- [ ] **Una sola familia** en el HUD (hallazgo 7).
- [ ] **Un solo blanco**: `TEXT` (`#e0e0e0`) contra `TEXT_STRONG` (`#ffffff`).
- [ ] ¿Mover el selector de mando de Sistema a Botones, donde se usa?
      (hallazgo 10).

---

## Resumen de fases

| Fase | Qué | Esfuerzo | Riesgo | Cambia lo que se ve |
|---|---|---|---|---|
| 0 | Instantánea del árbol de widgets | medio día | Bajo | No |
| 1 | Constantes y estilos | medio día | Bajo | No |
| 2 | Componentes | 1 día | Bajo | No |
| 3 | Pestañas por carpeta | 1–2 días | Medio | No |
| 4 | Asistente genérico | 1 día | Medio | No |
| 5 | Preview, HUD y lanzador | 1 día | Medio | No |
| 6 | Decisiones visuales | a elección | Bajo | **Sí** |

Orden obligado: **0 → 1 → 2 → 3 → 4 → 5**. La 6 puede ir en cualquier
momento después de la 1, punto por punto.

---

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Un cambio visual se cuela en un refactor | La instantánea de la Fase 0 lo detecta |
| Los tests llaman métodos privados que se mueven | Delegaciones hasta la Fase 5 |
| Importaciones circulares pestaña ↔ lanzador | Las pestañas solo conocen `AppContext` |
| Tk evalúa la fuente al crear el widget | `resolve_fonts()` después de `tk.Tk()` y antes de construir nada |
| El HUD vive en otro proceso | Llama `resolve_fonts()` por su cuenta |
| Mover `gui_app.py` rompe el lanzamiento | No se mueve: queda como lanzador |
| `motor.py` deja de encontrar el HUD | `hud/__init__.py` exporta `JoystickHUD` |
| `update_ui` corre a ~60 Hz | Llamar vistas en vez de código en línea cuesta unas llamadas por cuadro: despreciable |

---

## Métricas de éxito

| Métrica | Hoy | Meta |
|---|---|---|
| Líneas de `gui_app.py` | 1.683 | ≤ 15 |
| Archivo más grande de `frontend/` | 1.683 | ≤ 300 |
| Literales de color fuera de `style/` | ~145 (111 hex + 35 por nombre) | 0 |
| Tuplas de fuente fuera de `style/` | 40 | 0 |
| Líneas de los dos asistentes | 279 | ~150 |
| Claves cubiertas por el test de ida y vuelta | 22 (traslación y roll) | 43 (todas) |
| Tests | 94 | 94 + los nuevos, en cada fase |

---

## Qué se conserva

Todo el comportamiento. `ModernSlider`, el auto-ajuste de texto, la rueda del
mouse, los dos asistentes, el diálogo de orden de ejes, el preview, el HUD y
el formato de `config1.json` siguen iguales: se mueven, no se reescriben. El
tkinter falso (`tests/stubs/faketk.py`) que se escribió para la Fase C es lo
que hace posible todo el plan, porque permite construir la GUI completa y
compararla sin pantalla.
