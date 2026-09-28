# app.py
import json
import os
from datetime import datetime
import pymupdf as fitz
from pypdf import PdfReader, PdfWriter

PLANTILLA = "plantilla_formulario.pdf"
CARPETA = "salidas"

AREAS = ["liderazgo", "tecnico_mecanico", "social", "organizado",
         "artistico", "emprendimiento", "investigacion"]
NIVELES = ["bajo", "medio", "alto"]


def preparar_datos(datos: dict, nombres_campos: list) -> dict:
    salida = dict(datos)
    niveles = salida.pop("niveles", {})
    for area in AREAS:
        nivel_marcado = (niveles.get(area) or "").lower()
        for opcion in NIVELES:
            key = f"marca_{area}_{opcion}"
            salida[key] = "X" if opcion == nivel_marcado else ""
    for nombre in nombres_campos:
        salida.setdefault(nombre, "")
    return salida


def rellenar(datos: dict, nombre_archivo: str = None) -> str:
    os.makedirs(CARPETA, exist_ok=True)

    # 1. Rellenar con pypdf
    reader = PdfReader(PLANTILLA)
    writer = PdfWriter()
    writer.append(reader)
    try:
        writer.set_need_appearances_writer(True)
    except Exception:
        pass

    nombres_campos = list((reader.get_fields() or {}).keys())
    salida = preparar_datos(datos, nombres_campos)

    for page in writer.pages:
        writer.update_page_form_field_values(
            page, salida, auto_regenerate=False
        )

    if not nombre_archivo:
        n = salida.get("campo_nombre", "alumno").replace(" ", "_")
        f = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"{n}_{f}.pdf"

    ruta_final = os.path.join(CARPETA, nombre_archivo)
    ruta_temp = os.path.join(CARPETA, "_temp.pdf")

    with open(ruta_temp, "wb") as f:
        writer.write(f)

    # 2. Rasterizar cada página a imagen → PDF 100% limpio
    doc = fitz.open(ruta_temp)
    nuevo = fitz.open()

    for page in doc:
        # 3x = ~216 dpi (buena calidad, tamaño razonable)
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
        nueva_pag = nuevo.new_page(width=page.rect.width, height=page.rect.height)
        nueva_pag.insert_image(page.rect, pixmap=pix)

    nuevo.save(ruta_final, garbage=4, deflate=True)
    nuevo.close()
    doc.close()

    try:
        os.remove(ruta_temp)
    except Exception:
        pass

    print(f"✅ PDF generado (limpio): {ruta_final}")
    return ruta_final


def rellenar_desde_json(ruta_json: str) -> str:
    with open(ruta_json, "r", encoding="utf-8") as f:
        datos = json.load(f)
    return rellenar(datos)


if __name__ == "__main__":
    rellenar_desde_json("datos_ejemplo.json")