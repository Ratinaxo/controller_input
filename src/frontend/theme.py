import tkinter as tk
from tkinter import ttk

# Paleta de Colores
COLOR_BG = "#1e1e1e"
COLOR_PANEL = "#2d2d2d"
COLOR_TEXT = "#e0e0e0"
COLOR_ACCENT = "#00e676"
COLOR_ACCENT_DIM = "#00b359"
COLOR_WARN = "#ff3d00"

# Tipografías
FONT_MAIN = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_HEADER = ("Segoe UI", 11, "bold")

def apply_theme():
    """Configura el tema global de TTK"""
    style = ttk.Style()
    style.theme_use('clam')
    
    # Notebook (Pestañas)
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background="#333", foreground="white", 
                    padding=[15, 5], font=FONT_BOLD, borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLOR_PANEL)], 
              foreground=[("selected", COLOR_ACCENT)])
    
    # Frames y Barras
    style.configure("Card.TFrame", background=COLOR_PANEL, relief="flat")