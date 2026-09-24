"""
Verifica que LIDERAZGO cuenta exactamente 9 ítems cuando el alumno
marca 9 de sus 9 ítems correspondientes, y que E4 ya NO se cuenta
invertido.
"""
from vocacional.puntajes import calcular_pd


# ─────────────────────────────────────────────────────────────
# CASO 1: LIDERAZGO con 9 ítems marcados (E1, E2, P?, P?, H×5)
# E4 sin marcar NO debe sumar.
# ─────────────────────────────────────────────────────────────
def caso_1():
    print("\n" + "=" * 60)
    print("CASO 1: LIDERAZGO con 9 ítems correctos, E4 sin marcar")
    print("=" * 60)

    # Marcamos 2 de E (E1, E2), 2 de P (P3, P6), 5 de H (H1,H2,H4,H5,H8)
    # E3, E4, E5, E6 → sin marcar
    marcas = {
        # E: solo los 2 que el alumno marcó
        "E1": "si", "E2": "si",
        "E3": "no", "E4": "no", "E5": "no", "E6": "no",
        # P: dos sí
        "P1": "no", "P2": "no", "P3": "si",
        "P4": "no", "P5": "no", "P6": "si",
        # H: cinco sí
        "H1": "si", "H2": "si", "H3": "no", "H4": "si",
        "H5": "si", "H6": "no", "H7": "no", "H8": "si",
    }

    pd = calcular_pd(marcas)
    lid = pd["LIDERAZGO"]
    print(f"  PD_E = {lid['PD_E']}  (esperado 2)")
    print(f"  PD_P = {lid['PD_P']}  (esperado 2)")
    print(f"  PD_H = {lid['PD_H']}  (esperado 5)")
    print(f"  PD   = {lid['PD']}  (esperado 9)")

    assert lid["PD_E"] == 2, f"PD_E esperado 2, obtenido {lid['PD_E']}"
    assert lid["PD_P"] == 2, f"PD_P esperado 2, obtenido {lid['PD_P']}"
    assert lid["PD_H"] == 5, f"PD_H esperado 5, obtenido {lid['PD_H']}"
    assert lid["PD"]   == 9, f"PD total esperado 9, obtenido {lid['PD']}"
    print("  ✓ CORRECTO")


# ─────────────────────────────────────────────────────────────
# CASO 2: E4 marcado como "si" suma, no resta.
# ─────────────────────────────────────────────────────────────
def caso_2():
    print("\n" + "=" * 60)
    print("CASO 2: E4 marcado como 'si' debe SUMAR (no restar)")
    print("=" * 60)

    marcas = {"E4": "si"}
    pd = calcular_pd(marcas)
    lid = pd["LIDERAZGO"]
    print(f"  Solo E4='si' → PD_E de LIDERAZGO = {lid['PD_E']}  (esperado 1)")
    assert lid["PD_E"] == 1, f"PD_E esperado 1, obtenido {lid['PD_E']}"
    print("  ✓ CORRECTO")


# ─────────────────────────────────────────────────────────────
# CASO 3: E4 sin marcar NO suma.
# ─────────────────────────────────────────────────────────────
def caso_3():
    print("\n" + "=" * 60)
    print("CASO 3: E4 sin marcar debe dar 0 (bug corregido)")
    print("=" * 60)

    marcas = {"E4": "no"}
    pd = calcular_pd(marcas)
    lid = pd["LIDERAZGO"]
    print(f"  Solo E4='no' → PD_E de LIDERAZGO = {lid['PD_E']}  (esperado 0)")
    assert lid["PD_E"] == 0, f"PD_E esperado 0, obtenido {lid['PD_E']}"
    print("  ✓ CORRECTO")


# ─────────────────────────────────────────────────────────────
# CASO 4: Resumen de los 7 tipos con un set completo.
# ─────────────────────────────────────────────────────────────
def caso_4():
    print("\n" + "=" * 60)
    print("CASO 4: Cálculo de los 7 tipos con datos reales")
    print("=" * 60)

    marcas = {
        "E1": "si", "E2": "si", "E3": "no", "E4": "no", "E5": "no", "E6": "no",
        "P1": "no", "P2": "no", "P3": "si", "P4": "no", "P5": "no", "P6": "si",
        "H1": "si", "H2": "si", "H3": "no", "H4": "si", "H5": "si",
        "H6": "no", "H7": "no", "H8": "si",
    }
    pd = calcular_pd(marcas)
    for tipo, d in pd.items():
        print(f"  {tipo:20s}  PD_E={d['PD_E']:2d}  PD_P={d['PD_P']:2d}  "
              f"PD_H={d['PD_H']:2d}  PD={d['PD']:2d}")


if __name__ == "__main__":
    caso_1()
    caso_2()
    caso_3()
    caso_4()
    print("\n" + "=" * 60)
    print("✓ Todos los tests pasaron.")
    print("=" * 60)