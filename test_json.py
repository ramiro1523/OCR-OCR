import json
from pathlib import Path

ruta = Path("vocacional/data/catalogo_carreras.json")
print(f"Existe: {ruta.exists()}")

if ruta.exists():
    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    print(f"Carreras cargadas: {len(data['carreras'])}")
    for c in data["carreras"][:5]:
        print(f"  - {c['nombre']}")
    print("  ...")