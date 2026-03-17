import unittest
from secop_extractor import SecopExtractor

class TestSecopExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = SecopExtractor()
        # Datos simulados con diferentes escenarios
        self.mock_data = [
            {
                "entidad": "ENTIDAD TI EXITOSA",
                "precio_base": "80000000",
                "nombre_del_procedimiento": "Desarrollo de Software Web",
                "descripci_n_del_procedimiento": "API para gestión",
                "urlproceso": "http://secop.gov.co/1"
            },
            {
                "entidad": "ENTIDAD NO TI",
                "precio_base": "50000000",
                "nombre_del_procedimiento": "Compra de Papelería",
                "descripci_n_del_procedimiento": "Resmas de papel",
                "urlproceso": "http://secop.gov.co/2"
            },
            {
                "entidad": "ENTIDAD TI SIN DESC",
                "precio_base": "20000000",
                "nombre_del_procedimiento": "Sistemas Informáticos",
                "urlproceso": "http://secop.gov.co/3"
            },
             {
                "entidad": "ENTIDAD TI MAYUSCULAS",
                "precio_base": "95000000",
                "nombre_del_procedimiento": "DESARROLLO DE SOFTWARE",
                "descripci_n_del_procedimiento": "INFRAESTRUCTURA CLOUD",
                "urlproceso": "http://secop.gov.co/4"
            }
        ]

    def test_filtrado_semantico_exitoso(self):
        """Valida que se identifiquen correctamente los procesos de TI."""
        resultados = self.extractor.procesar_datos(self.mock_data)
        
        # Deben pasar: ENTIDAD TI EXITOSA, ENTIDAD TI SIN DESC, ENTIDAD TI MAYUSCULAS
        self.assertEqual(len(resultados), 3)
        entidades = [r['entidad'] for r in resultados]
        self.assertIn("ENTIDAD TI EXITOSA", entidades)
        self.assertIn("ENTIDAD TI MAYUSCULAS", entidades)
        self.assertNotIn("ENTIDAD NO TI", entidades)

    def test_manejo_campos_faltantes(self):
        """Valida que el sistema no falle si faltan campos opcionales."""
        datos_incompletos = [{"entidad": "TEST", "nombre_del_procedimiento": "Software"}]
        resultados = self.extractor.procesar_datos(datos_incompletos)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]['entidad'], "TEST")

    def test_conversion_precio(self):
        """Valida que el precio se convierta a float y se use para ordenar."""
        resultados = self.extractor.procesar_datos(self.mock_data)
        # El primer elemento debe ser el de mayor precio (95,000,000)
        self.assertEqual(resultados[0]['precio_base'], 95000000.0)
        self.assertIsInstance(resultados[0]['precio_base'], float)

if __name__ == "__main__":
    unittest.main()
