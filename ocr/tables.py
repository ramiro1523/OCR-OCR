import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

def extraer_rejilla_lineas(binaria: np.ndarray, escala: int = 30) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extrae las líneas horizontales y verticales de una imagen binaria (donde el fondo es 255 y tinta es 0).
    Retorna: (lineas_h, lineas_v, rejilla_combinada)
    """
    # Invertir para que las líneas sean blancas (255) sobre fondo negro (0)
    inv = cv2.bitwise_not(binaria)
    
    h, w = binaria.shape[:2]
    
    # Kernel horizontal
    longitud_h = max(20, w // escala)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (longitud_h, 1))
    lineas_h = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel_h, iterations=2)
    
    # Kernel vertical
    longitud_v = max(20, h // escala)
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, longitud_v))
    lineas_v = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel_v, iterations=2)
    
    # Combinar ambas
    rejilla = cv2.addWeighted(lineas_h, 0.5, lineas_v, 0.5, 0.0)
    _, rejilla_bin = cv2.threshold(rejilla, 50, 255, cv2.THRESH_BINARY)
    
    return lineas_h, lineas_v, rejilla_bin


def detectar_tablas(binaria: np.ndarray, min_area_ratio: float = 0.03) -> List[Dict[str, Any]]:
    """
    Detecta las regiones correspondientes a tablas rectangulares en el documento.
    """
    h_doc, w_doc = binaria.shape[:2]
    area_minima = (h_doc * w_doc) * min_area_ratio
    
    _, _, rejilla = extraer_rejilla_lineas(binaria)
    
    contornos, _ = cv2.findContours(rejilla, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    tablas = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area >= area_minima and w > (w_doc * 0.2) and h > (h_doc * 0.1):
            tablas.append({
                "x": x, "y": y, "w": w, "h": h,
                "area": area,
                "roi_binaria": binaria[y:y+h, x:x+w]
            })
            
    # Ordenar tablas de arriba hacia abajo (y de izquierda a derecha)
    tablas.sort(key=lambda t: (t["y"], t["x"]))
    return tablas


def extraer_celdas_tabla(tabla_binaria: np.ndarray) -> List[Dict[str, Any]]:
    """
    Extrae las celdas individuales dentro de una tabla recortada.
    """
    _, _, rejilla = extraer_rejilla_lineas(tabla_binaria, escala=25)
    contornos, _ = cv2.findContours(rejilla, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    h_t, w_t = tabla_binaria.shape[:2]
    celdas = []
    
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        # Filtrar celdas que no sean ni toda la tabla ni ruido diminuto
        if (15 < w < w_t * 0.95) and (10 < h < h_t * 0.2):
            celdas.append({
                "x": x, "y": y, "w": w, "h": h,
                "cx": x + w // 2,
                "cy": y + h // 2
            })
            
    # Ordenar por fila (y) y luego por columna (x) con tolerancia vertical
    if celdas:
        altura_media_celda = np.median([c["h"] for c in celdas])
        tolerancia_y = max(5, int(altura_media_celda * 0.5))
        
        celdas.sort(key=lambda c: (c["y"] // tolerancia_y, c["x"]))
        
    return celdas
