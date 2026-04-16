import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from src.application.validators import DEFAULT_DEPARTMENT, normalize_department
from src.domain.models import Tender, TenderRepository
from src.infrastructure.constants import IT_KEYWORD_PATTERN, SOCRATA_LIKE_SEEDS

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 20
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TIMEZONE = "America/Bogota"
DEFAULT_URL = "#"
DEFAULT_IDENTIFIER = "N/A"
UNKNOWN_STATUS = "Unknown"
DEFAULT_ORDER_BY = "fecha_de_recepcion_de ASC, precio_base DESC"
DATE_FORMAT = "%Y-%m-%d"
SODA_DATE_FORMAT = "%Y-%m-%dT00:00:00.000"
USER_AGENT = "RNS/2.2 (+https://github.com/Open-Source-Academic-Initiative/RNS)"


class _TTLCache:
    """Tiny in-process TTL cache using time.monotonic for expiry."""

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._entries: dict[Any, Tuple[float, Any]] = {}

    def get(self, key: Any) -> Optional[Any]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        self._entries[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._entries.clear()


class SocrataTenderRepository(TenderRepository):
    """Infrastructure Adapter: Consumes the Socrata API (SECOP II) to fetch tenders."""

    BASE_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        timezone_name: str = DEFAULT_TIMEZONE,
    ):
        self._injected_client = client
        self._client: Optional[httpx.AsyncClient] = client
        self.page_size = page_size
        self.max_pages = max_pages
        self.max_retries = max(1, max_retries)
        self.backoff_base = backoff_base
        self._tz = ZoneInfo(timezone_name)
        self._cache = _TTLCache(cache_ttl)

    async def aclose(self) -> None:
        """Release the internally-managed HTTP client, if any."""
        if self._client is not None and self._injected_client is None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
        return self._client

    async def search_by_criteria(
        self,
        max_budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Tender]:
        """Fetches active IT tenders using concurrent SECOP II pages."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        normalized_keyword = self._normalize_keyword(keyword)

        cache_key = (max_budget, normalized_department, normalized_keyword)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached[:limit]

        raw_pages = await self._fetch_all_pages(max_budget, normalized_department)

        matching_tenders: List[Tender] = []
        seen_ids: set[str] = set()
        for raw_page in raw_pages:
            for tender in self.map_raw_records(raw_page):
                if tender.id in seen_ids:
                    continue
                if normalized_keyword and not self._matches_keyword(tender, normalized_keyword):
                    continue
                seen_ids.add(tender.id)
                matching_tenders.append(tender)

        self._cache.set(cache_key, matching_tenders)
        return matching_tenders[:limit]

    async def fetch_raw_records(
        self,
        max_budget: float,
        department: Optional[str] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """Fetches raw ordered pages from SECOP II for compatibility use cases."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        raw_pages = await self._fetch_all_pages(max_budget, normalized_department)

        raw_results: List[dict] = []
        for page in raw_pages:
            raw_results.extend(page)
            if len(raw_results) >= limit:
                break

        return raw_results[:limit]

    def map_raw_records(self, raw_records: Iterable[dict]) -> List[Tender]:
        """Maps raw SECOP II records into sorted domain entities."""
        tenders: List[Tender] = []
        for raw_record in raw_records:
            tender = self._build_tender(raw_record)
            if tender is not None:
                tenders.append(tender)
        return sorted(tenders, key=lambda item: item.closing_date)

    async def _fetch_all_pages(
        self,
        max_budget: float,
        department: str,
    ) -> List[List[dict]]:
        tasks = [
            self._fetch_page(
                max_budget=max_budget,
                department=department,
                limit=self.page_size,
                offset=page_number * self.page_size,
            )
            for page_number in range(self.max_pages)
        ]
        pages = await asyncio.gather(*tasks)

        truncated: List[List[dict]] = []
        for page in pages:
            truncated.append(page)
            if len(page) < self.page_size:
                break
        return truncated

    async def _fetch_page(
        self,
        max_budget: float,
        department: str,
        limit: int,
        offset: int,
    ) -> List[dict]:
        params: dict[str, Any] = {
            "$where": self._build_where_clause(max_budget, department),
            "$limit": limit,
            "$offset": offset,
            "$order": DEFAULT_ORDER_BY,
        }
        headers = {"User-Agent": USER_AGENT}
        client = self._ensure_client()

        for attempt in range(self.max_retries):
            try:
                response = await client.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, list) else []
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt == self.max_retries - 1:
                    logger.warning(
                        "Socrata fetch failed after %d attempts (offset=%d): %s",
                        self.max_retries,
                        offset,
                        exc,
                    )
                    return []
                await asyncio.sleep(self.backoff_base * (2 ** attempt))
        return []

    def _build_where_clause(self, max_budget: float, department: str) -> str:
        today_iso = datetime.now(self._tz).strftime(SODA_DATE_FORMAT)
        clauses = [
            f"precio_base <= {max_budget}",
            "estado_de_apertura_del_proceso = 'Abierto'",
            f"fecha_de_recepcion_de >= '{today_iso}'",
        ]
        if department != DEFAULT_DEPARTMENT:
            safe_department = department.replace("'", "''")
            clauses.append(f"departamento_entidad = '{safe_department}'")

        seed_clause = self._build_seed_clause()
        if seed_clause:
            clauses.append(seed_clause)

        return " AND ".join(clauses)

    def _build_seed_clause(self) -> str:
        """Builds an OR chain of UPPER(col) LIKE '%SEED%' to prefilter at Socrata."""
        if not SOCRATA_LIKE_SEEDS:
            return ""
        like_fragments: list[str] = []
        for raw_seed in SOCRATA_LIKE_SEEDS:
            safe_seed = raw_seed.replace("'", "''").upper()
            like_fragments.append(f"UPPER(nombre_del_procedimiento) LIKE '%{safe_seed}%'")
            like_fragments.append(f"UPPER(descripci_n_del_procedimiento) LIKE '%{safe_seed}%'")
        return "(" + " OR ".join(like_fragments) + ")"

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

    def _matches_keyword(self, tender: Tender, keyword: str) -> bool:
        haystack = f"{tender.name} {tender.description} {tender.entity}".lower()
        return keyword in haystack

    def _normalize_keyword(self, keyword: Optional[str]) -> Optional[str]:
        if keyword is None:
            return None
        trimmed = keyword.strip().lower()
        return trimmed or None

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
