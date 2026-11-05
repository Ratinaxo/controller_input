"""Diagnóstico: ¿por qué el programa no ve la cámara?

El síntoma típico es este par de líneas en el log:

    [GUI] Tracker propio iniciado.
    [ WARN] ... VIDEOIO(V4L2:/dev/video0): select() timeout.

que significa que el nodo SE ABRIÓ pero nunca entregó un frame. El programa
no distingue ese caso de «todavía no llegó el primer frame», así que se queda
esperando para siempre sin decir nada.

La causa más común es que /dev/video0 no sea el nodo de captura. Muchas
cámaras UVC registran dos nodos: uno de vídeo y otro de metadatos. El de
metadatos se abre igual, pero no entrega ni un frame. Como el programa tiene
el índice 0 puesto a mano (backend/tracker.py y backend/motor.py), si el
orden de los nodos cambia, deja de funcionar sin ninguna explicación.

Este script prueba TODOS los nodos y dice cuál entrega imagen de verdad:

    uv run python src/experiments/diagnose_camera.py
    uv run python src/experiments/diagnose_camera.py --frames 10 --espera 5

Cerrá el programa (y OpenTrack, y cualquier pestaña del navegador con la
cámara) antes de correrlo: si otro proceso la tiene agarrada, el informe lo
dice, pero no puede probar nada más.
"""
import argparse
import fcntl
import glob
import os
import struct
import sys
import time

try:
    import cv2
except ImportError as e:
    print(f"No se pudo importar cv2 ({e}).")
    print("Corré esto con:  uv run python src/experiments/diagnose_camera.py")
    sys.exit(1)


# VIDIOC_QUERYCAP: le pregunta al kernel qué es este nodo, sin abrir la
# cámara para capturar. _IOR('V', 0, struct v4l2_capability), 104 bytes.
VIDIOC_QUERYCAP = 0x80685600
CAP_VIDEO_CAPTURE = 0x00000001
CAP_META_CAPTURE = 0x00800000
CAP_DEVICE_CAPS = 0x80000000


def nombre_del_nodo(path):
    """Nombre que le da el kernel, leído de /sys (no necesita abrirlo)."""
    dev = os.path.basename(path)
    try:
        with open(f"/sys/class/video4linux/{dev}/name") as f:
            return f.read().strip()
    except OSError:
        return "(sin nombre)"


def consultar_capacidades(path):
    """(driver, tarjeta, caps) del nodo, o (None, None, error) si no se pudo."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    except OSError as e:
        return None, None, f"no se pudo abrir: {e.strerror}"
    try:
        buf = bytearray(104)
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf)
    except OSError as e:
        os.close(fd)
        return None, None, f"no responde a VIDIOC_QUERYCAP: {e.strerror}"
    os.close(fd)

    driver = bytes(buf[0:16]).split(b"\0")[0].decode(errors="replace")
    tarjeta = bytes(buf[16:48]).split(b"\0")[0].decode(errors="replace")
    capabilities, device_caps = struct.unpack_from("<II", buf, 84)
    # Si el driver rellena device_caps, ese es el que vale para ESTE nodo;
    # capabilities describe el dispositivo físico entero.
    caps = device_caps if (capabilities & CAP_DEVICE_CAPS) else capabilities
    return driver, tarjeta, caps


def describir_caps(caps):
    if caps & CAP_VIDEO_CAPTURE:
        return "captura de vídeo"
    if caps & CAP_META_CAPTURE:
        return "SOLO METADATOS (nunca va a dar imagen)"
    return f"ni captura ni metadatos (0x{caps:08x})"


def fourcc_a_texto(valor):
    v = int(valor)
    if v <= 0:
        return "?"
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


def probar_captura(indice, frames, espera):
    """Abre el índice como lo hace el programa y trata de leer frames."""
    cap = cv2.VideoCapture(indice, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return {"abre": False}

    # Los mismos ajustes que pide backend/tracker.py.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    leidos = 0
    t0 = time.time()
    while leidos < frames and time.time() - t0 < espera:
        exito, frame = cap.read()
        if exito and frame is not None:
            leidos += 1
        else:
            time.sleep(0.05)
    transcurrido = time.time() - t0

    info = {
        "abre": True,
        "frames": leidos,
        "segundos": transcurrido,
        "ancho": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "alto": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fourcc": fourcc_a_texto(cap.get(cv2.CAP_PROP_FOURCC)),
    }
    cap.release()
    return info


def main():
    ap = argparse.ArgumentParser(description="Prueba todos los nodos de cámara.")
    ap.add_argument("--frames", type=int, default=5,
                    help="frames a leer de cada nodo antes de darlo por bueno (5)")
    ap.add_argument("--espera", type=float, default=3.0,
                    help="segundos máximos de espera por nodo (3.0)")
    args = ap.parse_args()

    print("=" * 62)
    print(" DIAGNÓSTICO DE CÁMARA")
    print("=" * 62)
    print(f" Python : {sys.version.split()[0]}")
    print(f" OpenCV : {cv2.__version__}")
    print()

    nodos = sorted(glob.glob("/dev/video*"),
                   key=lambda p: int("".join(c for c in p if c.isdigit()) or -1))
    if not nodos:
        print(" No hay ningún /dev/video*. El sistema no ve NINGUNA cámara:")
        print(" no es un problema del programa. Revisá que esté enchufada,")
        print(" probá otro puerto USB, y mirá `lsusb` y `dmesg | tail`.")
        return 1

    funcionan = []
    for path in nodos:
        indice = int("".join(c for c in path if c.isdigit()))
        driver, tarjeta, caps = consultar_capacidades(path)

        print(f"{path}  «{nombre_del_nodo(path)}»")
        if driver is None:
            print(f"   tipo         : {caps}")
            if "Device or resource busy" in str(caps):
                print("   → otro programa la tiene agarrada. Cerralo y volvé a probar.")
            print()
            continue

        print(f"   driver       : {driver}")
        print(f"   tipo         : {describir_caps(caps)}")

        if not (caps & CAP_VIDEO_CAPTURE):
            print("   → no se prueba: este nodo no puede dar imagen.")
            print()
            continue

        info = probar_captura(indice, args.frames, args.espera)
        if not info["abre"]:
            print("   se abre      : NO (OpenCV lo rechazó)")
            print()
            continue

        print(f"   se abre      : sí")
        if info["frames"] >= args.frames:
            print(f"   entrega      : SÍ · {info['frames']} frames en "
                  f"{info['segundos']:.1f} s")
            print(f"   formato      : {info['ancho']}x{info['alto']} {info['fourcc']}")
            funcionan.append(indice)
        else:
            print(f"   entrega      : NO · {info['frames']} frames en "
                  f"{info['segundos']:.1f} s de espera")
            print("   → este es el «select() timeout»: se abre pero no da imagen.")
        print()

    print("=" * 62)
    if not funcionan:
        print(" NINGÚN nodo entrega imagen.")
        print()
        print(" No es un problema del índice: es la cámara o el driver.")
        print(" Por orden, probá:")
        print("   1. Cerrar todo lo que pueda tenerla: OpenTrack, el navegador,")
        print("      otra instancia de este programa. Después:  fuser -v /dev/video0")
        print("   2. Desenchufarla y enchufarla en otro puerto (mejor USB 2.0:")
        print("      con varios dispositivos USB3 la negociación de ancho de")
        print("      banda falla y da exactamente este timeout).")
        print("   3. Si la máquina vino de suspensión, recargar el driver:")
        print("      sudo modprobe -r uvcvideo && sudo modprobe uvcvideo")
        print("   4. Confirmar con otro programa:  ffplay /dev/video0")
        return 1

    print(f" Nodos que SÍ entregan imagen: {', '.join(str(i) for i in funcionan)}")
    print()
    if 0 in funcionan:
        print(" El índice 0 funciona, que es el que usa el programa.")
        print(" Si aun así no la ves en la GUI, el problema está en otro lado:")
        print(" pasá el log completo.")
    else:
        print(f" El programa tiene el índice 0 puesto a mano, y el 0 NO sirve.")
        print(f" El que hay que usar es el {funcionan[0]}.")
        print()
        print(" Hoy no hay forma de cambiarlo desde la GUI: el índice está")
        print(" escrito en backend/tracker.py y backend/motor.py. Hay que")
        print(" hacerlo configurable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
