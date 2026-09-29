# app.py
import json
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

CAMPOS_MAYUS = {"campo_areas", "campo_areas_2", "potencial_puesto"}
CAMPOS_IZQUIERDA = {"campo_grado", "campo_grado_instruccion"}


def escribir(page, cfg, valor, centrado=True, bold=False):
    x0 = cfg["x"]
    y0 = cfg["y"]
    ancho = cfg["width"]
    alto = cfg["height"]
    fs = cfg.get("font_size", 10)

    page_h = page.rect.height
    font = "hebo" if bold else "helv"
    txt = str(valor)

    # ── Centrado vertical REAL ──
    # El texto tiene altura visual ≈ fs.
    # Baseline = top_rect + (alto + fs * 0.7) / 2
    # (0.7 ≈ ajuste empírico para que la "letra" quede centrada)
    y_top = page_h - y0 - alto
    y_base = y_top + (alto + fs * 0.7) / 2

    # ── Posición X ──
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


def procesar_valor(nombre, valor):
    if valor is None:
        return ""
    if nombre in CAMPOS_MAYUS:
        return str(valor).upper()
    return str(valor)


def rellenar(datos: dict, nombre_archivo: str = None) -> str:
    os.makedirs(CARPETA, exist_ok=True)

    if not os.path.exists(PLANTILLA):
        raise FileNotFoundError(f"❌ No existe: {PLANTILLA}")

    doc = fitz.open(PLANTILLA)
    page1 = doc[0]
    page2 = doc[1]

    # Cabecera
    for nombre, cfg in CAMPOS_TEXTO_P1.items():
        valor = datos.get(nombre, "")
        if valor:
            valor = procesar_valor(nombre, valor)
            centrado = nombre not in CAMPOS_IZQUIERDA
            escribir(page1, cfg, valor, centrado=centrado)

    # Marcas X
    niveles = datos.get("niveles", {})
    for area in AREAS:
        nivel = (niveles.get(area) or "").lower()
        for opcion in NIVELES:
            cfg = CAMPOS_MARCAS_P2[f"marca_{area}_{opcion}"]
            if opcion == nivel:
                escribir(page2, cfg, "X", bold=True, centrado=True)

    # Potencial + oración final
    for nombre, cfg in CAMPOS_TEXTO_P2.items():
        valor = datos.get(nombre, "")
        if valor:
            valor = procesar_valor(nombre, valor)
            centrado = nombre not in CAMPOS_IZQUIERDA
            escribir(page2, cfg, valor,
                     centrado=centrado,
                     bold=(nombre == "potencial_puesto"))

    if not nombre_archivo:
        n = datos.get("campo_nombre", "alumno").replace(" ", "_")
        f = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"{n}_{f}.pdf"

    ruta = os.path.join(CARPETA, nombre_archivo)
    doc.save(ruta, deflate=True)
    doc.close()

    print(f"✅ PDF generado: {ruta}")
    return ruta


def rellenar_desde_json(ruta_json: str) -> str:
    with open(ruta_json, "r", encoding="utf-8") as f:
        datos = json.load(f)
    return rellenar(datos)


if __name__ == "__main__":
    print("🚀 Iniciando...")
    rellenar_desde_json("datos_ejemplo.json")
    print("🏁 Terminado.")