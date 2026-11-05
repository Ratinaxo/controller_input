"""Barras bipolares de ejes (-1..1 con el cero al centro).

Las usan el preview del configurador (traslación y roll) y el HUD de vuelo
(traslación). Antes el mismo dibujo estaba escrito dos veces.
"""
from frontend.style import colors as C


class AxisBars:
    """Dibuja una fila por eje en `canvas`: etiqueta, marco, línea de cero y
    la barra que crece desde el centro.

    axes:      [(clave, texto, color), ...] en orden de arriba abajo
    label_x:   x del centro de las etiquetas
    x0, x1:    extremos horizontales de las barras
    y0:        y de la primera fila
    row_step:  distancia entre filas
    font:      fuente de las etiquetas
    """

    def __init__(self, canvas, axes, label_x, x0, x1, y0, row_step, font):
        self.canvas = canvas
        self.center_x = (x0 + x1) // 2
        self.half = (x1 - x0) // 2
        self.bars = {}
        for i, (key, text, color) in enumerate(axes):
            y = y0 + i * row_step
            canvas.create_text(label_x, y + 5, text=text, fill=color, font=font)
            canvas.create_rectangle(x0, y, x1, y + 10, outline=C.BORDER)
            canvas.create_line(self.center_x, y, self.center_x, y + 10, fill=C.AXIS_CENTER)
            bar = canvas.create_rectangle(self.center_x, y + 2, self.center_x, y + 8,
                                          fill=color, outline="")
            self.bars[key] = (bar, y)

    def update(self, values):
        """`values`: {clave: valor en -1..1}. Las claves que falten no se tocan."""
        for key, value in values.items():
            if key not in self.bars:
                continue
            item, y = self.bars[key]
            length = max(-1.0, min(1.0, float(value))) * self.half
            self.canvas.coords(item, self.center_x, y + 2, self.center_x + length, y + 8)
