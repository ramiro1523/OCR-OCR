# perfilar_ocr.py
"""
Perfila el pipeline OCR paso a paso para encontrar cuellos de botella.

NO modifica nada. Solo mide.
"""
import cProfile
import io
import os
import pstats
import time


PDF_PRUEBA = "James-Ramos-Legui_16_M.pdf"
ITERACIONES = 3


def perfil_completo():
    """Perfila el pipeline completo con cProfile."""
    from pipeline_vocacional import procesar_alumno

    print("=" * 70)
    print("PERFILADO DEL PIPELINE OCR")
    print("=" * 70)
    print(f"\nPDF: {PDF_PRUEBA}")
    print(f"Iteraciones: {ITERACIONES}\n")

    if not os.path.exists(PDF_PRUEBA):
        print(f"❌ No existe: {PDF_PRUEBA}")
        return

    # Crear el profiler
    pr = cProfile.Profile()

    # Ejecutar
    pr.enable()
    for i in range(ITERACIONES):
        print(f"  Iteración {i+1}/{ITERACIONES}...", end=" ", flush=True)
        t0 = time.perf_counter()
        procesar_alumno(PDF_PRUEBA, sexo="M")
        t1 = time.perf_counter()
        print(f"{t1-t0:.2f}s")
    pr.disable()

    # Analizar resultados
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(30)   # Top 30 funciones

    print("\n" + "=" * 70)
    print("TOP 30 FUNCIONES POR TIEMPO ACUMULADO")
    print("=" * 70)
    print(s.getvalue())


def perfil_etapas():
    """
    Mide el tiempo de cada etapa por separado.
    NO importa el pipeline completo, solo las funciones clave.
    """
    import numpy as np
    import pymupdf as fitz
    from ocr.preprocess import preprocesar_imagen, binarizar
    from ocr.tables import detectar_3_tablas_geometria
    from ocr.rows import obtener_filas_y_columnas_tabla

    print("\n" + "=" * 70)
    print("PERFILADO POR ETAPAS")
    print("=" * 70)

    if not os.path.exists(PDF_PRUEBA):
        print(f"❌ No existe: {PDF_PRUEBA}")
        return

    # ─── Etapa 0: PDF → imagen ───
    print("\n[Etapa 0] PDF → imagen (300 DPI)")
    t0 = time.perf_counter()
    doc = fitz.open(PDF_PRUEBA)
    pagina = doc[0]
    mat = fitz.Matrix(300/72, 300/72)
    pix = pagina.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width
    )
    doc.close()
    t1 = time.perf_counter()
    print(f"  Tiempo: {t1-t0:.3f}s | Tamaño: {img.shape}")

    # ─── Etapa 1: Preprocesamiento ───
    print("\n[Etapa 1] Preprocesamiento (binarización)")
    t0 = time.perf_counter()
    prep = preprocesar_imagen(img, metodo_binarizacion="otsu")
    t1 = time.perf_counter()
    print(f"  Tiempo: {t1-t0:.3f}s")

    # ─── Etapa 2: Detección de tablas ───
    print("\n[Etapa 2] Detección de 3 tablas")
    t0 = time.perf_counter()
    tablas = detectar_3_tablas_geometria(prep["binaria"])
    t1 = time.perf_counter()
    print(f"  Tiempo: {t1-t0:.3f}s | Tablas detectadas: {len(tablas)}")

    # ─── Etapa 3: Filas y columnas ───
    if tablas:
        print("\n[Etapa 3] Detección de filas/columnas")
        t0 = time.perf_counter()
        try:
            filas, x_cortes = obtener_filas_y_columnas_tabla(tablas[0], 33)
            t1 = time.perf_counter()
            print(f"  Tiempo: {t1-t0:.3f}s | Filas: {len(filas)}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    print("\n" + "▶" * 35)
    print("  PERFILADO COMPLETO (cProfile)")
    print("▶" * 35)
    perfil_completo()

    print("\n\n" + "▶" * 35)
    print("  PERFILADO POR ETAPAS")
    print("▶" * 35)
    perfil_etapas()