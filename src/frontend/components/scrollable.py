"""Pestañas con scroll vertical, ajuste de texto al ancho y rueda del mouse."""
import tkinter as tk
from tkinter import ttk

from frontend.style import colors as C


def is_descendant(widget, ancestor):
    w = widget
    while w is not None:
        if w == ancestor:
            return True
        w = getattr(w, 'master', None)
    return False


class ScrollableTabs:
    """Crea las pestañas de un Notebook con contenido desplazable, y maneja
    la rueda del mouse y el auto-ajuste de texto de todas ellas."""

    def __init__(self, root, notebook):
        self.root = root
        self.notebook = notebook
        self.canvases = []

    def add_tab(self, title):
        """Crea una pestaña cuyo contenido se desplaza verticalmente cuando
        no cabe. Devuelve el frame interior donde se agregan los widgets."""
        outer = tk.Frame(self.notebook, bg=C.PANEL)
        self.notebook.add(outer, text=title)

        canvas = tk.Canvas(outer, bg=C.PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        inner = tk.Frame(canvas, bg=C.PANEL)
        window_id = canvas.create_window((0, 0), window=inner, anchor='nw')

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # El contenido toma siempre el ancho visible (sliders responsivos).
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        self.canvases.append(canvas)
        return inner

    def enable_auto_wrap(self):
        """Las etiquetas de texto largo (o que declaren wraplength) ajustan
        su ancho al de su contenedor, en vez de un valor fijo en píxeles."""
        for canvas in self.canvases:
            enable_auto_wrap(canvas)

    def bind_mousewheel(self):
        # X11/XWayland usa Button-4/5; otros sistemas, MouseWheel.
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self.root.bind_all(seq, self.on_mousewheel, add="+")

    def on_mousewheel(self, event):
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = self.root.nametowidget(widget)
            except Exception:
                return
        for canvas in self.canvases:
            if not is_descendant(widget, canvas):
                continue
            # Solo desplazar si el contenido no cabe.
            bbox = canvas.bbox("all")
            if not bbox or bbox[3] - bbox[1] <= canvas.winfo_height():
                return
            up = getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0
            canvas.yview_scroll(-2 if up else 2, 'units')
            return


def enable_auto_wrap(root_widget):
    """Ajusta el 'wraplength' de las etiquetas largas al ancho real de su
    contenedor. Una etiqueta corta entra solo si declara un wraplength
    (spacing.WRAP_MARKER)."""
    stack = [root_widget]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if isinstance(w, tk.Label) and (
            len(str(w.cget("text"))) > 50 or str(w.cget("wraplength")) not in ("0", "")
        ):
            parent = w.master
            parent.bind(
                "<Configure>",
                lambda e, lbl=w: lbl.config(wraplength=max(150, e.width - 40)),
                add="+",
            )
