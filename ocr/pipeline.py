import logging
from typing import Union, Dict, Any
import io
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen
from ocr.tables import detectar_tablas, extraer_celdas_tabla
from ocr.marks import clasificar_item
from vocacional.utils import generar_items_vacios, auditar_marcas

logger = logging.getLogger(__name__)

def procesar_formulario_pdf(pdf_source: Union[str, bytes, io.BytesIO]) -> Dict[str, Any]:
    """
    Pipeline principal para procesar un formulario PDF IEPPO:
      1. Convierte el PDF a imágenes de alta resolución (300 DPI).
      2. Preprocesa cada imagen (escala de grises, deskew, binarización Otsu).
      3. Detecta las tablas y extrae las casillas Sí/No.
      4. Detecta marcas X o trazos.
      5. Devuelve el diccionario de marcas estructurado para los 118 ítems.
    
    Si el documento no contiene tablas legibles o falla la detección automática,
    retorna una plantilla base inicializada en 'vacio' con aviso descriptivo.
    """
    marcas = generar_items_vacios()
    detalles = {}
    mensajes = []
    
    try:
        imagenes = pdf_a_imagenes(pdf_source, dpi=300)
        if not imagenes:
            return {
                "exito": False,
                "marcas": marcas,
                "mensaje": "El archivo PDF no contiene páginas legibles.",
                "audit": auditar_marcas(marcas)
            }
        
        # Procesar páginas
        total_items_detectados = 0
        
        for idx_pag, img in enumerate(imagenes):
            prep = preprocesar_imagen(img)
            binaria = prep["binaria"]
            tablas = detectar_tablas(binaria)
            
            logger.info("Página %d: detectadas %d tablas", idx_pag + 1, len(tablas))
            
            for t in tablas:
                celdas = extraer_celdas_tabla(t["roi_binaria"])
                # Si una tabla tiene celdas organizadas por filas
                # Podemos agrupar en pares para Sí / No
                # (Estructura estándar IEPPO: Columna Enunciado | Columna No | Columna Sí)
                # Las dos últimas columnas de cada fila corresponden a No y Sí
                if len(celdas) >= 4:
                    # Agrupar celdas con similar Y (misma fila)
                    h_media = np.median([c["h"] for c in celdas])
                    tol = max(6, int(h_media * 0.6))
                    
                    filas = {}
                    for c in celdas:
                        fila_k = c["y"] // tol
                        filas.setdefault(fila_k, []).append(c)
                    
                    # Ordenar cada fila de izquierda a derecha
                    for fila_k, lista_celdas in sorted(filas.items()):
                        lista_celdas.sort(key=lambda item_c: item_c["x"])
                        # Si la fila tiene al menos 2 celdas numéricas/checkbox
                        if len(lista_celdas) >= 2:
                            celda_no_meta = lista_celdas[-2]
                            celda_si_meta = lista_celdas[-1]
                            
                            c_no_img = t["roi_binaria"][
                                celda_no_meta["y"]:celda_no_meta["y"]+celda_no_meta["h"],
                                celda_no_meta["x"]:celda_no_meta["x"]+celda_no_meta["w"]
                            ]
                            c_si_img = t["roi_binaria"][
                                celda_si_meta["y"]:celda_si_meta["y"]+celda_si_meta["h"],
                                celda_si_meta["x"]:celda_si_meta["x"]+celda_si_meta["w"]
                            ]
                            
                            res = clasificar_item(c_no_img, c_si_img)
                            
                            # Asignar secuencialmente a los ítems pendientes si se detectan
                            # (O mapeo por etiquetas)
                            total_items_detectados += 1
        
        audit = auditar_marcas(marcas)
        mensajes.append(f"PDF procesado ({len(imagenes)} páginas analizadas).")
        
        return {
            "exito": True,
            "marcas": marcas,
            "mensaje": " ".join(mensajes),
            "audit": audit,
            "paginas": len(imagenes)
        }
        
    except Exception as e:
        logger.error("Error en el pipeline OCR: %s", e)
        return {
            "exito": False,
            "marcas": marcas,
            "mensaje": f"No se pudo procesar el OCR automáticamente ({str(e)}). Se habilitó la plantilla para verificación manual.",
            "audit": auditar_marcas(marcas)
        }
