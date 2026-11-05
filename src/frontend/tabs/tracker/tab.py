"""Pestaña Head Tracker: ensambla las secciones en el orden de siempre."""
from frontend.tabs.base import Tab
from frontend.tabs.tracker.axis_order import AxisOrderSection
from frontend.tabs.tracker.camera import CameraSection
from frontend.tabs.tracker.roll import RollSection
from frontend.tabs.tracker.rotation import RotationSection
from frontend.tabs.tracker.source import HeadSourceSection
from frontend.tabs.tracker.translation import TranslationSection


class TrackerTab(Tab):
    title = "👀 Head Tracker"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.source = HeadSourceSection(ctx)
        self.rotation = RotationSection(ctx)
        self.translation = TranslationSection(ctx)
        self.roll = RollSection(ctx)
        self.axis_order = AxisOrderSection(ctx, self.source.mode)
        self.camera = CameraSection(ctx)
        # Orden visual de arriba abajo.
        self.sections = [self.source, self.rotation, self.translation,
                         self.roll, self.axis_order, self.camera]

    @property
    def owned_keys(self):
        keys = ('head_source',)
        for section in (self.rotation, self.translation, self.roll, self.camera):
            keys += section.owned_keys
        return keys

    def build(self, parent):
        for section in self.sections:
            section.build(parent)

        # Controles que solo aplican cuando la cámara propia es la fuente.
        self.source.dimmable_widgets = (self.rotation.sliders + self.translation.sliders
                                        + self.roll.sliders)
        self.source.dimmable_buttons = (self.rotation.buttons + self.camera.buttons
                                        + self.translation.buttons)
        self.source.refresh_state()

    def read_config(self):
        cfg = {'head_source': self.source.mode()}
        for section in (self.rotation, self.translation, self.roll, self.camera):
            cfg.update(section.read_config())
        return cfg

    def apply_config(self, cfg):
        for section in (self.rotation, self.translation, self.roll, self.camera):
            section.apply_config(cfg)
        # La fuente de cabeza del perfil se aplica en vivo (abre o libera la
        # cámara según corresponda). Va al final: el tracker nuevo se crea
        # con la configuración ya cargada.
        self.source.set_mode(cfg.get('head_source', 'internal'))
