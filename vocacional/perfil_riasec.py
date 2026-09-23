"""
Convierte las marcas del test IEPPO a un perfil RIASEC normalizado.

El formulario IEPPO tiene 118 ítems distribuidos en 3 bloques:
  - E (Estilos personales): 33 ítems
  - P (Actividades de preferencia): 47 ítems
  - H (Percepción de habilidad): 38 ítems

Cada ítem está asociado a un área RIASEC (esto viene de la
documentación del instrumento IEPPO). Este módulo mapea cada ítem
a su área y calcula el score agregado por área.
"""

from typing import Dict, List

# Mapeo de ítem → área RIASEC.
# R=Realista, I=Investigador, A=Artístico, S=Social, E=Emprendedor, C=Convencional
#
# ⚠️ IMPORTANTE: Este mapeo tiene que venir del manual del IEPPO.
# Los valores aquí son PLACEHOLDER — reemplázalos con los reales.
# El orden de las claves importa: cada lista tiene ítems específicos.

MAPA_ITEMS_RIASEC: Dict[str, List[str]] = {
    "R": [
        # Ejemplo:
        "E6", "E7", "E8", "E30", "E31",
        "P5", "P6", "P12", "P15", "P18",
        "H9", "H10", "H11", "H14",
    ],
    "I": [
        "E9", "E10", "E11", "E12",
        "P7", "P8", "P9", "P13",
        "H1", "H2", "H3", "H4", "H5",
    ],
    "A": [
        "E13", "E14", "E15", "E16",
        "P10", "P11", "P14",
        "H6", "H7", "H8",
    ],
    "S": [
        "E1", "E2", "E3", "E4", "E5",
        "P1", "P2", "P3", "P4",
        "H12", "H13", "H15",
    ],
    "E": [
        "E17", "E18", "E19", "E20",
        "P19", "P20", "P21", "P22",
        "H16", "H17", "H18",
    ],
    "C": [
        "E21", "E22", "E23", "E24", "E25", "E26", "E27", "E28", "E29",
        "P23", "P24", "P25", "P26", "P27", "P28", "P29",
        "H19", "H20", "H21", "H22", "H23", "H24",
    ],
}


def marcas_a_perfil_riasec(marcas: Dict[str, str]) -> Dict[str, float]:
    """
    Convierte las marcas del test ({"E1": "si", ...}) a un perfil
    RIASEC con 6 valores entre 0 y 1.

    Args:
        marcas: dict con claves tipo "E1", "P23", "H38" y valores
                "si" | "no" | "vacio" | "ambos".

    Returns:
        {"R": 0-1, "I": 0-1, "A": 0-1, "S": 0-1, "E": 0-1, "C": 0-1}
    """
    conteo: Dict[str, int] = {"R": 0, "I": 0, "A": 0, "S": 0, "E": 0, "C": 0}
    total_por_area: Dict[str, int] = {"R": 0, "I": 0, "A": 0, "S": 0, "E": 0, "C": 0}

    for area, items in MAPA_ITEMS_RIASEC.items():
        for item in items:
            total_por_area[area] += 1
            valor = marcas.get(item, "vacio")
            # "si" y "ambos" cuentan como marcado, el resto no
            if valor in ("si", "ambos"):
                conteo[area] += 1

    # Normaliza 0-1 (evita división por cero si algún área no tiene ítems)
    perfil = {}
    for area in ("R", "I", "A", "S", "E", "C"):
        total = total_por_area[area]
        perfil[area] = conteo[area] / total if total > 0 else 0.0

    return perfil