"""tkinter falso: suficiente para ejecutar de verdad el código que construye
la GUI, sin display ni el paquete python3-tk.

No dibuja nada: cada widget registra los argumentos con que se creó, cómo
se empaquetó y los ítems que se dibujaron en él. Con eso se puede:

  - detectar lo que un test de lógica no ve (atributos mal escritos,
    controles que se leen pero nunca se crean, valores que no sobreviven
    el viaje de widget a configuración);
  - sacar una instantánea del árbol completo (tests/gui_snapshot.py) y
    comprobar que un refactor no cambió nada de lo que se ve.
"""
import sys
import types

# Registro de estilos ttk (apply_theme): lo lee la instantánea.
STYLE_LOG = []


class W:
    """Widget genérico. Guarda sus argumentos, su empaquetado y sus hijos."""

    def __init__(self, parent=None, *args, **kw):
        self.kw = dict(kw)
        self.children = []
        self.master = parent if isinstance(parent, W) else None
        self.pack_kw = None
        self.manager = None
        self.items = []          # ítems de canvas, en orden de creación
        self.bindings = []       # (secuencia, callback)
        self.protocol_handlers = {}   # WM_DELETE_WINDOW y compañía
        self.after_ids = []           # temporizadores programados
        self.cancelled_after = []     # y los que se cancelaron
        self.pending_after = []       # (id, callback, args) sin ejecutar
        self.tab_text = None     # si es una pestaña de un Notebook
        self.pane_kw = None      # si es un panel de un PanedWindow
        self.destroyed = False
        if self.master is not None:
            self.master.children.append(self)

    # --- geometría -----------------------------------------------------------
    def pack(self, **kw):
        self.pack_kw = dict(kw)
        self.manager = "pack"

    def grid(self, **kw):
        self.pack_kw = dict(kw)
        self.manager = "grid"

    def place(self, **kw):
        self.pack_kw = dict(kw)
        self.manager = "place"

    def pack_forget(self):
        self.pack_kw = None
        self.manager = None

    forget = pack_forget
    grid_forget = pack_forget

    # --- configuración -------------------------------------------------------
    def config(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw.update(cnf)
        self.kw.update(kw)

    configure = config

    def cget(self, key):
        return self.kw.get(key, "")

    def __getitem__(self, key):
        return self.kw.get(key, "")

    def __setitem__(self, key, value):
        self.kw[key] = value

    def bind(self, sequence=None, func=None, add=None):
        self.bindings.append((sequence, func))

    def bind_all(self, sequence=None, func=None, add=None):
        self.bindings.append((sequence, func))

    # --- ciclo de vida ---------------------------------------------------------
    def destroy(self):
        self.destroyed = True
        if self.master is not None and self in self.master.children:
            self.master.children.remove(self)

    def winfo_children(self):
        return list(self.children)

    def winfo_exists(self):
        return not self.destroyed

    def winfo_width(self):
        return 300

    def winfo_height(self):
        return 200

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return 0

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def focus_set(self):
        pass

    def after(self, ms, func=None, *args):
        # No ejecuta el callback en el momento: lo deja pendiente, para que
        # el test decida cuándo corre (run_pending_after) y para poder
        # comprobar que se cancela al cerrar.
        ident = f"after#{len(self.after_ids)}#{id(func)}"
        self.after_ids.append(ident)
        self.pending_after.append((ident, func, args))
        return ident

    def after_cancel(self, ident):
        self.cancelled_after.append(ident)

    def run_pending_after(self, limit=1):
        """Ejecuta hasta `limit` callbacks de after() que no se cancelaron.

        Con límite, porque los lazos de la GUI se reprograman solos: sin él,
        ejecutar todo lo pendiente no terminaría nunca.
        """
        ran = 0
        while self.pending_after and ran < limit:
            ident, func, args = self.pending_after.pop(0)
            if ident in self.cancelled_after:
                continue
            if callable(func):
                func(*args)
            ran += 1
        return ran

    def update(self):
        pass

    def update_idletasks(self):
        pass

    def nametowidget(self, name):
        return name

    # --- ventanas (Tk / Toplevel) --------------------------------------------
    def title(self, text=None):
        if text is not None:
            self.kw["title"] = text

    def geometry(self, spec=None):
        if spec is not None:
            self.kw["geometry"] = spec

    wm_geometry = geometry

    def minsize(self, w=None, h=None):
        self.kw["minsize"] = [w, h]

    def protocol(self, name=None, func=None):
        if name is not None and func is not None:
            self.protocol_handlers[name] = func

    def transient(self, master=None):
        pass

    def grab_set(self):
        pass

    def mainloop(self):
        pass

    def attributes(self, *args):
        if len(args) >= 2:
            self.kw.setdefault("attributes", {})[str(args[0])] = args[1]

    wm_attributes = attributes

    def overrideredirect(self, flag=None):
        if flag is not None:
            self.kw["overrideredirect"] = bool(flag)

    wm_overrideredirect = overrideredirect

    def deiconify(self):
        self.kw["visible"] = True

    def withdraw(self):
        self.kw["visible"] = False

    # --- canvas ------------------------------------------------------------------
    def _item(self, kind, args, kw):
        item = {"kind": kind, "coords": list(args), "kw": dict(kw)}
        self.items.append(item)
        return len(self.items)          # id de ítem, como en Tk (empieza en 1)

    def create_rectangle(self, *a, **kw): return self._item("rectangle", a, kw)
    def create_line(self, *a, **kw): return self._item("line", a, kw)
    def create_oval(self, *a, **kw): return self._item("oval", a, kw)
    def create_text(self, *a, **kw): return self._item("text", a, kw)
    def create_window(self, *a, **kw): return self._item("window", a, kw)
    def create_image(self, *a, **kw): return self._item("image", a, kw)

    def _get_item(self, ident):
        if isinstance(ident, int) and 1 <= ident <= len(self.items):
            return self.items[ident - 1]
        return None

    def coords(self, ident, *args):
        item = self._get_item(ident)
        if item is not None and args:
            flat = []
            for a in args:
                flat.extend(a if isinstance(a, (list, tuple)) else [a])
            item["coords"] = flat

    def itemconfig(self, ident, **kw):
        item = self._get_item(ident)
        if item is not None:
            item["kw"].update(kw)

    itemconfigure = itemconfig

    def delete(self, *idents):
        if "all" in idents:
            self.items = []

    def bbox(self, *args):
        return (0, 0, 0, 0) if args and args[0] == "insert" else None

    def yview(self, *args):
        pass

    def yview_scroll(self, *args):
        pass

    # --- valores (Combobox, Scale, Entry, Progressbar) -------------------------
    def set(self, v):
        self.kw["value"] = v

    def get(self):
        return self.kw.get("value", 0)

    def current(self, index=None):
        values = list(self.kw.get("values", []))
        if index is not None and 0 <= index < len(values):
            self.kw["value"] = values[index]

    # --- contenedores -----------------------------------------------------------
    def add(self, child, **kw):
        """Notebook.add (text=) y PanedWindow.add (weight=)."""
        if "text" in kw:
            child.tab_text = kw["text"]
        else:
            child.pane_kw = dict(kw)

    def invoke(self):
        cmd = self.kw.get("command")
        if callable(cmd):
            return cmd()


class PhotoImage:
    """tk.PhotoImage falso: solo guarda con qué se creó. Sirve para
    comprobar que la vista de cámara convierte la imagen y, sobre todo,
    que se guarda la referencia (si Tk la pierde, el canvas se queda en
    blanco: es el error clásico)."""

    def __init__(self, data=None, **kw):
        self.data = data
        self.kw = dict(kw)

    def width(self):
        return 0

    def height(self):
        return 0


class Var:
    def __init__(self, master=None, value=None, **kw):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class Style:
    def __init__(self, *a, **kw):
        pass

    def theme_use(self, name=None):
        if name is not None:
            STYLE_LOG.append(["theme_use", name, {}])

    def configure(self, style, **kw):
        STYLE_LOG.append(["configure", style, dict(kw)])

    def map(self, style, **kw):
        STYLE_LOG.append(["map", style, {k: [list(x) for x in v] for k, v in kw.items()}])


class TextValue(W):
    """Widgets cuyo valor es texto (Entry, Combobox): vacíos devuelven "",
    como en Tk real. Devolver 0 hacía fallar código que busca en el texto."""

    def get(self):
        return self.kw.get("value", "")


def build():
    tk = types.ModuleType("tkinter")
    for name in ("Frame", "Label", "Button", "Checkbutton", "Canvas", "Scale",
                 "Toplevel", "Tk", "LabelFrame", "Text", "Listbox", "Radiobutton"):
        setattr(tk, name, type(name, (W,), {}))
    tk.Entry = type("Entry", (TextValue,), {})
    tk.DoubleVar = Var
    tk.BooleanVar = Var
    tk.StringVar = Var
    tk.IntVar = Var
    tk.TclError = RuntimeError
    tk.PhotoImage = PhotoImage

    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Progressbar", "Notebook", "Scrollbar", "Frame",
                 "PanedWindow", "Label", "Button", "Checkbutton"):
        setattr(ttk, name, type(name, (W,), {}))
    ttk.Combobox = type("Combobox", (TextValue,), {})
    ttk.Style = Style
    tk.ttk = ttk

    font = types.ModuleType("tkinter.font")
    font.families = lambda root=None: ()      # sin display no hay familias
    tk.font = font

    for sub, mod in (("ttk", ttk), ("font", font),
                     ("filedialog", types.ModuleType("tkinter.filedialog")),
                     ("messagebox", types.ModuleType("tkinter.messagebox"))):
        setattr(tk, sub, mod)
        sys.modules[f"tkinter.{sub}"] = mod
    sys.modules["tkinter"] = tk
    STYLE_LOG.clear()
    return tk
