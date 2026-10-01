# test_debug.py
"""
Prueba el pipeline CON DEBUG activado.
Muestra paso a paso qué está haciendo.
"""
import sys
import os
from pipeline_vocacional import procesar_alumno


# ─── Configura el PDF a probar ───
RUTA = "enzo-jimenez-rodriguez_16_M.pdf"   # ← cambia al nombre real
SEXO = "M"                         # ← o "M"


if not os.path.exists(RUTA):
    print(f"❌ No existe: {RUTA}")
    print("   Pon un PDF real con ese nombre en la carpeta.")
    sys.exit(1)

# Ejecutar con debug=True
resultado = procesar_alumno(RUTA, sexo=SEXO, debug=True)

# ─── Resumen final ───
print("\n" + "═" * 60)
print("RESUMEN FINAL PARA EL PDF")
print("═" * 60)
print(f"Puntajes:  {resultado['puntajes_directos']}")
print(f"Niveles:   {resultado['niveles']}")
print(f"Áreas:     {resultado['areas_top']}")
print(f"Carreras:  {resultado['carreras_top']}")
print(f"Potencial: {resultado['potencial']}")
print(f"Total:     {resultado['total_procesados']}/118")
print("═" * 60)