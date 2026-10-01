# benchmark_optimizado.py
"""
Verifica que el optimizador produce el MISMO resultado
y mide la diferencia de velocidad.
"""

import os
import statistics
import time


PDF_PRUEBA = "James-Ramos-Legui_16_M.pdf"
ITERACIONES = 3


def comparar():
    print("=" * 70)
    print("COMPARACIÓN: PIPELINE ORIGINAL vs OPTIMIZADO")
    print("=" * 70)

    if not os.path.exists(PDF_PRUEBA):
        print(f"❌ No existe: {PDF_PRUEBA}")
        return

    # ─── Pipeline original ───
    print("\n[1/2] Pipeline ORIGINAL...")
    from pipeline_vocacional import procesar_alumno

    tiempos_original = []
    resultado_original = None

    for i in range(ITERACIONES):
        print(f"  Iteración {i+1}/{ITERACIONES}...", end=" ", flush=True)
        t0 = time.perf_counter()
        r = procesar_alumno(PDF_PRUEBA, sexo="M")
        t1 = time.perf_counter()
        tiempos_original.append(t1 - t0)
        if resultado_original is None:
            resultado_original = r
        print(f"{t1-t0:.2f}s")

    # ─── Pipeline optimizado ───
    print("\n[2/2] Pipeline OPTIMIZADO...")
    import optimizador_ocr
    optimizador_ocr.limpiar_cache()   # limpiar antes de medir
    from optimizador_ocr import procesar_alumno_optimizado

    tiempos_optimizado = []
    resultado_optimizado = None

    for i in range(ITERACIONES):
        print(f"  Iteración {i+1}/{ITERACIONES}...", end=" ", flush=True)
        t0 = time.perf_counter()
        r = procesar_alumno_optimizado(PDF_PRUEBA, sexo="M")
        t1 = time.perf_counter()
        tiempos_optimizado.append(t1 - t0)
        if resultado_optimizado is None:
            resultado_optimizado = r
        print(f"{t1-t0:.2f}s")

    # ─── Comparar resultados ───
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: ¿Mismo resultado?")
    print("=" * 70)

    iguales = True
    claves = [
        "puntajes_directos", "niveles", "areas_top",
        "carreras_top", "potencial",
    ]
    for clave in claves:
        v_orig = resultado_original.get(clave)
        v_opt = resultado_optimizado.get(clave)
        if v_orig == v_opt:
            print(f"  ✅ {clave}: IDÉNTICO")
        else:
            print(f"  ❌ {clave}: DIFERENTE")
            print(f"      Original:    {v_orig}")
            print(f"      Optimizado:  {v_opt}")
            iguales = False

    # ─── Comparar tiempos ───
    print("\n" + "=" * 70)
    print("TIEMPOS")
    print("=" * 70)

    prom_orig = statistics.mean(tiempos_original)
    prom_opt = statistics.mean(tiempos_optimizado)
    mejora = (1 - prom_opt / prom_orig) * 100

    print(f"\n  Original:      {prom_orig:.2f}s (promedio de {ITERACIONES})")
    print(f"  Optimizado:    {prom_opt:.2f}s (promedio de {ITERACIONES})")
    print(f"  Mejora:        {mejora:+.1f}%")
    print(f"  Factor:        {prom_orig / prom_opt:.2f}x más rápido")

    print("\n" + "=" * 70)
    if iguales:
        print("✅ RESULTADO IDÉNTICO — puedes usar el optimizador")
    else:
        print("❌ RESULTADO DIFERENTE — NO usar el optimizador")
    print("=" * 70)


if __name__ == "__main__":
    comparar()