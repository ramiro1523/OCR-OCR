"""
Pipeline OCR principal para formularios IEPPO.

Layout del formulario (1 página, 3 tablas lado a lado):
  ┌───────────────┬─────────────────────┬──────────────────┐
  │ Parte 1       │ Parte 2             │ Parte 3          │
  │ Estilos (E)   │ Preferencias (P)    │ Habilidad (H)    │
  │ E1 – E33      │ P1 – P47            │ H1 – H38         │
  │ Col: Nº|No|Sí │ Col: Nº|No|Sí       │ Col: Nº|No|Sí    │
  └───────────────┴─────────────────────┴──────────────────┘

Cada tabla tiene filas con 3 celdas funcionales:
  Celda 0 → etiqueta (Nº)
  Celda 1 → casilla "No" (No se parece / No me interesa / No soy hábil)
  Celda 2 → casilla "Sí" (Se parece / Me interesa / Soy hábil)
"""

import logging
from typing import Union, Dict, Any, List
import io
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.marks import clasificar_item
from vocacional.utils import generar_items_vacios, obtener_bloques, auditar_marcas

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# MAPEO DE ETIQUETAS ORDENADAS
# ─────────────────────────────────────────────────────────────

def _etiquetas_ordenadas() -> List[str]:
    """Devuelve los 118 ítems en el orden correcto del formulario."""
    bloques = obtener_bloques()
    resultado = []
    for items in bloques.values():
        resultado.extend(items)
    return resultado  # E1..E33, P1..P47, H1..H38


# ─────────────────────────────────────────────────────────────
# DETECCIÓN DE FILAS EN UNA REGIÓN DE TABLA
# ─────────────────────────────────────────────────────────────

def _detectar_filas_tabla(
    roi_binaria: np.ndarray,
    n_items_esperados: int,
    min_altura_fila: int = 8,
    max_altura_fila: int = 60
) -> List[Dict[str, Any]]:
    """
    Detecta las filas de datos dentro de una región de tabla binarizada.
    Agrupa contornos por posición Y para identificar filas.
    
    Retorna lista de filas: [{"y_centro": int, "y1": int, "y2": int}, ...]
    ordenadas de arriba hacia abajo.
    """
    import cv2

    h_roi, w_roi = roi_binaria.shape[:2]

    # Proyección horizontal: sumar píxeles negros (tinta) por fila de píxeles
    # Líneas horizontales = alta concentración de tinta
    inv = cv2.bitwise_not(roi_binaria)

    # Usar morfología para aislar líneas horizontales
    longitud_linea = max(int(w_roi * 0.3), 20)
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (longitud_linea, 1))
    lineas_h = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel_h)

    # Proyección horizontal: sumar píxeles blancos por fila
    proyeccion = np.sum(lineas_h, axis=1).astype(np.float32)

    # Normalizar
    if proyeccion.max() > 0:
        proyeccion = proyeccion / proyeccion.max()

    # Encontrar posiciones Y donde hay líneas divisorias (umbral > 0.4)
    umbral = 0.4
    en_linea = proyeccion > umbral
    
    # Detectar transiciones: inicio y fin de cada línea
    separadores_y = []
    en_bloque = False
    inicio = 0
    for y, val in enumerate(en_linea):
        if val and not en_bloque:
            en_bloque = True
            inicio = y
        elif not val and en_bloque:
            en_bloque = False
            centro = (inicio + y) // 2
            separadores_y.append(centro)

    if en_bloque:
        separadores_y.append((inicio + h_roi) // 2)

    # Construir filas a partir de los separadores
    filas = []
    if len(separadores_y) >= 2:
        # Agregar borde superior e inferior si no están
        if separadores_y[0] > min_altura_fila:
            separadores_y = [0] + separadores_y
        if separadores_y[-1] < h_roi - min_altura_fila:
            separadores_y = separadores_y + [h_roi]

        for i in range(len(separadores_y) - 1):
            y1 = separadores_y[i]
            y2 = separadores_y[i + 1]
            altura = y2 - y1
            if min_altura_fila <= altura <= max_altura_fila:
                filas.append({
                    "y1": y1,
                    "y2": y2,
                    "y_centro": (y1 + y2) // 2,
                    "altura": altura
                })

    # Si no se detectaron suficientes filas con líneas, usar división uniforme
    if len(filas) < max(3, n_items_esperados // 3):
        logger.warning(
            "Pocas filas detectadas (%d), dividiendo uniformemente en %d",
            len(filas), n_items_esperados
        )
        filas = []
        # Estimar zona de datos (saltar encabezado ~15% superior)
        offset_header = int(h_roi * 0.15)
        zona_datos = h_roi - offset_header
        altura_fila = max(8, zona_datos // n_items_esperados)
        
        for i in range(n_items_esperados):
            y1 = offset_header + i * altura_fila
            y2 = min(h_roi, y1 + altura_fila)
            filas.append({
                "y1": y1,
                "y2": y2,
                "y_centro": (y1 + y2) // 2,
                "altura": altura_fila
            })

    return filas[:n_items_esperados]


# ─────────────────────────────────────────────────────────────
# EXTRACCIÓN DE CELDAS NO/SÍ EN UNA FILA
# ─────────────────────────────────────────────────────────────

def _extraer_casillas_fila(
    roi_fila: np.ndarray,
    n_columnas_total: int = 3
) -> tuple[np.ndarray, np.ndarray]:
    """
    Divide horizontalmente una fila en columnas y extrae las celdas No y Sí.
    
    Layout estándar IEPPO: [N° | No | Sí]  (3 columnas)
    - Columna 0 (izquierda): etiqueta (Nº)  → no se usa
    - Columna 1 (centro): casilla "No"
    - Columna 2 (derecha): casilla "Sí"
    
    Si la fila tiene diferente ancho, adapta proporciones.
    """
    h, w = roi_fila.shape[:2]
    ancho_col = w // n_columnas_total

    # Proporciones aproximadas observadas en el formulario IEPPO real:
    # Nº ocupa ~30% del ancho, No ~35%, Sí ~35%
    x_no = int(w * 0.30)
    x_si = int(w * 0.65)
    w_casilla = int(w * 0.33)

    celda_no = roi_fila[:, x_no: x_no + w_casilla]
    celda_si = roi_fila[:, x_si: x_si + w_casilla]

    return celda_no, celda_si


# ─────────────────────────────────────────────────────────────
# PROCESAR UNA TABLA COMPLETA (bloque E, P o H)
# ─────────────────────────────────────────────────────────────

def _procesar_bloque_tabla(
    roi_tabla: np.ndarray,
    etiquetas: List[str],
    marcas: dict,
    detalles: dict
) -> int:
    """
    Procesa una columna de tabla del formulario IEPPO (E, P o H).
    Detecta filas, clasifica cada casilla No/Sí, y GUARDA el resultado en marcas.
    
    Retorna: número de ítems procesados.
    """
    n_esperados = len(etiquetas)
    filas = _detectar_filas_tabla(roi_tabla, n_esperados)

    procesados = 0
    for i, fila in enumerate(filas):
        if i >= n_esperados:
            break

        etiqueta = etiquetas[i]
        y1, y2 = fila["y1"], fila["y2"]

        if y2 <= y1 or (y2 - y1) < 3:
            continue

        roi_fila = roi_tabla[y1:y2, :]
        if roi_fila.size == 0:
            continue

        celda_no, celda_si = _extraer_casillas_fila(roi_fila)

        if celda_no.size == 0 or celda_si.size == 0:
            continue

        # ✅ CORRECCIÓN DEL BUG: guardar resultado en marcas
        resultado = clasificar_item(celda_no, celda_si)
        marcas[etiqueta] = resultado["opcion"]   # "si" | "no" | "ambos" | "vacio"
        detalles[etiqueta] = resultado
        procesados += 1

    return procesados


# ─────────────────────────────────────────────────────────────
# DIVIDIR PÁGINA EN 3 BLOQUES (columnas de tablas)
# ─────────────────────────────────────────────────────────────

def _dividir_en_3_columnas(
    imagen_binaria: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Divide la página en 3 regiones horizontales correspondientes a:
      - Parte 1 (Estilos E): columna izquierda
      - Parte 2 (Preferencias P): columna central
      - Parte 3 (Habilidad H): columna derecha

    Detecta los límites reales de cada tabla buscando separaciones verticales
    (columnas de baja densidad de tinta). Si no hay separación clara, divide en tercios.
    """
    import cv2

    h, w = imagen_binaria.shape[:2]
    inv = cv2.bitwise_not(imagen_binaria)

    # Proyección vertical: sumar píxeles blancos por columna
    proyeccion_v = np.sum(inv, axis=0).astype(np.float32)

    # Normalizar
    if proyeccion_v.max() > 0:
        proyeccion_v = proyeccion_v / proyeccion_v.max()

    # Buscar valles (zonas de baja densidad = separadores entre tablas)
    # Solo buscar en la zona central de la página (evitar márgenes)
    zona_busqueda_inicio = int(w * 0.20)
    zona_busqueda_fin = int(w * 0.80)

    umbral_valle = 0.30
    en_valle = False
    valles = []
    inicio_valle = 0

    for x in range(zona_busqueda_inicio, zona_busqueda_fin):
        if proyeccion_v[x] < umbral_valle and not en_valle:
            en_valle = True
            inicio_valle = x
        elif proyeccion_v[x] >= umbral_valle and en_valle:
            en_valle = False
            centro_valle = (inicio_valle + x) // 2
            ancho_valle = x - inicio_valle
            if ancho_valle > int(w * 0.01):  # Valle mínimo de 1% del ancho
                valles.append(centro_valle)

    # Filtrar: necesitamos exactamente 2 valles para 3 bloques
    # Tomar el primer y segundo valle si hay suficientes
    if len(valles) >= 2:
        # Asegurar que los valles estén razonablemente distribuidos
        # (no demasiado juntos)
        valles_validos = [valles[0]]
        for v in valles[1:]:
            if v - valles_validos[-1] > int(w * 0.15):
                valles_validos.append(v)
        valles = valles_validos[:2]

    if len(valles) == 2:
        x_div1, x_div2 = valles[0], valles[1]
        logger.info("Divisiones detectadas en x=%d y x=%d (ancho=%d)", x_div1, x_div2, w)
    else:
        # Fallback: dividir en tercios
        x_div1 = w // 3
        x_div2 = (w * 2) // 3
        logger.warning("No se detectaron valles claros. Dividiendo en tercios: %d, %d", x_div1, x_div2)

    # Recortar con pequeño margen para excluir líneas divisorias
    margen = max(2, int(w * 0.005))
    col_e = imagen_binaria[:, 0: x_div1 - margen]
    col_p = imagen_binaria[:, x_div1 + margen: x_div2 - margen]
    col_h = imagen_binaria[:, x_div2 + margen: w]

    return col_e, col_p, col_h


# ─────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────

def procesar_formulario_pdf(pdf_source: Union[str, bytes, io.BytesIO]) -> Dict[str, Any]:
    """
    Pipeline OCR principal para el formulario IEPPO de una página.

    Pasos:
      1. Convertir PDF a imágenes de alta resolución (300 DPI).
      2. Preprocesar (escala de grises, deskew, binarización Otsu).
      3. Dividir la página en 3 columnas de tablas: E | P | H.
      4. En cada columna, detectar filas y clasificar casillas No/Sí.
      5. Guardar el estado detectado en el diccionario de marcas.

    Retorna dict con:
      - "exito": bool
      - "marcas": dict[item -> "si"|"no"|"ambos"|"vacio"]
      - "detalles": dict[item -> {densidad_no, densidad_si, confianza}]
      - "audit": resumen de ítems por estado
      - "mensaje": descripción del resultado
    """
    marcas = generar_items_vacios()
    detalles = {}
    mensajes = []
    exito = False

    try:
        imagenes = pdf_a_imagenes(pdf_source, dpi=300)

        if not imagenes:
            return {
                "exito": False,
                "marcas": marcas,
                "detalles": detalles,
                "mensaje": "El archivo PDF no contiene páginas legibles.",
                "audit": auditar_marcas(marcas)
            }

        # Obtener el orden correcto de las 118 etiquetas
        bloques = obtener_bloques()
        etiquetas_e = bloques["ESTILOS PERSONALES"]       # E1–E33 (33 ítems)
        etiquetas_p = bloques["ACTIVIDADES DE PREFERENCIA"]  # P1–P47 (47 ítems)
        etiquetas_h = bloques["PERCEPCIÓN DE HABILIDAD"]  # H1–H38 (38 ítems)

        total_procesados = 0

        for idx_pag, img in enumerate(imagenes):
            prep = preprocesar_imagen(img)
            binaria = prep["binaria"]

            logger.info("Página %d: %.1f° de corrección aplicada", idx_pag + 1, prep["angulo_correccion"])

            # Dividir en 3 columnas de tablas
            col_e, col_p, col_h = _dividir_en_3_columnas(binaria)

            # Procesar cada bloque — ✅ aquí se guardan los resultados en marcas
            n_e = _procesar_bloque_tabla(col_e, etiquetas_e, marcas, detalles)
            n_p = _procesar_bloque_tabla(col_p, etiquetas_p, marcas, detalles)
            n_h = _procesar_bloque_tabla(col_h, etiquetas_h, marcas, detalles)

            total_procesados += n_e + n_p + n_h
            logger.info(
                "Página %d: E=%d/%d  P=%d/%d  H=%d/%d  (total=%d/118)",
                idx_pag + 1,
                n_e, len(etiquetas_e),
                n_p, len(etiquetas_p),
                n_h, len(etiquetas_h),
                n_e + n_p + n_h
            )

        # Evaluación de calidad del resultado
        audit = auditar_marcas(marcas)

        if total_procesados == 0:
            mensajes.append(
                "⚠️ No se detectaron filas en el formulario. "
                "Por favor verifica que el PDF sea un escaneo válido del formulario IEPPO."
            )
            exito = False
        else:
            tasa = total_procesados / 118
            if tasa < 0.5:
                mensajes.append(
                    f"⚠️ Solo se procesaron {total_procesados}/118 ítems ({tasa*100:.0f}%). "
                    "El escaneo puede estar incompleto o muy inclinado. Revisa manualmente."
                )
            else:
                mensajes.append(
                    f"✅ OCR completado: {total_procesados}/118 ítems procesados. "
                    f"{len(audit['vacios'])} sin marca, {len(audit['ambos'])} con doble marca."
                )
            exito = True

        return {
            "exito": exito,
            "marcas": marcas,
            "detalles": detalles,
            "audit": audit,
            "mensaje": " ".join(mensajes),
            "paginas": len(imagenes),
            "total_procesados": total_procesados
        }

    except Exception as e:
        logger.error("Error en el pipeline OCR: %s", e, exc_info=True)
        return {
            "exito": False,
            "marcas": marcas,
            "detalles": detalles,
            "mensaje": (
                f"El OCR automático no pudo procesar el PDF ({str(e)}). "
                "Se habilitó la plantilla para verificación manual."
            ),
            "audit": auditar_marcas(marcas)
        }
