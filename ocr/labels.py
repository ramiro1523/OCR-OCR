import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)

def tesseract_disponible() -> bool:
    """Verifica si pytesseract y el ejecutable tesseract están configurados y disponibles."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def leer_texto_celda(celda_gris: np.ndarray, config: str = "--psm 7") -> str:
    """
    Lee el texto de una celda o región usando Tesseract si está disponible.
    Si no está disponible, retorna cadena vacía sin fallar.
    """
    if not tesseract_disponible():
        return ""
        
    try:
        import pytesseract
        # Limpieza ligera
        h, w = celda_gris.shape[:2]
        if h < 20 or w < 20:
            celda_gris = cv2.resize(celda_gris, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
            
        texto = pytesseract.image_to_string(celda_gris, config=config, lang="spa+eng")
        return texto.strip()
    except Exception as e:
        logger.debug("Tesseract no pudo leer la celda: %s", e)
        return ""


def buscar_ancla(imagen_gris: np.ndarray, texto_buscar: str) -> list[dict]:
    """
    Busca coordenadas de palabras clave en el documento para alinear cuadrículas.
    """
    if not tesseract_disponible():
        return []
        
    try:
        import pytesseract
        datos = pytesseract.image_to_data(imagen_gris, lang="spa+eng", output_type=pytesseract.Output.DICT)
        
        coincidencias = []
        n_cajas = len(datos["text"])
        for i in range(n_cajas):
            texto = datos["text"][i].strip().upper()
            if texto_buscar.upper() in texto:
                coincidencias.append({
                    "texto": texto,
                    "x": datos["left"][i],
                    "y": datos["top"][i],
                    "w": datos["width"][i],
                    "h": datos["height"][i]
                })
        return coincidencias
    except Exception as e:
        logger.debug("Error buscando ancla con Tesseract: %s", e)
        return []
