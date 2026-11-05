"""Sección «Asignación en el juego»: orden de los ejes de cada dispositivo."""
from tkinter import messagebox

import rust_motor

from frontend.components import section_header, divider, secondary_button
from frontend.style import spacing as S


def axis_order_text(external):
    """Orden real de los ejes de cada dispositivo virtual.

    El kernel numera los ejes por código ascendente, no por orden de
    registro, así que esta tabla (que viene de Rust) es el orden que va a
    ver el juego al asignar controles."""
    lines = []
    for title, fn_name in (("STICK", "stick_axis_order"), ("CABEZA", "head_axis_order")):
        fn = getattr(rust_motor, fn_name, None)
        axes = None
        if fn is not None:
            try:
                axes = fn()
            except Exception:
                axes = None
        lines.append(f"Dispositivo {title}:")
        if not axes:
            lines.append("   (no disponible: recompila el módulo Rust)")
        else:
            for i, (name, code) in enumerate(axes):
                lines.append(f"   eje {i}: {name}   (0x{code:02x})")
        lines.append("")

    if external:
        lines.append("La fuente de cabeza está en modo externo: el dispositivo de "
                     "cabeza no se crea y sus ejes los publica OpenTrack.")
    else:
        lines.append("Aparecen en el juego como DOS mandos separados.")
    return "\n".join(lines)


class AxisOrderSection:
    def __init__(self, ctx, get_mode):
        self.ctx = ctx
        self.get_mode = get_mode

    def build(self, parent):
        section_header(parent, "ASIGNACIÓN EN EL JUEGO")
        self.btn = secondary_button(parent, "🎛️ Ver orden de los ejes de cada dispositivo",
                                    command=self.show)
        self.btn.pack(fill='x', padx=S.PAD_TAB, pady=(0, 5))
        divider(parent)

    def show(self):
        messagebox.showinfo("Orden de los ejes", axis_order_text(self.get_mode() != 'internal'))
