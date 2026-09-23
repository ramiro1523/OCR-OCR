from vocacional.recomendador import recomendar_carreras

perfil = {"R": 0.7, "I": 0.4, "A": 0.3, "S": 0.5, "E": 0.4, "C": 0.5}

casos = [
    ["corredor de motos"],
    ["mecanica"],
    ["quiero ser doctor"],
    ["me gusta dibujar"],
    ["computadoras"],
    ["cocinar"],
    ["leyes", "justicia"],
    ["motos", "carros"],
]

for c in casos:
    print(f"\n>>> {c}")
    r = recomendar_carreras(perfil, c)
    for rec in r["recomendaciones"]:
        print(f"   {rec['nombre']:35s}  match={rec['match_usuario']:.2f}  "
              f"afinidad={rec['afinidad_test']:.2f}")
    if r.get("textos_no_encontrados"):
        print(f"   ⚠️  NO ENCONTRADO: {r['textos_no_encontrados']}")