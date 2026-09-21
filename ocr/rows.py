"""
Detección de filas y columnas dentro de una tabla IEPPO.

Robusto a múltiples variaciones de escaneo:
  - Diferentes resoluciones y DPI.
  - Distintos niveles de ruido y contraste.
  - Cortes X extra (ruido, líneas verticales tenues o dobles).
  - Cortes X faltantes (líneas tenues no detectadas por morfología).
  - Cortes Y faltantes o duplicados.
  - Encabezados con 3, 4 o 5 filas.
  - Tablas con proporciones horizontales ligeramente variables.

Layout esperado: [N° ~13% | No ~43% | Sí ~44%]

Estrategia en 3 capas por cada dimensión (Y y X):
  1. Detección morfológica de líneas.
  2. Proyección + agrupación + detección de líneas faltantes.
  3. Validación por contexto (n_filas_esperadas, proporciones del layout).
  4. Fallback proporcional como último recurso.
"""

import logging
from typing import List, Dict, Tuple

import cv2
import numpy as np

from ocr.tables import aislar_lineas_morfologicas, agrupar_coordenadas_cercanas

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

# Proporciones horizontales esperadas del layout IEPPO
PROP_N_FIN = 0.13          # Fin columna N° (inicio No)
PROP_NO_FIN = 0.56         # Fin columna No (inicio Sí)

# Rangos válidos para aceptar cortes X detectados morfológicamente
RANGO_N = (0.08, 0.28)     # Corte N°/No debe estar entre 8% y 28% del ancho
RANGO_NO = (0.45, 0.68)    # Corte No/Sí debe estar entre 45% y 68% del ancho

# Márgenes para descartar cortes en los extremos
MARGEN_EXTREMO = 0.04      # Cortes < 4% o > 96% del ancho se descartan

# Separación mínima entre cortes X adyacentes (relativo al ancho)
SEPARACION_MINIMA_X = 0.10
SEPARACION_MINIMA_W = 0.10  # Separación mínima entre el último corte y w

# =============================================================================
# CONFIGURACIÓN DE DETECCIÓN DE FILAS
# =============================================================================

UMBRAL_PROY_Y = 0.15       # Umbral de proyección Y (fracción del máximo)
UMBRAL_PROY_X = 0.15       # Umbral de proyección X (fracción del máximo)

DISTANCIA_MINIMA_Y = 12    # Distancia mínima para agrupar cortes Y
DISTANCIA_MINIMA_X = 15    # Distancia mínima para agrupar cortes X

TOLERANCIA_FILAS = 2       # Tolerancia de filas para reintento

EXCESO_MAXIMO_ENCABEZADO = 4  # Máximo exceso de filas atribuible a encabezado

# Rangos de altura de fila respecto a la mediana (para filtrado)
FILTRO_ALTURA_MIN = 0.5
FILTRO_ALTURA_MAX = 1.8
FILTRO_ALTURA_MIN_RELAJADO = 0.3
FILTRO_ALTURA_MAX_RELAJADO = 2.5

# Detección de líneas Y faltantes
FACTOR_ESPACIO_ANOMALO = 1.6   # Espacio > 1.6x la mediana → buscar línea faltante
UMBRAL_PICO_LOCAL = 0.20       # Umbral del pico local (fracción del máximo en zona)


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def obtener_filas_y_columnas_tabla(
    roi_binaria: np.ndarray,
    n_filas_esperadas: int
) -> Tuple[List[Dict[str, int]], List[int]]:
    """
    Aísla las divisiones Y (filas) y X (columnas) de una tabla IEPPO.

    Args:
        roi_binaria: Imagen binaria (fondo blanco 255, tinta negra 0).
        n_filas_esperadas: Número esperado de filas de datos (sin encabezado).

    Returns:
        (filas, x_cortes) donde:
          - filas: Lista de dicts {"y1": int, "y2": int} por fila.
          - x_cortes: [0, corte_n, corte_no, w].
    """
    # =========================================================================
    # 0. VALIDACIONES DEFENSIVAS
    # =========================================================================
    if roi_binaria is None or roi_binaria.size == 0:
        logger.error("ROI binaria vacía o None.")
        return [], _cortes_x_esperados(0)

    if not isinstance(roi_binaria, np.ndarray):
        logger.error("ROI no es ndarray (%s).", type(roi_binaria))
        return [], _cortes_x_esperados(0)

    if roi_binaria.dtype != np.uint8:
        logger.warning("ROI no es uint8 (%s). Convirtiendo.", roi_binaria.dtype)
        roi_binaria = roi_binaria.astype(np.uint8)

    if len(roi_binaria.shape) != 2:
        logger.error("ROI no es 2D (shape=%s).", roi_binaria.shape)
        return [], _cortes_x_esperados(0)

    h, w = roi_binaria.shape
    if h < 50 or w < 50:
        logger.error("ROI demasiado pequeña (%dx%d).", w, h)
        return [], _cortes_x_esperados(w)

    if n_filas_esperadas <= 0:
        logger.error("n_filas_esperadas debe ser > 0 (recibido: %d).", n_filas_esperadas)
        return [], _cortes_x_esperados(w)

    # =========================================================================
    # 1. DETECCIÓN MORFOLÓGICA DE LÍNEAS
    # =========================================================================
    try:
        inv = cv2.bitwise_not(roi_binaria)
        lineas_h, lineas_v = aislar_lineas_morfologicas(inv)
    except Exception as e:
        logger.error("Fallo al aislar líneas morfológicas: %s", e, exc_info=True)
        return _filas_uniformes(h, n_filas_esperadas), _cortes_x_esperados(w)

    if lineas_h is None or lineas_v is None:
        logger.warning("aislar_lineas_morfologicas retornó None. Usando fallback.")
        return _filas_uniformes(h, n_filas_esperadas), _cortes_x_esperados(w)

    # =========================================================================
    # 2. DETECCIÓN DE FILAS
    # =========================================================================
    filas = _detectar_filas(lineas_h, h, n_filas_esperadas)

    # =========================================================================
    # 3. DETECCIÓN DE COLUMNAS
    # =========================================================================
    x_cortes = _detectar_columnas(lineas_v, w)

    # =========================================================================
    # 4. RECORTE FINAL DE FILAS
    # =========================================================================
    if len(filas) > n_filas_esperadas:
        logger.warning("Recortando filas: %d → %d.", len(filas), n_filas_esperadas)
        filas = filas[:n_filas_esperadas]
    elif len(filas) < n_filas_esperadas:
        logger.warning("Solo %d filas de %d esperadas.", len(filas), n_filas_esperadas)

    return filas, x_cortes


# =============================================================================
# DETECCIÓN DE FILAS
# =============================================================================

def _detectar_filas(
    lineas_h: np.ndarray,
    h: int,
    n_filas_esperadas: int
) -> List[Dict[str, int]]:
    """
    Detecta las filas a partir de las líneas horizontales.

    Estrategia:
      1. Proyección Y con umbral proporcional al máximo.
      2. Agrupación de picos cercanos.
      3. Detección de líneas faltantes en intervalos anómalos.
      4. Validación por número esperado:
         - Exacto → devolver.
         - Más filas → quitar encabezado o filtrar por altura.
         - Menos filas → reintentar con umbral bajo.
      5. Fallback uniforme como último recurso.
    """
    proy_y = np.sum(lineas_h, axis=1)

    if proy_y.size == 0 or np.max(proy_y) == 0:
        logger.warning("Sin proyección Y válida. Usando fallback.")
        return _filas_uniformes(h, n_filas_esperadas)

    umbral_y = float(np.max(proy_y)) * UMBRAL_PROY_Y
    y_picos = np.where(proy_y > umbral_y)[0].tolist()

    if not y_picos:
        logger.warning("Sin picos Y. Usando fallback.")
        return _filas_uniformes(h, n_filas_esperadas)

    y_cortes = agrupar_coordenadas_cercanas(
        y_picos, distancia_minima=DISTANCIA_MINIMA_Y
    )

    # Detección de líneas faltantes
    y_cortes = _detectar_linea_faltante(lineas_h, y_cortes, h)

    logger.info(
        "Proyección Y: max=%d, umbral=%.0f, picos=%d, cortes=%d (esperado ~%d)",
        int(np.max(proy_y)), umbral_y, len(y_picos),
        len(y_cortes), n_filas_esperadas + 1
    )

    if len(y_cortes) < 2:
        logger.warning("Menos de 2 cortes Y. Usando fallback.")
        return _filas_uniformes(h, n_filas_esperadas)

    # Construir filas a partir de cortes
    filas_detectadas = []
    for i in range(len(y_cortes) - 1):
        y1 = int(y_cortes[i])
        y2 = int(y_cortes[i + 1])
        if y2 > y1:
            filas_detectadas.append({"y1": y1, "y2": y2})

    logger.info("Filas iniciales por proyección: %d (esperadas: %d)",
                len(filas_detectadas), n_filas_esperadas)

    # -------------------------------------------------------------------------
    # Caso ideal: número exacto
    # -------------------------------------------------------------------------
    if len(filas_detectadas) == n_filas_esperadas:
        logger.info("Filas detectadas exactas. ✓")
        return filas_detectadas

    # -------------------------------------------------------------------------
    # Caso 1: más filas → quitar encabezado o filtrar
    # -------------------------------------------------------------------------
    if len(filas_detectadas) > n_filas_esperadas:
        exceso = len(filas_detectadas) - n_filas_esperadas

        if exceso <= EXCESO_MAXIMO_ENCABEZADO:
            logger.info(
                "Detectadas %d filas (%d extra). Tomando últimas %d.",
                len(filas_detectadas), exceso, n_filas_esperadas
            )
            return filas_detectadas[exceso:]

        filas_filtradas = _filtrar_filas_por_altura(
            filas_detectadas, n_filas_esperadas
        )
        if filas_filtradas and len(filas_filtradas) == n_filas_esperadas:
            logger.info("Filtradas por altura: %d → %d. ✓",
                        len(filas_detectadas), len(filas_filtradas))
            return filas_filtradas

        logger.warning("Filtro de altura no convergió. Usando fallback.")
        return _filas_uniformes(h, n_filas_esperadas)

    # -------------------------------------------------------------------------
    # Caso 2: menos filas → reintentar con umbral bajo
    # -------------------------------------------------------------------------
    logger.warning("Menos filas de las esperadas: %d < %d. Reintentando.",
                   len(filas_detectadas), n_filas_esperadas)

    umbral_y_2 = float(np.max(proy_y)) * 0.08
    y_picos_2 = np.where(proy_y > umbral_y_2)[0].tolist()
    y_cortes_2 = agrupar_coordenadas_cercanas(
        y_picos_2, distancia_minima=DISTANCIA_MINIMA_Y
    )
    y_cortes_2 = _detectar_linea_faltante(lineas_h, y_cortes_2, h)

    if len(y_cortes_2) - 1 >= n_filas_esperadas - TOLERANCIA_FILAS:
        filas_reintento = []
        for i in range(len(y_cortes_2) - 1):
            y1 = int(y_cortes_2[i])
            y2 = int(y_cortes_2[i + 1])
            if y2 > y1:
                filas_reintento.append({"y1": y1, "y2": y2})

        if len(filas_reintento) >= n_filas_esperadas:
            exceso = len(filas_reintento) - n_filas_esperadas

            if exceso <= EXCESO_MAXIMO_ENCABEZADO:
                logger.info("Reintento: %d filas, tomando últimas %d.",
                            len(filas_reintento), n_filas_esperadas)
                return filas_reintento[exceso:]

            filas_filtradas = _filtrar_filas_por_altura(
                filas_reintento, n_filas_esperadas
            )
            if filas_filtradas and len(filas_filtradas) == n_filas_esperadas:
                logger.info("Reintento + filtro: %d. ✓", len(filas_filtradas))
                return filas_filtradas

    logger.warning("Reintento sin éxito. Usando fallback.")
    return _filas_uniformes(h, n_filas_esperadas)


# =============================================================================
# DETECCIÓN DE LÍNEA FALTANTE
# =============================================================================

def _detectar_linea_faltante(
    lineas_h: np.ndarray,
    y_cortes: List[int],
    h: int
) -> List[int]:
    """
    Detecta líneas horizontales faltantes en intervalos anormalmente largos.

    Si el espacio entre dos cortes consecutivos es >1.6x la mediana,
    busca un pico local en la proyección de esa zona y añade un corte.
    """
    if len(y_cortes) < 3:
        return y_cortes

    proy_y = np.sum(lineas_h, axis=1)

    if proy_y.size == 0 or np.max(proy_y) == 0:
        return y_cortes

    espacios = [y_cortes[i + 1] - y_cortes[i] for i in range(len(y_cortes) - 1)]
    if not espacios:
        return y_cortes

    espacio_promedio = float(np.median(espacios))
    umbral_espacio = espacio_promedio * FACTOR_ESPACIO_ANOMALO

    y_cortes_nuevos = [y_cortes[0]]
    añadidas = 0

    for i in range(len(y_cortes) - 1):
        y1 = y_cortes[i]
        y2 = y_cortes[i + 1]
        espacio = y2 - y1

        if espacio > umbral_espacio:
            zona = proy_y[y1:y2]
            if len(zona) > 10:
                centro_ini = len(zona) // 3
                centro_fin = (2 * len(zona)) // 3
                zona_central = zona[centro_ini:centro_fin]

                if len(zona_central) > 0:
                    idx_max_rel = int(np.argmax(zona_central))
                    idx_max = idx_max_rel + centro_ini
                    max_zona = float(np.max(zona))
                    umbral_local = max_zona * UMBRAL_PICO_LOCAL

                    if zona[idx_max] > umbral_local:
                        y_nuevo = y1 + idx_max
                        y_cortes_nuevos.append(y_nuevo)
                        añadidas += 1
                        logger.info(
                            "Línea faltante detectada en y=%d (espacio %d > %.0f).",
                            y_nuevo, espacio, umbral_espacio
                        )

        y_cortes_nuevos.append(y2)

    if añadidas > 0:
        logger.info("Líneas faltantes añadidas: %d (%d → %d cortes).",
                    añadidas, len(y_cortes), len(y_cortes_nuevos))

    return y_cortes_nuevos


# =============================================================================
# DETECCIÓN DE COLUMNAS
# =============================================================================

def _detectar_columnas(lineas_v: np.ndarray, w: int) -> List[int]:
    """
    Detecta los 4 cortes X de la tabla.

    Pasos:
      1. Proyección X con umbral.
      2. Agrupación de picos cercanos.
      3. Selección robusta del mejor par (corte_n, corte_no).
    """
    proy_x = np.sum(lineas_v, axis=0)

    if proy_x.size == 0 or np.max(proy_x) == 0:
        logger.warning("Sin proyección X válida. Usando cortes proporcionales.")
        return _cortes_x_esperados(w)

    umbral_x = float(np.max(proy_x)) * UMBRAL_PROY_X
    x_picos = np.where(proy_x > umbral_x)[0].tolist()

    if not x_picos:
        logger.warning("Sin picos X. Usando cortes proporcionales.")
        return _cortes_x_esperados(w)

    x_cortes_detectados = agrupar_coordenadas_cercanas(
        x_picos, distancia_minima=DISTANCIA_MINIMA_X
    )

    logger.info("Cortes X detectados: %d -> %s",
                len(x_cortes_detectados), x_cortes_detectados)

    return _seleccionar_x_cortes(x_cortes_detectados, w)


def _seleccionar_x_cortes(x_detectados: List[int], w: int) -> List[int]:
    """
    Selecciona exactamente 4 cortes X: [0, corte_n, corte_no, w].

    Robusto a:
      - Cortes extra (ruido, líneas verticales tenues o dobles).
      - Cortes duplicados.
      - Cortes faltantes.
      - Layout con proporciones horizontales ligeramente variables.

    Estrategia:
      1. Filtrar cortes válidos (excluir extremos).
      2. Buscar el MEJOR par (corte_n, corte_no) entre todos los válidos:
         - Cumplan con los rangos RANGO_N y RANGO_NO.
         - Tengan separación mínima entre sí y con w.
         - Minimicen la desviación respecto a las proporciones esperadas.
      3. Forzar 0 y w como extremos SIEMPRE.
      4. Si no hay par válido, usar proporciones esperadas.
    """
    if w <= 0:
        return [0, 0, 0, 0]

    # -------------------------------------------------------------------------
    # 1. Filtrar cortes válidos (excluir extremos)
    # -------------------------------------------------------------------------
    validos = []
    for x in sorted(x_detectados):
        if x <= 0 or x >= w:
            continue
        prop = x / w
        if MARGEN_EXTREMO < prop < (1 - MARGEN_EXTREMO):
            validos.append(x)

    if not validos:
        logger.info("Sin cortes X válidos en rango. Usando proporciones.")
        return _cortes_x_esperados(w)

    logger.debug("Cortes X válidos tras filtrar extremos: %s", validos)

    # -------------------------------------------------------------------------
    # 2. Buscar el MEJOR par (corte_n, corte_no)
    # -------------------------------------------------------------------------
    mejor_par = None
    mejor_score = -float("inf")

    # Separaciones mínimas
    sep_min_x = w * SEPARACION_MINIMA_X
    sep_min_w = w * SEPARACION_MINIMA_W

    for i, x1 in enumerate(validos):
        prop1 = x1 / w

        # x1 debe estar en el rango de N°
        if not (RANGO_N[0] <= prop1 <= RANGO_N[1]):
            continue

        for x2 in validos[i + 1:]:
            prop2 = x2 / w

            # x2 debe estar en el rango de No
            if not (RANGO_NO[0] <= prop2 <= RANGO_NO[1]):
                continue

            # Separación mínima entre cortes
            if x2 - x1 < sep_min_x:
                continue

            # Separación mínima del último corte con w
            if w - x2 < sep_min_w:
                continue

            # Score: proximidad a las proporciones esperadas
            desviacion_n = abs(prop1 - PROP_N_FIN)
            desviacion_no = abs(prop2 - PROP_NO_FIN)
            score = -(desviacion_n + desviacion_no)

            if score > mejor_score:
                mejor_score = score
                mejor_par = (x1, x2)

    # -------------------------------------------------------------------------
    # 3. Devolver el mejor par (o fallback)
    # -------------------------------------------------------------------------
    if mejor_par:
        corte_n, corte_no = mejor_par
        logger.info(
            "Cortes X seleccionados: corte_n=%d (%.1f%%), corte_no=%d (%.1f%%), w=%d",
            corte_n, corte_n / w * 100,
            corte_no, corte_no / w * 100,
            w
        )
        return [0, corte_n, corte_no, w]

    # -------------------------------------------------------------------------
    # 4. Fallback: proporciones esperadas
    # -------------------------------------------------------------------------
    logger.info("Sin par de cortes X válido. Usando proporciones esperadas.")
    return _cortes_x_esperados(w)


def _cortes_x_esperados(w: int) -> List[int]:
    """Cortes X proporcionales al layout IEPPO."""
    if w <= 0:
        return [0, 0, 0, 0]
    return [
        0,
        int(w * PROP_N_FIN),
        int(w * PROP_NO_FIN),
        w,
    ]


# =============================================================================
# FILTRADO POR ALTURA UNIFORME
# =============================================================================

def _filtrar_filas_por_altura(
    filas: List[Dict[str, int]],
    n_objetivo: int
) -> List[Dict[str, int]]:
    """
    Filtra filas para quedarse con las n_objetivo más uniformes en altura.

    Estrategia:
      1. Calcular mediana de alturas.
      2. Filtrar por rango [0.5×mediana, 1.8×mediana].
      3. Si quedan pocas, relajar el filtro a [0.3×, 2.5×].
      4. Si aún no alcanza, devolver las primeras n_objetivo.
      5. Ordenar las válidas por cercanía a la mediana.
    """
    if len(filas) <= n_objetivo:
        return filas

    alturas = np.array([f["y2"] - f["y1"] for f in filas], dtype=float)
    if len(alturas) == 0:
        return []

    mediana = float(np.median(alturas))
    if mediana <= 0:
        return filas[:n_objetivo]

    # Filtro inicial
    indices_validos = _aplicar_filtro_altura(
        alturas, mediana, FILTRO_ALTURA_MIN, FILTRO_ALTURA_MAX
    )

    # Relajar si quedan pocas
    if len(indices_validos) < n_objetivo:
        indices_validos = _aplicar_filtro_altura(
            alturas, mediana, FILTRO_ALTURA_MIN_RELAJADO, FILTRO_ALTURA_MAX_RELAJADO
        )

    if len(indices_validos) < n_objetivo:
        logger.warning("Filtro dejó %d filas de %d necesarias.",
                       len(indices_validos), n_objetivo)
        return filas[:n_objetivo]

    # Ordenar por cercanía a la mediana
    alturas_validas = alturas[indices_validos]
    distancias = np.abs(alturas_validas - mediana)
    indices_ordenados = np.argsort(distancias)

    # Tomar los n_objetivo más uniformes, preservando orden por Y
    indices_top = sorted(indices_validos[i] for i in indices_ordenados[:n_objetivo])

    return [filas[i] for i in indices_top]


def _aplicar_filtro_altura(
    alturas: np.ndarray,
    mediana: float,
    factor_min: float,
    factor_max: float
) -> List[int]:
    """Aplica filtro de altura y retorna los índices válidos."""
    limite_inferior = factor_min * mediana
    limite_superior = factor_max * mediana
    return [
        i for i, h in enumerate(alturas)
        if limite_inferior <= h <= limite_superior
    ]


# =============================================================================
# FALLBACK: FILAS UNIFORMES
# =============================================================================

def _filas_uniformes(h: int, n_filas_esperadas: int) -> List[Dict[str, int]]:
    """
    Divide la altura en n filas uniformes.

    Deja un margen superior para el encabezado (5% de la altura, mínimo 30px).
    """
    if h <= 0 or n_filas_esperadas <= 0:
        return []

    margen = max(30, int(h * 0.05))
    altura_util = h - margen

    if altura_util <= 0:
        return []

    paso = altura_util / n_filas_esperadas

    filas = []
    for i in range(n_filas_esperadas):
        y1 = int(margen + i * paso)
        y2 = int(margen + (i + 1) * paso)
        filas.append({"y1": y1, "y2": min(h, y2)})

    return filas

