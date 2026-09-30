# test_sprint0.py
"""
Prueba del Sprint 0: sin Streamlit, sin OCR.
Simula que ya tenemos los puntajes directos y genera el PDF.
"""
from puente import procesar_alumno


# ─── Datos simulados (en el Sprint 1 vendrán del pipeline OCR) ───
NOMBRE_ARCHIVO = "ana-rozas-hucho_16_F.pdf"

PUNTAJES_DIRECTOS = {
    "liderazgo": 38,
    "tecnico_mecanico": 41,
    "social": 55,
    "organizado": 36,
    "artistico": 25,
    "emprendimiento": 33,
    "investigacion": 37,
}

DATOS_GLOBALES = {
    "ie": "SANTO DOMINGO DE PANGOA",
    "fecha": "30/09/2026",
    "grado": "5",
    "nivel": "COMPLETA",
}


if __name__ == "__main__":
    print("🚀 Sprint 0 - Prueba de integración")
    print("-" * 50)

    ruta = procesar_alumno(
        nombre_archivo=NOMBRE_ARCHIVO,
        puntajes_directos=PUNTAJES_DIRECTOS,
        datos_globales=DATOS_GLOBALES,
    )

    print(f"✅ PDF generado: {ruta}")
    print("🏁 Abre el PDF y verifica que todo esté en su sitio.")