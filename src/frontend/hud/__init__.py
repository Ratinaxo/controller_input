"""HUD de vuelo. `from frontend.hud import JoystickHUD` sigue funcionando
igual que cuando el HUD era un solo archivo (lo usa backend/motor.py)."""
from frontend.hud.hud import JoystickHUD

__all__ = ["JoystickHUD"]
