"""
Test de la lógica de filtrado de carreras por nivel educativo e
institución (Opción B: filtro duro).

Verifica es_financiable() con distintos escenarios:
  - Nivel sin especificar (no filtra)
  - Nivel universitario/técnico/cetpro (filtra por jerarquía)
  - Institución sin especificar / indiferente (no filtra)
  - Institución pública o privada (filtra por mapeo)
  - Carreras sin mapeo (no se filtran, comportamiento seguro)
"""
from app import es_financiable, INSTITUCIONES_POR_CARRERA, NIVELES


# ─────────────────────────────────────────────────────────────
# UTILIDADES DE TEST
# ─────────────────────────────────────────────────────────────
_contador = {"pasados": 0, "fallados": 0}


def check(descripcion, esperado, *args, **kwargs):
    """Ejecuta un test y valida el resultado."""
    obtenido = es_financiable(*args, **kwargs)
    ok = obtenido == esperado
    simbolo = "✓" if ok else "✗"

    print(f"  {simbolo}  {descripcion}")
    print(f"      esperado={esperado}  obtenido={obtenido}")

    if ok:
        _contador["pasados"] += 1
    else:
        _contador["fallados"] += 1


# ─────────────────────────────────────────────────────────────
# SECCIÓN 1: Nivel educativo
# ─────────────────────────────────────────────────────────────
def test_nivel():
    print("\n" + "=" * 70)
    print("SECCIÓN 1: FILTRO POR NIVEL EDUCATIVO")
    print("=" * 70)

    # Sin especificar → no filtra nada
    check(
        "Sin especificar nivel → todo pasa",
        True,
        "universitario", "sin_especificar",
        carrera="Medicina", institucion_max="sin_especificar",
    )

    # Universitario pidiendo universitario → OK
    check(
        "Universitario → universitario: pasa",
        True,
        "universitario", "universitario",
        carrera="Medicina", institucion_max="sin_especificar",
    )

    # Universitario pidiendo técnico → descarta (jerarquía 3 > 2)
    check(
        "Carrera universitaria con nivel técnico: descarta",
        False,
        "universitario", "tecnico",
        carrera="Medicina", institucion_max="sin_especificar",
    )

    # Universitario pidiendo cetpro → descarta (jerarquía 3 > 1)
    check(
        "Carrera universitaria con nivel cetpro: descarta",
        False,
        "universitario", "cetpro",
        carrera="Medicina", institucion_max="sin_especificar",
    )

    # Técnico pidiendo universitario → OK (jerarquía 2 <= 3)
    check(
        "Carrera técnica con nivel universitario: pasa",
        True,
        "tecnico", "universitario",
        carrera="Mecánica Automotriz", institucion_max="sin_especificar",
    )

    # Técnico pidiendo técnico → OK
    check(
        "Carrera técnica con nivel técnico: pasa",
        True,
        "tecnico", "tecnico",
        carrera="Mecánica Automotriz", institucion_max="sin_especificar",
    )

    # Técnico pidiendo cetpro → descarta (jerarquía 2 > 1)
    check(
        "Carrera técnica con nivel cetpro: descarta",
        False,
        "tecnico", "cetpro",
        carrera="Mecánica Automotriz", institucion_max="sin_especificar",
    )

    # CETPRO pidiendo universitario → OK
    check(
        "Carrera cetpro con nivel universitario: pasa",
        True,
        "cetpro", "universitario",
        carrera="Cosmetología", institucion_max="sin_especificar",
    )

    # CETPRO pidiendo técnico → OK
    check(
        "Carrera cetpro con nivel técnico: pasa",
        True,
        "cetpro", "tecnico",
        carrera="Cosmetología", institucion_max="sin_especificar",
    )

    # CETPRO pidiendo cetpro → OK
    check(
        "Carrera cetpro con nivel cetpro: pasa",
        True,
        "cetpro", "cetpro",
        carrera="Cosmetología", institucion_max="sin_especificar",
    )


# ─────────────────────────────────────────────────────────────
# SECCIÓN 2: Filtro por institución
# ─────────────────────────────────────────────────────────────
def test_institucion():
    print("\n" + "=" * 70)
    print("SECCIÓN 2: FILTRO POR TIPO DE INSTITUCIÓN")
    print("=" * 70)

    # Sin especificar → no filtra
    check(
        "Institución sin especificar: no filtra (Medicina)",
        True,
        "universitario", "universitario",
        carrera="Medicina", institucion_max="sin_especificar",
    )

    # Indiferente → no filtra
    check(
        "Institución indiferente: no filtra (Marketing)",
        True,
        "universitario", "universitario",
        carrera="Marketing", institucion_max="indiferente",
    )

    # Pública + carrera pública-privada → OK
    check(
        "Pide pública, Medicina es pública+privada: pasa",
        True,
        "universitario", "universitario",
        carrera="Medicina", institucion_max="publica",
    )

    # Pública + carrera solo privada → descarta
    check(
        "Pide pública, Marketing es solo privada: descarta",
        False,
        "universitario", "universitario",
        carrera="Marketing", institucion_max="publica",
    )

    # Privada + carrera pública-privada → OK
    check(
        "Pide privada, Medicina es pública+privada: pasa",
        True,
        "universitario", "universitario",
        carrera="Medicina", institucion_max="privada",
    )

    # Privada + carrera solo pública → descarta
    check(
        "Pide privada, Astronomía es solo pública: descarta",
        False,
        "universitario", "universitario",
        carrera="Astronomía", institucion_max="privada",
    )

    # Privada + carrera solo privada → OK
    check(
        "Pide privada, Marketing es solo privada: pasa",
        True,
        "universitario", "universitario",
        carrera="Marketing", institucion_max="privada",
    )

    # Pública + carrera solo pública → OK
    check(
        "Pide pública, Astronomía es solo pública: pasa",
        True,
        "universitario", "universitario",
        carrera="Astronomía", institucion_max="publica",
    )


# ─────────────────────────────────────────────────────────────
# SECCIÓN 3: Casos borde
# ─────────────────────────────────────────────────────────────
def test_bordes():
    print("\n" + "=" * 70)
    print("SECCIÓN 3: CASOS BORDE")
    print("=" * 70)

    # Carrera sin mapeo → no se filtra
    check(
        "Carrera sin mapeo, pide pública: no se filtra",
        True,
        "universitario", "universitario",
        carrera="CarreraInventada", institucion_max="publica",
    )

    check(
        "Carrera sin mapeo, pide privada: no se filtra",
        True,
        "universitario", "universitario",
        carrera="CarreraInventada", institucion_max="privada",
    )

    # carrera=None → no se filtra por institución
    check(
        "carrera=None con pide pública: no filtra",
        True,
        "universitario", "universitario",
        carrera=None, institucion_max="publica",
    )

    # Sin argumentos opcionales (compatibilidad hacia atrás)
    check(
        "Sin argumentos opcionales: comportamiento seguro",
        True,
        "universitario", "universitario",
    )

    # Nivel + institución combinados
    check(
        "Técnico pidiendo pública, Mecánica Automotriz: pasa",
        True,
        "tecnico", "tecnico",
        carrera="Mecánica Automotriz", institucion_max="publica",
    )

    check(
        "Universitario pidiendo cetpro, Medicina: descarta por nivel",
        False,
        "universitario", "cetpro",
        carrera="Medicina", institucion_max="publica",
    )

    check(
        "CETPRO pidiendo privada, Cosmetología: pasa",
        True,
        "cetpro", "cetpro",
        carrera="Cosmetología", institucion_max="privada",
    )

    check(
        "CETPRO pidiendo privada, Dibujo y Pintura: pasa",
        True,
        "cetpro", "cetpro",
        carrera="Dibujo y Pintura", institucion_max="privada",
    )


# ─────────────────────────────────────────────────────────────
# SECCIÓN 4: Cobertura del mapeo
# ─────────────────────────────────────────────────────────────
def test_cobertura():
    print("\n" + "=" * 70)
    print("SECCIÓN 4: COBERTURA DEL MAPEO DE INSTITUCIONES")
    print("=" * 70)

    total = len(INSTITUCIONES_POR_CARRERA)
    print(f"  Carreras con mapeo: {total}")
    print(f"  Carreras sin mapeo: se filtran como 'disponible en todas'")

    # Cuántas son públicas, privadas, ambas
    solo_pub = sum(1 for v in INSTITUCIONES_POR_CARRERA.values() if v == {"publica"})
    solo_priv = sum(1 for v in INSTITUCIONES_POR_CARRERA.values() if v == {"privada"})
    ambas = sum(1 for v in INSTITUCIONES_POR_CARRERA.values() if len(v) == 2)

    print(f"    · Solo pública:  {solo_pub}")
    print(f"    · Solo privada:  {solo_priv}")
    print(f"    · Pública+priv:  {ambas}")

    # Verificar que las carreras del catálogo oficial están cubiertas
    from app import CATALOGO
    sin_mapeo = [c for c in CATALOGO if c not in INSTITUCIONES_POR_CARRERA]
    if sin_mapeo:
        print(f"\n  ⚠️  Carreras sin mapeo de institución ({len(sin_mapeo)}):")
        for c in sin_mapeo[:20]:  # muestra las primeras 20
            print(f"     · {c}")
        if len(sin_mapeo) > 20:
            print(f"     ... y {len(sin_mapeo) - 20} más")
        print("  Estas NO se filtran por institución (comportamiento seguro).")
    else:
        print("\n  ✓ Todas las carreras del catálogo tienen mapeo de institución.")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "█" * 70)
    print("  TEST: FILTRO DE CARRERAS POR NIVEL E INSTITUCIÓN (Opción B)")
    print("█" * 70)

    test_nivel()
    test_institucion()
    test_bordes()
    test_cobertura()

    print("\n" + "█" * 70)
    print("  RESULTADO FINAL")
    print("█" * 70)
    print(f"  Pasados:  {_contador['pasados']}")
    print(f"  Fallados: {_contador['fallados']}")

    if _contador["fallados"] == 0:
        print("\n  ✓ Todos los tests pasaron.")
    else:
        print(f"\n  ✗ {_contador['fallados']} test(s) fallaron. Revisa los detalles arriba.")

    print("█" * 70)