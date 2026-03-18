import os
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.domain.models import Tender
from src.presentation.web import app, get_tender_service


class StubTenderService:
    def execute(self, budget: float, department: str | None = None):
        return [
            Tender(
                id="WEB-001",
                reference="REF-WEB-001",
                entity="Mock Entity",
                name="Desarrollo de software a la medida",
                description="Procedimiento de prueba para la interfaz web",
                base_price=min(float(budget), 90000000.0),
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=7),
                url="https://example.test/process/WEB-001",
                department=department,
            )
        ]


def override_tender_service():
    return StubTenderService()


class TestWebInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_tender_service] = override_tender_service
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("SECOP II - Radar TI", response.text)
        self.assertIn("Parámetros de Búsqueda", response.text)

    def test_search_endpoint_renders_results(self):
        response = self.client.get("/search?budget=100000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Licitaciones Encontradas: 1", response.text)
        self.assertIn("Mock Entity", response.text)
        self.assertIn("Desarrollo de software a la medida", response.text)

    def test_invalid_department_returns_validation_error(self):
        response = self.client.get("/search?budget=100000000&department=DROP%20TABLE")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported department filter", response.text)

    def test_template_exists(self):
        self.assertTrue(os.path.exists("templates/index.html"))


if __name__ == "__main__":
    unittest.main()
