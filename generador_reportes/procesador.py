# procesador.py
"""
Procesa múltiples PDFs en paralelo usando ThreadPoolExecutor.

Ventajas:
  - El OCR de OpenCV libera el GIL en las operaciones grandes, así que
    los threads se ejecutan realmente en paralelo.
  - No hay que serializar datos entre procesos (más simple que
    ProcessPoolExecutor).
  - El pipeline ya tiene su propio timeout interno, no hay conflicto.
  - Cada PDF es independiente: si uno falla, los demás continúan.

Cuidado con max_workers:
  - El OCR consume mucha CPU. Con 8+ workers, la máquina se satura y
    todo va más lento.
  - Recomendado: 3-4 workers en laptop moderna, 6-8 en servidor.
"""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from parser_filename import parsear_filename


def _procesar_uno(args):
    """
    Procesa un solo archivo en un worker del pool.

    args = (idx, nombre_archivo, contenido_bytes, sexo, funcion_pipeline)

    Devuelve:
      (idx, resultado_dict, None) si tuvo éxito
      (idx, None, mensaje_error) si falló
    """
    idx, nombre_archivo, contenido_bytes, sexo, pipeline_fn = args

    ruta_tmp = None
    try:
        # Guardar bytes a un archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contenido_bytes)
            ruta_tmp = tmp.name

        # Ejecutar pipeline (la función ya tiene su propio timeout interno)
        resultado = pipeline_fn(ruta_tmp, sexo=sexo)
        return idx, resultado, None

    except Exception as e:
        return idx, None, f"{type(e).__name__}: {e}"

    finally:
        if ruta_tmp and os.path.exists(ruta_tmp):
            try:
                os.remove(ruta_tmp)
            except Exception:
                pass


def procesar_lote_paralelo(
    archivos,
    pipeline_fn,
    max_workers: int = 4,
    on_progress=None,
):
    """
    Procesa múltiples PDFs en paralelo.

    Args:
        archivos: lista de tuplas (nombre_archivo, contenido_bytes)
                  Ej: [("ana_16_F.pdf", bytes_pdf), ...]
        pipeline_fn: función procesar_alumno(ruta, sexo=...) → dict
        max_workers: cuántos PDFs procesar simultáneamente
        on_progress: callback(completados, total) para actualizar la UI

    Returns:
        (lista_alumnos, lista_errores)
          - lista_alumnos: dicts listos para session_state
          - lista_errores: [(nombre_archivo, mensaje_error), ...]
    """
    tareas = []

    for idx, (nombre_archivo, contenido) in enumerate(archivos):
        try:
            parsed = parsear_filename(nombre_archivo)
        except ValueError as e:
            # El nombre no sigue el patrón, lo saltamos
            continue
        tareas.append((
            idx,
            nombre_archivo,
            contenido,
            parsed["sexo"],
            pipeline_fn,
        ))

    resultados = [None] * len(tareas)
    errores = []
    completados = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {
            executor.submit(_procesar_uno, tarea): tarea
            for tarea in tareas
        }

        for futuro in as_completed(futuros):
            idx, resultado, error = futuro.result()
            tarea = futuros[futuro]
            nombre_archivo = tarea[1]
            completados += 1

            if error:
                errores.append((nombre_archivo, error))
            else:
                # Reconstruir el alumno con los datos del parser + pipeline
                try:
                    parsed = parsear_filename(nombre_archivo)
                    alumno = _construir_alumno(parsed, resultado, nombre_archivo)
                    resultados[idx] = alumno
                except Exception as e:
                    errores.append((nombre_archivo, f"Construcción: {e}"))

            if on_progress:
                on_progress(completados, len(tareas))

    alumnos = [r for r in resultados if r is not None]
    return alumnos, errores


def _construir_alumno(parsed: dict, resultado: dict, nombre_archivo: str) -> dict:
    """
    Construye el dict del alumno a partir del parser y del resultado del pipeline.
    """
    areas = resultado.get("areas_top", [])
    carreras = resultado.get("carreras_top", [])

    return {
        "nombre": parsed["nombre"],
        "edad": parsed["edad"],
        "sexo": parsed["sexo"],
        "archivo_original": nombre_archivo,
        "puntajes_directos": resultado["puntajes_directos"],
        "niveles": resultado["niveles"],
        "potencial": resultado["potencial"],
        "areas_top": areas,
        "carreras_top": carreras,
        "area_1": (areas[0].replace("_", " ").upper() if len(areas) > 0 else ""),
        "area_2": (areas[1].replace("_", " ").upper() if len(areas) > 1 else ""),
        "carrera_1": (carreras[0].upper() if len(carreras) > 0 else ""),
        "carrera_2": (carreras[1].upper() if len(carreras) > 1 else ""),
        "carrera_manual_1": "",
        "carrera_manual_2": "",
        "carrera_manual_3": "",
    }