"""
Debug de densidades por celda.

Uso:
    python debug_densidades.py <pdf> <item1> <item2> ...

Ejemplo:
    python debug_densidades.py PRUEBA1.pdf E1 E2 E5
"""

import sys
import cv2
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_3_tablas_geometria
from ocr.rows import obtener_filas_y_columnas_tabla
from ocr.marks import analizar_trazo_celda


PREFIJOS = {"E": 0, "P": 1, "H": 2}
N_FILAS = {"E": 33, "P": 47, "H": 38}


def main(pdf_path, items):
    imagenes = pdf_a_imagenes(pdf_path, dpi=300)
    prep = preprocesar_imagen(imagenes[0])
    binaria = prep["binaria"]

    tablas = detectar_3_tablas_geometria(binaria)
    tablas = sorted(tablas, key=lambda t: t["x"])

    # Preparar cada bloque
    bloques = {}
    for prefijo, idx_tabla in PREFIJOS.items():
        roi = tablas[idx_tabla]["roi_binaria"]
        filas, x_cortes = obtener_filas_y_columnas_tabla(roi, N_FILAS[prefijo])
        bloques[prefijo] = {
            "roi": roi,
            "filas": filas,
            "x_cortes": x_cortes,
        }

    # Para cada ítem pedido, mostrar densidades
    for item in items:
        prefijo = item[0]
        try:
            num = int(item[1:])
        except ValueError:
            print(f"❌ Item inválido: {item}")
            continue

        if prefijo not in bloques:
            print(f"❌ Prefijo inválido: {prefijo}")
            continue

        bloque = bloques[prefijo]
        idx = num - 1

        if idx < 0 or idx >= len(bloque["filas"]):
            print(f"❌ {item}: fuera de rango")
            continue

        fila = bloque["filas"][idx]
        x_cortes = bloque["x_cortes"]
        roi = bloque["roi"]

        y1, y2 = fila["y1"], fila["y2"]
        x_no_a, x_no_b = x_cortes[1], x_cortes[2]
        x_si_a, x_si_b = x_cortes[2], x_cortes[3]

        celda_no = roi[y1:y2, x_no_a:x_no_b]
        celda_si = roi[y1:y2, x_si_a:x_si_b]

        marcada_no, dens_no, area_no = analizar_trazo_celda(celda_no)
        marcada_si, dens_si, area_si = analizar_trazo_celda(celda_si)

        print(f"\n=== {item} ===")
        print(f"  Celda No: y={y1}-{y2}, x={x_no_a}-{x_no_b}")
        print(f"    densidad={dens_no:.4f}, area_max={area_no:.1f}, marcada={marcada_no}")
        print(f"  Celda Sí: y={y1}-{y2}, x={x_si_a}-{x_si_b}")
        print(f"    densidad={dens_si:.4f}, area_max={area_si:.1f}, marcada={marcada_si}")

        # Guardar imágenes para inspección visual
        cv2.imwrite(f"debug_{item}_no.png", celda_no)
        cv2.imwrite(f"debug_{item}_si.png", celda_si)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python debug_densidades.py <pdf> <item1> [item2] ...")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2:])