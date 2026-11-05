"""Pestaña Sistema: telemetría, dispositivos y perfiles.

El selector de mando emulado vivía acá; se mudó a Botones (Fase 6 del plan
de refactor), que es quien de verdad lo necesita para dibujar sus filas."""
import tkinter as tk
from tkinter import ttk

from frontend.components import (
    section_header, divider, note, field_label, secondary_button, checkbox,
)
from frontend.style import spacing as S
from frontend.tabs.base import Tab
from frontend.tabs.system.devices import get_device_list, phys_from_entry, select_by_phys
from frontend.tabs.system.profiles import save_profile_dialog, load_profile_dialog

TELEMETRY_NOTE = ("Guarda CSVs en src/logs/ durante el vuelo. Analízalos después con "
                  "experiments/plot_session.py -- no hay ninguna vista en vivo.")


class SystemTab(Tab):
    title = "Sistema"
    owned_keys = ('telemetry_enabled', 'mouse_phys', 'keyboard_phys')

    def __init__(self, ctx, get_config=None, apply_config=None):
        super().__init__(ctx)
        # Los perfiles guardan y cargan la configuración de TODAS las
        # pestañas: el lanzador pasa las funciones de config_bridge.
        self.get_config = get_config
        self.apply_config_all = apply_config

    def build(self, parent):
        pad = S.PAD_TAB
        cfg = self.ctx.config

        # --- TELEMETRÍA (diagnóstico post-vuelo) ---
        self.var_telemetry = tk.BooleanVar(value=bool(cfg.get('telemetry_enabled', False)))
        checkbox(parent, "Grabar telemetría para diagnóstico (post-vuelo)",
                 self.var_telemetry).pack(anchor='w', padx=pad, pady=(0, 5))
        note(parent, TELEMETRY_NOTE, padx=pad, pady=(0, 10), wrap=False)

        divider(parent, padx=pad)

        # --- DISPOSITIVOS DE ENTRADA ---
        section_header(parent, "DISPOSITIVOS DE ENTRADA", padx=pad, pady=(pad, 5))
        devices = get_device_list()

        field_label(parent, "Mouse Principal:", padx=pad)
        self.cb_mouse = ttk.Combobox(parent, values=devices, state="readonly", width=30)
        self.cb_mouse.pack(fill='x', padx=pad, pady=(0, 10))

        field_label(parent, "Teclado Principal:", padx=pad)
        self.cb_keyboard = ttk.Combobox(parent, values=devices, state="readonly", width=30)
        self.cb_keyboard.pack(fill='x', padx=pad, pady=(0, 10))

        divider(parent, padx=pad)

        # --- PERFILES ---
        section_header(parent, "PERFILES", padx=pad, pady=(5, 10))
        secondary_button(parent, "Guardar Perfil Como...",
                         command=lambda: save_profile_dialog(self.get_config)
                         ).pack(fill='x', padx=pad, pady=5)
        secondary_button(parent, "Cargar Perfil...",
                         command=lambda: load_profile_dialog(self.apply_config_all)
                         ).pack(fill='x', padx=pad, pady=5)

        self.preload_devices()

    # --- dispositivos ---
    def preload_devices(self):
        select_by_phys(self.cb_mouse, self.ctx.config.get('mouse_phys', ''))
        select_by_phys(self.cb_keyboard, self.ctx.config.get('keyboard_phys', ''))

    # --- configuración ---
    def read_config(self):
        cfg = {'telemetry_enabled': bool(self.var_telemetry.get())}
        for key, combo in (('mouse_phys', self.cb_mouse), ('keyboard_phys', self.cb_keyboard)):
            phys = phys_from_entry(combo.get())
            if phys:
                cfg[key] = phys
            elif self.ctx.config.get(key):
                cfg[key] = self.ctx.config[key]
        return cfg

    def apply_config(self, cfg):
        self.preload_devices()
        self.var_telemetry.set(bool(cfg.get('telemetry_enabled', False)))
