"""
Sustracción de plantilla maestra para eliminar cuadrícula, texto y ruido.

Proceso:
  1. Cargar plantilla (formulario en blanco) — cacheada.
  2. Redimensionar scan al tamaño de la plantilla.
  3. Alinear con ECC (subpixel).
  4. Diff = |scan_alineado - plantilla|.
  5. Umbralizar y limpiar.
  6. ELIMINAR líneas horizontales y verticales residuales (cuadrícula).
  7. Solo quedan marcas reales (X, ✓, ○) que son diagonales/curvas.

Resultado: imagen binaria con SOLO la tinta nueva del alumno.
"""

import logging
from pathlib import Path
from typing import Optional, Dict

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CACHE GLOBAL
# =============================================================================

_PLANTILLA_CACHE: Optional[Dict[str, np.ndarray]] = None


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

RUTA_PLANTILLA_BIN = "data/plantilla_ieppo.png"
RUTA_PLANTILLA_GRIS = "data/plantilla_ieppo_gris.png"

ECC_MOTION = cv2.MOTION_AFFINE
ECC_CRITERIA = (
    cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
    100,
    1e-4,
)

DIFF_UMBRAL = 40          # Umbral de diferencia (0-255)
ESCALA_MIN = 0.85         # Escala mínima permitida en ECC
ESCALA_MAX = 1.15         # Escala máxima permitida en ECC

# Kernels para eliminar líneas residuales
KERNEL_LINEA_H = (30, 1)  # Horizontal: ancho 30, alto 1
KERNEL_LINEA_V = (1, 30)  # Vertical: ancho 1, alto 30
KERNEL_DILATAR_LINEAS = (3, 3)  # Dilatar líneas antes de restar
KERNEL_LIMPIEZA = (2, 2)  # Limpieza morfológica


# =============================================================================
# CARGA DE PLANTILLA (CON CACHÉ)
# =============================================================================

def cargar_plantilla(
    ruta_bin: str = RUTA_PLANTILLA_BIN,
    ruta_gris: str = RUTA_PLANTILLA_GRIS
) -> Optional[Dict[str, np.ndarray]]:
    """Carga la plantilla desde disco con caché."""
    global _PLANTILLA_CACHE

    if _PLANTILLA_CACHE is not None:
        return _PLANTILLA_CACHE

    ruta_gris_path = Path(ruta_gris)
    if not ruta_gris_path.exists():
        logger.warning("Plantilla gris no encontrada: %s", ruta_gris_path)
        return None

    gris = cv2.imread(str(ruta_gris_path), cv2.IMREAD_GRAYSCALE)
    if gris is None:
        logger.warning("No se pudo leer plantilla gris: %s", ruta_gris_path)
        return None

    ruta_bin_path = Path(ruta_bin)
    if ruta_bin_path.exists():
        binaria = cv2.imread(str(ruta_bin_path), cv2.IMREAD_GRAYSCALE)
        if binaria is None:
            _, binaria = cv2.threshold(
                gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
    else:
        _, binaria = cv2.threshold(
            gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

    _PLANTILLA_CACHE = {
        "binaria": binaria,
        "gris": gris,
        "shape": gris.shape,
    }

    logger.info("✓ Plantilla cargada: %dx%d", gris.shape[1], gris.shape[0])
    return _PLANTILLA_CACHE


# =============================================================================
# ALINEAMIENTO ECC
# =============================================================================

def _alinear_ecc(
    scan_gris: np.ndarray,
    plantilla_gris: np.ndarray
) -> Optional[np.ndarray]:
    """Alinea el scan con la plantilla usando ECC subpixel."""
    try:
        warp_matrix = np.eye(2, 3, dtype=np.float32)

        template_norm = plantilla_gris.astype(np.float32) / 255.0
        scan_norm = scan_gris.astype(np.float32) / 255.0

        _, warp_matrix = cv2.findTransformECC(
            template_norm,
            scan_norm,
            warp_matrix,
            ECC_MOTION,
            ECC_CRITERIA,
            None,
            5,
        )

        escala_x = float(np.sqrt(warp_matrix[0, 0] ** 2 + warp_matrix[1, 0] ** 2))
        escala_y = float(np.sqrt(warp_matrix[0, 1] ** 2 + warp_matrix[1, 1] ** 2))

        if not (ESCALA_MIN <= escala_x <= ESCALA_MAX and
                ESCALA_MIN <= escala_y <= ESCALA_MAX):
            logger.warning(
                "Escala anómala en ECC (x=%.2f, y=%.2f). Sin alinear.",
                escala_x, escala_y
            )
            return None

        h_t, w_t = plantilla_gris.shape
        alineado = cv2.warpAffine(
            scan_gris,
            warp_matrix,
            (w_t, h_t),
            flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )

        logger.info(
            "Scan alineado con ECC (escala x=%.3f, y=%.3f)",
            escala_x, escala_y
        )
        return alineado

    except cv2.error as e:
        logger.warning("ECC falló (cv2.error): %s", e)
        return None
    except Exception as e:
        logger.warning("ECC falló: %s", e)
        return None


# =============================================================================
# DIFF CON ELIMINACIÓN DE LÍNEAS RESIDUALES
# =============================================================================

def _calcular_diff(
    scan_alineado: np.ndarray,
    plantilla_gris: np.ndarray,
    umbral: int = DIFF_UMBRAL
) -> np.ndarray:
    """
    Diff absoluto + umbral + limpieza + ELIMINACIÓN DE LÍNEAS RESIDUALES.

    Las marcas reales (X, ✓, ○) son diagonales/curvas, no líneas rectas.
    Los residuos de la cuadrícula son líneas horizontales/verticales puras.
    Este filtro las elimina quirúrgicamente.
    """
    # 1. Diff absoluto
    diff = cv2.absdiff(scan_alineado, plantilla_gris)

    # 2. Umbralizar
    _, diff_bin = cv2.threshold(diff, umbral, 255, cv2.THRESH_BINARY)

    # 3. Limpieza básica
    kernel_peq = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_LIMPIEZA)
    diff_limpio = cv2.morphologyEx(diff_bin, cv2.MORPH_OPEN, kernel_peq)

    # 4. Detectar líneas horizontales largas
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, KERNEL_LINEA_H)
    lineas_h = cv2.morphologyEx(diff_limpio, cv2.MORPH_OPEN, kernel_h)

    # 5. Detectar líneas verticales largas
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, KERNEL_LINEA_V)
    lineas_v = cv2.morphologyEx(diff_limpio, cv2.MORPH_OPEN, kernel_v)

    # 6. Dilatar líneas para asegurar cobertura de bordes
    kernel_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_DILATAR_LINEAS)
    lineas_h_dil = cv2.dilate(lineas_h, kernel_dil, iterations=1)
    lineas_v_dil = cv2.dilate(lineas_v, kernel_dil, iterations=1)

    # 7. Restar las líneas del diff
    solo_marcas = cv2.subtract(diff_limpio, lineas_h_dil)
    solo_marcas = cv2.subtract(solo_marcas, lineas_v_dil)

    # 8. Limpieza final
    kernel_final = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_LIMPIEZA)
    solo_marcas = cv2.morphologyEx(solo_marcas, cv2.MORPH_OPEN, kernel_final)
    solo_marcas = cv2.morphologyEx(solo_marcas, cv2.MORPH_CLOSE, kernel_final)

    # 9. Estadística
    total = solo_marcas.size
    pixeles = int(np.sum(solo_marcas > 0))
    densidad = pixeles / total if total > 0 else 0.0

    logger.info(
        "Diff final: densidad marcas=%.4f "
        "(líneas H=%d px, líneas V=%d px eliminadas)",
        densidad,
        int(np.sum(lineas_h_dil > 0)),
        int(np.sum(lineas_v_dil > 0))
    )

    return solo_marcas


# =============================================================================
# PIPELINE COMPLETO
# =============================================================================

def obtener_imagen_diff(scan_gris: np.ndarray) -> Optional[np.ndarray]:
    """
    Pipeline completo: cargar plantilla + resize + ECC + diff + filtro líneas.

    Returns:
        Imagen binaria del diff (solo marcas reales) o None si falla.
    """
    plantilla = cargar_plantilla()
    if plantilla is None:
        logger.warning("Plantilla no disponible. Diff no aplicado.")
        return None

    try:
        h_t, w_t = plantilla["shape"]

        if scan_gris.shape != (h_t, w_t):
            scan_resized = cv2.resize(
                scan_gris, (w_t, h_t), interpolation=cv2.INTER_AREA
            )
        else:
            scan_resized = scan_gris

        alineado = _alinear_ecc(scan_resized, plantilla["gris"])

        if alineado is None:
            logger.info("ECC no disponible. Usando scan sin alinear.")
            alineado = scan_resized

        diff = _calcular_diff(alineado, plantilla["gris"])

        return diff

    except Exception as e:
        logger.error("Error en obtener_imagen_diff: %s", e, exc_info=True)
        return None