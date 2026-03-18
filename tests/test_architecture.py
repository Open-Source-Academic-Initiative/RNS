import os
import unittest
from datetime import datetime, timedelta
from typing import List, Optional
from unittest import mock

from src.domain.models import Tender, TenderRepository
from src.application.services import SearchActiveTenders
from src.infrastructure.repositories import SocrataTenderRepository


class MockTenderRepository(TenderRepository):
    def search_by_criteria(
        self,
        max_budget: float,
        department: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Tender]:
        return [
            Tender(
                id="MOCK-001",
                reference="REF-2026-X",
                entity="Mock Entity",
                name="Mock Software",
                description="Desc",
                base_price=50000000.0,
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=5),
                url="http://mock.com",
                department="Bogotá",
            )
        ]


class DummyResponse:
    def __init__(self, payload, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class TestHexagonalArchitecture(unittest.TestCase):
    def test_domain_entity_validity(self):
        """Validates business logic in the Tender entity"""
        tender = Tender(
            id="1", reference="REF-01", entity="Test", name="T", description="D", base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() + timedelta(days=1),
            url="http",
        )
        self.assertTrue(tender.is_active)

        expired_tender = Tender(
            id="2", reference="REF-02", entity="Test", name="T", description="D", base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() - timedelta(days=1),
            url="http",
        )
        self.assertFalse(expired_tender.is_active)

    def test_use_case_search_tenders(self):
        """Validates the Use Case with a Mock Repository (Isolation)"""
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)
        
        results = service.execute(budget=100000000)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "MOCK-001")
        self.assertEqual(results[0].base_price, 50000000.0)

    def test_business_validation_negative_budget(self):
        """Validates that the Use Case rejects invalid budgets"""
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)
        
        with self.assertRaises(ValueError):
            service.execute(budget=-100)


class TestInfrastructureAdapter(unittest.TestCase):
    def _raw_item(self, process_id: str, name: str, closing_date: str):
        return {
            "id_del_proceso": process_id,
            "referencia_del_proceso": f"REF-{process_id}",
            "nombre_del_procedimiento": name,
            "descripci_n_del_procedimiento": f"Description for {name}",
            "precio_base": "1000000",
            "fecha_de_publicacion_del": "2026-01-01T00:00:00.000",
            "fecha_de_recepcion_de": closing_date,
            "entidad": "Test Entity",
            "urlproceso": "http://test.com",
            "estado_de_apertura_del_proceso": "Abierto",
        }

    def test_repository_fetches_multiple_pages_before_semantic_limit(self):
        session = mock.Mock()
        session.get.side_effect = [
            DummyResponse([
                self._raw_item("1", "Compra de papelería", "2026-12-31T00:00:00.000"),
                self._raw_item("2", "Servicio de cafetería", "2026-12-30T00:00:00.000"),
            ]),
            DummyResponse([
                self._raw_item("3", "Desarrollo de software a la medida", "2026-12-29T00:00:00.000"),
                self._raw_item("4", "Servicios cloud y ciberseguridad", "2026-12-28T00:00:00.000"),
            ]),
        ]
        repo = SocrataTenderRepository(session=session, page_size=2, max_pages=3)

        results = repo.search_by_criteria(max_budget=500000000, limit=2)

        self.assertEqual(len(results), 2)
        self.assertEqual(session.get.call_count, 2)
        self.assertTrue(all(isinstance(item, Tender) for item in results))
        self.assertEqual(
            [call.kwargs["params"]["$offset"] for call in session.get.call_args_list],
            [0, 2],
        )

    def test_map_raw_records_returns_sorted_tenders(self):
        repo = SocrataTenderRepository(session=mock.Mock())
        raw_records = [
            self._raw_item("1", "Servicios cloud y ciberseguridad", "2026-12-31T00:00:00.000"),
            self._raw_item("2", "Desarrollo de software a la medida", "2026-12-25T00:00:00.000"),
        ]

        mapped_tenders = repo.map_raw_records(raw_records)

        self.assertEqual([tender.id for tender in mapped_tenders], ["2", "1"])

    def test_repository_rejects_unsupported_department_filter(self):
        repo = SocrataTenderRepository(session=mock.Mock())

        with self.assertRaises(ValueError):
            repo.search_by_criteria(
                max_budget=500000000,
                department="Bogota'; DROP TABLE tenders",
            )

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_INTEGRATION") == "1",
        "Set RUN_LIVE_INTEGRATION=1 to execute the live Socrata integration test.",
    )
    def test_live_socrata_repository_mapping(self):
        repo = SocrataTenderRepository()
        results = repo.search_by_criteria(max_budget=500000000, limit=5)

        self.assertGreater(len(results), 0)
        item = results[0]
        self.assertIsInstance(item, Tender)
        self.assertIsInstance(item.closing_date, datetime)
        self.assertGreaterEqual(item.base_price, 0)

if __name__ == "__main__":
    unittest.main()
