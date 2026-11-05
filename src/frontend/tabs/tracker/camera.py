"""Sección Cámara: el botón que muestra/oculta la vista y la rotación del
video (DroidCam).

La vista misma ya no vive aquí: está en el panel derecho, junto al preview
de ejes (`frontend.preview.head_view`), porque ahí es donde tiene sentido
compararla con el resto de las lecturas del tracker. Esta sección solo
controla el widget compartido a través de `ctx.camera_view`."""
import tkinter as tk
from tkinter import ttk

from frontend.camera_view.widget import SHOW_TEXT, HIDE_TEXT
from frontend.components import section_header, secondary_button, ToolTip
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

ROTATION_OPTIONS = {"0°": 0, "90°": 90, "180°": 180, "270°": 270}

VIEW_TOOLTIP = (
    "Muestra u oculta la cámara en el panel derecho, junto al preview de "
    "ejes: lo que ve la cámara, con el encuadre y la orientación encima.\n\n"
    "• El círculo blanco crece al acercarte y el rojo marca la distancia "
    "a la que recentraste.\n"
    "• El recuadro verde se queda quieto y salta cuando te le sales; en "
    "ámbar estás cerca del borde del encuadre y en rojo ya te saliste.\n"
    "• Las tres flechas salen de la glabela (el entrecejo) y el punto "
    "marca el centro de la cabeza.\n\n"
    "La flecha de profundidad casi desaparece cuando miras de frente: es "
    "correcto, apunta hacia la cámara y se ve de canto.\n\n"
    "Ocultarla también apaga el dibujo, así que no cuesta nada.")


def rotation_label(value):
    return next((label for label, v in ROTATION_OPTIONS.items() if v == int(value)), "0°")


class CameraSection:
    owned_keys = ('cam_rotation',)

    def __init__(self, ctx):
        self.ctx = ctx
        self.view = None
        self.btn_view = None

    def build(self, parent):
        section_header(parent, "CÁMARA")

        # El widget de la vista lo crea el panel derecho (ver
        # `frontend.preview.head_view`), que se construye antes que las
        # pestañas justo para que `ctx.camera_view` ya exista acá. Esta
        # sección solo se queda con la referencia para mostrarla/ocultarla.
        self.view = self.ctx.camera_view

        self.btn_view = secondary_button(parent, HIDE_TEXT, self.toggle_view)
        self.btn_view.pack(anchor='w', padx=S.PAD_TAB, pady=(0, S.SPACE_M))
        ToolTip(self.btn_view, VIEW_TOOLTIP)

        row = tk.Frame(parent, bg=C.PANEL)
        row.pack(fill='x', padx=S.PAD_TAB, pady=5)
        tk.Label(row, text="Rotación del video:", bg=C.PANEL, fg=C.TEXT_STRONG,
                 font=FONTS.label).pack(anchor='w')

        self.cb_rotation = ttk.Combobox(row, values=list(ROTATION_OPTIONS.keys()),
                                        state="readonly", width=10)
        self.cb_rotation.pack(anchor='w', pady=(5, 0))
        self.cb_rotation.set(rotation_label(self.ctx.config.get('cam_rotation', 0)))

    def toggle_view(self):
        visible = self.view.toggle()
        self.btn_view.config(text=HIDE_TEXT if visible else SHOW_TEXT)

    @property
    def buttons(self):
        return [self.cb_rotation, self.btn_view]

    def read_config(self):
        return {'cam_rotation': ROTATION_OPTIONS.get(self.cb_rotation.get(), 0)}

    def apply_config(self, cfg):
        self.cb_rotation.set(rotation_label(cfg.get('cam_rotation', 0)))
