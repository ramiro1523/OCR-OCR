import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "division_items.json", encoding="utf-8") as f:
    DIVISION = json.load(f)


def calcular_pd(marcas: dict) -> dict:
    """
    Calcula el Puntaje Directo por tipo vocacional.
    
    marcas: {
      "E1": "si"|"no"|"ambos"|"vacio",
      "E2": ...,
      "P1": ..., "H1": ...
    }
    
    Retorna: {
      "LIDERAZGO": {"E": 3, "P": 0, "H": 3, "PD": 6},
      ...
    }
    """
    resultado = {}
    
    for tipo, bloques in DIVISION.items():
        suma_e = contar_si(marcas, bloques["E"])
        suma_p = contar_si(marcas, bloques["P"])
        suma_h = contar_si(marcas, bloques["H"])
        
        resultado[tipo] = {
            "E": suma_e,
            "P": suma_p,
            "H": suma_h,
            "PD": suma_e + suma_p + suma_h
        }
    
    return resultado

def contar_si(marcas: dict, items: list) -> int:
    """
    Cuenta cuántos ítems tienen marca "Sí".
    
    Reglas:
      - "Sí"    → 1 punto
      - "No"    → 0 puntos
      - "Ambos" → 0 puntos
      - Vacío    → 0 puntos
    """
    total = 0

    for item in items:
        estado = marcas.get(item, "vacio")
        if estado == "si":
            total += 1

    return total
