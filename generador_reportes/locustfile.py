# locustfile.py
"""
Prueba de carga HTTP contra Streamlit.

Mide la capacidad del servidor para:
  - Servir el HTML principal (/)
  - Responder al endpoint de salud (/_stcore/health)
  - Servir la config del host (/_stcore/host-config)

⚠️ NO mide el procesamiento de la app (WebSocket). Solo mide
    el rendimiento del servidor HTTP de Streamlit.
"""
from locust import HttpUser, task, between
import random


# Endpoints de Streamlit que SÍ responden por HTTP
ENDPOINTS = [
    ("/", "Homepage"),
    ("/_stcore/health", "Health Check"),
    ("/_stcore/host-config", "Host Config"),
]


class StreamlitUser(HttpUser):
    """
    Usuario simulado que hace peticiones repetidas a Streamlit.

    - wait_time: espera entre peticiones (simula tiempo de lectura)
    - @task(n): peso de la tarea (n mayor = más frecuente)
    """

    # Tiempo de espera entre peticiones (1 a 3 segundos)
    wait_time = between(1, 3)

    def on_start(self):
        """Se ejecuta UNA vez al iniciar cada usuario simulado."""
        self.client.get("/", name="Homepage")

    @task(5)
    def homepage(self):
        """Petición principal: la página HTML de Streamlit (peso 5)."""
        with self.client.get(
            "/", name="Homepage", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(3)
    def health_check(self):
        """Endpoint de salud de Streamlit (peso 3, más liviano)."""
        with self.client.get(
            "/_stcore/health", name="Health Check", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(1)
    def host_config(self):
        """Config del host de Streamlit (peso 1)."""
        with self.client.get(
            "/_stcore/host-config", name="Host Config", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")