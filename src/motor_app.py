import sys
import os
import traceback

# Aseguramos que Python encuentre los módulos en src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# IMPORTAMOS LA CLASE DEL BACKEND
from backend.motor import JoystickBackend

# IMPORTACIÓN DE CONFIGURACIÓN
try:
    from utils.config import load_config
except ImportError as e:
    print(f"[MOTOR APP ERROR] No se pudo importar utils.config: {e}")
    sys.exit(1)

def main():
    # 1. CARGAR CONFIGURACIÓN FRESCA DEL DISCO
    #    Esto es crucial: lee el JSON que la GUI acaba de guardar.
    try:
        config = load_config()
    except Exception as e:
        print(f"[MOTOR APP CRITICAL] Error cargando config: {e}", flush=True)
        sys.exit(1)

    # 2. VERIFICACIÓN VISUAL (FEEDBACK EN CONSOLA)
    #    Esto te permitirá confirmar que los cambios de la GUI llegaron al motor.
    print("\n" + "="*50)
    print(f" [MOTOR APP] INICIANDO VUELO (PID: {os.getpid()})")
    print("="*50)
    print(f" ► Radio Stick:   {config.get('radius')} px")
    print(f" ► Zona Muerta:   {config.get('deadzone')}")
    print(f" ► Curva:         {config.get('curve')}")
    print(f" ► Sens. Head Y:  {config.get('t_sens_y')}")
    print("="*50 + "\n", flush=True)

    # 3. INSTANCIAR EL MOTOR
    try:
        backend = JoystickBackend(config)
    except Exception as e:
        print(f"[MOTOR APP] Error instanciando backend:", flush=True)
        traceback.print_exc()
        sys.exit(1)

    # 4. CORRER EL LOOP PRINCIPAL
    #    backend.run() bloquea aquí hasta que termines de volar
    status = backend.run()

    # 5. LIMPIEZA
    if hasattr(backend, 'cleanup'):
        backend.cleanup()

    # 6. GESTIÓN DE SALIDA PARA EL SUPERVISOR
    if status == "RESTART":
        # Código 0 = "Volver a la GUI"
        print("[MOTOR APP] Solicitando retorno a configuración...", flush=True)
        sys.exit(0)
    else:
        # Código 1 = "Error o Salida Forzosa"
        print("[MOTOR APP] Finalizando proceso.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()