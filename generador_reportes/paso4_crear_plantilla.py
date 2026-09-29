# =====================================================================
# PASO4_CREAR_PLANTILLA.PY
# =====================================================================
# Crea la plantilla PDF con los 33 campos (invisibles o visibles según DEBUG).
#
#   DEBUG = True   →  cuadros rojos/amarillos VISIBLES (para calibrar)
#   DEBUG = False  →  campos INVISIBLES (para producción)
#
# Centrado:
#   - Horizontal: alignment (0=izq | 1=centro | 2=der) — por defecto centro.
#                 Si un campo define "alignment" en config_campos.py, se respeta.
#   - Vertical:   simulado con MARGEN_VERTICAL (reducir altura y centrar).
# =====================================================================

from PyPDFForm import PdfWrapper, Fields
from config_campos import (
    CAMPOS_TEXTO_P1, CAMPOS_TEXTO_P2, CAMPOS_MARCAS_P2
)

# --- Rutas ---
ENTRADA = "plantilla_original_reparada.pdf"
SALIDA  = "plantilla_formulario.pdf"

# --- Modo de calibración ---
# True  = cuadros visibles (borde rojo + fondo amarillo)
# False = campos invisibles (producción)
DEBUG = False

# --- Margen vertical alrededor del texto (simula centrado vertical) ---
# Valores recomendados: 1, 2, 3
#   - 1 → campos más ajustados al texto
#   - 2 → equilibrio (recomendado)
#   - 3 → campos un poco más altos
MARGEN_VERTICAL = 2


def _text(nombre, cfg, pagina):
    """
    Crea un campo de texto con:
      - Alineación horizontal configurable (por defecto: centrada)
      - Centrado vertical simulado (reduce altura y desplaza y)
    """
    x         = cfg["x"]
    y         = cfg["y"]           # base del área visual
    w         = cfg["width"]
    h         = cfg["height"]      # altura del área visual
    font_size = cfg.get("font_size", 9)

    # --- Centrado vertical simulado ---
    margen  = cfg.get("margen_v", MARGEN_VERTICAL)
    campo_h = font_size + margen
    campo_y = y + (h - campo_h) / 2

    return Fields.TextField(
        name=nombre,
        page_number=pagina,
        x=x,
        y=campo_y,
        width=w,
        height=campo_h,
        font_size=font_size,
        # 0=izq | 1=centro | 2=der — por defecto centro; configurable por campo
        alignment=cfg.get("alignment", 1),
        # --- Apariencia ---
        border_width=1 if DEBUG else 0,
        border_color=(1, 0, 0, 1) if DEBUG else None,
        bg_color=(1, 1, 0, 0.4) if DEBUG else None,
    )


def crear():
    pdf    = PdfWrapper(ENTRADA)
    campos = []

    # Página 1 — cabecera
    for nombre, cfg in CAMPOS_TEXTO_P1.items():
        campos.append(_text(nombre, cfg, pagina=1))

    # Página 2 — 21 marcas de la tabla
    for nombre, cfg in CAMPOS_MARCAS_P2.items():
        campos.append(_text(nombre, cfg, pagina=2))

    # Página 2 — potencial + oración final
    for nombre, cfg in CAMPOS_TEXTO_P2.items():
        campos.append(_text(nombre, cfg, pagina=2))

    pdf.bulk_create_fields(campos)

    with open(SALIDA, "wb+") as f:
        f.write(pdf.read())

    print(f"✅ {SALIDA} → {len(campos)} campos (DEBUG={DEBUG})")


if __name__ == "__main__":
    crear()