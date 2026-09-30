# test_conexion.py
import os
import glob
from pipeline_vocacional import procesar_alumno

# ─── Buscar un PDF automáticamente ───
CARPETAS_BUSQUEDA = ["..", ".", "../ocr", "../pdfs", "pdfs"]
patrones = []
for carpeta in CARPETAS_BUSQUEDA:
    patrones.append(os.path.join(carpeta, "*.pdf"))

pdfs_encontrados = []
for patron in patrones:
    pdfs_encontrados.extend(glob.glob(patron))

if not pdfs_encontrados:
    print("❌ No se encontró ningún PDF en las carpetas cercanas.")
    print("Coloca un PDF en la carpeta 'generador_Reportes/' o en la raíz del proyecto.")
    exit(1)

print("PDFs encontrados:")
for i, p in enumerate(pdfs_encontrados, 1):
    print(f"  [{i}] {p}")

# Usar el primero (o pide al usuario)
RUTA = pdfs_encontrados[0]
print(f"\n▶ Usando: {RUTA}\n")

# Extraer sexo del nombre si sigue el patrón
nombre = os.path.basename(RUTA).upper()
SEXO = "F"
if "_M." in nombre or nombre.endswith("_M"):
    SEXO = "M"
elif "_F." in nombre or nombre.endswith("_F"):
    SEXO = "F"
print(f"▶ Sexo detectado del nombre: {SEXO}\n")

# ─── Procesar ───
try:
    resultado = procesar_alumno(RUTA, sexo=SEXO)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("=" * 60)
print("PUNTAJES DIRECTOS:")
for k, v in resultado["puntajes_directos"].items():
    print(f"  {k:25s} PD={v}")

print("\nNIVELES:")
for k, v in resultado["niveles"].items():
    print(f"  {k:25s} → {v}")

print(f"\nPOTENCIAL: {resultado['potencial']}")
print(f"ÁREAS TOP: {resultado['areas_top']}")
print(f"CARRERAS TOP: {resultado['carreras_top']}")
print(f"TOTAL PROCESADOS: {resultado['total_procesados']}/118")
print("=" * 60)