# benchmark_ocr.py
"""
Mide el tiempo REAL del pipeline completo (OCR + cálculo + PDF)
por cada alumno procesado.
"""
import os
import time
import statistics
from pipeline_vocacional import procesar_alumno
from motor_pdf import generar_pdf
import tempfile


# ─── Configura tus PDFs de prueba ───
PDFS_PRUEBA = [
    "James-Ramos-Legui_16_M.pdf",   # ajusta a tus nombres
    # "otro_alumno_15_F.pdf",
    # "otro_mas_17_M.pdf",
]

# ─── Iteraciones ───
ITERACIONES = 20   # cada PDF se procesará N veces


def benchmark_pipeline():
    print("=" * 70)
    print("BENCHMARK DEL PIPELINE COMPLETO")
    print("=" * 70)

    # Verificar archivos
    faltantes = [p for p in PDFS_PRUEBA if not os.path.exists(p)]
    if faltantes:
        print("❌ Faltan archivos:")
        for f in faltantes:
            print(f"   - {f}")
        return

    print(f"\nPDFs de prueba: {len(PDFS_PRUEBA)}")
    print(f"Iteraciones por PDF: {ITERACIONES}")
    print(f"Total ejecuciones: {len(PDFS_PRUEBA) * ITERACIONES}\n")

    tiempos_ocr = []
    tiempos_pdf = []
    tiempos_total = []

    total_iter = len(PDFS_PRUEBA) * ITERACIONES
    contador = 0

    for ruta in PDFS_PRUEBA:
        sexo = "F" if "_F" in ruta else "M"
        print(f"▶ {ruta} (sexo={sexo})")

        for i in range(ITERACIONES):
            contador += 1
            print(f"  [{contador}/{total_iter}]", end=" ", flush=True)

            # ─── Etapa 1: OCR + cálculo ───
            t0 = time.perf_counter()
            try:
                resultado = procesar_alumno(ruta, sexo=sexo)
            except Exception as e:
                print(f"❌ Error OCR: {e}")
                continue
            t1 = time.perf_counter()

            # ─── Etapa 2: generar PDF ───
            datos_pdf = {
                "campo_nombre": resultado.get("nombre", "Test"),
                "campo_edad": "16",
                "campo_genero": sexo,
                "campo_fecha": "01/10/2026",
                "campo_grado_instruccion": "5",
                "campo_grado": "COMPLETA",
                "campo_colegio": "SANTO DOMINGO DE PANGOA",
                "niveles": resultado["niveles"],
                "potencial_puesto": resultado["potencial"],
                "campo_areas": resultado["areas_top"][0].upper() if resultado["areas_top"] else "",
                "campo_areas_2": resultado["areas_top"][1].upper() if len(resultado["areas_top"]) > 1 else "",
                "campo_carreras": resultado["carreras_top"][0].upper() if resultado["carreras_top"] else "",
                "campo_carreras_2": resultado["carreras_top"][1].upper() if len(resultado["carreras_top"]) > 1 else "",
            }

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                ruta_tmp = tmp.name

            t2 = time.perf_counter()
            try:
                generar_pdf(datos_pdf, ruta_salida=ruta_tmp)
            except Exception as e:
                print(f"❌ Error PDF: {e}")
                try:
                    os.remove(ruta_tmp)
                except:
                    pass
                continue
            t3 = time.perf_counter()

            try:
                os.remove(ruta_tmp)
            except:
                pass

            # Guardar tiempos
            tiempos_ocr.append(t1 - t0)
            tiempos_pdf.append(t3 - t2)
            tiempos_total.append(t3 - t0)

            print(f"OCR={t1-t0:.2f}s PDF={t3-t2:.3f}s Total={t3-t0:.2f}s")

    # ─── Resumen final ───
    if not tiempos_total:
        print("\n❌ No se pudo procesar ningún PDF.")
        return

    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    def mostrar_stats(nombre, tiempos):
        if not tiempos:
            return
        print(f"\n{nombre}:")
        print(f"  Ejecuciones:  {len(tiempos)}")
        print(f"  Promedio:     {statistics.mean(tiempos):.3f}s")
        print(f"  Mediana:      {statistics.median(tiempos):.3f}s")
        print(f"  Mínimo:       {min(tiempos):.3f}s")
        print(f"  Máximo:       {max(tiempos):.3f}s")
        if len(tiempos) >= 2:
            print(f"  Desv. std:    {statistics.stdev(tiempos):.3f}s")

    mostrar_stats("OCR + Cálculo vocacional", tiempos_ocr)
    mostrar_stats("Generación de PDF", tiempos_pdf)
    mostrar_stats("Pipeline completo (OCR + PDF)", tiempos_total)

    # ─── Estimación de concurrencia ───
    print("\n" + "=" * 70)
    print("ESTIMACIÓN DE CONCURRENCIA")
    print("=" * 70)
    promedio = statistics.mean(tiempos_total)
    print(f"\nTiempo promedio por alumno: {promedio:.2f}s")

    for workers in [1, 2, 3, 4, 6, 8]:
        throughput = workers / promedio
        print(f"  {workers} worker(s): ~{throughput:.2f} PDFs/segundo")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    benchmark_pipeline()