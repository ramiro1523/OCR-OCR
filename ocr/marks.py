"""
Clasificación de marcas en celdas IEPPO.

Determina si una celda "No" y una celda "Sí" están marcadas con X,
aplicando umbrales robustos y limpieza morfológica para evitar
falsos positivos por líneas impresas o ruido.

CAMBIOS respecto a versiones anteriores:
  - stroke_ratio se calcula contando PÍXELES del componente conexo
    más grande (cv2.connectedComponentsWithStats), no área geométrica
    de contorno (cv2.contourArea).
  - FASE 3.2: antes de connectedComponents, se aplica una dilatación
    3x3 para fusionar las dos diagonales de una X cuando no se tocan
    exactamente en el centro (típico de lapiceros finos). Sin esta
    fusión, OpenCV detectaba 2 componentes separados y el ratio caía
    a ~0.5 aunque la marca fuera real.
  - NUEVA señal: simetría diagonal (calcular_simetria_diagonal). Se
    usa en pipeline.py SOLO como desempate cuando no y sí tienen el
    mismo score. Distingue X (4 cuadrantes activos) de línea o mancha
    (1-2 cuadrantes). No afecta decisiones ya tomadas.
  - Eliminada la definición duplicada de calcular_distance_transform_score.
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

# Umbral de densidad principal
UMBRAL_DENSIDAD_MARCA = 0.020

# Umbral de área del contorno más grande (relativo al área interior)
UMBRAL_AREA_CONTORNO = 0.025

# Área mínima de contorno (en píxeles) para no ser considerado ruido
AREA_MINIMA_CONTORNO_PX = 20

# Factor de desambiguación por ratio cuando ambas celdas están marcadas
FACTOR_DESAMBIGUACION = 1.5

# Diferencia absoluta mínima para desambiguar cuando el ratio no es claro
DIFERENCIA_ABSOLUTA_AMBOS = 0.005

# FASE 3.2: kernel de fusión para unir diagonales de una X que no se
# tocan exactamente. 3x3 elíptico es suficiente para cerrar huecos de
# 1-2 px sin deformar la marca.
KERNEL_FUSION_TRAZOS = (3, 3)

# Simetría diagonal: umbral mínimo de densidad en un cuadrante para
# considerarlo "activo". 0.01 = 1% de píxeles. Detecta X tenues sin
# contar ruido.
UMBRAL_CUADRANTE_SIMETRIA = 0.01


# =============================================================================
# UTILIDAD COMPARTIDA: stroke_ratio robusto
# =============================================================================

def _stroke_ratio_por_pixeles(limpio: np.ndarray) -> float:
    """
    Fracción de tinta que pertenece al componente conexo más grande,
    contando PÍXELES (no área geométrica de contorno).

    FASE 3.2: se aplica una dilatación 3x3 antes de connectedComponents
    para fusionar los dos trazos de una X que no se tocan exactamente en
    el centro (típico en lapiceros finos). Sin esta fusión, OpenCV
    detecta 2 componentes y el ratio cae a ~0.5 aunque la marca sea real.

    El denominador sigue siendo la tinta total ORIGINAL (antes de
    dilatar) para mantener la precisión, y el resultado se limita a 1.0
    porque tras dilatar el componente principal puede superar el total.

    Args:
        limpio: imagen binaria ya con padding recortado y apertura
                morfológica aplicada, tinta = píxeles > 0.

    Returns:
        float 0-1.
    """
    tinta_total = int(np.sum(limpio > 0))
    if tinta_total == 0:
        return 0.0

    # FASE 3.2: dilatación de fusión
    kernel_fusion = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, KERNEL_FUSION_TRAZOS
    )
    limpio_fusionado = cv2.dilate(limpio, kernel_fusion, iterations=1)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        limpio_fusionado, connectivity=8
    )
    if n_labels <= 1:
        return 0.0

    # stats incluye el fondo en el índice 0 → excluirlo
    areas = stats[1:, cv2.CC_STAT_AREA]
    max_componente = int(areas.max())

    # Clamp a 1.0: la dilatación puede hacer que max_componente > tinta_total
    return min(1.0, max_componente / float(tinta_total))


# =============================================================================
# UTILIDAD COMPARTIDA: simetría diagonal
# =============================================================================

def calcular_simetria_diagonal(limpio: np.ndarray) -> float:
    """
    Score 0-1 de qué tan "simétrica en diagonal" es la tinta.

    Idea: una X real dibujada en una celda toca las 4 esquinas del
    interior (arriba-izq, arriba-der, abajo-izq, abajo-der). Una
    línea diagonal toca 2. Una mancha o un bleed toca 1.

    Se divide el interior en 4 cuadrantes (2x2) y se cuenta cuántos
    tienen tinta significativa.

    Args:
        limpio: imagen binaria (tinta > 0) del interior de la celda,
                ya con padding y apertura morfológica.

    Returns:
        float 0-1:
          - 1.00 → 4 cuadrantes con tinta (X clara)
          - 0.75 → 3 cuadrantes (X ligeramente descentrada)
          - 0.50 → 2 cuadrantes (línea o V)
          - 0.25 → 1 cuadrante (mancha, punto)
          - 0.00 → sin tinta
    """
    if limpio is None or limpio.size == 0:
        return 0.0

    h, w = limpio.shape[:2]
    if h < 4 or w < 4:
        return 0.0

    cy = h // 2
    cx = w // 2

    cuadrantes = (
        limpio[:cy, :cx],   # arriba-izquierda
        limpio[:cy, cx:],   # arriba-derecha
        limpio[cy:, :cx],   # abajo-izquierda
        limpio[cy:, cx:],   # abajo-derecha
    )

    activos = 0
    for q in cuadrantes:
        if q.size == 0:
            continue
        dens = float(np.sum(q > 0)) / q.size
        if dens >= UMBRAL_CUADRANTE_SIMETRIA:
            activos += 1

    return activos / 4.0


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
      - area_max: área del contorno más grande (geométrica, cv2.contourArea)
      - dens_centro: densidad en el 60% central
      - dens_izq: densidad en el 20% izquierdo
      - dens_der: densidad en el 20% derecho
      - stroke_ratio: fracción de tinta en el componente conexo más
        grande, contado por PÍXELES. FASE 3.2: se dilata 3x3 antes de
        connectedComponents para fusionar diagonales de X que no se
        tocan exactamente. Real X ≈ 1 sin importar el grosor;
        bleed/ruido disperso < 0.5.
      - simetria_diagonal: fracción de cuadrantes con tinta.
        X real ≈ 1.0; línea ≈ 0.5; mancha ≈ 0.25.
        Se usa SOLO como desempate en _clasificar_celda cuando no y sí
        tienen el mismo score. No afecta decisiones ya tomadas.
    """
    vacio = {
        "marcada": False, "dens_total": 0.0, "area_max": 0.0,
        "dens_centro": 0.0, "dens_izq": 0.0, "dens_der": 0.0,
        "stroke_ratio": 0.0,
        "simetria_diagonal": 0.0,
    }

    if celda_binaria is None or celda_binaria.size == 0:
        return dict(vacio)

    if celda_binaria.dtype != np.uint8:
        celda_binaria = celda_binaria.astype(np.uint8)

    h, w = celda_binaria.shape[:2]
    if h < 8 or w < 12:
        return dict(vacio)

    # Padding
    pad_y = max(1, int(h * PADDING_PROPORCION))
    pad_x = max(1, int(w * PADDING_PROPORCION))
    y1, y2 = pad_y, h - pad_y
    x1, x2 = pad_x, w - pad_x

    if y2 <= y1 or x2 <= x1:
        return dict(vacio)

    interior = celda_binaria[y1:y2, x1:x2]
    if interior.size == 0:
        return dict(vacio)

    # Limpieza morfológica
    inv = cv2.bitwise_not(interior)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    limpio = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel)

    # Densidad total
    total_size = limpio.size
    tinta_total = int(np.sum(limpio > 0))
    dens_total = tinta_total / total_size if total_size > 0 else 0.0

    # Contorno máximo (se mantiene para compatibilidad / debug)
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

    # Stroke ratio robusto (por píxeles, con fusión de trazos 3x3)
    stroke_ratio = _stroke_ratio_por_pixeles(limpio)

    # NUEVA señal: simetría diagonal
    simetria_diagonal = calcular_simetria_diagonal(limpio)

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
        "simetria_diagonal": simetria_diagonal,
    }


def calcular_varianza_gris(celda_gris: np.ndarray) -> float:
    """
    Calcula la varianza de los tonos de gris dentro de la celda.

    Una celda vacía tiene varianza baja (papel uniforme).
    Una celda con marca tiene varianza alta (tinta sobre papel).

    Esta señal es robusta ante el grosor del lapicero y el contraste.

    Args:
        celda_gris: Imagen en escala de grises (uint8, 0-255).

    Returns:
        float: varianza normalizada entre 0 y 1 (más alto = más probable marca).
    """
    if celda_gris is None or celda_gris.size == 0:
        return 0.0

    h, w = celda_gris.shape[:2]
    if h < 5 or w < 5:
        return 0.0

    # Padding interno para excluir bordes impresos
    pad_y = max(1, int(h * 0.15))
    pad_x = max(1, int(w * 0.15))

    y1, y2 = pad_y, h - pad_y
    x1, x2 = pad_x, w - pad_x

    if y2 <= y1 or x2 <= x1:
        return 0.0

    interior = celda_gris[y1:y2, x1:x2]
    if interior.size == 0:
        return 0.0

    # Varianza de los tonos (float para evitar overflow)
    varianza = float(np.var(interior.astype(np.float32)))

    # Normalizar: varianza > 2000 = marca clara, < 200 = vacío
    var_norm = min(1.0, varianza / 2000.0)

    return var_norm


def calcular_distance_transform_score(celda_binaria: np.ndarray) -> float:
    """
    Calcula el distance transform score de la celda.

    Mide cuánto penetra la tinta hacia el CENTRO de la celda.
    Un bleed de borde tiene distancia baja en el centro.
    Una marca real (X, ✓) tiene distancia alta en el centro.

    Args:
        celda_binaria: Imagen binaria (fondo blanco 255, tinta negra 0).

    Returns:
        float: score normalizado 0-1.
              0 = sin tinta central (vacío o solo bleed)
              >0.3 = marca que cruza el centro
    """
    if celda_binaria is None or celda_binaria.size == 0:
        return 0.0

    if celda_binaria.dtype != np.uint8:
        celda_binaria = celda_binaria.astype(np.uint8)

    h, w = celda_binaria.shape[:2]
    if h < 8 or w < 8:
        return 0.0

    # 1. Padding interno (25% para evitar bordes impresos)
    pad_y = max(2, int(h * 0.25))
    pad_x = max(2, int(w * 0.25))
    y1, y2 = pad_y, h - pad_y
    x1, x2 = pad_x, w - pad_x

    if y2 <= y1 or x2 <= x1:
        return 0.0

    interior = celda_binaria[y1:y2, x1:x2]
    if interior.size == 0:
        return 0.0

    # 2. Invertir: tinta debe ser blanca para distanceTransform
    tinta = cv2.bitwise_not(interior)

    # 3. Limpieza morfológica
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    tinta = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, kernel)

    # 4. Distance Transform
    dist = cv2.distanceTransform(tinta, cv2.DIST_L2, 5)

    if dist.max() == 0:
        return 0.0

    # 5. Medir tinta en el centro (zona central 40%)
    h_int, w_int = dist.shape
    cy1 = int(h_int * 0.30)
    cy2 = int(h_int * 0.70)
    cx1 = int(w_int * 0.30)
    cx2 = int(w_int * 0.70)

    zona_central = dist[cy1:cy2, cx1:cx2]
    if zona_central.size == 0:
        return 0.0

    # 6. Score: máximo de distancia en el centro normalizado
    dist_max_centro = float(np.max(zona_central))
    score = min(1.0, dist_max_centro / 5.0)

    return score