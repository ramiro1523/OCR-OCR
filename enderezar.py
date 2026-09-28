from pypdf import PdfReader, PdfWriter, Transformation

def enderezar_pdf(ruta_entrada, ruta_salida, grados):
    reader = PdfReader(ruta_entrada)
    writer = PdfWriter()

    for page in reader.pages:
        # Obtener el ancho y alto de la página para rotar sobre el centro
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        
        # Secuencia matemática: Mover al centro -> Rotar -> Mover a la posición original
        transform = (
            Transformation()
            .translate(-w/2, -h/2)
            .rotate(grados)
            .translate(w/2, h/2)
        )
        
        # Aplicar la rotación
        page.add_transformation(transform)
        writer.add_page(page)

    # Guardar el PDF corregido
    with open(ruta_salida, "wb") as archivo_salida:
        writer.write(archivo_salida)

# 1. Ruta del archivo original en tus Descargas
ruta_original = r"C:\Users\danil\Downloads\PDF_MUESTRA.pdf"

# 2. Ruta donde aparecerá el archivo enderezado
ruta_corregido = r"C:\Users\danil\Downloads\documento_corregido.pdf"

# 3. Ángulo de rotación (puedes cambiar el 3.5 por el número que necesites, incluso negativos como -2.0)
angulo = 3.5

print("Enderezando el documento...")
enderezar_pdf(ruta_original, ruta_corregido, angulo)
print(f"¡Listo! El PDF se guardó correctamente en: {ruta_corregido}")