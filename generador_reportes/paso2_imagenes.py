# paso2_imagenes.py
import pymupdf as fitz

doc = fitz.open("plantilla_original_reparada.pdf")
for i, pagina in enumerate(doc):
    mat = fitz.Matrix(2, 2)   # 2x → más resolución
    pix = pagina.get_pixmap(matrix=mat)
    nombre = f"pagina_{i+1}.png"
    pix.save(nombre)
    print(f"✅ {nombre} ({pix.width} x {pix.height} px)")
doc.close()
print("\n👉 Ahora abre estos PNG en Paint y márcalos con los colores indicados.")