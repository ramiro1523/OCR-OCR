import json
from pathlib import Path
from itertools import product

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / "carreras.json", encoding="utf-8") as f:
    CARRERAS = json.load(f)

# Si existe INVESTIGACIÓN o INVESTIGATIVO, asegurar sinergia
if "INVESTIGATIVO" in CARRERAS and "INVESTIGACIÓN" not in CARRERAS:
    CARRERAS["INVESTIGACIÓN"] = CARRERAS["INVESTIGATIVO"]
elif "INVESTIGACIÓN" in CARRERAS and "INVESTIGATIVO" not in CARRERAS:
    CARRERAS["INVESTIGATIVO"] = CARRERAS["INVESTIGACIÓN"]

# Cargar matriz de afinidad (afinidad.json o relaciones_carreras.json)
afinidad_path = DATA_DIR / "afinidad.json"
if not afinidad_path.exists():
    afinidad_path = DATA_DIR / "relaciones_carreras.json"

with open(afinidad_path, encoding="utf-8") as f:
    AFINIDAD = json.load(f)


# ─────────────────────────────────────────────
# ÍNDICES PRE-CALCULADOS
# ─────────────────────────────────────────────

def _construir_indice_grupos():
    """Carrera → lista de grupos con su nombre."""
    indice = {}
    for grupo_id, data in AFINIDAD.get("grupos", {}).items():
        nombre = data.get("nombre", grupo_id.capitalize())
        for carrera in data.get("carreras", []):
            indice.setdefault(carrera, []).append({"id": grupo_id, "nombre": nombre})
    return indice


def _construir_indice_tipos():
    """Carrera → tipos vocacionales a los que pertenece."""
    indice = {}
    for tipo, carreras in CARRERAS.items():
        for carrera in carreras:
            indice.setdefault(carrera, []).append(tipo)
    return indice


def _construir_indice_reglas():
    """Par ordenado (a,b) → diccionario de la regla especial."""
    indice = {}
    for regla in AFINIDAD.get("reglas_especiales", []):
        par = regla.get("par", [])
        if len(par) == 2:
            a, b = par[0], par[1]
            indice[(a, b)] = regla
            indice[(b, a)] = regla
    return indice


INDICE_GRUPOS = _construir_indice_grupos()
INDICE_TIPOS = _construir_indice_tipos()
INDICE_REGLAS = _construir_indice_reglas()

PALABRAS = AFINIDAD.get("palabras_clave", {})
TIPOS_REL = AFINIDAD.get("tipos_relacionados", {})
CONFIG = AFINIDAD.get("config", {
    "peso_grupo": 3,
    "peso_palabra_clave": 1,
    "peso_regla_especial": 5,
    "peso_tipo_relacionado": 2,
    "umbral_minimo": 2
})


# ─────────────────────────────────────────────
# ALGORITMO DE AFINIDAD TEMÁTICA
# ─────────────────────────────────────────────

def puntuar_afinidad(carrera_a: str, carrera_b: str, tipo_a: str, tipo_b: str) -> tuple[int, str]:
    """
    Calcula la puntuación de afinidad y determina la relación temática.
    
    Retorna: (puntaje, relacion_tematica)
    """
    puntaje = 0
    relacion = "General"
    
    # 1. Regla especial directa (máxima prioridad)
    if (carrera_a, carrera_b) in INDICE_REGLAS:
        regla = INDICE_REGLAS[(carrera_a, carrera_b)]
        puntaje += CONFIG.get("peso_regla_especial", 5) * 2  # bono extra por match directo
        relacion = regla.get("razon", regla.get("categoria", "Afinidad directa"))
    
    # 2. Grupos temáticos comunes
    grupos_a = {g["id"]: g["nombre"] for g in INDICE_GRUPOS.get(carrera_a, [])}
    grupos_b = {g["id"]: g["nombre"] for g in INDICE_GRUPOS.get(carrera_b, [])}
    comunes = set(grupos_a.keys()) & set(grupos_b.keys())
    
    if comunes:
        puntaje += len(comunes) * CONFIG.get("peso_grupo", 3)
        if relacion == "General":
            primer_grupo = next(iter(comunes))
            relacion = grupos_a[primer_grupo]
    
    # 3. Palabras clave comunes
    palabras_a = set(PALABRAS.get(carrera_a, []))
    palabras_b = set(PALABRAS.get(carrera_b, []))
    coincidencias = palabras_a & palabras_b
    if coincidencias:
        puntaje += len(coincidencias) * CONFIG.get("peso_palabra_clave", 1)
        if relacion == "General":
            relacion = f"Área {', '.join(list(coincidencias)[:2])}"
    
    # 4. Tipos vocacionales relacionados
    if tipo_b in TIPOS_REL.get(tipo_a, []):
        puntaje += CONFIG.get("peso_tipo_relacionado", 2)
    
    return puntaje, relacion


def seleccionar_4_carreras(tipo_top1: str, tipo_top2: str) -> dict:
    """
    Dado el Top 2 de tipos vocacionales, selecciona 4 carreras afines:
      - 2 principales (el mejor par temático con 1 carrera del Top 1 y 1 del Top 2)
      - 2 de respaldo (el segundo mejor par temático con 1 carrera del Top 1 y 1 del Top 2)
    
    Retorna: {
      "principales": [{"carrera": "...", "tipo": "...", "relacion": "...", "puntaje": N}, ...],
      "respaldo":    [{"carrera": "...", "tipo": "...", "relacion": "...", "puntaje": N}, ...]
    }
    """
    carreras_a = CARRERAS.get(tipo_top1, [])
    carreras_b = CARRERAS.get(tipo_top2, [])
    
    # Fallback de normalización
    if not carreras_a and tipo_top1.startswith("INVESTIG"):
        carreras_a = CARRERAS.get("INVESTIGATIVO", CARRERAS.get("INVESTIGACIÓN", []))
    if not carreras_b and tipo_top2.startswith("INVESTIG"):
        carreras_b = CARRERAS.get("INVESTIGATIVO", CARRERAS.get("INVESTIGACIÓN", []))
    
    # Evaluar todos los pares posibles (Top 1 x Top 2)
    pares = []
    for ca, cb in product(carreras_a, carreras_b):
        if ca == cb:
            continue
        pts, rel = puntuar_afinidad(ca, cb, tipo_top1, tipo_top2)
        pares.append({
            "carrera_a": ca,
            "carrera_b": cb,
            "puntaje": pts,
            "relacion": rel
        })
    
    # Ordenar por puntaje descendente
    pares.sort(key=lambda x: x["puntaje"], reverse=True)
    
    # Tomar los 2 mejores pares sin repetir carreras
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
    
    # Fallback si no hay suficientes pares
    if len(seleccionados) < 2:
        for ca in carreras_a:
            if ca in carreras_usadas:
                continue
            for cb in carreras_b:
                if cb in carreras_usadas or cb == ca:
                    continue
                pts, rel = puntuar_afinidad(ca, cb, tipo_top1, tipo_top2)
                seleccionados.append({
                    "carrera_a": ca,
                    "carrera_b": cb,
                    "puntaje": pts,
                    "relacion": rel or "Afinidad complementaria"
                })
                carreras_usadas.add(ca)
                carreras_usadas.add(cb)
                break
            if len(seleccionados) == 2:
                break
    
    # Formatear salida estructurada
    principales = []
    respaldo = []
    
    if len(seleccionados) >= 1:
        p = seleccionados[0]
        principales.append({"carrera": p["carrera_a"], "tipo": tipo_top1, "relacion": p["relacion"], "puntaje": p["puntaje"]})
        principales.append({"carrera": p["carrera_b"], "tipo": tipo_top2, "relacion": p["relacion"], "puntaje": p["puntaje"]})
    
    if len(seleccionados) >= 2:
        r = seleccionados[1]
        respaldo.append({"carrera": r["carrera_a"], "tipo": tipo_top1, "relacion": r["relacion"], "puntaje": r["puntaje"]})
        respaldo.append({"carrera": r["carrera_b"], "tipo": tipo_top2, "relacion": r["relacion"], "puntaje": r["puntaje"]})
    
    return {
        "principales": principales,
        "respaldo": respaldo
    }


# ─────── Prueba desde consola ───────
#   python -m vocacional.carreras
if __name__ == "__main__":
    for t1, t2 in [
        ("INVESTIGATIVO", "TÉCNICO MECÁNICO"),
        ("SOCIAL", "ARTÍSTICO"),
        ("EMPRENDEDOR", "ORGANIZADO"),
    ]:
        print(f"\n═══ {t1}  +  {t2} ═══")
        try:
            r = seleccionar_4_carreras(t1, t2)
        except Exception as e:
            print(f"  Error: {e}")
            continue
        for c in r["principales"]:
            print(f"  [P] {c['carrera']:35} [{c['tipo']}]  →  {c['relacion']}  ({c['puntaje']} pts)")
        for c in r["respaldo"]:
            print(f"  [R] {c['carrera']:35} [{c['tipo']}]  →  {c['relacion']}  ({c['puntaje']} pts)")