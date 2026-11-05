"""Textos de ayuda de la pestaña Head Tracker.

Cada pestaña es dueña de lo que explica: el icono [?] recibe el texto
directamente, sin pasar por un diccionario global.
"""

HELP = {
    't_sens_x': "SENSIBILIDAD YAW (Horizontal):\n"
        "Ganancia del giro de cabeza izquierda/derecha.\n\n"
        "• 10: al llegar al límite calibrado de tu cuello, la cámara llega\n"
        "  a su giro máximo.\n"
        "• 20: llega al máximo a mitad de recorrido (menos giro de cuello).\n"
        "Cambiarla NO obliga a recalibrar el rango de giro.",

    't_sens_y': "SENSIBILIDAD PITCH (Vertical):\n"
        "Ganancia del movimiento de cabeza arriba/abajo.\n\n"
        "Funciona igual que la de Yaw (10 = rango calibrado completo).\n"
        "Generalmente se usa un valor igual o ligeramente menor que en X\n"
        "para mantener estabilidad al mirar instrumentos del panel.",

    't_center_drag': "AUTO-CENTRADO DINÁMICO (Drift Fix):\n"
        "Soluciona el problema de tener que recentrar constantemente.\n\n"
        "Cuando miras cerca del centro, el centro 'virtual' persigue\n"
        "lentamente la orientación real de tu cabeza.\n"
        "• Si te acomodas en la silla, el tracker se ajustará solo en unos segundos.\n"
        "• 0.0: Desactivado (Centro fijo).\n"
        "• Valor Alto: Se ajusta rápido, pero puede sentirse 'flotante'.",

    't_min_cutoff': "ESTABILIDAD EN REPOSO (Filtro OneEuro, Hz):\n"
        "Cuánto se suaviza la vista cuando tienes la cabeza quieta.\n\n"
        "• Valor Bajo (0.3-0.8): Vista muy estable al mirar instrumentos,\n"
        "  pero los movimientos lentos se sienten algo pesados.\n"
        "• Valor Alto (2-5): Respuesta inmediata, pero puede notarse el\n"
        "  temblor de la cámara.\n"
        "• Recomendado: 1.0. Ajusta primero este, con la cabeza quieta.",

    't_beta': "REACCIÓN AL MOVIMIENTO (Filtro OneEuro, beta):\n"
        "Cuánto se reduce el suavizado cuando giras la cabeza rápido.\n\n"
        "• Valor Bajo (0-0.02): Giros rápidos con retraso (lag).\n"
        "• Valor Alto (0.1+): Giros rápidos sin retraso, pero al frenar\n"
        "  puede notarse algo de temblor.\n"
        "• Recomendado: 0.05. Súbelo hasta que el 'check six' no se atrase.",

    't_deadzone_t': "DEADZONE DEL TRACKER:\n"
        "Congela la cámara si mueves la cabeza muy poco.\n\n"
        "Útil si quieres mantener la vista fija en la mira del cañón\n"
        "sin que tu pulso afecte la puntería.",

    't_snap_axis': "MAGNETISMO DE EJES (Tracker):\n"
        "Ayuda a mirar perfectamente a los lados o arriba sin inclinar la cámara.\n\n"
        "Muy útil para revisar los espejos retrovisores o mirar el panel\n"
        "superior de instrumentos de forma limpia.",

    't_snap_outer': "MAGNETISMO DE BORDES (Look-Behind):\n"
        "Reduce la sensibilidad en los extremos del giro.\n\n"
        "Te ayuda a mantener la vista fija hacia atrás (Check-Six) cómodamente\n"
        "sin que la cámara tiemble o se gire sola.",

    't_trans_sens': "SENSIBILIDAD DE TRASLACIÓN (Ganancia):\n"
        "Ganancia POSTERIOR a la calibración, igual que en la rotación.\n\n"
        "• 10: el rango que calibraste da salida completa. Es el valor natural.\n"
        "• 20: salida completa a MITAD del recorrido calibrado (te asomas\n"
        "  más con menos movimiento, a costa de precisión).\n"
        "• 5: necesitas el doble de recorrido para llegar al tope.\n\n"
        "Cambiarla NO obliga a recalibrar: la calibración define el rango\n"
        "real de tu cuerpo, esto solo escala la salida.",

    't_trans_deadzone': "ZONA MUERTA DE TRASLACIÓN (%):\n"
        "Movimiento mínimo antes de que la cámara se desplace.\n\n"
        "La escala se REESCALA, así que no hay salto: al salir de la zona\n"
        "muerta la salida arranca en 0 y sigue llegando al tope.\n\n"
        "• La PROFUNDIDAD necesita más que los otros dos: respirar ya mueve\n"
        "  el valor. Por eso arranca en 6% contra el 3% de los demás.\n"
        "• Súbela hasta que, sentado quieto, la vista no derive sola.",

    't_trans_curve': "CURVA DE TRASLACIÓN (Gamma):\n"
        "Igual que la curva del stick, pero para asomarse.\n\n"
        "• 1.0 (Lineal): el desplazamiento es directo.\n"
        "• 1.5 - 2.0: los movimientos pequeños casi no mueven la cámara\n"
        "  (puedes mantener la vista fija en la mira) pero el tope se sigue\n"
        "  alcanzando al final del recorrido.\n"
        "• Recomendado: 1.5.",

    't_trans_invert': "INVERTIR SENTIDO DEL EJE:\n"
        "Si al inclinarte a un lado la cámara se va al lado contrario,\n"
        "marca esta casilla.\n\n"
        "El sentido depende de la orientación de tu cámara y del sistema de\n"
        "coordenadas que usa MediaPipe, así que no se puede saber de\n"
        "antemano. El asistente de calibración también lo detecta: si\n"
        "rechaza un paso diciendo que el eje va al revés, es esto.",

    't_trans_filter': "FILTRO DE TRASLACIÓN (One Euro):\n"
        "Suavizado de la POSICIÓN de la cabeza, independiente del filtro\n"
        "de la rotación.\n\n"
        "• Estabilidad en reposo (Hz): más bajo = más quieto sentado, pero\n"
        "  más retraso al asomarse.\n"
        "• Reacción (beta): más alto = menos retraso al moverse rápido, a\n"
        "  costa de algo de temblor al frenar.",

    't_trans_filter_z': "FILTRO DE PROFUNDIDAD (eje Z):\n"
        "Parámetros propios para el eje de profundidad, que es el MÁS\n"
        "RUIDOSO de los tres.\n\n"
        "MediaPipe estima la distancia a partir del tamaño aparente de la\n"
        "cara, y esa estimación tiembla bastante más que la posición\n"
        "lateral. Por eso arranca con más suavizado (0.4 Hz contra 0.8).\n\n"
        "Si acercarse al panel se siente con retraso, súbelo; si la vista\n"
        "'respira' sola, bájalo.",

    't_neck': "PIVOTE DEL CUELLO (cm):\n"
        "Tu cabeza gira sobre el cuello, no sobre la cara. Al girar, la cara\n"
        "se DESPLAZA aunque tu cuerpo no se mueva: sin corregirlo, mirar a\n"
        "un lado también mueve la cámara de lado.\n\n"
        "• Alto: cuánto está la cara POR ENCIMA del pivote (típico 10 cm).\n"
        "• Fondo: cuánto está POR DELANTE del pivote (típico 10 cm).\n\n"
        "CÓMO AJUSTARLO: gira la cabeza sin mover el cuerpo y mira las\n"
        "barras de traslación. Si se mueven, ajusta hasta que se queden\n"
        "casi quietas. Si al subir el valor EMPEORA, prueba con negativos:\n"
        "el signo depende del sistema de coordenadas de tu cámara.",

    't_sens_roll': "SENSIBILIDAD DE ROLL (Ganancia):\n"
        "El roll es inclinar la cabeza de lado (oreja al hombro).\n\n"
        "Misma convención que los demás: 10 = el límite en grados de abajo\n"
        "da salida completa.",

    't_roll_deadzone': "ZONA MUERTA DE ROLL (%):\n"
        "Inclinación mínima antes de que la cámara se ladee.\n\n"
        "Conviene dejarla: el roll suele ser un efecto secundario de otros\n"
        "movimientos, no algo que hagas a propósito.",

    'head_roll_limit_deg': "LÍMITE DE ROLL (grados):\n"
        "Cuánto tienes que ladear la cabeza para llegar al tope del eje.\n\n"
        "A diferencia del giro (que usa el octágono calibrado), el roll usa\n"
        "un límite simétrico simple: ladear la cabeza no necesita un\n"
        "asistente de 8 direcciones.\n\n"
        "• 30°: cómodo para la mayoría. Bájalo si te cuesta llegar al tope.",
}
