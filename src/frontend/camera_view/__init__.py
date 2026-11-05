"""Vista de cámara con overlay: círculo de distancia, recuadro de encuadre
y flechas de orientación, sobre el frame que ya lee el tracker.

`overlay` es puro dibujo (numpy + cv2, sin cámara ni Tk); `geometry` es la
matemática pura detrás de él (sin cv2 siquiera). El widget de Tk que
muestra esto embebido en la GUI (Fase 3 del plan) se agrega aparte, en
`widget.py`, cuando exista.

Ver docs/plan_vista_camara.md.
"""
from .overlay import CameraOverlay

__all__ = ["CameraOverlay"]
