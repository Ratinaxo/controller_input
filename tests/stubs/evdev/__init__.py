from types import SimpleNamespace
_c = dict(EV_SYN=0, EV_KEY=1, EV_REL=2, KEY_ESC=1, KEY_1=2, KEY_P=25, KEY_ENTER=28, KEY_A=30, KEY_COMMA=51,
    KEY_LEFTALT=56, KEY_CAPSLOCK=58, KEY_RIGHTALT=100, KEY_LEFTMETA=125, KEY_RIGHTMETA=126,
    REL_X=0, REL_Y=1, REL_HWHEEL=6, REL_WHEEL=8, BTN_LEFT=272, BTN_RIGHT=273, BTN_MIDDLE=274, BTN_SIDE=275, BTN_EXTRA=276,
    BTN_TRIGGER=0x120, BTN_THUMB=0x121, BTN_THUMB2=0x122, BTN_TOP=0x123, BTN_TOP2=0x124, BTN_PINKIE=0x125,
    BTN_BASE=0x126, BTN_BASE2=0x127, BTN_BASE3=0x128, BTN_BASE4=0x129, BTN_BASE5=0x12a, BTN_BASE6=0x12b,
    BTN_DEAD=0x12f, BTN_A=0x130, BTN_B=0x131, BTN_C=0x132, BTN_0=0x100,
    EV_ABS=3, ABS_X=0, ABS_Y=1, ABS_Z=2, ABS_RX=3, ABS_RY=4, ABS_RZ=5,
    ABS_THROTTLE=6, ABS_RUDDER=7, ABS_WHEEL=8, ABS_GAS=9, ABS_BRAKE=10,
    ABS_HAT0X=16, ABS_HAT0Y=17)
ecodes = SimpleNamespace(**_c)
ecodes.KEY = {v: k for k, v in _c.items() if k.startswith('KEY_')}
ecodes.BTN = {v: (['BTN_LEFT', 'BTN_MOUSE'] if k == 'BTN_LEFT' else k) for k, v in _c.items() if k.startswith('BTN_')}
class InputDevice:
    def __init__(self, p): raise OSError("stub")
def list_devices(): return []
