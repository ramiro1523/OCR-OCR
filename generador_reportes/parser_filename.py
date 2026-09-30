# parser_filename.py
"""
Extrae nombre, edad y sexo del nombre del archivo PDF.
Formato: nombre-apellido_edad_sexo.pdf
Ejemplo: ana-rozas-hucho_16_F.pdf
"""
import re
from pathlib import Path


def parsear_filename(nombre_archivo: str) -> dict:
    """
    Devuelve:
        {"nombre": "Ana Rozas Hucho", "edad": "16", "sexo": "F"}
    
    Lanza ValueError si el formato es incorrecto.
    """
    base = Path(nombre_archivo).stem

    # Patrón: nombre_edad_sexo
    patron = r"^(.+?)[_\-\s]+(\d{1,2})[_\-\s]+([FfMm])$"
    match = re.match(patron, base)

    if not match:
        raise ValueError(
            f"❌ Formato inválido: {nombre_archivo}\n"
            f"   Esperado: nombre-apellido_edad_sexo.pdf\n"
            f"   Ejemplo:  ana-rozas-hucho_16_F.pdf"
        )

    nombre_crudo, edad, sexo = match.groups()

    # "ana-rozas-hucho" → "Ana Rozas Hucho"
    nombre = nombre_crudo.replace("-", " ").replace("_", " ")
    nombre = " ".join(p.capitalize() for p in nombre.split())

    return {
        "nombre": nombre,
        "edad": edad,
        "sexo": sexo.upper(),
    }


if __name__ == "__main__":
    ejemplos = [
        "ana-rozas-hucho_16_F.pdf",
        "luis_perez_15_M.pdf",
        "maria-jose-lopez_17_F.PDF",
    ]
    for e in ejemplos:
        try:
            print(f"{e:35s} → {parsear_filename(e)}")
        except ValueError as err:
            print(f"{e:35s} → ERROR: {err}")