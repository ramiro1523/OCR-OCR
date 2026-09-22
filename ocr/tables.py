"""
Detección morfológica de las 3 tablas del formulario IEPPO.

Extrae líneas horizontales y verticales, agrupa coordenadas y detecta
los bounding boxes de las 3 cuadrículas: E (Estilos), P (Preferencias), H (Habilidad).

FASE 3.4 aplicada:
  - Y_INICIO_PROPORCION bajado de 0.15 a 0.10.
    Con fotos (perspectiva + encuadre variable), la fila E1 puede
    quedar muy cerca del borde superior. Con 0.15 se corría el riesgo
    de cortarla en la máscara de zona útil. Con 0.10 hay 5% extra
    de margen superior.
    rows.py ya está preparado para descartar filas de encabezado
    (toma las últimas n_esperadas), así que este margen extra no
    introduce ruido en la detección.
"""

import logging
from typing import List, Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Zona útil de la página (ignorar cabecera y pie).
# FASE 3.4: bajado de 0.15 a 0.10 para no cortar E1 en fotos con
# encuadre variable. El pie se mantiene en 0.98.
Y_INICIO_PROPORCION = 0.10
Y_FIN_PROPORCION = 0.98

# Filtros de contornos
AREA_MINIMA_PROPORCION = 0.04       # 4% del área de la zona útil
ALTO_MINIMO_PROPORCION = 0.45       # 45% de la altura de la zona útil
ANCHO_MAXIMO_PROPORCION = 0.60      # >60% = probablemente las 3 tablas unidas

# Dilatación para conectar componentes de la cuadrícula
KERNEL_DILATACION = (5, 5)


# =============================================================================
# FUNCIONES PÚBLICAS
# =============================================================================

def aislar_lineas_morfologicas(
    binaria_inv: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrae las líneas continuas horizontales y verticales mediante morfología.

    Args:
        binaria_inv: Imagen binaria INVERTIDA (tinta blanca, fondo negro).

    Returns:
        (lineas_h, lineas_v): Arrays de líneas horizontales y verticales.
    """
    if binaria_inv is None or binaria_inv.size == 0:
        logger.error("aislar_lineas_morfologicas: imagen vacía o None.")
        vacio = np.zeros((10, 10), dtype=np.uint8)
        return vacio, vacio

    if binaria_inv.dtype != np.uint8:
        binaria_inv = binaria_inv.astype(np.uint8)

    h, w = binaria_inv.shape[:2]

    # Kernel horizontal (ancho adaptado)
    kernel_h = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, w // 40), 1)
    )
    lineas_h = cv2.morphologyEx(binaria_inv, cv2.MORPH_OPEN, kernel_h)

    # Kernel vertical (alto adaptado)
    kernel_v = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(15, h // 50))
    )
    lineas_v = cv2.morphologyEx(binaria_inv, cv2.MORPH_OPEN, kernel_v)

    return lineas_h, lineas_v


def agrupar_coordenadas_cercanas(
    coordenadas: List[int],
    distancia_minima: int = 5
) -> List[int]:
    """
    Agrupa coordenadas Y o X duplicadas generadas por el grosor de los bordes.

    Args:
        coordenadas: Lista de coordenadas enteras (pueden estar desordenadas).
        distancia_minima: Distancia en px bajo la cual dos coordenadas se fusionan.

    Returns:
        Lista de coordenadas agrupadas (promedio de cada grupo).
    """
    if not coordenadas:
        return []

    coordenadas = sorted(coordenadas)
    agrupadas: List[int] = []
    grupo_actual = [coordenadas[0]]

    for c in coordenadas[1:]:
        if c - grupo_actual[-1] <= distancia_minima:
            grupo_actual.append(c)
        else:
            agrupadas.append(int(np.mean(grupo_actual)))
            grupo_actual = [c]

    if grupo_actual:
        agrupadas.append(int(np.mean(grupo_actual)))

    return agrupadas


def detectar_3_tablas_geometria(binaria: np.ndarray) -> List[Dict[str, Any]]:
    """
    Detecta los bounding boxes de las 3 tablas del formulario IEPPO.

    Args:
        binaria: Imagen binaria (fondo blanco, tinta negra).

    Returns:
        Lista de hasta 3 dicts con: x, y, w, h, roi_binaria.
        Siempre retorna 3 elementos (usa fallback si la detección falla).
    """
    # -------------------------------------------------------------------------
    # 0. Validaciones
    # -------------------------------------------------------------------------
    if binaria is None or binaria.size == 0:
        logger.error("detectar_3_tablas_geometria: imagen vacía o None.")
        return _fallback_3_columnas(np.zeros((100, 300), dtype=np.uint8))

    if binaria.dtype != np.uint8:
        binaria = binaria.astype(np.uint8)

    if len(binaria.shape) != 2:
        logger.error("detectar_3_tablas_geometria: imagen no es 2D.")
        return _fallback_3_columnas(np.zeros((100, 300), dtype=np.uint8))

    h, w = binaria.shape
    if h < 200 or w < 200:
        logger.error("detectar_3_tablas_geometria: imagen muy pequeña (%dx%d).", w, h)
        return _fallback_3_columnas(binaria)

    # -------------------------------------------------------------------------
    # 1. Definir zona útil (ignorar cabecera y pie)
    # -------------------------------------------------------------------------
    y_inicio = int(h * Y_INICIO_PROPORCION)
    y_fin = int(h * Y_FIN_PROPORCION)
    zona_util = binaria[y_inicio:y_fin, :]

    if zona_util.size == 0:
        logger.error("Zona útil vacía.")
        return _fallback_3_columnas(binaria)

    zona_h, zona_w = zona_util.shape

    logger.info(
        "Zona útil: y_inicio=%d (%.0f%%), y_fin=%d (%.0f%%), %dx%d px.",
        y_inicio, Y_INICIO_PROPORCION * 100,
        y_fin, Y_FIN_PROPORCION * 100,
        zona_w, zona_h,
    )

    # -------------------------------------------------------------------------
    # 2. Invertir para que la tinta sea blanca
    # -------------------------------------------------------------------------
    zona_util_inv = cv2.bitwise_not(zona_util)

    # -------------------------------------------------------------------------
    # 3. Extraer líneas y construir cuadrícula
    # -------------------------------------------------------------------------
    try:
        lineas_h, lineas_v = aislar_lineas_morfologicas(zona_util_inv)
        cuadricula = cv2.add(lineas_h, lineas_v)
    except Exception as e:
        logger.error("Error en morfología: %s. Usando fallback.", e)
        return _fallback_3_columnas(binaria)

    # Dilatar para conectar componentes cercanos (bordes de tabla)
    kernel_dil = cv2.getStructuringElement(cv2.MORPH_RECT, KERNEL_DILATACION)
    cuadricula_dil = cv2.dilate(cuadricula, kernel_dil, iterations=1)

    # -------------------------------------------------------------------------
    # 4. Encontrar contornos
    # -------------------------------------------------------------------------
    try:
        contornos, _ = cv2.findContours(
            cuadricula_dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
    except Exception as e:
        logger.error("Error en findContours: %s. Usando fallback.", e)
        return _fallback_3_columnas(binaria)

    # -------------------------------------------------------------------------
    # 5. Filtrar candidatos
    # -------------------------------------------------------------------------
    area_minima = (zona_h * zona_w) * AREA_MINIMA_PROPORCION
    alto_minimo = zona_h * ALTO_MINIMO_PROPORCION
    ancho_maximo = w * ANCHO_MAXIMO_PROPORCION

    candidatos: List[Dict[str, Any]] = []

    for c in contornos:
        x, y, ancho, alto = cv2.boundingRect(c)
        area = ancho * alto

        if area < area_minima:
            continue
        if alto < alto_minimo:
            continue
        if ancho > ancho_maximo:
            # Probablemente las 3 tablas están unidas: descartar candidato
            logger.debug("Contorno descartado: ancho %d > max %d.", ancho, ancho_maximo)
            continue

        candidatos.append({
            "x": x,
            "y": y + y_inicio,
            "w": ancho,
            "h": alto,
            "roi_binaria": binaria[
                y + y_inicio : y + y_inicio + alto,
                x : x + ancho
            ]
        })

    # -------------------------------------------------------------------------
    # 6. Ordenar de izquierda a derecha
    # -------------------------------------------------------------------------
    tablas_ordenadas = sorted(candidatos, key=lambda t: t["x"])

    # -------------------------------------------------------------------------
    # 7. Fallback si no hay 3 tablas válidas
    # -------------------------------------------------------------------------
    if len(tablas_ordenadas) < 3:
        logger.warning(
            "Solo %d tablas detectadas (se esperan 3). Aplicando fallback proporcional.",
            len(tablas_ordenadas)
        )
        return _fallback_3_columnas(binaria)

    logger.info(
        "3 tablas detectadas en x=[%d, %d, %d].",
        tablas_ordenadas[0]["x"],
        tablas_ordenadas[1]["x"],
        tablas_ordenadas[2]["x"]
    )

    return tablas_ordenadas[:3]


# =============================================================================
# FALLBACK
# =============================================================================

def _fallback_3_columnas(binaria: np.ndarray) -> List[Dict[str, Any]]:
    """
    Divide la imagen en 3 columnas iguales como fallback.

    Útil cuando la detección morfológica falla pero aún queremos intentar
    procesar el formulario.
    """
    if binaria is None or binaria.size == 0:
        binaria = np.zeros((3000, 2500), dtype=np.uint8)

    h, w = binaria.shape[:2]
    y_inicio = int(h * Y_INICIO_PROPORCION)
    y_fin = int(h * Y_FIN_PROPORCION)

    ancho_col = w // 3
    tablas = []

    for i in range(3):
        x1 = i * ancho_col
        x2 = (i + 1) * ancho_col if i < 2 else w
        tablas.append({
            "x": x1,
            "y": y_inicio,
            "w": x2 - x1,
            "h": y_fin - y_inicio,
            "roi_binaria": binaria[y_inicio:y_fin, x1:x2]
        })

    return tablas