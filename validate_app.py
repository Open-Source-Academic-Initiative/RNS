import unittest
from fastapi.testclient import TestClient
from main import app
import os

class TestWebInterface(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_home_page_loads(self):
        """Verifica que la página de inicio cargue correctamente"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SECOP II - Radar TI", response.text)

    def test_consultar_endpoint(self):
        """Verifica que el endpoint de consulta retorne resultados (o simulación)"""
        response = self.client.get("/consultar?presupuesto=100000000")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Licitaciones Encontradas", response.text)

    def test_templates_exist(self):
        """Verifica la existencia del archivo de plantilla"""
        self.assertTrue(os.path.exists("templates/index.html"))

if __name__ == "__main__":
    unittest.main()
