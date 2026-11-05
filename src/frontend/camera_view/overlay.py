"""Dibuja el overlay de la vista de cámara sobre un frame BGR de numpy.

Puro respecto a la fuente: no abre la cámara, no lee `cv2.VideoCapture`,
no sabe de Tk ni del tracker. Recibe todo lo que necesita como argumentos
de `draw()` y devuelve el mismo frame anotado. Así se usa igual desde la
ventana de depuración de OpenCV (Fase 1) y, más adelante, desde el widget
embebido (Fase 3), y se puede probar con un frame en blanco sin cámara
real. Ver docs/plan_vista_camara.md.
"""
import cv2

from frontend.style import colors as C

from . import geometry as G


def _hex_to_bgr(value):
    """"#rrggbb" de style/colors.py -> tupla BGR que espera cv2."""
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)


MESH_COLOR = (0, 200, 0)
CENTER_COLOR = (0, 255, 255)        # el punto del centro de la cabeza
REF_CIRCLE_COLOR = (0, 0, 255)      # círculo de la distancia de referencia
FACE_OUTLINE_COLOR = (255, 255, 255)

# Mismos colores que las barras de traslación de la GUI y del HUD: si la
# paleta cambia, este overlay la sigue sin tocarlo.
BOX_COLORS = {
    "ok": _hex_to_bgr(C.ACCENT),
    "warn": _hex_to_bgr(C.CAPTURE),
    "out": _hex_to_bgr(C.WARN),
}
AXIS_COLORS = (
    _hex_to_bgr(C.AXIS_LATERAL),
    _hex_to_bgr(C.AXIS_VERTICAL),
    _hex_to_bgr(C.AXIS_DEPTH),
)
TEXT_COLOR = _hex_to_bgr(C.TEXT_STRONG)

FONT = cv2.FONT_HERSHEY_SIMPLEX

# Largo de las flechas, en fracción del radio del círculo de la cara.
AXIS_LENGTH = 1.4


class CameraOverlay:
    """Dibuja el overlay y recuerda el recuadro de encuadre entre
    llamadas: es estático y solo salta cuando la cara se le sale."""

    def __init__(self, margin_x=G.MARGIN_X, margin_y=G.MARGIN_Y,
                 warn_ratio=G.FRAME_WARN_RATIO):
        self.margin_x = margin_x
        self.margin_y = margin_y
        self.warn_ratio = warn_ratio
        self._box = None
        self.last_state = None

    def reset(self):
        """Olvida el recuadro -- al cambiar de fuente o de resolución el
        anterior ya no tiene sentido."""
        self._box = None
        self.last_state = None

    def draw(self, frame, landmarks, R, ref_x, ref_y, ref_radius,
             rel_deg, rel_cm, mesh_step=4):
        """Anota `frame` (BGR, se modifica en el sitio) y lo devuelve.

        - `landmarks`: los puntos normalizados que entrega MediaPipe
          (objetos con `.x`/`.y` en 0..1). De aquí sale la glabela.
        - `R`: matriz de rotación 3x3 (de `matrix_parts`).
        - `ref_x, ref_y`: centro guardado al recentrar, normalizado (0..1).
        - `ref_radius`: radio de la cara guardado al recentrar, en píxeles
          (o `None`/`0` si todavía no se ha recentrado).
        - `rel_deg`: `(yaw, pitch, roll)` relativos, en grados.
        - `rel_cm`: `(tx, ty, tz)` relativos, en cm.
        """
        h, w = frame.shape[:2]

        for x, y in G.mesh_points(landmarks, w, h, step=mesh_step):
            cv2.circle(frame, (x, y), 1, MESH_COLOR, -1)

        all_pts = G.mesh_points(landmarks, w, h, step=1)
        cx, cy, radius = G.enclosing_circle(all_pts)
        cv2.circle(frame, (cx, cy), radius, FACE_OUTLINE_COLOR, 1, cv2.LINE_AA)

        if ref_radius:
            rx, ry = int(ref_x * w), int(ref_y * h)
            cv2.circle(frame, (rx, ry), int(ref_radius), REF_CIRCLE_COLOR, 1, cv2.LINE_AA)

        face_box = G.bounding_box(all_pts)
        fx, fy, fw, fh = face_box
        cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), FACE_OUTLINE_COLOR, 1)

        # El recuadro se queda donde está mientras la cara le quepa dentro.
        self._box = G.framing_box(self._box, face_box, w, h,
                                  self.margin_x, self.margin_y)
        self.last_state = G.framing_state(face_box, w, h, self.warn_ratio)
        p1, p2 = G.clip_box_to_frame(self._box, w, h)
        if p1 and p2:
            cv2.rectangle(frame, p1, p2, BOX_COLORS[self.last_state], 2)

        # Los ejes nacen en la glabela; el punto marca el centro de la
        # cabeza, por detrás de ella sobre el mismo eje de profundidad.
        glabella = G.landmark_px(landmarks, G.GLABELLA, w, h)
        for (dx, dy), color in zip(G.axis_vectors(R, radius * AXIS_LENGTH), AXIS_COLORS):
            end = (int(glabella[0] + dx), int(glabella[1] + dy))
            cv2.arrowedLine(frame, glabella, end, color, 2, cv2.LINE_AA, tipLength=0.25)
        cv2.circle(frame, G.head_center(glabella, R, radius), 4, CENTER_COLOR, -1)

        yaw, pitch, roll = rel_deg
        tx, ty, tz = rel_cm
        dist_txt = f"  dist {100.0 * radius / ref_radius:+.0f}%" if ref_radius else ""
        cv2.putText(frame, f"yaw {yaw:+.1f}  pitch {pitch:+.1f}  roll {roll:+.1f}{dist_txt}",
                    (10, 20), FONT, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)
        cv2.putText(frame, f"lat {tx:+.1f}cm  vert {ty:+.1f}cm  prof {tz:+.1f}cm",
                    (10, 38), FONT, 0.5, TEXT_COLOR, 1, cv2.LINE_AA)

        nudge = G.nudge_text(face_box, w, h)
        if nudge:
            cv2.putText(frame, nudge, (10, h - 15), FONT, 0.55,
                        BOX_COLORS[self.last_state], 2, cv2.LINE_AA)

        return frame
