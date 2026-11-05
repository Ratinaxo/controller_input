"""Textos de ayuda de la pestaña Stick / Mouse.

Cada pestaña es dueña de lo que explica: el icono [?] recibe el texto
directamente, sin pasar por un diccionario global.
"""

HELP = {
    'radius': "RADIO DEL STICK (Recorrido Físico):\n"
        "Define cuántos píxeles debes mover el mouse real para que el\n"
        "joystick virtual llegue a su tope (100%).\n\n"
        "• Valor Bajo (100-200px): Alta sensibilidad. Reacciona rápido con\n"
        "  movimientos cortos de muñeca. Ideal para combate ágil.\n"
        "• Valor Alto (400px+): Alta precisión. Requiere mover más el brazo.\n"
        "  Ideal para vuelo en formación, repostaje o helicópteros.",

    'outer': "SATURACIÓN EXTRA (Outer Deadzone):\n"
        "Recorrido extra permitido más allá del radio máximo.\n\n"
        "Si configuras esto en 50px, el stick sigue al 100% aunque muevas el\n"
        "mouse hasta 50px más allá del límite. Pasado eso, el recorrido se\n"
        "detiene: al volver, el stick empieza a moverse tras como máximo 50px.\n"
        "Útil para garantizar giros máximos sin tener que ser preciso.",

    'curve': "CURVA DE RESPUESTA (Gamma / Linealidad):\n"
        "Modifica la sensibilidad en el centro del stick sin perder velocidad máxima.\n\n"
        "• 1.0 (Lineal): El movimiento es directo (1:1).\n"
        "• 1.5 - 2.0 (Exponencial): El centro se vuelve muy suave (ideal para\n"
        "  apuntar o corregir rumbo) pero los extremos aceleran agresivamente.\n"
        "• Recomendado: 1.6 para War Thunder/DCS.",

    'deadzone': "ZONA MUERTA CENTRAL (%):\n"
        "Área en el centro del stick donde no se registra movimiento.\n\n"
        "Sirve para filtrar vibraciones de la mano o pequeños deslizamientos\n"
        "involuntarios del mouse cuando intentas volar nivelado.\n"
        "Al salir de la zona, la señal parte suavemente desde 0 (sin salto).\n"
        "• Recomendado: 0.05 (5%).",

    'snap': "MAGNETISMO DE EJES (Axis Snapping):\n"
        "Crea una fuerza invisible que 'pega' el stick a los ejes X o Y.\n\n"
        "Si intentas hacer un looping perfecto (solo eje Y), esto evitará\n"
        "que introduzcas alabeo (eje X) accidentalmente.\n"
        "• Alto: Movimientos robóticos y precisos.\n"
        "• Bajo/Cero: Movimiento orgánico y fluido.",
}
