"""Lo que comparten las pestañas, sin conocer al lanzador.

Las pestañas reciben un AppContext en vez de la ventana principal. Eso
evita importaciones circulares (pestaña <-> lanzador) y permite probar
cada pestaña con un contexto falso.
"""
import queue


class AppContext:
    """Estado compartido de la GUI.

    root:     ventana raíz de Tk (para diálogos y after()).
    config:   la configuración cargada. Se REEMPLAZA entera al cargar un
              perfil, así que nadie debe guardarse una referencia al dict:
              siempre se lee ctx.config.
    tracker:  el HeadTracker actual, o None con fuente externa. Cambia en
              vivo al alternar la fuente de cabeza.
    input_queue: eventos crudos de tecla/botón (código, valor, timestamp)
              que los hilos de evdev dejan para el hilo de Tk.
    camera_view: el widget de la vista de cámara embebida, compartido entre
              el panel derecho (donde vive) y la pestaña Head Tracker (que
              solo trae el botón para mostrarla/ocultarla). Lo rellena el
              lanzador al construir el panel de preview.
    """

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.tracker = None
        self.camera_view = None
        self.input_queue = queue.Queue()
        # Los rellena el lanzador: abren y cierran la cámara propia.
        self.start_head_source = lambda: None
        self.stop_head_source = lambda: None
