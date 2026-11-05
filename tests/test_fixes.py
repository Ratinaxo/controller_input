"""Pruebas de las correcciones en Python (tracker, motor, config, GUI).

Corre con:  python3 tests/test_fixes.py   (desde la raíz del repo)
Usa stubs para rust_motor / evdev / tkinter (no disponibles en este entorno).
"""
import base64
import contextlib
import math
import os
import queue
import sys
import types
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)            # gui_snapshot, al correr con -m unittest
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

# frontend.hud usa tkinter; motor.py solo necesita el nombre.
hud = types.ModuleType("frontend.hud")
hud.JoystickHUD = object
sys.modules["frontend.hud"] = hud

# frontend.camera_view.overlay usa frontend.style (que importa tkinter.ttk);
# tracker.py solo necesita poder instanciar CameraOverlay. `geometry.py` en
# cambio es puro -- sin cv2 ni tkinter -- así que se deja entrar de verdad
# dándole al paquete falso un __path__ real: se prueba sin ningún doble.
camera_view = types.ModuleType("frontend.camera_view")
camera_view.__path__ = [os.path.join(HERE, "..", "src", "frontend", "camera_view")]
sys.modules["frontend.camera_view"] = camera_view

camera_view_overlay = types.ModuleType("frontend.camera_view.overlay")


class _FakeCameraOverlay:
    def __init__(self, *args, **kwargs):
        self.last_state = None

    def reset(self):
        pass

    def draw(self, frame, *args, **kwargs):
        return frame


camera_view_overlay.CameraOverlay = _FakeCameraOverlay
sys.modules["frontend.camera_view.overlay"] = camera_view_overlay

import numpy as np
from evdev import ecodes
import rust_motor

from utils.config import load_config, LEGACY_KEYS, DEFAULT_CONFIG
from utils.controllers import load_controller, resolve_code, code_name
from backend import motor
from backend.tracker import (
    HeadTracker, EXPECTED_ANGLES, HEAD_SOURCES, create_head_source,
    valid_limit_points, has_legacy_calibration, matrix_to_euler,
    matrix_to_euler3, matrix_parts, compensate_neck, valid_trans_limits,
    TRANS_CALIB_UNITS, DEFAULT_TRANS_LIMIT_CM, TRANS_STEPS,
    direction_scales, angle_distance, CALIB_UNITS,
)
from frontend.camera_view import geometry as camera_geometry

import json
import tempfile
import utils.config as config_mod

USER_CONFIG = {
    "radius": 320, "curve": 1.0, "deadzone": 0.07, "snap": 0.01, "outer": 30,
    "t_sens_x": 11.0, "t_sens_y": 20.0, "t_smooth": 0.01, "t_center_drag": 0.001,
    "controller_profile": "thrustmaster_t16000m",
    "head_limit_points": [
        {"label": "up", "angle_deg": 267.04, "magnitude": 9.65},
        {"label": "down", "angle_deg": 90.71, "magnitude": 23.02},
        {"label": "left", "angle_deg": 173.09, "magnitude": 11.23},
        {"label": "right", "angle_deg": 23.38, "magnitude": 14.94},
        {"label": "diag_up_left", "angle_deg": 196.43, "magnitude": 13.88},
        {"label": "diag_up_right", "angle_deg": 63.14, "magnitude": 32.61},
        {"label": "diag_down_left", "angle_deg": 125.98, "magnitude": 17.88},
        {"label": "diag_down_right", "angle_deg": 50.31, "magnitude": 27.13},
    ],
    "yaw_limit_pos": 17.77, "yaw_limit_neg": 16.91, "pitch_limit_pos": 18.66, "pitch_limit_neg": 20.0,
}


def load_user_config():
    """Carga USER_CONFIG a través de load_config() usando un archivo temporal."""
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "config1.json"
        path.write_text(json.dumps(USER_CONFIG))
        original = config_mod.CONFIG_FILE
        config_mod.CONFIG_FILE = path
        try:
            return load_config()
        finally:
            config_mod.CONFIG_FILE = original


def rot(yaw_deg, pitch_deg):
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    Ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    M = np.eye(4)
    M[:3, :3] = Ry @ Rx
    return M


def make_tracker(config):
    """HeadTracker sin cámara ni MediaPipe, para probar el procesamiento."""
    import threading
    from collections import deque
    t = HeadTracker.__new__(HeadTracker)
    t._axes = (0.0, 0.0)
    t._head_axes = (0.0,) * 6
    t._rel_deg = (0.0, 0.0)
    t._rel_cm = (0.0, 0.0, 0.0)
    t.running = True
    t.show_debug = False
    t.config = config
    t.ref_yaw = t.ref_pitch = t.ref_roll = None
    t.ref_t = None
    t.ref_x = t.ref_y = 0.5
    t.ref_radius = 0
    t._overlay = camera_view_overlay.CameraOverlay()
    t._frame = None
    t._frame_count = 0
    t.overlay_enabled = False
    t.needs_recenter = True
    t._last_detect_t = None
    t._hist = deque(maxlen=240)
    t._hist_t = deque(maxlen=240)
    t._hist_lock = threading.Lock()
    t.filter_yaw = rust_motor.RustFilter(config.get("t_min_cutoff", 1.0), config.get("t_beta", 0.05), 1.0)
    t.filter_pitch = rust_motor.RustFilter(config.get("t_min_cutoff", 1.0), config.get("t_beta", 0.05), 1.0)
    t.filter_roll = rust_motor.RustFilter(config.get("t_min_cutoff", 1.0), config.get("t_beta", 0.05), 1.0)
    tmc = config.get("t_trans_min_cutoff", 0.8)
    tbeta = config.get("t_trans_beta", 0.02)
    t.filter_tx = rust_motor.RustFilter(tmc, tbeta, 1.0)
    t.filter_ty = rust_motor.RustFilter(tmc, tbeta, 1.0)
    t.filter_tz = rust_motor.RustFilter(config.get("t_trans_min_cutoff_z", 0.4),
                                       config.get("t_trans_beta_z", 0.01), 1.0)
    t._telemetry = SimpleNamespace(log=lambda row: None, close=lambda: None)
    t.start_time = 0.0
    return t


LM = [SimpleNamespace(x=0.5, y=0.5) for _ in range(478)]
LM[33] = SimpleNamespace(x=0.45, y=0.5)
LM[263] = SimpleNamespace(x=0.55, y=0.5)


def feed(t, yaw, pitch, t0, seconds, fps=30):
    n = int(seconds * fps)
    for i in range(n):
        t._process_detection(t0 + i / fps, LM, rot(yaw, pitch), 640, 480, None)
    return t0 + n / fps


class TestConfig(unittest.TestCase):
    def test_head_source_default(self):
        self.assertEqual(load_user_config()["head_source"], "internal")
        self.assertIn("internal", HEAD_SOURCES)
        self.assertIn("external", HEAD_SOURCES)

    def test_migration_of_user_config(self):
        cfg = load_user_config()
        for k in LEGACY_KEYS:
            self.assertNotIn(k, cfg)
        self.assertEqual(cfg["t_min_cutoff"], 1.0)
        self.assertEqual(cfg["t_beta"], 0.05)
        self.assertEqual(cfg["button_map"], {})
        self.assertEqual(cfg["radius"], 320)          # valores del usuario se conservan
        self.assertEqual(cfg["t_sens_y"], 20.0)
        self.assertEqual(len(cfg["head_limit_points"]), 8)
        self.assertTrue(has_legacy_calibration(cfg["head_limit_points"]))
        self.assertEqual(valid_limit_points(cfg["head_limit_points"]), [])


class TestProfileAndButtonMap(unittest.TestCase):
    def test_resolve_code(self):
        self.assertEqual(resolve_code("BTN_TRIGGER", ecodes), 0x120)
        self.assertEqual(resolve_code("0x12c", ecodes), 0x12C)
        self.assertEqual(resolve_code(300, ecodes), 300)
        self.assertEqual(resolve_code("300", ecodes), 300)
        self.assertIsNone(resolve_code("BTN_NOPE", ecodes))
        self.assertIsNone(resolve_code(True, ecodes))

    def test_profile_matches_virtual_device(self):
        profile = load_controller("thrustmaster_t16000m")
        codes = [resolve_code(b["code"], ecodes) for b in profile["buttons"]]
        self.assertEqual(codes, rust_motor.virtual_button_codes())
        self.assertEqual(motor.check_profile_codes(profile), [])

    def test_old_profile_is_flagged(self):
        old = {"buttons": [{"id": 14, "code": "BTN_A"}, {"id": 1, "code": "BTN_TRIGGER"}]}
        warnings = motor.check_profile_codes(old)
        self.assertEqual(len(warnings), 1)
        self.assertIn("14", warnings[0])

    def test_build_button_map(self):
        cfg = {"controller_profile": "thrustmaster_t16000m",
               "button_map": {"1": ecodes.BTN_LEFT, "14": ecodes.KEY_1, "16": 57,
                              "99": 3, "2": "abc"}}
        m = motor.build_button_map(cfg)
        self.assertEqual(m, {ecodes.BTN_LEFT: 0x120, ecodes.KEY_1: 0x12D, 57: 0x12F})

    def test_empty_map(self):
        self.assertEqual(motor.build_button_map({"button_map": {}}), {})


class TestPhysicsMirror(unittest.TestCase):
    """La GUI y el motor usan la misma función; aquí se prueba la réplica."""
    def test_preview_behaviour(self):
        p = rust_motor.RustPhysics(320, 1.0, 0.07, 0.1, 0.05, 30)
        self.assertEqual(p.hard_limit(), 350)
        x0, _, dz0, _ = p.calculate(0.07 * 320 + 0.01, 0)
        self.assertFalse(dz0)
        self.assertLess(x0, 0.001)
        self.assertEqual(p.calculate(320, 0)[0], 1.0)


class TestTrackerMath(unittest.TestCase):
    def test_euler_roundtrip(self):
        for y, p in [(0, 0), (20, 0), (0, -15), (25, 10), (-30, 12)]:
            ey, ep = matrix_to_euler(rot(y, p))
            self.assertAlmostEqual(ey, y, places=6)
            self.assertAlmostEqual(ep, p, places=6)

    def test_fallback_limit_is_35_degrees(self):
        cfg = {"t_sens_x": 10.0, "t_sens_y": 10.0, "head_limit_points": []}
        self.assertEqual(HeadTracker.compute_output(35, 0, cfg), (1.0, 0.0))
        yaw, _ = HeadTracker.compute_output(17.5, 0, cfg)
        self.assertAlmostEqual(yaw, 0.5)

    def test_sensitivity_is_post_gain(self):
        cfg = {"t_sens_x": 20.0, "t_sens_y": 10.0, "head_limit_points": []}
        yaw, _ = HeadTracker.compute_output(17.5, 0, cfg)
        self.assertAlmostEqual(yaw, 1.0)
        yaw, _ = HeadTracker.compute_output(10, 0, cfg)
        self.assertAlmostEqual(yaw, 20 / 35)

    def test_legacy_points_are_ignored(self):
        cfg = load_user_config()
        a = HeadTracker.compute_output(17.5, 0, cfg)
        b = HeadTracker.compute_output(17.5, 0, {**cfg, "head_limit_points": []})
        self.assertEqual(a, b)

    def test_user_bad_diagonal_would_be_rejected(self):
        # Punto 'diag_up_right' del config del usuario: medido en 63°.
        r = HeadTracker.validate_calibration_point(
            "diag_up_right", 32.6 * math.cos(math.radians(63.1)), 32.6 * math.sin(math.radians(63.1)))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "direction")
        self.assertEqual(r["expected"], 315.0)

    def test_center_reading_rejected(self):
        r = HeadTracker.validate_calibration_point("right", 2.0, 1.0)
        self.assertEqual(r["reason"], "center")

    def test_full_calibration_and_normalization(self):
        cfg = {"t_sens_x": 10.0, "t_sens_y": 10.0, "head_limit_points": [{"label": "up", "angle_deg": 1, "magnitude": 9}]}
        t = make_tracker(cfg)
        limits = {"right": 40, "left": 30, "up": 15, "down": 25,
                  "diag_up_left": 20, "diag_up_right": 22, "diag_down_left": 24, "diag_down_right": 28}
        for label, mag in limits.items():
            a = math.radians(EXPECTED_ANGLES[label] + 10)  # 10° de desvío: aceptable
            r = t.calibrate_direction(label, mag * math.cos(a), mag * math.sin(a))
            self.assertTrue(r["ok"], (label, r))
        pts = cfg["head_limit_points"]
        self.assertEqual(len(pts), 8)                 # el punto viejo se descartó
        self.assertTrue(all(p["units"] == "deg" for p in pts))
        a = math.radians(10)
        yaw, pitch = HeadTracker.compute_output(40 * math.cos(a), 40 * math.sin(a), cfg)
        self.assertAlmostEqual(math.hypot(yaw, pitch), 1.0, places=6)
        yaw, pitch = HeadTracker.compute_output(20 * math.cos(a), 20 * math.sin(a), cfg)
        self.assertAlmostEqual(math.hypot(yaw, pitch), 0.5, places=6)


class TestTrackerProcessing(unittest.TestCase):
    def test_recenter_and_response(self):
        cfg = {"t_sens_x": 10.0, "t_sens_y": 10.0, "t_min_cutoff": 1.0, "t_beta": 0.05,
               "t_center_drag": 0.0, "head_limit_points": []}
        t = make_tracker(cfg)
        # Postura inicial girada 5°: el primer frame define el centro.
        now = feed(t, 5, -3, 0.0, 0.5)
        self.assertEqual(t.get_axes(), (0.0, 0.0))
        # Girar 17.5° a la derecha respecto al centro -> ~0.5 en < 0.5 s.
        now = feed(t, 22.5, -3, now, 0.5)
        yaw, pitch = t.get_axes()
        self.assertGreater(yaw, 0.45)
        self.assertLess(abs(pitch), 0.02)
        # Recentrar: la salida vuelve a 0 en el mismo frame, sin deslizamiento.
        t.recenter()
        feed(t, 22.5, -3, now, 1 / 30)
        self.assertEqual(t.get_axes(), (0.0, 0.0))

    def test_lag_is_small(self):
        cfg = {"t_sens_x": 10.0, "t_sens_y": 10.0, "t_min_cutoff": 1.0, "t_beta": 0.05,
               "t_center_drag": 0.0, "head_limit_points": []}
        t = make_tracker(cfg)
        now = feed(t, 0, 0, 0.0, 0.3)
        # Giro rápido de 0 a 30° en 0.2 s
        for i in range(1, 7):
            now += 1 / 30
            t._process_detection(now, LM, rot(30 * i / 6, 0), 640, 480, None)
        now += 1 / 30
        t._process_detection(now, LM, rot(30, 0), 640, 480, None)
        # Tras ~100 ms más de mantener, debe estar sobre el 85% del objetivo.
        now = feed(t, 30, 0, now, 0.1)
        rel_yaw, _ = t.get_relative_degrees()
        self.assertGreater(rel_yaw, 0.85 * 30, rel_yaw)

    def test_center_drag(self):
        base = {"t_sens_x": 10.0, "t_sens_y": 10.0, "t_min_cutoff": 1.0, "t_beta": 0.05,
                "head_limit_points": []}
        t_on = make_tracker({**base, "t_center_drag": 0.02})
        t_off = make_tracker({**base, "t_center_drag": 0.0})
        for t in (t_on, t_off):
            now = feed(t, 0, 0, 0.0, 0.2)
            feed(t, 4, 0, now, 5.0)   # se acomoda 4° y se queda quieto
        self.assertLess(abs(t_on.get_relative_degrees()[0]), 0.5)
        self.assertAlmostEqual(t_off.get_relative_degrees()[0], 4.0, delta=0.05)
        # Lejos del centro (mirando a un lado) no hay arrastre.
        t_far = make_tracker({**base, "t_center_drag": 0.02})
        now = feed(t_far, 0, 0, 0.0, 0.2)
        feed(t_far, 30, 0, now, 3.0)
        self.assertAlmostEqual(t_far.get_relative_degrees()[0], 30.0, delta=0.05)

    def test_window_stats(self):
        import time as _time
        cfg = {"t_center_drag": 0.0, "head_limit_points": []}
        t = make_tracker(cfg)
        now = _time.time()
        for i in range(20):
            t._hist.append((now - 0.6 + i * 0.03, 20.0 + 0.1 * (i % 2), 5.0))
        s = t.window_stats()
        self.assertTrue(s["stable"], s)
        self.assertAlmostEqual(s["mean_yaw"], 20.05, delta=0.06)
        t._hist.clear()
        for i in range(20):
            t._hist.append((now - 0.6 + i * 0.03, 20.0 + 6.0 * (i % 2), 5.0))
        self.assertFalse(t.window_stats()["stable"])
        # Sin muestras recientes (cara perdida) tampoco es estable.
        t._hist.clear()
        for i in range(20):
            t._hist.append((now - 1.0 + i * 0.03, 20.0, 5.0))
        self.assertFalse(t.window_stats()["stable"])


# ---------------- GUI (lógica de la pestaña Botones, sin Tk) ----------------
def import_gui(rich=True):
    """Importa gui_app sobre el tkinter falso (tests/stubs/faketk.py), con los
    módulos reales de frontend. Se reimporta desde cero cada vez, para que
    ningún test herede un módulo construido sobre otro tk falso.

    El parámetro `rich` se conserva por compatibilidad: ya no hay modo
    liviano, porque reemplazar frontend.* por módulos vacíos dejaría a los
    tests probando reemplazos en cuanto esos módulos se muevan.
    """
    import faketk
    tk = faketk.build()

    # Combobox con estado observable: lo usan los tests de fuente de cabeza.
    class Combobox(faketk.TextValue):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.state = kw.get("state")
        def config(self, cnf=None, **kw):
            super().config(cnf, **kw)
            self.state = kw.get("state", self.state)
    tk.ttk.Combobox = Combobox
    sys.modules["tkinter.ttk"].Combobox = Combobox

    for name in list(sys.modules):
        if name == "gui_app" or name.startswith("frontend"):
            sys.modules.pop(name, None)
    import gui_app
    return gui_app


class FakeLabel:
    def __init__(self): self.text = ""
    def config(self, **kw): self.text = kw.get("text", self.text)


class FakeSlider:
    def __init__(self): self.enabled = None
    def set_enabled(self, v): self.enabled = v


class FakeButton:
    def __init__(self): self.state = None
    def config(self, **kw): self.state = kw.get("state", self.state)


def gui_modules():
    """Importa los módulos de la GUI sobre el tkinter falso."""
    import_gui()
    import importlib
    return {name: importlib.import_module(name) for name in (
        "frontend.app.context", "frontend.tabs.buttons.capture",
        "frontend.tabs.tracker.source", "frontend.tabs.tracker.translation",
        "frontend.tabs.tracker.wizards", "frontend.components.axis_bars",
        "frontend.components.calibration_wizard",
    )}


class TestButtonCapture(unittest.TestCase):
    """La captura de teclas ya no necesita ventana: se prueba directo."""

    @classmethod
    def setUpClass(cls):
        cls.mod = gui_modules()["frontend.tabs.buttons.capture"]

    def make(self):
        c = self.mod.ButtonCapture()
        c.labels = {str(i): f"Botón {i}" for i in range(1, 17)}
        return c

    def test_capture_assigns_and_moves_duplicates(self):
        c = self.make()
        c.capture_id, c.capture_started = "1", 100.0
        c.handle_raw_key(ecodes.KEY_1, 1, 101.0)
        self.assertEqual(c.button_map, {"1": ecodes.KEY_1})
        self.assertIsNone(c.capture_id)
        c.capture_id, c.capture_started = "2", 200.0
        ok, msg = c.handle_raw_key(ecodes.KEY_1, 1, 201.0)
        self.assertEqual(c.button_map, {"2": ecodes.KEY_1})
        self.assertIn("se movió", msg)

    def test_reserved_and_escape(self):
        c = self.make()
        c.capture_id, c.capture_started = "3", 0.0
        c.handle_raw_key(ecodes.KEY_CAPSLOCK, 1, 1.0)
        self.assertEqual(c.button_map, {})
        self.assertEqual(c.capture_id, "3")    # sigue escuchando
        c.handle_raw_key(ecodes.KEY_ESC, 1, 2.0)
        self.assertIsNone(c.capture_id)
        self.assertEqual(c.button_map, {})

    def test_shortcut_warning_and_mouse_button(self):
        c = self.make()
        c.capture_id = "4"
        _, msg = c.handle_raw_key(ecodes.KEY_P, 1, 1.0)
        self.assertIn("atajo", msg)
        c.capture_id = "1"
        c.handle_raw_key(ecodes.BTN_LEFT, 1, 2.0)
        self.assertEqual(c.button_map["1"], ecodes.BTN_LEFT)
        self.assertEqual(code_name(ecodes.BTN_LEFT, ecodes), "BTN_LEFT")

    def test_stale_events_ignored_on_capture_start(self):
        c = self.make()
        # El clic sobre «Asignar» ya estaba en cola: al empezar la captura se descarta.
        c.queue.put((ecodes.BTN_LEFT, 1, 1.0))
        c.queue.put((ecodes.BTN_LEFT, 0, 1.05))
        c.start("1", 2.0)
        self.assertTrue(c.queue.empty())
        c.handle_raw_key(ecodes.BTN_LEFT, 1, 1.9)     # anterior al inicio
        self.assertEqual(c.button_map, {})
        c.handle_raw_key(ecodes.BTN_RIGHT, 1, 2.1)
        self.assertEqual(c.button_map, {"1": ecodes.BTN_RIGHT})

    def test_release_does_not_assign_and_tracks_state(self):
        c = self.make()
        c.capture_id = "5"
        self.assertIsNone(c.handle_raw_key(ecodes.KEY_1, 0, 1.0))
        self.assertEqual(c.button_map, {})
        c.capture_id = None
        c.handle_raw_key(57, 1, 1.0)
        self.assertIn(57, c.physical_down)
        c.handle_raw_key(57, 0, 1.1)
        self.assertNotIn(57, c.physical_down)

    def test_drain_reports_the_last_result(self):
        c = self.make()
        c.capture_id, c.capture_started = "1", 0.0
        c.queue.put((ecodes.KEY_CAPSLOCK, 1, 1.0))   # rechazada
        c.queue.put((ecodes.KEY_1, 1, 2.0))          # aceptada
        changed, (ok, msg) = c.drain()
        self.assertTrue(changed)
        self.assertTrue(ok)
        self.assertIn("KEY_1", msg)


class TestHeadSource(unittest.TestCase):
    def test_external_does_not_open_camera(self):
        """Con fuente externa NO se construye HeadTracker: la cámara queda
        libre para OpenTrack."""
        called = []
        original = HeadTracker.__init__

        def spy(self, *a, **kw):
            called.append(kw)
            self.running = False

        HeadTracker.__init__ = spy
        try:
            self.assertIsNone(create_head_source({"head_source": "external"}))
            self.assertEqual(called, [])
            self.assertIsNotNone(create_head_source({"head_source": "internal"}))
            self.assertEqual(len(called), 1)
            # Sin la clave, se mantiene el comportamiento anterior.
            self.assertIsNotNone(create_head_source({}))
            self.assertEqual(len(called), 2)
        finally:
            HeadTracker.__init__ = original


class TestGuiHeadSource(unittest.TestCase):
    """Selector de fuente de cabeza: cámara propia u OpenTrack."""

    @classmethod
    def setUpClass(cls):
        mods = gui_modules()
        cls.ctx_mod = mods["frontend.app.context"]
        cls.source = mods["frontend.tabs.tracker.source"]

    def make(self, mode="internal"):
        ctx = self.ctx_mod.AppContext(root=None, config={"head_source": mode})
        ctx.started, ctx.stopped = [], []
        ctx.start_head_source = lambda: ctx.started.append(1)
        ctx.stop_head_source = lambda: ctx.stopped.append(1)
        section = self.source.HeadSourceSection(ctx)
        section.note = FakeLabel()
        section.dimmable_widgets = [FakeSlider(), FakeSlider()]
        section.dimmable_buttons = [FakeButton()]
        return ctx, section

    def test_mode_falls_back_to_config(self):
        self.assertEqual(self.make("external")[1].mode(), "external")
        self.assertEqual(self.make()[1].mode(), "internal")

    def test_switch_to_external_stops_camera_and_dims_controls(self):
        ctx, s = self.make("internal")
        ctx.config["head_source"] = "external"
        s.on_change()
        self.assertEqual(ctx.stopped, [1])
        self.assertEqual(ctx.started, [])
        self.assertTrue(all(w.enabled is False for w in s.dimmable_widgets))
        self.assertEqual(s.dimmable_buttons[0].state, "disabled")
        self.assertIn("OpenTrack", s.note.text)

    def test_switch_to_internal_starts_camera_and_enables_controls(self):
        ctx, s = self.make("external")
        ctx.config["head_source"] = "internal"
        s.on_change()
        self.assertEqual(ctx.started, [1])
        self.assertEqual(ctx.stopped, [])
        self.assertTrue(all(w.enabled is True for w in s.dimmable_widgets))
        self.assertEqual(s.dimmable_buttons[0].state, "normal")

    def test_combobox_is_readonly_when_enabled(self):
        """Un Combobox habilitado no debe quedar editable."""
        ctx, s = self.make("internal")
        combo = sys.modules["tkinter.ttk"].Combobox()
        s.dimmable_buttons = [combo]
        s.refresh_state()
        self.assertEqual(combo.state, "readonly")
        ctx.config["head_source"] = "external"
        s.refresh_state()
        self.assertEqual(combo.state, "disabled")


class TestGuiTranslation(unittest.TestCase):
    """Estado de la calibración de traslación, descarte y tabla de pasos."""

    @classmethod
    def setUpClass(cls):
        mods = gui_modules()
        cls.ctx_mod = mods["frontend.app.context"]
        cls.tr = mods["frontend.tabs.tracker.translation"]
        cls.wiz = mods["frontend.tabs.tracker.wizards"]
        cls.bars = mods["frontend.components.axis_bars"]

    def status(self, limits):
        return self.tr.format_trans_calibration_status(limits)

    def make(self, limits):
        ctx = self.ctx_mod.AppContext(root=None, config={"head_trans_limits": limits})
        section = self.tr.TranslationSection(ctx)
        section.lbl_status = FakeLabel()
        return ctx, section

    def test_steps_cover_every_sense_once(self):
        steps = [s for s, _ in self.wiz.TRANSLATION_STEPS]
        self.assertEqual(len(steps), 6)
        self.assertEqual(set(steps), set(TRANS_STEPS))

    def test_status_uncalibrated(self):
        text = self.status({"units": TRANS_CALIB_UNITS})
        self.assertIn("Sin calibrar", text)
        self.assertIn("0/6", text)

    def test_status_partial_lists_what_is_missing(self):
        text = self.status({"units": TRANS_CALIB_UNITS, "x_pos": 8.0, "x_neg": 7.0})
        self.assertIn("2/6", text)
        self.assertIn("y_pos", text)
        self.assertNotIn("x_pos", text.split("faltan")[1])

    def test_status_complete(self):
        limits = {"units": TRANS_CALIB_UNITS}
        limits.update({k: 8.0 for k in TRANS_STEPS})
        self.assertIn("6/6", self.status(limits))

    def test_legacy_units_count_as_uncalibrated(self):
        limits = {"units": "px"}
        limits.update({k: 800.0 for k in TRANS_STEPS})
        self.assertIn("Sin calibrar", self.status(limits))

    def test_reset_clears_limits_and_keeps_units(self):
        limits = {"units": TRANS_CALIB_UNITS}
        limits.update({k: 8.0 for k in TRANS_STEPS})
        ctx, s = self.make(limits)
        s.reset()
        self.assertEqual(ctx.config["head_trans_limits"], {"units": TRANS_CALIB_UNITS})
        self.assertIn("Sin calibrar", s.lbl_status.text)

    def test_reset_also_clears_the_running_tracker(self):
        ctx, s = self.make({"units": TRANS_CALIB_UNITS, "x_pos": 8.0})
        ctx.tracker = SimpleNamespace(config={"head_trans_limits": {"units": TRANS_CALIB_UNITS,
                                                                   "x_pos": 8.0}})
        s.reset()
        self.assertEqual(ctx.tracker.config["head_trans_limits"], {"units": TRANS_CALIB_UNITS})

    def test_axis_bars_are_clamped(self):
        class FakeCanvas:
            def __init__(self): self.items = []; self.calls = {}
            def create_text(self, *a, **kw): pass
            def create_line(self, *a, **kw): pass
            def create_rectangle(self, *a, **kw):
                self.items.append(kw.get("fill")); return len(self.items)
            def coords(self, item, *args): self.calls[item] = args
        canvas = FakeCanvas()
        bars = self.bars.AxisBars(canvas, [("tx", "LAT", "c"), ("ty", "VER", "c"),
                                           ("tz", "PROF", "c"), ("roll", "ROLL", "c")],
                                  label_x=0, x0=50, x1=150, y0=0, row_step=10, font=None)
        bars.update({"tx": 2.0, "ty": -2.0, "tz": 0.5, "roll": 0.0})
        right = {k: canvas.calls[bars.bars[k][0]][2] for k in ("tx", "ty", "tz", "roll")}
        self.assertEqual(right["tx"], 150)   # tope derecho
        self.assertEqual(right["ty"], 50)    # tope izquierdo
        self.assertEqual(right["tz"], 125)
        self.assertEqual(right["roll"], 100)


class TestWizardController(unittest.TestCase):
    """La mecánica del asistente, sin ventana."""

    @classmethod
    def setUpClass(cls):
        cls.w = gui_modules()["frontend.components.calibration_wizard"]

    def make(self):
        return self.w.WizardController([("a", "A"), ("b", "B")], stable_spread=1.0,
                                       timeout_s=6.0)

    def stats(self, stable=False, spread=float("inf"), n=10):
        return {"n": n, "spread": spread, "stable": stable}

    def test_counter_and_advance(self):
        c = self.make()
        self.assertEqual(c.counter_text(), "Paso 1 de 2")
        self.assertFalse(c.advance())
        self.assertEqual(c.counter_text(), "Paso 2 de 2")
        self.assertTrue(c.advance())
        self.assertTrue(c.finished)

    def test_stable_reading_ends_the_capture(self):
        c = self.make()
        c.begin_capture(now=0.0)
        self.assertEqual(c.poll(self.stats(), now=1.0), "waiting")
        self.assertTrue(c.capturing)
        self.assertEqual(c.poll(self.stats(stable=True), now=2.0), "stable")
        self.assertFalse(c.capturing)

    def test_timeout(self):
        c = self.make()
        c.begin_capture(now=0.0)
        self.assertEqual(c.poll(self.stats(), now=6.5), "timeout")
        self.assertFalse(c.capturing)

    def test_progress_bar(self):
        c = self.make()
        self.assertEqual(c.progress(self.stats(spread=float("inf"))), 0.0)
        self.assertEqual(c.progress(self.stats(spread=0.0)), 100.0)
        self.assertAlmostEqual(c.progress(self.stats(spread=1.5)), 50.0)
        # Sin muestras no hay estabilidad que medir.
        self.assertEqual(c.progress(self.stats(spread=0.0, n=0)), 0.0)

    def test_reject_messages(self):
        wiz = gui_modules()["frontend.tabs.tracker.wizards"]
        self.assertIn("centro", wiz.rotation_reject_message({"reason": "center"}))
        msg = wiz.rotation_reject_message({"reason": "direction", "angle": 90.0,
                                           "expected": 0.0})
        self.assertIn("90°", msg)
        self.assertIn("0°", msg)
        self.assertIn("cm", wiz.translation_reject_message({"reason": "center"}))
        inverted = wiz.translation_reject_message(
            {"reason": "axis", "expected_axis": 0, "dominant": 0})
        self.assertIn("al revés", inverted)
        wrong = wiz.translation_reject_message(
            {"reason": "axis", "expected_axis": 0, "dominant": 2})
        self.assertIn("profundidad", wrong)


class TestWizardCancel(unittest.TestCase):
    """La X (y Esc) cierran el asistente y descartan lo calibrado en él.

    Cada paso se guarda al instante en la configuración, así que sin
    descartar, una calibración a medio hacer quedaría como si fuera la
    buena. Y al revés: terminar los 6/8 pasos también cierra la ventana, y
    ahí el progreso NO se puede perder.
    """

    def launch(self):
        """La GUI real, con un tracker que sí sabe calibrar.

        En producción el tracker recibe el MISMO dict de configuración que
        la GUI (`create_head_source(ctx.config)`), así que el stub lo
        comparte igual: es donde un revert a medias se notaría.
        """
        import gui_snapshot
        from backend.tracker import HeadTracker

        class CalibTracker(gui_snapshot.FakeTracker):
            # Calibración de verdad (la de backend.tracker) sobre el stub,
            # con sus validadores: así los tests guardan exactamente lo que
            # guardaría el asistente en vuelo.
            calibrate_direction = HeadTracker.calibrate_direction
            calibrate_translation = HeadTracker.calibrate_translation
            direction_scales = HeadTracker.direction_scales
            # Estos dos son @staticmethod en HeadTracker: hay que volver a
            # envolverlos, o `self` se colaría como primer argumento.
            validate_calibration_point = staticmethod(HeadTracker.validate_calibration_point)
            validate_trans_calibration_point = staticmethod(
                HeadTracker.validate_trans_calibration_point)

            # Lectura «quieta» programable: el test la fija antes de marcar
            # cada paso, y así el asistente recorre su camino real.
            steady = None

            def window_stats(self, window_s=0.5):
                if self.steady is None:
                    return gui_snapshot.FakeTracker.window_stats(self, window_s)
                yaw, pitch = self.steady
                return {"n": 20, "span_s": 1.0, "mean_yaw": yaw, "mean_pitch": pitch,
                        "spread": 0.0, "stable": True}

            def trans_window_stats(self, window_s=0.5):
                if self.steady is None:
                    return gui_snapshot.FakeTracker.trans_window_stats(self, window_s)
                return {"n": 20, "span_s": 1.0, "mean": self.steady,
                        "spread": 0.0, "stable": True}

        ctx_holder = gui_snapshot.launched()
        tk, app = ctx_holder.__enter__()
        app.ctx.tracker = CalibTracker(app.ctx.config)
        return ctx_holder, tk, app

    @staticmethod
    def close_button(win):
        from frontend.components.calibration_wizard import CLOSE_TEXT
        import gui_snapshot
        return gui_snapshot.find_button(win, CLOSE_TEXT)

    @staticmethod
    def mark_step(win, tracker, steady):
        """Marca el paso actual como lo haría el usuario: fija la lectura
        quieta, pulsa «Marcar» y deja correr el lazo de lectura en vivo, que
        es quien detecta la estabilidad y guarda el paso."""
        import gui_snapshot
        from frontend.components.calibration_wizard import MARK_TEXT, RETRY_TEXT
        tracker.steady = steady
        btn = (gui_snapshot.find_button(win, MARK_TEXT)
               or gui_snapshot.find_button(win, RETRY_TEXT))
        assert btn is not None, "no encontré el botón «Marcar»"
        btn.invoke()
        win.run_pending_after(limit=1)

    # --- rotación (octágono) ---
    def test_x_discards_a_half_done_rotation_calibration(self):
        holder, tk, app = self.launch()
        try:
            before = [{"label": "up", "angle_deg": 270.0, "magnitude": 30.0, "units": "deg"}]
            app.ctx.config["head_limit_points"] = list(before)

            win = app.tracker_tab.rotation.open_wizard()
            self.assertIsNotNone(win, "el asistente no se abrió")

            # Un paso marcado: queda guardado al instante.
            app.ctx.tracker.calibrate_direction("right", 35.0, 0.0)
            app.ctx.config["head_limit_points"] = list(
                app.ctx.tracker.config["head_limit_points"])
            self.assertEqual(len(app.ctx.config["head_limit_points"]), 2)

            self.close_button(win).invoke()

            self.assertEqual(app.ctx.config["head_limit_points"], before)
            self.assertEqual(app.ctx.tracker.config["head_limit_points"], before)
            self.assertFalse(win.winfo_exists(), "la ventana sigue abierta")
        finally:
            holder.__exit__(None, None, None)

    def test_finishing_every_step_keeps_the_rotation_calibration(self):
        """Terminar los 8 pasos cierra la ventana Y guarda: pasa por el mismo
        `close()` que la X, así que si se descartara siempre, se perdería una
        calibración completa."""
        holder, tk, app = self.launch()
        try:
            from frontend.tabs.tracker.wizards import ROTATION_STEPS
            from backend.tracker import EXPECTED_ANGLES
            app.ctx.config["head_limit_points"] = []
            shown = {}
            tk.messagebox.showinfo = lambda title, msg, **kw: shown.update(msg=msg)

            win = app.tracker_tab.rotation.open_wizard()
            for label, _ in ROTATION_STEPS:
                angle = math.radians(EXPECTED_ANGLES[label])
                self.mark_step(win, app.ctx.tracker,
                               (30.0 * math.cos(angle), 30.0 * math.sin(angle)))

            self.assertIn("8 direcciones", shown.get("msg", ""), "no terminó el asistente")
            self.assertFalse(win.winfo_exists(), "la ventana no se cerró al terminar")
            points = app.ctx.config["head_limit_points"]
            self.assertEqual(len(points), len(ROTATION_STEPS))
            self.assertEqual({p["label"] for p in points},
                             {label for label, _ in ROTATION_STEPS})
        finally:
            holder.__exit__(None, None, None)

    # --- traslación (6 sentidos) ---
    def test_x_discards_a_half_done_translation_calibration(self):
        holder, tk, app = self.launch()
        try:
            before = {"units": TRANS_CALIB_UNITS, "x_pos": 9.0}
            app.ctx.config["head_trans_limits"] = dict(before)

            win = app.tracker_tab.translation.open_wizard()
            self.assertIsNotNone(win)

            app.ctx.tracker.calibrate_translation("y_neg", (0.2, -6.0, 0.3))
            app.ctx.config["head_trans_limits"] = dict(
                app.ctx.tracker.config["head_trans_limits"])
            self.assertIn("y_neg", app.ctx.config["head_trans_limits"])

            self.close_button(win).invoke()

            self.assertEqual(app.ctx.config["head_trans_limits"], before)
            self.assertEqual(app.ctx.tracker.config["head_trans_limits"], before)
        finally:
            holder.__exit__(None, None, None)

    def test_finishing_every_step_keeps_the_translation_calibration(self):
        holder, tk, app = self.launch()
        try:
            from frontend.tabs.tracker.wizards import TRANSLATION_STEPS
            from backend.tracker import TRANS_STEPS as SPECS
            app.ctx.config["head_trans_limits"] = {"units": TRANS_CALIB_UNITS}
            shown = {}
            tk.messagebox.showinfo = lambda title, msg, **kw: shown.update(msg=msg)

            win = app.tracker_tab.translation.open_wizard()
            for step, _ in TRANSLATION_STEPS:
                axis, sign = SPECS[step]
                mean = [0.0, 0.0, 0.0]
                mean[axis] = 8.0 * sign
                self.mark_step(win, app.ctx.tracker, tuple(mean))

            self.assertIn("6 sentidos", shown.get("msg", ""), "no terminó el asistente")
            self.assertFalse(win.winfo_exists())
            limits = app.ctx.config["head_trans_limits"]
            for step, _ in TRANSLATION_STEPS:
                self.assertAlmostEqual(limits[step], 8.0, places=6, msg=step)
        finally:
            holder.__exit__(None, None, None)

    def test_x_after_marking_real_steps_discards_them(self):
        """Lo mismo que arriba pero cerrando a mitad: los pasos marcados de
        verdad por el asistente se descartan."""
        holder, tk, app = self.launch()
        try:
            before = {"units": TRANS_CALIB_UNITS, "z_neg": 5.0}
            app.ctx.config["head_trans_limits"] = dict(before)
            win = app.tracker_tab.translation.open_wizard()

            self.mark_step(win, app.ctx.tracker, (8.0, 0.0, 0.0))    # x_pos
            self.mark_step(win, app.ctx.tracker, (-7.0, 0.0, 0.0))   # x_neg
            self.assertIn("x_pos", app.ctx.config["head_trans_limits"])

            self.close_button(win).invoke()
            self.assertEqual(app.ctx.config["head_trans_limits"], before)
            self.assertEqual(app.ctx.tracker.config["head_trans_limits"], before)
        finally:
            holder.__exit__(None, None, None)

    def test_status_label_goes_back_after_cancelling(self):
        """El texto de estado de la pestaña también vuelve atrás: si no, diría
        que hay 2/6 sentidos calibrados cuando ya no los hay."""
        holder, tk, app = self.launch()
        try:
            app.ctx.config["head_trans_limits"] = {"units": TRANS_CALIB_UNITS}
            section = app.tracker_tab.translation
            section.refresh_status()
            self.assertIn("Sin calibrar", section.lbl_status.kw["text"])

            win = section.open_wizard()
            app.ctx.tracker.calibrate_translation("x_pos", (8.0, 0.1, 0.2))
            section.refresh_status()      # como hace on_saved
            self.close_button(win).invoke()

            self.assertIn("Sin calibrar", section.lbl_status.kw["text"])
        finally:
            holder.__exit__(None, None, None)

    # --- la salida existe y está atada ---
    def test_both_wizards_have_a_close_button_with_help(self):
        holder, tk, app = self.launch()
        try:
            for opener in (app.tracker_tab.rotation.open_wizard,
                           app.tracker_tab.translation.open_wizard):
                win = opener()
                btn = self.close_button(win)
                self.assertIsNotNone(btn, "falta el botón de cerrar")
                import gui_snapshot
                self.assertIn("descarta", (gui_snapshot.tooltip_text(btn) or "").lower())
                win.close(discard=True)
        finally:
            holder.__exit__(None, None, None)

    def test_escape_and_window_manager_close_also_discard(self):
        holder, tk, app = self.launch()
        try:
            before = {"units": TRANS_CALIB_UNITS}
            for sequence in ("<Escape>", "WM_DELETE_WINDOW"):
                app.ctx.config["head_trans_limits"] = dict(before)
                win = app.tracker_tab.translation.open_wizard()
                app.ctx.tracker.calibrate_translation("z_pos", (0.1, 0.2, 7.0))
                app.ctx.config["head_trans_limits"] = dict(
                    app.ctx.tracker.config["head_trans_limits"])

                if sequence == "<Escape>":
                    handler = next(cb for seq, cb in win.bindings if seq == "<Escape>")
                    handler(None)
                else:
                    win.protocol_handlers[sequence]()

                self.assertEqual(app.ctx.config["head_trans_limits"], before,
                                 f"{sequence} no descartó el progreso")
                self.assertFalse(win.winfo_exists())
        finally:
            holder.__exit__(None, None, None)

    def test_cancelling_stops_the_live_reading_loop(self):
        """Al cerrar hay que cancelar el `after` de la lectura en vivo: si no,
        sigue corriendo contra una ventana destruida."""
        holder, tk, app = self.launch()
        try:
            win = app.tracker_tab.translation.open_wizard()
            self.assertTrue(win.cancelled_after == [] and win.after_ids,
                            "el asistente no programó la lectura en vivo")
            self.close_button(win).invoke()
            self.assertTrue(win.cancelled_after, "no se canceló el after al cerrar")
        finally:
            holder.__exit__(None, None, None)


class TestGuiSnapshot(unittest.TestCase):
    """La GUI completa (ventana, asistentes, diálogo de ejes, tooltip y HUD)
    tiene que ser idéntica al golden. Es la red de seguridad del refactor:
    cualquier cambio visible hace fallar este test, con la ruta exacta del
    widget que cambió. Si el cambio es a propósito, se regenera con
        uv run python tests/gui_snapshot.py --update
    """

    def test_gui_matches_golden(self):
        import json
        import gui_snapshot
        with open(gui_snapshot.GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        snap = json.loads(json.dumps(gui_snapshot.take(), ensure_ascii=False))
        problems = gui_snapshot.diff(golden, snap)
        self.assertEqual(problems, [], "la GUI cambió:\n" + "\n".join(problems))


class TestGuiIntegration(unittest.TestCase):
    """La GUI completa construida sobre el tkinter falso: el contrato de las
    pestañas, el puente de configuración y el camino de los perfiles."""

    NEW_PREFIXES = ("t_trans_", "t_neck_", "t_sens_roll", "t_roll_",
                    "head_roll_", "head_trans_")

    def test_every_key_has_exactly_one_owner(self):
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            owners = app.bridge.owners()
            config_keys = set(app.bridge.read_config())
        duplicated = {k: v for k, v in owners.items() if len(v) > 1}
        self.assertEqual(duplicated, {}, "claves con más de un dueño")
        self.assertEqual(len(owners), 43)
        # Lo que se lee es exactamente lo que se declara (salvo las rutas
        # físicas, que solo se escriben si hay un dispositivo elegido).
        self.assertEqual(set(owners) - config_keys, {"mouse_phys", "keyboard_phys"})

    def test_every_key_round_trips_through_the_widgets(self):
        """Cargar un perfil y volver a leerlo devuelve exactamente lo cargado,
        para las 43 claves de las 4 pestañas."""
        import gui_snapshot
        profile = gui_snapshot.fixed_config()
        # Valores distintos de los por defecto, para que un error se note.
        profile.update({
            "radius": 410, "outer": 35, "curve": 2.2, "deadzone": 0.12, "snap": 0.07,
            "t_sens_x": 22.5, "t_sens_y": 18.0, "t_min_cutoff": 1.7, "t_beta": 0.09,
            "t_center_drag": 0.004, "t_deadzone": 0.03, "t_snap_axis": 0.35,
            "t_snap_outer": 0.2, "cam_rotation": 180,
            "t_trans_sens_x": 12.0, "t_trans_sens_y": 14.0, "t_trans_sens_z": 16.0,
            "t_trans_deadzone_x": 0.05, "t_trans_deadzone_y": 0.04,
            "t_trans_deadzone_z": 0.09, "t_trans_curve_x": 1.2, "t_trans_curve_y": 2.0,
            "t_trans_curve_z": 2.5, "t_trans_invert_x": True, "t_trans_invert_y": False,
            "t_trans_invert_z": True, "t_trans_min_cutoff": 1.1, "t_trans_beta": 0.03,
            "t_trans_min_cutoff_z": 0.6, "t_trans_beta_z": 0.02,
            "t_neck_height_cm": 8.5, "t_neck_depth_cm": 11.0,
            "t_sens_roll": 13.0, "t_roll_deadzone": 0.05, "head_roll_limit_deg": 25.0,
            "telemetry_enabled": True, "button_map": {"1": 30, "5": 272},
        })
        with gui_snapshot.launched() as (tk, app):
            app.bridge.apply_config(dict(profile))
            back = app.bridge.read_config()
        for key, value in profile.items():
            if key in ("mouse_phys", "keyboard_phys", "head_source", "controller_profile"):
                continue
            self.assertIn(key, back, key)
            if isinstance(value, float):
                self.assertAlmostEqual(float(back[key]), value, places=6, msg=key)
            else:
                self.assertEqual(back[key], value, key)

    def test_saved_file_keeps_the_original_key_order(self):
        """Guardar desde la GUI no reordena config1.json."""
        import gui_snapshot
        from frontend.app.config_bridge import KEY_ORDER
        with gui_snapshot.launched() as (tk, app):
            keys = list(app.bridge.read_config())
        self.assertEqual(keys, [k for k in KEY_ORDER if k in keys])

    def test_invert_checkboxes_are_booleans(self):
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            cfg = app.bridge.read_config()
        for key in ("t_trans_invert_x", "t_trans_invert_y", "t_trans_invert_z"):
            self.assertIsInstance(cfg[key], bool)
        # 'y' arranca invertido: el eje vertical de la imagen crece hacia abajo.
        self.assertTrue(cfg["t_trans_invert_y"])

    def test_calibration_is_not_overwritten_by_widgets(self):
        import gui_snapshot
        limits = {"units": TRANS_CALIB_UNITS}
        limits.update({k: 7.5 for k in TRANS_STEPS})
        with gui_snapshot.launched() as (tk, app):
            app.ctx.config["head_trans_limits"] = limits
            self.assertEqual(app.bridge.read_config()["head_trans_limits"], limits)

    def test_tracker_controls_are_dimmed_in_external_mode(self):
        import gui_snapshot
        from backend.tracker import HEAD_SOURCES as SOURCES
        with gui_snapshot.launched() as (tk, app):
            section = app.tracker_tab.source
            section.combo.set(SOURCES["external"])
            section.on_change()
            self.assertIsNone(app.ctx.tracker)          # cámara liberada
            self.assertEqual(app.tracker_tab.translation.btn_calibrate.kw.get("state"),
                             "disabled")
            for chk in app.tracker_tab.translation.invert_checks:
                self.assertEqual(chk.kw.get("state"), "disabled")
            self.assertEqual(app.tracker_tab.camera.cb_rotation.kw.get("state"), "disabled")

    def test_controller_change_rebuilds_button_rows(self):
        """Elegir un mando en el combobox de Botones reconstruye sus filas.

        El selector vivía en Sistema y avisaba por evento (Fase 6, mudanza
        pendiente ya hecha); ahora Botones lee su propio combobox
        directamente, sin ningún evento de por medio."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            before = len(app.buttons_tab.rows)
            app.buttons_tab.rows = {}
            handler = next(cb for seq, cb in app.buttons_tab.cb_controller.bindings
                          if seq == "<<ComboboxSelected>>")
            handler(None)
            self.assertEqual(len(app.buttons_tab.rows), before)
            self.assertGreater(before, 0)

    def test_controller_selector_lives_in_buttons_not_system(self):
        """Fase 6, mudanza pendiente: el selector de mando se movió de
        Sistema a Botones. Sistema pierde la sección MANDO EMULADO."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            self.assertIsNotNone(app.buttons_tab.cb_controller)
            self.assertFalse(hasattr(app.system_tab, 'cb_controller'))
            self.assertNotIn('controller_profile', app.system_tab.owned_keys)
            self.assertIn('controller_profile', app.buttons_tab.owned_keys)

    def test_loading_a_profile_applies_the_saved_controller(self):
        """Cargar un perfil sigue aplicando el mando guardado, ahora sobre
        el combobox de Botones en vez del de Sistema. El combobox se
        descoloca a propósito antes de cargar, para que el test note si
        `apply_config` dejara de seleccionarlo de nuevo (con un solo mando
        en el fixture, comparar `controller_id()` no lo notaría: cae al
        mismo valor por el `ctx.config` ya reemplazado)."""
        import gui_snapshot
        from utils.controllers import DEFAULT_CONTROLLER_ID
        with gui_snapshot.launched() as (tk, app):
            correct_name = app.buttons_tab.cb_controller.get()
            app.buttons_tab.cb_controller.set("(descolocado a propósito)")

            profile = gui_snapshot.fixed_config()
            profile['controller_profile'] = DEFAULT_CONTROLLER_ID
            app.bridge.apply_config(dict(profile))

            self.assertEqual(app.buttons_tab.cb_controller.get(), correct_name)
            self.assertEqual(app.buttons_tab.controller_id(), DEFAULT_CONTROLLER_ID)
            self.assertEqual(app.bridge.read_config()['controller_profile'],
                             DEFAULT_CONTROLLER_ID)


class TestStyleLint(unittest.TestCase):
    """Ningún color ni fuente literal fuera de frontend/style/. Es lo que
    evita que el refactor se deshaga con el tiempo."""

    SRC = os.path.join(HERE, "..", "src")
    # Archivos obsoletos que se conservan solo como reexportación.
    SKIP = {"theme.py", "widgets.py", "tooltips.py", "hud.py"}

    def files(self):
        base = os.path.join(self.SRC, "frontend")
        for root, _, names in os.walk(base):
            if os.path.normpath(root).endswith(os.path.join("frontend", "style")):
                continue
            for name in names:
                if not name.endswith(".py"):
                    continue
                if root == base and name in self.SKIP:
                    continue
                yield os.path.join(root, name)
        yield os.path.join(self.SRC, "gui_app.py")

    def test_no_color_literals(self):
        import re
        hexcolor = re.compile(r"['\"]#[0-9a-fA-F]{3,6}['\"]")
        # Colores por nombre, como argumento con nombre o posicional.
        named = re.compile(r"['\"](white|black|red|gray|grey)['\"]")
        found = []
        for path in self.files():
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if hexcolor.search(line) or named.search(line):
                        found.append(f"{os.path.relpath(path, self.SRC)}:{i}: {line.strip()}")
        self.assertEqual(found, [], "\n".join(found))

    def test_no_font_literals(self):
        import re
        font = re.compile(r"\(['\"](Segoe UI|Arial|Consolas)['\"],\s*\d+")
        found = []
        for path in self.files():
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if font.search(line):
                        found.append(f"{os.path.relpath(path, self.SRC)}:{i}: {line.strip()}")
        self.assertEqual(found, [], "\n".join(found))

    def test_gui_app_is_a_thin_launcher(self):
        with open(os.path.join(self.SRC, "gui_app.py"), encoding="utf-8") as f:
            code = [l for l in f if l.strip() and not l.strip().startswith(("#", '"'))]
        self.assertLessEqual(len(code), 15)

    def test_no_frontend_file_over_300_lines(self):
        big = []
        for path in self.files():
            with open(path, encoding="utf-8") as f:
                n = sum(1 for _ in f)
            if n > 300:
                big.append(f"{os.path.relpath(path, self.SRC)}: {n}")
        self.assertEqual(big, [], "\n".join(big))


class TestMetrics(unittest.TestCase):
    """Fase D: las métricas que usan plot_session.py y compare_sessions.py."""

    @classmethod
    def setUpClass(cls):
        from experiments import metrics
        cls.m = metrics

    def test_rest_noise_on_a_flat_signal(self):
        r = self.m.rest_noise([0.5] * 50)
        self.assertEqual(r["std"], 0.0)
        self.assertEqual(r["p2p"], 0.0)
        self.assertEqual(r["jitter"], 0.0)

    def test_jitter_and_std_separate_tremor_from_drift(self):
        """Una deriva lenta y un temblor pueden tener la misma std, pero muy
        distinto jitter: el jitter es el que corresponde a lo que se ve."""
        n = 200
        drift = np.linspace(-1.0, 1.0, n)
        tremor = np.array([-1.0 if i % 2 else 1.0 for i in range(n)])
        self.assertAlmostEqual(self.m.rest_noise(drift)["std"],
                               self.m.rest_noise(tremor)["std"], delta=0.45)
        self.assertLess(self.m.rest_noise(drift)["jitter"],
                        self.m.rest_noise(tremor)["jitter"] / 100)

    def test_nan_cells_are_ignored(self):
        # Los frames sin detección dejan la celda vacía en el CSV.
        r = self.m.rest_noise([1.0, float("nan"), 1.0, float("nan")])
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["std"], 0.0)

    def test_empty_input(self):
        r = self.m.rest_noise([])
        self.assertEqual(r["n"], 0)
        self.assertTrue(math.isnan(r["std"]))

    def test_quietest_window_finds_the_quiet_part(self):
        # 10 s agitados, luego 6 s quietos.
        t = np.arange(0, 16, 0.02)
        v = np.where(t < 10, np.sin(t * 8), 0.0)
        w = self.m.quietest_window(t, v, window_s=5.0)
        self.assertGreater(w["start"], 9.5)
        self.assertLess(w["std"], 1e-9)

    def test_quietest_window_needs_enough_signal(self):
        t = np.arange(0, 2, 0.02)
        w = self.m.quietest_window(t, np.zeros_like(t), window_s=5.0)
        self.assertEqual(w["n"], 0)

    @staticmethod
    def _step(tau=0.25, fps=30, rest_s=2.0, total_s=14.0, sigma=0.0, seed=0):
        """Un escalón pasado por un filtro de primer orden, con reposo antes
        y ruido opcional: sube del 10 al 90 % en tau*ln(9)."""
        t = np.arange(0, total_s, 1 / fps)
        v = np.where(t < rest_s, 0.0, 1.0 - np.exp(-(t - rest_s) / tau))
        if sigma:
            v = np.clip(v + np.random.default_rng(seed).normal(0, sigma, t.size), -1, 1)
        return t, v

    def test_rise_time_matches_a_known_filter(self):
        """Si la medición no da tau*ln(9), la función está mal, no el filtro."""
        tau = 0.25
        t, v = self._step(tau=tau)
        times = self.m.rise_times(t, v, min_amplitude=0.3)
        self.assertEqual(len(times), 1)
        # +3 % de sesgo por el suavizado centrado, documentado en metrics.py.
        self.assertAlmostEqual(times[0], tau * math.log(9),
                               delta=0.05 * tau * math.log(9))

    def test_rise_time_survives_noise(self):
        """Sin suavizar antes de segmentar, el ruido en reposo parte la
        transición en tramos y el tiempo medido sale hasta un 40 % corto.
        Este test es el que fija ese arreglo."""
        tau = 0.25
        expected = tau * math.log(9)
        for sigma, tolerance in ((0.01, 0.10), (0.03, 0.20)):
            measured = []
            for seed in range(15):
                t, v = self._step(tau=tau, sigma=sigma, seed=seed)
                r = self.m.rise_times(t, v, min_amplitude=0.3)
                self.assertTrue(r, f"no detectó la transición con ruido {sigma}")
                measured.append(r[0])
            median = float(np.median(measured))
            self.assertAlmostEqual(median, expected, delta=tolerance * expected,
                                   msg=f"ruido {sigma}: mediana {median:.3f}s")

    def test_smoothing_is_centered_and_adds_no_lag(self):
        """Una ventana centrada no desplaza el flanco: es lo que permite
        medir tiempos sobre la señal suavizada."""
        v = np.concatenate([np.zeros(20), np.ones(20)])
        sm = self.m.smooth_centered(v, 5)
        # El cruce del 50 % sigue en el mismo sitio que en la señal cruda.
        self.assertAlmostEqual(float(np.argmax(sm >= 0.5)), 20.0, delta=1.0)
        # Y los extremos no inventan rampas.
        self.assertAlmostEqual(sm[0], 0.0, delta=1e-9)
        self.assertAlmostEqual(sm[-1], 1.0, delta=1e-9)

    def test_smoothing_is_a_noop_when_too_narrow(self):
        v = np.array([1.0, 5.0, 1.0])
        self.assertTrue(np.array_equal(self.m.smooth_centered(v, 1), v))

    def test_rise_time_ignores_small_wiggles(self):
        t = np.arange(0, 3, 0.01)
        v = 0.05 * np.sin(t * 5)
        self.assertEqual(self.m.rise_times(t, v, min_amplitude=0.3), [])

    def test_rise_time_handles_both_directions(self):
        tau = 0.25
        half = np.arange(0, 4, 1 / 30)
        up = 1.0 - np.exp(-half / tau)
        down = up[-1] * np.exp(-half / tau)
        t = np.arange(0, 8, 1 / 30)[:up.size + down.size]
        times = self.m.rise_times(t, np.concatenate([up, down]), min_amplitude=0.3)
        self.assertEqual(len(times), 2, times)
        for value in times:
            self.assertAlmostEqual(value, tau * math.log(9),
                                   delta=0.10 * tau * math.log(9))

    def test_correlation_edges(self):
        self.assertAlmostEqual(self.m.correlation([1, 2, 3], [2, 4, 6]), 1.0, delta=1e-9)
        self.assertAlmostEqual(self.m.correlation([1, 2, 3], [6, 4, 2]), -1.0, delta=1e-9)
        # Serie constante: no hay correlación definida, y no debe explotar.
        self.assertEqual(self.m.correlation([1, 1, 1], [1, 2, 3]), 0.0)
        self.assertEqual(self.m.correlation([1], [1]), 0.0)

    def test_neck_report_flags_a_bad_pivot(self):
        """Un pivote mal ajustado deja la traslación lateral pegada al yaw:
        es justo la firma que este informe tiene que delatar."""
        yaw = np.sin(np.arange(0, 10, 0.01))
        bad = self.m.neck_compensation_report(yaw, 0.4 * yaw, np.zeros_like(yaw),
                                              np.zeros_like(yaw))
        self.assertEqual(bad["worst_axis"], "lateral")
        self.assertGreater(bad["worst"], 0.99)

    def test_neck_report_passes_a_good_pivot(self):
        rng = np.random.default_rng(0)
        yaw = np.sin(np.arange(0, 10, 0.01))
        noise = rng.normal(0, 0.02, yaw.size)
        good = self.m.neck_compensation_report(yaw, noise, rng.normal(0, 0.02, yaw.size),
                                              rng.normal(0, 0.02, yaw.size))
        self.assertLess(good["worst"], 0.2)


class TestRecordAxes(unittest.TestCase):
    """Fase D: las partes puras del grabador de ejes. Lo que necesita un
    dispositivo real no se puede probar aquí, pero la normalización sí: sin
    ella, nuestros ±32767 y el rango de otro dispositivo no se comparan."""

    @classmethod
    def setUpClass(cls):
        from experiments import record_axes
        cls.r = record_axes

    def test_symmetric_range(self):
        n = self.r.normalize_abs
        self.assertAlmostEqual(n(32767, -32767, 32767), 1.0, delta=1e-9)
        self.assertAlmostEqual(n(-32767, -32767, 32767), -1.0, delta=1e-9)
        self.assertAlmostEqual(n(0, -32767, 32767), 0.0, delta=1e-9)

    def test_unsigned_range_is_centered(self):
        """Un eje de 0..255 tiene su centro en 127.5, no en 0."""
        n = self.r.normalize_abs
        self.assertAlmostEqual(n(255, 0, 255), 1.0, delta=1e-9)
        self.assertAlmostEqual(n(0, 0, 255), -1.0, delta=1e-9)
        self.assertAlmostEqual(n(127.5, 0, 255), 0.0, delta=1e-9)

    def test_out_of_range_is_clamped(self):
        n = self.r.normalize_abs
        self.assertEqual(n(99999, -32767, 32767), 1.0)
        self.assertEqual(n(-99999, -32767, 32767), -1.0)

    def test_degenerate_range_does_not_divide_by_zero(self):
        self.assertEqual(self.r.normalize_abs(5, 3, 3), 0.0)

    def test_pick_device_matches_case_insensitively(self):
        devices = [("/dev/input/event3", "Thrustmaster T.16000M (Rust Thread)"),
                   ("/dev/input/event4", "Virtual Head Tracker (Rust Thread)")]
        path, name = self.r.pick_device(devices, "virtual head")
        self.assertEqual(path, "/dev/input/event4")
        self.assertIn("Head", name)

    def test_pick_device_reports_what_is_available(self):
        devices = [("/dev/input/event3", "Teclado")]
        with self.assertRaises(SystemExit) as ctx:
            self.r.pick_device(devices, "opentrack")
        self.assertIn("Teclado", str(ctx.exception))

    def test_axis_names_cover_both_devices(self):
        """Los 6 ejes de cabeza y los 4 del stick tienen que tener nombre en
        el CSV, o las columnas saldrían como 'abs<código>'."""
        from evdev import ecodes
        for code in (ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_Z, ecodes.ABS_RX,
                     ecodes.ABS_RY, ecodes.ABS_RZ, ecodes.ABS_THROTTLE,
                     ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y):
            self.assertIn(code, self.r.AXIS_NAMES)


class TestHeadDeviceClassification(unittest.TestCase):
    """El dispositivo de cabeza tiene que ser un JOYSTICK para el sistema.

    En la Fase A se declaró sin botones: con ABS_X + ABS_Y + ABS_Z y sin
    teclas, udev (systemd) y SDL lo clasifican como acelerómetro y el juego
    no lo lista. Estos tests fijan la regla y comprueban el dispositivo tal
    como está declarado en device.rs."""

    DEVICE_RS = os.path.join(HERE, "..", "src", "backend", "motor_rust", "src", "device.rs")
    ABS_CODES = {"ABS_X": 0, "ABS_Y": 1, "ABS_Z": 2, "ABS_RX": 3, "ABS_RY": 4, "ABS_RZ": 5,
                 "ABS_THROTTLE": 6, "ABS_HAT0X": 16, "ABS_HAT0Y": 17}

    @classmethod
    def setUpClass(cls):
        from experiments import diagnose_input
        cls.d = diagnose_input

    def test_phase_a_head_device_was_an_accelerometer(self):
        """Reproduce el fallo: 6 ejes y ningún botón."""
        self.assertEqual(self.d.predict_udev_class([], [0, 1, 2, 3, 4, 5]), "accelerometer")

    def test_one_button_makes_it_a_joystick(self):
        self.assertEqual(self.d.predict_udev_class([0x120], [0, 1, 2, 3, 4, 5]), "joystick")

    def test_stick_device_is_a_joystick(self):
        buttons = list(range(0x120, 0x130))
        self.assertEqual(self.d.predict_udev_class(buttons, [0, 1, 5, 6, 16, 17]), "joystick")

    def test_other_shapes(self):
        p = self.d.predict_udev_class
        self.assertEqual(p([], [0, 1, 2]), "accelerometer")            # acelerómetro real
        self.assertEqual(p([], [5]), "joystick")                       # pedales: sin X/Y
        self.assertEqual(p([0x110, 0x111, 0x112], [0, 1]), "mouse")    # mouse absoluto (VM)
        self.assertEqual(p([0x120], [0, 1, 2], props=[0x06]), "accelerometer")

    def test_parse_udev_data(self):
        text = "I:123\nE:ID_INPUT=1\nE:ID_INPUT_ACCELEROMETER=1\nG:seat\n"
        props = self.d.parse_udev_data(text)
        self.assertEqual(props, {"ID_INPUT": "1", "ID_INPUT_ACCELEROMETER": "1"})
        self.assertEqual(self.d.udev_verdict(props), "accelerometer")
        self.assertEqual(self.d.udev_verdict({"ID_INPUT": "1", "ID_INPUT_JOYSTICK": "1"}),
                         "joystick")
        self.assertEqual(self.d.udev_verdict({}), "desconocido")

    def _head_device_shape(self):
        """Ejes y botones del dispositivo de cabeza, leídos de device.rs."""
        import re
        with open(self.DEVICE_RS, encoding="utf-8") as f:
            src = f.read()
        body = src[src.index("pub fn create_head_device"):]
        body = body[:body.index("builder.build()")]
        axes = [self.ABS_CODES[a] for a in re.findall(r"AbsoluteAxisCode::(ABS_\w+)", body)]
        const = src[src.index("pub const HEAD_BUTTON_CODES"):]
        const = const[:const.index("];")]
        buttons = [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", const.split("=", 1)[1])]
        declares_keys = "with_keys(&keys)" in body
        return axes, buttons, declares_keys

    def test_head_device_in_device_rs_is_a_joystick(self):
        axes, buttons, declares_keys = self._head_device_shape()
        self.assertEqual(sorted(axes), [0, 1, 2, 3, 4, 5])
        self.assertTrue(buttons, "el dispositivo de cabeza no declara botones")
        self.assertTrue(declares_keys, "create_head_device no registra sus botones")
        self.assertEqual(self.d.predict_udev_class(buttons, axes), "joystick")


class TestNeckCompensation(unittest.TestCase):
    """B2: girar la cabeza sin mover el cuerpo no debe trasladar la cámara."""

    H, D = 10.0, 10.0

    def face_matrix(self, yaw, pitch, pivot=(0.0, 0.0, 0.0)):
        """Matriz de una cabeza que gira sobre el cuello: la cara está a
        (0, H, D) del pivote en coordenadas de la cabeza, así que al girar
        se traslada aunque el pivote no se mueva."""
        M = rot(yaw, pitch)
        d = np.array([0.0, self.H, self.D])
        M[:3, 3] = np.asarray(pivot, dtype=float) + M[:3, :3] @ d
        return M

    def test_rotation_alone_does_not_translate(self):
        readings = []
        for yaw, pitch in [(0, 0), (30, 0), (-30, 0), (0, 25), (0, -25), (25, 20)]:
            R, t = matrix_parts(self.face_matrix(yaw, pitch))
            readings.append(compensate_neck(R, t, self.H, self.D))
        base = readings[0]
        for value in readings[1:]:
            # Con d bien ajustado, la lectura compensada no se mueve.
            self.assertLess(float(np.max(np.abs(value - base))), 1e-9)

    def test_uncompensated_rotation_does_translate(self):
        """Sin compensar, girar 30 grados sí desplaza la lectura: es el
        problema que B2 resuelve, y confirma que el test de arriba no pasa
        por casualidad."""
        _, t0 = matrix_parts(self.face_matrix(0, 0))
        _, t1 = matrix_parts(self.face_matrix(30, 0))
        self.assertGreater(float(np.max(np.abs(t1 - t0))), 1.0)

    def test_body_movement_survives(self):
        """Compensar no debe comerse el movimiento real del cuerpo."""
        R, t = matrix_parts(self.face_matrix(20, 0, pivot=(6.0, 0.0, 0.0)))
        comp = compensate_neck(R, t, self.H, self.D)
        R0, t0 = matrix_parts(self.face_matrix(20, 0))
        base = compensate_neck(R0, t0, self.H, self.D)
        self.assertAlmostEqual(float(comp[0] - base[0]), 6.0, delta=1e-9)

    def test_roll_is_extracted(self):
        yaw, pitch, roll = matrix_to_euler3(rot(0, 0))
        self.assertAlmostEqual(roll, 0.0, delta=1e-6)
        yaw2, pitch2 = matrix_to_euler(rot(15, 10))
        y3, p3, _ = matrix_to_euler3(rot(15, 10))
        self.assertAlmostEqual(yaw2, y3, delta=1e-9)
        self.assertAlmostEqual(pitch2, p3, delta=1e-9)


class TestTranslationOutput(unittest.TestCase):
    """B4: normalización por eje, ganancia, zona muerta y curva."""

    def cfg(self, **over):
        c = {
            "head_trans_limits": {
                "units": TRANS_CALIB_UNITS,
                "x_pos": 8.0, "x_neg": 4.0,
                "y_pos": 6.0, "y_neg": 6.0,
                "z_pos": 12.0, "z_neg": 12.0,
            },
            "t_trans_sens_x": 10.0, "t_trans_sens_y": 10.0, "t_trans_sens_z": 10.0,
            "t_trans_deadzone_x": 0.0, "t_trans_deadzone_y": 0.0, "t_trans_deadzone_z": 0.0,
            "t_trans_curve_x": 1.0, "t_trans_curve_y": 1.0, "t_trans_curve_z": 1.0,
            "t_trans_invert_x": False, "t_trans_invert_y": False, "t_trans_invert_z": False,
        }
        c.update(over)
        return c

    def out(self, rel, **over):
        return HeadTracker.compute_translation_output(rel, self.cfg(**over))

    def test_calibrated_limit_gives_full_output(self):
        tx, ty, tz = self.out((8.0, 6.0, 12.0))
        self.assertAlmostEqual(tx, 1.0, delta=1e-6)
        self.assertAlmostEqual(ty, 1.0, delta=1e-6)
        self.assertAlmostEqual(tz, 1.0, delta=1e-6)

    def test_each_sense_has_its_own_limit(self):
        # x_neg = 4 cm: a -4 cm ya está al tope, mientras x_pos = 8 cm.
        self.assertAlmostEqual(self.out((-4.0, 0, 0))[0], -1.0, delta=1e-6)
        self.assertAlmostEqual(self.out((4.0, 0, 0))[0], 0.5, delta=1e-6)

    def test_output_is_clamped(self):
        self.assertAlmostEqual(self.out((30.0, 0, 0))[0], 1.0, delta=1e-6)

    def test_gain_is_post_normalization(self):
        # 20 = salida completa a mitad del rango calibrado.
        self.assertAlmostEqual(self.out((4.0, 0, 0), t_trans_sens_x=20.0)[0], 1.0, delta=1e-6)

    def test_uncalibrated_axis_uses_default(self):
        c = self.cfg()
        c["head_trans_limits"] = {"units": TRANS_CALIB_UNITS}
        v = HeadTracker.compute_translation_output((DEFAULT_TRANS_LIMIT_CM, 0, 0), c)
        self.assertAlmostEqual(v[0], 1.0, delta=1e-6)

    def test_legacy_limits_are_ignored(self):
        self.assertEqual(valid_trans_limits({"x_pos": 5.0}), {})
        self.assertEqual(valid_trans_limits({"units": "px", "x_pos": 5.0}), {})
        self.assertEqual(valid_trans_limits({"units": TRANS_CALIB_UNITS, "x_pos": 5.0}),
                         {"x_pos": 5.0})

    def test_deadzone_is_rescaled_without_jump(self):
        # Justo en el borde de la zona muerta la salida es 0 y crece desde
        # ahí: no hay salto al 0.2 como habría sin reescalar.
        just_inside = self.out((8.0 * 0.20, 0, 0), t_trans_deadzone_x=0.20)[0]
        self.assertAlmostEqual(just_inside, 0.0, delta=1e-6)
        half = self.out((8.0 * 0.60, 0, 0), t_trans_deadzone_x=0.20)[0]
        self.assertAlmostEqual(half, 0.5, delta=1e-6)
        # Y el tope se sigue alcanzando.
        self.assertAlmostEqual(self.out((8.0, 0, 0), t_trans_deadzone_x=0.20)[0], 1.0, delta=1e-6)

    def test_curve_keeps_ends(self):
        c = self.out((8.0 * 0.5, 0, 0), t_trans_curve_x=2.0)[0]
        self.assertAlmostEqual(c, 0.25, delta=1e-6)
        self.assertAlmostEqual(self.out((8.0, 0, 0), t_trans_curve_x=2.0)[0], 1.0, delta=1e-6)
        self.assertAlmostEqual(self.out((0.0, 0, 0), t_trans_curve_x=2.0)[0], 0.0, delta=1e-9)

    def test_invert_flips_sense(self):
        self.assertAlmostEqual(self.out((8.0, 0, 0), t_trans_invert_x=True)[0], -1.0, delta=1e-6)

    def test_deadzone_covers_noise_below_its_threshold(self):
        """La zona muerta anula exactamente el ruido por debajo de
        dz * rango_calibrado, y nada más.

        Cuánta zona muerta hace falta depende del ruido real de la cámara,
        así que el valor se ajusta desde la GUI; lo que se comprueba aquí
        es la propiedad, no un número concreto. Con los valores por defecto
        (3 % lateral/vertical, 6 % profundidad) el margen es de 1.8 mm en
        un rango de 6 cm y 7.2 mm en uno de 12 cm.
        """
        dz = {"x": 0.03, "y": 0.03, "z": 0.06}
        limits = {"x": 8.0, "y": 6.0, "z": 12.0}
        over = {f"t_trans_deadzone_{k}": v for k, v in dz.items()}
        for i, name in enumerate(("x", "y", "z")):
            margin = dz[name] * limits[name]
            for factor, expect_zero in ((0.5, True), (0.99, True), (1.5, False)):
                rel = [0.0, 0.0, 0.0]
                rel[i] = margin * factor
                value = self.out(tuple(rel), **over)[i]
                if expect_zero:
                    self.assertEqual(value, 0.0, f"{name} a {factor}x del margen")
                else:
                    self.assertGreater(value, 0.0, f"{name} a {factor}x del margen")


class TestTranslationCalibration(unittest.TestCase):
    """B4: validación de los pasos del asistente."""

    def test_dominant_axis_is_required(self):
        # Se pide inclinarse a la derecha pero lo que más cambia es la
        # profundidad: se rechaza.
        r = HeadTracker.validate_trans_calibration_point("x_pos", (3.0, 0.0, 9.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "axis")

    def test_good_reading_is_accepted(self):
        r = HeadTracker.validate_trans_calibration_point("x_pos", (7.0, 0.5, 1.0))
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["magnitude"], 7.0)

    def test_center_is_rejected(self):
        r = HeadTracker.validate_trans_calibration_point("z_neg", (0.1, 0.1, -0.5))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "center")

    def test_wrong_sense_is_rejected(self):
        r = HeadTracker.validate_trans_calibration_point("x_pos", (-7.0, 0.5, 1.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "axis")

    def test_unknown_step(self):
        self.assertEqual(
            HeadTracker.validate_trans_calibration_point("nope", (7.0, 0, 0))["reason"], "step")

    def test_calibrate_stores_magnitude_with_units(self):
        t = make_tracker({"head_trans_limits": {"units": TRANS_CALIB_UNITS}})
        r = t.calibrate_translation("y_neg", (0.5, -6.5, 0.4))
        self.assertTrue(r["ok"])
        limits = t.config["head_trans_limits"]
        self.assertEqual(limits["units"], TRANS_CALIB_UNITS)
        self.assertAlmostEqual(limits["y_neg"], 6.5)

    def test_calibrate_discards_other_units(self):
        t = make_tracker({"head_trans_limits": {"units": "px", "x_pos": 999.0}})
        t.calibrate_translation("x_pos", (7.0, 0.0, 0.0))
        self.assertAlmostEqual(t.config["head_trans_limits"]["x_pos"], 7.0)

    def test_rejected_reading_is_not_stored(self):
        t = make_tracker({"head_trans_limits": {"units": TRANS_CALIB_UNITS}})
        t.calibrate_translation("x_pos", (0.1, 0.0, 0.0))
        self.assertNotIn("x_pos", t.config["head_trans_limits"])

    def test_all_six_steps_exist(self):
        self.assertEqual(len(TRANS_STEPS), 6)


class TestTranslationEndToEnd(unittest.TestCase):
    """Criterios de aceptación de la Fase B, sobre el lazo completo
    (_process_detection): compensación + filtro + normalización."""

    H, D = 10.0, 10.0

    def cfg(self):
        return {
            "t_sens_x": 10.0, "t_sens_y": 10.0, "t_min_cutoff": 1.0, "t_beta": 0.05,
            "t_center_drag": 0.0, "head_limit_points": [],
            "t_neck_height_cm": self.H, "t_neck_depth_cm": self.D,
            "head_trans_limits": {
                "units": TRANS_CALIB_UNITS,
                "x_pos": 8.0, "x_neg": 8.0, "y_pos": 8.0, "y_neg": 8.0,
                "z_pos": 8.0, "z_neg": 8.0,
            },
            "t_trans_sens_x": 10.0, "t_trans_sens_y": 10.0, "t_trans_sens_z": 10.0,
            "t_trans_deadzone_x": 0.0, "t_trans_deadzone_y": 0.0, "t_trans_deadzone_z": 0.0,
            "t_trans_curve_x": 1.0, "t_trans_curve_y": 1.0, "t_trans_curve_z": 1.0,
            "t_trans_invert_x": False, "t_trans_invert_y": False, "t_trans_invert_z": False,
            "head_roll_limit_deg": 30.0, "t_sens_roll": 10.0, "t_roll_deadzone": 0.0,
        }

    def feed_head(self, t, yaw, pitch, t0, seconds, pivot=(0.0, 0.0, 0.0), fps=30):
        n = int(seconds * fps)
        for i in range(n):
            M = rot(yaw, pitch)
            M[:3, 3] = np.asarray(pivot, dtype=float) + M[:3, :3] @ np.array([0.0, self.H, self.D])
            t._process_detection(t0 + i / fps, LM, M, 640, 480, None)
        return t0 + n / fps

    def test_turning_head_barely_moves_translation(self):
        """Girar la cabeza sin mover el cuerpo deja la traslación por debajo
        del 10 % de su recorrido."""
        t = make_tracker(self.cfg())
        now = self.feed_head(t, 0, 0, 0.0, 0.5)
        now = self.feed_head(t, 30, 0, now, 1.0)
        _, _, _, tx, ty, tz = t.get_head_axes()
        for name, value in (("tx", tx), ("ty", ty), ("tz", tz)):
            self.assertLess(abs(value), 0.10, f"{name} = {value}")

    def test_leaning_to_the_limit_gives_full_output(self):
        """Inclinarse hasta el límite calibrado da salida completa."""
        t = make_tracker(self.cfg())
        now = self.feed_head(t, 0, 0, 0.0, 0.5)
        now = self.feed_head(t, 0, 0, now, 2.0, pivot=(8.0, 0.0, 0.0))
        tx = t.get_head_axes()[3]
        self.assertGreater(tx, 0.9, tx)

    def test_recenter_zeroes_translation(self):
        t = make_tracker(self.cfg())
        now = self.feed_head(t, 0, 0, 0.0, 0.5)
        now = self.feed_head(t, 0, 0, now, 1.0, pivot=(5.0, 0.0, 0.0))
        self.assertGreater(t.get_head_axes()[3], 0.3)
        t.recenter()
        self.feed_head(t, 0, 0, now, 1 / 30, pivot=(5.0, 0.0, 0.0))
        self.assertEqual(t.get_head_axes()[3:], (0.0, 0.0, 0.0))

    def test_head_axes_order_matches_the_device(self):
        """El orden es (yaw, pitch, roll, tx, ty, tz): los tres primeros
        son los mismos que get_axes() sigue entregando."""
        t = make_tracker(self.cfg())
        now = self.feed_head(t, 0, 0, 0.0, 0.5)
        self.feed_head(t, 20, 10, now, 1.0)
        axes = t.get_head_axes()
        self.assertEqual(len(axes), 6)
        self.assertEqual(axes[:2], t.get_axes())

    def test_not_running_gives_six_zeros(self):
        t = make_tracker(self.cfg())
        t.running = False
        self.assertEqual(t.get_head_axes(), (0.0,) * 6)


class TestRollOutput(unittest.TestCase):
    def test_limit_gives_full_output(self):
        cfg = {"head_roll_limit_deg": 30.0, "t_sens_roll": 10.0, "t_roll_deadzone": 0.0}
        self.assertAlmostEqual(HeadTracker.compute_roll_output(30.0, cfg), 1.0, delta=1e-6)
        self.assertAlmostEqual(HeadTracker.compute_roll_output(-30.0, cfg), -1.0, delta=1e-6)
        self.assertAlmostEqual(HeadTracker.compute_roll_output(60.0, cfg), 1.0, delta=1e-6)

    def test_deadzone(self):
        cfg = {"head_roll_limit_deg": 30.0, "t_sens_roll": 10.0, "t_roll_deadzone": 0.1}
        self.assertEqual(HeadTracker.compute_roll_output(2.0, cfg), 0.0)


class TestCameraViewGeometry(unittest.TestCase):
    """Fase 1 de docs/plan_vista_camara.md: las funciones puras de
    `frontend.camera_view.geometry`, sin cv2 ni cámara."""

    IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    # Yaw de 90 grados sobre el eje vertical: la columna X pasa a ser -Z.
    YAW90 = [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]

    @staticmethod
    def face(x, y, w=128, h=153):
        """Una caja de cara del tamaño que mide una real a ~60 cm."""
        return (x, y, w, h)

    # --- círculo de distancia -------------------------------------------
    def test_radius_grows_when_landmarks_separate(self):
        """El círculo de distancia crece cuando la cara ocupa más frame
        (se acerca a la cámara), y con eso alcanza para el indicador."""
        close = [(50, 50), (60, 50), (55, 60), (55, 40)]
        far = [(50, 50), (56, 50), (53, 56), (53, 44)]
        _, _, r_close = camera_geometry.enclosing_circle(close)
        _, _, r_far = camera_geometry.enclosing_circle(far)
        self.assertGreater(r_close, r_far)

    def test_enclosing_circle_contains_every_point(self):
        pts = [(10, 10), (90, 15), (40, 80), (5, 60)]
        cx, cy, r = camera_geometry.enclosing_circle(pts)
        for x, y in pts:
            self.assertLessEqual(math.hypot(x - cx, y - cy), r + 1e-9)

    # --- cuadrado de encuadre: estático ----------------------------------
    def test_framing_box_is_wider_than_tall_and_holds_the_face(self):
        """Apaisado a propósito: la cara es más alta que ancha, así que
        con márgenes iguales salía un cuadrado desproporcionado."""
        box = camera_geometry.framing_box(None, self.face(250, 150), 640, 480)
        self.assertGreater(box[2], box[3])
        self.assertTrue(camera_geometry.box_contains(box, self.face(250, 150)))

    def test_framing_box_is_smaller_than_the_old_square(self):
        """No debe volver a crecer: el cuadrado viejo medía 189x189 para
        esta misma cara y se veía grande."""
        box = camera_geometry.framing_box(None, self.face(250, 150), 640, 480)
        self.assertLess(box[2] * box[3], 189 * 189)
        self.assertLess(box[3], 189)

    def test_framing_box_does_not_move_while_the_face_fits(self):
        """Lo que pediste: el recuadro es estático. Mientras la caja
        blanca quepa dentro, no se mueve ni un píxel. El paso vertical es
        corto a propósito: con MARGIN_Y en 0.06 la holgura de arriba y
        abajo es de unos 9 px, no de 30 como a los lados."""
        sq = camera_geometry.framing_box(None, self.face(250, 150), 640, 480)
        for dx, dy in ((5, 4), (12, -6), (20, 3), (-8, 7)):
            moved = camera_geometry.framing_box(
                sq, self.face(250 + dx, 150 + dy), 640, 480)
            self.assertEqual(moved, sq)

    def test_framing_box_jumps_only_when_the_face_leaves_it(self):
        sq = camera_geometry.framing_box(None, self.face(250, 150), 640, 480)
        out = self.face(250 + 200, 150)
        self.assertFalse(camera_geometry.box_contains(sq, out))
        moved = camera_geometry.framing_box(sq, out, 640, 480)
        self.assertNotEqual(moved, sq)
        self.assertTrue(camera_geometry.box_contains(moved, out))

    def test_framing_box_stays_inside_the_frame(self):
        """Contra el borde el cuadrado se recorta al frame en vez de
        salirse: es lo que hace que la caja blanca acabe asomando por
        fuera de la verde cuando ya no hay hacia dónde seguir."""
        box = camera_geometry.framing_box(None, self.face(600, 400), 640, 480)
        x, y, w, h = box
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, 640)
        self.assertLessEqual(y + h, 480)

    def test_framing_box_never_exceeds_the_frame(self):
        box = camera_geometry.framing_box(None, self.face(100, 50, 600, 460), 640, 480)
        self.assertLessEqual(box[2], 640)
        self.assertLessEqual(box[3], 480)

    # --- estado del encuadre ---------------------------------------------
    def test_framing_ok_when_comfortably_inside(self):
        state = camera_geometry.framing_state(self.face(250, 150), 640, 480)
        self.assertEqual(state, "ok")

    def test_framing_warns_before_it_actually_clips(self):
        """Hallazgo 3 del plan: el ámbar tiene que avisar ANTES de que la
        cara toque el borde, no en el instante en que ya se salió."""
        # A 20 px del borde derecho: todavía cabe entera, pero es menos
        # de un tercio del ancho de la cara.
        state = camera_geometry.framing_state(self.face(492, 150), 640, 480)
        self.assertEqual(state, "warn")

    def test_framing_out_once_the_face_clips_the_frame(self):
        state = camera_geometry.framing_state(self.face(560, 150), 640, 480)
        self.assertEqual(state, "out")

    def test_nudge_names_the_side_that_is_clipped(self):
        # Se sale por la derecha -> corregir yendo a la izquierda.
        self.assertEqual(
            camera_geometry.nudge_text(self.face(560, 150), 640, 480),
            "muévete a la izquierda")
        # Se sale por la izquierda -> corregir yendo a la derecha.
        self.assertEqual(
            camera_geometry.nudge_text(self.face(-30, 150), 640, 480),
            "muévete a la derecha")
        # Esquina: se sale por arriba y por la derecha a la vez.
        self.assertEqual(
            camera_geometry.nudge_text(self.face(560, -20), 640, 480),
            "muévete a la izquierda y abajo")

    def test_nudge_is_none_when_the_face_fits(self):
        self.assertIsNone(camera_geometry.nudge_text(self.face(250, 150), 640, 480))

    def test_clip_box_to_frame_returns_the_visible_part(self):
        p1, p2 = camera_geometry.clip_box_to_frame((-20, -10, 100, 50), 640, 480)
        self.assertEqual(p1, (0, 0))
        self.assertEqual(p2, (80, 40))

    def test_clip_box_to_frame_none_when_fully_outside(self):
        p1, p2 = camera_geometry.clip_box_to_frame((-200, 0, 50, 50), 640, 480)
        self.assertEqual((p1, p2), (None, None))

    # --- ejes desde la glabela -------------------------------------------
    def test_axis_vectors_with_identity_matrix(self):
        """Con `R = I` (mirando derecho a la cámara): el eje lateral queda
        horizontal, el vertical queda vertical, y el de profundidad casi
        desaparece -- exactamente el hallazgo 1 del plan."""
        lateral, vertical, depth = camera_geometry.axis_vectors(
            self.IDENTITY, length=40.0)
        self.assertAlmostEqual(lateral[0], 40.0)
        self.assertAlmostEqual(lateral[1], 0.0)
        self.assertAlmostEqual(vertical[0], 0.0)
        self.assertNotAlmostEqual(vertical[1], 0.0)
        self.assertAlmostEqual(depth[0], 0.0)
        self.assertAlmostEqual(depth[1], 0.0)

    def test_axis_vectors_rotate_with_r(self):
        """Girar la cabeza 90 grados intercambia el eje lateral por el de
        profundidad: las flechas siguen a `R`, no quedan fijas."""
        lateral, _, _ = camera_geometry.axis_vectors(self.YAW90, length=40.0)
        self.assertAlmostEqual(lateral[0], 0.0, delta=1e-9)
        self.assertAlmostEqual(lateral[1], 0.0, delta=1e-9)

    def test_vertical_arrow_follows_the_head_down(self):
        """El signo vertical, ya verificado con la cámara: al agachar la
        cabeza la flecha vertical tiene que bajar en la imagen (la Y de
        la imagen crece hacia abajo, así que su dy es positivo)."""
        # Cabeceo hacia abajo: el eje Y de la cabeza se inclina al frente.
        pitch_down = [[1.0, 0.0, 0.0], [0.0, 0.5, -0.866], [0.0, 0.866, 0.5]]
        _, vertical, _ = camera_geometry.axis_vectors(pitch_down, length=40.0)
        self.assertLess(vertical[1], 0.0)   # sigue apuntando "arriba"
        pitch_more = [[1.0, 0.0, 0.0], [0.0, -0.5, -0.866], [0.0, 0.866, -0.5]]
        _, vertical2, _ = camera_geometry.axis_vectors(pitch_more, length=40.0)
        self.assertGreater(vertical2[1], 0.0)   # pasada la vertical, baja

    # --- centro de la cabeza ---------------------------------------------
    def test_head_center_sits_on_the_glabella_when_facing_forward(self):
        """Mirando de frente el desplazamiento es puro eje de la cámara,
        así que en proyección ortográfica el punto cae sobre la glabela."""
        center = camera_geometry.head_center((320, 200), self.IDENTITY, 100)
        self.assertEqual(center, (320, 200))

    def test_head_center_moves_behind_the_glabella_when_turning(self):
        """Al girar 90 grados el centro se va hacia ATRÁS, al lado
        contrario de donde mira la cara. Con YAW90 la cara mira hacia la
        derecha de la imagen, así que el centro queda a la izquierda de
        la glabela -- no basta con comprobar que se movió: si el signo
        estuviera invertido, el punto saldría flotando por delante de la
        cara, y eso se vería igual de "movido"."""
        center = camera_geometry.head_center((320, 200), self.YAW90, 100)
        self.assertLess(center[0], 320)
        self.assertEqual(center[1], 200)      # el giro es horizontal

    def test_head_center_depth_scales_with_the_face(self):
        """Más cerca de la cámara (radio mayor) el centro queda más lejos
        en píxeles: la profundidad es una fracción del tamaño de la cara,
        no un número fijo de píxeles."""
        near = camera_geometry.head_center((320, 200), self.YAW90, 200)
        far = camera_geometry.head_center((320, 200), self.YAW90, 100)
        self.assertGreater(abs(near[0] - 320), abs(far[0] - 320))

    def test_glabella_is_the_landmark_verified_against_the_camera(self):
        """El 9 se eligió corriendo MediaPipe sobre un frame real, no de
        memoria. Si alguien lo cambia, que sea a propósito."""
        self.assertEqual(camera_geometry.GLABELLA, 9)


class TestCalibrationDirectionScaling(unittest.TestCase):
    """La cámara mirando desde abajo (y un cuello que gira más de lado que
    hacia abajo) hacen que el rango de pitch sea varias veces menor que el
    de yaw. En grados crudos, una diagonal honesta no cae en los 135°
    nominales y el asistente la rechazaba."""

    @staticmethod
    def point(label, yaw, pitch):
        return {"label": label, "units": CALIB_UNITS,
                "angle_deg": math.degrees(math.atan2(pitch, yaw)) % 360.0,
                "magnitude": math.hypot(yaw, pitch)}

    def cardinals(self):
        """Cuatro cardinales reales: ~35° de yaw contra ~10° de pitch."""
        return [self.point("right", 35, 2), self.point("left", -34, 1),
                self.point("up", 1, -14), self.point("down", 2, 7)]

    # --- el rango propio ---------------------------------------------------
    def test_scales_come_from_the_cardinals(self):
        ys, ps = direction_scales(self.cardinals())
        self.assertAlmostEqual(ys, (35.06 + 34.01) / 2, delta=0.2)
        self.assertAlmostEqual(ps, (14.04 + 7.28) / 2, delta=0.2)

    def test_no_scales_until_both_axes_are_measured(self):
        self.assertIsNone(direction_scales([]))
        solo_horizontal = [self.point("right", 35, 2), self.point("left", -34, 1)]
        self.assertIsNone(direction_scales(solo_horizontal))
        solo_vertical = [self.point("up", 1, -14), self.point("down", 2, 7)]
        self.assertIsNone(direction_scales(solo_vertical))

    def test_scales_ignore_the_diagonals(self):
        pts = self.cardinals() + [self.point("diag_down_left", -35, 6)]
        self.assertEqual(direction_scales(pts), direction_scales(self.cardinals()))

    def test_absurdly_small_scale_is_not_trusted(self):
        pts = [self.point("right", 35, 0), self.point("left", -35, 0),
               self.point("up", 0, -1), self.point("down", 0, 1)]
        self.assertIsNone(direction_scales(pts))

    # --- el caso reportado -------------------------------------------------
    def test_the_reported_diagonal_is_accepted(self):
        """El caso exacto que falló: pedía 135 ± 30 y medía más de 170."""
        scales = direction_scales(self.cardinals())
        crudo = HeadTracker.validate_calibration_point("diag_down_left", -35.0, 6.0)
        self.assertGreater(crudo["angle"], 170.0)
        self.assertFalse(crudo["ok"])           # en grados crudos, rechazada

        propio = HeadTracker.validate_calibration_point(
            "diag_down_left", -35.0, 6.0, scales)
        self.assertTrue(propio["ok"], propio)
        self.assertLess(angle_distance(propio["angle_scaled"], 135.0), 30.0)

    def test_the_stored_angle_stays_in_raw_degrees(self):
        """El ángulo que se GUARDA tiene que seguir siendo el crudo: el
        octágono de _normalize_polygon trabaja en grados crudos, y
        guardarle el normalizado le deformaría la geometría."""
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("diag_down_left", -35.0, 6.2, scales)
        self.assertAlmostEqual(r["angle"],
                               math.degrees(math.atan2(6.2, -35.0)) % 360.0, delta=1e-6)
        self.assertNotAlmostEqual(r["angle"], r["angle_scaled"], delta=1.0)

    # --- lo que NO debe aceptar --------------------------------------------
    def test_a_pure_sideways_move_is_still_not_a_diagonal(self):
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("diag_down_left", -35.0, 0.5, scales)
        self.assertFalse(r["ok"])
        self.assertEqual(r["detail"], "angle")

    def test_moving_to_the_opposite_side_is_rejected_by_sign(self):
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("diag_down_left", 35.0, 6.2, scales)
        self.assertFalse(r["ok"])
        self.assertEqual(r["detail"], "sign")

    def test_a_cardinal_with_the_other_axis_dragging_is_rejected(self):
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("down", 8.0, 8.0, scales)
        self.assertFalse(r["ok"])
        self.assertEqual(r["detail"], "dominance")

    def test_barely_moving_is_still_center(self):
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("down", 0.2, 1.0, scales)
        self.assertEqual(r["reason"], "center")

    # --- agacharse: menos grados, misma validez ----------------------------
    def test_a_short_but_clean_down_is_accepted(self):
        """«Al agacharme no detecta lo suficiente»: 4° hacia abajo es poco
        en grados crudos, pero es más de un tercio de SU rango vertical."""
        scales = direction_scales(self.cardinals())
        r = HeadTracker.validate_calibration_point("down", 1.0, 4.0, scales)
        self.assertTrue(r["ok"], r)

    def test_cardinals_do_not_need_scales(self):
        """Las cardinales son los primeros pasos, cuando todavía no hay
        rango propio medido: se validan por dominancia, que no lo necesita."""
        r = HeadTracker.validate_calibration_point("down", 1.0, 4.0)
        self.assertTrue(r["ok"], r)

    # --- integración con calibrate_direction -------------------------------
    def test_calibrate_direction_uses_its_own_scales(self):
        t = make_tracker({"head_limit_points": list(self.cardinals())})
        r = t.calibrate_direction("diag_down_left", -35.0, 6.0)
        self.assertTrue(r["ok"], r)
        guardado = [p for p in t.config["head_limit_points"]
                    if p["label"] == "diag_down_left"][0]
        self.assertGreater(guardado["angle_deg"], 170.0)   # guardado en crudo


class TestLatestFrame(unittest.TestCase):
    """Fase 2 de docs/plan_vista_camara.md: el tracker publica el frame ya
    anotado para que la GUI lo muestre embebida, sin abrir otra ventana."""

    H, D = 10.0, 10.0

    def cfg(self):
        return {"t_sens_x": 10.0, "t_sens_y": 10.0, "t_min_cutoff": 1.0,
                "t_beta": 0.05, "t_center_drag": 0.0, "head_limit_points": [],
                "t_neck_height_cm": self.H, "t_neck_depth_cm": self.D,
                "head_roll_limit_deg": 30.0, "t_sens_roll": 10.0,
                "t_roll_deadzone": 0.0}

    def feed(self, t, frame, n=3, t0=0.0, fps=30):
        for i in range(n):
            M = rot(0, 0)
            M[:3, 3] = np.array([0.0, self.H, self.D])
            t._process_detection(t0 + i / fps, LM, M, 640, 480, frame)
        return t0 + n / fps

    @staticmethod
    def frame():
        return np.zeros((480, 640, 3), np.uint8)

    def test_no_frame_before_anything_happens(self):
        t = make_tracker(self.cfg())
        frame, count = t.latest_frame()
        self.assertIsNone(frame)
        self.assertEqual(count, 0)

    def test_nothing_is_drawn_while_nobody_is_looking(self):
        """Con el overlay apagado y sin ventana de depuración no se dibuja:
        el seguimiento sigue igual, pero el contador no avanza."""
        t = make_tracker(self.cfg())
        t.overlay_enabled = False
        t.show_debug = False
        self.feed(t, self.frame())
        self.assertEqual(t.latest_frame()[1], 0)
        self.assertNotEqual(t.get_head_axes(), None)

    def test_the_counter_advances_once_per_detection(self):
        t = make_tracker(self.cfg())
        t.overlay_enabled = True
        self.feed(t, self.frame(), n=3)
        self.assertEqual(t.latest_frame()[1], 3)

    def test_latest_frame_is_the_last_one(self):
        """Devuelve el último, no el primero: es lo que hace que la vista
        no se quede pegada en una imagen vieja."""
        t = make_tracker(self.cfg())
        t.overlay_enabled = True
        primero, ultimo = self.frame(), self.frame()
        now = self.feed(t, primero, n=1)
        self.feed(t, ultimo, n=1, t0=now)
        self.assertIs(t.latest_frame()[0], ultimo)

    def test_the_debug_window_still_draws_on_its_own(self):
        """`show_debug` manda por su cuenta: la ventana aparte de OpenCV
        sigue funcionando aunque nadie haya encendido la vista embebida."""
        t = make_tracker(self.cfg())
        t.overlay_enabled = False
        t.show_debug = True
        self.feed(t, self.frame(), n=2)
        self.assertEqual(t.latest_frame()[1], 2)

    def test_turning_the_overlay_off_drops_the_frame(self):
        """Apagarla suelta el frame: si no, la GUI seguiría mostrando la
        última imagen congelada, que parece una cámara colgada."""
        t = make_tracker(self.cfg())
        t.overlay_enabled = True
        self.feed(t, self.frame())
        self.assertIsNotNone(t.latest_frame()[0])
        t.set_overlay_enabled(False)
        self.assertIsNone(t.latest_frame()[0])

    def test_turning_it_off_keeps_the_debug_window_frame(self):
        t = make_tracker(self.cfg())
        t.overlay_enabled = True
        t.show_debug = True
        self.feed(t, self.frame())
        t.set_overlay_enabled(False)
        self.assertIsNotNone(t.latest_frame()[0])

    def test_a_missing_frame_does_not_crash(self):
        """El motor sin GUI llama sin frame; no debe explotar por querer
        dibujar sobre nada."""
        t = make_tracker(self.cfg())
        t.overlay_enabled = True
        self.feed(t, None)
        self.assertIsNone(t.latest_frame()[0])
        # Y no se publica un "frame" que no existe: sin esto, la GUI
        # creería que hay imagen nueva y trataría de dibujar None.
        self.assertEqual(t.latest_frame()[1], 0)


class TestCameraViewWidget(unittest.TestCase):
    """Fase 3 de docs/plan_vista_camara.md: el widget de Tk que muestra el
    frame ya anotado dentro de la GUI, sin la ventana aparte de OpenCV."""

    class FakeTrackerWithFrames:
        """Un tracker de mentira con la parte de la Fase 2 que usa la vista."""

        def __init__(self, frame=None, count=1):
            self._frame, self._count = frame, count
            self.overlay_enabled = False
            self.enabled_calls = []

        def latest_frame(self):
            return self._frame, self._count

        def set_overlay_enabled(self, enabled):
            self.overlay_enabled = bool(enabled)
            self.enabled_calls.append(bool(enabled))

        def publish(self, frame):
            self._frame, self._count = frame, self._count + 1

    @staticmethod
    def frame(w=640, h=480):
        return np.zeros((h, w, 3), np.uint8)

    @contextlib.contextmanager
    def view(self, tracker=None, **kw):
        """La vista sobre el tk falso, con un contexto mínimo. Va como
        gestor de contexto porque el tk falso solo existe dentro de él."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            from frontend.camera_view.widget import CameraView
            ctx = SimpleNamespace(tracker=tracker, config={}, root=app.root)
            yield CameraView(tk.Frame(app.root), ctx, **kw), ctx

    # --- escalado ----------------------------------------------------------
    def test_fit_scales_down_keeping_the_aspect(self):
        with self.view() as (view, _):
            from frontend.camera_view.widget import fit
            self.assertEqual(fit(self.frame(640, 480), (320, 240)).shape[:2], (240, 320))

    def test_fit_does_not_deform_a_wider_camera(self):
        with self.view() as (view, _):
            from frontend.camera_view.widget import fit
            h, w = fit(self.frame(640, 360), (320, 240)).shape[:2]
            self.assertAlmostEqual(w / h, 640 / 360, delta=0.02)
            self.assertLessEqual(w, 320)
            self.assertLessEqual(h, 240)

    def test_fit_never_upscales(self):
        """Agrandar solo gasta y se ve peor."""
        with self.view() as (view, _):
            from frontend.camera_view.widget import fit
            self.assertEqual(fit(self.frame(160, 120), (320, 240)).shape[:2], (120, 160))

    # --- conversión --------------------------------------------------------
    def test_conversion_falls_back_to_ppm_without_a_real_tk(self):
        """Sin un Tk de verdad, Pillow no puede crear su PhotoImage. El
        respaldo de `cv2.imencode('.ppm')` tiene que cubrirlo: es el mismo
        camino que se usaría con un Pillow compilado sin soporte de Tk."""
        with self.view() as (view, _):
            from frontend.camera_view.widget import to_tk_image
            photo = to_tk_image(self.frame())
            self.assertIsNotNone(photo)
            self.assertTrue(base64.b64decode(photo.data).startswith(b"P6"))

    # --- contenido ---------------------------------------------------------
    def test_it_says_who_has_the_camera_with_an_external_source(self):
        with self.view(tracker=None) as (view, _):
            from frontend.camera_view.widget import MSG_EXTERNAL
            view.refresh()
            self.assertEqual(view.canvas.items[1]["kw"]["text"], MSG_EXTERNAL)

    def test_it_waits_while_there_is_no_frame_yet(self):
        with self.view(tracker=self.FakeTrackerWithFrames(None)) as (view, _):
            from frontend.camera_view.widget import MSG_WAITING
            view.refresh()
            self.assertEqual(view.canvas.items[1]["kw"]["text"], MSG_WAITING)

    def test_it_turns_the_overlay_on_by_itself(self):
        """Y en CADA pasada, no una sola vez: el tracker se reemplaza en
        vivo al alternar la fuente, y el nuevo nace con el overlay
        apagado."""
        tracker = self.FakeTrackerWithFrames(self.frame())
        with self.view(tracker=tracker) as (view, ctx):
            view.refresh()
            self.assertTrue(tracker.overlay_enabled)

            nuevo = self.FakeTrackerWithFrames(self.frame())
            ctx.tracker = nuevo
            view.refresh()
            self.assertTrue(nuevo.overlay_enabled)

    def test_it_draws_the_frame_and_keeps_the_reference(self):
        """Guardar la referencia a la imagen no es opcional: si se pierde,
        Tk la recoge y el canvas se queda en blanco."""
        with self.view(tracker=self.FakeTrackerWithFrames(self.frame())) as (view, _):
            view.refresh()
            self.assertIsNotNone(view._photo)
            self.assertIs(view.canvas.items[0]["kw"]["image"], view._photo)
            self.assertEqual(view.canvas.items[0]["kw"]["state"], "normal")

    def test_it_does_not_reconvert_the_same_frame(self):
        """La razón de ser del contador: con la GUI a 60 Hz y la cámara a
        30, la mitad de las conversiones serían de la misma imagen."""
        tracker = self.FakeTrackerWithFrames(self.frame())
        with self.view(tracker=tracker) as (view, _):
            view.refresh()
            primera = view._photo
            view.refresh()
            self.assertIs(view._photo, primera)

            tracker.publish(self.frame())
            view.refresh()
            self.assertIsNot(view._photo, primera)

    # --- encender y apagar -------------------------------------------------
    def test_hiding_also_turns_the_drawing_off(self):
        """Es el sentido del botón: el coste se va con la vista."""
        tracker = self.FakeTrackerWithFrames(self.frame())
        with self.view(tracker=tracker) as (view, _):
            view.refresh()
            self.assertTrue(tracker.overlay_enabled)
            view.hide()
            self.assertFalse(tracker.overlay_enabled)
            self.assertIsNone(view._photo)

    def test_hiding_stops_the_loop(self):
        with self.view(tracker=self.FakeTrackerWithFrames(self.frame())) as (view, _):
            view.start()
            pendiente = view._after_id
            self.assertIsNotNone(pendiente)
            view.hide()
            self.assertIn(pendiente, view.canvas.cancelled_after)
            self.assertIsNone(view._after_id)

    def test_toggle_reports_the_new_state(self):
        with self.view(tracker=self.FakeTrackerWithFrames(self.frame())) as (view, _):
            self.assertFalse(view.toggle())
            self.assertTrue(view.toggle())

    def test_a_destroyed_view_stops_its_loop(self):
        """Si el lazo siguiera vivo sobre un canvas destruido, cada vuelta
        lanzaría una excepción dentro de Tk."""
        with self.view(tracker=self.FakeTrackerWithFrames(self.frame())) as (view, _):
            view.start()
            view.canvas.destroy()
            view._tick()
            self.assertIsNone(view._after_id)


class TestCameraSectionInTheTab(unittest.TestCase):
    """La sección CÁMARA de la pestaña Head Tracker: ya no dibuja la vista
    (eso vive en el panel derecho, ver TestCameraInThePreviewPanel), solo
    trae el botón para mostrarla/ocultarla y la rotación del video."""

    def test_the_button_controls_the_shared_view(self):
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            camera = app.tracker_tab.camera
            self.assertIsNotNone(camera.view)
            self.assertIs(camera.view, app.preview.head.camera)

    def test_the_button_says_what_it_will_do(self):
        from frontend.camera_view.widget import SHOW_TEXT, HIDE_TEXT
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            camera = app.tracker_tab.camera
            self.assertEqual(camera.btn_view.kw["text"], HIDE_TEXT)
            camera.btn_view.invoke()
            self.assertEqual(camera.btn_view.kw["text"], SHOW_TEXT)
            camera.btn_view.invoke()
            self.assertEqual(camera.btn_view.kw["text"], HIDE_TEXT)

    def test_the_button_actually_toggles_the_view_in_the_panel(self):
        """El botón vive en la pestaña, pero lo que prende y apaga está en
        el panel derecho: hay que probar que de verdad llegan al mismo
        objeto, no solo que cada lado se ve bien por separado."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            camera = app.tracker_tab.camera
            view = app.preview.head.camera
            self.assertTrue(view.visible)
            camera.btn_view.invoke()
            self.assertFalse(view.visible)
            camera.btn_view.invoke()
            self.assertTrue(view.visible)

    def test_the_view_is_dimmed_with_an_external_source(self):
        """Con OpenTrack no hay cámara propia que mostrar."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            app.tracker_tab.source.set_mode("external")
            self.assertEqual(app.tracker_tab.camera.btn_view.kw["state"], "disabled")


class TestCameraInThePreviewPanel(unittest.TestCase):
    """Fase 3 corregida: la cámara vive en el panel derecho, junto al
    preview de ejes (yaw/pitch y las barras), no dentro de la pestaña
    Head Tracker -- que solo se queda con el botón de mostrar/ocultar."""

    def test_the_video_sits_above_the_yaw_pitch_dot(self):
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            head = app.preview.head
            self.assertIsNotNone(head.camera)
            hermanos = head.camera_holder.master.children
            self.assertLess(hermanos.index(head.camera_holder),
                            hermanos.index(head.canvas))

    def test_showing_it_again_keeps_its_place(self):
        """El canvas vive dentro de un contenedor propio justo por esto:
        `pack` respeta el orden de llamada, así que al volver a mostrarlo
        directamente sobre el panel reaparecería al final de todo."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            head = app.preview.head
            hermanos = head.camera_holder.master.children
            antes = hermanos.index(head.camera_holder)
            app.tracker_tab.camera.btn_view.invoke()
            app.tracker_tab.camera.btn_view.invoke()
            self.assertEqual(hermanos.index(head.camera_holder), antes)
            self.assertIs(head.camera.canvas.master, head.camera_holder)

    def test_ctx_camera_view_is_the_same_object_the_panel_built(self):
        """`ctx.camera_view` es cómo la pestaña llega al widget: si el
        panel se reconstruyera con uno nuevo y la pestaña se quedara con
        el viejo, el botón dejaría de tener efecto."""
        import gui_snapshot
        with gui_snapshot.launched() as (tk, app):
            self.assertIs(app.ctx.camera_view, app.preview.head.camera)


class TestNoPopupDebugWindow(unittest.TestCase):
    """La vista embebida (Fase 3) reemplaza la ventana aparte de OpenCV.

    `create_head_source` está importado con `from ... import` en
    launcher.py, así que queda ligado al módulo en el momento de importar
    y no se puede espiar reemplazando `backend.tracker.create_head_source`
    después -- por eso esto se verifica sobre el código fuente en vez de
    sobre una llamada capturada."""

    def test_launcher_starts_the_tracker_without_the_debug_window(self):
        """Importa `frontend.app.launcher` bajo el tk falso (no hay
        tkinter de verdad en este entorno) en vez de arriba del archivo,
        para no ligarlo antes de que `faketk.build()` lo permita."""
        import inspect
        import gui_snapshot

        with gui_snapshot.launched():
            import frontend.app.launcher as launcher
            src = inspect.getsource(launcher.ConfigLauncher._start_head_source)

        self.assertIn("show_debug=False", src)
        self.assertNotIn("show_debug=True", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
