# test_faltantes.py
import warnings, contextlib, io
with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
    warnings.simplefilter("ignore")
    from app import CATALOGO, INSTITUCIONES_POR_CARRERA

faltantes = sorted(c for c in CATALOGO if c not in INSTITUCIONES_POR_CARRERA)
print(f"Carreras sin mapeo ({len(faltantes)}):")
for c in faltantes:
    print(f"  · {c}")