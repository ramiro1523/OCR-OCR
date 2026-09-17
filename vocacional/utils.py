"""
Utilidades para el motor vocacional y el flujo de ítems IEPPO.
"""

def generar_items_vacios() -> dict[str, str]:
    """
    Genera el diccionario inicial con los 118 ítems del formulario en estado 'vacio'.
    - Bloque E (Estilos Personales): E1 a E33
    - Bloque P (Actividades de Preferencia): P1 a P47
    - Bloque H (Percepción de Habilidad): H1 a H38
    """
    items = {}
    for i in range(1, 34):
        items[f"E{i}"] = "vacio"
    for i in range(1, 48):
        items[f"P{i}"] = "vacio"
    for i in range(1, 39):
        items[f"H{i}"] = "vacio"
    return items


def obtener_bloques() -> dict[str, list[str]]:
    """Devuelve los ítems agrupados por bloque."""
    return {
        "ESTILOS PERSONALES": [f"E{i}" for i in range(1, 34)],
        "ACTIVIDADES DE PREFERENCIA": [f"P{i}" for i in range(1, 48)],
        "PERCEPCIÓN DE HABILIDAD": [f"H{i}" for i in range(1, 39)]
    }


def auditar_marcas(marcas: dict[str, str]) -> dict:
    """
    Audita el estado de las marcas para detectar ítems dudosos o que requieren atención.
    - vacios: sin marcar (advertencia ⚠️)
    - ambos: doble marca X X (cuenta como Sí ✅)
    - si: solo Sí marcado (cuenta como Sí ✅)
    - no: solo No marcado (0 puntos ✅)
    """
    vacios = [item for item, val in marcas.items() if val == "vacio"]
    ambos = [item for item, val in marcas.items() if val == "ambos"]
    si = [item for item, val in marcas.items() if val == "si"]
    no = [item for item, val in marcas.items() if val == "no"]
    
    return {
        "total": len(marcas),
        "vacios": vacios,
        "ambos": ambos,
        "si": si,
        "no": no,
        "dudosos": vacios + ambos
    }
