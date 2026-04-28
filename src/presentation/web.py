import csv
import io
import logging
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, List, Optional

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.application.services import SearchActiveTenders
from src.application.validators import (
    ALLOWED_DEPARTMENTS,
    ALLOWED_PROCESS_STATUSES,
    DEFAULT_DEPARTMENT,
    DEFAULT_PROCESS_STATUS,
    normalize_department,
)
from src.domain.models import Tender
from src.infrastructure.repositories import SocrataTenderRepository

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = 100000000
MAX_BUDGET = 100000000000
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_KEYWORD_LENGTH = 64
NEGATIVE_BUDGET_ERROR = "El presupuesto debe ser un valor positivo."
INVALID_DEPARTMENT_ERROR = "El filtro de departamento seleccionado no es válido."
INVALID_PROCESS_STATUS_ERROR = "El filtro de estado seleccionado no es válido."
UNEXPECTED_SEARCH_ERROR = "Se produjo un error al procesar la solicitud. Inténtalo de nuevo más tarde."
DEPARTMENT_OPTIONS = [
    {"value": DEFAULT_DEPARTMENT, "label": "Todos (Nacional)"},
    {"value": "Distrito Capital de Bogotá", "label": "Bogotá D.C."},
    {"value": "Antioquia", "label": "Antioquia (Medellín)"},
    {"value": "Valle del Cauca", "label": "Valle del Cauca (Cali)"},
    {"value": "Atlántico", "label": "Atlántico (Barranquilla)"},
    {"value": "Santander", "label": "Santander"},
    {"value": "Cundinamarca", "label": "Cundinamarca"},
]
PROCESS_STATUS_OPTIONS = [
    {"value": DEFAULT_PROCESS_STATUS, "label": "Todos abiertos"},
    {"value": "Borrador", "label": "Borrador"},
    {"value": "Publicado", "label": "Publicado"},
]

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
    title="SECOP II - Radar TI",
    description="Herramienta de vigilancia tecnológica para la contratación pública.",
    version="2.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
)


def get_tender_service(request: Request) -> SearchActiveTenders:
    """Factory that reuses the singleton repository across requests."""
    return SearchActiveTenders(request.app.state.repository)


def _safe_department_selection(department: str) -> str:
    try:
        return normalize_department(department)
    except ValueError:
        return DEFAULT_DEPARTMENT


def _safe_process_status_selection(process_status: str) -> str:
    if process_status in ALLOWED_PROCESS_STATUSES:
        return process_status
    return DEFAULT_PROCESS_STATUS


def _translate_validation_error(error: ValueError) -> str:
    message = str(error)
    if message == "Unsupported department filter":
        return INVALID_DEPARTMENT_ERROR
    if message == "Unsupported process status filter":
        return INVALID_PROCESS_STATUS_ERROR
    if message == "Budget cannot be negative":
        return NEGATIVE_BUDGET_ERROR
    return message


def _normalize_keyword(keyword: Optional[str]) -> Optional[str]:
    if keyword is None:
        return None
    trimmed = keyword.strip()
    return trimmed or None


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
    budget: int,
    department_sel: str,
    process_status_sel: str,
    keyword: str,
    results: Optional[List[Tender]],
    pagination: Optional[dict],
    error: Optional[str],
) -> dict[str, Any]:
    return {
        "request": request,
        "results": results,
        "pagination": pagination,
        "budget": budget,
        "department_sel": department_sel,
        "process_status_sel": process_status_sel,
        "keyword": keyword,
        "departments": DEPARTMENT_OPTIONS,
        "process_statuses": PROCESS_STATUS_OPTIONS,
        "error": error,
        "is_simulation": False,
    }


def _render_index(
    request: Request,
    *,
    budget: int = DEFAULT_BUDGET,
    department_sel: str = DEFAULT_DEPARTMENT,
    process_status_sel: str = DEFAULT_PROCESS_STATUS,
    keyword: str = "",
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
            budget=budget,
            department_sel=department_sel,
            process_status_sel=process_status_sel,
            keyword=keyword,
            results=results,
            pagination=pagination,
            error=error,
        ),
        status_code=status_code,
    )


async def _execute_search(
    service: SearchActiveTenders,
    budget: float,
    department: str,
    keyword: Optional[str],
    process_status: str,
) -> List[Tender]:
    return await service.execute(
        budget=budget,
        department=department,
        keyword=keyword,
        process_status=process_status,
    )


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Main interface."""
    return _render_index(request)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)],
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    process_status: Annotated[str, Query(max_length=32)] = DEFAULT_PROCESS_STATUS,
    keyword: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    service: SearchActiveTenders = Depends(get_tender_service),
) -> HTMLResponse:
    """Search endpoint that orchestrates the use case and renders the view."""
    normalized_keyword = _normalize_keyword(keyword)
    try:
        selected_department = _safe_department_selection(department)
        selected_process_status = _safe_process_status_selection(process_status)
        results = await _execute_search(
            service,
            budget,
            department,
            normalized_keyword,
            process_status,
        )
        page_slice, pagination = _paginate(results, page, per_page)
        return _render_index(
            request,
            budget=int(budget),
            department_sel=selected_department,
            process_status_sel=selected_process_status,
            keyword=normalized_keyword or "",
            results=page_slice,
            pagination=pagination,
        )
    except ValueError as error:
        return _render_index(
            request,
            budget=int(budget),
            department_sel=DEFAULT_DEPARTMENT,
            process_status_sel=DEFAULT_PROCESS_STATUS,
            keyword=normalized_keyword or "",
            results=[],
            pagination=None,
            error=_translate_validation_error(error),
            status_code=400,
        )
    except Exception:
        logger.exception("Unexpected error while processing the tender search.")
        return _render_index(
            request,
            budget=int(budget),
            department_sel=_safe_department_selection(department),
            process_status_sel=_safe_process_status_selection(process_status),
            keyword=normalized_keyword or "",
            results=[],
            pagination=None,
            error=UNEXPECTED_SEARCH_ERROR,
            status_code=500,
        )


@app.get("/search.csv")
async def search_csv(
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)],
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    process_status: Annotated[str, Query(max_length=32)] = DEFAULT_PROCESS_STATUS,
    keyword: Annotated[str, Query(max_length=MAX_KEYWORD_LENGTH)] = "",
    service: SearchActiveTenders = Depends(get_tender_service),
):
    """Exports the current search result as a CSV file."""
    normalized_keyword = _normalize_keyword(keyword)
    try:
        results = await _execute_search(
            service,
            budget,
            department,
            normalized_keyword,
            process_status,
        )
    except ValueError as error:
        return PlainTextResponse(
            _translate_validation_error(error),
            status_code=400,
        )
    except Exception:
        logger.exception("Unexpected error while exporting tender search results.")
        return PlainTextResponse(UNEXPECTED_SEARCH_ERROR, status_code=500)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "reference",
        "entity",
        "name",
        "description",
        "base_price",
        "publish_date",
        "closing_date",
        "department",
        "status",
        "url",
    ])
    for tender in results:
        writer.writerow([
            tender.id,
            tender.reference,
            tender.entity,
            tender.name,
            tender.description,
            f"{tender.base_price:.2f}",
            tender.publish_date.strftime("%Y-%m-%d"),
            tender.closing_date.strftime("%Y-%m-%d"),
            tender.department or "",
            tender.status,
            tender.url,
        ])

    buffer.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="secop_radar_ti.csv"'}
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers=headers)
