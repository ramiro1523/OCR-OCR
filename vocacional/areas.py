def ranking_tipos(puntajes_baremos: dict) -> list:
    """
    Ordena los tipos vocacionales por Baremo Final (descendente).
    En caso de empate en Baremo, desempata por PD descendente.
    
    Retorna: [
      {"tipo": "ORGANIZADO", "PD": 11, "Baremo": 52, "posicion": 1},
      {"tipo": "TÉCNICO MECÁNICO", "PD": 8, "Baremo": 50, "posicion": 2},
      ...
    ]
    """
    lista = []
    for tipo, datos in puntajes_baremos.items():
        baremo = datos.get("Baremo")
        pd = datos.get("PD", 0)
        # Se incluyen todos los tipos; si baremo es None, se asigna 0 para el ordenamiento
        lista.append({
            "tipo": tipo,
            "PD": pd,
            "Baremo": baremo
        })
    
    # Ordenar por Baremo descendente (los None van al final) y desempate por PD descendente
    lista.sort(key=lambda x: (x["Baremo"] if x["Baremo"] is not None else -1, x["PD"]), reverse=True)
    
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