"""
Sustracción de plantilla maestra para eliminar cuadrícula, texto y ruido.

Proceso:
  1. Cargar plantilla (formulario en blanco) — cacheada.
  2. Orientar plantilla al scan (rota 90° si están en orientaciones opuestas).
  3. Redimensionar scan al tamaño de la plantilla (solo por escala).
  4. Alinear con ECC subpixel; fallback a ORB + homografía.
  5. Diff robusto con BLACKHAT: extrae features oscuros locales de
     scan y plantilla, luego los compara. Ignora variaciones globales
     de brillo/contraste entre plantilla y scan.
  6. Umbralizar y limpiar.
  7. ELIMINAR líneas horizontales y verticales residuales (cuadrícula).
  8. Solo quedan marcas reales (X, ✓, ○) que son diagonales/curvas.

FIXES aplicados:
  - ESCALA_MIN / ESCALA_MAX definidos (antes lanzaban NameError silencioso,
    lo que hacía que ECC SIEMPRE fallara y el diff se calculara sobre un
    scan desalineado).
  - Rotación automática de la plantilla si scan y plantilla tienen
    orientaciones opuestas (portrait vs landscape).
  - Fallback ORB cuando ECC no converge.
  - Si ECC y ORB fallan → devolver None (NO "sin alinear"). El pipeline
    caerá a modo clásico, que es mejor que un diff basura.
  - Garantía estricta: el diff devuelto SIEMPRE tiene la misma shape
    que el scan de entrada. Si no, se descarta.
  - DIFF con BLACKHAT en vez de absdiff directo. absdiff se ensuciaba
    con cualquier diferencia de nivel de fondo entre plantilla y scan,
    produciendo densidades de 0.03+ que forzaban el modo clásico.
    BLACKHAT extrae solo features oscuros locales (tinta real) e ignora
    el nivel de fondo.
  - FASE 3.3: kernels morfológicos DINÁMICOS. Los tamaños de los
    kernels de detección de líneas y blackhat se calculan según el
    tamaño real de la imagen, en lugar de usar constantes fijas.
    Esto hace que el algoritmo funcione igual si llega una foto a
    150 DPI, un escáner a 300 DPI o un PDF renderizado a 600 DPI.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

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

# --- Alineamiento ECC ---
ECC_MOTION = cv2.MOTION_AFFINE
ECC_CRITERIA = (
    cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
    200,
    1e-5,
)
ECC_GAUSS_FILT_SIZE = 5

# Rangos de escala aceptables para la transformación ECC.
# Evita aceptar transforms absurdos (colapsos, escalados de 10x).
ESCALA_MIN = 0.85
ESCALA_MAX = 1.15

# --- Fallback ORB ---
ORB_N_FEATURES = 5000
ORB_MATCH_RATIO = 0.75     # ratio test de Lowe
ORB_MIN_MATCHES = 20       # mínimo de matches buenos para aceptar homografía
ORB_MIN_INLIERS = 15       # mínimo de inliers para aceptar la homografía

# --- Diff ---
# Umbral sobre la señal BLACKHAT. Con blackhat el rango útil es más
# estrecho que con absdiff directo, así que 50 funciona bien.
DIFF_UMBRAL = 50

# --- Kernels DINÁMICOS (FASE 3.3) ---
# Los kernels se calculan en función del tamaño real de la imagen.
# Así el algoritmo funciona igual a 150, 300 o 600 DPI.
FACTOR_KERNEL_LINEA_H = 80      # kh = ancho_imagen / 80
FACTOR_KERNEL_LINEA_V = 100     # kv = alto_imagen / 100
FACTOR_KERNEL_BLACKHAT = 80     # k_bh = min(alto, ancho) / 80

# Mínimos absolutos (para imágenes muy pequeñas)
KERNEL_LINEA_MIN = 15
KERNEL_BLACKHAT_MIN = 15

# Kernels FIJOS (no dependen del tamaño)
KERNEL_DILATAR_LINEAS = (5, 5)
KERNEL_LIMPIEZA = (2, 2)


# =============================================================================
# CÁLCULO DE KERNELS DINÁMICOS
# =============================================================================

def _calcular_kernels_dinamicos(
    h: int,
    w: int
) -> Tuple[int, int, int]:
    """
    Calcula los tamaños de los kernels morfológicos según la resolución.

    FASE 3.3: en vez de usar constantes fijas calibradas para 300 DPI,
    los kernels se escalan proporcionalmente al tamaño de la imagen.
    Eso hace al algoritmo independiente de la resolución de entrada.

    Args:
        h: alto de la imagen en píxeles.
        w: ancho de la imagen en píxeles.

    Returns:
        (kh, kv, k_bh):
          - kh: kernel horizontal para detectar líneas de tabla.
          - kv: kernel vertical para detectar líneas de tabla.
          - k_bh: kernel para BLACKHAT (extraer features oscuros locales).
    """
    kh = max(KERNEL_LINEA_MIN, int(w / FACTOR_KERNEL_LINEA_H))
    kv = max(KERNEL_LINEA_MIN, int(h / FACTOR_KERNEL_LINEA_V))
    k_bh = max(KERNEL_BLACKHAT_MIN, int(min(h, w) / FACTOR_KERNEL_BLACKHAT))

    # El kernel del blackhat DEBE ser impar para tener centro simétrico
    if k_bh % 2 == 0:
        k_bh += 1

    return kh, kv, k_bh


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

    logger.info("✓ Plantilla cargada: %dx%d (h=%d, w=%d)",
                gris.shape[1], gris.shape[0],
                gris.shape[0], gris.shape[1])
    return _PLANTILLA_CACHE


# =============================================================================
# ORIENTACIÓN DE PLANTILLA RESPECTO AL SCAN
# =============================================================================

def _orientar_plantilla_a_scan(
    plantilla_gris: np.ndarray,
    scan_shape: tuple
) -> Optional[np.ndarray]:
    """
    Ajusta la orientación de la plantilla para que coincida con la del scan.

    Casos:
      - Misma shape → devolver tal cual.
      - Shapes intercambiadas (portrait vs landscape) → rotar 90° CW.
      - Shapes incompatibles → None.

    Args:
        plantilla_gris: plantilla en gris.
        scan_shape: shape del scan (h, w) o (h, w, c).

    Returns:
        Plantilla orientada o None si no se puede compatibilizar.
    """
    h_s, w_s = scan_shape[:2]
    h_t, w_t = plantilla_gris.shape[:2]

    if (h_t, w_t) == (h_s, w_s):
        return plantilla_gris

    if (h_t, w_t) == (w_s, h_s):
        logger.warning(
            "Plantilla %dx%d y scan %dx%d con orientación opuesta. "
            "Rotando plantilla 90° CW para compatibilizar.",
            w_t, h_t, w_s, h_s,
        )
        return cv2.rotate(plantilla_gris, cv2.ROTATE_90_CLOCKWISE)

    logger.error(
        "Dimensiones incompatibles: plantilla %dx%d, scan %dx%d. "
        "No se puede alinear.",
        w_t, h_t, w_s, h_s,
    )
    return None


# =============================================================================
# ALINEAMIENTO ECC
# =============================================================================

def _alinear_ecc(
    scan_gris: np.ndarray,
    plantilla_gris: np.ndarray
) -> Optional[np.ndarray]:
    """
    Alinea el scan con la plantilla usando ECC subpixel.

    Devuelve la imagen alineada o None si ECC no converge o la
    transformación resultante es anómala.
    """
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
            ECC_GAUSS_FILT_SIZE,
        )

        escala_x = float(np.sqrt(warp_matrix[0, 0] ** 2 + warp_matrix[1, 0] ** 2))
        escala_y = float(np.sqrt(warp_matrix[0, 1] ** 2 + warp_matrix[1, 1] ** 2))

        if not (ESCALA_MIN <= escala_x <= ESCALA_MAX and
                ESCALA_MIN <= escala_y <= ESCALA_MAX):
            logger.warning(
                "Escala anómala en ECC (x=%.3f, y=%.3f). Descartando alineación.",
                escala_x, escala_y
            )
            return None

        tx = float(warp_matrix[0, 2])
        ty = float(warp_matrix[1, 2])
        logger.info(
            "ECC OK: escala=(%.3f, %.3f) traslación=(%.1f, %.1f) px",
            escala_x, escala_y, tx, ty
        )

        h_t, w_t = plantilla_gris.shape
        alineado = cv2.warpAffine(
            scan_gris,
            warp_matrix,
            (w_t, h_t),
            flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return alineado

    except cv2.error as e:
        logger.warning("ECC falló (cv2.error): %s", e)
        return None
    except Exception as e:
        logger.warning("ECC falló: %s", e)
        return None


# =============================================================================
# FALLBACK: ALINEAMIENTO CON ORB + HOMOGRAFÍA
# =============================================================================

def _alinear_orb(
    scan_gris: np.ndarray,
    plantilla_gris: np.ndarray
) -> Optional[np.ndarray]:
    """
    Fallback cuando ECC no converge. Usa ORB + BFMatcher + homografía.

    Es menos preciso que ECC subpixel, pero robusto ante desplazamientos
    grandes o rotaciones moderadas.
    """
    try:
        orb = cv2.ORB_create(nfeatures=ORB_N_FEATURES)

        kp_t, des_t = orb.detectAndCompute(plantilla_gris, None)
        kp_s, des_s = orb.detectAndCompute(scan_gris, None)

        if des_t is None or des_s is None:
            logger.warning("ORB: no se pudieron extraer descriptores.")
            return None

        if len(kp_t) < ORB_MIN_MATCHES or len(kp_s) < ORB_MIN_MATCHES:
            logger.warning(
                "ORB: muy pocos keypoints (plantilla=%d, scan=%d).",
                len(kp_t), len(kp_s)
            )
            return None

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matches = bf.knnMatch(des_t, des_s, k=2)

        # Ratio test de Lowe
        buenos = []
        for m_n in matches:
            if len(m_n) < 2:
                continue
            m, n = m_n
            if m.distance < ORB_MATCH_RATIO * n.distance:
                buenos.append(m)

        if len(buenos) < ORB_MIN_MATCHES:
            logger.warning(
                "ORB: muy pocos matches buenos (%d < %d).",
                len(buenos), ORB_MIN_MATCHES
            )
            return None

        pts_t = np.float32([kp_t[m.queryIdx].pt for m in buenos]).reshape(-1, 1, 2)
        pts_s = np.float32([kp_s[m.trainIdx].pt for m in buenos]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(pts_s, pts_t, cv2.RANSAC, 5.0)

        if H is None:
            logger.warning("ORB: findHomography devolvió None.")
            return None

        inliers = int(np.sum(mask)) if mask is not None else 0

        # Rechazar si los inliers son muy pocos (alineación dudosa)
        if inliers < ORB_MIN_INLIERS:
            logger.warning(
                "ORB: muy pocos inliers (%d < %d). Descartando.",
                inliers, ORB_MIN_INLIERS
            )
            return None

        logger.info(
            "ORB OK: %d matches, %d inliers (%.0f%%).",
            len(buenos), inliers, 100.0 * inliers / max(len(buenos), 1)
        )

        h_t, w_t = plantilla_gris.shape
        alineado = cv2.warpPerspective(
            scan_gris, H, (w_t, h_t),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return alineado

    except Exception as e:
        logger.warning("ORB falló: %s", e)
        return None


# =============================================================================
# DIFF CON BLACKHAT + ELIMINACIÓN DE LÍNEAS RESIDUALES
# =============================================================================

def _calcular_diff(
    scan_alineado: np.ndarray,
    plantilla_gris: np.ndarray,
    umbral: int = DIFF_UMBRAL
) -> np.ndarray:
    """
    Diff robusto contra variaciones globales de brillo/contraste.

    En vez de absdiff(scan, plantilla) directo (que se ensucia con
    cualquier diferencia de nivel de fondo entre plantilla y scan),
    se aplica BLACKHAT a ambas imágenes: BLACKHAT = cierre(img) - img,
    que extrae solo features oscuros locales (tinta, texto, marcas)
    ignorando el nivel de fondo.

    Luego se compara blackhat(scan) vs blackhat(plantilla).

    FASE 3.3: los kernels morfológicos se calculan dinámicamente según
    el tamaño real de la imagen. Así el algoritmo funciona igual a
    cualquier resolución (150, 300, 600 DPI).

    Args:
        scan_alineado: scan alineado a la plantilla.
        plantilla_gris: plantilla en escala de grises.
        umbral: umbral de binarización del diff de blackhats (0-255).

    Returns:
        Imagen binaria (uint8) con 255 en píxeles de tinta nueva.
    """
    h, w = scan_alineado.shape[:2]

    # FASE 3.3: kernels dinámicos según resolución real
    kh, kv, k_bh = _calcular_kernels_dinamicos(h, w)

    logger.debug(
        "Kernels dinámicos: kh=%d, kv=%d, k_bh=%d (imagen %dx%d)",
        kh, kv, k_bh, w, h
    )

    # 1. Suavizado ligero para reducir ruido de sensor/JPEG
    scan_blur = cv2.GaussianBlur(scan_alineado, (3, 3), 0)
    plant_blur = cv2.GaussianBlur(plantilla_gris, (3, 3), 0)

    # 2. Kernel para estimar el fondo local (BLACKHAT)
    kernel_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_bh, k_bh))

    # 3. BLACKHAT: extrae features oscuros locales, ignora nivel de fondo
    scan_bh = cv2.morphologyEx(scan_blur, cv2.MORPH_BLACKHAT, kernel_bg)
    plant_bh = cv2.morphologyEx(plant_blur, cv2.MORPH_BLACKHAT, kernel_bg)

    # 4. Diff de los blackhats
    diff = cv2.absdiff(scan_bh, plant_bh)

    # 5. Umbralizar
    _, diff_bin = cv2.threshold(diff, umbral, 255, cv2.THRESH_BINARY)

    # 6. Limpieza básica
    kernel_peq = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_LIMPIEZA)
    diff_limpio = cv2.morphologyEx(diff_bin, cv2.MORPH_OPEN, kernel_peq)

    # 7. Detectar líneas horizontales residuales (kernel dinámico)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (kh, 1))
    lineas_h = cv2.morphologyEx(diff_limpio, cv2.MORPH_OPEN, kernel_h)

    # 8. Detectar líneas verticales residuales (kernel dinámico)
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kv))
    lineas_v = cv2.morphologyEx(diff_limpio, cv2.MORPH_OPEN, kernel_v)

    # 9. Dilatar líneas para cubrir sus bordes
    kernel_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, KERNEL_DILATAR_LINEAS)
    lineas_h_dil = cv2.dilate(lineas_h, kernel_dil, iterations=2)
    lineas_v_dil = cv2.dilate(lineas_v, kernel_dil, iterations=2)

    # 10. Restar líneas
    solo_marcas = cv2.subtract(diff_limpio, lineas_h_dil)
    solo_marcas = cv2.subtract(solo_marcas, lineas_v_dil)

    # 11. Limpieza final
    solo_marcas = cv2.morphologyEx(solo_marcas, cv2.MORPH_OPEN, kernel_peq)

    # 12. Estadística
    total = solo_marcas.size
    pixeles = int(np.sum(solo_marcas > 0))
    densidad = pixeles / total if total > 0 else 0.0

    logger.info(
        "Diff (blackhat, kh=%d kv=%d k_bh=%d): densidad=%.5f "
        "(líneas H=%d px, V=%d px)",
        kh, kv, k_bh, densidad,
        int(np.sum(lineas_h_dil > 0)),
        int(np.sum(lineas_v_dil > 0)),
    )

    return solo_marcas


# =============================================================================
# PIPELINE COMPLETO
# =============================================================================

def obtener_imagen_diff(scan_gris: np.ndarray) -> Optional[np.ndarray]:
    """
    Pipeline completo: cargar plantilla + orientar + resize + alineación + diff.

    Orden de intentos de alineación:
      1. ECC subpixel (mejor precisión)
      2. ORB + homografía (fallback)
      3. Si ambos fallan → devolver None. NO se usa "sin alinear" porque
         un diff sobre imágenes desalineadas es peor que no tener diff.

    Garantía: el diff devuelto SIEMPRE tiene la misma shape que scan_gris.
    Si por alguna razón no la tiene, se descarta.

    Returns:
        Imagen binaria del diff (solo marcas reales) o None si falla.
    """
    plantilla = cargar_plantilla()
    if plantilla is None:
        logger.warning("Plantilla no disponible. Diff no aplicado.")
        return None

    try:
        scan_shape_original = scan_gris.shape

        # 1. Orientar plantilla al scan
        plantilla_gris = _orientar_plantilla_a_scan(
            plantilla["gris"], scan_shape_original
        )
        if plantilla_gris is None:
            logger.warning("No se pudo orientar la plantilla al scan. Diff omitido.")
            return None

        # 2. Resize si hace falta (ahora solo por escala, no por rotación)
        if scan_gris.shape != plantilla_gris.shape:
            logger.info(
                "Ajustando tamaño scan %s → %s",
                scan_gris.shape, plantilla_gris.shape,
            )
            scan_resized = cv2.resize(
                scan_gris,
                (plantilla_gris.shape[1], plantilla_gris.shape[0]),
                interpolation=cv2.INTER_AREA,
            )
        else:
            scan_resized = scan_gris

        # 3. Intento ECC
        alineado = _alinear_ecc(scan_resized, plantilla_gris)
        metodo = "ECC"

        # 4. Fallback ORB
        if alineado is None:
            logger.info("ECC no disponible. Probando fallback ORB...")
            alineado = _alinear_orb(scan_resized, plantilla_gris)
            metodo = "ORB"

        # 5. Si ambos fallan → None (mejor modo clásico que diff basura)
        if alineado is None:
            logger.warning(
                "ECC y ORB fallaron. Diff omitido (mejor modo clásico "
                "que diff basura)."
            )
            return None

        logger.info("Alineación usada: %s", metodo)

        # 6. Calcular diff
        diff = _calcular_diff(alineado, plantilla_gris)

        # 7. Garantía estricta de shape
        if diff.shape != scan_shape_original:
            logger.error(
                "Diff resultante %s != scan original %s. Diff descartado.",
                diff.shape, scan_shape_original,
            )
            return None

        return diff

    except Exception as e:
        logger.error("Error en obtener_imagen_diff: %s", e, exc_info=True)
        return None