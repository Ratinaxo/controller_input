import os
import re
import subprocess


def get_screen_size():
    """Resolución de pantalla sin depender de Xlib/pyautogui.
    Intenta xrandr (funciona vía XWayland en la mayoría de compositores:
    KDE, GNOME, Hyprland con xwayland habilitado). Si falla (Wayland puro
    sin XWayland, o xrandr no instalado), cae a un valor por defecto.

    Puede sobreescribirse con las variables de entorno SCREEN_W / SCREEN_H
    si necesitas forzar un valor exacto en tu setup:
        SCREEN_W=2560 SCREEN_H=1440 uv run python src/main.py

    Módulo compartido (no vive en backend/motor.py ni en frontend/hud.py)
    porque motor.py importa hud.py, así que hud.py no puede importar de
    vuelta desde motor.py sin crear un import circular.
    """
    env_w, env_h = os.environ.get("SCREEN_W"), os.environ.get("SCREEN_H")
    if env_w and env_h:
        try:
            return int(env_w), int(env_h)
        except ValueError:
            pass

    try:
        out = subprocess.check_output(
            ["xrandr", "--current"], stderr=subprocess.DEVNULL
        ).decode()
        m = re.search(r'current\s+(\d+)\s*x\s*(\d+)', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    print("[DISPLAY] No se pudo detectar resolución vía xrandr, usando 1920x1080 "
          "(fija SCREEN_W/SCREEN_H si necesitas otro valor).", flush=True)
    return 1920, 1080
