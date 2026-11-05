"""Instantánea de la GUI completa sobre el tkinter falso.

Construye la ventana del configurador, abre los dos asistentes, el diálogo
de orden de ejes y un tooltip, y construye el HUD de vuelo. De cada árbol
registra, en orden: tipo de widget, texto, colores, fuentes, empaquetado e
ítems de canvas. Colores y fuentes se normalizan para comparar lo que SE VE,
no cómo está escrito (#444 == #444444 == "gray27" no, pero "white" ==
"#ffffff"; ("Segoe UI", 9) == ("Segoe UI", 9, "normal")).

La interacción se hace como la haría un usuario: los asistentes y el
diálogo se abren PULSANDO SU BOTÓN, buscado por su texto. Así el arnés no
depende de nombres internos, que son justamente lo que un refactor cambia.

Uso:
    uv run python tests/gui_snapshot.py --update    # regenera el golden
    uv run python tests/gui_snapshot.py             # compara y muestra diferencias
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
GOLDEN = os.path.join(HERE, "golden", "gui_tree.json")

for _p in (os.path.join(HERE, "stubs"), SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COLOR_KEYS = {
    "bg", "fg", "background", "foreground", "fill", "outline", "troughcolor",
    "activebackground", "activeforeground", "highlightbackground", "highlightcolor",
    "selectcolor", "insertbackground", "disabledforeground",
}
NAMED_COLORS = {
    "white": "#ffffff", "black": "#000000", "red": "#ff0000",
    "gray": "#808080", "grey": "#808080",
}
# Argumentos que no son apariencia: se registra solo que existen.
CALLABLE_KEYS = {"command", "yscrollcommand", "xscrollcommand"}


def norm_color(value):
    if not isinstance(value, str):
        return value
    v = value.strip().lower()
    if v in NAMED_COLORS:
        return NAMED_COLORS[v]
    if v.startswith("#") and len(v) == 4:
        return "#" + "".join(c * 2 for c in v[1:])
    return v


def norm_font(value):
    if isinstance(value, (tuple, list)):
        parts = list(value)
        if len(parts) == 2:
            parts.append("normal")
        return parts
    return value


def norm_value(key, value):
    if key in COLOR_KEYS:
        return norm_color(value)
    if key == "font":
        return norm_font(value)
    if key in CALLABLE_KEYS:
        return "<callable>" if callable(value) else value
    if key in ("variable", "textvariable"):
        return {"var": getattr(value, "_v", None)}
    if key == "window":
        return type(value).__name__
    if callable(value):
        return "<callable>"
    if isinstance(value, tuple):
        return [norm_value(key, v) for v in value]
    if isinstance(value, list):
        return [norm_value(key, v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: norm_value(k, v) for k, v in value.items()}
    return value


def norm_kw(kw):
    return {k: norm_value(k, v) for k, v in sorted(kw.items())}


def tooltip_text(widget):
    for _, cb in widget.bindings:
        owner = getattr(cb, "__self__", None)
        if owner is not None and type(owner).__name__ == "ToolTip":
            return getattr(owner, "text", None)
    return None


def node(widget):
    out = {"type": type(widget).__name__, "kw": norm_kw(widget.kw)}
    if widget.pack_kw is not None:
        out[widget.manager] = norm_kw(widget.pack_kw)
    if widget.tab_text is not None:
        out["tab"] = widget.tab_text
    if widget.pane_kw is not None:
        out["pane"] = norm_kw(widget.pane_kw)
    if widget.items:
        out["items"] = [{"kind": i["kind"],
                         "coords": [round(c, 3) if isinstance(c, float) else c
                                    for c in i["coords"]],
                         "kw": norm_kw(i["kw"])} for i in widget.items]
    tip = tooltip_text(widget)
    if tip is not None:
        out["tooltip"] = tip
    if widget.children:
        out["children"] = [node(c) for c in widget.children]
    return out


def find(widget, predicate):
    if predicate(widget):
        return widget
    for c in widget.children:
        hit = find(c, predicate)
        if hit is not None:
            return hit
    return None


def find_button(root, text):
    return find(root, lambda w: type(w).__name__ == "Button" and w.kw.get("text") == text)


class FakeTracker:
    """Tracker determinista: valores fijos y distintos de cero, para que la
    posición de los puntos y las barras del preview entre en la instantánea."""

    running = True

    def __init__(self, config):
        self.config = config

    def get_axes(self):
        return (0.1, -0.2)

    def get_head_axes(self):
        return (0.1, -0.2, 0.05, 0.3, -0.1, 0.2)

    def get_relative_degrees(self):
        return (5.0, -3.0)

    def get_relative_cm(self):
        return (1.0, -0.5, 0.2)

    def window_stats(self, window_s=0.5):
        return {"n": 0, "span_s": 0.0, "mean_yaw": 0.0, "mean_pitch": 0.0,
                "spread": float("inf"), "stable": False}

    def trans_window_stats(self, window_s=0.5):
        return {"n": 0, "span_s": 0.0, "mean": (0.0, 0.0, 0.0),
                "spread": float("inf"), "stable": False}

    def update_config(self, cfg):
        pass

    def recenter(self):
        pass

    def stop(self):
        self.running = False


def fixed_config():
    """Configuración determinista: los valores por defecto más una
    calibración parcial, para que los textos de estado no sean los vacíos."""
    from utils.config import _migrate
    cfg = _migrate({})
    cfg["head_limit_points"] = [
        {"label": "up", "angle_deg": 270.0, "magnitude": 30.0, "units": "deg"},
        {"label": "right", "angle_deg": 0.0, "magnitude": 35.0, "units": "deg"},
    ]
    cfg["head_trans_limits"] = {"units": "cm", "x_pos": 8.0, "x_neg": 7.5}
    return cfg


def _fresh_import():
    """Construye el tk falso, fija la configuración y el tracker, y reimporta
    la GUI desde cero. El orden importa: los módulos de la GUI copian estos
    nombres al importarse, así que el parche va ANTES."""
    for p in (os.path.join(HERE, "stubs"), SRC):
        if p not in sys.path:
            sys.path.insert(0, p)
    import faketk
    tk = faketk.build()

    for name in list(sys.modules):
        if name == "gui_app" or name.startswith("frontend"):
            sys.modules.pop(name, None)

    import utils.config as uc
    uc.load_config = fixed_config
    uc.save_config = lambda cfg: None

    import backend.tracker as bt
    bt.create_head_source = lambda config, show_debug=False, source=0: FakeTracker(config)

    os.environ["SCREEN_W"], os.environ["SCREEN_H"] = "1920", "1080"
    import gui_app
    return tk, faketk, gui_app


class launched:
    """Construye la GUI completa sobre el tk falso y deja todo como estaba
    al salir. Para tests de integración:

        with gui_snapshot.launched() as (tk, app):
            app.bridge.read_config()
    """

    def __enter__(self):
        import utils.config as uc
        import backend.tracker as bt
        self._saved = (uc.load_config, uc.save_config, bt.create_head_source)
        tk, _, gui_app = _fresh_import()
        return tk, gui_app.ConfigLauncher()

    def __exit__(self, *exc):
        import utils.config as uc
        import backend.tracker as bt
        uc.load_config, uc.save_config, bt.create_head_source = self._saved
        for name in list(sys.modules):
            if name == "gui_app" or name.startswith("frontend"):
                sys.modules.pop(name, None)
        return False


def take():
    """Toma la instantánea y deja los módulos parcheados como estaban."""
    # backend.tracker importa frontend.camera_view.overlay, que importa
    # frontend.style (tkinter.ttk de verdad). El tk falso tiene que existir
    # ANTES de esta primera importación, no solo dentro de _fresh_import().
    for p in (os.path.join(HERE, "stubs"), SRC):
        if p not in sys.path:
            sys.path.insert(0, p)
    import faketk
    faketk.build()

    import utils.config as uc
    import backend.tracker as bt
    saved = (uc.load_config, uc.save_config, bt.create_head_source)
    try:
        return _take()
    finally:
        uc.load_config, uc.save_config, bt.create_head_source = saved
        for name in list(sys.modules):
            if name == "gui_app" or name.startswith("frontend"):
                sys.modules.pop(name, None)


def _take():
    tk, faketk, gui_app = _fresh_import()
    snap = {}

    app = gui_app.ConfigLauncher()
    root = app.root
    snap["main_window"] = node(root)
    snap["ttk_styles"] = [[a, b, norm_kw(c)] for a, b, c in faketk.STYLE_LOG]

    # --- asistentes: se abren pulsando su botón, como el usuario ------------
    def open_dialog(button_text):
        before = len(root.children)
        btn = find_button(root, button_text)
        if btn is None:
            raise AssertionError(f"no existe el botón «{button_text}»")
        btn.invoke()
        new = root.children[before:]
        return [node(w) for w in new]

    snap["wizard_rotation"] = open_dialog("🧭 Calibrar rango de giro (asistente guiado)")
    snap["wizard_translation"] = open_dialog("📐 Calibrar rango de traslación (6 pasos)")

    shown = {}
    tk.messagebox.showinfo = lambda title, msg, **kw: shown.update(title=title, msg=msg)
    find_button(root, "🎛️ Ver orden de los ejes de cada dispositivo").invoke()
    snap["axis_order_dialog"] = shown

    # --- tooltip: el primer icono de ayuda, abierto -------------------------
    icon = find(root, lambda w: tooltip_text(w) is not None)
    owner = next(getattr(cb, "__self__") for _, cb in icon.bindings
                 if type(getattr(cb, "__self__", None)).__name__ == "ToolTip")
    owner._show()
    snap["tooltip_popup"] = node(owner.tip_window)

    # --- todos los textos de ayuda, en orden de aparición -------------------
    tips = []

    def collect(w):
        t = tooltip_text(w)
        if t is not None:
            tips.append(t)
        for c in w.children:
            collect(c)

    collect(root)
    snap["help_texts"] = tips

    # --- HUD de vuelo --------------------------------------------------------
    from frontend.hud import JoystickHUD
    hud = JoystickHUD(320)
    hud.update(0.3, -0.4, 0.5, -0.25, 0.1, -0.2, False, False, head_trans=(0.3, -0.1, 0.2))
    snap["hud_stick_window"] = node(hud.root)
    snap["hud_head_window"] = node(hud.win_tracker)
    return snap


def diff(a, b, path="", out=None, limit=40):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(a) != type(b):
        out.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: falta en el golden -> {b[k]!r}"[:300])
            elif k not in b:
                out.append(f"{path}.{k}: desapareció (era {a[k]!r})"[:300])
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} elementos -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
    elif a != b:
        out.append(f"{path}: {a!r} -> {b!r}"[:300])
    return out


def main():
    snap = json.loads(json.dumps(take(), ensure_ascii=False))
    if "--update" in sys.argv:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"[OK] Golden regenerado: {GOLDEN}")
        return
    with open(GOLDEN, encoding="utf-8") as f:
        golden = json.load(f)
    problems = diff(golden, snap)
    if problems:
        print(f"[DIFERENCIAS] {len(problems)} (se muestran hasta 40):")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("[OK] La GUI es idéntica al golden.")


if __name__ == "__main__":
    main()
