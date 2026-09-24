"""
Puntuación de los 7 tipos vocacionales IEPPO.

Replica las fórmulas del Excel `IEPPO` (columnas F, M, T → AH, AI, AJ → AK),
PERO corrige el bug de E4 que existía en la planilla original.

El Excel original tenía una fórmula errónea en E4 (usaba C12 en vez de D12)
que hacía que E4 contara invertido: 1 si estaba SIN marcar, 0 si estaba
marcada. Eso nunca se justificó contra el manual del IEPPO. Aquí se trata
E4 como cualquier otro ítem: 1 si "si", 0 en cualquier otro caso.

Con esta corrección, LIDERAZGO con 9 ítems marcados da PD=9 (antes daba 10)
y su baremo cae en 48 en vez de 50.
"""
from __future__ import annotations


# ─────────────────────────────────────────────────────────────
# MAPEO DE ÍTEMS POR TIPO (extraído de IEPPO!AH*:AJ*)
# ─────────────────────────────────────────────────────────────
ITEMS_POR_TIPO = {
    "LIDERAZGO":        {"E": list(range(1, 7)),   "P": list(range(1, 7)),   "H": list(range(1, 9))},
    "TÉCNICO MECÁNICO": {"E": list(range(7, 11)),  "P": list(range(7, 12)),  "H": list(range(9, 14))},
    "SOCIAL":           {"E": list(range(11, 16)), "P": list(range(12, 18)), "H": list(range(14, 18))},
    "ORGANIZADO":       {"E": list(range(16, 22)), "P": list(range(18, 25)), "H": list(range(18, 25))},
    "ARTÍSTICO":        {"E": list(range(22, 26)), "P": list(range(25, 33)), "H": list(range(25, 29))},
    "EMPRENDEDOR":      {"E": list(range(26, 34)), "P": list(range(33, 40)), "H": list(range(29, 35))},
    "INVESTIGATIVO":    {"E": [],                  "P": list(range(40, 48)), "H": list(range(35, 39))},
}


def _marca_a_valor(marca: str) -> int:
    """
    Devuelve 1 si la marca es 'si' (o 'ambos'), 0 en cualquier otro caso.
    """
    m = (marca or "").strip().lower()
    return 1 if m in ("si", "ambos") else 0


def calcular_pd(marcas: dict) -> dict:
    """
    Recibe {E1: 'si'|'no'|'vacio'|'ambos', P1:..., H1:...}
    Devuelve, por tipo vocacional, las sumas parciales por bloque y el total.

    Returns:
        {
          "LIDERAZGO": {"PD_E": int, "PD_P": int, "PD_H": int, "PD": int},
          ...
        }
    """
    resultado = {}
    for tipo, grupos in ITEMS_POR_TIPO.items():
        pd_e = sum(
            _marca_a_valor(marcas.get(f"E{n}", "vacio"))
            for n in grupos["E"]
        )
        pd_p = sum(
            _marca_a_valor(marcas.get(f"P{n}", "vacio"))
            for n in grupos["P"]
        )
        pd_h = sum(
            _marca_a_valor(marcas.get(f"H{n}", "vacio"))
            for n in grupos["H"]
        )

        # El bloque E no participa en INVESTIGATIVO (así está en el manual)
        if tipo == "INVESTIGATIVO":
            pd_e = 0

        resultado[tipo] = {
            "PD_E": pd_e,
            "PD_P": pd_p,
            "PD_H": pd_h,
            "PD":   pd_e + pd_p + pd_h,
        }
    return resultado