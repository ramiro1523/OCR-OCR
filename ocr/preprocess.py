"""
Preprocesamiento de imágenes para el pipeline OCR IEPPO.

Funciones:
  - convertir_a_gris: BGR → escala de grises.
  - corregir_inclinacion: Deskew mediante HoughLinesP (robusto).
  - binarizar: Otsu o adaptativo.
  - preprocesar_imagen: Pipeline completo.
"""

import logging
import platform
from typing import Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN DE TESSERACT (para que no falle OSD en Windows)
# =============================================================================

try:
    import pytesseract
    if platform.system() == "Windows":
        # Rutas típicas de instalación de Tesseract en Windows
        rutas_posibles = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for ruta in rutas_posibles:
            import os
            if os.path.exists(ruta):
                pytesseract.pytesseract.tesseract_cmd = ruta
                logger.info("Tesseract configurado en: %s", ruta)
                break
except Exception as e:
    logger.warning("No se pudo configurar pytesseract: %s", e)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

ANGULO_MAXIMO_DESKEW = 15.0        # No corregir más de 15° (probable error)
ANGULO_MINIMO_DESKEW = 0.3         # Ignorar ángulos < 0.3°
HOUGH_THRESHOLD = 100              # Umbral HoughLinesP
HOUGH_MIN_LINE_LENGTH_FACTOR = 0.3 # minLineLength = 30% del ancho
HOUGH_MAX_LINE_GAP = 20            # maxLineGap


# =============================================================================
# FUNCIONES PÚBLICAS
# =============================================================================

def convertir_a_gris(imagen: np.ndarray) -> np.ndarray:
    """Convierte BGR o BGRA a escala de grises. Si ya es gris, la retorna."""
    if imagen is None or imagen.size == 0:
        return imagen

    if len(imagen.shape) == 2:
        return imagen

    if imagen.shape[2] == 4:
        return cv2.cvtColor(imagen, cv2.COLOR_BGRA2GRAY)

    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


def corregir_inclinacion(gris: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Corrige la inclinación de una imagen en escala de grises.

    Usa detección de bordes Canny + HoughLinesP para estimar el ángulo
    dominante, y luego rota la imagen para enderezarla.

    Args:
        gris: Imagen en escala de grises.

    Returns:
        (imagen_corregida, angulo_aplicado_grados)
    """
    if gris is None or gris.size == 0:
        return gris, 0.0

    try:
        # 1. Detección de bordes
        bordes = cv2.Canny(gris, 50, 150, apertureSize=3)

        # 2. HoughLinesP para detectar segmentos de línea
        h, w = gris.shape[:2]
        min_line_length = max(100, int(w * HOUGH_MIN_LINE_LENGTH_FACTOR))

        lineas = cv2.HoughLinesP(
            bordes,
            rho=1,
            theta=np.pi / 180,
            threshold=HOUGH_THRESHOLD,
            minLineLength=min_line_length,
            maxLineGap=HOUGH_MAX_LINE_GAP,
        )

        if lineas is None or len(lineas) == 0:
            logger.debug("No se detectaron líneas para deskew.")
            return gris, 0.0

        # 3. Calcular ángulos de las líneas
        angulos = []
        for linea in lineas:
            # Fix crítico: aplanar sin importar la forma (N,1,4) o (N,4)
            coords = np.asarray(linea).ravel()
            if coords.size < 4:
                continue
            x1, y1, x2, y2 = coords[:4]

            # Ignorar líneas casi verticales (no sirven para estimar inclinación)
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) < 1:
                continue

            angulo = np.degrees(np.arctan2(dy, dx))

            # Normalizar a rango [-45, 45]
            if angulo < -45:
                angulo += 90
            elif angulo > 45:
                angulo -= 90

            angulos.append(angulo)

        if not angulos:
            logger.debug("No se obtuvieron ángulos válidos para deskew.")
            return gris, 0.0

        # 4. Ángulo mediana (robusto ante outliers)
        angulo_mediana = float(np.median(angulos))

        # 5. Filtrar ángulos absurdos
        if abs(angulo_mediana) < ANGULO_MINIMO_DESKEW:
            return gris, 0.0
        if abs(angulo_mediana) > ANGULO_MAXIMO_DESKEW:
            logger.warning(
                "Ángulo de deskew %.2f° fuera de rango. Ignorando.",
                angulo_mediana
            )
            return gris, 0.0

        # 6. Rotar la imagen
        centro = (w // 2, h // 2)
        matriz = cv2.getRotationMatrix2D(centro, angulo_mediana, 1.0)
        corregida = cv2.warpAffine(
            gris,
            matriz,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        logger.info("Deskew aplicado: %.2f°", angulo_mediana)
        return corregida, angulo_mediana

    except Exception as e:
        logger.error("Error en corregir_inclinacion: %s", e, exc_info=True)
        return gris, 0.0


def binarizar(
    gris: np.ndarray,
    metodo: str = "otsu"
) -> np.ndarray:
    """
    Binariza una imagen en escala de grises.

    Args:
        gris: Imagen en escala de grises.
        metodo: "otsu" o "adaptativo".

    Returns:
        Imagen binaria (fondo blanco 255, tinta negra 0).
    """
    if gris is None or gris.size == 0:
        return gris

    try:
        if metodo == "otsu":
            _, binaria = cv2.threshold(
                gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        elif metodo == "adaptativo":
            binaria = cv2.adaptiveThreshold(
                gris,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=31,
                C=10,
            )
        else:
            logger.warning("Método de binarización desconocido '%s'. Usando Otsu.", metodo)
            _, binaria = cv2.threshold(
                gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

        return binaria

    except Exception as e:
        logger.error("Error en binarizar: %s", e, exc_info=True)
        return gris


def preprocesar_imagen(
    imagen: np.ndarray,
    metodo_binarizacion: str = "otsu"
) -> Dict[str, Any]:
    """
    Pipeline completo de preprocesamiento.

    Pasos:
      1. Convertir a escala de grises.
      2. Corregir inclinación (deskew).
      3. Binarizar.

    Args:
        imagen: Imagen BGR, BGRA o gris.
        metodo_binarizacion: "otsu" o "adaptativo".

    Returns:
        Dict con:
          - "gris": imagen en escala de grises (corregida).
          - "binaria": imagen binarizada.
          - "angulo_correccion": ángulo aplicado.
    """
    if imagen is None or imagen.size == 0:
        logger.error("preprocesar_imagen: imagen vacía o None.")
        vacio = np.zeros((100, 100), dtype=np.uint8)
        return {
            "gris": vacio,
            "binaria": vacio,
            "angulo_correccion": 0.0,
        }

    # 1. Escala de grises
    gris = convertir_a_gris(imagen)

    # 2. Deskew
    gris_corregido, angulo = corregir_inclinacion(gris)

    # 3. Binarización
    binaria = binarizar(gris_corregido, metodo=metodo_binarizacion)

    return {
        "gris": gris_corregido,
        "binaria": binaria,
        "angulo_correccion": angulo,
    }