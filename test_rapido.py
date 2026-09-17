"""
Script de prueba rápida del pipeline OCR IEPPO.

Uso:
    python test_rapido.py <ruta_al_pdf>

Ejemplo:
    python test_rapido.py C:\\Users\\danil\\Downloads\\PRUEBA1.pdf
"""

import sys
import json
import logging
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

# Suprimir logs ruidosos de librerías externas
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("pdfminer").setLevel(logging.WARNING)


# ============================================================
# FUNCIÓN DE PRUEBA DE TABLAS (diagnóstico opcional)
# ============================================================

def probar_deteccion_tablas(ruta_pdf):
    """
    Ejecuta una prueba independiente para inspeccionar:
    - ROI de cada tabla
    - líneas horizontales
    - líneas verticales
    - proyección de líneas horizontales

    Guarda imágenes de depuración en la carpeta actual.
    """
    print(f"\n{'=' * 70}")
    print("  PRUEBA DE DETECCIÓN GEOMÉTRICA DE TABLAS")
    print(f"{'=' * 70}\n")

    try:
        from ocr.pdf_to_image import pdf_a_imagenes
        from ocr.preprocess import preprocesar_imagen
        from ocr.tables import (
            aislar_lineas_morfologicas,
            detectar_3_tablas_geometria
        )
    except ImportError as e:
        print(f"❌ Error importando módulos para detección de tablas: {e}")
        return

    try:
        print("📄 Convirtiendo PDF a imagen...")
        imagenes = pdf_a_imagenes(str(ruta_pdf), dpi=300)

        if not imagenes:
            print("❌ No se obtuvieron imágenes del PDF.")
            return

        img = imagenes[0]
        print(f"   Imagen obtenida: {img.shape[1]}x{img.shape[0]}")

        print("\n🔧 Preprocesando imagen...")
        prep = preprocesar_imagen(img)
        binaria = prep["binaria"]
        print(f"   Imagen binaria: {binaria.shape[1]}x{binaria.shape[0]}")

        print("\n📐 Detectando tablas geométricamente...")
        tablas = detectar_3_tablas_geometria(binaria)
        print(f"\n✅ Tablas detectadas: {len(tablas)}")

        if not tablas:
            print("⚠️ No se detectaron tablas.")
            return

        for i, t in enumerate(tablas):
            roi = t["roi_binaria"]
            h, w = roi.shape

            print(f"\n{'-' * 70}")
            print(f"  TABLA {i}")
            print(f"{'-' * 70}")
            print(f"  Tamaño:   {w}x{h}")
            print(f"  Posición: x={t['x']}, y={t['y']}")

            inv = cv2.bitwise_not(roi)
            lineas_h, lineas_v = aislar_lineas_morfologicas(inv)

            proy_y = np.sum(lineas_h, axis=1)
            proy_x = np.sum(lineas_v, axis=0)

            print(f"  Proyección Y: max={proy_y.max()}, mean={proy_y.mean():.1f}")
            print(f"  Proyección X: max={proy_x.max()}, mean={proy_x.mean():.1f}")

            cv2.imwrite(f"debug_tabla_{i}_roi.png", roi)
            cv2.imwrite(f"debug_tabla_{i}_lineas_h.png", lineas_h)
            cv2.imwrite(f"debug_tabla_{i}_lineas_v.png", lineas_v)

            print(f"  🖼️  debug_tabla_{i}_*.png guardados")

        print(f"\n{'=' * 70}")
        print("  FIN DE PRUEBA DE TABLAS")
        print(f"{'=' * 70}\n")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# FUNCIÓN PARA MOSTRAR RESULTADOS DEL PIPELINE
# ============================================================

def mostrar_resultado(resultado):
    """Imprime el resultado del pipeline en formato legible."""

    print(f"\n{'=' * 70}")
    print("  RESULTADO")
    print(f"{'=' * 70}")

    print(f"  Éxito:            {resultado['exito']}")
    print(f"  Páginas:          {resultado['paginas']}")
    print(f"  Total procesados: {resultado['total_procesados']}/118")
    print(f"  Mensaje:          {resultado['mensaje']}")

    audit = resultado.get("audit", {})
    marcas = resultado.get("marcas", {})

    print(f"\n  Auditoría de marcas:")
    print(f"    Vacíos:       {len(audit.get('vacios', []))}")
    print(f"    Dobles:       {len(audit.get('ambos', []))}")
    print(f"    Solo 'No':    {len(audit.get('no', []))}")
    print(f"    Solo 'Sí':    {len(audit.get('si', []))}")

    # Mostrar primeros 5 de cada bloque
    print(f"\n  Estilos (E1..E33):")
    for i in range(1, 6):
        item = f"E{i}"
        if item in marcas:
            emoji = {"si": "✅", "no": "⬜", "ambos": "⚠️", "vacio": "❓"}.get(marcas[item], "?")
            print(f"    {item}: {emoji} {marcas[item]}")

    print(f"\n  Preferencias (P1..P47):")
    for i in range(1, 6):
        item = f"P{i}"
        if item in marcas:
            emoji = {"si": "✅", "no": "⬜", "ambos": "⚠️", "vacio": "❓"}.get(marcas[item], "?")
            print(f"    {item}: {emoji} {marcas[item]}")

    print(f"\n  Habilidad (H1..H38):")
    for i in range(1, 6):
        item = f"H{i}"
        if item in marcas:
            emoji = {"si": "✅", "no": "⬜", "ambos": "⚠️", "vacio": "❓"}.get(marcas[item], "?")
            print(f"    {item}: {emoji} {marcas[item]}")

    print(f"\n{'=' * 70}\n")


# ============================================================
# MAIN
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("❌ Uso: python test_rapido.py <ruta_al_pdf>")
        print("   Ejemplo: python test_rapido.py PRUEBA1.pdf")
        sys.exit(1)

    ruta_pdf = Path(sys.argv[1])

    if not ruta_pdf.exists():
        print(f"❌ No existe el archivo: {ruta_pdf}")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print("  PROBANDO PIPELINE OCR")
    print(f"  Archivo: {ruta_pdf}")
    print(f"  Tamaño:  {ruta_pdf.stat().st_size / 1024:.1f} KB")
    print(f"{'=' * 70}\n")

    # ========================================================
    # IMPORTAR PIPELINE
    # ========================================================
    try:
        from ocr.pipeline import procesar_formulario_pdf_con_timeout
    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        print("   Verifica que todos los módulos existan:")
        print("   - ocr/pipeline.py")
        print("   - ocr/tables.py")
        print("   - ocr/rows.py")
        print("   - ocr/marks.py")
        print("   - ocr/preprocess.py")
        print("   - ocr/pdf_to_image.py")
        print("   - vocacional/utils.py")
        sys.exit(1)

    # ========================================================
    # EJECUTAR PIPELINE
    # ========================================================
    print("⏳ Procesando...\n")

    try:
        resultado = procesar_formulario_pdf_con_timeout(str(ruta_pdf), timeout_seg=60)
    except Exception as e:
        print(f"❌ Error durante el procesamiento: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # ========================================================
    # MOSTRAR RESULTADOS
    # ========================================================
    mostrar_resultado(resultado)

    # Guardar JSON completo
    ruta_json = ruta_pdf.with_suffix(".resultado.json")
    try:
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2, default=str)
        print(f"  💾 Resultado completo guardado en: {ruta_json}")
    except Exception as e:
        print(f"  ⚠️ No se pudo guardar el JSON: {e}")


# ============================================================
# ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    main()