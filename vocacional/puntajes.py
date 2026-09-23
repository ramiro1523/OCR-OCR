"""
Puntuación de los 7 tipos vocacionales IEPPO.
Replica exactamente las fórmulas del Excel `IEPPO` (columnas F, M, T → AH, AI, AJ → AK).
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────
# MAPEO DE ÍTEMS POR TIPO (extraído de IEPPO!AH*:AJ*)
# ─────────────────────────────────────────────────────────────
ITEMS_POR_TIPO = {
    "LIDERAZGO":        {"E": list(range(1, 7)),  "P": list(range(1, 7)),  "H": list(range(1, 9))},
    "TÉCNICO MECÁNICO": {"E": list(range(7, 11)), "P": list(range(7, 12)), "H": list(range(9, 14))},
    "SOCIAL":           {"E": list(range(11, 16)),"P": list(range(12, 18)),"H": list(range(14, 18))},
    "ORGANIZADO":       {"E": list(range(16, 22)),"P": list(range(18, 25)),"H": list(range(18, 25))},
    "ARTÍSTICO":        {"E": list(range(22, 26)),"P": list(range(25, 33)),"H": list(range(25, 29))},
    "EMPRENDEDOR":      {"E": list(range(26, 34)),"P": list(range(33, 40)),"H": list(range(29, 35))},
    "INVESTIGATIVO":    {"E": [],                 "P": list(range(40, 48)),"H": list(range(35, 39))},
}

# Ítems con el BUG del Excel (F12 usa C12 en vez de D12)
ITEMS_BUG_E = {"E4"}  # si marcan "no" en E4, cuenta 1; si marcan "si", cuenta 0


def _marca_a_valor(marca: str, es_bug: bool = False) -> int:
    """
    Excel:
        E y P: IF(marca="si", 1, 0)   ← normal
        E4 (bug): IF(marca="no", 1, 0)
    """
    m = (marca or "").strip().lower()
    if es_bug:
        return 1 if m == "no" else 0
    return 1 if m == "si" else 0


def calcular_pd(marcas: dict) -> dict:
    """
    Recibe {E1: 'si'|'no'|'vacio'|'ambos', P1:..., H1:...}
    Devuelve {TIPO: PD_total} replicando AK11:AK17.
    """
    resultado = {}
    for tipo, grupos in ITEMS_POR_TIPO.items():
        pd_e = sum(
            _marca_a_valor(marcas.get(f"E{n}", "vacio"), es_bug=(f"E{n}" in ITEMS_BUG_E))
            for n in grupos["E"]
        )
        pd_p = sum(_marca_a_valor(marcas.get(f"P{n}", "vacio")) for n in grupos["P"])
        pd_h = sum(_marca_a_valor(marcas.get(f"H{n}", "vacio")) for n in grupos["H"])

        # AH17 en Excel es literal '--' → INVESTIGATIVO no suma E
        if tipo == "INVESTIGATIVO":
            pd_e = 0

        resultado[tipo] = {
            "PD_E": pd_e,
            "PD_P": pd_p,
            "PD_H": pd_h,
            "PD":   pd_e + pd_p + pd_h,
        }
    return resultado