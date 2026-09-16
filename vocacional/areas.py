def ranking_tipos(puntajes_baremos: dict) -> list:
    """
    Ordena los tipos vocacionales por Baremo Final (descendente).
    
    Retorna: [
      {"tipo": "ORGANIZADO", "PD": 11, "Baremo": 52, "posicion": 1},
      {"tipo": "TÉCNICO MECÁNICO", "PD": 8, "Baremo": 50, "posicion": 2},
      ...
    ]
    """
    lista = []
    for tipo, datos in puntajes_baremos.items():
        if datos["Baremo"] is not None:
            lista.append({
                "tipo": tipo,
                "PD": datos["PD"],
                "Baremo": datos["Baremo"]
            })
    
    # Ordenar por Baremo descendente
    lista.sort(key=lambda x: x["Baremo"], reverse=True)
    
    # Añadir posición
    for i, item in enumerate(lista, start=1):
        item["posicion"] = i
    
    return lista


def top_2(puntajes_baremos: dict) -> list:
    """
    Devuelve los 2 tipos vocacionales con mayor Baremo Final.
    """
    ranking = ranking_tipos(puntajes_baremos)
    return ranking[:2]