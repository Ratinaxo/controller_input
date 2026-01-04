import math

class InputPhysics:
    """
    Lógica de física de entrada.
    MODIFICADO: Ahora usa lógica de 'Square Gate' para permitir 
    diagonales al 100% (1.0, 1.0) en lugar de recortarlas circularmente.
    """
    
    @staticmethod
    def apply_axis_curve(value, exponent):
        """Aplica la curva a un solo eje manteniendo el signo."""
        sign = 1 if value >= 0 else -1
        # Aseguramos que el valor absoluto no pase de 1.0 antes de la curva
        val_clamped = min(abs(value), 1.0)
        # Aplicamos curva exponencial
        val_curved = val_clamped ** exponent
        return val_curved * sign
    
    @staticmethod
    def calculate(delta_x, delta_y, config):
        STICK_RADIUS = config['radius']
        SNAP_THRESHOLD = config['snap']
        DEADZONE = config['deadzone'] # Ahora se aplica por eje o radial, veremos abajo
        CURVE = config['curve']
        
        # 1. Normalización inicial (-1.0 a 1.0 teóricamente, pero puede pasarse)
        raw_x = delta_x / STICK_RADIUS
        raw_y = delta_y / STICK_RADIUS

        # 2. Axis Snapping (Magnetismo)
        is_snapped = False
        # Snapping X
        if abs(raw_x) < (abs(raw_y) * config.get('t_snap_axis', 0.1)):
             # Si X es muy pequeño comparado con Y, forzamos X a 0 (Solo vertical)
             pass 
        
        # Implementación simple de snap al centro de los ejes
        if abs(raw_x) < SNAP_THRESHOLD:
            raw_x = 0.0
            is_snapped = True
        if abs(raw_y) < SNAP_THRESHOLD:
            raw_y = 0.0
            is_snapped = True

        # 3. Deadzone RADIAL (Para que el centro siga sintiéndose orgánico)
        # Seguimos usando magnitud para el deadzone para no tener un "cuadrado muerto" en el centro
        raw_mag = math.hypot(raw_x, raw_y)
        in_deadzone = False
        
        final_x = 0.0
        final_y = 0.0

        if raw_mag < DEADZONE:
            in_deadzone = True
        else:
            # 4. CÁLCULO INDEPENDIENTE (La clave de las diagonales)
            # En lugar de normalizar el vector, procesamos X e Y por separado.
            # Esto permite llegar a (1.0, 1.0) en las esquinas.
            
            # Re-escalamos suavemente para evitar el salto del deadzone
            # (Esto es opcional, pero mejora la precisión fina)
            
            final_x = InputPhysics.apply_axis_curve(raw_x, CURVE)
            final_y = InputPhysics.apply_axis_curve(raw_y, CURVE)

        # 5. Saturación (Clamping) INDEPENDIENTE
        # Si el usuario mueve el mouse muy lejos, cortamos en 1.0, 
        # pero NO unimos los ejes. Esto forma un CUADRADO de límites.
        final_x = max(min(final_x, 1.0), -1.0)
        final_y = max(min(final_y, 1.0), -1.0)

        return final_x, final_y, {
            'is_snapped': is_snapped,
            'in_deadzone': in_deadzone,
            'raw_mag': raw_mag
        }