# motor_pdf.py
"""
Motor de generación de PDF usando PyMuPDF.
Escribe directamente el texto sobre la plantilla (sin AcroForms, sin fondos azules).
"""
import os
from datetime import datetime
import pymupdf as fitz
from config_campos import (
    CAMPOS_TEXTO_P1, CAMPOS_TEXTO_P2, CAMPOS_MARCAS_P2,
)

PLANTILLA = "plantilla_original_reparada.pdf"
CARPETA = "salidas"

AREAS = ["liderazgo", "tecnico_mecanico", "social", "organizado",
         "artistico", "emprendimiento", "investigacion"]
NIVELES = ["bajo", "medio", "alto"]

CAMPOS_MAYUS = {
    "campo_areas",
    "campo_areas_2",
    "potencial_puesto",
    "campo_nombre",      # ← NUEVO: nombre del alumno en MAYÚSCULAS
    "campo_colegio",     # ← NUEVO: nombre del colegio en MAYÚSCULAS
}
CAMPOS_IZQUIERDA = {"campo_grado"}


def _escribir(page, cfg, valor, centrado=True, bold=False):
    x0 = cfg["x"]
    y0 = cfg["y"]
    ancho = cfg["width"]
    alto = cfg["height"]
    fs = cfg.get("font_size", 10)

    page_h = page.rect.height
    font = "hebo" if bold else "helv"
    txt = str(valor)

    y_top = page_h - y0 - alto
    y_base = y_top + (alto + fs * 0.7) / 2

    if centrado:
        tw = fitz.get_text_length(txt, fontname=font, fontsize=fs)
        x = x0 + (ancho - tw) / 2
    else:
        x = x0 + 0.5

    page.insert_text(
        fitz.Point(x, y_base),
        txt,
        fontsize=fs,
        fontname=font,
        color=(0, 0, 0),
    )


def _procesar_valor(nombre, valor):
    if valor is None:
        return ""
    valor = str(valor)

    # Grado de instrucción: agregar "°" si no lo tiene
    if nombre == "campo_grado_instruccion":
        valor = valor.strip()
        if not valor:              # ← si está vacío, devolver vacío
            return ""
        if not valor.endswith("°"):
            valor = valor + "°"
        return valor

    if nombre in CAMPOS_MAYUS:
        return valor.upper()
    return valor

def generar_pdf(datos: dict, ruta_salida: str = None) -> str:
    """
    datos = {
        "campo_nombre": "Ana Rozas Hucho",
        "campo_edad": "16",
        "campo_genero": "F",
        "campo_fecha": "30/09/2026",
        "campo_grado_instruccion": "5",
        "campo_grado": "COMPLETA",
        "campo_colegio": "SANTO DOMINGO DE PANGOA",
        "niveles": {"liderazgo": "bajo", ...},
        "potencial_puesto": "ALTO",
        "campo_areas": "SOCIAL",
        "campo_areas_2": "TÉCNICO MECÁNICO",
        "campo_carreras": "CIENCIAS DE LA SALUD",
        "campo_carreras_2": "ING AMBIENTAL",
    }
    """
    if not os.path.exists(PLANTILLA):
        raise FileNotFoundError(f"❌ No existe: {PLANTILLA}")

    doc = fitz.open(PLANTILLA)
    page1 = doc[0]
    page2 = doc[1]

    # Cabecera
    for nombre, cfg in CAMPOS_TEXTO_P1.items():
        valor = datos.get(nombre, "")
        if valor:
            valor = _procesar_valor(nombre, valor)
            _escribir(page1, cfg, valor,
                      centrado=(nombre not in CAMPOS_IZQUIERDA))

    # Marcas "X"
    niveles = datos.get("niveles", {})
    for area in AREAS:
        nivel = (niveles.get(area) or "").lower()
        for opcion in NIVELES:
            cfg = CAMPOS_MARCAS_P2[f"marca_{area}_{opcion}"]
            if opcion == nivel:
                _escribir(page2, cfg, "X", bold=True, centrado=True)

    # Potencial + oración final
    for nombre, cfg in CAMPOS_TEXTO_P2.items():
        valor = datos.get(nombre, "")
        if valor:
            valor = _procesar_valor(nombre, valor)
            _escribir(page2, cfg, valor,
                      centrado=(nombre not in CAMPOS_IZQUIERDA),
                      bold=(nombre == "potencial_puesto"))

    # Guardar
    if not ruta_salida:
        os.makedirs(CARPETA, exist_ok=True)
        n = datos.get("campo_nombre", "alumno").replace(" ", "_")
        f = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_salida = os.path.join(CARPETA, f"{n}_{f}.pdf")

    doc.save(ruta_salida, deflate=True)
    doc.close()
    return ruta_salida