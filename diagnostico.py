"""
Diagnóstico de detección de tablas, filas y columnas.

Genera imágenes de debug en ./debug/ para inspeccionar visualmente qué 
está detectando el pipeline.
"""

import os
import sys
import cv2
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_3_tablas_geometria, aislar_lineas_morfologicas
from ocr.rows import obtener_filas_y_columnas_tabla


def main(pdf_path):
    os.makedirs("debug", exist_ok=True)

    print(f"Procesando: {pdf_path}")
    imagenes = pdf_a_imagenes(pdf_path, dpi=300)
    img = imagenes[0]

    prep = preprocesar_imagen(img)
    binaria = prep["binaria"]

    cv2.imwrite("debug/01_binaria.png", binaria)

    tablas = detectar_3_tablas_geometria(binaria)
    print(f"Tablas detectadas: {len(tablas)}")

    nombres = ["E", "P", "H"]
    filas_esperadas = [33, 47, 38]

    for i, (t, nombre, n_filas) in enumerate(zip(tablas, nombres, filas_esperadas)):
        roi = t["roi_binaria"]
        h, w = roi.shape
        print(f"\n=== Bloque {nombre} ===")
        print(f"  ROI: {w}x{h} en x={t['x']}, y={t['y']}")

        cv2.imwrite(f"debug/02_{nombre}_roi.png", roi)

        # Detectar líneas morfológicas
        inv = cv2.bitwise_not(roi)
        lineas_h, lineas_v = aislar_lineas_morfologicas(inv)

        cv2.imwrite(f"debug/03_{nombre}_lineas_h.png", lineas_h)
        cv2.imwrite(f"debug/03_{nombre}_lineas_v.png", lineas_v)

        # Proyección Y (filas)
        proy_y = np.sum(lineas_h, axis=1)
        print(f"  proy_y: max={proy_y.max()}, mean={proy_y.mean():.1f}, "
              f"percentil_75={np.percentile(proy_y, 75):.0f}")

        # Proyección X (columnas)
        proy_x = np.sum(lineas_v, axis=0)
        print(f"  proy_x: max={proy_x.max()}, mean={proy_x.mean():.1f}, "
              f"percentil_75={np.percentile(proy_x, 75):.0f}")

        # Detectar filas y columnas con el pipeline actual
        filas, x_cortes = obtener_filas_y_columnas_tabla(roi, n_filas)
        print(f"  Filas detectadas: {len(filas)} (esperadas: {n_filas})")
        print(f"  x_cortes: {x_cortes}")

        # Dibujar las filas detectadas sobre la ROI
        roi_color = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        for fila in filas:
            cv2.line(roi_color, (0, fila["y1"]), (w, fila["y1"]), (0, 0, 255), 1)
        for x in x_cortes:
            cv2.line(roi_color, (x, 0), (x, h), (0, 255, 0), 1)

        cv2.imwrite(f"debug/04_{nombre}_deteccion.png", roi_color)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python diagnostico.py <ruta_pdf>")
        sys.exit(1)
    main(sys.argv[1])