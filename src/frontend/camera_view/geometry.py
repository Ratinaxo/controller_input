"""Geometría pura para la vista de cámara: sin cv2, sin cámara, sin Tk.

Todo aquí son funciones sobre números y tuplas -- se prueban sin levantar
una cámara ni tener OpenCV instalado. El módulo que sí dibuja
(`overlay.py`) las usa y les pone encima los colores y el frame.
Ver docs/plan_vista_camara.md.
"""
import math

# Landmark de la GLABELA: el punto liso del frontal, en la línea media,
# justo encima del entrecejo. Es el origen de los tres ejes.
#
# Verificado, no adivinado: se corrió el detector de MediaPipe sobre un
# frame real y se compararon los candidatos habituales. El 9 cae a la
# altura del extremo interno de las cejas (105 y 334) y en la línea
# media; el 8 y el 168 quedan más abajo (radix y nasion, ya sobre el
# puente de la nariz) y el 151 y el 10 más arriba, en la frente.
GLABELLA = 9

# A qué profundidad está el centro de la cabeza por detrás de la glabela,
# como fracción del radio del círculo de la cara. El círculo va de la
# barbilla a la frente (radio ~ media altura de la cara, unos 10 cm), y
# del hueso frontal al centro del cráneo hay unos 8-9 cm.
#
# Mirando de frente el punto queda casi sobre la glabela, porque el
# desplazamiento es en la dirección de la cámara y la proyección es
# ortográfica; se separa al girar la cabeza, que es justo cuando sirve:
# marca el centro de giro, no un punto de la piel.
HEAD_CENTER_DEPTH = 0.85

# Cuánto se agranda la caja de la cara al recalcular el recuadro de
# encuadre, por separado en ancho y alto. No es un margen "en vivo": el
# recuadro se queda quieto, y este margen es la holgura que se le deja al
# recolocarlo -- o sea, cuánto te puedes mover antes del siguiente salto.
#
# Son dos constantes y no una porque el recuadro es un RECTÁNGULO
# APAISADO a propósito: la cara es más alta que ancha (unos 128x153 px a
# 60 cm), así que un margen igual en los dos ejes daba un cuadrado que se
# veía desproporcionado.
#
# Con esa cara de referencia: 197x171 px, más ancho que alto, y un 6 %
# más chico de área que el cuadrado de 189x189 que había antes.
#
# EL COMPROMISO: bajar el alto se come la holgura vertical, porque el
# recuadro tiene que seguir conteniendo la caja de la cara. Con 0.06
# quedan ~9 px arriba y abajo (menos de 1 cm de cabeceo) contra ~35 px a
# los lados, así que al asentir se recoloca bastante seguido. Si molesta,
# MARGIN_Y es la perilla: 0.12 lo devuelve a ~18 px.
MARGIN_X = 0.27
MARGIN_Y = 0.06

# Fracción del tamaño de la cara a la que se avisa en ámbar, antes de que
# la cara llegue a tocar el borde del frame. Con margen 0 el aviso pasaba
# de verde a rojo casi sin ámbar intermedio (plan, hallazgo 3).
#
# 0.15 resultó ser demasiado tarde al medirlo con una cara real: con la
# cara a ~130 px de ancho daban 19 px de aviso, menos de 1,5 cm de
# movimiento. 0.30 da unos 2,5 cm, que sí alcanza para reaccionar.
FRAME_WARN_RATIO = 0.30

# Signo de la Y al proyectar los ejes de la cabeza (columnas de R) sobre
# la imagen, que crece hacia abajo. VERIFICADO contra la cámara real: con
# este signo las flechas apuntan como deben (y al revés de OpenTrack, que
# las tiene invertidas).
AXIS_Y_SIGN = -1


def mesh_points(landmarks, img_w, img_h, step=1):
    """Landmarks normalizados (0..1, con `.x`/`.y`) a píxeles enteros,
    tomando 1 de cada `step`. `step=4` alcanza para confirmar
    visualmente que la detección sigue viva sin recargar el frame;
    `step=1` para el círculo y el recuadro de la cara, con toda la
    precisión posible."""
    return [(int(lm.x * img_w), int(lm.y * img_h))
            for lm in landmarks[::max(1, step)]]


def landmark_px(landmarks, index, img_w, img_h):
    """Un landmark suelto en píxeles enteros."""
    lm = landmarks[index]
    return int(lm.x * img_w), int(lm.y * img_h)


def enclosing_circle(points):
    """Círculo que contiene todos los `points`: (cx, cy, radius) en
    píxeles.

    No es el círculo mínimo -- para eso hace falta un algoritmo aparte
    (p.ej. `cv2.minEnclosingCircle`, o Welzl si se quiere sin cv2). Este
    es más simple: centro = centroide, radio = distancia al punto más
    lejano. Siempre contiene todos los puntos y, para un indicador de
    distancia, lo único que importa es que crezca y se achique de forma
    monótona con el tamaño de la cara -- lo hace igual, sin traer cv2 a
    un módulo que se prueba sin él."""
    if not points:
        return 0, 0, 0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    radius = max(math.hypot(x - cx, y - cy) for x, y in points)
    # ceil, no truncar: redondear el radio hacia abajo podía dejar fuera al
    # punto más lejano (el que define exactamente ese radio).
    return int(round(cx)), int(round(cy)), int(math.ceil(radius))


def bounding_box(points):
    """(x, y, w, h) del rectángulo que contiene todos los `points`."""
    if not points:
        return 0, 0, 0, 0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return x0, y0, x1 - x0, y1 - y0


def box_contains(outer, inner):
    """True si `outer` contiene por completo a `inner`, cajas (x,y,w,h)."""
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ix >= ox and iy >= oy
            and ix + iw <= ox + ow and iy + ih <= oy + oh)


def framing_box(prev, face_box, frame_w, frame_h,
                margin_x=MARGIN_X, margin_y=MARGIN_Y):
    """El recuadro de encuadre: ESTÁTICO mientras la cara quepa dentro.

    Solo se recalcula cuando `face_box` se sale de `prev`, y entonces
    salta de golpe a un recuadro nuevo centrado en la cara. Nada de
    suavizado ni de perseguir la cara frame a frame: un recuadro que se
    mueve todo el rato no dice nada, uno que se queda quieto convierte
    "me salí" en un evento que se ve.

    Es apaisado a propósito (ver MARGIN_X / MARGIN_Y) y se recorta al
    frame, así que contra el borde deja de poder seguir a la cara y la
    caja blanca acaba asomando por fuera."""
    if prev is not None and box_contains(prev, face_box):
        return prev
    fx, fy, fw, fh = face_box
    w = min(fw * (1.0 + 2.0 * margin_x), float(frame_w))
    h = min(fh * (1.0 + 2.0 * margin_y), float(frame_h))
    cx, cy = fx + fw / 2.0, fy + fh / 2.0
    x = min(max(cx - w / 2.0, 0.0), max(0.0, frame_w - w))
    y = min(max(cy - h / 2.0, 0.0), max(0.0, frame_h - h))
    return x, y, w, h


def _overflow(box, frame_w, frame_h):
    """Cuánto se sale `box` de un frame `frame_w`x`frame_h`, en píxeles,
    por cada lado (0 si no se sale por ese lado)."""
    x, y, w, h = box
    left = max(0.0, -x)
    top = max(0.0, -y)
    right = max(0.0, (x + w) - frame_w)
    bottom = max(0.0, (y + h) - frame_h)
    return left, top, right, bottom


def framing_state(face_box, frame_w, frame_h, warn_ratio=FRAME_WARN_RATIO):
    """"ok", "warn" u "out" según lo cerca que está la CARA del borde del
    frame -- que es lo que de verdad importa: no el recuadro, sino si te
    estás saliendo de la cámara.

    "out" en cuanto la cara se recorta contra el borde. "warn" antes de
    eso, cuando el borde más cercano queda a menos de `warn_ratio` del
    tamaño de la propia cara: avisa ANTES de cruzar, no en el instante en
    que ya se cruzó (plan, hallazgo 3)."""
    if _overflow(face_box, frame_w, frame_h) != (0.0, 0.0, 0.0, 0.0):
        return "out"
    x, y, w, h = face_box
    if w <= 0 or h <= 0:
        return "out"
    margins = (x / w, y / h, (frame_w - (x + w)) / w, (frame_h - (y + h)) / h)
    return "warn" if min(margins) < warn_ratio else "ok"


def nudge_text(face_box, frame_w, frame_h):
    """Frase de qué corregir ("muévete a la derecha y arriba"), o `None`
    si la cara todavía cabe entera en el frame."""
    left, top, right, bottom = _overflow(face_box, frame_w, frame_h)
    parts = []
    if left > 0:
        parts.append("a la derecha")
    elif right > 0:
        parts.append("a la izquierda")
    if top > 0:
        parts.append("abajo")
    elif bottom > 0:
        parts.append("arriba")
    if not parts:
        return None
    return "muévete " + " y ".join(parts)


def clip_box_to_frame(box, frame_w, frame_h):
    """`box` recortado al frame, como dos esquinas `(x0, y0), (x1, y1)`
    enteras listas para dibujar. `(None, None)` si no queda nada dentro
    del frame."""
    x, y, w, h = box
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(frame_w, int(round(x + w))), min(frame_h, int(round(y + h)))
    if x1 <= x0 or y1 <= y0:
        return None, None
    return (x0, y0), (x1, y1)


def project(R, vector, y_sign=AXIS_Y_SIGN):
    """Proyección ortográfica de un `vector` en coordenadas de la CABEZA
    sobre la imagen: se aplica `R` y se toman las componentes (x, y),
    invirtiendo la Y porque la de la imagen crece hacia abajo.

    La componente Z del resultado se descarta -- es justamente la que se
    pierde al no tener perspectiva real."""
    vx, vy, vz = (float(v) for v in vector)
    dx = float(R[0][0]) * vx + float(R[0][1]) * vy + float(R[0][2]) * vz
    dy = float(R[1][0]) * vx + float(R[1][1]) * vy + float(R[1][2]) * vz
    return dx, y_sign * dy


def axis_vectors(R, length=40.0, y_sign=AXIS_Y_SIGN):
    """Vector 2D `(dx, dy)` en píxeles de cada uno de los 3 ejes de la
    cabeza -- columnas de `R`, en orden lateral / vertical / profundidad
    -- proyectados sobre la imagen y escalados a `length`.

    La flecha de profundidad casi desaparece cuando la cabeza mira de
    frente: apunta a la cámara y la proyección ortográfica la acorta a
    nada (plan, hallazgo 1)."""
    basis = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return [tuple(c * length for c in project(R, v, y_sign)) for v in basis]


def head_center(glabella_px, R, radius, depth=HEAD_CENTER_DEPTH,
                y_sign=AXIS_Y_SIGN):
    """El centro de la cabeza, en píxeles: `depth * radius` por DETRÁS de
    la glabela, sobre el eje de profundidad de la propia cabeza.

    Es el punto alrededor del cual gira la cabeza, no un punto de la
    piel: mirando de frente cae casi sobre la glabela y se va separando
    al girar, que es cuando sirve de referencia."""
    gx, gy = glabella_px
    dx, dy = project(R, (0.0, 0.0, -float(depth) * float(radius)), y_sign)
    return int(round(gx + dx)), int(round(gy + dy))
