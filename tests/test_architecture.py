import json
import os
import unittest
from datetime import datetime, timedelta
from typing import List, Optional

import httpx

from src.application.services import SearchActiveTenders
from src.domain.models import Tender, TenderRepository
from src.infrastructure.repositories import SocrataTenderRepository


class MockTenderRepository(TenderRepository):
    def __init__(self) -> None:
        self.last_call: dict = {}

    async def search_by_criteria(
        self,
        max_budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 1000,
        process_status: Optional[str] = None,
    ) -> List[Tender]:
        self.last_call = {
            "max_budget": max_budget,
            "department": department,
            "keyword": keyword,
            "process_status": process_status,
            "limit": limit,
        }
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


def _build_transport(pages):
    calls = {"count": 0, "offsets": [], "wheres": [], "selects": []}

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("$offset", "0"))
        calls["count"] += 1
        calls["offsets"].append(offset)
        calls["wheres"].append(request.url.params.get("$where", ""))
        calls["selects"].append(request.url.params.get("$select", ""))
        page_index = calls["count"] - 1
        payload = pages[page_index] if page_index < len(pages) else []
        return httpx.Response(200, content=json.dumps(payload), headers={"Content-Type": "application/json"})

    return httpx.MockTransport(handler), calls


class TestHexagonalArchitecture(unittest.IsolatedAsyncioTestCase):
    async def test_domain_entity_validity(self):
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

    async def test_use_case_search_tenders(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        results = await service.execute(budget=100000000)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "MOCK-001")
        self.assertEqual(results[0].base_price, 50000000.0)

    async def test_use_case_threads_keyword_to_repository(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        await service.execute(budget=100000000, keyword="kubernetes")

        self.assertEqual(repo.last_call["keyword"], "kubernetes")

    async def test_use_case_threads_process_status_to_repository(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        await service.execute(budget=100000000, process_status="Publicado")

        self.assertEqual(repo.last_call["process_status"], "Publicado")

    async def test_business_validation_negative_budget(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        with self.assertRaises(ValueError):
            await service.execute(budget=-100)

    async def test_business_validation_unsupported_process_status(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        with self.assertRaises(ValueError):
            await service.execute(budget=100000000, process_status="Seleccionado")


class TestInfrastructureAdapter(unittest.IsolatedAsyncioTestCase):
    def _raw_item(
        self,
        process_id: str,
        name: str,
        closing_date: str,
        process_status: str = "Publicado",
    ) -> dict:
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
            "estado_del_procedimiento": process_status,
        }

    async def test_repository_fetches_pages_concurrently_and_dedupes(self):
        pages = [
            [
                self._raw_item("1", "Compra de papelería", "2026-12-31T00:00:00.000"),
                self._raw_item("2", "Servicio de cafetería", "2026-12-30T00:00:00.000"),
            ],
            [
                self._raw_item("3", "Desarrollo de software a la medida", "2026-12-29T00:00:00.000"),
                self._raw_item("4", "Servicios cloud y ciberseguridad", "2026-12-28T00:00:00.000"),
            ],
        ]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(client=client, page_size=2, max_pages=3, cache_ttl=0)

        try:
            results = await repo.search_by_criteria(max_budget=500000000, limit=10)
        finally:
            await client.aclose()

        self.assertEqual(len(results), 2)
        self.assertEqual(calls["count"], 3)
        self.assertTrue(all(isinstance(item, Tender) for item in results))
        self.assertEqual(sorted(calls["offsets"]), [0, 2, 4])

    async def test_repository_filters_by_process_status_in_socrata_query(self):
        pages = [[
            self._raw_item("1", "Desarrollo de software a la medida", "2026-12-31T00:00:00.000"),
        ]]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(client=client, page_size=5, max_pages=1, cache_ttl=0)

        try:
            results = await repo.search_by_criteria(
                max_budget=500000000,
                process_status="Publicado",
                limit=5,
            )
        finally:
            await client.aclose()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "Publicado")
        self.assertIn("estado_de_apertura_del_proceso = 'Abierto'", calls["wheres"][0])
        self.assertIn("estado_del_procedimiento = 'Publicado'", calls["wheres"][0])
        self.assertIn("estado_del_procedimiento", calls["selects"][0])
        self.assertIn("urlproceso", calls["selects"][0])
        self.assertNotIn("nit_entidad", calls["selects"][0])

    async def test_fetch_raw_records_uses_limit_to_cap_socrata_pages(self):
        pages = [
            [
                self._raw_item("1", "Desarrollo de software", "2026-12-31T00:00:00.000"),
                self._raw_item("2", "Servicios cloud", "2026-12-30T00:00:00.000"),
            ],
            [
                self._raw_item("3", "Auditoría informática", "2026-12-29T00:00:00.000"),
                self._raw_item("4", "Ciberseguridad", "2026-12-28T00:00:00.000"),
            ],
            [
                self._raw_item("5", "Fábrica de software", "2026-12-27T00:00:00.000"),
                self._raw_item("6", "Gobierno de datos", "2026-12-26T00:00:00.000"),
            ],
        ]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(client=client, page_size=2, max_pages=5, cache_ttl=0)

        try:
            results = await repo.fetch_raw_records(max_budget=500000000, limit=3)
        finally:
            await client.aclose()

        self.assertEqual(len(results), 3)
        self.assertEqual(calls["count"], 2)
        self.assertEqual(sorted(calls["offsets"]), [0, 2])

    async def test_repository_uses_cache_on_repeat_call(self):
        pages = [[
            self._raw_item("1", "Desarrollo de software a la medida", "2026-12-31T00:00:00.000"),
        ]]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(client=client, page_size=5, max_pages=1, cache_ttl=60)

        try:
            first = await repo.search_by_criteria(max_budget=500000000, limit=5)
            second = await repo.search_by_criteria(max_budget=500000000, limit=5)
        finally:
            await client.aclose()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(calls["count"], 1)

    async def test_repository_filters_by_keyword(self):
        pages = [[
            self._raw_item("1", "Desarrollo de software a la medida", "2026-12-31T00:00:00.000"),
            self._raw_item("2", "Servicios cloud y ciberseguridad", "2026-12-30T00:00:00.000"),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(client=client, page_size=5, max_pages=1, cache_ttl=0)

        try:
            results = await repo.search_by_criteria(max_budget=500000000, keyword="CLOUD", limit=10)
        finally:
            await client.aclose()

        self.assertEqual([t.id for t in results], ["2"])

    async def test_repository_retries_on_transient_failure(self):
        attempts = {"count": 0}
        payload = [self._raw_item("1", "Desarrollo de software", "2026-12-31T00:00:00.000")]

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return httpx.Response(503)
            return httpx.Response(200, content=json.dumps(payload), headers={"Content-Type": "application/json"})

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(
            client=client,
            page_size=5,
            max_pages=1,
            cache_ttl=0,
            max_retries=3,
            backoff_base=0,
        )

        try:
            results = await repo.search_by_criteria(max_budget=500000000, limit=5)
        finally:
            await client.aclose()

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(results), 1)

    async def test_repository_rejects_unsupported_department_filter(self):
        repo = SocrataTenderRepository()

        with self.assertRaises(ValueError):
            await repo.search_by_criteria(
                max_budget=500000000,
                department="Bogota'; DROP TABLE tenders",
            )

        await repo.aclose()

    async def test_map_raw_records_returns_sorted_tenders(self):
        repo = SocrataTenderRepository()
        raw_records = [
            self._raw_item("1", "Servicios cloud y ciberseguridad", "2026-12-31T00:00:00.000"),
            self._raw_item("2", "Desarrollo de software a la medida", "2026-12-25T00:00:00.000"),
        ]

        mapped_tenders = repo.map_raw_records(raw_records)

        self.assertEqual([tender.id for tender in mapped_tenders], ["2", "1"])
        await repo.aclose()

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_INTEGRATION") == "1",
        "Set RUN_LIVE_INTEGRATION=1 to execute the live Socrata integration test.",
    )
    async def test_live_socrata_repository_mapping(self):
        repo = SocrataTenderRepository()
        try:
            results = await repo.search_by_criteria(max_budget=500000000, limit=5)
        finally:
            await repo.aclose()

        self.assertGreater(len(results), 0)
        item = results[0]
        self.assertIsInstance(item, Tender)
        self.assertIsInstance(item.closing_date, datetime)
        self.assertGreaterEqual(item.base_price, 0)


if __name__ == "__main__":
    unittest.main()
