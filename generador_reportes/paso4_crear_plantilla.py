# paso4_crear_plantilla.py
from PyPDFForm import PdfWrapper, Fields
from config_campos import (
    CAMPOS_TEXTO_P1, CAMPOS_TEXTO_P2, CAMPOS_MARCAS_P2
)

ENTRADA = "plantilla_original_reparada.pdf"
SALIDA = "plantilla_formulario.pdf"

# 🔴 True = cuadros VISIBLES para calibrar  |  False = campos INVISIBLES
DEBUG = True


def _text(nombre, cfg, pagina):
    return Fields.TextField(
        name=nombre,
        page_number=pagina,
        x=cfg["x"], y=cfg["y"],
        width=cfg["width"], height=cfg["height"],
        font_size=cfg.get("font_size", 9),
        # --- Apariencia ---
        border_width=1 if DEBUG else 0,
        border_color=(1, 0, 0, 1) if DEBUG else None,       # rojo | sin borde
        bg_color=(1, 1, 0, 0.4) if DEBUG else None,         # amarillo translúcido | sin fondo
    )


def crear():
    pdf = PdfWrapper(ENTRADA)
    campos = []

    for nombre, cfg in CAMPOS_TEXTO_P1.items():
        campos.append(_text(nombre, cfg, pagina=1))

    for nombre, cfg in CAMPOS_MARCAS_P2.items():
        campos.append(_text(nombre, cfg, pagina=2))

    for nombre, cfg in CAMPOS_TEXTO_P2.items():
        campos.append(_text(nombre, cfg, pagina=2))

    pdf.bulk_create_fields(campos)
    with open(SALIDA, "wb+") as f:
        f.write(pdf.read())

    print(f"✅ {SALIDA} → {len(campos)} campos (DEBUG={DEBUG})")


if __name__ == "__main__":
    crear()