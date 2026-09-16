import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """Conexión a PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "ieppo"),
        user=os.getenv("DB_USER", "ieppo_user"),
        password=os.getenv("DB_PASSWORD")
    )