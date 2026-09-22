"""
Pipeline OCR Principal para formularios IEPPO.

Mejoras de robustez:
  - Sustracción de plantilla con filtro de líneas residuales.
  - Análisis por bloque con umbral adaptativo.
  - Detección de columnas invertidas por bloque.
  - Flag "revisar" para casos anómalos.
  - Guardado de imágenes debug de items marcados.
  - NO aplica swaps automáticos (honesto: solo marca para revisión).

FIXES aplicados:
  - _analizar_bloque ya no declara "vacio" cuando la mayoría de las
    densidades son 0 pero algunas son altas. Se mira max_d y si hay
    algún ítem claramente marcado, el bloque NO es vacío. Esto evita
    tirar bloques enteros (P, H) cuando los percentiles colapsan a 0.
  - Detección de cuadrícula residual usa min(no, si) por ítem, no
    max (con max disparaba siempre en formularios completos).
  - Si el diff tiene shape distinta a la binaria, se DESCARTA en vez
    de reescalarlo (reescalar corrompía el análisis).
  - Añadido check de densidad máxima del diff: si es demasiado alta,
    el diff no está funcionando y se cae a modo clásico.
  - FASE 1: la carga de archivos pasa por ocr.entrada.cargar_formulario,
    que acepta PDF, JPG, JPEG, PNG, BMP, TIFF y WEBP. Se detecta el
    tipo por extensión o por magic bytes. Devuelve siempre una lista
    de imágenes en escala de grises.
  - MEJORA anti-artefactos: en _clasificar_celda se detecta cuando
    una celda tiene dens_centro excesivo (> 0.22). Una X real ocupa
    0.03-0.15 del centro; más de 0.22 solo puede ser mancha, garabato
    o sombra. Al detectarlo, se anulan TODAS las señales de esa celda
    (dens_total, dens_centro, stroke_ratio, dist_transform) para que
    no vote. La otra celda, si tiene marca real, gana sola.
  - MEJORA simetría diagonal: en _clasificar_celda se usa
    simetria_diagonal (calculada en marks.py) como desempate cuando
    no y sí tienen EXACTAMENTE el mismo score. Una X tiene simetría
    ~1.0; una línea ~0.5; una mancha ~0.25. Nunca cambia decisiones
    ya tomadas, solo desempata casos perfectamente empatados.
"""

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Union, Dict, Any, List

import cv2
import numpy as np
import pytesseract

from ocr.entrada import cargar_formulario
from ocr.preprocess import preprocesar_imagen, binarizar
from ocr.tables import detectar_3_tablas_geometria
from ocr.rows import obtener_filas_y_columnas_tabla
from ocr.marks import (
    analizar_trazo_celda_multisenal,
    calcular_varianza_gris,
    calcular_distance_transform_score,
)
from vocacional.utils import generar_items_vacios, auditar_marcas
from ocr.template import obtener_imagen_diff

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES
# =============================================================================

DPI_PROCESAMIENTO = 300
TOTAL_ITEMS_ESPERADOS = 118
PORCENTAJE_EXITO_TOTAL = 1.00
PORCENTAJE_EXITO_PARCIAL = 0.93
TIMEOUT_SEGUNDOS = 60
UMBRAL_NITIDEZ_MINIMA = 100
TAMANO_MAXIMO_OSD = 2000
CONFIANZA_MINIMA_OSD = 5.0

# Detección de bloque VACÍO
P75_VACIO = 0.020
P50_VACIO = 0.010
P25_MARCADO = 0.040

# Clamp del umbral
UMBRAL_MIN = 0.005
UMBRAL_MAX = 0.020

# Clasificación multi-señal
MARCA_DENS_FACTOR = 1.0
MARCA_CENTRO_FACTOR = 0.25
MARCA_STROKE_MIN = 0.10

UMBRAL_RESCATE_DENS = 0.025
UMBRAL_RESCATE_STROKE = 0.15

RATIO_DESAMBIGUACION = 1.25

# Rango de densidad del diff a nivel imagen completa
DENSIDAD_MINIMA_DIFF = 0.001
DENSIDAD_MAXIMA_DIFF = 0.030

# Detección de cuadrícula residual (a nivel bloque)
UMBRAL_MEDIANA_RESIDUAL = 0.05

# Detección de outliers
DENSIDAD_ALTA = 0.060
DENSIDAD_MUY_BAJA = 0.005
RATIO_OUTLIER = 4.0
VENTANA_VECINOS = 2

# Detección de artefactos (manchas, garabatos, sombras)
# Una X real tiene dens_centro entre 0.03 y 0.15. Más de 0.22 solo
# puede ser un artefacto. Cuando se detecta, se anula la señal de
# esa celda para que no vote en _clasificar_celda.
UMBRAL_ARTEFACTO_CENTRO = 0.22

# Guardar imágenes de debug de items marcados
GUARDAR_DEBUG_ITEMS = True
RUTA_DEBUG_ITEMS = "debug_items"


# =============================================================================
# UTILIDADES
# =============================================================================

def _respuesta_error(marcas, detalles, mensaje, paginas=0, total_procesados=0):
    return {
        "exito": False, "marcas": marcas, "detalles": detalles,
        "mensaje": mensaje, "audit": auditar_marcas(marcas),
        "paginas": paginas, "total_procesados": total_procesados,
    }


def _verificar_orientacion_pdf(imagen_np: np.ndarray) -> np.ndarray:
    try:
        h, w = imagen_np.shape[:2]
        if max(h, w) > TAMANO_MAXIMO_OSD:
            escala = TAMANO_MAXIMO_OSD / max(h, w)
            imagen_peq = cv2.resize(imagen_np, None, fx=escala, fy=escala,
                                     interpolation=cv2.INTER_AREA)
        else:
            imagen_peq = imagen_np

        if len(imagen_peq.shape) == 3:
            gris_peq = cv2.cvtColor(imagen_peq, cv2.COLOR_BGR2GRAY)
        else:
            gris_peq = imagen_peq

        _, binaria_peq = cv2.threshold(
            gris_peq, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        osd = pytesseract.image_to_osd(
            binaria_peq, output_type=pytesseract.Output.DICT
        )
        rotacion = osd.get("rotate", 0)
        confianza = float(osd.get("orientation_conf", 0))

        if confianza < CONFIANZA_MINIMA_OSD:
            return imagen_np

        if rotacion == 90:
            return cv2.rotate(imagen_np, cv2.ROTATE_90_CLOCKWISE)
        elif rotacion == 180:
            return cv2.rotate(imagen_np, cv2.ROTATE_180)
        elif rotacion == 270:
            return cv2.rotate(imagen_np, cv2.ROTATE_90_COUNTERCLOCKWISE)
    except Exception as e:
        logger.warning("OSD falló (%s).", type(e).__name__)
    return imagen_np


def _validar_binarizacion(binaria, gris):
    pixeles_tinta = int(np.sum(binaria == 0))
    densidad = pixeles_tinta / binaria.size
    nitidez = float(cv2.Laplacian(gris, cv2.CV_64F).var())

    if densidad < 0.005:
        return False, f"densidad muy baja ({densidad:.3f})"
    if densidad > 0.70:
        return False, f"densidad muy alta ({densidad:.3f})"
    if nitidez < UMBRAL_NITIDEZ_MINIMA:
        return False, f"borrosa ({nitidez:.1f})"
    return True, "OK"


def _validar_estructura_tablas(tablas):
    if len(tablas) < 3:
        return False, f"solo {len(tablas)}/3 tablas"
    for i, t in enumerate(tablas):
        if not isinstance(t, dict) or "x" not in t or "roi_binaria" not in t:
            return False, f"tabla {i} estructura inválida"
        if t["roi_binaria"] is None or t["roi_binaria"].size == 0:
            return False, f"tabla {i} ROI vacía"
    return True, "OK"


# =============================================================================
# ANÁLISIS POR BLOQUE
# =============================================================================

def _analizar_bloque(celdas_bloque, prefijo):
    """
    Analiza las densidades de un bloque para decidir su régimen.

    FIX: antes se declaraba "vacio" si p75 < 0.020 y p50 < 0.010.
    Eso fallaba cuando la mayoría de celdas tenían densidad 0
    (por ejemplo, filas mal recortadas que caen en zona blanca) pero
    unos pocos ítems sí tenían marca real. Con percentiles dominados
    por ceros, el bloque entero se tiraba como "vacio".

    Ahora se mira max_d: si ALGÚN ítem tiene densidad clara, el bloque
    NO está vacío aunque p25/p50/p75 sean 0.
    """
    if not celdas_bloque:
        return {"tipo": "vacio", "umbral": 0.0, "p25": 0, "p50": 0, "p75": 0}

    densidades = [
        max(c["no"]["dens_total"], c["si"]["dens_total"])
        for c in celdas_bloque.values()
    ]

    if len(densidades) < 5:
        return {"tipo": "vacio", "umbral": 0.0, "p25": 0, "p50": 0, "p75": 0}

    p25 = float(np.percentile(densidades, 25))
    p50 = float(np.percentile(densidades, 50))
    p75 = float(np.percentile(densidades, 75))
    max_d = float(np.max(densidades))

    logger.info(
        "Bloque %s: p25=%.4f, p50=%.4f, p75=%.4f, max=%.4f (n=%d)",
        prefijo, p25, p50, p75, max_d, len(densidades)
    )

    # FIX: si el máximo no llega ni al umbral bajo, el bloque SÍ está vacío.
    if max_d < P75_VACIO:
        logger.info("Bloque %s: VACÍO (max=%.4f < %.4f)", prefijo, max_d, P75_VACIO)
        return {"tipo": "vacio", "umbral": 0.0, "p25": p25, "p50": p50, "p75": p75}

    # Bloque claramente marcado: p25 por encima del umbral de marca clara.
    if p25 > P25_MARCADO:
        umbral = max(UMBRAL_MIN, min(UMBRAL_MAX, p25 * 0.4))
        logger.info("Bloque %s: MARCADO (umbral=%.4f)", prefijo, umbral)
        return {"tipo": "marcado", "umbral": umbral, "p25": p25, "p50": p50, "p75": p75}

    # Bloque mixto con percentiles colapsados a 0 (mayoría de celdas sin
    # densidad, unos pocos ítems con densidad clara). Usar umbral bajo fijo.
    if p75 < P75_VACIO:
        umbral = UMBRAL_MIN
        logger.info(
            "Bloque %s: MIXTO-CON-CEROS (umbral=%.4f, max=%.4f)",
            prefijo, umbral, max_d
        )
        return {"tipo": "mixto", "umbral": umbral, "p25": p25, "p50": p50, "p75": p75}

    # Bloque mixto normal.
    umbral = (p25 + p75) / 2
    umbral = max(UMBRAL_MIN, min(UMBRAL_MAX, umbral))
    logger.info("Bloque %s: MIXTO (umbral=%.4f)", prefijo, umbral)
    return {"tipo": "mixto", "umbral": umbral, "p25": p25, "p50": p50, "p75": p75}


# =============================================================================
# CLASIFICACIÓN
# =============================================================================

def _es_marca_real(sig, umbral, densidades_bloque=None):
    dens_total = sig["dens_total"]
    dens_centro = sig["dens_centro"]
    sr = sig["stroke_ratio"]

    if dens_total >= umbral:
        if dens_centro < umbral * MARCA_CENTRO_FACTOR:
            return False
        if sr < MARCA_STROKE_MIN:
            return False
        return True

    if densidades_bloque is not None and len(densidades_bloque) > 0:
        mediana = float(np.median(densidades_bloque))
        if mediana > 0.001 and dens_total > mediana * 2.5:
            if dens_centro > 0.005 or sr > 0.25:
                return True

    if dens_total > UMBRAL_RESCATE_DENS and sr > UMBRAL_RESCATE_STROKE:
        return True

    return False


def _clasificar_celda(s_no, s_si, umbral, densidades_bloque=None):
    """
    Clasificación con VOTACIÓN PONDERADA.

    MEJORA anti-artefactos: se detecta cuando una celda tiene
    dens_centro excesivo (> UMBRAL_ARTEFACTO_CENTRO = 0.22). Una X
    real ocupa 0.03-0.15 del centro; más de 0.22 solo puede ser una
    mancha, garabato o sombra. Al detectarlo, se anulan TODAS las
    señales de esa celda (dens_total, dens_centro, stroke_ratio,
    dist_transform) para que no vote. La otra celda, si tiene marca
    real, gana sola.

    MEJORA simetría diagonal: cuando no y sí tienen EXACTAMENTE el
    mismo score, se usa simetria_diagonal como desempate final.
    Una X toca los 4 cuadrantes (~1.0); una línea toca 2 (~0.5);
    una mancha toca 1 (~0.25). Solo se activa si el score está
    perfectamente empatado, así que no cambia decisiones ya tomadas.

    Pesos de la votación (suman 10):
      - Densidad total: 2 (ruidosa)
      - Densidad centro: 4 (más fiable)
      - Stroke ratio: 2
      - Distance transform: 2
    """
    dens_no = s_no["dens_total"]
    dens_si = s_si["dens_total"]
    centro_no = s_no.get("dens_centro", 0.0)
    centro_si = s_si.get("dens_centro", 0.0)
    sr_no = s_no.get("stroke_ratio", 0.0)
    sr_si = s_si.get("stroke_ratio", 0.0)
    dt_no = s_no.get("dist_transform", 0.0)
    dt_si = s_si.get("dist_transform", 0.0)

    # Simetría diagonal (desempate, no decide por sí sola)
    simetria_no = s_no.get("simetria_diagonal", 0.0)
    simetria_si = s_si.get("simetria_diagonal", 0.0)

    # --- MEJORA: neutralizar artefactos ---
    if centro_no > UMBRAL_ARTEFACTO_CENTRO:
        logger.debug(
            "Artefacto en 'no' (centro=%.4f > %.2f). Señal anulada.",
            centro_no, UMBRAL_ARTEFACTO_CENTRO
        )
        dens_no = 0.0
        centro_no = 0.0
        sr_no = 0.0
        dt_no = 0.0

    if centro_si > UMBRAL_ARTEFACTO_CENTRO:
        logger.debug(
            "Artefacto en 'si' (centro=%.4f > %.2f). Señal anulada.",
            centro_si, UMBRAL_ARTEFACTO_CENTRO
        )
        dens_si = 0.0
        centro_si = 0.0
        sr_si = 0.0
        dt_si = 0.0

    # Pesos (suman 10)
    PESO_DENSIDAD = 2
    PESO_CENTRO = 4
    PESO_STROKE = 2
    PESO_DT = 2

    umbral_centro = umbral * MARCA_CENTRO_FACTOR
    umbral_dt = 0.25

    # Señales por celda
    m_dens_no = 1 if dens_no >= umbral else 0
    m_dens_si = 1 if dens_si >= umbral else 0

    m_centro_no = 1 if centro_no >= umbral_centro else 0
    m_centro_si = 1 if centro_si >= umbral_centro else 0

    m_sr_no = 1 if (sr_no >= MARCA_STROKE_MIN and dens_no > umbral * 0.5) else 0
    m_sr_si = 1 if (sr_si >= MARCA_STROKE_MIN and dens_si > umbral * 0.5) else 0

    m_dt_no = 1 if dt_no >= umbral_dt else 0
    m_dt_si = 1 if dt_si >= umbral_dt else 0

    # Score ponderado
    score_no = (PESO_DENSIDAD * m_dens_no +
                PESO_CENTRO * m_centro_no +
                PESO_STROKE * m_sr_no +
                PESO_DT * m_dt_no)

    score_si = (PESO_DENSIDAD * m_dens_si +
                PESO_CENTRO * m_centro_si +
                PESO_STROKE * m_sr_si +
                PESO_DT * m_dt_si)

    # 1. Ambos con score bajo → vacío
    if score_no < 3 and score_si < 3:
        return {"opcion": "vacio", "puntaje": 0, "confianza": "alta"}

    # 2. Diferencia clara
    diff = abs(score_no - score_si)
    if diff >= 3:
        ganador = "si" if score_si > score_no else "no"
        confianza = "alta" if diff >= 5 else "media"
        return {"opcion": ganador,
                "puntaje": 1 if ganador == "si" else 0,
                "confianza": confianza}

    # 3. Diferencia moderada → densidad total como desempate
    if diff > 0:
        if dens_si > dens_no:
            return {"opcion": "si", "puntaje": 1, "confianza": "media"}
        elif dens_no > dens_si:
            return {"opcion": "no", "puntaje": 0, "confianza": "media"}

    # 4. Empate de score → desempatar por densidad central
    if abs(centro_si - centro_no) > 0.003:
        if centro_si > centro_no:
            return {"opcion": "si", "puntaje": 1, "confianza": "media"}
        else:
            return {"opcion": "no", "puntaje": 0, "confianza": "media"}

    # 4.5. Desempate por simetría diagonal (solo si score empatado)
    # Este bloque NUNCA se ejecuta si el score ya decidió algo.
    # Solo interviene cuando diff == 0 y la densidad central también empató.
    if simetria_no != simetria_si:
        if simetria_si > simetria_no and simetria_si >= 0.5:
            return {"opcion": "si", "puntaje": 1, "confianza": "media"}
        if simetria_no > simetria_si and simetria_no >= 0.5:
            return {"opcion": "no", "puntaje": 0, "confianza": "media"}

    # 5. Empate real
    if score_no >= 5 and score_si >= 5:
        return {"opcion": "ambos", "puntaje": 1, "confianza": "baja",
                "revisar": True, "motivo": "empate de score con ambos altos"}

    return {"opcion": "vacio", "puntaje": 0, "confianza": "baja",
            "revisar": True, "motivo": "empate de score con ambos bajos"}


# =============================================================================
# DETECCIÓN DE OUTLIERS Y ANOMALÍAS
# =============================================================================

def _detectar_outliers_bloque(celdas_bloque, prefijo, densidades_bloque):
    items_revisar = set()

    if not densidades_bloque or len(densidades_bloque) < 5:
        return items_revisar

    items_ordenados = sorted(
        celdas_bloque.keys(),
        key=lambda k: int(k[len(prefijo):]) if k[len(prefijo):].isdigit() else 0
    )

    # 1. Densidad alta pero stroke bajo
    for item_key, d in celdas_bloque.items():
        no = d["no"]
        si = d["si"]

        dens_max = max(no["dens_total"], si["dens_total"])
        sr_min = min(no["stroke_ratio"], si["stroke_ratio"])

        if dens_max > DENSIDAD_ALTA and sr_min < 0.12:
            items_revisar.add(item_key)

    # 2. Ventana deslizante
    for idx, item_key in enumerate(items_ordenados):
        vecinos = []
        for v in range(-VENTANA_VECINOS, VENTANA_VECINOS + 1):
            if v == 0:
                continue
            v_idx = idx + v
            if 0 <= v_idx < len(items_ordenados):
                v_key = items_ordenados[v_idx]
                if v_key in celdas_bloque:
                    vd = celdas_bloque[v_key]
                    vecinos.append(max(vd["no"]["dens_total"],
                                        vd["si"]["dens_total"]))

        if not vecinos:
            continue

        mediana_vecinos = float(np.median(vecinos))
        dens_actual = max(
            celdas_bloque[item_key]["no"]["dens_total"],
            celdas_bloque[item_key]["si"]["dens_total"]
        )

        if mediana_vecinos > 0.001 and dens_actual > mediana_vecinos * RATIO_OUTLIER:
            items_revisar.add(item_key)

    # 3. Inversión de columna
    suma_no_bloque = sum(c["no"]["dens_total"] for c in celdas_bloque.values())
    suma_si_bloque = sum(c["si"]["dens_total"] for c in celdas_bloque.values())

    if suma_no_bloque > suma_si_bloque * 3 and suma_no_bloque > 0.5:
        for item_key, d in celdas_bloque.items():
            if d["si"]["dens_total"] > DENSIDAD_ALTA and d["no"]["dens_total"] < DENSIDAD_MUY_BAJA:
                items_revisar.add(item_key)

    if suma_si_bloque > suma_no_bloque * 3 and suma_si_bloque > 0.5:
        for item_key, d in celdas_bloque.items():
            if d["no"]["dens_total"] > DENSIDAD_ALTA and d["si"]["dens_total"] < DENSIDAD_MUY_BAJA:
                items_revisar.add(item_key)

    return items_revisar


def _validar_coherencia_bloque(celdas_bloque, prefijo):
    if not celdas_bloque:
        return set()

    items_revisar = set()

    items_ordenados = sorted(
        celdas_bloque.keys(),
        key=lambda k: int(k[len(prefijo):]) if k[len(prefijo):].isdigit() else 0
    )

    total_no = sum(c["no"]["dens_total"] for c in celdas_bloque.values())
    total_si = sum(c["si"]["dens_total"] for c in celdas_bloque.values())

    tendencia = "no" if total_no > total_si else "si"

    for item_key in items_ordenados:
        d = celdas_bloque[item_key]
        dens_no = d["no"]["dens_total"]
        dens_si = d["si"]["dens_total"]

        if max(dens_no, dens_si) < 0.05:
            continue

        direccion = "no" if dens_no > dens_si else "si"

        if direccion != tendencia:
            pos = items_ordenados.index(item_key)
            if pos < 2:
                items_revisar.add(item_key)

    return items_revisar


# =============================================================================
# GUARDAR IMÁGENES DEBUG
# =============================================================================

def _guardar_debug_items(
    celdas_por_bloque,
    items_revisar,
    prefijo_a_roi,
    x_cortes_por_bloque,
    filas_por_bloque
):
    """
    Guarda imágenes de las celdas marcadas como "revisar" para inspección.
    """
    if not GUARDAR_DEBUG_ITEMS:
        return

    try:
        os.makedirs(RUTA_DEBUG_ITEMS, exist_ok=True)
    except Exception:
        return

    for prefijo, celdas in celdas_por_bloque.items():
        roi = prefijo_a_roi.get(prefijo)
        x_cortes = x_cortes_por_bloque.get(prefijo)
        filas = filas_por_bloque.get(prefijo)

        if roi is None or x_cortes is None or filas is None:
            continue

        for item_key in sorted(items_revisar):
            if not item_key.startswith(prefijo):
                continue

            try:
                idx = int(item_key[len(prefijo):]) - 1
                if idx < 0 or idx >= len(filas):
                    continue

                fila = filas[idx]
                y1, y2 = fila["y1"], fila["y2"]
                x_no_a, x_no_b = x_cortes[1], x_cortes[2]
                x_si_a, x_si_b = x_cortes[2], x_cortes[3]

                celda_no = roi[y1:y2, x_no_a:x_no_b]
                celda_si = roi[y1:y2, x_si_a:x_si_b]

                # Concatenar horizontalmente
                h = min(celda_no.shape[0], celda_si.shape[0])
                c_no = celda_no[:h]
                c_si = celda_si[:h]
                combinada = np.hstack([c_no, np.full((h, 5), 128, dtype=np.uint8), c_si])

                # Escalar 3x
                combinada = cv2.resize(
                    combinada, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST
                )

                ruta = os.path.join(RUTA_DEBUG_ITEMS, f"{item_key}.png")
                cv2.imwrite(ruta, combinada)
            except Exception as e:
                logger.debug("Error guardando debug %s: %s", item_key, e)


def _detectar_posible_swap_tope(celdas_bloque, prefijo):
    """
    Detecta si las 2 primeras filas del bloque podrían estar invertidas.

    Patrón:
      - La tendencia del bloque (sin la primera fila) es clara.
      - Fila 0 va contra la tendencia.
      - Fila 1 sigue la tendencia.
      - Fila 2 sigue la tendencia.
      - Densidades de 0 y 1 son comparables.

    IMPORTANTE: Esto NO corrige. Solo marca para revisión.
    """
    if not celdas_bloque or len(celdas_bloque) < 4:
        return set()

    items_ordenados = sorted(
        celdas_bloque.keys(),
        key=lambda k: int(k[len(prefijo):]) if k[len(prefijo):].isdigit() else 0
    )

    key_0, key_1, key_2 = items_ordenados[0], items_ordenados[1], items_ordenados[2]

    # Tendencia del bloque SIN la primera fila
    suma_no = sum(celdas_bloque[k]["no"]["dens_total"]
                  for k in items_ordenados[1:])
    suma_si = sum(celdas_bloque[k]["si"]["dens_total"]
                  for k in items_ordenados[1:])

    if suma_no > suma_si * 3:
        tendencia = "no"
    elif suma_si > suma_no * 3:
        tendencia = "si"
    else:
        return set()

    direccion_opuesta = "si" if tendencia == "no" else "no"

    def _dir(d):
        dn = d["no"]["dens_total"]
        ds = d["si"]["dens_total"]
        if max(dn, ds) < 0.030:
            return None
        return "no" if dn > ds else "si"

    dir_0 = _dir(celdas_bloque[key_0])
    dir_1 = _dir(celdas_bloque[key_1])
    dir_2 = _dir(celdas_bloque[key_2])

    if not (dir_0 == direccion_opuesta and dir_1 == tendencia and dir_2 == tendencia):
        return set()

    dens_0 = max(celdas_bloque[key_0]["no"]["dens_total"],
                 celdas_bloque[key_0]["si"]["dens_total"])
    dens_1 = max(celdas_bloque[key_1]["no"]["dens_total"],
                 celdas_bloque[key_1]["si"]["dens_total"])

    if dens_0 < 0.030 or dens_1 < 0.030:
        return set()

    ratio = max(dens_0, dens_1) / max(min(dens_0, dens_1), 0.001)
    if ratio > 3.0:
        return set()

    logger.warning(
        "Posible swap detectado en %s: %s (dir=%s) ↔ %s (dir=%s) [tend=%s]",
        prefijo, key_0, dir_0, key_1, dir_1, tendencia
    )
    return {key_0, key_1}


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def procesar_formulario_pdf(pdf_source):
    marcas = generar_items_vacios()
    detalles: Dict[str, Any] = {}
    mensajes: list = []

    try:
        # 1. Cargar archivo (PDF, JPG, PNG, BMP, TIFF, WEBP)
        try:
            imagenes = cargar_formulario(pdf_source, dpi=DPI_PROCESAMIENTO)
        except ValueError as e_doc:
            logger.error("Error al cargar el archivo: %s", e_doc, exc_info=True)
            return _respuesta_error(marcas, detalles,
                "El archivo está dañado o su formato no está soportado. "
                "Acepta PDF, JPG, PNG, BMP, TIFF y WEBP.")
        except Exception as e_doc:
            logger.error("Error inesperado al cargar el archivo: %s",
                         e_doc, exc_info=True)
            return _respuesta_error(marcas, detalles,
                "No se pudo abrir el archivo. Verifica que no esté corrupto.")

        if not imagenes:
            return _respuesta_error(marcas, detalles,
                "El archivo no contiene imágenes legibles.")

        if len(imagenes) > 1:
            logger.warning("Documento con %d páginas. Procesando la primera.",
                           len(imagenes))
            mensajes.append(f"⚠️ Documento de {len(imagenes)} páginas.")

        img_np = imagenes[0]

        # 2. Orientación
        img_np = _verificar_orientacion_pdf(img_np)

        # 3. Preprocesamiento
        prep = preprocesar_imagen(img_np, metodo_binarizacion="otsu")
        binaria = prep["binaria"]
        gris = prep["gris"]
        es_foto = prep.get("es_foto", False)
        logger.info(
            "Preprocesado: deskew=%.2f°, origen=%s",
            prep.get("angulo_correccion", 0.0),
            "FOTO" if es_foto else "ESCÁNER"
        )

        es_valida, motivo = _validar_binarizacion(binaria, gris)
        if not es_valida:
            logger.info("Otsu no óptima (%s). Reintentando adaptativo...", motivo)
            binaria = binarizar(gris, metodo="adaptativo")
            es_valida_2, motivo_2 = _validar_binarizacion(binaria, gris)
            if not es_valida_2:
                return _respuesta_error(marcas, detalles,
                    "El escaneo tiene muy baja calidad o está demasiado borroso.",
                    paginas=1)

        # 3b. Sustracción de plantilla
        diff_img = None
        usar_diff = False

        try:
            diff_img = obtener_imagen_diff(gris)
            cv2.imwrite("debug_scan_gris.png", gris)

            if diff_img is not None:
                cv2.imwrite("debug_diff_raw.png", diff_img)

                if diff_img.shape != binaria.shape:
                    # FIX: no reescalar. Un diff con shape distinta es basura.
                    logger.warning(
                        "Diff shape %s != binaria shape %s. "
                        "Descartando diff (evita corromper el análisis).",
                        diff_img.shape, binaria.shape,
                    )
                    diff_img = None
                    usar_diff = False
                else:
                    diff_img = cv2.bitwise_not(diff_img)
                    cv2.imwrite("debug_diff.png", diff_img)

                    pixeles_tinta = int(np.sum(diff_img == 0))
                    densidad_tinta = pixeles_tinta / diff_img.size

                    logger.info(
                        "DENSIDAD DIFF = %.6f | pixeles negros = %d | total = %d",
                        densidad_tinta, pixeles_tinta, diff_img.size
                    )

                    if densidad_tinta < DENSIDAD_MINIMA_DIFF:
                        logger.warning(
                            "✗ Diff casi vacío (%.4f < %.4f).",
                            densidad_tinta, DENSIDAD_MINIMA_DIFF
                        )
                        usar_diff = False
                    elif densidad_tinta > DENSIDAD_MAXIMA_DIFF:
                        logger.warning(
                            "✗ Diff demasiado denso (%.4f > %.4f). "
                            "Cuadrícula residual. Cayendo a modo clásico.",
                            densidad_tinta, DENSIDAD_MAXIMA_DIFF
                        )
                        usar_diff = False
                    else:
                        usar_diff = True
                        logger.info("✓ Sustracción aplicada (invertida).")
            else:
                logger.warning("✗ Sustracción no disponible.")
        except Exception as e:
            logger.warning("Error en sustracción: %s", e)
            usar_diff = False

        # 4. Detección de tablas
        gris_para_analisis_global = gris
        logger.info("Var. gris: imagen completa en gris lista para análisis.")
        tablas = detectar_3_tablas_geometria(binaria)
        es_valida_tablas, motivo_tablas = _validar_estructura_tablas(tablas)
        if not es_valida_tablas:
            return _respuesta_error(marcas, detalles,
                f"No se pudo identificar la estructura ({motivo_tablas}).",
                paginas=1)

        tablas = sorted(tablas, key=lambda t: t["x"])

        bloques_info = [
            ("ESTILOS PERSONALES",         "E", 33, tablas[0]),
            ("ACTIVIDADES DE PREFERENCIA", "P", 47, tablas[1]),
            ("PERCEPCIÓN DE HABILIDAD",    "H", 38, tablas[2]),
        ]

        # PASE 1
        logger.info("PASE 1: Extrayendo señales por bloque...")

        celdas_por_bloque: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {
            "E": {}, "P": {}, "H": {}
        }
        roi_por_bloque: Dict[str, np.ndarray] = {}
        x_cortes_por_bloque: Dict[str, List[int]] = {}
        filas_por_bloque: Dict[str, List[Dict[str, int]]] = {}

        total_procesados = 0
        bloques_con_problemas: list = []

        for nombre_bloque, prefijo, n_esperados, info_tabla in bloques_info:
            roi_tabla = info_tabla["roi_binaria"]
            x_tabla = info_tabla["x"]
            y_tabla = info_tabla["y"]
            h_tabla, w_tabla = roi_tabla.shape

            if usar_diff and diff_img is not None:
                roi_para_analisis = diff_img[
                    y_tabla:y_tabla + h_tabla,
                    x_tabla:x_tabla + w_tabla
                ]
            else:
                roi_para_analisis = roi_tabla

            # Recortar la misma región desde la imagen en gris
            gris_para_analisis = gris_para_analisis_global[
                y_tabla:y_tabla + h_tabla,
                x_tabla:x_tabla + w_tabla
            ]

            if gris_para_analisis.shape != roi_tabla.shape:
                logger.warning(
                    "gris_para_analisis shape %s != roi_tabla shape %s. "
                    "Ajustando.",
                    gris_para_analisis.shape, roi_tabla.shape
                )
                try:
                    gris_para_analisis = cv2.resize(
                        gris_para_analisis,
                        (roi_tabla.shape[1], roi_tabla.shape[0]),
                        interpolation=cv2.INTER_LINEAR
                    )
                except Exception as e:
                    logger.warning("Resize falló: %s. Usando gris global.", e)
                    gris_para_analisis = gris_para_analisis_global

            try:
                filas, x_cortes = obtener_filas_y_columnas_tabla(roi_tabla, n_esperados)
            except Exception as e_rows:
                logger.error("Error en cuadrícula de %s: %s", nombre_bloque, e_rows)
                bloques_con_problemas.append(f"{nombre_bloque}: cuadrícula")
                continue

            if len(x_cortes) < 4:
                bloques_con_problemas.append(f"{nombre_bloque}: cortes X")
                continue

            if len(filas) != n_esperados:
                bloques_con_problemas.append(f"{nombre_bloque}: {len(filas)}/{n_esperados}")

            x_no_a, x_no_b = x_cortes[1], x_cortes[2]
            x_si_a, x_si_b = x_cortes[2], x_cortes[3]

            items_bloque = 0
            for idx, fila in enumerate(filas):
                if idx >= n_esperados:
                    break

                item_key = f"{prefijo}{idx + 1}"
                y1, y2 = fila["y1"], fila["y2"]

                if y2 <= y1 or (y2 - y1) < 3:
                    continue

                celda_no = roi_para_analisis[y1:y2, x_no_a:x_no_b]
                celda_si = roi_para_analisis[y1:y2, x_si_a:x_si_b]

                if celda_no.size == 0 or celda_si.size == 0:
                    continue

                s_no = analizar_trazo_celda_multisenal(celda_no)
                s_si = analizar_trazo_celda_multisenal(celda_si)
                s_no["dist_transform"] = calcular_distance_transform_score(celda_no)
                s_si["dist_transform"] = calcular_distance_transform_score(celda_si)

                # Añadir varianza gris
                try:
                    gris_celda_no = gris[y_tabla + y1:y_tabla + y2,
                                          x_tabla + x_no_a:x_tabla + x_no_b]
                    gris_celda_si = gris[y_tabla + y1:y_tabla + y2,
                                          x_tabla + x_si_a:x_tabla + x_si_b]
                    s_no["varianza_gris"] = calcular_varianza_gris(gris_celda_no)
                    s_si["varianza_gris"] = calcular_varianza_gris(gris_celda_si)
                except Exception as e:
                    logger.debug("Var. gris falló para %s: %s", item_key, e)
                    s_no["varianza_gris"] = 0.0
                    s_si["varianza_gris"] = 0.0

                celdas_por_bloque[prefijo][item_key] = {"no": s_no, "si": s_si}
                items_bloque += 1

            # Guardar referencias para debug
            roi_por_bloque[prefijo] = roi_para_analisis
            x_cortes_por_bloque[prefijo] = x_cortes
            filas_por_bloque[prefijo] = filas

            total_procesados += items_bloque
            logger.info("Bloque %s (%s): %d/%d celdas.",
                        nombre_bloque, prefijo, items_bloque, n_esperados)

        # PASE 2: Análisis y clasificación
        logger.info("PASE 2: Análisis y clasificación...")

        items_revisar_globales = set()

        for prefijo in ["E", "P", "H"]:
            celdas_bloque = celdas_por_bloque[prefijo]

            # Densidades con MAX: la celda "más marcada" de cada ítem.
            densidades_bloque = [
                max(c["no"]["dens_total"], c["si"]["dens_total"])
                for c in celdas_bloque.values()
            ]

            # Densidades con MIN: la celda "más vacía" de cada ítem.
            # Solo para detectar cuadrícula residual / diff fallido.
            densidades_min_bloque = [
                min(c["no"]["dens_total"], c["si"]["dens_total"])
                for c in celdas_bloque.values()
            ]

            # =================================================================
            # DETECCIÓN DE CUADRÍCULA RESIDUAL
            # =================================================================
            mediana_min = float(np.median(densidades_min_bloque)) if densidades_min_bloque else 0.0
            mediana_max = float(np.median(densidades_bloque)) if densidades_bloque else 0.0

            logger.info(
                "Bloque %s: mediana(min)=%.4f mediana(max)=%.4f (n=%d)",
                prefijo, mediana_min, mediana_max, len(densidades_min_bloque)
            )

            if mediana_min > UMBRAL_MEDIANA_RESIDUAL:
                logger.warning(
                    "Bloque %s: mediana(min)=%.4f > %.2f. "
                    "Cuadrícula residual detectada. Todas las celdas → 'vacio'.",
                    prefijo, mediana_min, UMBRAL_MEDIANA_RESIDUAL
                )
                for item_key in celdas_bloque.keys():
                    marcas[item_key] = "vacio"
                    detalles[item_key] = {
                        "opcion": "vacio", "puntaje": 0, "confianza": "alta",
                        "motivo": "cuadrícula residual en el bloque"
                    }
                continue

            analisis = _analizar_bloque(celdas_bloque, prefijo)
            tipo_bloque = analisis["tipo"]
            umbral_bloque = analisis["umbral"]

            logger.info("Bloque %s: tipo=%s, umbral=%.4f",
                        prefijo, tipo_bloque, umbral_bloque)

            if tipo_bloque == "vacio":
                for item_key in celdas_bloque.keys():
                    marcas[item_key] = "vacio"
                    detalles[item_key] = {
                        "opcion": "vacio", "puntaje": 0, "confianza": "alta",
                        "dens_total_no": round(celdas_bloque[item_key]["no"]["dens_total"], 4),
                        "dens_total_si": round(celdas_bloque[item_key]["si"]["dens_total"], 4),
                    }
                continue

            # Clasificar
            for item_key, d in celdas_bloque.items():
                clasif = _clasificar_celda(d["no"], d["si"], umbral_bloque, densidades_bloque)
                marcas[item_key] = clasif["opcion"]
                detalles[item_key] = {
                    "opcion": clasif["opcion"],
                    "puntaje": clasif["puntaje"],
                    "dens_total_no": round(d["no"]["dens_total"], 4),
                    "dens_total_si": round(d["si"]["dens_total"], 4),
                    "dens_centro_no": round(d["no"]["dens_centro"], 4),
                    "dens_centro_si": round(d["si"]["dens_centro"], 4),
                    "stroke_ratio_no": round(d["no"]["stroke_ratio"], 3),
                    "stroke_ratio_si": round(d["si"]["stroke_ratio"], 3),
                    "confianza": clasif["confianza"],
                }
                if clasif.get("revisar"):
                    detalles[item_key]["revisar"] = True
                    detalles[item_key]["motivo"] = clasif.get("motivo", "")

            # Detectar outliers y coherencia
            items_revisar = _detectar_outliers_bloque(
                celdas_bloque, prefijo, densidades_bloque
            )
            items_incoherentes = _validar_coherencia_bloque(celdas_bloque, prefijo)
            items_revisar = items_revisar | items_incoherentes

            swap_flag = _detectar_posible_swap_tope(celdas_bloque, prefijo)
            if swap_flag:
                items_revisar = items_revisar | swap_flag

            # Aplicar flags
            for item_key in items_revisar:
                if item_key in detalles and not detalles[item_key].get("revisar"):
                    detalles[item_key]["revisar"] = True
                    detalles[item_key]["motivo"] = "outlier del bloque"

            for item_key in swap_flag:
                if item_key in detalles:
                    detalles[item_key]["revisar"] = True
                    detalles[item_key]["motivo"] = "posible swap de filas"

            items_revisar_globales |= items_revisar

            if items_revisar:
                logger.info("Bloque %s: items a revisar = %s",
                            prefijo, sorted(items_revisar))

        # Guardar imágenes de debug de los items marcados
        if items_revisar_globales:
            _guardar_debug_items(
                celdas_por_bloque,
                items_revisar_globales,
                roi_por_bloque,
                x_cortes_por_bloque,
                filas_por_bloque,
            )

        # Resultado
        audit = auditar_marcas(marcas)
        n_vacios = len(audit.get("vacios", []))
        n_ambos = len(audit.get("ambos", []))
        n_revisar = sum(1 for d in detalles.values() if d.get("revisar"))

        umbral_total = int(TOTAL_ITEMS_ESPERADOS * PORCENTAJE_EXITO_TOTAL)
        umbral_parcial = int(TOTAL_ITEMS_ESPERADOS * PORCENTAJE_EXITO_PARCIAL)

        modo = "con sustracción" if usar_diff else "clásico"

        if total_procesados >= umbral_total and not bloques_con_problemas:
            exito = True
            mensajes.append(
                f"✅ OCR completado ({modo}): {total_procesados}/{TOTAL_ITEMS_ESPERADOS}. "
                f"({n_vacios} vacíos, {n_ambos} dobles, {n_revisar} a revisar)."
            )
        elif total_procesados >= umbral_parcial:
            exito = True
            mensajes.append(
                f"⚠️ Procesado con advertencias ({modo}): "
                f"{total_procesados}/{TOTAL_ITEMS_ESPERADOS}."
            )
            if bloques_con_problemas:
                mensajes.append("Bloques: " + ", ".join(bloques_con_problemas) + ".")
        else:
            exito = False
            mensajes.append(
                f"❌ Procesamiento insuficiente: {total_procesados}/{TOTAL_ITEMS_ESPERADOS}."
            )

        return {
            "exito": exito,
            "marcas": marcas,
            "detalles": detalles,
            "audit": audit,
            "mensaje": " ".join(mensajes),
            "paginas": 1,
            "total_procesados": total_procesados,
            "modo": "diff" if usar_diff else "clasico",
            "items_revisar": sorted([k for k, d in detalles.items() if d.get("revisar")]),
        }

    except FileNotFoundError:
        return _respuesta_error(marcas, detalles,
            "No se pudo acceder al archivo proporcionado.")
    except MemoryError:
        return _respuesta_error(marcas, detalles,
            "La imagen es demasiado grande.")
    except Exception as e:
        logger.error("Excepción no controlada: %s", e, exc_info=True)
        return _respuesta_error(marcas, detalles,
            f"Error inesperado ({type(e).__name__}).")


# =============================================================================
# WRAPPER CON TIMEOUT
# =============================================================================

def procesar_formulario_pdf_con_timeout(pdf_source, timeout_seg=TIMEOUT_SEGUNDOS):
    marcas = generar_items_vacios()
    detalles: Dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=1) as executor:
        futuro = executor.submit(procesar_formulario_pdf, pdf_source)
        try:
            return futuro.result(timeout=timeout_seg)
        except FuturesTimeout:
            return _respuesta_error(marcas, detalles,
                f"El procesamiento excedió {timeout_seg} segundos.")
        except Exception as e:
            return _respuesta_error(marcas, detalles,
                f"Error inesperado: {type(e).__name__}.")