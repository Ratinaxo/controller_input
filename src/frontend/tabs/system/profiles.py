"""Guardar y cargar perfiles de configuración (archivos JSON)."""
import json
from tkinter import filedialog, messagebox


def save_profile_dialog(get_config):
    fn = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
    if not fn:
        return
    try:
        with open(fn, 'w') as f:
            json.dump(get_config(), f, indent=4)
        messagebox.showinfo("Saved", "Perfil guardado.")
    except Exception as e:
        messagebox.showerror("Error", str(e))


def load_profile_dialog(apply_config):
    fn = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
    if not fn:
        return
    try:
        with open(fn, 'r') as f:
            cfg = json.load(f)
        apply_config(cfg)
    except Exception as e:
        messagebox.showerror("Error", str(e))
