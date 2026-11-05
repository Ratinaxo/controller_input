"""Widget de Tk que muestra el frame anotado que publica el tracker.

No dibuja el overlay: eso lo hace `overlay.py` dentro del hilo de la
cámara. Aquí solo se recoge el último frame ya anotado, se escala y se
convierte a una imagen que Tk sepa pintar. Ver docs/plan_vista_camara.md,
Fase 3.
"""
import base64
import tkinter as tk

import cv2

from frontend.style import colors as C
from frontend.style.fonts import FONTS

VIEW_W, VIEW_H = 320, 240
REFRESH_MS = 33                  # ~30 fps, la cadencia de la cámara

MSG_EXTERNAL = "La cámara la está usando OpenTrack"
MSG_WAITING = "Esperando a la cámara…"

SHOW_TEXT = "📷 Mostrar cámara"
HIDE_TEXT = "📷 Ocultar cámara"


def fit(frame, size=(VIEW_W, VIEW_H)):
    """Escala `frame` para que quepa en `size` sin deformarlo.

    Nunca lo agranda: si la cámara ya da menos resolución que el panel,
    interpolar hacia arriba solo gasta y se ve peor.
    """
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return frame
    scale = min(size[0] / float(w), size[1] / float(h))
    if scale >= 1.0:
        return frame
    return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)


def to_tk_image(frame, size=(VIEW_W, VIEW_H)):
    """Frame BGR de numpy -> imagen que Tk pueda dibujar, o `None`.

    Camino principal: Pillow, que ya viene instalado (matplotlib lo
    arrastra) y está declarado como dependencia propia porque ahora el
    programa depende de él de verdad.

    Respaldo: `cv2.imencode('.ppm')` en base64, que Tk entiende de forma
    nativa. Hace falta porque Pillow se puede compilar SIN soporte de Tk
    (`PIL._imagingtk`), y en ese caso `ImageTk` existe pero falla al
    usarlo, no al importarlo -- por eso el try envuelve la conversión
    entera y no solo el import.
    """
    small = fit(frame, size)
    try:
        from PIL import Image, ImageTk
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        return ImageTk.PhotoImage(Image.fromarray(rgb))
    except Exception:
        pass
    ok, buffer = cv2.imencode(".ppm", small)      # imencode espera BGR
    if not ok:
        return None
    return tk.PhotoImage(data=base64.b64encode(buffer.tobytes()))


class CameraView:
    """La vista de la cámara con el overlay, embebida en la GUI.

    Se refresca sola y solo reconvierte la imagen cuando el tracker
    publicó un frame nuevo: por eso `latest_frame()` devuelve también un
    contador. Sin eso, con la GUI a 60 Hz y la cámara a 30, la mitad de
    las conversiones serían de la misma imagen.
    """

    def __init__(self, parent, ctx, size=(VIEW_W, VIEW_H),
                 refresh_ms=REFRESH_MS, visible=True):
        self.ctx = ctx
        self.size = size
        self.refresh_ms = refresh_ms
        self.visible = bool(visible)
        self._after_id = None
        self._last_count = None
        # Hay que guardar la referencia a la imagen: si se pierde, Tk la
        # recoge y el canvas se queda en blanco. Es el error clásico.
        self._photo = None

        self.canvas = tk.Canvas(parent, width=size[0], height=size[1],
                                bg=C.CANVAS, highlightthickness=1,
                                highlightbackground=C.BORDER)
        self.image_item = self.canvas.create_image(size[0] // 2, size[1] // 2)
        self.message_item = self.canvas.create_text(
            size[0] // 2, size[1] // 2, text=MSG_WAITING,
            fill=C.TEXT_MUTED, font=FONTS.note)

    # --- empaquetado ------------------------------------------------------
    def pack(self, **kw):
        self._pack_kw = dict(kw)
        if self.visible:
            self.canvas.pack(**kw)
            self.start()
        return self

    # --- encendido y apagado ----------------------------------------------
    def show(self):
        self.visible = True
        self.canvas.pack(**getattr(self, "_pack_kw", {}))
        self.start()

    def hide(self):
        """Oculta la vista Y apaga el dibujo en el tracker: el coste se va
        con ella, que es el sentido del botón."""
        self.visible = False
        self.stop()
        self._set_tracker_overlay(False)
        self._photo = None
        self._last_count = None
        try:
            self.canvas.pack_forget()
        except Exception:
            pass

    def toggle(self):
        self.hide() if self.visible else self.show()
        return self.visible

    # --- lazo -------------------------------------------------------------
    def start(self):
        if self._after_id is None:
            self._schedule()

    def stop(self):
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def destroy(self):
        self.stop()
        self._set_tracker_overlay(False)
        self.canvas.destroy()

    def _schedule(self):
        self._after_id = self.canvas.after(self.refresh_ms, self._tick)

    def _tick(self):
        self._after_id = None
        if not self.canvas.winfo_exists():
            return
        try:
            self.refresh()
        except Exception:
            # El lazo de dibujo nunca debe tumbar la GUI, igual que el
            # lazo principal del lanzador.
            pass
        if self.visible:
            self._schedule()

    # --- contenido --------------------------------------------------------
    def _tracker(self):
        return getattr(self.ctx, "tracker", None)

    def _set_tracker_overlay(self, enabled):
        tracker = self._tracker()
        setter = getattr(tracker, "set_overlay_enabled", None)
        if callable(setter):
            setter(enabled)

    def refresh(self):
        """Una pasada: enciende el overlay si hace falta, y pinta el frame
        nuevo si lo hay."""
        tracker = self._tracker()
        if tracker is None:
            self._show_message(MSG_EXTERNAL)
            return
        # Se enciende en cada pasada, no una sola vez: el tracker se
        # reemplaza en vivo al alternar la fuente de cabeza, y el nuevo
        # nace con el overlay apagado.
        self._set_tracker_overlay(True)

        frame, count = tracker.latest_frame()
        if count == self._last_count:
            return
        self._last_count = count
        if frame is None:
            self._show_message(MSG_WAITING)
            return
        photo = to_tk_image(frame, self.size)
        if photo is None:
            self._show_message(MSG_WAITING)
            return
        self._photo = photo
        self.canvas.itemconfig(self.image_item, image=photo, state='normal')
        self.canvas.itemconfig(self.message_item, text="")

    def _show_message(self, text):
        self._photo = None
        self.canvas.itemconfig(self.image_item, image="", state='hidden')
        self.canvas.itemconfig(self.message_item, text=text)
