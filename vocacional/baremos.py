import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "baremos_mujeres.json", encoding="utf-8") as f:
    BAREMOS_M = json.load(f)

varones_file = DATA_DIR / "baremos_varones.json"
if not varones_file.exists():
    varones_file = DATA_DIR / "baremos_hombres.json"

with open(varones_file, encoding="utf-8") as f:
    BAREMOS_V = json.load(f)


def calcular_baremos(puntajes: dict, sexo: str) -> dict:
    """
    Aplica la tabla de conversión según sexo ('M' para varones, 'F' para mujeres).
    
    puntajes: {"LIDERAZGO": {"PD": 6, ...}, ...}
    sexo: "M" o "F"
    
    Retorna: {
      "LIDERAZGO": {"PD": 6, "Baremo": 42},
      ...
    }
    """
    sexo_clean = str(sexo).strip().upper()
    if sexo_clean not in ("M", "F"):
        raise ValueError(f"Sexo debe ser 'M' o 'F', recibido: '{sexo}'")
    
    tabla = BAREMOS_V if sexo_clean == "M" else BAREMOS_M
    resultado = {}
    
    for tipo, datos in puntajes.items():
        pd = datos["PD"] if isinstance(datos, dict) and "PD" in datos else int(datos)
        tabla_tipo = tabla.get(tipo, [])
        
        if 0 <= pd < len(tabla_tipo) and tabla_tipo[pd] is not None:
            baremo = tabla_tipo[pd]
        else:
            baremo = None  # PD no posible o fuera de rango para ese tipo
        
        resultado[tipo] = {
            "PD": pd,
            "Baremo": baremo
        }
    
    return resultado