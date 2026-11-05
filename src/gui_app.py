"""Lanzador de la GUI de configuración.

utils.GUI_SCRIPT ejecuta este archivo por ruta, así que se queda aquí. Todo
el código de la interfaz vive en src/frontend/:

    frontend/style/       colores, fuentes, espaciado y tema ttk
    frontend/components/  piezas reutilizables (sliders, botones, asistente...)
    frontend/tabs/        una carpeta por pestaña
    frontend/preview/     panel derecho
    frontend/hud/         HUD de vuelo (lo abre el motor)
    frontend/app/         ventana principal, estado compartido, entrada
"""
from frontend.app.launcher import ConfigLauncher

__all__ = ["ConfigLauncher"]

if __name__ == "__main__":
    app = ConfigLauncher()
    app.run()
