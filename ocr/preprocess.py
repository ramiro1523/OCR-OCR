"""
Preprocesamiento de imágenes para el pipeline OCR IEPPO.

CONFIGURACIÓN ACTUAL:
  - Sustracción de fondo: DESACTIVADA
  - Filtro bilateral: DESACTIVADA
  - CLAHE: DESACTIVADA
  - Sharpen: DESACTIVADO

Esto mantiene la coherencia con la plantilla y calibración de marks.py.
"""

import logging
import os
import platform
from typing import Dict, Any, Tuple

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
# FLAGS DE MEJORAS (TODOS DESACTIVADOS)
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
# FUNCIONES PÚBLICAS
# =============================================================================

def convertir_a_gris(imagen: np.ndarray) -> np.ndarray:
    if imagen is None or imagen.size == 0:
        return imagen
    if len(imagen.shape) == 2:
        return imagen
    if imagen.shape[2] == 4:
        return cv2.cvtColor(imagen, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


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
        corregida = cv2.warpAffine(
            gris, matriz, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        logger.info("Deskew aplicado: %.2f°", angulo_mediana)
        return corregida, angulo_mediana

    except Exception as e:
        logger.error("Error en deskew: %s", e, exc_info=True)
        return gris, 0.0


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
# FUNCIONES DE MEJORA (opcionales, desactivadas)
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
    metodo_binarizacion: str = "otsu"
) -> Dict[str, Any]:
    if imagen is None or imagen.size == 0:
        logger.error("preprocesar_imagen: imagen vacía.")
        vacio = np.zeros((100, 100), dtype=np.uint8)
        return {"gris": vacio, "binaria": vacio, "angulo_correccion": 0.0}

    # 1. Escala de grises
    gris = convertir_a_gris(imagen)

    # 2-5. Mejoras opcionales (todas desactivadas por defecto)
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

    # 6. Deskew
    gris_corregido, angulo = corregir_inclinacion(gris)

    # 7. Binarización
    binaria = binarizar(gris_corregido, metodo=metodo_binarizacion)

    return {
        "gris": gris_corregido,
        "binaria": binaria,
        "angulo_correccion": angulo,
    }