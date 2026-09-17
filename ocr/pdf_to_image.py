import io
import logging
from typing import Union, List
import numpy as np
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

def pdf_a_imagenes(pdf_source: Union[str, bytes, io.BytesIO], dpi: int = 300) -> List[np.ndarray]:
    """
    Convierte las páginas de un archivo PDF a una lista de imágenes OpenCV (BGR, numpy array).
    
    pdf_source: ruta a archivo (str), contenido en bytes o BytesIO/UploadedFile de Streamlit.
    dpi: resolución deseada (por defecto 300 DPI para alta precisión en OCR de marcas).
    """
    imagenes = []
    zoom = dpi / 72.0  # 72 dpi es la resolución estándar de PDF
    mat = fitz.Matrix(zoom, zoom)
    
    try:
        if isinstance(pdf_source, str):
            doc = fitz.open(pdf_source)
        elif isinstance(pdf_source, bytes):
            doc = fitz.open(stream=pdf_source, filetype="pdf")
        elif hasattr(pdf_source, "read"):
            # Objeto tipo BytesIO o UploadedFile de Streamlit
            pdf_bytes = pdf_source.read()
            # Reiniciar cursor por si se vuelve a leer
            if hasattr(pdf_source, "seek"):
                pdf_source.seek(0)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        else:
            raise ValueError("Formato de pdf_source no soportado.")
        
        for num_pag in range(len(doc)):
            pagina = doc[num_pag]
            pix = pagina.get_pixmap(matrix=mat, alpha=False)
            
            # Convertir buffer de pixmap a numpy array
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            
            # Si tiene 3 canales, PyMuPDF entrega RGB -> convertir a BGR para OpenCV
            if pix.n == 3:
                import cv2
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pix.n == 1:
                import cv2
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                
            imagenes.append(img)
            
        doc.close()
    except Exception as e:
        logger.error("Error al convertir PDF a imágenes: %s", e)
        raise
        
    return imagenes
