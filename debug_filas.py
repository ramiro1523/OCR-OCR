"""
Debug visual de filas detectadas en el bloque E.

Genera imágenes anotadas con:
  - Cortes Y detectados (líneas rojas)
  - Etiquetas E1..E33 por fila
  - Cortes X (líneas verdes)
  - Puntos de densidad

Uso:
    python debug_filas.py <pdf>
"""

import sys
from pathlib import Path

import cv2
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_3_tablas_geometria
from ocr.tables import aislar_lineas_morfologicas, agrupar_coordenadas_cercanas


# Configuración (duplicada de rows.py para inspección)
UMBRAL_PROY_Y = 0.15
DISTANCIA_MINIMA_Y = 12
EXCESO_MAXIMO_ENCABEZADO = 4


def main(pdf_path):
    print(f"\n{'='*70}")
    print("  DEBUG VISUAL DE FILAS - BLOQUE E")
    print(f"{'='*70}\n")

    # 1. Cargar PDF y preprocesar
    print("📄 Cargando PDF...")
    imagenes = pdf_a_imagenes(pdf_path, dpi=300)
    img = imagenes[0]
    print(f"   Imagen: {img.shape[1]}x{img.shape[0]}")

    print("🔧 Preprocesando...")
    prep = preprocesar_imagen(img)
    binaria = prep["binaria"]

    print("📐 Detectando tablas...")
    tablas = detectar_3_tablas_geometria(binaria)
    tablas = sorted(tablas, key=lambda t: t["x"])
    print(f"   Tablas detectadas: {len(tablas)}")

    if len(tablas) < 1:
        print("❌ No se detectó el bloque E.")
        return

    # 2. Tomar el bloque E
    bloque_e = tablas[0]
    roi = bloque_e["roi_binaria"]
    h, w = roi.shape
    print(f"\n   Bloque E: {w}x{h} en x={bloque_e['x']}, y={bloque_e['y']}")

    # 3. Detectar líneas horizontales
    inv = cv2.bitwise_not(roi)
    lineas_h, lineas_v = aislar_lineas_morfologicas(inv)

    # 4. Proyección Y
    proy_y = np.sum(lineas_h, axis=1)
    umbral_y = float(np.max(proy_y)) * UMBRAL_PROY_Y

    print(f"\n   Proyección Y: max={int(np.max(proy_y))}, umbral={umbral_y:.0f}")

    y_picos = np.where(proy_y > umbral_y)[0].tolist()
    y_cortes = agrupar_coordenadas_cercanas(y_picos, distancia_minima=DISTANCIA_MINIMA_Y)

    print(f"\n   Cortes Y brutos detectados: {len(y_cortes)}")
    print(f"   Listado: {y_cortes}")

    # Calcular espacios entre cortes
    if len(y_cortes) >= 2:
        espacios = [y_cortes[i+1] - y_cortes[i] for i in range(len(y_cortes)-1)]
        print(f"\n   Espacios entre cortes:")
        for i, esp in enumerate(espacios):
            print(f"     y_corte[{i}]→[{i+1}] = {y_cortes[i]}→{y_cortes[i+1]} = {esp}px")

    # 5. Aplicar la lógica actual del pipeline
    filas_detectadas = []
    for i in range(len(y_cortes) - 1):
        y1 = int(y_cortes[i])
        y2 = int(y_cortes[i + 1])
        if y2 > y1:
            filas_detectadas.append({"y1": y1, "y2": y2})

    print(f"\n   Filas detectadas (bruto): {len(filas_detectadas)}")

    # Aplicar la lógica de "tomar las últimas 33"
    n_esperadas = 33
    exceso = len(filas_detectadas) - n_esperadas

    print(f"\n   Filas esperadas: {n_esperadas}")
    print(f"   Exceso: {exceso}")

    if exceso > 0 and exceso <= EXCESO_MAXIMO_ENCABEZADO:
        print(f"   → Tomando las últimas {n_esperadas} (descartando primeras {exceso})")
        filas_finales = filas_detectadas[exceso:]
        # Informar qué filas se descartaron
        print(f"\n   Filas descartadas (encabezado):")
        for i, f in enumerate(filas_detectadas[:exceso]):
            print(f"     Fila extra {i}: y={f['y1']}-{f['y2']} (altura={f['y2']-f['y1']}px)")
    else:
        filas_finales = filas_detectadas[:n_esperadas]

    print(f"\n   Filas finales: {len(filas_finales)}")

    # 6. Detectar cortes X
    proy_x = np.sum(lineas_v, axis=0)
    umbral_x = float(np.max(proy_x)) * UMBRAL_PROY_Y
    x_picos = np.where(proy_x > umbral_x)[0].tolist()
    x_cortes_raw = agrupar_coordenadas_cercanas(x_picos, distancia_minima=15)

    print(f"\n   Cortes X brutos: {x_cortes_raw}")

    # Usar los cortes proporcionales si no hay suficientes
    if len(x_cortes_raw) >= 4:
        x_cortes = x_cortes_raw[:4]
    else:
        x_cortes = [0, int(w*0.13), int(w*0.56), w]

    print(f"   Cortes X finales: {x_cortes}")

    # 7. Generar imagen de debug
    print(f"\n   🎨 Generando imagen de debug...")

    # Convertir ROI a color
    roi_color = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)

    # Dibujar cortes X (verde)
    for x in x_cortes:
        cv2.line(roi_color, (x, 0), (x, h), (0, 200, 0), 2)

    # Dibujar cortes Y
    # Primero, en AZUL las filas descartadas (encabezado)
    for f in filas_detectadas[:exceso] if exceso > 0 else []:
        cv2.line(roi_color, (0, f["y1"]), (w, f["y1"]), (255, 100, 0), 2)
        cv2.line(roi_color, (0, f["y2"]), (w, f["y2"]), (255, 100, 0), 2)

    # Luego, en ROJO los cortes Y de las filas finales
    for f in filas_finales:
        cv2.line(roi_color, (0, f["y1"]), (w, f["y1"]), (0, 0, 255), 2)

    # Marcar la última línea (y2 de la última fila)
    if filas_finales:
        ultimo_y = filas_finales[-1]["y2"]
        cv2.line(roi_color, (0, ultimo_y), (w, ultimo_y), (0, 0, 255), 2)

    # Etiquetas E1..E33 en el centro de cada fila
    for i, f in enumerate(filas_finales):
        item = f"E{i+1}"
        y_centro = (f["y1"] + f["y2"]) // 2
        # Poner la etiqueta en el borde izquierdo, sobre la columna N°
        cv2.putText(
            roi_color,
            item,
            (5, y_centro + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 255),  # Magenta
            1,
            cv2.LINE_AA
        )

    # Guardar imagen
    archivo = "debug_filas_bloque_e.png"
    cv2.imwrite(archivo, roi_color)
    print(f"   💾 Guardado: {archivo}")

    # 8. Generar imagen ampliada de las primeras 10 filas (para ver detalle)
    y_limite = filas_finales[10]["y2"] if len(filas_finales) > 10 else h
    roi_top = roi_color[0:y_limite, :]

    # Escalar 2x para mejor visualización
    roi_top_2x = cv2.resize(roi_top, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    archivo_zoom = "debug_filas_bloque_e_zoom_top.png"
    cv2.imwrite(archivo_zoom, roi_top_2x)
    print(f"   💾 Guardado: {archivo_zoom}")

    # 9. Imprimir mapa de asignación
    print(f"\n   📋 Mapa de asignación:")
    print(f"   {'Item':<6} {'y1':>6} {'y2':>6} {'altura':>8} {'centro':>8}")
    print(f"   {'-'*40}")

    for i, f in enumerate(filas_finales[:40]):
        item = f"E{i+1}"
        y1 = f["y1"]
        y2 = f["y2"]
        altura = y2 - y1
        centro = (y1 + y2) // 2
        print(f"   {item:<6} {y1:>6} {y2:>6} {altura:>8} {centro:>8}")

    print(f"\n{'='*70}")
    print("  FIN DEL DEBUG")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python debug_filas.py <ruta_pdf>")
        sys.exit(1)
    main(sys.argv[1])