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
        min_budget: float,
        max_budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10000,
        process_status: Optional[str] = None,
        phase: Optional[str] = None,
        published_since_days: int = 60,
        profile: str = "opensai",
        only_high_fit: bool = False,
        only_new: bool = False,
    ) -> List[Tender]:
        self.last_call = {
            "min_budget": min_budget,
            "max_budget": max_budget,
            "department": department,
            "keyword": keyword,
            "process_status": process_status,
            "phase": phase,
            "published_since_days": published_since_days,
            "profile": profile,
            "only_high_fit": only_high_fit,
            "only_new": only_new,
            "limit": limit,
        }
        return [
            Tender(
                id="MOCK-001",
                reference="REF-2026-X",
                entity="Universidad Demo",
                name="Administración de campus virtual Moodle",
                description="Soporte, actualización y analítica de aprendizaje",
                base_price=120000000.0,
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=5),
                url="http://mock.com",
                department="Distrito Capital de Bogotá",
                phase="Presentación de oferta",
                match_score=88.0,
                match_label="Alto encaje",
                match_reasons=["LMS / educación virtual"],
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
            id="1",
            reference="REF-01",
            entity="Test",
            name="T",
            description="D",
            base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() + timedelta(days=1),
            url="http",
        )
        self.assertTrue(tender.is_active)

        expired_tender = Tender(
            id="2",
            reference="REF-02",
            entity="Test",
            name="T",
            description="D",
            base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() - timedelta(days=1),
            url="http",
        )
        self.assertFalse(expired_tender.is_active)

    async def test_use_case_threads_new_filters_to_repository(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        await service.execute(
            budget=260000000,
            min_budget=60000000,
            department="Atlantico",
            keyword="moodle",
            process_status="Publicado",
            phase="Presentación de oferta",
            published_since_days=45,
            profile="opensai",
            only_high_fit=True,
            only_new=True,
        )

        self.assertEqual(repo.last_call["min_budget"], 60000000)
        self.assertEqual(repo.last_call["max_budget"], 260000000)
        self.assertEqual(repo.last_call["department"], "Atlántico")
        self.assertEqual(repo.last_call["keyword"], "moodle")
        self.assertEqual(repo.last_call["profile"], "opensai")
        self.assertTrue(repo.last_call["only_high_fit"])
        self.assertTrue(repo.last_call["only_new"])
        self.assertEqual(repo.last_call["published_since_days"], 45)

    async def test_business_validation_budget_range(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        with self.assertRaises(ValueError):
            await service.execute(budget=100, min_budget=200)

    async def test_business_validation_invalid_profile(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        with self.assertRaises(ValueError):
            await service.execute(budget=100000000, profile="unknown")

    async def test_business_validation_invalid_published_window(self):
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)

        with self.assertRaises(ValueError):
            await service.execute(budget=100000000, published_since_days=0)


class TestInfrastructureAdapter(unittest.IsolatedAsyncioTestCase):
    def _repo(self, client: Optional[httpx.AsyncClient] = None, **kwargs) -> SocrataTenderRepository:
        return SocrataTenderRepository(
            client=client,
            cache_ttl=0,
            snapshot_db_path=":memory:",
            **kwargs,
        )

    def _raw_item(
        self,
        process_id: str,
        name: str,
        description: str,
        *,
        closing_date: Optional[str] = "2026-12-31T00:00:00.000",
        publish_date: str = "2026-04-15T00:00:00.000",
        price: str = "100000000",
        entity: str = "Universidad Demo",
        process_status: str = "Publicado",
        phase: str = "Presentación de oferta",
        modality: str = "Licitación pública",
    ) -> dict:
        return {
            "id_del_proceso": process_id,
            "referencia_del_proceso": f"REF-{process_id}",
            "nombre_del_procedimiento": name,
            "descripci_n_del_procedimiento": description,
            "precio_base": price,
            "fecha_de_publicacion_del": publish_date,
            "fecha_de_recepcion_de": closing_date,
            "entidad": entity,
            "urlproceso": {"url": f"http://test.com/{process_id}"},
            "estado_de_apertura_del_proceso": "Abierto",
            "estado_del_procedimiento": process_status,
            "fase": phase,
            "modalidad_de_contratacion": modality,
            "departamento_entidad": "Distrito Capital de Bogotá",
        }

    async def test_repository_filters_by_publication_window_and_budget_range(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte y actualización del LMS institucional",
            ),
        ]]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        class FixedClockRepository(type(repo)):
            def _now(self_inner) -> datetime:
                return datetime(2026, 5, 1, 12, 0, 0)

        repo.__class__ = FixedClockRepository

        try:
            await repo.search_by_criteria(
                min_budget=60000000,
                max_budget=260000000,
                published_since_days=60,
                limit=5,
            )
        finally:
            await client.aclose()
            await repo.aclose()

        where_clause = calls["wheres"][0]
        select_clause = calls["selects"][0]
        self.assertIn("precio_base >= 60000000", where_clause)
        self.assertIn("precio_base <= 260000000", where_clause)
        self.assertIn("fecha_de_publicacion_del >= '2026-03-02T00:00:00.000'", where_clause)
        self.assertNotIn("fecha_de_recepcion_de >=", where_clause)
        self.assertIn("modalidad_de_contratacion", select_clause)

    async def test_repository_keeps_records_without_closing_date(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte y actualización del LMS institucional",
                closing_date=None,
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].closing_date_known)
        self.assertIn("SECOP no expone fecha de cierre", " ".join(results[0].risk_flags))

    async def test_repository_dedupes_similar_notices(self):
        pages = [[
            self._raw_item(
                "1",
                "Diseños digitales multimedia para campus virtual",
                "Producción de piezas para cursos del campus virtual",
                price="77000000",
                entity="ASOCIACIÓN COLOMBIANA DE PORCICULTORES",
            ),
            self._raw_item(
                "2",
                "Diseños digitales multimedia para campus virtual",
                "Producción de piezas para cursos del campus virtual",
                price="77000000",
                entity="ASOCIACIÓN COLOMBIANA DE PORCICULTORES",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=10)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual(len(results), 1)

    def _opensai_vs_generic_pages(self):
        return [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte, actualización, analítica de aprendizaje y accesibilidad WCAG",
                price="138754000",
                entity="INSTITUTO NACIONAL DE CANCEROLOGIA ESE",
            ),
            self._raw_item(
                "2",
                "Licenciamiento de antivirus corporativo",
                "Renovación de licenciamiento ESET PROTECT ELITE CLOUD",
                price="169985173",
                entity="MUNICIPIO DE RIONEGRO",
            ),
        ]]

    async def test_repository_opensai_scope_excludes_generic_it_noise(self):
        # Con scope=profile_only el universo OpenSAI excluye procesos IT que no
        # encajan en sus categorías (p. ej. antivirus genérico).
        transport, _ = _build_transport(self._opensai_vs_generic_pages())
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(
                min_budget=0, max_budget=500000000, limit=10, profile="opensai"
            )
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual([tender.id for tender in results], ["1"])
        self.assertGreaterEqual(results[0].match_score, 70)
        self.assertEqual(results[0].match_label, "Alto encaje")
        self.assertEqual(results[0].supplier_action_code, "present_offer")

    async def test_repository_generic_it_scope_keeps_full_it_universe(self):
        # generic_it = "Radar TI" mantiene todo lo IT (scope=all_it), incluso
        # procesos que no caen en ninguna categoría OpenSAI.
        transport, _ = _build_transport(self._opensai_vs_generic_pages())
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(
                min_budget=0, max_budget=500000000, limit=10, profile="generic_it"
            )
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual(sorted(tender.id for tender in results), ["1", "2"])

    async def test_repository_prioritizes_menor_cuantia_manifest_interest(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte, actualización y accesibilidad WCAG para el LMS institucional",
                price="140000000",
                phase="Presentación de oferta",
                modality="Licitación pública",
            ),
            self._raw_item(
                "2",
                "Soporte de campus virtual Moodle por menor cuantía",
                "Ajustes, capacitación y analítica de aprendizaje para aula virtual",
                price="90000000",
                phase="Manifestación de interés (Menor Cuantía)",
                modality="Menor cuantía",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=10)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual([item.id for item in results], ["2", "1"])
        self.assertEqual(results[0].supplier_action_code, "manifest_interest")
        self.assertEqual(results[0].supplier_action_label, "Manifestar interés ahora")
        self.assertEqual(results[0].supplier_action_rank, 0)
        self.assertIn("menor cuantía", " ".join(results[0].match_reasons).lower())

    async def test_repository_maps_observation_and_offer_actions(self):
        repo = self._repo()
        try:
            results = repo.map_raw_records(
                [
                    self._raw_item(
                        "1",
                        "Observaciones para campus virtual Moodle",
                        "Revisión de pliegos para LMS institucional",
                        phase="Presentación de observaciones",
                    ),
                    self._raw_item(
                        "2",
                        "Oferta para virtualización Linux KVM",
                        "Administración de infraestructura KVM y libvirt",
                        phase="Presentación de oferta",
                    ),
                ],
                profile="opensai",
            )
        finally:
            await repo.aclose()

        by_id = {item.id: item for item in results}
        self.assertEqual(by_id["1"].supplier_action_code, "observe")
        self.assertEqual(by_id["1"].supplier_action_label, "Observar pliegos")
        self.assertEqual(by_id["2"].supplier_action_code, "present_offer")
        self.assertEqual(by_id["2"].supplier_action_label, "Presentar oferta")

    async def test_repository_only_high_fit_filters_low_alignment(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte, actualización, analítica de aprendizaje y accesibilidad WCAG",
                price="138754000",
            ),
            self._raw_item(
                "2",
                "Licenciamiento de antivirus corporativo",
                "Renovación de licenciamiento ESET PROTECT ELITE CLOUD",
                price="169985173",
                entity="MUNICIPIO DE RIONEGRO",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(
                min_budget=0,
                max_budget=500000000,
                only_high_fit=True,
                limit=10,
            )
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual([item.id for item in results], ["1"])

    async def test_repository_filters_obvious_non_it_false_positives(self):
        pages = [[
            self._raw_item(
                "1",
                "Compra de papelería",
                "Suministro de papelería y útiles de oficina",
                price="90000000",
            ),
            self._raw_item(
                "2",
                "Administración de virtualización KVM",
                "Servicio de administración de servidores Linux con KVM y Libvirt",
                price="120000000",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=10)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual([item.id for item in results], ["2"])

    async def test_repository_keyword_filter_works_over_matching_payload(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte y actualización del LMS institucional",
            ),
            self._raw_item(
                "2",
                "Virtualización KVM y Linux",
                "Administración de infraestructura de centros de datos",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(
                min_budget=0,
                max_budget=500000000,
                keyword="moodle",
                limit=10,
            )
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual([item.id for item in results], ["1"])

    async def test_repository_uses_cache_on_repeat_call(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte y actualización del LMS institucional",
            ),
        ]]
        transport, calls = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = SocrataTenderRepository(
            client=client,
            page_size=5,
            max_pages=1,
            cache_ttl=60,
            snapshot_db_path=":memory:",
        )

        try:
            first = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
            second = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(calls["count"], 1)

    async def test_repository_retries_on_transient_failure(self):
        attempts = {"count": 0}
        payload = [self._raw_item("1", "Administración de campus virtual Moodle", "Soporte LMS")]

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
            snapshot_db_path=":memory:",
        )

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(results), 1)

    async def test_repository_rejects_unsafe_department_filter(self):
        repo = self._repo()

        with self.assertRaises(ValueError):
            await repo.search_by_criteria(
                min_budget=0,
                max_budget=500000000,
                department="Bogota'; DROP TABLE tenders",
            )

        await repo.aclose()

    async def test_repository_marks_first_seen_records_as_new(self):
        pages = [[
            self._raw_item(
                "1",
                "Administración de campus virtual Moodle",
                "Soporte y actualización del LMS institucional",
            ),
        ]]
        transport, _ = _build_transport(pages)
        client = httpx.AsyncClient(transport=transport)
        repo = self._repo(client=client, page_size=5, max_pages=1)

        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
        finally:
            await client.aclose()
            await repo.aclose()

        self.assertTrue(results[0].is_new)
        self.assertIsNotNone(results[0].first_seen_at)
        self.assertIsNotNone(results[0].last_seen_at)

    @unittest.skipUnless(
        os.getenv("RUN_LIVE_INTEGRATION") == "1",
        "Set RUN_LIVE_INTEGRATION=1 to execute the live Socrata integration test.",
    )
    async def test_live_socrata_repository_mapping(self):
        repo = SocrataTenderRepository(snapshot_db_path=":memory:")
        try:
            results = await repo.search_by_criteria(min_budget=0, max_budget=500000000, limit=5)
        finally:
            await repo.aclose()

        self.assertGreater(len(results), 0)
        item = results[0]
        self.assertIsInstance(item, Tender)
        self.assertIsInstance(item.closing_date, datetime)
        self.assertGreaterEqual(item.base_price, 0)


if __name__ == "__main__":
    unittest.main()
