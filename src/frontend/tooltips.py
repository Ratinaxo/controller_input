import tkinter as tk
from frontend.theme import COLOR_ACCENT

# ==============================================================================
#  DICCIONARIO DE TEXTOS (EXPLICATIVO Y DETALLADO)
# ==============================================================================
HELP_TEXTS = {
    # --- STICK / MOUSE ---
    "radius": (
        "RADIO DEL STICK (Recorrido Físico):\n"
        "Define cuántos píxeles debes mover el mouse real para que el\n"
        "joystick virtual llegue a su tope (100%).\n\n"
        "• Valor Bajo (100-200px): Alta sensibilidad. Reacciona rápido con\n"
        "  movimientos cortos de muñeca. Ideal para combate ágil.\n"
        "• Valor Alto (400px+): Alta precisión. Requiere mover más el brazo.\n"
        "  Ideal para vuelo en formación, repostaje o helicópteros."
    ),
    
    "outer": (
        "SATURACIÓN EXTRA (Outer Deadzone):\n"
        "Zona de seguridad más allá del radio máximo.\n\n"
        "Si configuras esto en 50px, el motor seguirá enviando el 100% de señal\n"
        "incluso si mueves el mouse 50px más allá del límite.\n"
        "Útil para garantizar giros máximos sin tener que ser preciso\n"
        "con el límite del mousepad."
    ),
    
    "curve": (
        "CURVA DE RESPUESTA (Gamma / Linealidad):\n"
        "Modifica la sensibilidad en el centro del stick sin perder velocidad máxima.\n\n"
        "• 1.0 (Lineal): El movimiento es directo (1:1).\n"
        "• 1.5 - 2.0 (Exponencial): El centro se vuelve muy suave (ideal para\n"
        "  apuntar o corregir rumbo) pero los extremos aceleran agresivamente.\n"
        "• Recomendado: 1.6 para War Thunder/DCS."
    ),
    
    "deadzone": (
        "ZONA MUERTA CENTRAL (%):\n"
        "Área en el centro del stick donde no se registra movimiento.\n\n"
        "Sirve para filtrar vibraciones de la mano o pequeños deslizamientos\n"
        "involuntarios del mouse cuando intentas volar nivelado.\n"
        "• Recomendado: 0.05 (5%)."
    ),
    
    "snap": (
        "MAGNETISMO DE EJES (Axis Snapping):\n"
        "Crea una fuerza invisible que 'pega' el stick a los ejes X o Y.\n\n"
        "Si intentas hacer un looping perfecto (solo eje Y), esto evitará\n"
        "que introduzcas alabeo (eje X) accidentalmente.\n"
        "• Alto: Movimientos robóticos y precisos.\n"
        "• Bajo/Cero: Movimiento orgánico y fluido."
    ),
    
    # --- TRACKER ---
    "t_sens_x": (
        "SENSIBILIDAD YAW (Horizontal):\n"
        "Multiplicador de giro de cabeza izquierda/derecha.\n\n"
        "Define cuánto gira la cámara del juego por cada grado que giras tu cabeza real.\n"
        "• Objetivo: Poder mirar tus 'seis' (atrás) con un giro cómodo de cuello\n"
        "  sin perder de vista el monitor."
    ),
    
    "t_sens_y": (
        "SENSIBILIDAD PITCH (Vertical):\n"
        "Multiplicador de movimiento de cabeza arriba/abajo.\n\n"
        "Generalmente se usa un valor igual o ligeramente menor que en X\n"
        "para mantener estabilidad al mirar instrumentos del panel."
    ),
    
    "t_center_drag": (
        "AUTO-CENTRADO DINÁMICO (Drift Fix):\n"
        "Soluciona el problema de tener que recentrar constantemente.\n\n"
        "El centro 'virtual' perseguirá lentamente la posición de tu nariz.\n"
        "• Si te acomodas en la silla, el tracker se ajustará solo en unos segundos.\n"
        "• 0.0: Desactivado (Centro fijo).\n"
        "• Valor Alto: Se ajusta rápido, pero puede sentirse 'flotante'."
    ),
    
    "t_smooth": (
        "SUAVIZADO (Filtro OneEuro):\n"
        "Elimina los micro-temblores naturales del rostro y el ruido de la cámara.\n\n"
        "• Valor Bajo: Respuesta instantánea, pero la imagen puede vibrar.\n"
        "• Valor Alto: Imagen muy estable y cinematográfica, pero introduce\n"
        "  una pequeña latencia (lag).\n"
        "• Busca el equilibrio donde no sientas mareo."
    ),
    
    "t_deadzone_t": (
        "DEADZONE DEL TRACKER:\n"
        "Congela la cámara si mueves la cabeza muy poco.\n\n"
        "Útil si quieres mantener la vista fija en la mira del cañón\n"
        "sin que tu pulso afecte la puntería."
    ),
    
    "t_snap_axis": (
        "MAGNETISMO DE EJES (Tracker):\n"
        "Ayuda a mirar perfectamente a los lados o arriba sin inclinar la cámara.\n\n"
        "Muy útil para revisar los espejos retrovisores o mirar el panel\n"
        "superior de instrumentos de forma limpia."
    ),
    
    "t_snap_outer": (
        "MAGNETISMO DE BORDES (Look-Behind):\n"
        "Reduce la sensibilidad en los extremos del giro.\n\n"
        "Te ayuda a mantener la vista fija hacia atrás (Check-Six) cómodamente\n"
        "sin que la cámara tiemble o se gire sola."
    )
}

# ==============================================================================
#  CLASE TOOLTIP (Lógica Visual Mejorada)
# ==============================================================================
class ToolTip:
    def __init__(self, widget, text_key):
        self.widget = widget
        self.text = HELP_TEXTS.get(text_key, text_key)
        self.tip_window = None
        self.id = None
        
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        self._unschedule()
        # 300ms de espera para no molestar si pasas rápido
        self.id = self.widget.after(300, self._show)

    def leave(self, event=None):
        self._unschedule()
        self._hide()

    def _unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def _show(self):
        if not self.widget.winfo_exists():
            return
            
        # Calcular posición (ligeramente desplazado del mouse)
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 30
        y = y + self.widget.winfo_rooty() + 20
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True) # Quitar bordes de ventana OS
        tw.wm_geometry(f"+{x}+{y}")
        
        # Frame contenedor para el borde de color
        main_frame = tk.Frame(tw, bg="#252526", highlightthickness=1, highlightbackground="#444")
        main_frame.pack()

        # Borde lateral de acento (Estilo VS Code / Moderno)
        accent_strip = tk.Frame(main_frame, bg=COLOR_ACCENT, width=3)
        accent_strip.pack(side='left', fill='y')
        
        # Etiqueta de texto
        label = tk.Label(main_frame, text=self.text, justify='left',
                       background="#252526", fg="#e0e0e0", 
                       relief='flat', borderwidth=0,
                       font=("Segoe UI", 9), padx=10, pady=8)
        label.pack(side='left')

    def _hide(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

# ==============================================================================
#  FUNCIÓN GENERADORA DE ICONO
# ==============================================================================
def create_help_icon(parent, key):
    """Crea un icono [?] interactivo."""
    icon = tk.Label(parent, text="?", 
                    bg="#333", fg="#aaa",
                    font=("Consolas", 9, "bold"), # Fuente monoespaciada para el ?
                    width=3, cursor="hand2")
    
    # Efecto Hover simple
    def on_enter(e): icon.config(bg=COLOR_ACCENT, fg="black")
    def on_leave(e): icon.config(bg="#333", fg="#aaa")
    
    icon.bind("<Enter>", on_enter, add="+")
    icon.bind("<Leave>", on_leave, add="+")
    
    # Conectar lógica
    ToolTip(icon, key)
    
    return icon