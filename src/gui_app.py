import sys
import os
import json
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyautogui
from pynput import mouse as pynput_mouse

# --- IMPORTS DE LÓGICA ---
from backend.inputs import InputPhysics
from backend.tracker import HeadTracker
from utils.config import load_config, save_config

# --- IMPORTS DE VISUALIZACIÓN ---
from frontend.theme import apply_theme, COLOR_BG, COLOR_PANEL, COLOR_ACCENT, COLOR_WARN, FONT_BOLD, FONT_HEADER
from frontend.widgets import ModernSlider
from frontend.tooltips import create_help_icon  # <--- IMPORTAMOS LA NUEVA FUNCIÓN

pyautogui.FAILSAFE = False

class ConfigLauncher:
    def __init__(self):
        self.current_config = load_config()
        self.running_preview = True
        self.live_throttle = 0.0
        self.live_rudder = 0.0
        self.pressed_buttons = set()
        self.after_id = None
        self.tracker = None

        self.root = tk.Tk()
        self.root.title("AeroController // Pro Configurator")
        self.root.geometry("1200x780")
        self.root.configure(bg=COLOR_BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

        apply_theme()
        self._build_layout()
        self._init_hardware()
        
        self.screen_w, self.screen_h = pyautogui.size()
        self.update_ui()

    def _init_hardware(self):
        print("[GUI] Iniciando Tracker en modo Debug...")
        try:
            self.tracker = HeadTracker(config=self.current_config, show_debug=True)
        except Exception as e:
            print(f"[GUI ERROR] Fallo Tracker: {e}")
            
        self.mouse_listener = pynput_mouse.Listener(on_scroll=self.on_scroll, on_click=self.on_click)
        self.mouse_listener.start()

    def _build_layout(self):
        main_container = tk.Frame(self.root, bg=COLOR_BG)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)

        left_panel = tk.Frame(main_container, bg=COLOR_BG, width=450)
        left_panel.pack(side='left', fill='y', padx=(0, 10))
        
        tk.Label(left_panel, text="CONFIGURACIÓN DE VUELO", font=("Segoe UI", 16, "bold"), 
                 bg=COLOR_BG, fg=COLOR_ACCENT).pack(anchor='w', pady=(0, 10))
        
        self.notebook = ttk.Notebook(left_panel)
        self.notebook.pack(fill='both', expand=True)

        self._build_tab_stick()
        self._build_tab_tracker()
        self._build_tab_system()

        self.btn_fly = tk.Button(left_panel, text=">>> INICIAR VUELO <<<", 
                                 bg=COLOR_ACCENT, fg="black", font=("Segoe UI", 14, "bold"),
                                 relief="flat", command=self.start_simulation, cursor="hand2")
        self.btn_fly.pack(fill='x', pady=15, ipady=10)

        right_panel = tk.Frame(main_container, bg=COLOR_BG)
        right_panel.pack(side='right', fill='both', expand=True)
        self._build_visualization_panel(right_panel)

    # --- HELPER PARA CREAR SLIDER + ICONO ---
    def _add_slider_row(self, parent, text, min_v, max_v, step, val, key, cmd=None):
        """Crea una fila con el Slider a la izquierda y el icono '?' a la derecha"""
        container = tk.Frame(parent, bg=COLOR_PANEL)
        container.pack(fill='x', padx=15, pady=2)
        
        # El Slider se expande
        slider = ModernSlider(container, text, min_v, max_v, step, val, cmd)
        slider.pack(side='left', fill='x', expand=True)
        
        # El Icono se queda fijo a la derecha (Alineado arriba para que coincida con el título del slider)
        icon = create_help_icon(container, key)
        icon.pack(side='right', padx=(10, 0), anchor='n', pady=5)
        
        return slider

    def _build_tab_stick(self):
        tab = tk.Frame(self.notebook, bg=COLOR_PANEL)
        self.notebook.add(tab, text="🕹️ Stick / Mouse")
        
        pad = 15
        tk.Label(tab, text="GEOMETRÍA", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(pad, 5))
        
        # Usamos el nuevo helper _add_slider_row
        self.s_radius = self._add_slider_row(tab, "Radio Máximo (px)", 100, 800, 10, self.current_config.get('radius', 300), "radius", self._update_curve_graph)
        self.s_outer  = self._add_slider_row(tab, "Zona Saturación Extra (px)", 0, 200, 5, self.current_config.get('outer', 50), "outer")

        tk.Frame(tab, bg="#444", height=1).pack(fill='x', padx=pad, pady=10) 

        tk.Label(tab, text="RESPUESTA", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(5, 5))
        
        self.s_curve    = self._add_slider_row(tab, "Linealidad (Curva)", 1.0, 4.0, 0.1, self.current_config.get('curve', 1.0), "curve", self._update_curve_graph)
        self.s_deadzone = self._add_slider_row(tab, "Zona Muerta (%)", 0.0, 0.30, 0.01, self.current_config.get('deadzone', 0.05), "deadzone")
        self.s_snap     = self._add_slider_row(tab, "Magnetismo Ejes (%)", 0.0, 0.20, 0.01, self.current_config.get('snap', 0.05), "snap")

        self.curve_canvas = tk.Canvas(tab, height=100, bg="#222", highlightthickness=0)
        self.curve_canvas.pack(fill='x', padx=pad, pady=10)
        self._update_curve_graph()

    def _build_tab_tracker(self):
        tab = tk.Frame(self.notebook, bg=COLOR_PANEL)
        self.notebook.add(tab, text="👀 Head Tracker")
        
        pad = 15
        tk.Label(tab, text="SENSIBILIDAD", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(pad, 5))
        
        self.t_sens_x = self._add_slider_row(tab, "Yaw (X)", 1.0, 20.0, 0.5, self.current_config.get('t_sens_x', 10.0), "t_sens_x")
        self.t_sens_y = self._add_slider_row(tab, "Pitch (Y)", 1.0, 20.0, 0.5, self.current_config.get('t_sens_y', 10.0), "t_sens_y")

        tk.Frame(tab, bg="#444", height=1).pack(fill='x', padx=pad, pady=10)

        tk.Label(tab, text="COMPORTAMIENTO", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(5, 5))
        
        self.t_center_drag = self._add_slider_row(tab, "Auto-Centrado (Peso)", 0.0, 0.02, 0.001, self.current_config.get('t_center_drag', 0.005), "t_center_drag")
        self.t_smooth      = self._add_slider_row(tab, "Suavizado (Filtro)", 0.01, 1.0, 0.05, self.current_config.get('t_smooth', 0.5), "t_smooth")
        self.t_deadzone    = self._add_slider_row(tab, "Deadzone Central", 0.0, 0.1, 0.005, self.current_config.get('t_deadzone', 0.02), "t_deadzone_t")
        
        tk.Frame(tab, bg="#444", height=1).pack(fill='x', padx=pad, pady=10)
        
        tk.Label(tab, text="MAGNETISMO (Snap)", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(5, 5))
        
        self.t_snap_axis  = self._add_slider_row(tab, "Fuerza Ejes", 0.0, 0.5, 0.05, self.current_config.get('t_snap_axis', 0.25), "t_snap_axis")
        self.t_snap_outer = self._add_slider_row(tab, "Fuerza Bordes", 0.0, 0.3, 0.01, self.current_config.get('t_snap_outer', 0.10), "t_snap_outer")

    def _build_tab_system(self):
        tab = tk.Frame(self.notebook, bg=COLOR_PANEL)
        self.notebook.add(tab, text="💾 Sistema")
        
        pad = 20
        tk.Label(tab, text="PERFILES", bg=COLOR_PANEL, fg=COLOR_ACCENT, font=FONT_HEADER).pack(anchor='w', padx=pad, pady=(pad, 10))
        
        tk.Button(tab, text="Guardar Perfil Como...", bg="#444", fg="white", 
                  command=self._save_profile_dialog).pack(fill='x', padx=pad, pady=5)
        tk.Button(tab, text="Cargar Perfil...", bg="#444", fg="white", 
                  command=self._load_profile_dialog).pack(fill='x', padx=pad, pady=5)

        tk.Label(tab, text="Atajos:", bg=COLOR_PANEL, fg="gray").pack(anchor='w', padx=pad, pady=(20,5))
        tk.Label(tab, text="• ALT+P: Pausar/Configurar", bg=COLOR_PANEL, fg="white").pack(anchor='w', padx=pad)
        tk.Label(tab, text="• ALT/WIN + < : Recentrar", bg=COLOR_PANEL, fg="white").pack(anchor='w', padx=pad)

    def _build_visualization_panel(self, parent):
        # 1. STICK PREVIEW
        frame_stick = tk.Frame(parent, bg=COLOR_BG)
        frame_stick.pack(fill='both', expand=True, padx=10, pady=10)
        tk.Label(frame_stick, text="STICK PREVIEW", bg=COLOR_BG, fg="#888", font=FONT_BOLD).pack()
        
        self.canvas_size = 250
        self.center_pt = self.canvas_size // 2
        self.vis_scale = 70
        
        self.canvas = tk.Canvas(frame_stick, width=self.canvas_size, height=self.canvas_size, 
                                bg="#000", highlightthickness=1, highlightbackground="#333")
        self.canvas.pack(pady=5)
        
        limit = self.vis_scale
        c = self.center_pt
        self.canvas.create_rectangle(c - limit, c - limit, c + limit, c + limit, outline="#444", dash=(2, 4))
        self.canvas.create_line(c, 0, c, self.canvas_size, fill="#222")
        self.canvas.create_line(0, c, self.canvas_size, c, fill="#222")
        self.dot = self.canvas.create_oval(0,0,0,0, fill=COLOR_WARN)

        # 2. TRACKER PREVIEW
        frame_head = tk.Frame(parent, bg=COLOR_BG)
        frame_head.pack(fill='both', expand=True, padx=10, pady=10)
        tk.Label(frame_head, text="TRACKER PREVIEW", bg=COLOR_BG, fg="#888", font=FONT_BOLD).pack()
        
        self.canvas_head = tk.Canvas(frame_head, width=self.canvas_size, height=150, 
                                     bg="#000", highlightthickness=1, highlightbackground="#333")
        self.canvas_head.pack(pady=5)
        
        tk.Button(frame_head, text="🎯 RECENTRAR CABEZA", bg="#444", fg="white", font=("Segoe UI", 8, "bold"),
                  relief="flat", command=self.safe_recenter).pack(side='bottom', fill='x', padx=60, pady=(0, 10))

        hc, vc = self.canvas_size // 2, 75
        self.canvas_head.create_line(hc, 0, hc, 150, fill="#222")
        self.canvas_head.create_line(0, vc, self.canvas_size, vc, fill="#222")
        self.head_dot = self.canvas_head.create_oval(0,0,0,0, fill=COLOR_ACCENT)

        # 3. INPUTS & BUTTONS
        tk.Label(parent, text="RAW INPUTS", bg=COLOR_BG, fg="#888", font=FONT_BOLD).pack(pady=(10,0))
        self.pb_throttle = ttk.Progressbar(parent, orient="horizontal", mode="determinate")
        self.pb_throttle.pack(fill='x', padx=30, pady=5)
        
        self.canvas_rudder = tk.Canvas(parent, height=15, bg="#333", highlightthickness=0)
        self.canvas_rudder.pack(fill='x', padx=30, pady=5)
        self.rudder_ind = self.canvas_rudder.create_rectangle(0,0,0,0, fill="#ff00ff")

        self.btn_container = tk.Frame(parent, bg=COLOR_BG)
        self.btn_container.pack(pady=10)
        self.btn_widgets = {}
        btns = [("L", "Button.left"), ("R", "Button.right"), ("M", "Button.middle"), ("S1", "Button.x1"), ("S2", "Button.x2")]
        for txt, code in btns:
            lbl = tk.Label(self.btn_container, text=txt, bg="#333", fg="white", font=("Arial", 8), width=6, pady=4)
            lbl.pack(side='left', padx=2)
            self.btn_widgets[code] = lbl

    # --- LOGIC ---
    def safe_recenter(self):
        if self.tracker: self.tracker.recenter()

    def _update_curve_graph(self, val=None):
        # val es opcional porque sliders a veces mandan el valor, a veces no.
        w = self.curve_canvas.winfo_width()
        if w < 10: w = 350
        h = 100
        self.curve_canvas.delete("all")
        curve = self.s_curve.get()
        points = []
        for i in range(0, w, 5):
            x_norm = i / w
            y_norm = math.pow(x_norm, curve)
            points.extend([i, h - (y_norm * h)])
        self.curve_canvas.create_line(points, fill=COLOR_ACCENT, width=2)

    def _get_current_config(self):
        return {
            'radius': int(self.s_radius.get()),
            'curve': self.s_curve.get(),
            'deadzone': self.s_deadzone.get(),
            'snap': self.s_snap.get(),
            'outer': int(self.s_outer.get()),
            't_sens_x': self.t_sens_x.get(),
            't_sens_y': self.t_sens_y.get(),
            't_smooth': self.t_smooth.get(),
            't_deadzone': self.t_deadzone.get(),
            't_snap_axis': self.t_snap_axis.get(),
            't_snap_outer': self.t_snap_outer.get(),
            't_center_drag': self.t_center_drag.get()
        }

    def update_ui(self):
        if not self.running_preview: return
        try:
            cfg = self._get_current_config()
            if self.tracker: self.tracker.update_config(cfg)

            mx, my = pyautogui.position()
            dx = mx - (self.screen_w // 2)
            dy = my - (self.screen_h // 2)
            fx, fy, stats = InputPhysics.calculate(dx, dy, cfg)

            vs = self.vis_scale
            self.canvas.coords(self.dot, 
                               self.center_pt + (fx * vs) - 6, self.center_pt + (fy * vs) - 6,
                               self.center_pt + (fx * vs) + 6, self.center_pt + (fy * vs) + 6)
            self.canvas.itemconfig(self.dot, fill="#555" if stats['in_deadzone'] else COLOR_WARN)

            if self.tracker:
                tx, ty = self.tracker.get_axes()
                hx = self.center_pt + (tx * 40)
                hy = 75 + (ty * 40) 
                self.canvas_head.coords(self.head_dot, hx-5, hy-5, hx+5, hy+5)

            self.pb_throttle['value'] = ((self.live_throttle + 1) / 2) * 100
            
            if abs(self.live_rudder) > 0.01:
                self.live_rudder += 0.01 if self.live_rudder < 0 else -0.01
            
            rw = self.canvas_rudder.winfo_width()
            rc = rw // 2
            rlen = self.live_rudder * (rw // 2 - 5)
            self.canvas_rudder.coords(self.rudder_ind, rc, 0, rc + rlen, 15)

            for code, widget in self.btn_widgets.items():
                is_p = any(code in p for p in self.pressed_buttons)
                widget.configure(bg=COLOR_ACCENT if is_p else "#333", fg="black" if is_p else "white")

        except Exception: pass
        self.after_id = self.root.after(16, self.update_ui)

    def _save_profile_dialog(self):
        fn = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if fn:
            try:
                with open(fn, 'w') as f: json.dump(self._get_current_config(), f, indent=4)
                messagebox.showinfo("Saved", "Perfil guardado.")
            except Exception as e: messagebox.showerror("Error", str(e))

    def _load_profile_dialog(self):
        fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if fn:
            try:
                with open(fn, 'r') as f: cfg = json.load(f)
                self.s_radius.set(cfg.get('radius', 300))
                self.s_curve.set(cfg.get('curve', 1.0))
                self.s_deadzone.set(cfg.get('deadzone', 0.05))
                self.s_snap.set(cfg.get('snap', 0.05))
                self.s_outer.set(cfg.get('outer', 50))
                
                self.t_sens_x.set(cfg.get('t_sens_x', 10.0))
                self.t_sens_y.set(cfg.get('t_sens_y', 10.0))
                self.t_smooth.set(cfg.get('t_smooth', 0.5))
                self.t_deadzone.set(cfg.get('t_deadzone', 0.02))
                self.t_snap_axis.set(cfg.get('t_snap_axis', 0.25))
                self.t_snap_outer.set(cfg.get('t_snap_outer', 0.10))
                self.t_center_drag.set(cfg.get('t_center_drag', 0.005))
                
                self._update_curve_graph()
            except Exception as e: messagebox.showerror("Error", str(e))

    def on_scroll(self, x, y, dx, dy):
        if dy != 0: self.live_throttle = max(min(self.live_throttle + dy * 0.05, 1.0), -1.0)
        if dx != 0: self.live_rudder = max(min(self.live_rudder + dx * 0.2, 1.0), -1.0)

    def on_click(self, x, y, button, pressed):
        s = str(button)
        if pressed: self.pressed_buttons.add(s)
        else: self.pressed_buttons.discard(s)

    def _cleanup_before_exit(self):
        self.running_preview = False
        if self.after_id: self.root.after_cancel(self.after_id)
        if hasattr(self, 'mouse_listener'): self.mouse_listener.stop()
        if self.tracker: self.tracker.stop()

    def start_simulation(self):
        print("[GUI] Guardando configuración y arrancando motor...")
        save_config(self._get_current_config())
        self._cleanup_before_exit()
        self.root.destroy()
        print("[GUI] Saliendo con código 10...", flush=True)
        sys.exit(10)

    def on_close_window(self):
        self._cleanup_before_exit()
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ConfigLauncher()
    app.run()