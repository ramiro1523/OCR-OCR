import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def is_db_available() -> bool:
    """Verifica de forma rápida y segura si PostgreSQL está disponible."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "ieppo"),
            user=os.getenv("DB_USER", "ieppo_user"),
            password=os.getenv("DB_PASSWORD", ""),
            connect_timeout=2
        )
        conn.close()
        return True
    except Exception as e:
        logger.debug("Base de datos no disponible: %s", e)
        return False


def get_connection():
    """
    Retorna una conexión a PostgreSQL o None si no está disponible.
    No bloquea ni hace colapsar la aplicación.
    """
    try:
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "ieppo"),
            user=os.getenv("DB_USER", "ieppo_user"),
            password=os.getenv("DB_PASSWORD", ""),
            connect_timeout=3
        )
    except Exception as e:
        logger.warning("No se pudo conectar a la base de datos PostgreSQL: %s", e)
        return None