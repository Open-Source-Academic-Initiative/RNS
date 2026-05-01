import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx
from prometheus_client import Counter, Histogram

from src.application.validators import (
    DEFAULT_DEPARTMENT,
    DEFAULT_PHASE,
    DEFAULT_PROCESS_STATUS,
    normalize_department,
    normalize_phase,
    normalize_process_status,
    normalize_profile,
)
from src.domain.models import Tender, TenderRepository
from src.infrastructure.constants import (
    GENERIC_NEGATIVE_PATTERN,
    IT_KEYWORD_PATTERN,
    MATCH_PROFILES,
    SOCRATA_LIKE_SEEDS,
)

logger = logging.getLogger(__name__)

# Metrics Definition
SOCRATA_REQUESTS_TOTAL = Counter(
    "rns_socrata_requests_total",
    "Total Socrata API requests by method and status",
    ["method", "status_code"],
)
SOCRATA_REQUEST_DURATION_SECONDS = Histogram(
    "rns_socrata_request_duration_seconds",
    "Socrata API request latency in seconds",
    ["method"],
)
SOCRATA_ERRORS_TOTAL = Counter(
    "rns_socrata_errors_total",
    "Total Socrata API errors by exception type",
    ["exception_type"],
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


DEFAULT_PAGE_SIZE = _env_int("RNS_PAGE_SIZE", 100)
DEFAULT_SEARCH_LIMIT = _env_int("RNS_SEARCH_LIMIT", 10000)
DEFAULT_MAX_PAGES = _env_int("RNS_MAX_PAGES", 100)
DEFAULT_PAGE_BATCH_SIZE = _env_int("RNS_PAGE_BATCH_SIZE", 4)
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CACHE_TTL_SECONDS = float(_env_int("RNS_CACHE_TTL_SECONDS", 300))
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TIMEZONE = os.getenv("RNS_TIMEZONE", "America/Bogota")
DEFAULT_PUBLISHED_SINCE_DAYS = _env_int("RNS_PUBLISHED_SINCE_DAYS", 60)
DEFAULT_NEWNESS_HOURS = _env_int("RNS_NEWNESS_HOURS", 48)
DEFAULT_MAX_SEED_CLAUSE_LENGTH = 6000
DEFAULT_URL = "#"
DEFAULT_IDENTIFIER = "N/A"
UNKNOWN_STATUS = "Unknown"
DEFAULT_ORDER_BY = "fecha_de_publicacion_del DESC, precio_base DESC"
DATE_FORMAT = "%Y-%m-%d"
SODA_DATE_FORMAT = "%Y-%m-%dT00:00:00.000"
USER_AGENT = "RNS/3.0 (+https://github.com/Open-Source-Academic-Initiative/RNS)"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DB_PATH = os.getenv(
    "RNS_SNAPSHOT_DB_PATH",
    str(PROJECT_ROOT / "data" / "rns_snapshots.sqlite3"),
)
SECOP_SELECT_FIELDS = (
    "id_del_proceso",
    "referencia_del_proceso",
    "entidad",
    "nombre_del_procedimiento",
    "descripci_n_del_procedimiento",
    "precio_base",
    "fecha_de_publicacion_del",
    "fecha_de_recepcion_de",
    "urlproceso",
    "departamento_entidad",
    "modalidad_de_contratacion",
    "fase",
    "estado_de_apertura_del_proceso",
    "estado_del_procedimiento",
)
SECOP_SELECT_CLAUSE = ", ".join(SECOP_SELECT_FIELDS)

ACTION_MANIFEST_INTEREST = "manifest_interest"
ACTION_PRESENT_OFFER = "present_offer"
ACTION_OBSERVE = "observe"
ACTION_PREQUALIFY = "prequalify"
ACTION_FOLLOW_UP = "follow_up"
ACTION_REVIEW = "review"
ACTION_NOT_OPEN = "not_open"
ACTION_EXPIRED = "expired"

MENOR_CUANTIA_MARKERS = ("menor cuantia", "menor cuantía")
MANIFEST_INTEREST_PHASES = {
    "Manifestación de interés (Menor Cuantía)",
}
PRESENT_OFFER_PHASES = {
    "Presentación de oferta",
    "Fase de ofertas",
    "Proceso de ofertas",
    "Fase de Selección (Presentación de ofertas)",
}
OBSERVATION_PHASES = {
    "Presentación de observaciones",
    "Presentación de observaciones (precalificación)",
}
PREQUALIFICATION_PHASES = {
    "Pré-Calificación de competidores",
    "Presentación de oferta (precalificación)",
}
FOLLOW_UP_PHASES = {
    "Clarification submission",
    "Estimate Phase",
    "Selección de ofertas (borrador)",
    "Fase de Concurso",
}


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


class _SnapshotStore:
    """Small SQLite store to track first-seen and last-seen opportunities."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tender_snapshots (
                cluster_id TEXT PRIMARY KEY,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_payload_hash TEXT NOT NULL,
                last_id TEXT NOT NULL,
                last_url TEXT NOT NULL,
                last_name TEXT NOT NULL,
                profile TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def observe(
        self,
        tender: Tender,
        *,
        payload_hash: str,
        seen_at: datetime,
        profile: str,
    ) -> tuple[datetime, datetime, bool]:
        row = self._conn.execute(
            """
            SELECT first_seen_at, last_seen_at
            FROM tender_snapshots
            WHERE cluster_id = ?
            """,
            (tender.cluster_id,),
        ).fetchone()
        seen_at_raw = seen_at.isoformat()
        if row is None:
            self._conn.execute(
                """
                INSERT INTO tender_snapshots (
                    cluster_id, first_seen_at, last_seen_at, last_payload_hash,
                    last_id, last_url, last_name, profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tender.cluster_id,
                    seen_at_raw,
                    seen_at_raw,
                    payload_hash,
                    tender.id,
                    tender.url,
                    tender.name,
                    profile,
                ),
            )
            self._conn.commit()
            return seen_at, seen_at, True

        first_seen_at = datetime.fromisoformat(row[0])
        self._conn.execute(
            """
            UPDATE tender_snapshots
            SET last_seen_at = ?, last_payload_hash = ?, last_id = ?, last_url = ?, last_name = ?, profile = ?
            WHERE cluster_id = ?
            """,
            (
                seen_at_raw,
                payload_hash,
                tender.id,
                tender.url,
                tender.name,
                profile,
                tender.cluster_id,
            ),
        )
        self._conn.commit()
        is_new = (seen_at - first_seen_at) <= timedelta(hours=DEFAULT_NEWNESS_HOURS)
        return first_seen_at, seen_at, is_new

    def close(self) -> None:
        self._conn.close()


class SocrataTenderRepository(TenderRepository):
    """Infrastructure Adapter: Consumes SECOP II and enriches matches for OpenSAI."""

    BASE_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        page_batch_size: int = DEFAULT_PAGE_BATCH_SIZE,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        timezone_name: str = DEFAULT_TIMEZONE,
        snapshot_db_path: str = DEFAULT_SNAPSHOT_DB_PATH,
    ):
        self._injected_client = client
        self._client: Optional[httpx.AsyncClient] = client
        self.page_size = max(1, page_size)
        self.max_pages = max(1, max_pages)
        self.page_batch_size = max(1, page_batch_size)
        self.max_retries = max(1, max_retries)
        self.backoff_base = backoff_base
        self._tz = ZoneInfo(timezone_name)
        self._cache = _TTLCache(cache_ttl)
        self._seed_clause = self._build_seed_clause()
        self._snapshot_store = _SnapshotStore(snapshot_db_path)
        if len(self._seed_clause) > DEFAULT_MAX_SEED_CLAUSE_LENGTH:
            logger.warning(
                "Socrata seed clause length (%d chars) exceeds %d; disabling remote seed prefilter.",
                len(self._seed_clause),
                DEFAULT_MAX_SEED_CLAUSE_LENGTH,
            )
            self._seed_clause = ""

    async def aclose(self) -> None:
        """Release managed resources."""
        if self._client is not None and self._injected_client is None:
            await self._client.aclose()
            self._client = None
        self._snapshot_store.close()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
        return self._client

    async def search_by_criteria(
        self,
        min_budget: float,
        max_budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        process_status: Optional[str] = None,
        phase: Optional[str] = None,
        published_since_days: int = DEFAULT_PUBLISHED_SINCE_DAYS,
        profile: str = "opensai",
        only_high_fit: bool = False,
        only_new: bool = False,
    ) -> List[Tender]:
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        normalized_keyword = self._normalize_keyword(keyword)
        normalized_process_status = normalize_process_status(process_status)
        normalized_phase = normalize_phase(phase)
        normalized_profile = normalize_profile(profile)

        cache_key = (
            min_budget,
            max_budget,
            normalized_department,
            normalized_keyword,
            normalized_process_status,
            normalized_phase,
            published_since_days,
            normalized_profile,
            only_high_fit,
            only_new,
            limit,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached[:limit]

        raw_pages = await self._fetch_all_pages(
            min_budget=min_budget,
            max_budget=max_budget,
            department=normalized_department,
            process_status=normalized_process_status,
            phase=normalized_phase,
            published_since_days=published_since_days,
            raw_limit=limit,
        )
        raw_records = [record for page in raw_pages for record in page]
        results = self._enrich_results(
            raw_records,
            keyword=normalized_keyword,
            profile_name=normalized_profile,
            only_high_fit=only_high_fit,
            only_new=only_new,
        )
        ranked = self._rank_results(results)
        self._cache.set(cache_key, ranked)
        return ranked[:limit]

    async def fetch_raw_records(
        self,
        max_budget: float,
        department: Optional[str] = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        process_status: Optional[str] = None,
        phase: Optional[str] = None,
        min_budget: float = 0,
        published_since_days: int = DEFAULT_PUBLISHED_SINCE_DAYS,
    ) -> List[dict]:
        """Fetches raw ordered pages from SECOP II for compatibility use cases."""
        if limit <= 0:
            return []

        normalized_department = normalize_department(department)
        normalized_process_status = normalize_process_status(process_status)
        normalized_phase = normalize_phase(phase)
        raw_pages = await self._fetch_all_pages(
            min_budget=min_budget,
            max_budget=max_budget,
            department=normalized_department,
            process_status=normalized_process_status,
            phase=normalized_phase,
            published_since_days=published_since_days,
            raw_limit=limit,
        )
        raw_results: List[dict] = []
        for page in raw_pages:
            raw_results.extend(page)
            if len(raw_results) >= limit:
                break
        return raw_results[:limit]

    def map_raw_records(self, raw_records: Iterable[dict], profile: str = "generic_it") -> List[Tender]:
        """Maps raw SECOP II records into enriched domain entities."""
        tenders = self._enrich_results(raw_records, keyword=None, profile_name=profile, only_high_fit=False, only_new=False)
        return self._rank_results(tenders)

    def _enrich_results(
        self,
        raw_records: Iterable[dict],
        *,
        keyword: Optional[str],
        profile_name: str,
        only_high_fit: bool,
        only_new: bool,
    ) -> List[Tender]:
        profile = MATCH_PROFILES[profile_name]
        threshold = float(profile.get("high_fit_threshold", 70))
        deduped: dict[str, Tender] = {}
        now = self._now()

        for raw_record in raw_records:
            tender = self._build_tender(raw_record)
            if tender is None:
                continue
            self._score_tender(tender, profile_name=profile_name, now=now)
            self._observe_tender(tender, profile_name=profile_name, seen_at=now)

            if keyword and not self._matches_keyword(tender, keyword):
                continue
            if only_high_fit and tender.match_score < threshold:
                continue
            if only_new and not tender.is_new:
                continue

            existing = deduped.get(tender.cluster_id)
            if existing is None or self._is_better_candidate(tender, existing):
                deduped[tender.cluster_id] = tender

        return list(deduped.values())

    async def _fetch_all_pages(
        self,
        *,
        min_budget: float,
        max_budget: float,
        department: str,
        process_status: str,
        phase: str,
        published_since_days: int,
        raw_limit: Optional[int] = None,
    ) -> List[List[dict]]:
        page_cap = self._page_cap_for_limit(raw_limit)
        all_pages: List[List[dict]] = []
        for page_start in range(0, page_cap, self.page_batch_size):
            pages = await self._fetch_page_batch(
                min_budget=min_budget,
                max_budget=max_budget,
                department=department,
                process_status=process_status,
                phase=phase,
                published_since_days=published_since_days,
                start_page=page_start,
                page_count=min(self.page_batch_size, page_cap - page_start),
            )
            for page in pages:
                all_pages.append(page)
                if len(page) < self.page_size:
                    return all_pages
        return all_pages

    async def _fetch_page_batch(
        self,
        *,
        min_budget: float,
        max_budget: float,
        department: str,
        process_status: str,
        phase: str,
        published_since_days: int,
        start_page: int,
        page_count: int,
    ) -> List[List[dict]]:
        tasks = [
            self._fetch_page(
                min_budget=min_budget,
                max_budget=max_budget,
                department=department,
                process_status=process_status,
                phase=phase,
                published_since_days=published_since_days,
                limit=self.page_size,
                offset=(start_page + page_index) * self.page_size,
            )
            for page_index in range(page_count)
        ]
        pages = await asyncio.gather(*tasks)
        return list(pages)

    def _page_cap_for_limit(self, raw_limit: Optional[int]) -> int:
        if raw_limit is None:
            return self.max_pages
        if raw_limit <= 0:
            return 0
        pages_for_limit = (raw_limit + self.page_size - 1) // self.page_size
        return max(1, min(self.max_pages, pages_for_limit))

    async def _fetch_page(
        self,
        *,
        min_budget: float,
        max_budget: float,
        department: str,
        process_status: str,
        phase: str,
        published_since_days: int,
        limit: int,
        offset: int,
    ) -> List[dict]:
        import urllib.parse

        where_clause = self._build_where_clause(
            min_budget=min_budget,
            max_budget=max_budget,
            department=department,
            process_status=process_status,
            phase=phase,
            published_since_days=published_since_days,
        )

        # Socrata requires $ prefix for system parameters, but some servers fail if not encoded as %24
        # We build the query string manually to ensure correct encoding
        query_params = [
            (f"%24select", SECOP_SELECT_CLAUSE),
            (f"%24where", where_clause),
            (f"%24limit", str(limit)),
            (f"%24offset", str(offset)),
            (f"%24order", DEFAULT_ORDER_BY),
        ]

        query_string = "&".join([f"{k}={urllib.parse.quote(v)}" for k, v in query_params])
        full_url = f"{self.BASE_URL}?{query_string}"

        headers = {"User-Agent": USER_AGENT}
        client = self._ensure_client()
        # Aumentamos el timeout para Socrata debido a la complejidad de las queries SoQL
        client.timeout = httpx.Timeout(60.0)

        for attempt in range(self.max_retries):
            start_time = time.monotonic()
            try:
                response = await client.get(full_url, headers=headers)
                duration = time.monotonic() - start_time
                SOCRATA_REQUEST_DURATION_SECONDS.labels(method="GET").observe(duration)
                SOCRATA_REQUESTS_TOTAL.labels(method="GET", status_code=str(response.status_code)).inc()

                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, list) else []
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                SOCRATA_ERRORS_TOTAL.labels(exception_type=type(exc).__name__).inc()
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

    def _build_where_clause(
        self,
        *,
        min_budget: float,
        max_budget: float,
        department: str,
        process_status: str,
        phase: str,
        published_since_days: int,
    ) -> str:
        publication_cutoff = (self._now() - timedelta(days=published_since_days)).strftime(SODA_DATE_FORMAT)
        clauses = [
            f"precio_base >= {max(min_budget, 0)}",
            f"precio_base <= {max_budget}",
            "estado_de_apertura_del_proceso = 'Abierto'",
            f"fecha_de_publicacion_del >= '{publication_cutoff}'",
        ]
        if department != DEFAULT_DEPARTMENT:
            safe_department = department.replace("'", "''")
            clauses.append(f"departamento_entidad = '{safe_department}'")
        if process_status != DEFAULT_PROCESS_STATUS:
            safe_process_status = process_status.replace("'", "''")
            clauses.append(f"estado_del_procedimiento = '{safe_process_status}'")
        if phase != DEFAULT_PHASE:
            safe_phase = phase.replace("'", "''")
            clauses.append(f"fase = '{safe_phase}'")
        if self._seed_clause:
            clauses.append(self._seed_clause)
        return " AND ".join(clauses)

    def _now(self) -> datetime:
        return datetime.now(self._tz).replace(tzinfo=None, microsecond=0)

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
        procedure_name = raw_record.get("nombre_del_procedimiento", "") or ""
        procedure_description = raw_record.get("descripci_n_del_procedimiento", "") or ""
        analysis_text = f"{procedure_name} {procedure_description}"

        if not self._matches_it_keywords(analysis_text):
            return None
        if GENERIC_NEGATIVE_PATTERN.search(analysis_text):
            return None

        try:
            closing_date_raw = raw_record.get("fecha_de_recepcion_de")
            closing_date_known = bool(closing_date_raw)
            publish_date = self._parse_date(raw_record.get("fecha_de_publicacion_del"), self._now())
            closing_date = self._parse_date(closing_date_raw, datetime.max.replace(microsecond=0))
            tender = Tender(
                id=raw_record.get("id_del_proceso", DEFAULT_IDENTIFIER),
                reference=raw_record.get("referencia_del_proceso", DEFAULT_IDENTIFIER),
                entity=raw_record.get("entidad", DEFAULT_IDENTIFIER),
                name=procedure_name,
                description=procedure_description,
                base_price=float(raw_record.get("precio_base", 0)),
                publish_date=publish_date,
                closing_date=closing_date,
                url=self._extract_url(raw_record.get("urlproceso", DEFAULT_URL)),
                department=raw_record.get("departamento_entidad"),
                status=raw_record.get("estado_del_procedimiento")
                or raw_record.get("estado_de_apertura_del_proceso", UNKNOWN_STATUS),
                opening_status=raw_record.get("estado_de_apertura_del_proceso") or UNKNOWN_STATUS,
                phase=raw_record.get("fase"),
                modality=raw_record.get("modalidad_de_contratacion"),
                closing_date_known=closing_date_known,
                deadline_confidence="confirmada" if closing_date_known else "sin fecha en dataset",
            )
            tender.cluster_id = self._cluster_id_for(tender)
            return tender
        except (TypeError, ValueError):
            return None

    def _matches_it_keywords(self, analysis_text: str) -> bool:
        return IT_KEYWORD_PATTERN.search(analysis_text) is not None

    def _matches_keyword(self, tender: Tender, keyword: str) -> bool:
        haystack = " ".join(
            (
                tender.name,
                tender.description,
                tender.entity,
                tender.department or "",
                tender.modality or "",
                tender.supplier_action_label,
                tender.supplier_action_detail,
                " ".join(tender.match_reasons),
                " ".join(tender.risk_flags),
            )
        ).lower()
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

    def _cluster_id_for(self, tender: Tender) -> str:
        entity_part = self._normalize_text(tender.entity)
        name_part = self._normalize_text(tender.name)[:180]
        price_part = str(int(tender.base_price))
        digest = hashlib.sha1(f"{entity_part}|{name_part}|{price_part}".encode("utf-8")).hexdigest()
        return digest[:20]

    def _normalize_text(self, value: str) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
        return " ".join(normalized.split())

    def _score_tender(self, tender: Tender, *, profile_name: str, now: datetime) -> None:
        profile = MATCH_PROFILES[profile_name]
        combined_text = " ".join(
            (
                tender.entity,
                tender.name,
                tender.description,
                tender.department or "",
                tender.phase or "",
                tender.modality or "",
                tender.opening_status or "",
                tender.status,
            )
        )
        entity_text = " ".join((tender.entity, tender.department or ""))
        self._classify_supplier_action(tender, now=now)

        reasons: list[str] = []
        risks: list[str] = []
        score = 0.0

        for rule in profile.get("categories", []) or []:
            pattern = rule.get("compiled_patterns")
            if pattern and pattern.search(combined_text):
                score += float(rule.get("weight", 0))
                reasons.append(rule.get("label", "Coincidencia temática"))

        for rule in profile.get("entity_bonuses", []) or []:
            pattern = rule.get("compiled_patterns")
            if pattern and pattern.search(entity_text):
                score += float(rule.get("weight", 0))
                reasons.append(rule.get("label", "Tipo de entidad afín"))

        for phase_name, phase_bonus in (profile.get("phase_bonuses") or {}).items():
            if (tender.phase or "").strip() == phase_name:
                score += float(phase_bonus)
                reasons.append(f"Etapa favorable: {phase_name}")
                break

        action_bonus, action_reason = self._supplier_action_bonus(tender)
        if action_bonus:
            score += action_bonus
            reasons.append(action_reason)

        days_since_publication = max(0, (now.date() - tender.publish_date.date()).days)
        freshness_score = self._freshness_bonus(profile, days_since_publication)
        if freshness_score:
            score += freshness_score
            reasons.append(f"Publicado hace {days_since_publication} días")

        if not tender.closing_date_known:
            score -= float(profile.get("closing_date_unknown_penalty", 0))
            risks.append("SECOP no expone fecha de cierre; requiere validación manual")
        elif tender.closing_date.date() < now.date():
            score -= 60
            risks.append("La fecha de cierre del dataset parece vencida")

        for rule in profile.get("risk_penalties", []) or []:
            pattern = rule.get("compiled_patterns")
            if pattern and pattern.search(combined_text):
                score -= float(rule.get("weight", 0))
                risks.append(rule.get("label", "Riesgo de encaje"))

        if self._looks_like_nominal_person_record(tender):
            score -= 18
            risks.append("El objeto parece orientado a una hoja de vida individual")

        tender.profile = profile_name
        tender.days_since_publication = days_since_publication
        tender.freshness_score = freshness_score
        tender.match_score = max(0.0, min(100.0, score))
        tender.match_reasons = self._unique_ordered(reasons)
        tender.risk_flags = self._unique_ordered(risks)
        tender.match_label = self._match_label_for(tender.match_score, profile)

    def _classify_supplier_action(self, tender: Tender, *, now: datetime) -> None:
        phase = (tender.phase or "").strip()
        is_menor_cuantia = self._is_menor_cuantia(tender)
        opening_status = (tender.opening_status or "").strip().casefold()

        if tender.closing_date_known and tender.closing_date.date() < now.date():
            tender.supplier_action_code = ACTION_EXPIRED
            tender.supplier_action_label = "No accionable: cierre vencido"
            tender.supplier_action_detail = "El cierre reportado por SECOP ya pasó; solo sirve para trazabilidad o aprendizaje."
            tender.supplier_action_rank = 90
            return

        if opening_status and opening_status != "abierto":
            tender.supplier_action_code = ACTION_NOT_OPEN
            tender.supplier_action_label = "Validar apertura"
            tender.supplier_action_detail = "El dataset no marca el proceso como abierto; confirmar en SECOP II antes de invertir esfuerzo."
            tender.supplier_action_rank = 80
            return

        if phase in MANIFEST_INTEREST_PHASES or is_menor_cuantia:
            tender.supplier_action_code = ACTION_MANIFEST_INTEREST
            tender.supplier_action_label = "Manifestar interés ahora"
            tender.supplier_action_detail = (
                "Menor cuantía: manifestar interés en SECOP II antes del cierre de la etapa para poder competir."
            )
            tender.supplier_action_rank = 0
            return

        if phase in PRESENT_OFFER_PHASES:
            tender.supplier_action_code = ACTION_PRESENT_OFFER
            tender.supplier_action_label = "Presentar oferta"
            tender.supplier_action_detail = "Preparar y radicar oferta formal antes de la fecha y hora de cierre."
            tender.supplier_action_rank = 10
            return

        if phase in OBSERVATION_PHASES:
            tender.supplier_action_code = ACTION_OBSERVE
            tender.supplier_action_label = "Observar pliegos"
            tender.supplier_action_detail = "Enviar observaciones o solicitudes de ajuste; todavía no equivale a oferta formal."
            tender.supplier_action_rank = 25
            return

        if phase in PREQUALIFICATION_PHASES:
            tender.supplier_action_code = ACTION_PREQUALIFY
            tender.supplier_action_label = "Gestionar precalificación"
            tender.supplier_action_detail = "Revisar requisitos de precalificación antes de preparar una oferta completa."
            tender.supplier_action_rank = 35
            return

        if phase in FOLLOW_UP_PHASES:
            tender.supplier_action_code = ACTION_FOLLOW_UP
            tender.supplier_action_label = "Seguimiento operativo"
            tender.supplier_action_detail = "Monitorear aclaraciones, estimaciones o cambios antes de comprometer una oferta."
            tender.supplier_action_rank = 50
            return

        tender.supplier_action_code = ACTION_REVIEW
        tender.supplier_action_label = "Revisar manualmente"
        tender.supplier_action_detail = "Validar etapa, cronograma y requisitos habilitantes en SECOP II antes de actuar."
        tender.supplier_action_rank = 60

    def _is_menor_cuantia(self, tender: Tender) -> bool:
        modality_text = self._normalize_text(tender.modality or "")
        phase_text = self._normalize_text(tender.phase or "")
        return any(
            marker in modality_text or marker in phase_text
            for marker in MENOR_CUANTIA_MARKERS
        )

    def _supplier_action_bonus(self, tender: Tender) -> tuple[float, str]:
        if tender.supplier_action_code == ACTION_MANIFEST_INTEREST:
            return 14.0, "Acción prioritaria: manifestar interés en menor cuantía"
        if tender.supplier_action_code == ACTION_PRESENT_OFFER:
            return 8.0, "Acción disponible: presentar oferta"
        if tender.supplier_action_code == ACTION_OBSERVE:
            return 3.0, "Interacción temprana: observar pliegos"
        if tender.supplier_action_code == ACTION_PREQUALIFY:
            return 4.0, "Acción previa: gestionar precalificación"
        return 0.0, ""

    def _freshness_bonus(self, profile: dict[str, Any], days_since_publication: int) -> float:
        for window in profile.get("freshness_windows", []) or []:
            if days_since_publication <= int(window.get("days", 0)):
                return float(window.get("score", 0))
        return 0.0

    def _looks_like_nominal_person_record(self, tender: Tender) -> bool:
        tokens = [piece for piece in tender.name.replace(",", " ").split() if piece]
        if 2 <= len(tokens) <= 5 and all(token.isalpha() and token == token.upper() for token in tokens):
            return True
        return False

    def _match_label_for(self, score: float, profile: dict[str, Any]) -> str:
        high = float(profile.get("high_fit_threshold", 70))
        medium = max(35.0, high - 20.0)
        if score >= high:
            return "Alto encaje"
        if score >= medium:
            return "Encaje medio"
        return "Bajo encaje"

    def _observe_tender(self, tender: Tender, *, profile_name: str, seen_at: datetime) -> None:
        payload_hash = hashlib.sha1(
            "|".join(
                [
                    tender.entity,
                    tender.name,
                    tender.description,
                    str(int(tender.base_price)),
                    tender.url,
                    tender.phase or "",
                    tender.modality or "",
                    tender.opening_status or "",
                    tender.status,
                ]
            ).encode("utf-8")
        ).hexdigest()
        first_seen_at, last_seen_at, is_new = self._snapshot_store.observe(
            tender,
            payload_hash=payload_hash,
            seen_at=seen_at,
            profile=profile_name,
        )
        tender.first_seen_at = first_seen_at
        tender.last_seen_at = last_seen_at
        tender.is_new = is_new

    def _is_better_candidate(self, candidate: Tender, current: Tender) -> bool:
        candidate_tuple = (
            -candidate.supplier_action_rank,
            candidate.match_score,
            candidate.closing_date_known,
            candidate.publish_date,
            len(candidate.description or ""),
            candidate.first_seen_at or datetime.min,
        )
        current_tuple = (
            -current.supplier_action_rank,
            current.match_score,
            current.closing_date_known,
            current.publish_date,
            len(current.description or ""),
            current.first_seen_at or datetime.min,
        )
        return candidate_tuple > current_tuple

    def _rank_results(self, tenders: List[Tender]) -> List[Tender]:
        return sorted(
            tenders,
            key=lambda tender: (
                tender.supplier_action_rank,
                -tender.match_score,
                -tender.freshness_score,
                0 if tender.is_new else 1,
                tender.days_since_publication if tender.days_since_publication is not None else 9999,
                0 if tender.closing_date_known else 1,
                tender.closing_date,
                -tender.base_price,
                (tender.entity or "").casefold(),
                tender.id,
            ),
        )

    def _unique_ordered(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered
