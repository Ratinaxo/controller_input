"""Pestaña Botones: mando emulado y mapeo tecla/botón físico -> botón del
joystick virtual.

El selector de mando vivía en Sistema (Fase 6 del plan de refactor, punto
pendiente). Se mueve acá porque es quien de verdad lo necesita: elegir un
modelo distinto solo cambia lo que se dibuja en esta pestaña."""
import time
import tkinter as tk
from tkinter import ttk

from evdev import ecodes

from backend.motor import check_profile_codes
from frontend.components import divider, field_label, section_header, note, secondary_button
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS
from frontend.tabs.base import Tab
from frontend.tabs.buttons.capture import ButtonCapture
from utils.controllers import list_controllers, load_controller, code_name, DEFAULT_CONTROLLER_ID

INSTRUCTIONS = ("Pulsa «Asignar» y luego la tecla o el botón del mouse que quieres usar "
                "(Esc cancela). La fila se ilumina cuando presionas su tecla asignada.\n"
                "⚠ El teclado no se captura en exclusiva: el juego también recibe la tecla. "
                "Usa teclas sin otra función en el juego. Los botones del mouse sí son "
                "exclusivos durante el vuelo.")


def parse_button_map(raw):
    """{id: código} del JSON -> {str(id): int(código)}, descartando basura."""
    out = {}
    for k, v in (raw or {}).items():
        try:
            out[str(int(k))] = int(v)
        except (TypeError, ValueError):
            continue
    return out


class ButtonsTab(Tab):
    title = "🎮 Botones"
    owned_keys = ('button_map', 'controller_profile')

    def __init__(self, ctx):
        super().__init__(ctx)
        self.capture = ButtonCapture(parse_button_map(ctx.config.get('button_map')),
                                     ctx.input_queue)
        self.rows = {}
        self.frame = None
        self.lbl_status = None
        self.cb_controller = None

    def build(self, parent):
        pad = S.PAD_TAB
        cfg = self.ctx.config

        # --- MANDO EMULADO ---
        section_header(parent, "MANDO EMULADO", padx=pad, pady=(pad, 5))

        self.controllers = list_controllers()
        names = [c['display_name'] for c in self.controllers]
        self.controller_id_by_name = {c['display_name']: c['id'] for c in self.controllers}

        field_label(parent, "Modelo:", padx=pad)
        self.cb_controller = ttk.Combobox(parent, values=names, state="readonly", width=30)
        self.cb_controller.pack(fill='x', padx=pad, pady=(0, 10))
        self.cb_controller.bind("<<ComboboxSelected>>", lambda e: self.rebuild_rows())
        self._select_controller(cfg.get('controller_profile', DEFAULT_CONTROLLER_ID),
                                fallback_first=True)

        divider(parent, padx=pad)

        section_header(parent, "MAPEO DE BOTONES", pady=(pad, 5))
        note(parent, INSTRUCTIONS, pady=(0, 6))

        self.lbl_status = tk.Label(parent, text="", bg=C.PANEL, fg=C.TEXT_STRONG,
                                   font=FONTS.label, justify='left', wraplength=S.WRAP_MARKER)
        self.lbl_status.pack(anchor='w', padx=pad, pady=(0, 6))

        self.frame = tk.Frame(parent, bg=C.PANEL)
        self.frame.pack(fill='x', padx=pad, pady=(0, pad))

        self.rebuild_rows()

    # --- filas ---
    def rebuild_rows(self):
        if self.frame is None:
            return
        for child in self.frame.winfo_children():
            child.destroy()
        self.rows = {}
        self.capture.labels = {}
        self.capture.capture_id = None

        controller_id = self.controller_id()
        try:
            profile = load_controller(controller_id)
        except Exception as e:
            tk.Label(self.frame, text=f"No se pudo cargar el perfil '{controller_id}': {e}",
                     bg=C.PANEL, fg=C.WARN, wraplength=S.WRAP_BUTTON_WARNING,
                     justify='left').pack(anchor='w')
            return

        warnings = check_profile_codes(profile)
        if warnings:
            tk.Label(self.frame, text="⚠ " + "\n⚠ ".join(warnings),
                     bg=C.PANEL, fg=C.WARN, font=FONTS.note,
                     wraplength=S.WRAP_BUTTON_WARNING, justify='left').pack(anchor='w', pady=(0, 6))

        for entry in profile.get('buttons', []):
            bid = str(entry.get('id'))
            label = entry.get('name', f"Botón {bid}")
            row = tk.Frame(self.frame, bg=C.SURFACE_OFF)
            row.pack(fill='x', pady=1)
            name = tk.Label(row, text=label, bg=C.SURFACE_OFF, fg=C.TEXT_STRONG,
                            font=FONTS.body, width=18, anchor='w')
            name.pack(side='left', padx=(6, 4), pady=3)
            assigned = tk.Label(row, text="", bg=C.CODE_BG, fg=C.ACCENT,
                                font=FONTS.mono, width=16, anchor='w')
            assigned.pack(side='left', padx=4, pady=3)
            secondary_button(row, "✕", command=lambda b=bid: self.clear(b),
                             relief='flat', width=2).pack(side='right', padx=(2, 6), pady=2)
            secondary_button(row, "Asignar", command=lambda b=bid: self.start_capture(b),
                             relief='flat').pack(side='right', padx=2, pady=2)
            self.rows[bid] = {"row": row, "name": name, "assigned": assigned}
            self.capture.labels[bid] = label
        self.refresh_rows()

    def refresh_rows(self):
        for bid, w in self.rows.items():
            code = self.capture.button_map.get(bid)
            w["assigned"].config(text=code_name(code, ecodes) if code is not None else "—")
            if bid == self.capture.capture_id:
                bg = C.CAPTURE
            elif code is not None and code in self.capture.physical_down:
                bg = C.ACCENT
            else:
                bg = C.SURFACE_OFF
            w["row"].config(bg=bg)
            w["name"].config(bg=bg, fg=C.TEXT_ON_ACCENT if bg != C.SURFACE_OFF else C.TEXT_STRONG)

    # --- mando ---
    def controller_id(self):
        cb = self.cb_controller
        if cb is not None and cb.get() in getattr(self, 'controller_id_by_name', {}):
            return self.controller_id_by_name[cb.get()]
        return self.ctx.config.get('controller_profile', DEFAULT_CONTROLLER_ID)

    def _select_controller(self, controller_id, fallback_first=False):
        name = next((c['display_name'] for c in self.controllers if c['id'] == controller_id), None)
        if name:
            self.cb_controller.set(name)
        elif fallback_first and self.controllers:
            self.cb_controller.current(0)

    # --- acciones ---
    def start_capture(self, bid):
        msg = self.capture.start(bid, time.time())
        self.lbl_status.config(text=msg, fg=C.CAPTURE)
        self.refresh_rows()

    def clear(self, bid):
        self.capture.clear(bid)
        self.lbl_status.config(text="", fg=C.TEXT_STRONG)
        self.refresh_rows()

    def process_input(self):
        """Vacía la cola de eventos crudos. Lo llama el lazo de la GUI.
        Devuelve True si hubo eventos o hay una captura en curso (las filas
        se redibujan)."""
        changed, result = self.capture.drain()
        if result is not None:
            ok, msg = result
            self.lbl_status.config(text=msg, fg=C.ACCENT if ok else C.WARN)
        if changed or self.capture.capture_id is not None:
            self.refresh_rows()
        return changed

    # --- configuración ---
    def read_config(self):
        return {
            'button_map': {str(k): int(v) for k, v in self.capture.button_map.items()},
            'controller_profile': self.controller_id(),
        }

    def apply_config(self, cfg):
        self.capture.button_map = parse_button_map(cfg.get('button_map'))
        self._select_controller(cfg.get('controller_profile', DEFAULT_CONTROLLER_ID))
        self.rebuild_rows()
