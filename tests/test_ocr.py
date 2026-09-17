import unittest
import numpy as np
import cv2
from ocr.marks import esta_casilla_marcada, clasificar_item
from ocr.preprocess import binarizar, corregir_inclinacion

class TestOCRModules(unittest.TestCase):

    def test_casilla_vacia(self):
        # Crear imagen blanca (papel sin marca)
        celda = np.ones((50, 50), dtype=np.uint8) * 255
        marcada, dens = esta_casilla_marcada(celda)
        self.assertFalse(marcada)
        self.assertEqual(dens, 0.0)

    def test_casilla_con_marca_x(self):
        # Crear imagen blanca con una 'X' negra en el centro
        celda = np.ones((60, 60), dtype=np.uint8) * 255
        # Dibujar línea diagonal 1
        cv2.line(celda, (15, 15), (45, 45), color=0, thickness=3)
        # Dibujar línea diagonal 2
        cv2.line(celda, (15, 45), (45, 15), color=0, thickness=3)
        
        marcada, dens = esta_casilla_marcada(celda)
        self.assertTrue(marcada)
        self.assertGreater(dens, 0.04)

    def test_clasificar_item_si(self):
        celda_no = np.ones((60, 60), dtype=np.uint8) * 255
        celda_si = np.ones((60, 60), dtype=np.uint8) * 255
        cv2.line(celda_si, (15, 15), (45, 45), color=0, thickness=3)
        cv2.line(celda_si, (15, 45), (45, 15), color=0, thickness=3)
        
        res = clasificar_item(celda_no, celda_si)
        self.assertEqual(res["opcion"], "si")
        self.assertEqual(res["puntaje"], 1)

    def test_clasificar_item_ambos(self):
        # Ambas marcadas -> cuenta como Sí (1 punto)
        celda_no = np.ones((60, 60), dtype=np.uint8) * 255
        cv2.line(celda_no, (15, 15), (45, 45), color=0, thickness=3)
        cv2.line(celda_no, (15, 45), (45, 15), color=0, thickness=3)
        
        celda_si = np.ones((60, 60), dtype=np.uint8) * 255
        cv2.line(celda_si, (15, 15), (45, 45), color=0, thickness=3)
        cv2.line(celda_si, (15, 45), (45, 15), color=0, thickness=3)
        
        res = clasificar_item(celda_no, celda_si)
        self.assertEqual(res["opcion"], "ambos")
        self.assertEqual(res["puntaje"], 1)

    def test_binarizacion(self):
        img_gris = np.ones((100, 100), dtype=np.uint8) * 240
        cv2.rectangle(img_gris, (20, 20), (80, 80), color=20, thickness=-1)
        binaria = binarizar(img_gris)
        # Debe haber píxeles 0 y 255
        self.assertIn(0, binaria)
        self.assertIn(255, binaria)

if __name__ == "__main__":
    unittest.main()
