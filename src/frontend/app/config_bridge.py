"""Junta la configuración de todas las pestañas y la reparte al cargar un
perfil. Reemplaza a los dos métodos que antes metían la mano en los
widgets de las cuatro pestañas (_get_current_config y la mitad de
_load_profile_dialog)."""

# Orden de las claves en config1.json: el mismo que antes del refactor, para
# que guardar desde la GUI no reordene el archivo del usuario. Las claves
# que no estén aquí van al final.
KEY_ORDER = (
    'radius', 'curve', 'deadzone', 'snap', 'outer',
    't_sens_x', 't_sens_y', 't_min_cutoff', 't_beta', 't_deadzone',
    't_snap_axis', 't_snap_outer', 't_center_drag', 'cam_rotation', 'head_source',
    't_trans_sens_x', 't_trans_sens_y', 't_trans_sens_z',
    't_trans_deadzone_x', 't_trans_deadzone_y', 't_trans_deadzone_z',
    't_trans_curve_x', 't_trans_curve_y', 't_trans_curve_z',
    't_trans_invert_x', 't_trans_invert_y', 't_trans_invert_z',
    't_trans_min_cutoff', 't_trans_beta', 't_trans_min_cutoff_z', 't_trans_beta_z',
    't_neck_height_cm', 't_neck_depth_cm',
    't_sens_roll', 't_roll_deadzone', 'head_roll_limit_deg',
    'controller_profile', 'button_map', 'telemetry_enabled',
    'head_limit_points', 'head_trans_limits', 'mouse_phys', 'keyboard_phys',
)


def ordered(cfg):
    """`cfg` con las claves en el orden de KEY_ORDER."""
    rank = {k: i for i, k in enumerate(KEY_ORDER)}
    return dict(sorted(cfg.items(), key=lambda kv: rank.get(kv[0], len(rank))))


class ConfigBridge:
    """tabs:        en orden de lectura (el del Notebook).
    apply_order: en orden de aplicación. El orden entre Sistema y Botones ya
                 no importa (el selector de mando vive en Botones, que lee
                 su propio combobox); Head Tracker va al final porque
                 cambiar la fuente puede abrir la cámara, y el tracker
                 nuevo tiene que nacer con la configuración ya cargada.
    """

    def __init__(self, ctx, tabs, apply_order=None):
        self.ctx = ctx
        self.tabs = list(tabs)
        self.apply_order = list(apply_order or tabs)

    def read_config(self):
        merged = {}
        for tab in self.tabs:
            merged.update(tab.read_config())
        return ordered(merged)

    def apply_config(self, cfg):
        """Carga `cfg` (por ejemplo, un perfil) en todas las pestañas."""
        self.ctx.config = cfg
        for tab in self.apply_order:
            tab.apply_config(cfg)

    def owners(self):
        """{clave: [títulos de las pestañas que la declaran]}. Un test
        verifica que cada clave tenga exactamente un dueño."""
        out = {}
        for tab in self.tabs:
            for key in tab.owned_keys:
                out.setdefault(key, []).append(tab.title)
        return out
