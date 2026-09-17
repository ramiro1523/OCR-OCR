"""
Clasificación de marcas en celdas IEPPO.

Determina si una celda "No" y una celda "Sí" están marcadas con X,
aplicando umbrales robustos y limpieza morfológica para evitar
falsos positivos por líneas impresas o ruido.
"""

import logging
from typing import Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Padding interno para excluir bordes impresos
PADDING_PROPORCION = 0.10

# Umbral de densidad principal (bajado de 0.022 a 0.020)
UMBRAL_DENSIDAD_MARCA = 0.020

# Umbral de área del contorno más grande (relativo al área interior)
UMBRAL_AREA_CONTORNO = 0.025

# Área mínima de contorno (en píxeles) para no ser considerado ruido
AREA_MINIMA_CONTORNO_PX = 20

# Factor de desambiguación por ratio cuando ambas celdas están marcadas
FACTOR_DESAMBIGUACION = 1.5

# Diferencia absoluta mínima para desambiguar cuando el ratio no es claro
DIFERENCIA_ABSOLUTA_AMBOS = 0.005


# =============================================================================
# FUNCIONES PÚBLICAS
# =============================================================================

def analizar_trazo_celda(celda_binaria: np.ndarray) -> Tuple[bool, float, float]:
    """
    Analiza una celda individual y determina si está marcada.

    Pipeline:
      1. Recortar bordes impresos (padding interno del 10%).
      2. Limpiar con apertura morfológica (elimina líneas finas y ruido).
      3. Calcular densidad de píxeles oscuros.
      4. Analizar contornos (componentes conectados).
      5. Decidir si está marcada con doble criterio.

    Args:
        celda_binaria: Imagen binaria (fondo blanco 255, tinta negra 0).

    Returns:
        (esta_marcada: bool, densidad: float, area_contorno_max: float)
    """
    if celda_binaria is None or celda_binaria.size == 0:
        return False, 0.0, 0.0

    if celda_binaria.dtype != np.uint8:
        celda_binaria = celda_binaria.astype(np.uint8)

    h, w = celda_binaria.shape[:2]
    if h < 8 or w < 8:
        return False, 0.0, 0.0

    # -------------------------------------------------------------------------
    # 1. Recorte de bordes
    # -------------------------------------------------------------------------
    pad_y = max(1, int(h * PADDING_PROPORCION))
    pad_x = max(1, int(w * PADDING_PROPORCION))

    y1 = pad_y
    y2 = h - pad_y
    x1 = pad_x
    x2 = w - pad_x

    if y2 <= y1 or x2 <= x1:
        return False, 0.0, 0.0

    interior = celda_binaria[y1:y2, x1:x2]

    if interior.size == 0:
        return False, 0.0, 0.0

    # -------------------------------------------------------------------------
    # 2. Limpieza morfológica
    # -------------------------------------------------------------------------
    interior_inv = cv2.bitwise_not(interior)

    kernel_limpieza = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    interior_limpio = cv2.morphologyEx(
        interior_inv, cv2.MORPH_OPEN, kernel_limpieza
    )

    # -------------------------------------------------------------------------
    # 3. Densidad de píxeles de tinta
    # -------------------------------------------------------------------------
    total_pixeles = interior_limpio.size
    pixeles_tinta = int(np.sum(interior_limpio > 0))

    if total_pixeles > 0:
        densidad = float(pixeles_tinta) / float(total_pixeles)
    else:
        densidad = 0.0

    # -------------------------------------------------------------------------
    # 4. Análisis de contornos
    # -------------------------------------------------------------------------
    contornos, _ = cv2.findContours(
        interior_limpio, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    max_area = 0.0
    for c in contornos:
        area = cv2.contourArea(c)
        if area > max_area:
            max_area = area

    # -------------------------------------------------------------------------
    # 5. Decisión con doble criterio
    # -------------------------------------------------------------------------
    area_umbral = total_pixeles * UMBRAL_AREA_CONTORNO

    cumple_densidad = densidad >= UMBRAL_DENSIDAD_MARCA
    cumple_contorno = (
        max_area >= area_umbral and max_area >= AREA_MINIMA_CONTORNO_PX
    )

    marcada = cumple_densidad or cumple_contorno

    return marcada, densidad, max_area


def clasificar_item(
    celda_no: np.ndarray,
    celda_si: np.ndarray
) -> Dict[str, Any]:
    """
    Clasifica el estado de un ítem según las reglas IEPPO.

    Args:
        celda_no: Región de la celda "No".
        celda_si: Región de la celda "Sí".

    Returns:
        Dict con:
          - opcion: "si" | "no" | "ambos" | "vacio"
          - puntaje: 1 si puntúa, 0 si no
          - densidad_no: float
          - densidad_si: float
          - confianza: "alta" | "media" | "baja"
    """
    no_marcado, dens_no, area_no = analizar_trazo_celda(celda_no)
    si_marcado, dens_si, area_si = analizar_trazo_celda(celda_si)

    # -------------------------------------------------------------------------
    # Caso 1: solo uno de los dos está marcado (caso ideal)
    # -------------------------------------------------------------------------
    if si_marcado and not no_marcado:
        return {
            "opcion": "si",
            "puntaje": 1,
            "densidad_no": round(dens_no, 4),
            "densidad_si": round(dens_si, 4),
            "confianza": "alta"
        }

    if no_marcado and not si_marcado:
        return {
            "opcion": "no",
            "puntaje": 0,
            "densidad_no": round(dens_no, 4),
            "densidad_si": round(dens_si, 4),
            "confianza": "alta"
        }

    # -------------------------------------------------------------------------
    # Caso 2: ambos marcados → desambiguar
    # -------------------------------------------------------------------------
    if si_marcado and no_marcado:

        # Desambiguación 1: ratio significativo
        if dens_si > (dens_no * FACTOR_DESAMBIGUACION):
            return {
                "opcion": "si",
                "puntaje": 1,
                "densidad_no": round(dens_no, 4),
                "densidad_si": round(dens_si, 4),
                "confianza": "media"
            }

        if dens_no > (dens_si * FACTOR_DESAMBIGUACION):
            return {
                "opcion": "no",
                "puntaje": 0,
                "densidad_no": round(dens_no, 4),
                "densidad_si": round(dens_si, 4),
                "confianza": "media"
            }

        # Desambiguación 2: diferencia absoluta significativa
        # Esto captura los casos donde ambas densidades son similares
        # pero una es claramente mayor (ej. H24, H28)
        diff = abs(dens_si - dens_no)
        if diff >= DIFERENCIA_ABSOLUTA_AMBOS:
            if dens_si > dens_no:
                return {
                    "opcion": "si",
                    "puntaje": 1,
                    "densidad_no": round(dens_no, 4),
                    "densidad_si": round(dens_si, 4),
                    "confianza": "media"
                }
            else:
                return {
                    "opcion": "no",
                    "puntaje": 0,
                    "densidad_no": round(dens_no, 4),
                    "densidad_si": round(dens_si, 4),
                    "confianza": "media"
                }

        # Doble marca real (densidades muy similares)
        return {
            "opcion": "ambos",
            "puntaje": 1,
            "densidad_no": round(dens_no, 4),
            "densidad_si": round(dens_si, 4),
            "confianza": "baja"
        }

    # -------------------------------------------------------------------------
    # Caso 3: ninguno marcado
    # -------------------------------------------------------------------------
    return {
        "opcion": "vacio",
        "puntaje": 0,
        "densidad_no": round(dens_no, 4),
        "densidad_si": round(dens_si, 4),
        "confianza": "alta"
    }
def analizar_trazo_celda_extendido(
    celda_binaria: np.ndarray
) -> Tuple[bool, float, float, float, float]:
    """
    Analiza una celda con perfil horizontal (mitad izquierda vs mitad derecha).

    Devuelve:
        (marcada, densidad_total, area_max, densidad_izq, densidad_der)

    Donde densidad_izq y densidad_der se calculan sobre la mitad
    izquierda y derecha del interior de la celda, respectivamente.

    Esto permite detectar BLEED: si la densidad está concentrada
    cerca del borde, probablemente es tinta de la celda vecina.
    """
    if celda_binaria is None or celda_binaria.size == 0:
        return False, 0.0, 0.0, 0.0, 0.0

    if celda_binaria.dtype != np.uint8:
        celda_binaria = celda_binaria.astype(np.uint8)

    h, w = celda_binaria.shape[:2]
    if h < 8 or w < 12:
        return False, 0.0, 0.0, 0.0, 0.0

    # Recorte de bordes (igual que analizar_trazo_celda)
    pad_y = max(1, int(h * PADDING_PROPORCION))
    pad_x = max(1, int(w * PADDING_PROPORCION))

    y1, y2 = pad_y, h - pad_y
    x1, x2 = pad_x, w - pad_x

    if y2 <= y1 or x2 <= x1:
        return False, 0.0, 0.0, 0.0, 0.0

    interior = celda_binaria[y1:y2, x1:x2]
    if interior.size == 0:
        return False, 0.0, 0.0, 0.0, 0.0

    # Limpieza morfológica
    interior_inv = cv2.bitwise_not(interior)
    kernel_limpieza = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    interior_limpio = cv2.morphologyEx(interior_inv, cv2.MORPH_OPEN, kernel_limpieza)

    # Densidad total
    total = interior_limpio.size
    tinta_total = int(np.sum(interior_limpio > 0))
    densidad = float(tinta_total) / float(total) if total > 0 else 0.0

    # Densidad por mitades
    h_int, w_int = interior_limpio.shape
    mitad_x = w_int // 2

    mitad_izq = interior_limpio[:, :mitad_x]
    mitad_der = interior_limpio[:, mitad_x:]

    dens_izq = (float(np.sum(mitad_izq > 0)) / mitad_izq.size
                if mitad_izq.size > 0 else 0.0)
    dens_der = (float(np.sum(mitad_der > 0)) / mitad_der.size
                if mitad_der.size > 0 else 0.0)

    # Contorno máximo
    contornos, _ = cv2.findContours(
        interior_limpio, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    max_area = 0.0
    for c in contornos:
        area = cv2.contourArea(c)
        if area > max_area:
            max_area = area

    # Decisión de marca (misma que analizar_trazo_celda)
    area_umbral = total * UMBRAL_AREA_CONTORNO
    cumple_densidad = densidad >= UMBRAL_DENSIDAD_MARCA
    cumple_contorno = (
        max_area >= area_umbral and max_area >= AREA_MINIMA_CONTORNO_PX
    )
    marcada = cumple_densidad or cumple_contorno

    return marcada, densidad, max_area, dens_izq, dens_der


def analizar_trazo_celda_multisenal(celda_binaria: np.ndarray) -> Dict[str, float]:
    """
    Análisis multi-señal de una celda.

    Retorna un dict con:
      - marcada: bool (por densidad total)
      - dens_total: densidad global
      - area_max: área del contorno más grande
      - dens_centro: densidad en el 60% central
      - dens_izq: densidad en el 20% izquierdo
      - dens_der: densidad en el 20% derecho
      - stroke_ratio: max_area / (dens_total * total_area) — real X ≈ 1, bleed < 0.5
    """
    if celda_binaria is None or celda_binaria.size == 0:
        return {
            "marcada": False, "dens_total": 0.0, "area_max": 0.0,
            "dens_centro": 0.0, "dens_izq": 0.0, "dens_der": 0.0,
            "stroke_ratio": 0.0,
        }

    if celda_binaria.dtype != np.uint8:
        celda_binaria = celda_binaria.astype(np.uint8)

    h, w = celda_binaria.shape[:2]
    if h < 8 or w < 12:
        return {
            "marcada": False, "dens_total": 0.0, "area_max": 0.0,
            "dens_centro": 0.0, "dens_izq": 0.0, "dens_der": 0.0,
            "stroke_ratio": 0.0,
        }

    # Padding
    pad_y = max(1, int(h * PADDING_PROPORCION))
    pad_x = max(1, int(w * PADDING_PROPORCION))
    y1, y2 = pad_y, h - pad_y
    x1, x2 = pad_x, w - pad_x

    if y2 <= y1 or x2 <= x1:
        return {
            "marcada": False, "dens_total": 0.0, "area_max": 0.0,
            "dens_centro": 0.0, "dens_izq": 0.0, "dens_der": 0.0,
            "stroke_ratio": 0.0,
        }

    interior = celda_binaria[y1:y2, x1:x2]
    if interior.size == 0:
        return {
            "marcada": False, "dens_total": 0.0, "area_max": 0.0,
            "dens_centro": 0.0, "dens_izq": 0.0, "dens_der": 0.0,
            "stroke_ratio": 0.0,
        }

    # Limpieza morfológica
    inv = cv2.bitwise_not(interior)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    limpio = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel)

    # Densidad total
    total_size = limpio.size
    tinta_total = int(np.sum(limpio > 0))
    dens_total = tinta_total / total_size if total_size > 0 else 0.0

    # Contorno máximo
    contornos, _ = cv2.findContours(
        limpio, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    max_area = 0.0
    for c in contornos:
        a = cv2.contourArea(c)
        if a > max_area:
            max_area = a

    # Densidad central (60% central)
    h_int, w_int = limpio.shape
    cy1, cy2 = int(h_int * 0.20), int(h_int * 0.80)
    cx1, cx2 = int(w_int * 0.20), int(w_int * 0.80)
    centro = limpio[cy1:cy2, cx1:cx2]
    dens_centro = (np.sum(centro > 0) / centro.size) if centro.size > 0 else 0.0

    # Densidad bordes (20% izquierdo y derecho)
    borde_izq = limpio[:, :max(1, w_int // 5)]
    borde_der = limpio[:, min(w_int - 1, 4 * w_int // 5):]
    dens_izq = (np.sum(borde_izq > 0) / borde_izq.size) if borde_izq.size > 0 else 0.0
    dens_der = (np.sum(borde_der > 0) / borde_der.size) if borde_der.size > 0 else 0.0

    # Stroke ratio: qué fracción de la tinta está en un solo trazo conectado
    stroke_ratio = max_area / tinta_total if tinta_total > 0 else 0.0

    # Decisión de marcada (por densidad total)
    marcada = dens_total >= UMBRAL_DENSIDAD_MARCA

    return {
        "marcada": marcada,
        "dens_total": dens_total,
        "area_max": max_area,
        "dens_centro": dens_centro,
        "dens_izq": dens_izq,
        "dens_der": dens_der,
        "stroke_ratio": stroke_ratio,
    }