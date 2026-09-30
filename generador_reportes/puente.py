# puente.py
"""
Une todas las piezas:
  parser_filename + motor_calculo + motor_pdf
en una sola función que produce el PDF final.
"""
from parser_filename import parsear_filename
from motor_calculo import calcular_informe
from motor_pdf import generar_pdf


def construir_datos_alumno(
    nombre_archivo: str,
    puntajes_directos: dict,
    datos_globales: dict,
) -> dict:
    """
    Devuelve el dict completo listo para motor_pdf.generar_pdf()
    """
    # 1. Parser
    parsed = parsear_filename(nombre_archivo)

    # 2. Cálculo
    calculo = calcular_informe(puntajes_directos, parsed["sexo"])

    areas = calculo["areas_top"]          # ej. ["artistico", "emprendimiento"]
    carreras = calculo["carreras_top"]    # ej. ["Arquitectura", "Diseño Gráfico", ...]

    return {
        # Cabecera
        "campo_nombre": parsed["nombre"],
        "campo_edad": parsed["edad"],
        "campo_genero": parsed["sexo"],
        "campo_fecha": datos_globales["fecha"],
        "campo_grado_instruccion": datos_globales["grado"],
        "campo_grado": datos_globales["nivel"],
        "campo_colegio": datos_globales["ie"],

        # Cálculo
        "niveles": calculo["niveles"],
        "potencial_puesto": calculo["potencial"],

        # 🔑 ÁREAS SEPARADAS (el "y" ya está en el PDF)
        "campo_areas": (
            areas[0].replace("_", " ").upper() if len(areas) > 0 else ""
        ),
        "campo_areas_2": (
            areas[1].replace("_", " ").upper() if len(areas) > 1 else ""
        ),

        # 🔑 CARRERAS SEPARADAS (el "y" ya está en el PDF)
        "campo_carreras": (
            carreras[0].upper() if len(carreras) > 0 else ""
        ),
        "campo_carreras_2": (
            carreras[1].upper() if len(carreras) > 1 else ""
        ),
    }


def procesar_alumno(
    nombre_archivo: str,
    puntajes_directos: dict,
    datos_globales: dict,
    ruta_salida: str = None,
) -> str:
    datos = construir_datos_alumno(nombre_archivo, puntajes_directos, datos_globales)
    return generar_pdf(datos, ruta_salida)