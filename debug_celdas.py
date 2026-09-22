"""
Script de debug para inspeccionar las celdas detectadas por el pipeline.

Genera:
  - debug_celdas_bloque_E.png  (imagen grande, una fila por ítem)
  - debug_celdas_bloque_P.png
  - debug_celdas_bloque_H.png

Cada fila muestra: [ítem] [celda NO] | [celda SI] | [densidades + clasificación]
"""

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

from ocr.entrada import cargar_formulario
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_3_tablas_geometria
from ocr.rows import obtener_filas_y_columnas_tabla

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

RUTA_DEBUG = Path("debug_celdas")
RUTA_DEBUG.mkdir(exist_ok=True)


def _dibujar_texto(img, texto, x, y, escala=0.5, color=(0, 0, 0)):
    cv2.putText(
        img, texto, (x, y),
        cv2.FONT_HERSHEY_SIMPLEX, escala, color, 1, cv2.LINE_AA
    )


def main(pdf_path):
    print(f"Procesando: {pdf_path}")

    # Cargar y preprocesar (mismo pipeline que producción)
    imagenes = cargar_formulario(pdf_path, dpi=300)
    img_np = imagenes[0]

    prep = preprocesar_imagen(img_np, metodo_binarizacion="otsu")
    binaria = prep["binaria"]

    # Detectar tablas
    tablas = detectar_3_tablas_geometria(binaria)
    tablas = sorted(tablas, key=lambda t: t["x"])

    bloques_info = [
        ("E", 33, tablas[0]),
        ("P", 47, tablas[1]),
        ("H", 38, tablas[2]),
    ]

    for prefijo, n_esperados, info_tabla in bloques_info:
        roi_tabla = info_tabla["roi_binaria"]

        try:
            filas, x_cortes = obtener_filas_y_columnas_tabla(roi_tabla, n_esperados)
        except Exception as e:
            print(f"  Error en bloque {prefijo}: {e}")
            continue

        if len(x_cortes) < 4:
            print(f"  Bloque {prefijo}: cortes X insuficientes")
            continue

        x_no_a, x_no_b = x_cortes[1], x_cortes[2]
        x_si_a, x_si_b = x_cortes[2], x_cortes[3]

        # Altura de cada fila + margen para el texto del índice
        ALTO_TEXTO = 30
        ALTO_FILA_MAX = 80  # reescalamos todas a esta altura

        filas_render = []
        for idx, fila in enumerate(filas):
            if idx >= n_esperados:
                break

            y1, y2 = fila["y1"], fila["y2"]
            if y2 <= y1:
                continue

            celda_no = roi_tabla[y1:y2, x_no_a:x_no_b]
            celda_si = roi_tabla[y1:y2, x_si_a:x_si_b]

            if celda_no.size == 0 or celda_si.size == 0:
                continue

            # Reescalar celdas a altura uniforme
            h_orig = celda_no.shape[0]

            def _rescalar(celda):
                if celda.shape[0] == 0:
                    return np.full((ALTO_FILA_MAX, 100), 255, dtype=np.uint8)
                escala = ALTO_FILA_MAX / celda.shape[0]
                nuevo_ancho = max(1, int(celda.shape[1] * escala))
                return cv2.resize(celda, (nuevo_ancho, ALTO_FILA_MAX),
                                  interpolation=cv2.INTER_NEAREST)

            c_no = _rescalar(celda_no)
            c_si = _rescalar(celda_si)

            fila_render = np.full(
                (ALTO_FILA_MAX + ALTO_TEXTO, c_no.shape[1] + c_si.shape[1] + 300),
                255, dtype=np.uint8
            )

            # Celdas
            fila_render[ALTO_TEXTO:ALTO_TEXTO + ALTO_FILA_MAX, 0:c_no.shape[1]] = c_no
            offset_si = c_no.shape[1] + 10
            fila_render[ALTO_TEXTO:ALTO_TEXTO + ALTO_FILA_MAX,
                        offset_si:offset_si + c_si.shape[1]] = c_si

            # Texto superior
            item_key = f"{prefijo}{idx + 1}"
            _dibujar_texto(fila_render, item_key, 5, 22, escala=0.7)

            # Etiquetas "NO" y "SI" arriba
            _dibujar_texto(fila_render, "NO", 5, ALTO_TEXTO - 5, escala=0.5, color=(0, 0, 255))
            _dibujar_texto(fila_render, "SI", offset_si, ALTO_TEXTO - 5, escala=0.5, color=(255, 0, 0))

            # Información de la fila (Y1, Y2, alto)
            info = f"y1={y1} y2={y2} h={y2-y1}"
            _dibujar_texto(
                fila_render, info,
                offset_si + c_si.shape[1] + 10, 22,
                escala=0.4, color=(128, 128, 128)
            )

            filas_render.append(fila_render)

        if not filas_render:
            print(f"  Bloque {prefijo}: sin filas para renderizar")
            continue

        # Ancho máximo entre todas las filas (por si varían)
        ancho_max = max(f.shape[1] for f in filas_render)
        filas_uniform = []
        for f in filas_render:
            if f.shape[1] < ancho_max:
                pad = np.full((f.shape[0], ancho_max - f.shape[1]), 255, dtype=np.uint8)
                f = np.hstack([f, pad])
            filas_uniform.append(f)
            # Separador
            filas_uniform.append(
                np.full((2, ancho_max), 200, dtype=np.uint8)
            )

        imagen_final = np.vstack(filas_uniform)
        ruta = RUTA_DEBUG / f"debug_celdas_bloque_{prefijo}.png"
        cv2.imwrite(str(ruta), imagen_final)
        print(f"  Guardado: {ruta} ({len(filas_render)} filas)")

    print("\nListo. Revisa la carpeta 'debug_celdas/'.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python debug_celdas.py <ruta.pdf>")
        sys.exit(1)
    main(sys.argv[1])