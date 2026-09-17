import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

def convertir_a_grises(imagen: np.ndarray) -> np.ndarray:
    """Convierte una imagen BGR o RGB a escala de grises."""
    if len(imagen.shape) == 2:
        return imagen
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


def corregir_inclinacion(gris: np.ndarray, max_angulo: float = 15.0) -> tuple[np.ndarray, float]:
    """
    Detecta y corrige pequeñas inclinaciones (deskew) en documentos escaneados.
    Retorna la imagen corregida y el ángulo de rotación aplicado en grados.
    """
    h, w = gris.shape[:2]
    
    # Binarización invertida para detectar texto y líneas
    _, thresh = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Detección de líneas horizontales para medir el ángulo
    lineas = cv2.HoughLinesP(
        thresh, 1, np.pi / 180, threshold=150,
        minLineLength=w // 6, maxLineGap=20
    )
    
    angulos = []
    if lineas is not None:
        for linea in lineas:
            x1, y1, x2, y2 = linea[0]
            if x2 != x1:
                angulo = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                # Filtrar solo líneas casi horizontales
                if -max_angulo <= angulo <= max_angulo:
                    angulos.append(angulo)
                    
    angulo_mediano = float(np.median(angulos)) if angulos else 0.0
    
    if abs(angulo_mediano) > 0.2:
        centro = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(centro, angulo_mediano, 1.0)
        corregida = cv2.warpAffine(
            gris, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        return corregida, angulo_mediano
        
    return gris, 0.0


def binarizar(gris: np.ndarray, metodo: str = "otsu") -> np.ndarray:
    """
    Binariza la imagen en escala de grises.
    Retorna imagen binaria donde 255 es blanco y 0 es negro.
    """
    if metodo == "adaptativo":
        return cv2.adaptiveThreshold(
            gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 21, 10
        )
    else:
        # Otsu con desenfoque Gaussiano ligero para eliminar motas
        desenfoque = cv2.GaussianBlur(gris, (3, 3), 0)
        _, binaria = cv2.threshold(desenfoque, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binaria


def preprocesar_imagen(imagen: np.ndarray) -> dict:
    """
    Pipeline completo de preprocesamiento de una página escaneada.
    Retorna diccionario con la imagen original, gris corregida y binaria.
    """
    gris = convertir_a_grises(imagen)
    corregida, angulo = corregir_inclinacion(gris)
    binaria = binarizar(corregida, metodo="otsu")
    
    return {
        "gris": corregida,
        "binaria": binaria,
        "angulo_correccion": angulo
    }
