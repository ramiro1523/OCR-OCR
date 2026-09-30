# diagnostico.py
import json
from config_campos import CAMPOS_TEXTO_P1

print("=" * 60)
print("DIAGNÓSTICO")
print("=" * 60)

with open("datos_ejemplo.json", "r", encoding="utf-8") as f:
    datos = json.load(f)

print("\nCLAVES DEL JSON:")
for k in sorted(datos.keys()):
    print("   " + repr(k) + " = " + repr(datos[k]))

print("\nCLAVES DE CAMPOS_TEXTO_P1 (config_campos.py):")
for k in sorted(CAMPOS_TEXTO_P1.keys()):
    print("   " + repr(k))

print("\nCOMPARACION:")
faltantes = []
for k in CAMPOS_TEXTO_P1:
    tiene = k in datos
    marca = "OK" if tiene else "FALTA"
    print("   " + k.ljust(30) + " -> en JSON: " + marca)
    if not tiene:
        faltantes.append(k)

print("\n" + "=" * 60)
if faltantes:
    print("FALTAN " + str(len(faltantes)) + " claves en el JSON:")
    for k in faltantes:
        print("   - " + k)
    print("\nAGREGA ESTAS LINEAS AL JSON:")
    for k in faltantes:
        print('   "' + k + '": "VALOR_AQUI",')
else:
    print("OK: Todos los campos del config estan en el JSON.")
print("=" * 60)