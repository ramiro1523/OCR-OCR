# verificar_colores.py
from pypdf import PdfReader

reader = PdfReader("salidas/Ana_García_López_20260928_112914.pdf")

print("Campos y sus colores de fondo (BG):")
for page in reader.pages:
    if "/Annots" not in page:
        continue
    for annot in page["/Annots"]:
        obj = annot.get_object()
        nombre = obj.get("/T", "?")
        bg = obj.get("/MK", {}).get("/BG", "sin fondo")
        print(f"  {nombre:30s}  BG={bg}")