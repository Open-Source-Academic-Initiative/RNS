import logging
from datetime import datetime
from typing import Any, Iterable, List, Optional

import requests

from src.application.validators import DEFAULT_DEPARTMENT, normalize_department
from src.domain.models import Tender, TenderRepository
from src.infrastructure.constants import IT_KEYWORD_PATTERN

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 20
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_URL = "#"
DEFAULT_IDENTIFIER = "N/A"
UNKNOWN_STATUS = "Unknown"
DEFAULT_ORDER_BY = "fecha_de_recepcion_de ASC, precio_base DESC"
DATE_FORMAT = "%Y-%m-%d"
SODA_DATE_FORMAT = "%Y-%m-%dT00:00:00.000"
USER_AGENT = "RNS/2.1 (+https://github.com/Open-Source-Academic-Initiative/RNS)"


class SocrataTenderRepository(TenderRepository):
    """Infrastructure Adapter: Consumes the Socrata API (SECOP II) to fetch tenders."""

    BASE_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"

    def __init__(
        self,
        session: Any = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ):
        self.session = session or requests
        self.page_size = page_size
        self.max_pages = max_pages

    def search_by_criteria(self,
                           max_budget: float,
                           department: Optional[str] = None,
                           limit: int = 1000) -> List[Tender]:
        """Fetches active IT tenders using ordered SECOP II pages."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        matching_tenders: List[Tender] = []
        seen_tender_ids = set()

        for raw_page in self._iter_raw_pages(max_budget, normalized_department):
            for tender in self.map_raw_records(raw_page):
                if tender.id in seen_tender_ids:
                    continue
                seen_tender_ids.add(tender.id)
                matching_tenders.append(tender)
                if len(matching_tenders) >= limit:
                    return matching_tenders[:limit]

        return matching_tenders[:limit]

    def fetch_raw_records(self,
                          max_budget: float,
                          department: Optional[str] = None,
                          limit: int = 1000) -> List[dict]:
        """Fetches raw ordered pages from SECOP II for compatibility use cases."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        raw_results: List[dict] = []

        for raw_page in self._iter_raw_pages(max_budget, normalized_department, raw_limit=limit):
            raw_results.extend(raw_page)

        return raw_results[:limit]

    def map_raw_records(self, raw_records: Iterable[dict]) -> List[Tender]:
        """Maps raw SECOP II records into sorted domain entities."""
        tenders: List[Tender] = []

        for raw_record in raw_records:
            tender = self._build_tender(raw_record)
            if tender is not None:
                tenders.append(tender)

        return sorted(tenders, key=lambda item: item.closing_date)

    def _build_where_clause(self, max_budget: float, department: str) -> str:
        today_iso = datetime.now().strftime(SODA_DATE_FORMAT)
        where_clause = (
            f"precio_base <= {max_budget} "
            f"AND estado_de_apertura_del_proceso = 'Abierto' "
            f"AND fecha_de_recepcion_de >= '{today_iso}'"
        )

        if department != DEFAULT_DEPARTMENT:
            safe_department = department.replace("'", "''")
            where_clause += f" AND departamento_entidad = '{safe_department}'"

        return where_clause

    def _iter_raw_pages(
        self,
        max_budget: float,
        department: str,
        raw_limit: Optional[int] = None,
    ) -> Iterable[List[dict]]:
        collected_raw_records = 0

        for page_number in range(self.max_pages):
            if raw_limit is not None and collected_raw_records >= raw_limit:
                break

            page_limit = self.page_size
            if raw_limit is not None:
                page_limit = min(self.page_size, raw_limit - collected_raw_records)

            raw_page = self._fetch_page(
                max_budget=max_budget,
                department=department,
                limit=page_limit,
                offset=page_number * self.page_size,
            )
            if not raw_page:
                break

            yield raw_page
            collected_raw_records += len(raw_page)

            if len(raw_page) < page_limit:
                break

    def _fetch_page(self, max_budget: float, department: str, limit: int, offset: int) -> List[dict]:
        params = {
            "$where": self._build_where_clause(max_budget, department),
            "$limit": limit,
            "$offset": offset,
            "$order": DEFAULT_ORDER_BY,
        }
        headers = {"User-Agent": USER_AGENT}

        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Infrastructure Error (Socrata): %s", exc)
            return []

    def _build_tender(self, raw_record: dict) -> Optional[Tender]:
        procedure_name = raw_record.get("nombre_del_procedimiento", "")
        procedure_description = raw_record.get("descripci_n_del_procedimiento", "")

        if not self._matches_it_keywords(procedure_name, procedure_description):
            return None

        try:
            return Tender(
                id=raw_record.get("id_del_proceso", DEFAULT_IDENTIFIER),
                reference=raw_record.get("referencia_del_proceso", DEFAULT_IDENTIFIER),
                entity=raw_record.get("entidad", DEFAULT_IDENTIFIER),
                name=procedure_name,
                description=procedure_description,
                base_price=float(raw_record.get("precio_base", 0)),
                publish_date=self._parse_date(raw_record.get("fecha_de_publicacion_del"), datetime.min),
                closing_date=self._parse_date(raw_record.get("fecha_de_recepcion_de"), datetime.max),
                url=self._extract_url(raw_record.get("urlproceso", DEFAULT_URL)),
                department=raw_record.get("departamento_entidad"),
                status=raw_record.get("estado_de_apertura_del_proceso", UNKNOWN_STATUS),
            )
        except (TypeError, ValueError):
            return None

    def _matches_it_keywords(self, procedure_name: str, procedure_description: str) -> bool:
        analysis_text = f"{procedure_name} {procedure_description}"
        return IT_KEYWORD_PATTERN.search(analysis_text) is not None

    def _parse_date(self, raw_date: Optional[str], fallback: datetime) -> datetime:
        if not raw_date:
            return fallback

        normalized_date = raw_date.split("T")[0]
        if not normalized_date:
            return fallback

        return datetime.strptime(normalized_date, DATE_FORMAT)

    def _extract_url(self, raw_url: Any) -> str:
        if isinstance(raw_url, dict):
            return raw_url.get("url", DEFAULT_URL)
        return raw_url or DEFAULT_URL
