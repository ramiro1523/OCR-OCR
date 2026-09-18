"""
Script para generar la plantilla maestra del formulario IEPPO.

Uso:
    python generar_plantilla.py <ruta_al_pdf_en_blanco.pdf>

Ejemplo:
    python generar_plantilla.py C:\\Users\\danil\\Downloads\\ieppo_blanco.pdf

Genera:
    data/plantilla_ieppo.png       (binaria)
    data/plantilla_ieppo_gris.png  (grayscale, para ECC)
"""

import sys
import os
from pathlib import Path

import cv2

from ocr.pdf_to_image import pdf_a_imagenes
from ocr.preprocess import preprocesar_imagen


def main():
    if len(sys.argv) < 2:
        print("❌ Uso: python generar_plantilla.py <ruta_al_pdf_en_blanco.pdf>")
        print("   Ejemplo: python generar_plantilla.py ieppo_blanco.pdf")
        sys.exit(1)

    ruta_pdf = Path(sys.argv[1])
    if not ruta_pdf.exists():
        print(f"❌ No existe el archivo: {ruta_pdf}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print("  GENERANDO PLANTILLA MAESTRA")
    print(f"  PDF: {ruta_pdf}")
    print(f"{'=' * 60}\n")

    # 1. Renderizar PDF a imagen
    print("📄 Convirtiendo PDF a imagen...")
    imagenes = pdf_a_imagenes(str(ruta_pdf), dpi=300)

    if not imagenes:
        print("❌ El PDF no tiene páginas legibles.")
        sys.exit(1)

    if len(imagenes) > 1:
        print(f"⚠️  PDF con {len(imagenes)} páginas. Usando la primera.")

    img = imagenes[0]
    print(f"   Imagen: {img.shape[1]}x{img.shape[0]}")

    # 2. Preprocesar (gris + deskew + binarizar)
    print("\n🔧 Preprocesando (gris + deskew + binarizar)...")
    prep = preprocesar_imagen(img, metodo_binarizacion="otsu")
    binaria = prep["binaria"]
    gris = prep["gris"]

    # 3. Crear directorio data/ si no existe
    os.makedirs("data", exist_ok=True)

    # 4. Guardar
    ruta_bin = "data/plantilla_ieppo.png"
    ruta_gris = "data/plantilla_ieppo_gris.png"

    cv2.imwrite(ruta_bin, binaria)
    cv2.imwrite(ruta_gris, gris)

    print(f"\n✅ Plantilla guardada:")
    print(f"   - {ruta_bin}  ({binaria.shape[1]}x{binaria.shape[0]})")
    print(f"   - {ruta_gris} ({gris.shape[1]}x{gris.shape[0]})")
    print(f"\n{'=' * 60}")
    print("  Ahora ejecuta el pipeline normalmente.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()