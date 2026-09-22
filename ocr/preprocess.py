"""
Preprocesamiento de imágenes para el pipeline OCR IEPPO.

Pipeline:
  0. Conversión a escala de grises.
  1. Detección de si es FOTO o ESCÁNER.
     - Si es foto: detectar hoja + warp de perspectiva (endereza).
     - Si es escáner: saltar (ya viene plana).
  2. Normalización de iluminación (solo si es foto).
  3. Deskew (rotación leve residual).
  4. Binarización (Otsu o adaptativa).

Configuración de mejoras opcionales:
  - Sustracción de fondo: DESACTIVADA
  - Filtro bilateral: DESACTIVADA
  - CLAHE: DESACTIVADA
  - Sharpen: DESACTIVADO

FASE 2 aplicada:
  - _detectar_hoja_y_enderezar: detecta el contorno rectangular de la
    hoja y aplica warp de perspectiva. Resuelve fotos torcidas/en ángulo.
  - _normalizar_iluminacion: elimina sombras y gradientes de luz
    dividiendo por un fondo estimado con blur grande.
  - _es_foto: clasifica automáticamente el origen según contenido en
    los bordes de la imagen.

FASE 3.5 aplicada:
  - Deskew usa BORDER_CONSTANT (blanco puro) en vez de BORDER_REPLICATE
    para no crear franjas negras en las esquinas rotadas que tables.py
    confundiría con marcos de tabla.
"""

import logging
import os
import platform
from typing import Dict, Any, Tuple, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN DE TESSERACT
# =============================================================================

try:
    import pytesseract
    if platform.system() == "Windows":
        rutas_posibles = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for ruta in rutas_posibles:
            if os.path.exists(ruta):
                pytesseract.pytesseract.tesseract_cmd = ruta
                logger.info("Tesseract configurado en: %s", ruta)
                break
except Exception as e:
    logger.warning("No se pudo configurar pytesseract: %s", e)


# =============================================================================
# CONFIGURACIÓN DE DESKEW
# =============================================================================

ANGULO_MAXIMO_DESKEW = 15.0
ANGULO_MINIMO_DESKEW = 0.3
HOUGH_THRESHOLD = 100
HOUGH_MIN_LINE_LENGTH_FACTOR = 0.3
HOUGH_MAX_LINE_GAP = 20


# =============================================================================
# CONFIGURACIÓN DE DETECCIÓN FOTO vs ESCÁNER
# =============================================================================

# Si el porcentaje de píxeles oscuros en el marco exterior supera este
# umbral, se asume FOTO (mesa, fondo, sombras alrededor de la hoja).
# Un escáner tiene los bordes casi blancos → muy pocos oscuros.
UMBRAL_OSCURO_BORDE_FOTO = 0.02
ANCHO_MARCO_BORDE = 0.03   # 3% del ancho/alto en cada borde


# =============================================================================
# CONFIGURACIÓN DE DETECCIÓN DE HOJA
# =============================================================================

# Área mínima de la hoja respecto al área total de la imagen.
# 0.20 = la hoja ocupa al menos 20% de la foto. Descarta contornos
# pequeños (objetos, dedos, etc.).
AREA_MINIMA_HOJA = 0.20

# Epsilon para approxPolyDP (porcentaje del perímetro del contorno).
# 0.02 = aproximación moderada, acepta esquinas ligeramente curvas.
EPSILON_POLY = 0.02


# =============================================================================
# CONFIGURACIÓN DE NORMALIZACIÓN DE ILUMINACIÓN
# =============================================================================

# Tamaño del kernel para estimar el fondo (fracción del menor lado).
# Un valor muy pequeño deja pasar las sombras; muy grande las exagera.
FACTOR_BLUR_ILUMINACION = 0.04


# =============================================================================
# FLAGS DE MEJORAS OPCIONALES (TODAS DESACTIVADAS)
# =============================================================================

APLICAR_SUSTRACCION_FONDO = False
TAMANO_BLUR_FONDO = 71

APLICAR_FILTRO_BILATERAL = False
BILATERAL_D = 5
BILATERAL_SIGMA_COLOR = 50
BILATERAL_SIGMA_SPACE = 50

APLICAR_CLAHE = False
CLAHE_CLIP_LIMIT = 2.5
CLAHE_TILE_GRID = (8, 8)

APLICAR_SHARPEN = False
SHARPEN_SIGMA = 1.0
SHARPEN_STRENGTH = 1.5


# =============================================================================
# FUNCIONES BÁSICAS
# =============================================================================

def convertir_a_gris(imagen: np.ndarray) -> np.ndarray:
    if imagen is None or imagen.size == 0:
        return imagen
    if len(imagen.shape) == 2:
        return imagen
    if imagen.shape[2] == 4:
        return cv2.cvtColor(imagen, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


# =============================================================================
# DETECCIÓN FOTO vs ESCÁNER
# =============================================================================

def _es_foto(gris: np.ndarray) -> bool:
    """
    Decide si la imagen proviene de una foto o de un escáner.

    Criterio: en un escáner, los bordes de la imagen son papel blanco
    (casi sin píxeles oscuros). En una foto, los bordes suelen contener
    el fondo (mesa, sombra, dedos) → más píxeles oscuros.

    Returns:
        True si parece foto, False si parece escáner.
    """
    if gris is None or gris.size == 0:
        return False

    h, w = gris.shape[:2]
    if h < 50 or w < 50:
        return False

    # Marco exterior (borde de 3% en cada lado)
    mh = max(2, int(h * ANCHO_MARCO_BORDE))
    mw = max(2, int(w * ANCHO_MARCO_BORDE))

    marcos = [
        gris[:mh, :],           # arriba
        gris[-mh:, :],          # abajo
        gris[:, :mw],           # izquierda
        gris[:, -mw:],          # derecha
    ]

    total_pix = 0
    total_oscuros = 0
    for m in marcos:
        if m.size == 0:
            continue
        total_pix += m.size
        total_oscuros += int(np.sum(m < 128))

    if total_pix == 0:
        return False

    proporcion_oscura = total_oscuros / total_pix

    es = proporcion_oscura > UMBRAL_OSCURO_BORDE_FOTO
    logger.info(
        "Detección foto/escáner: %.2f%% oscuro en bordes (umbral %.1f%%) → %s",
        proporcion_oscura * 100.0,
        UMBRAL_OSCURO_BORDE_FOTO * 100.0,
        "FOTO" if es else "ESCÁNER",
    )
    return es


# =============================================================================
# DETECCIÓN DE HOJA Y WARP DE PERSPECTIVA
# =============================================================================

def _ordenar_puntos(pts: np.ndarray) -> np.ndarray:
    """
    Ordena 4 puntos como [top-left, top-right, bottom-right, bottom-left].

    Args:
        pts: array (4, 2) float32.

    Returns:
        array (4, 2) float32 reordenado.
    """
    pts = pts.reshape(4, 2).astype(np.float32)

    # Suma y diferencia para clasificar esquinas
    suma = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(suma)]
    br = pts[np.argmax(suma)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _detectar_contorno_hoja(gris: np.ndarray) -> Optional[np.ndarray]:
    """
    Detecta el contorno rectangular de la hoja en una foto.

    Estrategia:
      1. Suavizar + Canny + dilatar para cerrar huecos.
      2. Encontrar contornos externos.
      3. Buscar el contorno con 4 esquinas y área grande.
      4. Fallback: usar minAreaRect del contorno más grande.

    Returns:
        Array (4, 2) float32 con las 4 esquinas ordenadas, o None.
    """
    h, w = gris.shape[:2]
    area_imagen = h * w

    # 1. Suavizar y detectar bordes
    blur = cv2.GaussianBlur(gris, (5, 5), 0)
    bordes = cv2.Canny(blur, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    bordes = cv2.dilate(bordes, kernel, iterations=1)
    bordes = cv2.morphologyEx(bordes, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 2. Contornos externos
    contornos, _ = cv2.findContours(
        bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contornos:
        logger.warning("No se detectaron contornos en la foto.")
        return None

    # 3. Buscar el mejor contorno de 4 lados
    mejor_poly = None
    mejor_area = 0.0

    for c in sorted(contornos, key=cv2.contourArea, reverse=True)[:10]:
        area = cv2.contourArea(c)
        if area < area_imagen * AREA_MINIMA_HOJA:
            continue

        perim = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, EPSILON_POLY * perim, True)

        if len(approx) == 4:
            if area > mejor_area:
                mejor_area = area
                mejor_poly = approx

    if mejor_poly is not None:
        logger.info(
            "Hoja detectada con 4 esquinas (área=%.1f%% de la imagen).",
            100.0 * mejor_area / area_imagen,
        )
        return _ordenar_puntos(mejor_poly)

    # 4. Fallback: minAreaRect del contorno más grande
    contorno_mas_grande = max(contornos, key=cv2.contourArea)
    area_grande = cv2.contourArea(contorno_mas_grande)

    if area_grande < area_imagen * AREA_MINIMA_HOJA:
        logger.warning(
            "Contorno más grande solo cubre %.1f%% de la imagen. "
            "No se puede detectar hoja.",
            100.0 * area_grande / area_imagen,
        )
        return None

    rect = cv2.minAreaRect(contorno_mas_grande)
    caja = cv2.boxPoints(rect)
    logger.info(
        "Hoja detectada por minAreaRect (área=%.1f%%).",
        100.0 * area_grande / area_imagen,
    )
    return _ordenar_puntos(caja)


def _warp_perspectiva(gris: np.ndarray, esquinas: np.ndarray) -> np.ndarray:
    """
    Aplica warp de perspectiva para enderezar la hoja.

    Calcula el tamaño destino a partir de las distancias entre esquinas
    y aplica getPerspectiveTransform + warpPerspective.
    """
    tl, tr, br, bl = esquinas

    ancho_a = np.linalg.norm(br - bl)
    ancho_b = np.linalg.norm(tr - tl)
    ancho_dst = int(max(ancho_a, ancho_b))

    alto_a = np.linalg.norm(tr - br)
    alto_b = np.linalg.norm(tl - bl)
    alto_dst = int(max(alto_a, alto_b))

    if ancho_dst < 50 or alto_dst < 50:
        logger.warning(
            "Tamaño destino inválido tras warp (%dx%d). Se omite.",
            ancho_dst, alto_dst,
        )
        return gris

    dst = np.array([
        [0, 0],
        [ancho_dst - 1, 0],
        [ancho_dst - 1, alto_dst - 1],
        [0, alto_dst - 1],
    ], dtype=np.float32)

    M = cv2.getPerspectiveTransform(esquinas, dst)
    warpeada = cv2.warpPerspective(
        gris, M, (ancho_dst, alto_dst),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )

    logger.info(
        "Warp aplicado: %s → %dx%d",
        gris.shape, ancho_dst, alto_dst,
    )
    return warpeada


def _detectar_hoja_y_enderezar(gris: np.ndarray) -> np.ndarray:
    """
    Envuelve detección + warp. Si algo falla, devuelve el gris original.
    """
    try:
        esquinas = _detectar_contorno_hoja(gris)
        if esquinas is None:
            logger.info("No se detectó hoja. Se mantiene la imagen original.")
            return gris

        return _warp_perspectiva(gris, esquinas)

    except Exception as e:
        logger.warning("Error en detección/warp de hoja: %s", e)
        return gris


# =============================================================================
# NORMALIZACIÓN DE ILUMINACIÓN
# =============================================================================

def _normalizar_iluminacion(gris: np.ndarray) -> np.ndarray:
    """
    Elimina sombras y gradientes de iluminación.

    Estima el fondo con un blur grande y divide la imagen original por
    ese fondo. Las zonas oscuras (tinta, texto) quedan oscuras; las
    zonas claras (papel) quedan uniformemente claras, sin importar la
    iluminación original.

    Fórmula: normalizada = (gris / fondo) * 255
    """
    try:
        h, w = gris.shape[:2]
        lado_menor = min(h, w)

        # Kernel del blur: impar, proporcional al tamaño de la imagen
        ksize = max(31, int(lado_menor * FACTOR_BLUR_ILUMINACION))
        if ksize % 2 == 0:
            ksize += 1
        ksize = min(ksize, lado_menor - 1 if lado_menor % 2 == 1 else lado_menor - 2)

        if ksize < 15:
            logger.warning("Imagen muy pequeña para normalizar iluminación.")
            return gris

        # Fondo estimado
        fondo = cv2.GaussianBlur(gris, (ksize, ksize), 0)

        # Evitar divisiones por cero
        fondo_f = fondo.astype(np.float32)
        fondo_f = np.where(fondo_f < 1.0, 1.0, fondo_f)

        gris_f = gris.astype(np.float32)
        normalizada = (gris_f / fondo_f) * 255.0
        normalizada = np.clip(normalizada, 0, 255).astype(np.uint8)

        logger.info(
            "Iluminación normalizada (kernel=%d, imagen %dx%d).",
            ksize, w, h,
        )
        return normalizada

    except Exception as e:
        logger.warning("Error en normalización de iluminación: %s", e)
        return gris


# =============================================================================
# DESKEW (con BORDER_CONSTANT tras Fase 3.5)
# =============================================================================

def corregir_inclinacion(gris: np.ndarray) -> Tuple[np.ndarray, float]:
    if gris is None or gris.size == 0:
        return gris, 0.0

    try:
        bordes = cv2.Canny(gris, 50, 150, apertureSize=3)
        h, w = gris.shape[:2]
        min_line_length = max(100, int(w * HOUGH_MIN_LINE_LENGTH_FACTOR))

        lineas = cv2.HoughLinesP(
            bordes, rho=1, theta=np.pi / 180,
            threshold=HOUGH_THRESHOLD,
            minLineLength=min_line_length,
            maxLineGap=HOUGH_MAX_LINE_GAP,
        )

        if lineas is None or len(lineas) == 0:
            return gris, 0.0

        angulos = []
        for linea in lineas:
            coords = np.asarray(linea).ravel()
            if coords.size < 4:
                continue
            x1, y1, x2, y2 = coords[:4]
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) < 1:
                continue
            angulo = np.degrees(np.arctan2(dy, dx))
            if angulo < -45:
                angulo += 90
            elif angulo > 45:
                angulo -= 90
            angulos.append(angulo)

        if not angulos:
            return gris, 0.0

        angulo_mediana = float(np.median(angulos))

        if abs(angulo_mediana) < ANGULO_MINIMO_DESKEW:
            return gris, 0.0
        if abs(angulo_mediana) > ANGULO_MAXIMO_DESKEW:
            logger.warning("Deskew %.2f° fuera de rango.", angulo_mediana)
            return gris, 0.0

        centro = (w // 2, h // 2)
        matriz = cv2.getRotationMatrix2D(centro, angulo_mediana, 1.0)

        # FASE 3.5: BORDER_CONSTANT blanco en vez de BORDER_REPLICATE
        corregida = cv2.warpAffine(
            gris, matriz, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )

        logger.info("Deskew aplicado: %.2f°", angulo_mediana)
        return corregida, angulo_mediana

    except Exception as e:
        logger.error("Error en deskew: %s", e, exc_info=True)
        return gris, 0.0


# =============================================================================
# BINARIZACIÓN
# =============================================================================

def binarizar(gris: np.ndarray, metodo: str = "otsu") -> np.ndarray:
    if gris is None or gris.size == 0:
        return gris

    try:
        if metodo == "otsu":
            _, binaria = cv2.threshold(
                gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        elif metodo == "adaptativo":
            binaria = cv2.adaptiveThreshold(
                gris, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=31, C=10,
            )
        else:
            _, binaria = cv2.threshold(
                gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        return binaria
    except Exception as e:
        logger.error("Error en binarizar: %s", e, exc_info=True)
        return gris


# =============================================================================
# FUNCIONES DE MEJORA OPCIONALES (DESACTIVADAS)
# =============================================================================

def sustraer_fondo(gris: np.ndarray) -> np.ndarray:
    if gris is None or gris.size == 0:
        return gris
    try:
        h, w = gris.shape[:2]
        kernel = TAMANO_BLUR_FONDO
        if kernel % 2 == 0:
            kernel += 1
        kernel = min(kernel, min(h, w) - 1)
        if kernel < 5:
            return gris

        fondo = cv2.medianBlur(gris, kernel)
        gris_float = gris.astype(np.float32)
        fondo_float = fondo.astype(np.float32)
        fondo_float = np.where(fondo_float < 1.0, 1.0, fondo_float)
        corregido = (gris_float / fondo_float) * 255.0
        corregido = np.clip(corregido, 0, 255).astype(np.uint8)
        return corregido
    except Exception as e:
        logger.warning("Sustracción de fondo falló: %s", e)
        return gris


def aplicar_filtro_bilateral(gris: np.ndarray) -> np.ndarray:
    if gris is None or gris.size == 0:
        return gris
    try:
        return cv2.bilateralFilter(
            gris, d=BILATERAL_D,
            sigmaColor=BILATERAL_SIGMA_COLOR,
            sigmaSpace=BILATERAL_SIGMA_SPACE,
        )
    except Exception as e:
        logger.warning("Filtro bilateral falló: %s", e)
        return gris


def aplicar_clahe(gris: np.ndarray) -> np.ndarray:
    if gris is None or gris.size == 0:
        return gris
    try:
        clahe = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP_LIMIT,
            tileGridSize=CLAHE_TILE_GRID,
        )
        return clahe.apply(gris)
    except Exception as e:
        logger.warning("CLAHE falló: %s", e)
        return gris


def aplicar_sharpen(gris: np.ndarray) -> np.ndarray:
    if gris is None or gris.size == 0:
        return gris
    try:
        blur = cv2.GaussianBlur(gris, (0, 0), SHARPEN_SIGMA)
        return cv2.addWeighted(
            gris, 1.0 + SHARPEN_STRENGTH,
            blur, -SHARPEN_STRENGTH, 0
        )
    except Exception as e:
        logger.warning("Sharpen falló: %s", e)
        return gris


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def preprocesar_imagen(
    imagen: np.ndarray,
    metodo_binarizacion: str = "otsu",
) -> Dict[str, Any]:
    """
    Pipeline completo de preprocesamiento.

    Orden:
      1. Gris.
      2. Detección foto vs escáner.
      3. Si es foto:
         a. Detección de hoja + warp de perspectiva.
         b. Normalización de iluminación.
      4. Mejoras opcionales (todas desactivadas por defecto).
      5. Deskew.
      6. Binarización.

    Returns:
        dict con "gris", "binaria", "angulo_correccion", "es_foto".
    """
    if imagen is None or imagen.size == 0:
        logger.error("preprocesar_imagen: imagen vacía.")
        vacio = np.zeros((100, 100), dtype=np.uint8)
        return {
            "gris": vacio, "binaria": vacio,
            "angulo_correccion": 0.0, "es_foto": False,
        }

    # 1. Escala de grises
    gris = convertir_a_gris(imagen)

    # 2. Detección foto vs escáner
    es_foto = _es_foto(gris)

    # 3. Etapas exclusivas de foto
    if es_foto:
        # 3a. Enderezar (detección de hoja + warp de perspectiva)
        gris = _detectar_hoja_y_enderezar(gris)
        # 3b. Normalizar iluminación
        gris = _normalizar_iluminacion(gris)

    # 4. Mejoras opcionales (todas desactivadas por defecto)
    mejoras_aplicadas = []

    if APLICAR_SUSTRACCION_FONDO:
        gris = sustraer_fondo(gris)
        mejoras_aplicadas.append("sustraccion_fondo")

    if APLICAR_FILTRO_BILATERAL:
        gris = aplicar_filtro_bilateral(gris)
        mejoras_aplicadas.append("filtro_bilateral")

    if APLICAR_CLAHE:
        gris = aplicar_clahe(gris)
        mejoras_aplicadas.append("clahe")

    if APLICAR_SHARPEN:
        gris = aplicar_sharpen(gris)
        mejoras_aplicadas.append("sharpen")

    if mejoras_aplicadas:
        logger.info("Mejoras aplicadas: %s", ", ".join(mejoras_aplicadas))

    # 5. Deskew
    gris_corregido, angulo = corregir_inclinacion(gris)

    # 6. Binarización
    binaria = binarizar(gris_corregido, metodo=metodo_binarizacion)

    return {
        "gris": gris_corregido,
        "binaria": binaria,
        "angulo_correccion": angulo,
        "es_foto": es_foto,
    }