"""Contrato de las pestañas del configurador."""


class Tab:
    """Una pestaña del Notebook.

    Cada pestaña es DUEÑA de un conjunto de claves de configuración: las
    lee de sus widgets (read_config) y las escribe en ellos (apply_config).
    Ninguna otra pestaña toca esas claves; config_bridge junta y reparte, y
    un test verifica que ninguna clave tenga dos dueños.
    """

    title = ""
    # Claves de configuración que esta pestaña posee.
    owned_keys = ()

    def __init__(self, ctx):
        self.ctx = ctx

    def build(self, parent):
        """Crea los widgets dentro de `parent` (el frame con scroll)."""
        raise NotImplementedError

    def read_config(self):
        """Devuelve SOLO las claves que posee esta pestaña."""
        return {}

    def apply_config(self, cfg):
        """Pone en los widgets los valores de `cfg` (al cargar un perfil)."""
