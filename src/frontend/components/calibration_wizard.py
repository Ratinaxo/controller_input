"""Asistente de calibración genérico.

Antes había dos asistentes (giro y traslación) con la misma mecánica
escrita dos veces. Ahora:

  - WizardController: la lógica, SIN Tk. Pasos, captura, estabilidad y
    tiempo límite. Se prueba sin ventana.
  - WizardSpec: lo que distingue a cada asistente (pasos, lectura en vivo,
    cómo se mide la estabilidad, qué función guarda y los textos).
  - open_wizard(): la vista, que solo dibuja y conecta las dos cosas.
"""
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk, messagebox
from typing import Callable, Optional

from frontend.components.buttons import primary_button, secondary_button
from frontend.components.tooltip import ToolTip
from frontend.style import colors as C, spacing as S
from frontend.style.fonts import FONTS

CAPTURE_TIMEOUT_S = 6.0
LIVE_REFRESH_MS = 50

MSG_NOT_RUNNING = "El tracker no está corriendo todavía."
MSG_TIMEOUT = ("No pude leer una posición estable (¿se pierde la cara?). "
               "Quédate quieto y reintenta.")
MARK_TEXT = "Marcar ➜"
RETRY_TEXT = "Reintentar ➜"
HOLD_BUTTON_TEXT = "Mantén la posición…"

CLOSE_TEXT = "✕"
CLOSE_TOOLTIP = ("Cerrar el asistente y volver a la configuración.\n\n"
                 "Se descarta TODO lo calibrado en este asistente: los pasos que\n"
                 "hayas marcado no se guardan y queda la calibración que tenías\n"
                 "antes de abrirlo.\n\n"
                 "También funciona con la tecla Esc.")


class WizardController:
    """Estado del asistente, sin interfaz.

    steps:          [(clave, instrucción), ...]
    stable_spread:  dispersión (en las unidades de la lectura) que se
                    considera "quieto"; la barra de progreso se llena al
                    bajar de 3 veces ese valor
    """

    def __init__(self, steps, stable_spread, timeout_s=CAPTURE_TIMEOUT_S):
        self.steps = list(steps)
        self.stable_spread = float(stable_spread)
        self.timeout_s = float(timeout_s)
        self.index = 0
        self.capturing = False
        self.started = 0.0

    @property
    def step(self):
        return self.steps[self.index]

    @property
    def finished(self):
        return self.index >= len(self.steps)

    def counter_text(self):
        return f"Paso {self.index + 1} de {len(self.steps)}"

    def begin_capture(self, now=None):
        self.capturing = True
        self.started = time.time() if now is None else now

    def progress(self, stats):
        """Porcentaje de la barra de estabilidad (0..100)."""
        spread = stats["spread"] if stats["n"] else float("inf")
        return max(0.0, min(100.0, 100.0 * (1.0 - spread / (self.stable_spread * 3))))

    def poll(self, stats, now=None):
        """Revisa una captura en curso. Devuelve 'stable', 'timeout' o
        'waiting'. Las dos primeras terminan la captura."""
        now = time.time() if now is None else now
        if stats["stable"]:
            self.capturing = False
            return "stable"
        if now - self.started > self.timeout_s:
            self.capturing = False
            return "timeout"
        return "waiting"

    def advance(self):
        """Pasa al paso siguiente. Devuelve True si ya no quedan pasos."""
        self.index += 1
        return self.finished


@dataclass
class WizardSpec:
    """Lo que distingue a un asistente de otro."""
    geometry_key: str                          # clave en spacing.WIZARD_GEOMETRY
    window_title: str
    dialog_title: str                          # título de los messagebox
    external_message: str                      # si la fuente es externa
    steps: list
    stable_spread: float
    stats: Callable                            # stats(tracker) -> dict
    live_text: Callable                        # live_text(tracker) -> str
    calibrate: Callable                        # calibrate(tracker, clave, stats) -> dict
    reject_message: Callable                   # reject_message(result) -> str
    on_saved: Callable                         # on_saved(tracker) tras guardar un paso
    # Para poder cancelar: snapshot() guarda lo calibrado ANTES de abrir, y
    # restore(tracker, valor) lo devuelve tal cual si el usuario cierra a
    # medias. Cada paso se guarda al instante, así que sin esto una
    # calibración a medio hacer quedaría como si fuera la buena.
    snapshot: Callable                         # snapshot() -> valor opaco
    restore: Callable                          # restore(tracker, valor)
    ready_message: str
    hold_message: str
    done_message: str
    wraplength: int = S.WRAP_DIALOG_ROTATION
    hint: Optional[str] = None                 # texto fijo bajo la instrucción
    live_pady: Optional[tuple] = None          # pady de la lectura en vivo
    extra: dict = field(default_factory=dict)


def open_wizard(root, tracker, spec):
    """Abre el asistente modal. Devuelve la ventana, o None si no se puede
    calibrar (fuente externa o tracker detenido)."""
    if tracker is None:
        messagebox.showwarning(spec.dialog_title, spec.external_message)
        return None
    if not tracker.running:
        messagebox.showwarning(spec.dialog_title, MSG_NOT_RUNNING)
        return None

    ctl = WizardController(spec.steps, spec.stable_spread)

    win = tk.Toplevel(root)
    win.title(spec.window_title)
    win.configure(bg=C.PANEL)
    win.geometry(S.WIZARD_GEOMETRY[spec.geometry_key])
    win.transient(root)
    win.grab_set()

    after = {"id": None}
    # Lo calibrado antes de abrir: se devuelve tal cual si se cancela.
    saved = {"before": spec.snapshot(), "committed": False}

    # Cabecera: número de paso a la izquierda, botón de cerrar a la derecha.
    # El botón va DENTRO de la ventana porque no todos los compositores
    # decoran una ventana modal, y sin él el asistente queda sin salida.
    header = tk.Frame(win, bg=C.PANEL)
    header.pack(fill='x', padx=10, pady=(10, 0))

    lbl_step_count = tk.Label(header, text="", bg=C.PANEL, fg=C.TEXT_MUTED, font=FONTS.body)
    lbl_step_count.pack(side='left', padx=(5, 0))

    btn_close = secondary_button(header, CLOSE_TEXT, command=lambda: close(discard=True),
                                 font=FONTS.label, relief='flat', width=3)
    btn_close.pack(side='right')
    ToolTip(btn_close, CLOSE_TOOLTIP)

    lbl_instruction = tk.Label(win, text="", bg=C.PANEL, fg=C.ACCENT,
                               font=FONTS.instruction, wraplength=spec.wraplength,
                               justify='center')
    lbl_instruction.pack(pady=8, padx=15)

    if spec.hint:
        tk.Label(win, text=spec.hint, bg=C.PANEL, fg=C.TEXT_MUTED, font=FONTS.note).pack()

    lbl_live = tk.Label(win, text="", bg=C.PANEL, fg=C.TEXT_SUBTLE, font=FONTS.mono)
    if spec.live_pady is not None:
        lbl_live.pack(pady=spec.live_pady)
    else:
        lbl_live.pack()

    pb = ttk.Progressbar(win, orient='horizontal', mode='determinate',
                         length=S.WIZARD_PROGRESS_LENGTH, maximum=100)
    pb.pack(pady=6)

    lbl_feedback = tk.Label(win, text="", bg=C.PANEL, fg=C.TEXT_STRONG, font=FONTS.body,
                            wraplength=spec.wraplength, justify='center')
    lbl_feedback.pack(pady=5)

    btn_mark = primary_button(win, MARK_TEXT, font=FONTS.button_lg)
    btn_mark.pack(pady=10, ipadx=10, ipady=4)

    def show_step():
        _, text = ctl.step
        lbl_step_count.config(text=ctl.counter_text())
        lbl_instruction.config(text=text)
        lbl_feedback.config(text=spec.ready_message, fg=C.TEXT_STRONG)
        btn_mark.config(state='normal', text=MARK_TEXT)
        pb['value'] = 0

    def live_update():
        # Lectura en vivo, también fuera de la captura.
        if not win.winfo_exists():
            return
        lbl_live.config(text=spec.live_text(tracker))
        if ctl.capturing:
            poll_capture()
        # poll_capture puede haber cerrado la ventana (último paso marcado):
        # reprogramar sobre una ventana destruida es un error de Tk.
        if not win.winfo_exists():
            return
        after["id"] = win.after(LIVE_REFRESH_MS, live_update)

    def poll_capture():
        stats = spec.stats(tracker)
        pb['value'] = ctl.progress(stats)
        status = ctl.poll(stats)
        if status == "stable":
            finish_capture(stats)
        elif status == "timeout":
            btn_mark.config(state='normal', text=RETRY_TEXT)
            lbl_feedback.config(text=MSG_TIMEOUT, fg=C.WARN)

    def finish_capture(stats):
        label, _ = ctl.step
        result = spec.calibrate(tracker, label, stats)
        btn_mark.config(state='normal', text=RETRY_TEXT)

        if not result["ok"]:
            lbl_feedback.config(text=spec.reject_message(result), fg=C.WARN)
            return

        spec.on_saved(tracker)
        if ctl.advance():
            # Terminado: esto SÍ se guarda, así que se cierra sin descartar.
            close(discard=False)
            messagebox.showinfo(spec.dialog_title, spec.done_message)
            return
        show_step()

    def on_mark():
        ctl.begin_capture()
        btn_mark.config(state='disabled', text=HOLD_BUTTON_TEXT)
        lbl_feedback.config(text=spec.hold_message, fg=C.CAPTURE)

    def close(discard=True):
        """Cierra el asistente. Con `discard` (la X, Esc o la X del sistema)
        devuelve la calibración al estado que tenía antes de abrirlo."""
        ctl.capturing = False
        if after["id"]:
            try:
                win.after_cancel(after["id"])
            except Exception:
                pass
            after["id"] = None
        if discard and not saved["committed"]:
            spec.restore(tracker, saved["before"])
        else:
            saved["committed"] = True
        if win.winfo_exists():
            win.destroy()

    btn_mark.config(command=on_mark)
    win.protocol("WM_DELETE_WINDOW", lambda: close(discard=True))
    win.bind("<Escape>", lambda e: close(discard=True))
    show_step()
    live_update()
    win.close = close        # para los tests y para cerrarlo desde fuera
    return win
