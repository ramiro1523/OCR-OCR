import logging
from typing import Optional
from db.connection import get_connection

logger = logging.getLogger(__name__)

def guardar_evaluacion(nombre: str, sexo: str, marcas: dict, puntajes: dict, carreras: dict) -> Optional[int]:
    """
    Guarda una evaluación completa en PostgreSQL si la base de datos está disponible.
    Si la base de datos no está activa o configurada, no lanza error y retorna None.
    """
    conn = get_connection()
    if not conn:
        logger.info("Base de datos en modo Offline. La evaluación no se persistió.")
        return None
    
    try:
        with conn.cursor() as cur:
            # 1. Insertar formulario
            cur.execute(
                "INSERT INTO formularios (nombre, sexo) VALUES (%s, %s) RETURNING id;",
                (nombre, sexo)
            )
            form_id = cur.fetchone()[0]
            
            # 2. Insertar marcas
            # opcion: "no" | "si" | "ambos" | "vacio"
            # puntaje: 1 si si/ambos, 0 en otro caso
            marcas_rows = []
            for item, opcion in marcas.items():
                pt = 1 if opcion in ("si", "ambos") else 0
                marcas_rows.append((form_id, item, opcion, pt))
            
            cur.executemany(
                "INSERT INTO marcas (formulario_id, item, opcion, puntaje) VALUES (%s, %s, %s, %s);",
                marcas_rows
            )
            
            # 3. Insertar puntajes y posiciones
            from vocacional.areas import ranking_tipos
            ranking = ranking_tipos(puntajes)
            puntajes_rows = [
                (form_id, r["tipo"], r["PD"], r["Baremo"], r["posicion"])
                for r in ranking
            ]
            cur.executemany(
                "INSERT INTO puntajes (formulario_id, tipo, pd, baremo, posicion) VALUES (%s, %s, %s, %s, %s);",
                puntajes_rows
            )
            
            # 4. Insertar carreras sugeridas
            carreras_rows = []
            for c in carreras.get("principales", []):
                carreras_rows.append((form_id, c["carrera"], c["tipo"], True))
            for c in carreras.get("respaldo", []):
                carreras_rows.append((form_id, c["carrera"], c["tipo"], False))
            
            if carreras_rows:
                cur.executemany(
                    "INSERT INTO carreras_sugeridas (formulario_id, carrera, tipo, es_principal) VALUES (%s, %s, %s, %s);",
                    carreras_rows
                )
            
            conn.commit()
            logger.info("Evaluación guardada exitosamente con ID %s", form_id)
            return form_id
            
    except Exception as e:
        conn.rollback()
        logger.error("Error al guardar evaluación en la base de datos: %s", e)
        return None
    finally:
        conn.close()


def obtener_ultimas_evaluaciones(limite: int = 10) -> list[dict]:
    """Obtiene el historial de formularios procesados (si la BD está activa)."""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, sexo, fecha_procesado FROM formularios ORDER BY fecha_procesado DESC LIMIT %s;",
                (limite,)
            )
            rows = cur.fetchall()
            return [
                {"id": r[0], "nombre": r[1], "sexo": r[2], "fecha_procesado": r[3]}
                for r in rows
            ]
    except Exception as e:
        logger.error("Error al consultar evaluaciones: %s", e)
        return []
    finally:
        conn.close()
