"""
Diagnóstico: muestra exactamente qué ítems está contando la app
para LIDERAZGO, y compara con el esperado (9 ítems → PD=9).
"""
from vocacional.puntajes import calcular_pd
from vocacional.utils import obtener_bloques

# Simulamos un formulario con TODOS los ítems marcados como "si"
# para ver cuántos aporta LIDERAZGO
marcas_todas_si = {}
for bloque, items in obtener_bloques().items():
    for item in items:
        marcas_todas_si[item] = "si"

pd = calcular_pd(marcas_todas_si)
print("=" * 60)
print("CON TODOS LOS ÍTEMS EN 'si'")
print("=" * 60)
for tipo, valor in pd.items():
    print(f"  {tipo:25s}  PD = {valor}")

print()
print("=" * 60)
print("BUSCANDO QUÉ ÍTEMS APORTAN A LIDERAZGO")
print("=" * 60)

# Importamos el mapa interno
try:
    from vocacional import puntajes as P
    # Buscamos en el módulo cualquier variable que sea un dict
    # con listas de items por tipo
    for nombre in dir(P):
        obj = getattr(P, nombre)
        if isinstance(obj, dict) and obj:
            # ¿Parece un mapa tipo → [items]?
            primer_valor = next(iter(obj.values()))
            if isinstance(primer_valor, (list, tuple, set)):
                if "LIDERAZGO" in obj:
                    items_liderazgo = obj["LIDERAZGO"]
                    print(f"\nVariable: {nombre}")
                    print(f"  LIDERAZGO tiene {len(items_liderazgo)} ítems:")
                    for it in sorted(items_liderazgo):
                        print(f"    - {it}")
                break
except Exception as e:
    print(f"No se pudo importar el mapa: {e}")