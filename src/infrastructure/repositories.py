import logging
from datetime import datetime
from typing import Any, List, Optional

import requests

from src.application.validators import normalize_department
from src.domain.models import Tender, TenderRepository
from src.infrastructure.constants import IT_KEYWORD_PATTERN

logger = logging.getLogger(__name__)


class SocrataTenderRepository(TenderRepository):
    """Infrastructure Adapter: Consumes the Socrata API (SECOP II) to fetch tenders."""

    BASE_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"

    def __init__(
        self,
        session: Any = None,
        page_size: int = 100,
        max_pages: int = 20,
    ):
        self.session = session or requests
        self.page_size = page_size
        self.max_pages = max_pages

    def search_by_criteria(self,
                           max_budget: float,
                           department: Optional[str] = None,
                           limit: int = 1000) -> List[Tender]:
        """
        Queries the Socrata API in ordered pages until the filtered semantic limit is reached.
        """
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        results = []
        seen_ids = set()

        for page_number in range(self.max_pages):
            raw_page = self._fetch_page(
                max_budget=max_budget,
                department=normalized_department,
                limit=self.page_size,
                offset=page_number * self.page_size,
            )
            if not raw_page:
                break

            for tender in self._map_to_domain(raw_page):
                if tender.id in seen_ids:
                    continue
                seen_ids.add(tender.id)
                results.append(tender)
                if len(results) >= limit:
                    return sorted(results, key=lambda item: item.closing_date)[:limit]

            if len(raw_page) < self.page_size:
                break

        return sorted(results, key=lambda item: item.closing_date)[:limit]

    def fetch_raw_records(self,
                          max_budget: float,
                          department: Optional[str] = None,
                          limit: int = 1000) -> List[dict]:
        """Fetches raw ordered pages from SECOP II for compatibility use cases."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        raw_results: List[dict] = []

        for page_number in range(self.max_pages):
            remaining = limit - len(raw_results)
            if remaining <= 0:
                break

            page_limit = min(self.page_size, remaining)
            raw_page = self._fetch_page(
                max_budget=max_budget,
                department=normalized_department,
                limit=page_limit,
                offset=page_number * self.page_size,
            )
            if not raw_page:
                break

            raw_results.extend(raw_page)
            if len(raw_page) < page_limit:
                break

        return raw_results[:limit]

    def _build_where_clause(self, max_budget: float, department: str) -> str:
        today_iso = datetime.now().strftime("%Y-%m-%dT00:00:00.000")
        where_clause = (
            f"precio_base <= {max_budget} "
            f"AND estado_de_apertura_del_proceso = 'Abierto' "
            f"AND fecha_de_recepcion_de >= '{today_iso}'"
        )

        if department != "Todos":
            safe_department = department.replace("'", "''")
            where_clause += f" AND departamento_entidad = '{safe_department}'"

        return where_clause

    def _fetch_page(self, max_budget: float, department: str, limit: int, offset: int) -> List[dict]:
        params = {
            "$where": self._build_where_clause(max_budget, department),
            "$limit": limit,
            "$offset": offset,
            "$order": "fecha_de_recepcion_de ASC, precio_base DESC",
        }
        headers = {
            "User-Agent": "RNS/2.1 (+https://github.com/Open-Source-Academic-Initiative/RNS)"
        }

        try:
            response = self.session.get(self.BASE_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("Infrastructure Error (Socrata): %s", exc)
            return []

    def _map_to_domain(self, data: List[dict]) -> List[Tender]:
        results = []
        for item in data:
            name = item.get('nombre_del_procedimiento', '')
            description = item.get('descripci_n_del_procedimiento', '')
            analysis_text = f"{name} {description}"

            # Domain Filtering (IT Only)
            if IT_KEYWORD_PATTERN.search(analysis_text):
                try:
                    # Safe date extraction and cleaning
                    pub_date_str = item.get('fecha_de_publicacion_del', '').split('T')[0]
                    closing_date_str = item.get('fecha_de_recepcion_de', '').split('T')[0]
                    
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d') if pub_date_str else datetime.min
                    closing_date = datetime.strptime(closing_date_str, '%Y-%m-%d') if closing_date_str else datetime.max
                    
                    # Safe URL extraction (can be dict or str)
                    raw_url = item.get('urlproceso', '#')
                    final_url = raw_url.get('url', '#') if isinstance(raw_url, dict) else raw_url

                    tender = Tender(
                        id=item.get('id_del_proceso', 'N/A'),
                        reference=item.get('referencia_del_proceso', 'N/A'),
                        entity=item.get('entidad', 'N/A'),
                        name=name,
                        description=description,
                        base_price=float(item.get('precio_base', 0)),
                        publish_date=pub_date,
                        closing_date=closing_date,
                        url=final_url,
                        department=item.get('departamento_entidad'),
                        status=item.get('estado_de_apertura_del_proceso', 'Unknown')
                    )
                    results.append(tender)
                except (ValueError, TypeError):
                    # Silenced mapping error log to avoid breaking flow
                    continue
        
        # Sort by Closing Date (Urgency)
        return sorted(results, key=lambda x: x.closing_date)
