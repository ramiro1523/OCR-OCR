# paso1_reparar.py
import pymupdf as fitz
import os

ENTRADA = "plantilla_original.pdf"      # ← tu PDF original limpio
SALIDA = "plantilla_original_reparada.pdf"

print(f"📄 Leyendo: {ENTRADA} ({os.path.getsize(ENTRADA)} bytes)")
doc = fitz.open(ENTRADA)
print(f"   Páginas: {doc.page_count}")
doc.save(SALIDA, garbage=3, deflate=True, clean=True)
doc.close()
print(f"✅ Generado: {SALIDA} ({os.path.getsize(SALIDA)} bytes)")