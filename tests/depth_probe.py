"""
Fase 0 - Sonda de profundidad (desechable, fuera de src/).

Corre el mismo modelo de MediaPipe que usa el proyecto real (FaceLandmarker,
modo VIDEO, con matriz de transformación facial) y loggea en un CSV, frame
a frame:

  - tx, ty, tz          -> traslación cruda de la matriz 4x4 (columna [:, 3])
  - yaw_deg, pitch_deg  -> los mismos ángulos que ya usa tracker.py, para
                           poder chequear "contaminación cruzada" (girar la
                           cabeza sin acercarse/alejarse no debería mover tz)
  - face_width_px       -> distancia en píxeles entre ojos (lm[33]/lm[263])
  - depth_proxy         -> 1000 / face_width_px, la alternativa "Plan B" si
                           tz no resulta usable

Uso:
    python3 experiments/depth_probe.py --camera 0 --model ../src/models/face_landmarker.task

Controles en la ventana de video:
    q  -> salir y cerrar el CSV
"""
import argparse
import csv
import math
import os
import time

import cv2
import numpy as np
import mediapipe as mp


def matrix_to_euler(matrix):
    R = np.array(matrix)[:3, :3]
    yaw = np.degrees(np.arctan2(-R[2, 0], np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)))
    pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    return yaw, pitch


def main():
    parser = argparse.ArgumentParser(description="Sonda de profundidad (Fase 0)")
    parser.add_argument("--camera", type=int, default=0, help="Índice de cámara (default 0)")
    parser.add_argument("--model", type=str, default="src/models/face_landmarker.task",
                         help="Ruta al .task de MediaPipe (ajustar si tu modelo vive en otro lado)")
    parser.add_argument("--log", type=str, default="depth_probe.csv", help="Archivo CSV de salida")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"[ERROR] No se encontró el modelo en: {args.model}")
        print("        Pasa la ruta correcta con --model /ruta/a/face_landmarker.task")
        return

    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=args.model),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=True,
    )
    landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    cap = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        print(f"[ERROR] No se pudo abrir la cámara índice {args.camera}")
        return

    csv_file = open(args.log, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow(["t", "tx", "ty", "tz", "yaw_deg", "pitch_deg", "face_width_px", "depth_proxy"])

    print(f"[OK] Grabando en '{args.log}'. Moveté la cabeza (adelante/atrás, giros) y presioná 'q' para terminar.")

    start_time = time.time()
    last_ts_ms = 0
    frame_count = 0

    try:
        while True:
            success, frame = cap.read()
            if not success:
                time.sleep(0.05)
                continue

            frame = cv2.flip(frame, 1)
            img_h, img_w, _ = frame.shape
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)

            now = time.time()
            ts_ms = int((now - start_time) * 1000)
            if ts_ms <= last_ts_ms:
                ts_ms = last_ts_ms + 1
            last_ts_ms = ts_ms

            detection = landmarker.detect_for_video(mp_image, ts_ms)

            hud_lines = ["Sin rostro detectado"]

            if detection.face_landmarks:
                lm = detection.face_landmarks[0]

                # Fallback clasico: ancho interocular en pixeles
                eye_l, eye_r = lm[33], lm[263]
                dx = (eye_r.x - eye_l.x) * img_w
                dy = (eye_r.y - eye_l.y) * img_h
                face_width_px = max(math.hypot(dx, dy), 1.0)
                depth_proxy = 1000.0 / face_width_px

                tx = ty = tz = float("nan")
                yaw_deg = pitch_deg = float("nan")

                if detection.facial_transformation_matrixes:
                    matrix = detection.facial_transformation_matrixes[0]
                    tx, ty, tz = matrix[0][3], matrix[1][3], matrix[2][3]
                    yaw_deg, pitch_deg = matrix_to_euler(matrix)

                writer.writerow([f"{now - start_time:.3f}", tx, ty, tz,
                                  yaw_deg, pitch_deg, face_width_px, depth_proxy])
                frame_count += 1
                if frame_count % 30 == 0:  # flush periódico, no en cada frame
                    csv_file.flush()

                hud_lines = [
                    f"tx={tx:.4f}  ty={ty:.4f}  tz={tz:.4f}",
                    f"yaw={yaw_deg:6.1f}  pitch={pitch_deg:6.1f}",
                    f"face_width_px={face_width_px:6.1f}  depth_proxy={depth_proxy:.3f}",
                ]

            for i, line in enumerate(hud_lines):
                cv2.putText(frame, line, (10, 25 + i * 22), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 255, 0), 1, cv2.LINE_AA)

            cv2.imshow("Fase 0 - Sonda de profundidad (q para salir)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        csv_file.close()
        landmarker.close()
        print(f"[OK] {frame_count} frames guardados en '{args.log}'.")


if __name__ == "__main__":
    main()
