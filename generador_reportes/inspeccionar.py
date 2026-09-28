# inspeccionar.py
from pypdf import PdfReader

reader = PdfReader("plantilla_formulario.pdf")
campos = reader.get_fields() or {}

print(f"📋 Total: {len(campos)} campos\n")
for nombre in sorted(campos.keys()):
    print(f"  - {nombre}")