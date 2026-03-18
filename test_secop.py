import unittest

from secop_extractor import SecopExtractor


class TestSecopExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = SecopExtractor()
        self.mock_data = [
            {
                "entidad": "SUCCESSFUL IT ENTITY",
                "precio_base": "80000000",
                "nombre_del_procedimiento": "Desarrollo de Software Web",
                "descripci_n_del_procedimiento": "API de Gestión",
                "urlproceso": "http://secop.gov.co/1"
            },
            {
                "entidad": "NON-IT ENTITY",
                "precio_base": "50000000",
                "nombre_del_procedimiento": "Compra de Papelería",
                "descripci_n_del_procedimiento": "Resmas de papel",
                "urlproceso": "http://secop.gov.co/2"
            },
            {
                "entidad": "IT ENTITY NO DESC",
                "precio_base": "20000000",
                "nombre_del_procedimiento": "Sistemas de Computo",
                "urlproceso": "http://secop.gov.co/3"
            },
            {
                "entidad": "UPPERCASE IT ENTITY",
                "precio_base": "95000000",
                "nombre_del_procedimiento": "DESARROLLO DE SOFTWARE",
                "descripci_n_del_procedimiento": "INFRAESTRUCTURA CLOUD",
                "urlproceso": "http://secop.gov.co/4"
            }
        ]

    def test_semantic_filtering_success(self):
        """Validates that IT processes are correctly identified."""
        results = self.extractor.process_data(self.mock_data)

        self.assertEqual(len(results), 3)
        entities = [item["entity"] for item in results]
        self.assertIn("SUCCESSFUL IT ENTITY", entities)
        self.assertIn("UPPERCASE IT ENTITY", entities)
        self.assertNotIn("NON-IT ENTITY", entities)

    def test_missing_fields_handling(self):
        """Validates that the system does not crash if optional fields are missing."""
        incomplete_data = [{"entidad": "TEST", "nombre_del_procedimiento": "Software"}]
        results = self.extractor.process_data(incomplete_data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entity"], "TEST")

    def test_price_conversion(self):
        """Validates that price is converted to float and used for sorting."""
        results = self.extractor.process_data(self.mock_data)
        self.assertEqual(results[0]["base_price"], 95000000.0)
        self.assertIsInstance(results[0]["base_price"], float)

if __name__ == "__main__":
    unittest.main()
