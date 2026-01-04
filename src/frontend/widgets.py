import tkinter as tk
# Importamos los colores desde nuestro nuevo archivo de tema
from frontend.theme import COLOR_PANEL, COLOR_TEXT, COLOR_ACCENT, FONT_BOLD

class ModernSlider(tk.Frame):
    """Widget compuesto: Etiqueta + Slider + Caja Numérica"""
    def __init__(self, parent, text, from_, to, resolution, initial, command=None):
        super().__init__(parent, bg=COLOR_PANEL)
        self.command = command
        
        # Aseguramos float
        val = float(initial) if initial is not None else from_
        self.var = tk.DoubleVar(value=val)
        
        # Etiqueta
        lbl = tk.Label(self, text=text, bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_BOLD)
        lbl.pack(anchor='w', padx=5, pady=(5,0))
        
        row = tk.Frame(self, bg=COLOR_PANEL)
        row.pack(fill='x', padx=5, pady=5)
        
        # Slider
        self.scale = tk.Scale(row, from_=from_, to=to, resolution=resolution, 
                              variable=self.var, orient='horizontal', 
                              bg=COLOR_PANEL, fg=COLOR_TEXT, 
                              troughcolor="#404040", highlightthickness=0,
                              activebackground=COLOR_ACCENT, command=self._on_change,
                              showvalue=False)
        self.scale.pack(side='left', fill='x', expand=True)
        
        # Caja Numérica
        self.entry = tk.Entry(row, textvariable=self.var, width=5, 
                              bg="#111", fg=COLOR_ACCENT, insertbackground="white",
                              relief="flat", justify="center")
        self.entry.pack(side='right', padx=(10,0))
        self.entry.bind('<Return>', self._on_entry)

    def _on_change(self, val):
        if self.command: self.command()
        
    def _on_entry(self, event):
        try:
            val = float(self.entry.get())
            self.scale.set(val)
            if self.command: self.command()
        except ValueError: pass
        self.focus_set() 

    def get(self): return self.var.get()
    def set(self, val): self.var.set(val)