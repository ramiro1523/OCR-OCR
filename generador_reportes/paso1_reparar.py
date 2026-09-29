# paso1_reparar.py
import pymupdf as fitz
import os

ENTRADA = "plantilla_original.pdf"
SALIDA = "plantilla_original_reparada.pdf"

print("Leyendo:", ENTRADA, os.path.getsize(ENTRADA), "bytes")
doc = fitz.open(ENTRADA)
print("Paginas:", doc.page_count)
doc.save(SALIDA, garbage=3, deflate=True, clean=True)
doc.close()
print("Generado:", SALIDA, os.path.getsize(SALIDA), "bytes")