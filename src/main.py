import subprocess
import sys
import time
from utils.utils import GUI_SCRIPT, MOTOR_SCRIPT

PYTHON_EXEC = sys.executable 

def main():
    print("==========================================")
    print("   SUPERVISOR DE PROCESOS - INICIANDO     ")
    print("==========================================")
    print(f"[INFO] Python: {PYTHON_EXEC}")

    while True:
        # ---------------------------------------------------------
        # FASE 1: EJECUTAR GUI
        # ---------------------------------------------------------
        print("\n>>> [SUPERVISOR] Lanzando GUI...")
        try:
            # Agregamos "-u" para ver logs al instante
            result_gui = subprocess.run([PYTHON_EXEC, "-u", str(GUI_SCRIPT)])
            exit_code = result_gui.returncode
        except KeyboardInterrupt:
            print("\n[SUPERVISOR] Detenido por usuario.")
            break

        if exit_code == 0:
            print("[SUPERVISOR] Salida manual (Código 0). Apagando.")
            break
        elif exit_code == 10:
            print("[SUPERVISOR] GUI solicitó vuelo. Iniciando Motor...")
        else:
            print(f"[SUPERVISOR] GUI crasheó (Código {exit_code}). Reiniciando en 2s...")
            time.sleep(2)
            continue

        # ---------------------------------------------------------
        # FASE 2: ENFRIAMIENTO
        # ---------------------------------------------------------
        time.sleep(1.0)

        # ---------------------------------------------------------
        # FASE 3: EJECUTAR MOTOR
        # ---------------------------------------------------------
        print("\n>>> [SUPERVISOR] Lanzando MOTOR...")
        try:
            # Agregamos "-u" aquí también
            result_motor = subprocess.run([PYTHON_EXEC, "-u", str(MOTOR_SCRIPT)])
            motor_code = result_motor.returncode
        except KeyboardInterrupt:
            print("\n[SUPERVISOR] Detenido durante vuelo.")
            break
        
        # Si el motor devuelve 0, vuelve a la GUI (comportamiento normal de "Atrás")
        # Si devuelve 1, hubo un error real.
        if motor_code != 0:
            print(f"[SUPERVISOR] Motor finalizó con error (Código {motor_code}).")
            print("Revisa los logs de arriba.")
            time.sleep(2) # Pausa para leer el error
        else:
            print(f"[SUPERVISOR] Motor finalizado correctamente. Volviendo a GUI...")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()