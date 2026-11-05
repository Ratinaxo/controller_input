"""Sección «Fuente de datos de cabeza»: cámara propia u OpenTrack."""
from tkinter import ttk

from backend.tracker import HEAD_SOURCES
from frontend.components import section_header, divider, note
from frontend.style import colors as C, spacing as S

NOTE_INTERNAL = "Este programa publica su propio dispositivo de cabeza (6 ejes) y usa la cámara."
NOTE_EXTERNAL = ("La cámara queda libre para OpenTrack, que publica su propio "
                 "joystick con los 6 ejes. Aquí los ejes de cabeza van centrados "
                 "y los ajustes de abajo no se aplican; se conservan para cuando "
                 "vuelvas a la cámara propia.")


class HeadSourceSection:
    """Selector de fuente y atenuado del resto de los controles del tracker.

    `dimmable_widgets` (sliders) y `dimmable_buttons` los rellena la pestaña
    con los controles de las demás secciones: solo aplican cuando la fuente
    es la cámara propia.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.by_name = {v: k for k, v in HEAD_SOURCES.items()}
        self.combo = None
        self.note = None
        self.dimmable_widgets = []
        self.dimmable_buttons = []

    def build(self, parent):
        pad = S.PAD_TAB
        section_header(parent, "FUENTE DE DATOS DE CABEZA", pady=(pad, 5))

        self.combo = ttk.Combobox(parent, values=list(HEAD_SOURCES.values()),
                                  state="readonly", width=30)
        self.combo.pack(fill='x', padx=pad, pady=(0, 5))
        current = self.ctx.config.get('head_source', 'internal')
        self.combo.set(HEAD_SOURCES.get(current, HEAD_SOURCES['internal']))
        self.combo.bind("<<ComboboxSelected>>", self.on_change)

        self.note = note(parent, "")
        divider(parent)

    def mode(self):
        combo = self.combo
        if combo is not None and combo.get() in self.by_name:
            return self.by_name[combo.get()]
        return self.ctx.config.get('head_source', 'internal')

    def set_mode(self, mode):
        """Selecciona `mode` en el combo (al cargar un perfil) y lo aplica."""
        if self.combo is not None:
            self.combo.set(HEAD_SOURCES.get(mode, HEAD_SOURCES['internal']))
        self.on_change()

    def on_change(self, event=None):
        """Aplica el cambio en vivo: abre o cierra la cámara al instante, para
        no tener que reiniciar la GUI al alternar con OpenTrack."""
        mode = self.mode()
        self.ctx.config['head_source'] = mode
        if mode == 'internal':
            self.ctx.start_head_source()
        else:
            self.ctx.stop_head_source()
        self.refresh_state()

    def refresh_state(self):
        """Atenúa los controles del tracker cuando no los usa este programa."""
        internal = self.mode() == 'internal'
        for widget in self.dimmable_widgets:
            try:
                widget.set_enabled(internal)
            except Exception:
                pass
        for btn in self.dimmable_buttons:
            try:
                if internal:
                    # Un Combobox habilitado va en 'readonly', no en 'normal'
                    # (si no, el usuario podría escribir valores inválidos).
                    btn.config(state='readonly' if isinstance(btn, ttk.Combobox) else 'normal')
                else:
                    btn.config(state='disabled')
            except Exception:
                pass
        if self.note is not None:
            if internal:
                self.note.config(text=NOTE_INTERNAL, fg=C.TEXT_MUTED)
            else:
                self.note.config(text=NOTE_EXTERNAL, fg=C.WARN)
