import cv2
import numpy as np
import logging
from typing import Tuple, Dict

logger = logging.getLogger(__name__)

def esta_casilla_marcada(
    celda_binaria: np.ndarray,
    umbral_densidad: float = 0.045,
    margen_borde_pct: float = 0.15
) -> Tuple[bool, float]:
    """
    Determina si una casilla (celda) contiene una marca 'X' o trazo de bolígrafo.
    
    celda_binaria: imagen binaria (0 = tinta/negro, 255 = papel/blanco)
    umbral_densidad: porcentaje mínimo de píxeles oscuros para considerar la marca activa
    margen_borde_pct: margen interno para recortar los bordes de la cuadrícula
    
    Retorna: (esta_marcada: bool, densidad_tinta: float)
    """
    h, w = celda_binaria.shape[:2]
    if h < 6 or w < 6:
        return False, 0.0
    
    # Recortar márgenes internos para ignorar las líneas de la celda
    my = max(1, int(h * margen_borde_pct))
    mx = max(1, int(w * margen_borde_pct))
    
    if (h - 2 * my) <= 2 or (w - 2 * mx) <= 2:
        interior = celda_binaria
    else:
        interior = celda_binaria[my:h-my, mx:w-mx]
    
    total_pixeles = interior.size
    if total_pixeles == 0:
        return False, 0.0
        
    # Contar píxeles negros (tinta)
    pixeles_tinta = np.sum(interior == 0)
    densidad = float(pixeles_tinta) / float(total_pixeles)
    
    # Verificación complementaria: contornos dentro del área interior
    inv_interior = cv2.bitwise_not(interior)
    contornos, _ = cv2.findContours(inv_interior, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    tiene_trazos = False
    for c in contornos:
        area_c = cv2.contourArea(c)
        if area_c > (total_pixeles * 0.02):  # Contorno con tamaño de trazo significativo
            tiene_trazos = True
            break
            
    marcada = (densidad >= umbral_densidad) and tiene_trazos
    return marcada, densidad


def clasificar_item(
    celda_no: np.ndarray,
    celda_si: np.ndarray,
    umbral_densidad: float = 0.045
) -> Dict[str, any]:
    """
    Evalúa las celdas 'No' y 'Sí' de un ítem para determinar su estado y puntuación.
    
    Estados posibles:
      - "si"    : Solo 'Sí' marcado   -> 1 punto
      - "no"    : Solo 'No' marcado   -> 0 puntos
      - "ambos" : Ambos marcados (XX) -> 1 punto (cuenta como Sí)
      - "vacio" : Sin marca detectada -> 0 puntos
    """
    no_marcado, dens_no = esta_casilla_marcada(celda_no, umbral_densidad)
    si_marcado, dens_si = esta_casilla_marcada(celda_si, umbral_densidad)
    
    if si_marcado and not no_marcado:
        estado = "si"
        puntaje = 1
    elif no_marcado and not si_marcado:
        estado = "no"
        puntaje = 0
    elif si_marcado and no_marcado:
        estado = "ambos"
        puntaje = 1
    else:
        estado = "vacio"
        puntaje = 0
        
    return {
        "opcion": estado,
        "puntaje": puntaje,
        "densidad_no": dens_no,
        "densidad_si": dens_si,
        "confianza": "alta" if estado in ("si", "no") else "revision"
    }
