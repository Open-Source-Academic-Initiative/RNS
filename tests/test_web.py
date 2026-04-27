import os
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.application.validators import normalize_department
from src.domain.models import Tender
from src.presentation.web import app, get_tender_service


class StubTenderService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, budget: float, department: str | None = None, keyword: str | None = None):
        normalized_department = normalize_department(department)
        self.calls.append({
            "budget": budget,
            "department": normalized_department,
            "keyword": keyword,
        })
        tenders = [
            Tender(
                id=f"WEB-{index:03d}",
                reference=f"REF-WEB-{index:03d}",
                entity=f"Mock Entity {index}",
                name=f"Desarrollo de software #{index}",
                description="Procedimiento de prueba para la interfaz web",
                base_price=min(float(budget), 10000000.0 * index),
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=7 + index),
                url=f"https://example.test/process/WEB-{index:03d}",
                department=normalized_department,
            )
            for index in range(1, 4)
        ]
        if keyword:
            needle = keyword.lower()
            tenders = [t for t in tenders if needle in t.name.lower()]
        return tenders


_stub_instance = StubTenderService()


def override_tender_service():
    return _stub_instance


class TestWebInterface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_tender_service] = override_tender_service
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def setUp(self):
        _stub_instance.calls.clear()

    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("SECOP II - Radar TI", response.text)
        self.assertIn("Parámetros de Búsqueda", response.text)
        self.assertIn("Palabra clave", response.text)

    def test_search_endpoint_renders_results(self):
        response = self.client.get("/search?budget=100000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Licitaciones Encontradas: 3", response.text)
        self.assertIn("Mock Entity 1", response.text)
        self.assertIn("Desarrollo de software #1", response.text)
        self.assertIn("Exportar CSV", response.text)

    def test_frontend_is_local_and_avoids_modal_inline_data_handlers(self):
        response = self.client.get("/search?budget=100000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cdn.tailwindcss.com", response.text)
        self.assertNotIn("onclick=\"openModal", response.text)
        self.assertIn("data-text=", response.text)

    def test_search_threads_keyword_to_service(self):
        response = self.client.get("/search?budget=100000000&department=Todos&keyword=KUBE")

        self.assertEqual(response.status_code, 200)
        last_call = _stub_instance.calls[-1]
        self.assertEqual(last_call["keyword"], "KUBE")

    def test_pagination_controls_render(self):
        response = self.client.get("/search?budget=100000000&department=Todos&per_page=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Página 1 de 3", response.text)
        self.assertIn("Siguiente →", response.text)

    def test_csv_export_returns_csv(self):
        response = self.client.get("/search.csv?budget=100000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))
        body = response.text
        self.assertIn("id,reference,entity", body)
        self.assertIn("WEB-001", body)

    def test_csv_export_invalid_department_returns_validation_error(self):
        response = self.client.get("/search.csv?budget=100000000&department=DROP%20TABLE")

        self.assertEqual(response.status_code, 400)
        self.assertIn("El filtro de departamento seleccionado no es válido.", response.text)

    def test_invalid_department_returns_validation_error(self):
        response = self.client.get("/search?budget=100000000&department=DROP%20TABLE")

        self.assertEqual(response.status_code, 400)
        self.assertIn("El filtro de departamento seleccionado no es válido.", response.text)

    def test_template_exists(self):
        self.assertTrue(os.path.exists("templates/index.html"))


if __name__ == "__main__":
    unittest.main()
