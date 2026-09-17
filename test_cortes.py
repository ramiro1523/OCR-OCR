"""Verifica los cortes X de cada bloque."""

import sys
import cv2
from pathlib import Path

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_3_tablas_geometria
from ocr.rows import obtener_filas_y_columnas_tabla


def main(pdf_path):
    imagenes = pdf_a_imagenes(pdf_path, dpi=300)
    prep = preprocesar_imagen(imagenes[0])
    binaria = prep["binaria"]

    tablas = detectar_3_tablas_geometria(binaria)
    tablas = sorted(tablas, key=lambda t: t["x"])

    nombres = ["E", "P", "H"]
    n_filas = [33, 47, 38]

    for nombre, n, t in zip(nombres, n_filas, tablas):
        roi = t["roi_binaria"]
        h, w = roi.shape

        filas, x_cortes = obtener_filas_y_columnas_tabla(roi, n)

        print(f"\n=== Bloque {nombre} (w={w}) ===")
        print(f"  Filas: {len(filas)}/{n}")
        print(f"  Cortes X: {x_cortes}")
        print(f"  Proporciones:")
        for i, x in enumerate(x_cortes):
            print(f"    Corte {i}: {x} px = {x/w*100:.1f}%")

        # Ancho de cada columna
        col_n = x_cortes[1] - x_cortes[0]
        col_no = x_cortes[2] - x_cortes[1]
        col_si = x_cortes[3] - x_cortes[2]
        print(f"  Anchos: N°={col_n}px, No={col_no}px, Sí={col_si}px")

        # Guardar ROI con cortes dibujados
        roi_color = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        for x in x_cortes:
            cv2.line(roi_color, (x, 0), (x, h), (0, 255, 0), 2)
        cv2.imwrite(f"debug_cortes_{nombre}.png", roi_color)


if __name__ == "__main__":
    main(sys.argv[1])