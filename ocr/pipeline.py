"""
Pipeline OCR Principal para formularios IEPPO.

Combina:
  - Sustracción de plantilla (elimina cuadrícula, texto, ruido).
  - Filtro de líneas residuales del diff.
  - Análisis por bloque con umbral adaptativo.
  - Detección de bloques vacíos.
  - Clasificación multi-señal.
"""

import io
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Union, Dict, Any, List

import cv2
import numpy as np
import pytesseract

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen, binarizar
from ocr.tables import detectar_3_tablas_geometria
from ocr.rows import obtener_filas_y_columnas_tabla
from ocr.marks import analizar_trazo_celda_multisenal
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

# -----------------------------------------------------------------------------
# Detección de bloque VACÍO (con diff limpio sin líneas, valores bajan)
# -----------------------------------------------------------------------------
P75_VACIO = 0.020
P50_VACIO = 0.010
P25_MARCADO = 0.040

# Clamp del umbral
UMBRAL_MIN = 0.005
UMBRAL_MAX = 0.020

# Clasificación multi-señal
MARCA_DENS_FACTOR = 1.0
MARCA_CENTRO_FACTOR = 0.4
MARCA_STROKE_MIN = 0.15

RATIO_DESAMBIGUACION = 1.25

# Umbral mínimo de densidad para considerar válido el diff
DENSIDAD_MINIMA_DIFF = 0.001


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

    logger.info("Bloque %s: p25=%.4f, p50=%.4f, p75=%.4f (n=%d)",
                prefijo, p25, p50, p75, len(densidades))

    if p75 < P75_VACIO and p50 < P50_VACIO:
        logger.info("Bloque %s: VACÍO", prefijo)
        return {"tipo": "vacio", "umbral": 0.0, "p25": p25, "p50": p50, "p75": p75}

    if p25 > P25_MARCADO:
        umbral = max(UMBRAL_MIN, min(UMBRAL_MAX, p25 * 0.4))
        logger.info("Bloque %s: MARCADO (umbral=%.4f)", prefijo, umbral)
        return {"tipo": "marcado", "umbral": umbral, "p25": p25, "p50": p50, "p75": p75}

    umbral = (p25 + p75) / 2
    umbral = max(UMBRAL_MIN, min(UMBRAL_MAX, umbral))
    logger.info("Bloque %s: MIXTO (umbral=%.4f)", prefijo, umbral)
    return {"tipo": "mixto", "umbral": umbral, "p25": p25, "p50": p50, "p75": p75}


# =============================================================================
# CLASIFICACIÓN
# =============================================================================

def _es_marca_real(sig, umbral):
    if sig["dens_total"] < umbral * MARCA_DENS_FACTOR:
        return False
    if sig["dens_centro"] < umbral * MARCA_CENTRO_FACTOR:
        return False
    if sig["stroke_ratio"] < MARCA_STROKE_MIN:
        return False
    return True


def _clasificar_celda(s_no, s_si, umbral):
    marca_no = _es_marca_real(s_no, umbral)
    marca_si = _es_marca_real(s_si, umbral)

    if marca_no and not marca_si:
        return {"opcion": "no", "puntaje": 0, "confianza": "alta"}

    if marca_si and not marca_no:
        return {"opcion": "si", "puntaje": 1, "confianza": "alta"}

    if marca_no and marca_si:
        dens_no = s_no["dens_total"]
        dens_si = s_si["dens_total"]
        centro_no = s_no["dens_centro"]
        centro_si = s_si["dens_centro"]

        if dens_si > dens_no * RATIO_DESAMBIGUACION:
            return {"opcion": "si", "puntaje": 1, "confianza": "media"}
        if dens_no > dens_si * RATIO_DESAMBIGUACION:
            return {"opcion": "no", "puntaje": 0, "confianza": "media"}

        if centro_si > centro_no * 1.2:
            return {"opcion": "si", "puntaje": 1, "confianza": "baja"}
        if centro_no > centro_si * 1.2:
            return {"opcion": "no", "puntaje": 0, "confianza": "baja"}

        return {"opcion": "ambos", "puntaje": 1, "confianza": "baja"}

    return {"opcion": "vacio", "puntaje": 0, "confianza": "alta"}


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def procesar_formulario_pdf(pdf_source):
    marcas = generar_items_vacios()
    detalles: Dict[str, Any] = {}
    mensajes: list = []

    try:
        # =====================================================================
        # 1. RENDERIZAR PDF
        # =====================================================================
        try:
            imagenes = pdf_a_imagenes(pdf_source, dpi=DPI_PROCESAMIENTO)
        except Exception as e_pdf:
            logger.error("Error al renderizar PDF: %s", e_pdf, exc_info=True)
            return _respuesta_error(marcas, detalles,
                "El archivo está dañado, protegido con contraseña o no es un PDF válido.")

        if not imagenes:
            return _respuesta_error(marcas, detalles,
                "El archivo PDF no contiene páginas legibles.")

        if len(imagenes) > 1:
            logger.warning("PDF con %d páginas. Procesando la primera.", len(imagenes))
            mensajes.append(f"⚠️ PDF de {len(imagenes)} páginas.")

        img_np = imagenes[0]

        # =====================================================================
        # 2. ORIENTACIÓN
        # =====================================================================
        img_np = _verificar_orientacion_pdf(img_np)

        # =====================================================================
        # 3. PREPROCESAMIENTO
        # =====================================================================
        prep = preprocesar_imagen(img_np, metodo_binarizacion="otsu")
        binaria = prep["binaria"]
        gris = prep["gris"]
        logger.info("Deskew aplicado: %.2f°", prep.get("angulo_correccion", 0.0))

        es_valida, motivo = _validar_binarizacion(binaria, gris)
        if not es_valida:
            logger.info("Otsu no óptima (%s). Reintentando adaptativo...", motivo)
            binaria = binarizar(gris, metodo="adaptativo")
            es_valida_2, motivo_2 = _validar_binarizacion(binaria, gris)
            if not es_valida_2:
                return _respuesta_error(marcas, detalles,
                    "El escaneo tiene muy baja calidad o está demasiado borroso.",
                    paginas=1)

        # =====================================================================
        # 3b. SUSTRACCIÓN DE PLANTILLA
        # =====================================================================
        diff_img = None
        usar_diff = False

        try:
            diff_img = obtener_imagen_diff(gris)
            if diff_img is not None:
                if diff_img.shape != binaria.shape:
                    logger.warning(
                        "Shape de diff (%s) != binaria (%s). Redimensionando.",
                        diff_img.shape, binaria.shape
                    )
                    diff_img = cv2.resize(
                        diff_img,
                        (binaria.shape[1], binaria.shape[0]),
                        interpolation=cv2.INTER_NEAREST
                    )

                # Invertir (diff tiene fondo negro, marks espera fondo blanco)
                diff_img = cv2.bitwise_not(diff_img)

                pixeles_tinta = int(np.sum(diff_img == 0))
                densidad_tinta = pixeles_tinta / diff_img.size

                logger.info("Densidad de tinta en diff: %.4f", densidad_tinta)

                if densidad_tinta < DENSIDAD_MINIMA_DIFF:
                    logger.warning(
                        "✗ Diff casi vacío (%.4f). Descartando.",
                        densidad_tinta
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

        # =====================================================================
        # 4. DETECCIÓN DE TABLAS
        # =====================================================================
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

        # =====================================================================
        # PASE 1: EXTRAER SEÑALES POR BLOQUE
        # =====================================================================
        logger.info("PASE 1: Extrayendo señales por bloque...")

        celdas_por_bloque: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {
            "E": {}, "P": {}, "H": {}
        }
        total_procesados = 0
        bloques_con_problemas: list = []

        for nombre_bloque, prefijo, n_esperados, info_tabla in bloques_info:
            roi_tabla = info_tabla["roi_binaria"]
            x_tabla = info_tabla["x"]
            y_tabla = info_tabla["y"]
            h_tabla, w_tabla = roi_tabla.shape

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

            if usar_diff and diff_img is not None:
                roi_diff = diff_img[y_tabla:y_tabla + h_tabla,
                                     x_tabla:x_tabla + w_tabla]
                if roi_diff.shape != roi_tabla.shape:
                    logger.warning("ROI diff shape incorrecto. Usando binaria.")
                    roi_diff = roi_tabla
                roi_para_analisis = roi_diff
            else:
                roi_para_analisis = roi_tabla

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

                celdas_por_bloque[prefijo][item_key] = {"no": s_no, "si": s_si}
                items_bloque += 1

            total_procesados += items_bloque
            logger.info("Bloque %s (%s): %d/%d celdas.",
                        nombre_bloque, prefijo, items_bloque, n_esperados)

        # =====================================================================
        # PASE 2: ANÁLISIS Y CLASIFICACIÓN
        # =====================================================================
        logger.info("PASE 2: Análisis y clasificación...")

        for prefijo in ["E", "P", "H"]:
            celdas_bloque = celdas_por_bloque[prefijo]

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

            for item_key, d in celdas_bloque.items():
                clasif = _clasificar_celda(d["no"], d["si"], umbral_bloque)
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

        # =====================================================================
        # RESULTADO
        # =====================================================================
        audit = auditar_marcas(marcas)
        n_vacios = len(audit.get("vacios", []))
        n_ambos = len(audit.get("ambos", []))

        umbral_total = int(TOTAL_ITEMS_ESPERADOS * PORCENTAJE_EXITO_TOTAL)
        umbral_parcial = int(TOTAL_ITEMS_ESPERADOS * PORCENTAJE_EXITO_PARCIAL)

        modo = "con sustracción" if usar_diff else "clásico"

        if total_procesados >= umbral_total and not bloques_con_problemas:
            exito = True
            mensajes.append(
                f"✅ OCR completado ({modo}): {total_procesados}/{TOTAL_ITEMS_ESPERADOS}. "
                f"({n_vacios} vacíos, {n_ambos} dobles)."
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
        }

    except FileNotFoundError:
        return _respuesta_error(marcas, detalles,
            "No se pudo acceder al archivo PDF proporcionado.")
    except MemoryError:
        return _respuesta_error(marcas, detalles,
            "La imagen del PDF es demasiado grande.")
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