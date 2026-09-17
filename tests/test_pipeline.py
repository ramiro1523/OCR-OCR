"""
Tests de integración del pipeline OCR usando imágenes sintéticas
que replican el layout real del formulario IEPPO:

  [ PARTE 1 E ] [ PARTE 2 P ] [ PARTE 3 H ]
  N° | No | Sí   N° | No | Sí  N° | No | Sí
"""

import unittest
import io
import numpy as np
import cv2

from ocr.pipeline import (
    procesar_formulario_pdf,
    _dividir_en_3_columnas,
    _detectar_filas_tabla,
    _procesar_bloque_tabla,
    _extraer_casillas_fila,
)
from ocr.marks import clasificar_item
from vocacional.utils import generar_items_vacios


def _crear_marca_x(celda: np.ndarray) -> np.ndarray:
    """Dibuja una 'X' en el centro de una celda."""
    h, w = celda.shape[:2]
    p1, p2 = int(w * 0.2), int(h * 0.2)
    p3, p4 = int(w * 0.8), int(h * 0.8)
    cv2.line(celda, (p1, p2), (p3, p4), 0, 2)
    cv2.line(celda, (p3, p2), (p1, p4), 0, 2)
    return celda


def _construir_tabla_sintetica(n_filas: int, ancho: int = 200, alto_fila: int = 22,
                                 patron_si: list = None) -> np.ndarray:
    """
    Crea una tabla sintética con n_filas filas y 3 columnas (N°, No, Sí).
    patron_si: lista de booleanos indicando si la casilla Sí está marcada para cada fila.
    """
    alto = alto_fila * (n_filas + 1)  # +1 por encabezado
    tabla = np.ones((alto, ancho), dtype=np.uint8) * 255

    col_w = ancho // 3
    # Dibujar líneas divisorias
    for y in range(0, alto, alto_fila):
        cv2.line(tabla, (0, y), (ancho - 1, y), 0, 1)
    for x in [col_w, col_w * 2]:
        cv2.line(tabla, (x, 0), (x, alto - 1), 0, 1)

    # Rellenar marcas según patrón
    if patron_si is None:
        patron_si = [True] * n_filas

    for i in range(n_filas):
        y_fila = alto_fila * (i + 1)  # Saltar encabezado
        if patron_si[i]:
            # Marcar casilla Sí (columna 2)
            celda_si = tabla[y_fila + 2: y_fila + alto_fila - 2,
                             col_w * 2 + 2: ancho - 2]
            _crear_marca_x(celda_si)

    return tabla


class TestPipelineMapeo(unittest.TestCase):
    """Pruebas que verifican que los resultados se guardan correctamente en marcas."""

    def test_extraer_casillas_fila(self):
        """Casilla Sí con marca debe detectarse correctamente en una fila."""
        fila = np.ones((22, 200), dtype=np.uint8) * 255
        # Marcar la parte derecha (Sí)
        cv2.line(fila, (140, 4), (178, 18), 0, 2)
        cv2.line(fila, (178, 4), (140, 18), 0, 2)

        celda_no, celda_si = _extraer_casillas_fila(fila)

        res = clasificar_item(celda_no, celda_si)
        self.assertEqual(res["opcion"], "si")
        self.assertEqual(res["puntaje"], 1)

    def test_procesar_bloque_guarda_resultados(self):
        """
        CASO CRÍTICO: Verifica que _procesar_bloque_tabla guarda
        los resultados en el diccionario marcas (el bug que se corrigió).
        """
        marcas = generar_items_vacios()
        detalles = {}
        etiquetas = [f"E{i}" for i in range(1, 7)]  # E1–E6

        # Tabla sintética: 6 ítems, todos con Sí marcado
        tabla = _construir_tabla_sintetica(
            n_filas=6,
            ancho=200,
            alto_fila=24,
            patron_si=[True, False, True, False, True, True]
        )

        n = _procesar_bloque_tabla(tabla, etiquetas, marcas, detalles)

        # El bug era que marcas quedaba todo "vacio" aunque se procesara.
        # Con el fix, debe haber cambiado:
        self.assertGreater(n, 0, "No se procesó ningún ítem")

        # Al menos algunos ítems deben haber cambiado de "vacio"
        estados = [marcas[e] for e in etiquetas]
        items_detectados = [e for e in estados if e != "vacio"]

        self.assertGreater(
            len(items_detectados), 0,
            f"BUG: marcas quedó todo vacio. Estados: {estados}"
        )

    def test_dividir_en_3_columnas(self):
        """Verificar que la división en 3 columnas produce imágenes de ancho > 0."""
        pagina = np.ones((1000, 800), dtype=np.uint8) * 255

        # Simular 3 tablas con líneas divisorias verticales
        cv2.line(pagina, (265, 0), (265, 999), 0, 2)
        cv2.line(pagina, (532, 0), (532, 999), 0, 2)

        col_e, col_p, col_h = _dividir_en_3_columnas(pagina)

        self.assertGreater(col_e.shape[1], 0, "Columna E sin ancho")
        self.assertGreater(col_p.shape[1], 0, "Columna P sin ancho")
        self.assertGreater(col_h.shape[1], 0, "Columna H sin ancho")

        # Las 3 columnas juntas deben sumar aproximadamente el ancho total
        total = col_e.shape[1] + col_p.shape[1] + col_h.shape[1]
        self.assertGreater(total, 700, f"Ancho total {total} < 700")

    def test_detectar_filas_tabla(self):
        """Verificar que se detectan filas en una tabla sintética."""
        tabla = _construir_tabla_sintetica(n_filas=10, ancho=200, alto_fila=22)
        filas = _detectar_filas_tabla(tabla, n_items_esperados=10)

        # Deben detectarse al menos 5 de 10 filas
        self.assertGreater(len(filas), 4, f"Solo {len(filas)} filas detectadas")

        # Cada fila debe tener y2 > y1
        for f in filas:
            self.assertGreater(f["y2"], f["y1"])

    def test_pipeline_sin_pdf_retorna_fallback(self):
        """Si el PDF falla, debe retornar marcas vacías sin lanzar excepción."""
        resultado = procesar_formulario_pdf(b"datos_invalidos")

        self.assertIn("marcas", resultado)
        self.assertIn("exito", resultado)
        self.assertEqual(len(resultado["marcas"]), 118)
        # No debe lanzar excepciones — siempre retorna dict


if __name__ == "__main__":
    unittest.main()
