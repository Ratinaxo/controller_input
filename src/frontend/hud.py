import tkinter as tk
import pyautogui

class JoystickHUD:
    def __init__(self, radius_px):
        # Obtener dimensiones de pantalla
        self.screen_w, self.screen_h = pyautogui.size()
        
        # --- VENTANA 1: STICK (Derecha) ---
        self.root = tk.Tk()
        self.root.title("Stick HUD")
        self._configure_window(self.root)
        
        self.size = 260
        self.center = self.size // 2
        
        # Posición: Esquina Inferior Derecha
        x_pos = self.screen_w - self.size - 20
        y_pos = self.screen_h - self.size - 20
        self.root.geometry(f"{self.size}x{self.size}+{x_pos}+{y_pos}")

        self.canvas = tk.Canvas(self.root, width=self.size, height=self.size, bg='black', highlightthickness=0)
        self.canvas.pack()

        # --- VENTANA 2: TRACKER (Izquierda) ---
        self.win_tracker = tk.Toplevel(self.root)
        self.win_tracker.title("Head HUD")
        self._configure_window(self.win_tracker)
        
        self.track_size = 150
        self.track_center = self.track_size // 2
        
        # Posición: Esquina Inferior Izquierda
        x_pos_t = 20
        y_pos_t = self.screen_h - self.track_size - 20
        self.win_tracker.geometry(f"{self.track_size}x{self.track_size}+{x_pos_t}+{y_pos_t}")
        
        self.cv_tracker = tk.Canvas(self.win_tracker, width=self.track_size, height=self.track_size, bg='black', highlightthickness=0)
        self.cv_tracker.pack()

        # ==========================================
        # ELEMENTOS VISUALES - STICK (Derecha)
        # ==========================================
        
        # 1. Límite Cuadrado (Reflejando la nueva física)
        self.radius_vis = 80
        # Dibujamos un recuadro que representa el 100% de input (1.0, 1.0)
        self.canvas.create_rectangle(self.center - self.radius_vis, self.center - self.radius_vis,
                                     self.center + self.radius_vis, self.center + self.radius_vis,
                                     outline='#444', width=2, dash=(4, 4))
        
        # Cruz central
        self.canvas.create_line(self.center, 40, self.center, 220, fill='#222')
        self.canvas.create_line(40, self.center, 220, self.center, fill='#222')

        # 2. Barra Acelerador (Izquierda del panel derecho)
        self.canvas.create_rectangle(10, 40, 25, 218, outline="white")
        self.canvas.create_line(8, 129, 27, 129, fill="gray", width=1) # Marca cero
        self.throttle_bar = self.canvas.create_rectangle(12, 218, 23, 218, fill="#00ffff", outline="")
        self.canvas.create_text(18, 30, text="THR", fill="white", font=("Arial", 8, "bold"))

        # 3. Barra Timón (Abajo del panel derecho)
        self.canvas.create_rectangle(40, 235, 220, 250, outline="white")
        self.canvas.create_line(130, 235, 130, 250, fill="gray") # Marca centro
        self.rudder_bar = self.canvas.create_rectangle(130, 237, 130, 248, fill="#ff00ff", outline="")
        self.canvas.create_text(130, 225, text="RUDDER", fill="white", font=("Arial", 8, "bold"))

        # 4. Punto del Stick (Cursor)
        self.stick_dot = self.draw_circle(self.canvas, self.center, self.center, 6, fill='red', outline='white')

        # ==========================================
        # ELEMENTOS VISUALES - TRACKER (Izquierda)
        # ==========================================
        
        # Cruz de mira
        self.cv_tracker.create_line(self.track_center, 10, self.track_center, 140, fill="#00ff00", dash=(2,4))
        self.cv_tracker.create_line(10, self.track_center, 140, self.track_center, fill="#00ff00", dash=(2,4))
        
        # Etiqueta
        self.cv_tracker.create_text(self.track_center, 10, text="HEAD", fill="#00ff00", font=("Arial", 7, "bold"))
        
        # Punto de la cabeza
        self.head_dot = self.draw_circle(self.cv_tracker, self.track_center, self.track_center, 4, fill='#00ff00', outline='')

    def _configure_window(self, window):
        """Configuración común para ventanas transparentes"""
        window.overrideredirect(True) 
        window.attributes('-topmost', True)
        window.attributes('-alpha', 0.6) # Transparencia

    def draw_circle(self, canvas, x, y, r, **kwargs):
        return canvas.create_oval(x-r, y-r, x+r, y+r, **kwargs)

    def update(self, x_norm, y_norm, throttle_val, rudder_val, head_yaw, head_pitch, is_deadzone, is_snapped):
        """
        Actualiza ambos HUDs.
        x_norm, y_norm: -1.0 a 1.0 (Stick)
        head_yaw, head_pitch: -1.0 a 1.0 (Cabeza)
        """
        
        # --- 1. ACTUALIZAR STICK (DERECHA) ---
        vis_x = self.center + (x_norm * self.radius_vis)
        vis_y = self.center + (y_norm * self.radius_vis)
        
        self.canvas.coords(self.stick_dot, vis_x-6, vis_y-6, vis_x+6, vis_y+6)
        
        # Cambio de color según estado
        if is_deadzone: color = '#555'
        elif is_snapped: color = '#00ffff' # Cyan si está pegado al eje
        else: 
            # Rojo intenso si está al máximo (saturación)
            if abs(x_norm) > 0.99 or abs(y_norm) > 0.99: color = '#ff0000'
            else: color = '#ff8800' # Naranja normal
            
        self.canvas.itemconfig(self.stick_dot, fill=color)

        # --- 2. ACTUALIZAR THROTTLE ---
        # Mapeo de -1..1 a coordenadas Y (Invirtiendo eje Y de pantalla)
        # Base: 218, Tope: 40. Rango: 178px
        normalized_throttle = (throttle_val + 1.0) / 2.0
        bar_top_y = 218 - (normalized_throttle * 178)
        self.canvas.coords(self.throttle_bar, 12, 218, 23, bar_top_y)
        
        # Color dinámico (WEP / Reverso)
        t_color = "#00ffff"
        if throttle_val > 0.95: t_color = "#ff0000" # WEP
        elif throttle_val < 0: t_color = "#ff5555" # Reverso
        self.canvas.itemconfig(self.throttle_bar, fill=t_color)

        # --- 3. ACTUALIZAR RUDDER ---
        # Centro: 130. Ancho max: 90px por lado.
        r_len = rudder_val * 90
        self.canvas.coords(self.rudder_bar, 130, 237, 130 + r_len, 248)

        # --- 4. ACTUALIZAR TRACKER (IZQUIERDA) ---
        # Escala visual: 50px de desplazamiento máximo
        track_scale = 50 
        hx = self.track_center + (head_yaw * track_scale)
        hy = self.track_center + (head_pitch * track_scale)
        
        self.cv_tracker.coords(self.head_dot, hx-4, hy-4, hx+4, hy+4)

        # Refrescar ventanas
        self.root.update()
        
    def close(self):
        try: 
            self.win_tracker.destroy()
            self.root.destroy()
        except: pass