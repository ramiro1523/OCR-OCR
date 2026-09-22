import unittest
from vocacional.puntajes import calcular_pd, contar_si
from vocacional.baremos import calcular_baremos
from vocacional.areas import ranking_tipos, top_2
from vocacional.carreras import seleccionar_4_carreras
from vocacional.utils import generar_items_vacios, auditar_marcas

class TestVocacionalEngine(unittest.TestCase):

    def test_reglas_marcas(self):
        marcas = {
            "E1": "si",     # 1 pt
            "E2": "no",     # 0 pt
            "E3": "ambos",  # 1 pt
            "E4": "vacio",  # 0 pt
        }
        self.assertEqual(contar_si(marcas, ["E1"]), 1)
        self.assertEqual(contar_si(marcas, ["E2"]), 0)
        self.assertEqual(contar_si(marcas, ["E3"]), 0)
        self.assertEqual(contar_si(marcas, ["E4"]), 0)

    def test_baremos_mujeres(self):
        # Según tabla 7.1 MUJERES:
        # LIDERAZGO PD 0 -> 28, PD 6 -> 40, PD 11 -> 50
        # TEC.MEC PD 8 -> 60, PD 14 -> 80
        puntajes = {
            "LIDERAZGO": {"PD": 6},
            "TÉCNICO MECÁNICO": {"PD": 8}
        }
        baremos = calcular_baremos(puntajes, "F")
        self.assertEqual(baremos["LIDERAZGO"]["Baremo"], 40)
        self.assertEqual(baremos["TÉCNICO MECÁNICO"]["Baremo"], 60)

    def test_baremos_varones(self):
        # Según tabla 7.2 VARONES:
        # LIDERAZGO PD 0 -> 30, PD 6 -> 42, PD 11 -> 52
        # TEC.MEC PD 8 -> 50
        puntajes = {
            "LIDERAZGO": {"PD": 6},
            "TÉCNICO MECÁNICO": {"PD": 8}
        }
        baremos = calcular_baremos(puntajes, "M")
        self.assertEqual(baremos["LIDERAZGO"]["Baremo"], 42)
        self.assertEqual(baremos["TÉCNICO MECÁNICO"]["Baremo"], 50)

    def test_top_2_ranking(self):
        con_baremos = {
            "LIDERAZGO": {"PD": 6, "Baremo": 42},
            "TÉCNICO MECÁNICO": {"PD": 8, "Baremo": 50},
            "SOCIAL": {"PD": 6, "Baremo": 44},
            "ORGANIZADO": {"PD": 11, "Baremo": 52},
            "ARTÍSTICO": {"PD": 2, "Baremo": 34},
            "EMPRENDEDOR": {"PD": 9, "Baremo": 42},
            "INVESTIGATIVO": {"PD": 0, "Baremo": 31}
        }
        top = top_2(con_baremos)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["tipo"], "ORGANIZADO")
        self.assertEqual(top[0]["Baremo"], 52)
        self.assertEqual(top[1]["tipo"], "TÉCNICO MECÁNICO")
        self.assertEqual(top[1]["Baremo"], 50)

    def test_afinidad_organizado_emprendedor(self):
        # Requerimiento 9.6:
        # ORGANIZADO + EMPRENDEDOR
        # Contabilidad <-> Finanzas (Finanzas)
        # Marketing <-> Administración (Negocios)
        carreras = seleccionar_4_carreras("ORGANIZADO", "EMPRENDEDOR")
        self.assertEqual(len(carreras["principales"]), 2)
        self.assertEqual(len(carreras["respaldo"]), 2)
        
        nombres_p = {c["carrera"] for c in carreras["principales"]}
        nombres_r = {c["carrera"] for c in carreras["respaldo"]}
        
        # Deben contener o emparejar carreras afines
        self.assertTrue(bool(nombres_p & {"Contabilidad", "Finanzas", "Administración", "Marketing"}))
        self.assertTrue(bool(nombres_r & {"Contabilidad", "Finanzas", "Administración", "Marketing"}))

    def test_afinidad_tecnico_mecanico_artistico(self):
        # Requerimiento 9.7: TÉCNICO MECÁNICO + ARTÍSTICO
        carreras = seleccionar_4_carreras("TÉCNICO MECÁNICO", "ARTÍSTICO")
        self.assertEqual(len(carreras["principales"]), 2)
        self.assertEqual(len(carreras["respaldo"]), 2)

    def test_utils_items(self):
        items = generar_items_vacios()
        self.assertEqual(len(items), 118)
        self.assertTrue("E1" in items and "E33" in items)
        self.assertTrue("P1" in items and "P47" in items)
        self.assertTrue("H1" in items and "H38" in items)
        
        audit = auditar_marcas(items)
        self.assertEqual(len(audit["vacios"]), 118)

if __name__ == "__main__":
    unittest.main()
