import os
import unittest
from datetime import datetime, timedelta

import httpx

from src.application.validators import (
    normalize_department,
    normalize_phase,
    normalize_process_status,
    normalize_profile,
)
from src.domain.models import Tender
from src.presentation.web import _stream_csv, app, get_tender_service


class StubTenderService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(
        self,
        budget: float,
        min_budget: float = 0,
        department: str | None = None,
        keyword: str | None = None,
        process_status: str | None = None,
        phase: str | None = None,
        published_since_days: int = 60,
        profile: str = "opensai",
        only_high_fit: bool = False,
        only_new: bool = False,
    ):
        normalized_department = normalize_department(department)
        normalized_process_status = normalize_process_status(process_status)
        normalized_phase = normalize_phase(phase)
        normalized_profile = normalize_profile(profile)
        self.calls.append(
            {
                "budget": budget,
                "min_budget": min_budget,
                "department": normalized_department,
                "keyword": keyword,
                "process_status": normalized_process_status,
                "phase": normalized_phase,
                "published_since_days": published_since_days,
                "profile": normalized_profile,
                "only_high_fit": only_high_fit,
                "only_new": only_new,
            }
        )
        tenders = [
            Tender(
                id="WEB-001",
                cluster_id="cluster-1",
                reference="REF-WEB-001",
                entity="Instituto Nacional de Cancerología ESE",
                name="Administración de campus virtual Moodle",
                description="Soporte y mantenimiento del campus virtual institucional.",
                base_price=138754000.0,
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=7),
                url="https://example.test/process/WEB-001",
                department=normalized_department,
                status="Publicado",
                opening_status="Abierto",
                phase="Presentación de oferta",
                modality="Licitación pública",
                supplier_action_code="present_offer",
                supplier_action_label="Presentar oferta",
                supplier_action_detail="Preparar y radicar oferta formal antes de la fecha y hora de cierre.",
                supplier_action_rank=10,
                profile=normalized_profile,
                match_score=92.0,
                match_label="Alto encaje",
                match_reasons=["LMS / educación virtual", "Universidad o institución educativa"],
                risk_flags=[],
                freshness_score=14.0,
                days_since_publication=2,
                is_new=True,
                first_seen_at=datetime.now(),
                last_seen_at=datetime.now(),
            ),
            Tender(
                id="WEB-002",
                cluster_id="cluster-2",
                reference="REF-WEB-002",
                entity="ASOCIACIÓN COLOMBIANA DE PORCICULTORES",
                name="Gobernanza de datos y tableros de control",
                description="Data lake, capacitación y tableros de control.",
                base_price=74946666.0,
                publish_date=datetime.now() - timedelta(days=4),
                closing_date=datetime.now() + timedelta(days=10),
                url="https://example.test/process/WEB-002",
                department=normalized_department,
                status="Publicado",
                opening_status="Abierto",
                phase="Fase de ofertas",
                modality="Selección abreviada",
                supplier_action_code="present_offer",
                supplier_action_label="Presentar oferta",
                supplier_action_detail="Preparar y radicar oferta formal antes de la fecha y hora de cierre.",
                supplier_action_rank=10,
                profile=normalized_profile,
                match_score=81.0,
                match_label="Alto encaje",
                match_reasons=["Datos / BI / ML", "Publicado hace 4 días"],
                risk_flags=["SECOP no expone fecha de cierre; requiere validación manual"] if only_new else [],
                freshness_score=11.0,
                days_since_publication=4,
                is_new=False,
                first_seen_at=datetime.now() - timedelta(days=2),
                last_seen_at=datetime.now(),
            ),
            Tender(
                id="WEB-003",
                cluster_id="cluster-3",
                reference="REF-WEB-003",
                entity="Municipio de Rionegro",
                name="Licenciamiento de antivirus corporativo",
                description="Renovación ESET PROTECT ELITE CLOUD.",
                base_price=169985173.0,
                publish_date=datetime.now() - timedelta(days=12),
                closing_date=datetime.now() + timedelta(days=4),
                url="https://example.test/process/WEB-003",
                department=normalized_department,
                status="Publicado",
                opening_status="Abierto",
                phase="Presentación de oferta",
                modality="Selección abreviada",
                supplier_action_code="present_offer",
                supplier_action_label="Presentar oferta",
                supplier_action_detail="Preparar y radicar oferta formal antes de la fecha y hora de cierre.",
                supplier_action_rank=10,
                profile=normalized_profile,
                match_score=28.0,
                match_label="Bajo encaje",
                match_reasons=["Infraestructura / seguridad"],
                risk_flags=["Vendor lock-in o compra cerrada"],
                freshness_score=9.0,
                days_since_publication=12,
                is_new=False,
                first_seen_at=datetime.now() - timedelta(days=8),
                last_seen_at=datetime.now(),
            ),
        ]
        if normalized_process_status != "Todos":
            tenders = [t for t in tenders if t.status == normalized_process_status]
        if normalized_phase != "Todos":
            tenders = [t for t in tenders if t.phase == normalized_phase]
        if keyword:
            needle = keyword.lower()
            tenders = [
                t
                for t in tenders
                if needle in " ".join([t.name, t.description, " ".join(t.match_reasons)]).lower()
            ]
        if only_high_fit:
            tenders = [t for t in tenders if t.match_score >= 70]
        if only_new:
            tenders = [t for t in tenders if t.is_new]
        return tenders


_stub_instance = StubTenderService()


def override_tender_service():
    return _stub_instance


class TestWebInterface(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.dependency_overrides[get_tender_service] = override_tender_service
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://testserver")
        _stub_instance.calls.clear()

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_home_page_loads(self):
        response = await self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("RNS · Radar OpenSAI", response.text)
        self.assertIn("Parámetros de Priorización", response.text)
        self.assertIn("Solo alto encaje", response.text)
        self.assertIn("Últimos 60 días", response.text)
        self.assertIn('<select name="department"', response.text)
        self.assertIn('<option value="Todos" selected>Todos</option>', response.text)
        self.assertIn('<option value="Distrito Capital de Bogotá"', response.text)

    async def test_search_endpoint_renders_results(self):
        response = await self.client.get("/search?budget=260000000&min_budget=60000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Oportunidades priorizadas: 3", response.text)
        self.assertIn("Instituto Nacional de Cancerología ESE", response.text)
        self.assertIn("Alto encaje", response.text)
        self.assertIn("Presentar oferta", response.text)
        self.assertIn("Exportar CSV enriquecido", response.text)

    async def test_frontend_is_local_and_avoids_modal_inline_handlers(self):
        response = await self.client.get("/search?budget=260000000&min_budget=60000000&department=Todos")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cdn.tailwindcss.com", response.text)
        self.assertNotIn('onclick="openModal', response.text)
        self.assertIn("data-description=", response.text)

    async def test_search_threads_new_filters_to_service(self):
        response = await self.client.get(
            "/search?budget=260000000&min_budget=60000000&department=Atlantico&profile=opensai"
            "&published_since_days=45&only_high_fit=true&only_new=true&keyword=moodle"
        )

        self.assertEqual(response.status_code, 200)
        last_call = _stub_instance.calls[-1]
        self.assertEqual(last_call["department"], "Atlántico")
        self.assertEqual(last_call["min_budget"], 60000000)
        self.assertEqual(last_call["published_since_days"], 45)
        self.assertEqual(last_call["profile"], "opensai")
        self.assertTrue(last_call["only_high_fit"])
        self.assertTrue(last_call["only_new"])
        self.assertEqual(last_call["keyword"], "moodle")

    async def test_search_can_select_bogota_department(self):
        response = await self.client.get(
            "/search?budget=260000000&min_budget=60000000&department=Bogot%C3%A1&profile=opensai"
        )

        self.assertEqual(response.status_code, 200)
        last_call = _stub_instance.calls[-1]
        self.assertEqual(last_call["department"], "Distrito Capital de Bogotá")
        self.assertIn('<option value="Distrito Capital de Bogotá" selected>', response.text)

    async def test_search_filters_by_phase(self):
        response = await self.client.get(
            "/search?budget=260000000&min_budget=0&department=Todos&phase=Fase%20de%20ofertas&only_high_fit=false"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Oportunidades priorizadas: 1", response.text)
        self.assertIn("Gobernanza de datos y tableros de control", response.text)

    async def test_pagination_controls_render(self):
        response = await self.client.get("/search?budget=260000000&min_budget=0&department=Todos&only_high_fit=false&per_page=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Página 1 de 3", response.text)
        self.assertIn("Siguiente →", response.text)

    async def test_search_sorts_full_result_set_before_pagination(self):
        first_page = await self.client.get(
            "/search?budget=260000000&min_budget=0&department=Todos&only_high_fit=false"
            "&sort_by=base_price&sort_dir=desc&per_page=1"
        )
        second_page = await self.client.get(
            "/search?budget=260000000&min_budget=0&department=Todos&only_high_fit=false"
            "&sort_by=base_price&sort_dir=desc&per_page=1&page=2"
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertIn("Municipio de Rionegro", first_page.text)
        self.assertEqual(second_page.status_code, 200)
        self.assertIn("Instituto Nacional de Cancerología ESE", second_page.text)

    async def test_csv_export_returns_enriched_csv(self):
        response = await self.client.get("/search.csv?budget=260000000&min_budget=0&department=Todos&only_high_fit=false")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))
        body = response.text
        self.assertIn("cluster_id,reference,entity", body)
        self.assertIn("match_score", body)
        self.assertIn("supplier_action_label", body)
        self.assertIn("WEB-001", body)
        self.assertIn("Alto encaje", body)
        self.assertIn("Presentar oferta", body)

    async def test_api_search_returns_json_payload(self):
        response = await self.client.get("/api/search?budget=260000000&min_budget=0&department=Todos&only_high_fit=false")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        body = response.json()
        self.assertEqual(body["pagination"]["total"], 3)
        self.assertEqual(body["filters"]["profile"], "opensai")
        first = body["results"][0]
        for required_key in (
            "id",
            "entity",
            "match_score",
            "match_reasons",
            "risk_flags",
            "is_new",
            "first_seen_at",
            "supplier_action_code",
            "supplier_action_label",
            "supplier_action_detail",
            "supplier_action_rank",
            "modality",
            "opening_status",
        ):
            self.assertIn(required_key, first)

    async def test_api_search_honors_only_high_fit(self):
        response = await self.client.get("/api/search?budget=260000000&min_budget=0&department=Todos&only_high_fit=true")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pagination"]["total"], 2)
        self.assertTrue(all(item["match_score"] >= 70 for item in body["results"]))

    async def test_invalid_department_returns_validation_error(self):
        response = await self.client.get("/search?budget=260000000&min_budget=0&department=DROP%27%20TABLE")

        self.assertEqual(response.status_code, 400)
        self.assertIn("departamento", response.text.lower())

    async def test_template_exists(self):
        self.assertTrue(os.path.exists("templates/index.html"))

    async def test_healthz_returns_ok(self):
        response = await self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("version", body)

    async def test_static_css_is_served(self):
        response = await self.client.get("/static/style.css")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/css"))
        self.assertIn(".score-card", response.text)
        self.assertIn(".pill--action", response.text)

    async def test_index_links_external_stylesheet(self):
        response = await self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/static/style.css"', response.text)
        self.assertNotIn("<style>", response.text)

    async def test_stream_csv_yields_one_chunk_per_row(self):
        tenders = [
            Tender(
                id=f"STR-{idx}",
                cluster_id=f"cluster-{idx}",
                reference=f"REF-STR-{idx}",
                entity=f"Stream Entity {idx}",
                name=f"Procedimiento {idx}",
                description="desc",
                base_price=1000.0 * idx,
                publish_date=datetime(2026, 4, 1),
                closing_date=datetime(2026, 5, idx + 1),
                url="https://example.test",
                department="Todos",
                status="Publicado",
                phase="Presentación de oferta",
                profile="opensai",
                match_score=80 - idx,
                match_label="Alto encaje",
                match_reasons=["LMS / educación virtual"],
                risk_flags=[],
                freshness_score=10,
                is_new=idx == 1,
            )
            for idx in range(1, 4)
        ]

        chunks = list(_stream_csv(tenders))

        self.assertEqual(len(chunks), len(tenders) + 1)
        self.assertTrue(chunks[0].startswith("id,cluster_id,reference"))
        self.assertIn("STR-1", chunks[1])
        self.assertIn("Alto encaje", chunks[1])


if __name__ == "__main__":
    unittest.main()
