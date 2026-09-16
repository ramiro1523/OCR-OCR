import json
from pathlib import Path
from itertools import product

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "carreras.json", encoding="utf-8") as f:
    CARRERAS = json.load(f)

with open(DATA_DIR / "afinidad.json", encoding="utf-8") as f:
    AFINIDAD = json.load(f)


# ─────────────────────────────────────────────
# ÍNDICES PRE-CALCULADOS (para velocidad)
# ─────────────────────────────────────────────

def _construir_indice_grupos():
    """Carrera → lista de grupos a los que pertenece."""
    indice = {}
    for grupo, data in AFINIDAD["grupos"].items():
        for carrera in data["carreras"]:
            indice.setdefault(carrera, []).append(grupo)
    return indice


def _construir_indice_tipos():
    """Carrera → tipo vocacional al que pertenece (el primero que la contenga)."""
    indice = {}
    for tipo, carreras in CARRERAS.items():
        for carrera in carreras:
            indice.setdefault(carrera, []).append(tipo)
    return indice


def _construir_indice_reglas():
    """Par ordenado (a,b) → True si hay regla especial."""
    indice = set()
    for regla in AFINIDAD["reglas_especiales"]:
        a, b = regla["par"]
        indice.add((a, b))
        indice.add((b, a))
    return indice


INDICE_GRUPOS = _construir_indice_grupos()
INDICE_TIPOS = _construir_indice_tipos()
INDICE_REGLAS = _construir_indice_reglas()

PALABRAS = AFINIDAD["palabras_clave"]
TIPOS_REL = AFINIDAD["tipos_relacionados"]
CONFIG = AFINIDAD["config"]


# ─────────────────────────────────────────────
# ALGORITMO HÍBRIDO
# ─────────────────────────────────────────────

def puntuar_afinidad(carrera_a: str, carrera_b: str, tipo_a: str, tipo_b: str) -> int:
    """
    Calcula la puntuación de afinidad entre 2 carreras.
    
    Componentes:
      1. Grupos temáticos comunes        × peso_grupo (3)
      2. Palabras clave comunes          × peso_palabra_clave (1)
      3. Regla especial (par directo)    × peso_regla_especial (5)
      4. Tipos vocacionales relacionados × peso_tipo_relacionado (2)
    """
    puntaje = 0
    
    # 1. Grupos comunes
    grupos_a = set(INDICE_GRUPOS.get(carrera_a, []))
    grupos_b = set(INDICE_GRUPOS.get(carrera_b, []))
    puntaje += len(grupos_a & grupos_b) * CONFIG["peso_grupo"]
    
    # 2. Palabras clave comunes
    palabras_a = set(PALABRAS.get(carrera_a, []))
    palabras_b = set(PALABRAS.get(carrera_b, []))
    puntaje += len(palabras_a & palabras_b) * CONFIG["peso_palabra_clave"]
    
    # 3. Regla especial
    if (carrera_a, carrera_b) in INDICE_REGLAS:
        puntaje += CONFIG["peso_regla_especial"]
    
    # 4. Tipos vocacionales relacionados
    if tipo_b in TIPOS_REL.get(tipo_a, []):
        puntaje += CONFIG["peso_tipo_relacionado"]
    
    return puntaje


def seleccionar_4_carreras(tipo_top1: str, tipo_top2: str) -> dict:
    """
    Dado el Top 2 de tipos vocacionales, devuelve 4 carreras afines:
      - 2 principales (el mejor par)
      - 2 respaldo (el segundo mejor par)
    
    Retorna: {
      "principales": [{"carrera": "X", "tipo": "T1", "puntaje": N}, ...],
      "respaldo":    [{"carrera": "Y", "tipo": "T2", "puntaje": N}, ...]
    }
    """
    carreras_a = CARRERAS.get(tipo_top1, [])
    carreras_b = CARRERAS.get(tipo_top2, [])
    
    # Generar todos los pares posibles
    pares = []
    for ca, cb in product(carreras_a, carreras_b):
        if ca == cb:
            continue
        puntaje = puntuar_afinidad(ca, cb, tipo_top1, tipo_top2)
        if puntaje >= CONFIG["umbral_minimo"]:
            pares.append({
                "carrera_a": ca,
                "carrera_b": cb,
                "puntaje": puntaje
            })
    
    # Ordenar por puntaje descendente
    pares.sort(key=lambda x: x["puntaje"], reverse=True)
    
    # Tomar los 2 mejores pares evitando repetir carreras
    seleccionados = []
    carreras_usadas = set()
    
    for par in pares:
        if par["carrera_a"] in carreras_usadas or par["carrera_b"] in carreras_usadas:
            continue
        seleccionados.append(par)
        carreras_usadas.add(par["carrera_a"])
        carreras_usadas.add(par["carrera_b"])
        if len(seleccionados) == 2:
            break
    
    # Si no se encontraron 2 pares, rellenar con las primeras del tipo
    while len(seleccionados) < 2:
        for c in carreras_a + carreras_b:
            if c not in carreras_usadas:
                seleccionados.append({
                    "carrera_a": c,
                    "carrera_b": "—",
                    "puntaje": 0
                })
                carreras_usadas.add(c)
                break
        else:
            break
    
    # Formatear resultado
    principales = []
    respaldo = []
    
    if len(seleccionados) >= 1:
        p = seleccionados[0]
        principales.append({"carrera": p["carrera_a"], "tipo": tipo_top1, "puntaje": p["puntaje"]})
        principales.append({"carrera": p["carrera_b"], "tipo": tipo_top2, "puntaje": p["puntaje"]})
    
    if len(seleccionados) >= 2:
        r = seleccionados[1]
        respaldo.append({"carrera": r["carrera_a"], "tipo": tipo_top1, "puntaje": r["puntaje"]})
        respaldo.append({"carrera": r["carrera_b"], "tipo": tipo_top2, "puntaje": r["puntaje"]})
    
    return {
        "principales": principales,
        "respaldo": respaldo
    }