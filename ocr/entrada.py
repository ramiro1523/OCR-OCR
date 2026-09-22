"""
Capa de entrada unificada para el pipeline OCR IEPPO.

Acepta:
  - PDF (renderiza a DPI configurable, una imagen por página).
  - JPG / JPEG / PNG / BMP / TIFF / TIF / WEBP (carga directa).
  - Cualquiera de los anteriores como: ruta (str/Path), bytes o
    file-like object (BytesIO, archivo abierto en modo 'rb').
  - np.ndarray ya en memoria (por si un caller ya tiene la imagen).

Devuelve SIEMPRE una lista de imágenes en escala de grises (uint8, 2D),
para que el resto del pipeline no tenga que distinguir el origen.
"""

import io
import logging
from pathlib import Path
from typing import List, Optional, Union

import cv2
import numpy as np

from ocr.pdf_to_image import pdf_a_imagenes

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

EXTENSIONES_IMAGEN = {
    ".jpg", ".jpeg", ".png", ".bmp",
    ".tif", ".tiff", ".webp",
}

# Magic bytes para detección robusta cuando no hay extensión
_MAGIC_PDF = b"%PDF"
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_BMP = b"BM"
_MAGIC_TIFF_LE = b"II*\x00"
_MAGIC_TIFF_BE = b"MM\x00*"
_MAGIC_RIFF = b"RIFF"
_MAGIC_WEBP = b"WEBP"


# =============================================================================
# DETECCIÓN DE TIPO
# =============================================================================

def _leer_magic_bytes(fuente, n: int = 16) -> Optional[bytes]:
    """
    Lee los primeros n bytes de la fuente sin consumirla si es file-like.
    Devuelve None si no se puede leer.
    """
    try:
        if isinstance(fuente, (str, Path)):
            with open(fuente, "rb") as f:
                return f.read(n)

        if isinstance(fuente, (bytes, bytearray)):
            return bytes(fuente[:n])

        if hasattr(fuente, "read"):
            pos = None
            if hasattr(fuente, "tell"):
                try:
                    pos = fuente.tell()
                except Exception:
                    pos = None

            data = fuente.read(n)
            if isinstance(data, str):
                data = data.encode("latin-1", errors="ignore")

            if pos is not None and hasattr(fuente, "seek"):
                try:
                    fuente.seek(pos)
                except Exception:
                    pass

            return data

    except Exception as e:
        logger.warning("No se pudieron leer magic bytes: %s", e)

    return None


def _detectar_tipo(fuente) -> str:
    """
    Devuelve 'pdf', 'imagen' o 'desconocido'.
    Primero por extensión, si aplica; luego por magic bytes.
    """
    # 1. Por extensión (si es path)
    if isinstance(fuente, (str, Path)):
        ext = Path(fuente).suffix.lower()
        if ext == ".pdf":
            return "pdf"
        if ext in EXTENSIONES_IMAGEN:
            return "imagen"

    # 2. Por magic bytes
    magic = _leer_magic_bytes(fuente)
    if magic is None:
        return "desconocido"

    if magic.startswith(_MAGIC_PDF):
        return "pdf"
    if magic.startswith(_MAGIC_JPEG):
        return "imagen"
    if magic.startswith(_MAGIC_PNG):
        return "imagen"
    if magic.startswith(_MAGIC_BMP):
        return "imagen"
    if magic.startswith(_MAGIC_TIFF_LE) or magic.startswith(_MAGIC_TIFF_BE):
        return "imagen"
    if len(magic) >= 12 and magic[:4] == _MAGIC_RIFF and magic[8:12] == _MAGIC_WEBP:
        return "imagen"

    return "desconocido"


# =============================================================================
# CARGA DE IMAGEN
# =============================================================================

def _bytes_a_array(fuente) -> np.ndarray:
    """
    Convierte la fuente (path, bytes, file-like) a un np.ndarray
    BGR (o gris, según el contenido). Lanza si no se puede decodificar.
    """
    if isinstance(fuente, (str, Path)):
        data = np.fromfile(str(fuente), dtype=np.uint8)

    elif isinstance(fuente, (bytes, bytearray)):
        data = np.frombuffer(bytes(fuente), dtype=np.uint8)

    elif hasattr(fuente, "read"):
        raw = fuente.read()
        if isinstance(raw, str):
            raw = raw.encode("latin-1", errors="ignore")
        data = np.frombuffer(raw, dtype=np.uint8)

    else:
        raise ValueError(f"Tipo de fuente no soportado: {type(fuente)}")

    if data.size == 0:
        raise ValueError("La fuente está vacía (0 bytes).")

    # cv2.imdecode autodetecta el formato (JPEG, PNG, BMP, TIFF, WEBP…)
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("cv2.imdecode no pudo decodificar la imagen.")

    return img


def _normalizar_a_gris(img: np.ndarray) -> np.ndarray:
    """Convierte cualquier imagen (BGR, BGRA, gris, 16-bit) a uint8 gris."""
    if img is None or img.size == 0:
        raise ValueError("Imagen vacía en normalización.")

    # 16-bit → 8-bit
    if img.dtype == np.uint16:
        img = (img / 256.0).astype(np.uint8)
    elif img.dtype != np.uint8:
        img = img.astype(np.uint8)

    if len(img.shape) == 2:
        return img

    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.shape[2] == 1:
        return img[:, :, 0]

    raise ValueError(f"Canales no soportados: {img.shape}")


# =============================================================================
# API PÚBLICA
# =============================================================================

def cargar_formulario(
    fuente: Union[str, Path, bytes, bytearray, io.IOBase, np.ndarray],
    dpi: int = 300,
) -> List[np.ndarray]:
    """
    Carga un formulario desde cualquier fuente soportada.

    Args:
        fuente: ruta (str/Path), bytes, file-like (abierto en 'rb')
                o np.ndarray ya en memoria.
        dpi: resolución a la que renderizar PDFs. Se ignora para
             imágenes (una imagen no tiene DPI "real").

    Returns:
        Lista de imágenes en escala de grises (uint8, 2D).
        - PDF con N páginas → N imágenes.
        - Imagen suelta     → 1 imagen.

    Raises:
        ValueError si el formato no está soportado o el archivo está dañado.
    """
    # Caso especial: ya es un ndarray en memoria
    if isinstance(fuente, np.ndarray):
        logger.info("Entrada: np.ndarray in-memory, shape=%s", fuente.shape)
        return [_normalizar_a_gris(fuente)]

    tipo = _detectar_tipo(fuente)
    logger.info("Formato detectado: %s", tipo)

    # -------------------------------------------------------------------------
    # PDF
    # -------------------------------------------------------------------------
    if tipo == "pdf":
        try:
            imagenes = pdf_a_imagenes(fuente, dpi=dpi)
        except Exception as e:
            logger.error("Error renderizando PDF: %s", e, exc_info=True)
            raise ValueError(f"El PDF está dañado o no se pudo renderizar: {e}")

        resultado = []
        for idx, img in enumerate(imagenes):
            try:
                gris = _normalizar_a_gris(img)
                resultado.append(gris)
            except Exception as e:
                logger.warning("Página %d del PDF no se pudo normalizar: %s", idx, e)

        if not resultado:
            raise ValueError("El PDF no produjo ninguna página válida.")

        logger.info("PDF cargado: %d página(s) a %d DPI.", len(resultado), dpi)
        return resultado

    # -------------------------------------------------------------------------
    # Imagen (JPG, PNG, BMP, TIFF, WEBP)
    # -------------------------------------------------------------------------
    if tipo == "imagen":
        try:
            img = _bytes_a_array(fuente)
        except Exception as e:
            logger.error("Error decodificando imagen: %s", e, exc_info=True)
            raise ValueError(f"La imagen está dañada o no se pudo decodificar: {e}")

        gris = _normalizar_a_gris(img)
        logger.info(
            "Imagen cargada: shape original=%s, gris shape=%s",
            img.shape, gris.shape,
        )
        return [gris]

    # -------------------------------------------------------------------------
    # No soportado
    # -------------------------------------------------------------------------
    raise ValueError(
        "Formato no soportado. Acepta PDF, JPG, JPEG, PNG, BMP, TIFF y WEBP."
    )