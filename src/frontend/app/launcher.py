"""Ventana principal del configurador.

Solo arma la ventana, conecta las pestañas y el preview, y corre el lazo.
Todo lo demás vive en su módulo: pestañas en frontend/tabs/, preview en
frontend/preview/, estilos en frontend/style/.
"""
import sys
import tkinter as tk
from tkinter import ttk

import rust_motor

from backend.tracker import create_head_source
from frontend.app.config_bridge import ConfigBridge
from frontend.app.context import AppContext
from frontend.app.input_reader import InputReader, InputState
from frontend.components import primary_button, ScrollableTabs
from frontend.preview import PreviewPanel
from frontend.style import colors as C, spacing as S, apply_theme, resolve_fonts
from frontend.style.fonts import FONTS
from frontend.tabs.buttons import ButtonsTab
from frontend.tabs.stick import StickTab
from frontend.tabs.system import SystemTab
from frontend.tabs.tracker import TrackerTab
from utils.config import load_config, save_config

WINDOW_TITLE = "AeroController // Pro Configurator (RUST NATIVE)"
UI_REFRESH_MS = 16
EXIT_START_FLIGHT = 10     # main.py lanza el motor al ver este código


class ConfigLauncher:
    def __init__(self):
        config = load_config()
        self.running_preview = True
        self.after_id = None
        self.input_state = InputState()

        # --- Física Rust para el preview (la misma del vuelo) ---
        try:
            self.rust_physics = rust_motor.RustPhysics(300.0, 1.0, 0.05, 0.1, 0.05, 50.0)
            print("[GUI] Motor físico Rust cargado para previsualización.")
        except Exception as e:
            print(f"[GUI CRITICAL] No se pudo cargar libreria Rust: {e}")
            sys.exit(1)

        self.root = tk.Tk()
        # ANTES de construir cualquier widget: Tk evalúa la tupla de fuente
        # al crearlo, así que resolver las familias después no cambiaría
        # nada de lo ya construido (Fase 6, «fuentes con respaldo»).
        resolve_fonts(self.root)
        self.root.title(WINDOW_TITLE)
        # Tamaño inicial según la pantalla (1200x780 como máximo) y un mínimo
        # utilizable. Todo el contenido de las pestañas tiene scroll, así que
        # la ventana puede achicarse sin que nada quede inaccesible.
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        fw, fh = S.WINDOW_SCREEN_FRACTION
        self.root.geometry(f"{min(S.WINDOW_MAX[0], int(sw * fw))}x{min(S.WINDOW_MAX[1], int(sh * fh))}")
        self.root.minsize(*S.WINDOW_MIN)
        self.root.configure(bg=C.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        self.ctx = AppContext(self.root, config)
        self.ctx.start_head_source = self._start_head_source
        self.ctx.stop_head_source = self._stop_head_source
        self.input_reader = InputReader(self.input_state, self.ctx.input_queue)

        # --- Pestañas ---
        self.stick_tab = StickTab(self.ctx)
        self.tracker_tab = TrackerTab(self.ctx)
        self.system_tab = SystemTab(self.ctx)
        self.buttons_tab = ButtonsTab(self.ctx)
        self.tabs = [self.stick_tab, self.tracker_tab, self.buttons_tab, self.system_tab]
        self.bridge = ConfigBridge(
            self.ctx, self.tabs,
            apply_order=[self.stick_tab, self.system_tab, self.buttons_tab, self.tracker_tab])
        self.system_tab.get_config = self.bridge.read_config
        self.system_tab.apply_config_all = self.bridge.apply_config

        apply_theme()
        self._build_layout()
        self._init_hardware()
        self.update_ui()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # Panel dividido: el usuario puede arrastrar el separador, y al
        # redimensionar la ventana ambos lados se reparten el espacio.
        paned = ttk.PanedWindow(self.root, orient='horizontal', style="Main.TPanedwindow")
        paned.pack(fill='both', expand=True, padx=10, pady=10)

        left_panel = tk.Frame(paned, bg=C.BG)
        right_panel = tk.Frame(paned, bg=C.BG)
        paned.add(left_panel, weight=3)
        paned.add(right_panel, weight=2)

        # El panel derecho se arma ANTES que las pestañas: la vista de
        # cámara vive ahí (junto al preview de ejes) y `ctx.camera_view`
        # tiene que existir cuando la pestaña Head Tracker construya su
        # botón de mostrar/ocultar. El orden de construcción no cambia el
        # orden visual izquierda/derecha, que ya quedó fijado por los
        # `paned.add(...)` de arriba.
        self.preview = PreviewPanel(right_panel, self.ctx, self.rust_physics,
                                    self.input_state, self.safe_recenter)

        tk.Label(left_panel, text="CONFIGURACIÓN DE VUELO", font=FONTS.title,
                 bg=C.BG, fg=C.ACCENT).pack(side='top', anchor='w', pady=(0, 10))

        # El botón se empaqueta ANTES que el notebook (abajo), así pack le
        # reserva su espacio primero y nunca queda fuera de la ventana.
        self.btn_fly = primary_button(left_panel, ">>> INICIAR VUELO <<<",
                                      command=self.start_simulation, font=FONTS.cta,
                                      relief="flat", cursor="hand2")
        self.btn_fly.pack(side='bottom', fill='x', pady=(10, 0), ipady=8)

        self.notebook = ttk.Notebook(left_panel)
        self.notebook.pack(side='top', fill='both', expand=True)

        self.scroll = ScrollableTabs(self.root, self.notebook)
        for tab in self.tabs:
            tab.build(self.scroll.add_tab(tab.title))

        # Textos largos: se re-ajustan al ancho real de la pestaña.
        self.scroll.enable_auto_wrap()
        self.scroll.bind_mousewheel()

    # ------------------------------------------------------------------
    # Hardware y fuente de cabeza
    # ------------------------------------------------------------------
    def _init_hardware(self):
        self._start_head_source()
        self.input_reader.start(self.ctx.config)

    def _start_head_source(self):
        """Abre la cámara propia solo si la fuente de cabeza es 'internal'.
        Con 'external' no se toca la cámara, para que OpenTrack pueda usarla
        mientras esta ventana está abierta."""
        if self.ctx.tracker is not None:
            return
        try:
            # La vista embebida (Fase 3 de docs/plan_vista_camara.md)
            # reemplaza la ventana aparte de OpenCV: pedirla en modo debug
            # seguía abriendo esa ventana emergente además del widget.
            self.ctx.tracker = create_head_source(self.ctx.config, show_debug=False)
            if self.ctx.tracker is not None:
                print("[GUI] Tracker propio iniciado.")
        except Exception as e:
            print(f"[GUI ERROR] Fallo Tracker: {e}")
            self.ctx.tracker = None

    def _stop_head_source(self):
        if self.ctx.tracker is None:
            return
        print("[GUI] Deteniendo tracker propio y liberando la cámara...")
        try:
            self.ctx.tracker.stop()
        except Exception as e:
            print(f"[GUI] Error al detener el tracker: {e}")
        self.ctx.tracker = None

    def safe_recenter(self):
        if self.ctx.tracker:
            self.ctx.tracker.recenter()
        self.input_state.recenter_stick()

    # ------------------------------------------------------------------
    # Lazo de la interfaz
    # ------------------------------------------------------------------
    def update_ui(self):
        if not self.running_preview:
            return
        try:
            self.buttons_tab.process_input()
            cfg = self.bridge.read_config()
            if self.ctx.tracker:
                self.ctx.tracker.update_config(cfg)
            self.preview.update(cfg, self.ctx.tracker)
        except Exception:
            pass  # evita spam en consola si algo falla en el lazo de dibujo
        self.after_id = self.root.after(UI_REFRESH_MS, self.update_ui)

    # ------------------------------------------------------------------
    # Salida
    # ------------------------------------------------------------------
    def _cleanup_before_exit(self):
        self.running_preview = False
        self.input_reader.close()
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self._stop_head_source()

    def start_simulation(self):
        print("[GUI] Guardando configuración y arrancando motor...")
        save_config(self.bridge.read_config())
        self._cleanup_before_exit()
        self.root.destroy()
        print(f"[GUI] Saliendo con código {EXIT_START_FLIGHT}...", flush=True)
        sys.exit(EXIT_START_FLIGHT)

    def on_close_window(self):
        self._cleanup_before_exit()
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()
