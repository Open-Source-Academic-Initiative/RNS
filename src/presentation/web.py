import csv
import ipaddress
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Callable, Iterator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from src.application.services import SearchActiveTenders
from src.application.validators import (
    ALLOWED_PHASES,
    ALLOWED_PROCESS_STATUSES,
    DEFAULT_DEPARTMENT,
    DEFAULT_PHASE,
    DEFAULT_PROCESS_STATUS,
    DEFAULT_PROFILE,
    normalize_department,
    normalize_phase,
    normalize_process_status,
    normalize_profile,
)
from src.domain.models import Tender
from src.infrastructure.repositories import SocrataTenderRepository

logger = logging.getLogger(__name__)

# Metrics Definition
HTTP_REQUESTS_TOTAL = Counter(
    "rns_http_requests_total",
    "Total HTTP requests by method, path and status",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "rns_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


def is_local_metrics_request(request: Request) -> bool:
    """Security check: allows /metrics only from loopback and blocks proxy headers."""
    client_host = request.client.host if request.client else "unknown"

    # Block if proxy headers are present (X-Forwarded-For, etc)
    if any(h in request.headers for h in ("x-forwarded-for", "x-real-ip", "forwarded")):
        return False

    try:
        # Support both IPv4 (127.0.0.1) and IPv6 (::1)
        client_ip = ipaddress.ip_address(client_host)
        return client_ip.is_loopback
    except ValueError:
        return client_host in ("localhost", "127.0.0.1", "::1")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION = os.getenv("RNS_VERSION", "3.0.0")
DEFAULT_MIN_BUDGET = _env_int("RNS_DEFAULT_MIN_BUDGET", 60000000)
DEFAULT_BUDGET = _env_int("RNS_DEFAULT_BUDGET", 260000000)
MAX_BUDGET = _env_int("RNS_MAX_BUDGET", 100000000000)
DEFAULT_PUBLISHED_SINCE_DAYS = _env_int("RNS_DEFAULT_PUBLISHED_SINCE_DAYS", 60)
DEFAULT_PAGE_SIZE = _env_int("RNS_WEB_PAGE_SIZE", 25)
MAX_PAGE_SIZE = _env_int("RNS_WEB_MAX_PAGE_SIZE", 100)
MAX_KEYWORD_LENGTH = 64
API_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("API_CORS_ORIGINS", "*").split(",")
    if origin.strip()
] or ["*"]
DEFAULT_SORT_BY = "supplier_action_rank"
DEFAULT_SORT_DIR = "asc"
SORT_DIRECTIONS = {"asc", "desc"}
NEGATIVE_BUDGET_ERROR = "Los presupuestos deben ser valores positivos."
INVALID_BUDGET_RANGE_ERROR = "El presupuesto mínimo no puede superar el presupuesto máximo."
INVALID_PUBLISHED_WINDOW_ERROR = "La ventana de publicación debe ser un valor positivo."
INVALID_DEPARTMENT_ERROR = "El filtro de departamento seleccionado no es válido."
INVALID_PROCESS_STATUS_ERROR = "El filtro de estado seleccionado no es válido."
INVALID_PHASE_ERROR = "El filtro de etapa seleccionado no es válido."
INVALID_PROFILE_ERROR = "El perfil de búsqueda seleccionado no es válido."
UNEXPECTED_SEARCH_ERROR = "Se produjo un error al procesar la solicitud. Inténtalo de nuevo más tarde."

DEPARTMENT_SUGGESTIONS = [
    "Distrito Capital de Bogotá",
    "Amazonas",
    "Antioquia",
    "Arauca",
    "Atlántico",
    "Bolívar",
    "Boyacá",
    "Caldas",
    "Caquetá",
    "Casanare",
    "Cauca",
    "Cesar",
    "Chocó",
    "Córdoba",
    "Cundinamarca",
    "Guainía",
    "Guaviare",
    "Huila",
    "La Guajira",
    "Magdalena",
    "Meta",
    "Nariño",
    "Norte de Santander",
    "Putumayo",
    "Quindío",
    "Risaralda",
    "Santander",
    "Sucre",
    "Tolima",
    "Valle del Cauca",
    "Vaupés",
    "Vichada",
]
PROCESS_STATUS_OPTIONS = [
    {"value": DEFAULT_PROCESS_STATUS, "label": "Todos abiertos"},
    {"value": "Borrador", "label": "Borrador"},
    {"value": "Publicado", "label": "Publicado"},
]
PHASE_OPTIONS = [{"value": DEFAULT_PHASE, "label": "Todas las etapas"}] + [
    {"value": phase, "label": phase} for phase in ALLOWED_PHASES if phase != DEFAULT_PHASE
]
PROFILE_OPTIONS = [
    {"value": "opensai", "label": "OpenSAI"},
    {"value": "generic_it", "label": "Radar TI general"},
]
PUBLISHED_WINDOW_OPTIONS = [
    {"value": 7, "label": "Últimos 7 días"},
    {"value": 15, "label": "Últimos 15 días"},
    {"value": 30, "label": "Últimos 30 días"},
    {"value": 60, "label": "Últimos 60 días"},
    {"value": 90, "label": "Últimos 90 días"},
]
SORT_FIELDS: dict[str, Callable[[Tender], Any]] = {
    "match_score": lambda tender: tender.match_score,
    "freshness_score": lambda tender: tender.freshness_score,
    "entity": lambda tender: (tender.entity or "").casefold(),
    "base_price": lambda tender: tender.base_price,
    "publish_date": lambda tender: tender.publish_date,
    "closing_date": lambda tender: tender.closing_date,
    "match_label": lambda tender: tender.match_label.casefold(),
    "supplier_action_rank": lambda tender: tender.supplier_action_rank,
}

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,testserver").split(",")
    if host.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = SocrataTenderRepository()
    app.state.repository = repository
    try:
        yield
    finally:
        await repository.aclose()


app = FastAPI(
    title="SECOP II - Radar OpenSAI",
    description="Herramienta de vigilancia para detectar oportunidades más alineadas con OpenSAI.",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_middleware(request: Request, call_next: Callable):
    start_time = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start_time

    # Record metrics
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=request.method,
        path=request.url.path
    ).observe(duration)
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        path=request.url.path,
        status_code=str(response.status_code)
    ).inc()

    return response


STATIC_DIR = PROJECT_ROOT / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_tender_service(request: Request) -> SearchActiveTenders:
    return SearchActiveTenders(request.app.state.repository)


def _safe_department_selection(department: str) -> str:
    try:
        return normalize_department(department)
    except ValueError:
        return DEFAULT_DEPARTMENT


def _safe_process_status_selection(process_status: str) -> str:
    try:
        return normalize_process_status(process_status)
    except ValueError:
        return DEFAULT_PROCESS_STATUS


def _safe_phase_selection(phase: str) -> str:
    try:
        return normalize_phase(phase)
    except ValueError:
        return DEFAULT_PHASE


def _safe_profile_selection(profile: str) -> str:
    try:
        return normalize_profile(profile)
    except ValueError:
        return DEFAULT_PROFILE


def _translate_validation_error(error: ValueError) -> str:
    message = str(error)
    if message == "Unsafe filter value" or message == "Unsupported department filter":
        return INVALID_DEPARTMENT_ERROR
    if message == "Unsupported process status filter":
        return INVALID_PROCESS_STATUS_ERROR
    if message == "Unsupported phase filter":
        return INVALID_PHASE_ERROR
    if message == "Unsupported profile filter":
        return INVALID_PROFILE_ERROR
    if message in {"Budget cannot be negative", "Minimum budget cannot be negative"}:
        return NEGATIVE_BUDGET_ERROR
    if message == "Minimum budget cannot exceed maximum budget":
        return INVALID_BUDGET_RANGE_ERROR
    if message == "Published-since window must be positive":
        return INVALID_PUBLISHED_WINDOW_ERROR
    return message


def _normalize_keyword(keyword: Optional[str]) -> Optional[str]:
    if keyword is None:
        return None
    trimmed = keyword.strip()
    return trimmed or None


def _normalize_sort(sort_by: str, sort_dir: str) -> tuple[str, str]:
    normalized_sort_by = sort_by.strip() if sort_by else DEFAULT_SORT_BY
    if normalized_sort_by not in SORT_FIELDS:
        normalized_sort_by = DEFAULT_SORT_BY
    normalized_sort_dir = sort_dir.strip().lower() if sort_dir else DEFAULT_SORT_DIR
    if normalized_sort_dir not in SORT_DIRECTIONS:
        normalized_sort_dir = DEFAULT_SORT_DIR
    return normalized_sort_by, normalized_sort_dir


def _sort_results(results: List[Tender], sort_by: str, sort_dir: str) -> List[Tender]:
    key_func = SORT_FIELDS[sort_by]
    reverse = sort_dir == "desc"

    def sortable_value(tender: Tender) -> tuple[Any, ...]:
        value = key_func(tender)
        if isinstance(value, datetime):
            value = value.timestamp()
        if sort_by == "supplier_action_rank":
            return (
                value,
                -tender.match_score,
                -tender.freshness_score,
                (tender.entity or "").casefold(),
                tender.id,
            )
        return (
            value,
            tender.freshness_score,
            (tender.entity or "").casefold(),
            tender.id,
        )

    return sorted(results, key=sortable_value, reverse=reverse)


def _paginate(results: List[Tender], page: int, per_page: int) -> tuple[List[Tender], dict]:
    total = len(results)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * per_page
    end = start + per_page
    pagination = {
        "page": current_page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_page": current_page - 1,
        "next_page": current_page + 1,
    }
    return results[start:end], pagination


def _build_page_context(
    request: Request,
    *,
    min_budget: int,
    budget: int,
    department_sel: str,
    process_status_sel: str,
    phase_sel: str,
    profile_sel: str,
    published_since_days: int,
    keyword: str,
    sort_by: str,
    sort_dir: str,
    only_high_fit: bool,
    only_new: bool,
    results: Optional[List[Tender]],
    pagination: Optional[dict],
    error: Optional[str],
) -> dict[str, Any]:
    return {
        "request": request,
        "results": results,
        "pagination": pagination,
        "min_budget": min_budget,
        "budget": budget,
        "department_sel": department_sel,
        "process_status_sel": process_status_sel,
        "phase_sel": phase_sel,
        "profile_sel": profile_sel,
        "published_since_days": published_since_days,
        "keyword": keyword,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "only_high_fit": only_high_fit,
        "only_new": only_new,
        "departments": DEPARTMENT_SUGGESTIONS,
        "process_statuses": PROCESS_STATUS_OPTIONS,
        "phases": PHASE_OPTIONS,
        "profiles": PROFILE_OPTIONS,
        "published_windows": PUBLISHED_WINDOW_OPTIONS,
        "error": error,
    }


def _render_index(
    request: Request,
    *,
    min_budget: int = DEFAULT_MIN_BUDGET,
    budget: int = DEFAULT_BUDGET,
    department_sel: str = DEFAULT_DEPARTMENT,
    process_status_sel: str = DEFAULT_PROCESS_STATUS,
    phase_sel: str = DEFAULT_PHASE,
    profile_sel: str = DEFAULT_PROFILE,
    published_since_days: int = DEFAULT_PUBLISHED_SINCE_DAYS,
    keyword: str = "",
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
    only_high_fit: bool = False,
    only_new: bool = False,
    results: Optional[List[Tender]] = None,
    pagination: Optional[dict] = None,
    error: Optional[str] = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        _build_page_context(
            request,
            min_budget=min_budget,
            budget=budget,
            department_sel=department_sel,
            process_status_sel=process_status_sel,
            phase_sel=phase_sel,
            profile_sel=profile_sel,
            published_since_days=published_since_days,
            keyword=keyword,
            sort_by=sort_by,
            sort_dir=sort_dir,
            only_high_fit=only_high_fit,
            only_new=only_new,
            results=results,
            pagination=pagination,
            error=error,
        ),
        status_code=status_code,
    )


async def _execute_search(
    service: SearchActiveTenders,
    *,
    min_budget: float,
    budget: float,
    department: str,
    keyword: Optional[str],
    process_status: str,
    phase: str,
    published_since_days: int,
    profile: str,
    only_high_fit: bool,
    only_new: bool,
) -> List[Tender]:
    return await service.execute(
        budget=budget,
        min_budget=min_budget,
        department=department,
        keyword=keyword,
        process_status=process_status,
        phase=phase,
        published_since_days=published_since_days,
        profile=profile,
        only_high_fit=only_high_fit,
        only_new=only_new,
    )


CSV_HEADER_ROW = [
    "id",
    "cluster_id",
    "reference",
    "entity",
    "name",
    "description",
    "base_price",
    "publish_date",
    "closing_date",
    "closing_date_known",
    "department",
    "phase",
    "status",
    "opening_status",
    "modality",
    "supplier_action_code",
    "supplier_action_label",
    "supplier_action_detail",
    "supplier_action_rank",
    "profile",
    "match_score",
    "match_label",
    "match_reasons",
    "risk_flags",
    "days_since_publication",
    "freshness_score",
    "is_new",
    "first_seen_at",
    "last_seen_at",
    "url",
]


def _serialize_datetime(value: Optional[datetime]) -> str:
    return value.isoformat() if value else ""


def _csv_row_for(tender: Tender) -> list[str]:
    return [
        tender.id,
        tender.cluster_id,
        tender.reference,
        tender.entity,
        tender.name,
        tender.description,
        f"{tender.base_price:.2f}",
        _serialize_datetime(tender.publish_date),
        _serialize_datetime(tender.closing_date if tender.closing_date_known else None),
        "true" if tender.closing_date_known else "false",
        tender.department or "",
        tender.phase or "",
        tender.status,
        tender.opening_status or "",
        tender.modality or "",
        tender.supplier_action_code,
        tender.supplier_action_label,
        tender.supplier_action_detail,
        str(tender.supplier_action_rank),
        tender.profile,
        f"{tender.match_score:.2f}",
        tender.match_label,
        " | ".join(tender.match_reasons),
        " | ".join(tender.risk_flags),
        str(tender.days_since_publication or 0),
        f"{tender.freshness_score:.2f}",
        "true" if tender.is_new else "false",
        _serialize_datetime(tender.first_seen_at),
        _serialize_datetime(tender.last_seen_at),
        tender.url,
    ]


class _CsvLineBuffer:
    def __init__(self) -> None:
        self._chunks: list[str] = []

    def write(self, chunk: str) -> int:
        self._chunks.append(chunk)
        return len(chunk)

    def drain(self) -> str:
        line = "".join(self._chunks)
        self._chunks.clear()
        return line


def _stream_csv(rows: List[Tender]) -> Iterator[str]:
    sink = _CsvLineBuffer()
    writer = csv.writer(sink)
    writer.writerow(CSV_HEADER_ROW)
    yield sink.drain()
    for tender in rows:
        writer.writerow(_csv_row_for(tender))
        yield sink.drain()


def _tender_to_dict(tender: Tender) -> dict[str, Any]:
    payload = asdict(tender)
    payload["publish_date"] = tender.publish_date.isoformat()
    payload["closing_date"] = tender.closing_date.isoformat()
    payload["first_seen_at"] = _serialize_datetime(tender.first_seen_at)
    payload["last_seen_at"] = _serialize_datetime(tender.last_seen_at)
    payload["is_active"] = tender.is_active
    return payload


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return _render_index(request)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": APP_VERSION})


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    if not is_local_metrics_request(request):
        raise HTTPException(status_code=403, detail="Forbidden: Metrics only available locally")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)] = DEFAULT_BUDGET,
    min_budget: Annotated[float, Query(ge=0, le=MAX_BUDGET)] = DEFAULT_MIN_BUDGET,
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    process_status: Annotated[str, Query(max_length=64)] = DEFAULT_PROCESS_STATUS,
    phase: Annotated[str, Query(max_length=96)] = DEFAULT_PHASE,
    profile: Annotated[str, Query(max_length=32)] = DEFAULT_PROFILE,
    published_since_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_PUBLISHED_SINCE_DAYS,
    keyword: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    only_high_fit: bool = False,
    only_new: bool = False,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    sort_by: Annotated[str, Query(max_length=32)] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(max_length=4)] = DEFAULT_SORT_DIR,
    service: SearchActiveTenders = Depends(get_tender_service),
) -> HTMLResponse:
    normalized_keyword = _normalize_keyword(keyword)
    selected_sort_by, selected_sort_dir = _normalize_sort(sort_by, sort_dir)
    try:
        selected_department = _safe_department_selection(department)
        selected_process_status = _safe_process_status_selection(process_status)
        selected_phase = _safe_phase_selection(phase)
        selected_profile = _safe_profile_selection(profile)
        results = await _execute_search(
            service,
            min_budget=min_budget,
            budget=budget,
            department=department,
            keyword=normalized_keyword,
            process_status=process_status,
            phase=phase,
            published_since_days=published_since_days,
            profile=profile,
            only_high_fit=only_high_fit,
            only_new=only_new,
        )
        results = _sort_results(results, selected_sort_by, selected_sort_dir)
        page_slice, pagination = _paginate(results, page, per_page)
        return _render_index(
            request,
            min_budget=int(min_budget),
            budget=int(budget),
            department_sel=selected_department,
            process_status_sel=selected_process_status,
            phase_sel=selected_phase,
            profile_sel=selected_profile,
            published_since_days=published_since_days,
            keyword=normalized_keyword or "",
            sort_by=selected_sort_by,
            sort_dir=selected_sort_dir,
            only_high_fit=only_high_fit,
            only_new=only_new,
            results=page_slice,
            pagination=pagination,
        )
    except ValueError as error:
        return _render_index(
            request,
            min_budget=int(min_budget),
            budget=int(budget),
            department_sel=DEFAULT_DEPARTMENT,
            process_status_sel=DEFAULT_PROCESS_STATUS,
            phase_sel=DEFAULT_PHASE,
            profile_sel=DEFAULT_PROFILE,
            published_since_days=published_since_days,
            keyword=normalized_keyword or "",
            sort_by=selected_sort_by,
            sort_dir=selected_sort_dir,
            only_high_fit=only_high_fit,
            only_new=only_new,
            results=[],
            pagination=None,
            error=_translate_validation_error(error),
            status_code=400,
        )
    except Exception:
        logger.exception("Unexpected error while processing the tender search.")
        return _render_index(
            request,
            min_budget=int(min_budget),
            budget=int(budget),
            department_sel=_safe_department_selection(department),
            process_status_sel=_safe_process_status_selection(process_status),
            phase_sel=_safe_phase_selection(phase),
            profile_sel=_safe_profile_selection(profile),
            published_since_days=published_since_days,
            keyword=normalized_keyword or "",
            sort_by=selected_sort_by,
            sort_dir=selected_sort_dir,
            only_high_fit=only_high_fit,
            only_new=only_new,
            results=[],
            pagination=None,
            error=UNEXPECTED_SEARCH_ERROR,
            status_code=500,
        )


@app.get("/search.csv")
async def search_csv(
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)] = DEFAULT_BUDGET,
    min_budget: Annotated[float, Query(ge=0, le=MAX_BUDGET)] = DEFAULT_MIN_BUDGET,
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    process_status: Annotated[str, Query(max_length=64)] = DEFAULT_PROCESS_STATUS,
    phase: Annotated[str, Query(max_length=96)] = DEFAULT_PHASE,
    profile: Annotated[str, Query(max_length=32)] = DEFAULT_PROFILE,
    published_since_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_PUBLISHED_SINCE_DAYS,
    keyword: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    only_high_fit: bool = False,
    only_new: bool = False,
    sort_by: Annotated[str, Query(max_length=32)] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(max_length=4)] = DEFAULT_SORT_DIR,
    service: SearchActiveTenders = Depends(get_tender_service),
):
    normalized_keyword = _normalize_keyword(keyword)
    selected_sort_by, selected_sort_dir = _normalize_sort(sort_by, sort_dir)
    try:
        results = await _execute_search(
            service,
            min_budget=min_budget,
            budget=budget,
            department=department,
            keyword=normalized_keyword,
            process_status=process_status,
            phase=phase,
            published_since_days=published_since_days,
            profile=profile,
            only_high_fit=only_high_fit,
            only_new=only_new,
        )
        results = _sort_results(results, selected_sort_by, selected_sort_dir)
    except ValueError as error:
        return PlainTextResponse(_translate_validation_error(error), status_code=400)
    except Exception:
        logger.exception("Unexpected error while exporting tender search results.")
        return PlainTextResponse(UNEXPECTED_SEARCH_ERROR, status_code=500)

    headers = {"Content-Disposition": 'attachment; filename="rns_opensai_matches.csv"'}
    return StreamingResponse(_stream_csv(results), media_type="text/csv", headers=headers)


@app.get("/api/search")
async def api_search(
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)] = DEFAULT_BUDGET,
    min_budget: Annotated[float, Query(ge=0, le=MAX_BUDGET)] = DEFAULT_MIN_BUDGET,
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    process_status: Annotated[str, Query(max_length=64)] = DEFAULT_PROCESS_STATUS,
    phase: Annotated[str, Query(max_length=96)] = DEFAULT_PHASE,
    profile: Annotated[str, Query(max_length=32)] = DEFAULT_PROFILE,
    published_since_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_PUBLISHED_SINCE_DAYS,
    keyword: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    only_high_fit: bool = False,
    only_new: bool = False,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    sort_by: Annotated[str, Query(max_length=32)] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(max_length=4)] = DEFAULT_SORT_DIR,
    service: SearchActiveTenders = Depends(get_tender_service),
) -> JSONResponse:
    normalized_keyword = _normalize_keyword(keyword)
    selected_sort_by, selected_sort_dir = _normalize_sort(sort_by, sort_dir)
    try:
        results = await _execute_search(
            service,
            min_budget=min_budget,
            budget=budget,
            department=department,
            keyword=normalized_keyword,
            process_status=process_status,
            phase=phase,
            published_since_days=published_since_days,
            profile=profile,
            only_high_fit=only_high_fit,
            only_new=only_new,
        )
        results = _sort_results(results, selected_sort_by, selected_sort_dir)
        page_slice, pagination = _paginate(results, page, per_page)
        return JSONResponse(
            {
                "filters": {
                    "min_budget": int(min_budget),
                    "budget": int(budget),
                    "department": _safe_department_selection(department),
                    "process_status": _safe_process_status_selection(process_status),
                    "phase": _safe_phase_selection(phase),
                    "profile": _safe_profile_selection(profile),
                    "published_since_days": published_since_days,
                    "keyword": normalized_keyword or "",
                    "only_high_fit": only_high_fit,
                    "only_new": only_new,
                    "sort_by": selected_sort_by,
                    "sort_dir": selected_sort_dir,
                },
                "pagination": pagination,
                "results": [_tender_to_dict(tender) for tender in page_slice],
            }
        )
    except ValueError as error:
        return JSONResponse({"error": _translate_validation_error(error)}, status_code=400)
    except Exception:
        logger.exception("Unexpected error while serving /api/search.")
        return JSONResponse({"error": UNEXPECTED_SEARCH_ERROR}, status_code=500)
