# Plan de limpieza y sanitización

> **Ejecución (28-09-2026):** los pasos marcados ✅ abajo ya se aplicaron y
> están commiteados/escritos en tu máquina. Los marcados ⚠️ **no se
> pudieron ejecutar** porque esta sesión no tiene una herramienta para
> borrar archivos ni una terminal en tu máquina (solo puede leer, escribir
> y reemplazar archivos) -- quedan como acción manual tuya, con el comando
> exacto al lado. También se confirmó que **la carpeta no es un
> repositorio git** (no hay `.git/`), así que los pasos de `git add`/
> `git rm --cached` del plan original no aplicaban; si querés control de
> versiones real, hay que correr `git init` primero.

Plan de ejecución concreto para la Fase 0 y Fase 5 de
`docs/plan_deuda_tecnica.md` (higiene de repo + código muerto), con pasos
en orden, comandos exactos, y cómo verificar cada uno antes de seguir al
siguiente. Nada de esto se ejecutó todavía -- es la lista para hacerlo.

Convención de riesgo: 🟢 no puede romper nada (borra basura/no-código o
metadatos). 🟡 podría cambiar comportamiento si algo depende de lo que se
toca -- correr los tests después. 🔴 no hay ninguno en este plan.

Después de cada paso 🟡, correr:
```
uv run python -m unittest tests.test_fixes
```
y si el paso toca algo del motor Rust, además:
```
cd src/backend/motor_rust && cargo test && cd -
```

---

## 1. Archivos y datos sueltos en la raíz

- [ ] ⚠️ **Borrar `config.json` de la raíz.** Confirmado: es un fósil de
  un esquema viejo (433 bytes, le faltan `t_min_cutoff`, `t_beta`,
  `head_trans_limits`, `button_map`, `head_limit_points`...) -- se comparó
  línea por línea contra `src/config/config1.json` (el que de verdad usa
  la app) y quedó claro que es una copia vieja, no un archivo en uso.
  **No se pudo borrar desde acá** (sin terminal ni herramienta de borrado
  en esta sesión). Corré en tu máquina:
  ```
  rm "/home/ratin/Entornos de Python/controlador_wt/controller_input-main/config.json"
  ```
- [ ] ⚠️ **Borrar los artefactos de trabajo sueltos.** Mismo motivo, misma
  acción manual:
  ```
  rm "/home/ratin/Entornos de Python/controlador_wt/controller_input-main/run.log" \
     "/home/ratin/Entornos de Python/controlador_wt/controller_input-main/depth_probe.csv" \
     "/home/ratin/Entornos de Python/controlador_wt/controller_input-main/depth_probe.png"
  ```
  Ya quedaron en `.gitignore` (paso 2) para que no se cuelen de nuevo el
  día que haya un repo git.

## 2. `.gitignore`

- [x] ✅ Agregadas las entradas `run.log`, `depth_probe.csv`,
  `depth_probe.png`, `config.json`.
- [x] ✅ **Sacado `*.lock` del `.gitignore`.** Ya no ignora `uv.lock`.
- [x] ✅ **Sacado también `Cargo.lock`** de la lista explícita (línea 15
  original) -- mismo argumento que `uv.lock`: es una app, no una
  librería, y querés builds reproducibles del motor.
- [ ] 🟢 `*.sh` se dejó como estaba (no había ningún script de utilidad
  visible para revisar si convenía versionarlo).

`.gitignore` resultante: sigue ignorando compilados/entornos
(`__pycache__/`, `.venv`, `target/`, `*.egg-info`) y el modelo sin usar
(`blaze_face_short_range.tflite`), ya no ignora lockfiles, y suma los
artefactos de ejecución de la sección 1.

## 3. Lockfiles: versionarlos

- [ ] ⚠️ **No se pudo hacer `git add`** porque **la carpeta no tiene un
  repositorio git** (`ls -la` en la raíz no muestra `.git/`). No hay nada
  que "commitear" todavía. Si querés versionar el proyecto:
  ```
  cd "/home/ratin/Entornos de Python/controlador_wt/controller_input-main"
  git init
  git add .
  git commit -m "Estado inicial del repo"
  ```
  Con el `.gitignore` ya corregido (sección 2), ese primer commit va a
  incluir `uv.lock` y `Cargo.lock` automáticamente y va a dejar afuera
  `run.log`/`depth_probe.*`/`config.json`.

## 4. Dependencias declaradas

- [x] ✅ **Sacada `keyboard` de `pyproject.toml`.** Ya se había confirmado
  por grep que no se usa en ningún lado de `src/`.
- [x] ✅ **Agregado el campo de licencia** (`license = "GPL-3.0-or-later"`)
  al bloque `[project]`.
- [ ] ⚠️ Falta correr `uv sync` en tu máquina para regenerar `uv.lock` sin
  `keyboard` -- esta sesión no tiene una terminal ahí para hacerlo:
  ```
  cd "/home/ratin/Entornos de Python/controlador_wt/controller_input-main"
  uv sync
  ```

## 5. Código muerto marcado por el propio código

Se confirmó (por grep sobre el espejo de `src/frontend/`, que está al día
porque esta misma sesión lo mantuvo sincronizado) que ningún archivo del
proyecto importa `theme.py`, `widgets.py`, `tooltips.py` ni el `hud.py`
plano -- solo el paquete real `frontend/hud/` está en uso, confirmado
porque `motor.py` y `tests/gui_snapshot.py` importan `frontend.hud`, que
resuelve al paquete, no al archivo obsoleto.

- [ ] ⚠️ `src/frontend/theme.py`
- [ ] ⚠️ `src/frontend/widgets.py`
- [ ] ⚠️ `src/frontend/tooltips.py`
- [ ] ⚠️ `src/frontend/hud.py` (el archivo plano)

**No se pudieron borrar** desde acá (sin terminal en tu máquina). Comando
para los cuatro juntos:
```
cd "/home/ratin/Entornos de Python/controlador_wt/controller_input-main/src/frontend"
rm theme.py widgets.py tooltips.py hud.py
```
Después, correr la suite de tests completa para confirmar que nada se
rompió (debería quedar igual, porque nada los importaba).

## 6. Config legacy sin usar (`device_mouse_path` / `device_kb_path`)

- [x] ✅ **Confirmado y arreglado.** Se leyó `src/config/config1.json`
  real de tu máquina: no tiene `device_mouse_path` ni `device_kb_path`.
  Se borró el bloque muerto en `src/backend/motor.py` (dentro de
  `find_input_devices`, la rama "selección manual antigua") -- no cambia
  ningún comportamiento porque esa rama nunca se ejecutaba con tu config
  actual.

## 7. Infraestructura sin uso

- [x] ✅ **Confirmado y arreglado.** Se buscó `.on(`/`.emit(` en todo
  `src/` y `tests/` (espejo local, al día) y no hay ningún llamador. Se
  borraron `AppContext.on()`, `AppContext.emit()` y el diccionario
  `_listeners` que los respaldaba, en `src/frontend/app/context.py`.

## 8. Documentación desincronizada

- [x] ✅ **Hecho.** Se agregó la nota de "desactualizado" al principio de
  `docs/plan_refactor_gui.md`, señalando que su Fase 6 ya se completó y
  está registrada en `docs/plan_vista_camara.md`.

---

## Pendiente de tu lado (todo lo que necesitaba borrar archivos o una terminal)

Juntando todo lo de arriba en un solo bloque para copiar y pegar en tu
máquina:

```bash
cd "/home/ratin/Entornos de Python/controlador_wt/controller_input-main"

# 1. Borrar fósiles y artefactos de trabajo
rm -f config.json run.log depth_probe.csv depth_probe.png

# 5. Borrar código muerto ya confirmado como sin uso
rm -f src/frontend/theme.py src/frontend/widgets.py \
      src/frontend/tooltips.py src/frontend/hud.py

# 4. Regenerar el lockfile sin la dependencia "keyboard"
uv sync

# 3. (opcional pero recomendado) inicializar git, ahora que el
#    .gitignore está correcto
git init
git add .
git commit -m "Estado inicial del repo"
```

## Verificación final

- [ ] `uv run python -m unittest tests.test_fixes` -- suite completa en
  verde (correr después del bloque de arriba, sobre todo después de
  borrar los 4 archivos y el bloque de `motor.py`).
- [ ] `cd src/backend/motor_rust && cargo test && cd -` -- en verde (no
  se tocó nada de Rust en esta pasada, así que debería seguir igual).
- [ ] `git status` (una vez que exista el repo) no muestra ningún archivo
  suelto de trabajo.
- [ ] `grep -rln "se puede borrar\|BORRA ESTE" src/` no devuelve nada
  (una vez borrados los 4 archivos).
- [ ] La app arranca y vuela normalmente (`uv run src/main.py`) -- checkeo
  manual final, porque nada de esto tiene un test end-to-end que lo cubra.
