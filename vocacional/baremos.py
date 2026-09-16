import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "baremos_mujeres.json", encoding="utf-8") as f:
    BAREMOS_M = json.load(f)

with open(DATA_DIR / "baremos_varones.json", encoding="utf-8") as f:
    BAREMOS_V = json.load(f)


def calcular_baremos(puntajes: dict, sexo: str) -> dict:
    """
    Aplica la tabla de conversión según sexo.
    
    puntajes: {"LIDERAZGO": {"PD": 6, ...}, ...}
    sexo: "M" o "F"
    
    Retorna: {
      "LIDERAZGO": {"PD": 6, "Baremo": 42},
      ...
    }
    """
    if sexo not in ("M", "F"):
        raise ValueError("Sexo debe ser 'M' o 'F'")
    
    tabla = BAREMOS_V if sexo == "M" else BAREMOS_M
    resultado = {}
    
    for tipo, datos in puntajes.items():
        pd = datos["PD"]
        tabla_tipo = tabla.get(tipo, [])
        
        if pd < len(tabla_tipo) and tabla_tipo[pd] is not None:
            baremo = tabla_tipo[pd]
        else:
            baremo = None  # PD no posible para ese tipo
        
        resultado[tipo] = {
            "PD": pd,
            "Baremo": baremo
        }
    
    return resultado