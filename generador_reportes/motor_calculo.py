# motor_calculo.py
"""
Motor de cálculo de baremos SOVIO.
⚠️ IMPORTANTE: Ajusta los rangos a los valores REALES de tu manual SOVIO.
Los valores aquí son de ejemplo, basados en la regla que me mostraste:
   ≤ 39 Bajo · 40-60 Medio · ≥ 61 Alto
"""

# ─────────────────────────────────────────────────────────────
# BAREMOS POR SEXO
# Cada área tiene 3 rangos (bajo, medio, alto)
# Los rangos son inclusivos: (min, max)
# ─────────────────────────────────────────────────────────────
BAREMOS = {
    "F": {  # Mujeres
        "liderazgo":         {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "tecnico_mecanico":  {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "social":            {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "organizado":        {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "artistico":         {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "emprendimiento":    {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "investigacion":     {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
    },
    "M": {  # Hombres — AJUSTA con tus baremos reales
        "liderazgo":         {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "tecnico_mecanico":  {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "social":            {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "organizado":        {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "artistico":         {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "emprendimiento":    {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
        "investigacion":     {"bajo": (0, 39), "medio": (40, 60), "alto": (61, 999)},
    },
}

# ─────────────────────────────────────────────────────────────
# CARRERAS SUGERIDAS POR ÁREA
# Cuando un área es top, se sugieren estas carreras
# ─────────────────────────────────────────────────────────────
CARRERAS_POR_AREA = {
    "liderazgo":         ["Derecho", "Administración", "Ing Industrial"],
    "tecnico_mecanico":  ["Ingeniería Mecánica", "Ingeniería Civil", "Electrónica"],
    "social":            ["Educación", "Psicología", "Trabajo Social"],
    "organizado":        ["Contabilidad", "Administración", "Economía"],
    "artistico":         ["Arquitectura", "Diseño Gráfico", "Comunicación"],
    "emprendimiento":    ["Administración", "Negocios", "Marketing"],
    "investigacion":     ["Ciencias de la Salud", "Ing Ambiental", "Veterinaria"],
}


def _nivel_de_puntaje(area: str, puntaje: int, sexo: str) -> str:
    """Devuelve 'bajo', 'medio' o 'alto'."""
    baremos_sexo = BAREMOS.get(sexo, BAREMOS["F"])
    rango = baremos_sexo.get(area, {})
    for nivel, (min_, max_) in rango.items():
        if min_ <= puntaje <= max_:
            return nivel
    return "bajo"


def calcular_informe(puntajes: dict, sexo: str) -> dict:
    """
    puntajes = {"liderazgo": 38, "tecnico_mecanico": 41, ...}
    sexo = "F" o "M"

    Devuelve:
    {
        "niveles": {"liderazgo": "bajo", ...},
        "potencial": "ALTO",
        "areas_top": ["social", "tecnico_mecanico"],
        "carreras_top": ["Ciencias de la Salud", "Ing Ambiental", ...],
    }
    """
    sexo = (sexo or "F").upper()

    # 1. Calcular nivel de cada área
    niveles = {}
    for area, puntaje in puntajes.items():
        niveles[area] = _nivel_de_puntaje(area, puntaje, sexo)

    # 2. Top 2 áreas por puntaje (mayor a menor)
    ordenados = sorted(puntajes.items(), key=lambda x: -x[1])
    areas_top = [a for a, _ in ordenados[:2]]

    # 3. Carreras sugeridas (de las 2 áreas top, sin repetir)
    carreras = []
    for area in areas_top:
        carreras.extend(CARRERAS_POR_AREA.get(area, []))
    carreras_top = list(dict.fromkeys(carreras))[:4]

    # 4. Potencial Empresarial
    pot = "BAJO"
    if niveles.get("emprendimiento") == "alto" and niveles.get("liderazgo") == "alto":
        pot = "ALTO"
    elif niveles.get("emprendimiento") in ("medio", "alto"):
        pot = "MEDIO"

    return {
        "niveles": niveles,
        "potencial": pot,
        "areas_top": areas_top,
        "carreras_top": carreras_top,
    }


if __name__ == "__main__":
    # Prueba con los datos del ejemplo que me diste
    puntajes_prueba = {
        "liderazgo": 38,
        "tecnico_mecanico": 41,
        "social": 55,
        "organizado": 36,
        "artistico": 25,
        "emprendimiento": 33,
        "investigacion": 37,
    }
    resultado = calcular_informe(puntajes_prueba, "F")
    print("Niveles:", resultado["niveles"])
    print("Potencial:", resultado["potencial"])
    print("Áreas top:", resultado["areas_top"])
    print("Carreras top:", resultado["carreras_top"])