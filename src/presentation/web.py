import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.application.services import SearchActiveTenders
from src.application.validators import ALLOWED_DEPARTMENTS, DEFAULT_DEPARTMENT
from src.infrastructure.repositories import SocrataTenderRepository

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = 100000000
MAX_BUDGET = 100000000000
INVALID_DEPARTMENT_ERROR = "El filtro de departamento seleccionado no es válido."
UNEXPECTED_SEARCH_ERROR = "Se produjo un error al procesar la solicitud. Inténtalo de nuevo más tarde."
DEPARTMENT_OPTIONS = [
    {"value": DEFAULT_DEPARTMENT, "label": "Todos (Nacional)"},
    {"value": "Distrito Capital de Bogotá", "label": "Bogotá D.C."},
    {"value": "Antioquia", "label": "Antioquia (Medellín)"},
    {"value": "Valle del Cauca", "label": "Valle del Cauca (Cali)"},
    {"value": "Atlantico", "label": "Atlántico (Barranquilla)"},
    {"value": "Santander", "label": "Santander"},
    {"value": "Cundinamarca", "label": "Cundinamarca"},
]

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

app = FastAPI(
    title="SECOP II - Radar TI",
    description="Herramienta de vigilancia tecnológica para la contratación pública.",
    version="2.1.0",
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "testserver"],
)


def get_tender_service() -> SearchActiveTenders:
    """Factory to inject the repository into the use case."""
    return SearchActiveTenders(SocrataTenderRepository())


def _build_page_context(
    request: Request,
    *,
    budget: int = DEFAULT_BUDGET,
    department_sel: str = DEFAULT_DEPARTMENT,
    results: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "request": request,
        "results": results,
        "budget": budget,
        "department_sel": department_sel,
        "departments": DEPARTMENT_OPTIONS,
        "error": error,
        "is_simulation": False,
    }


def _render_index(
    request: Request,
    *,
    budget: int = DEFAULT_BUDGET,
    department_sel: str = DEFAULT_DEPARTMENT,
    results: Any = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        _build_page_context(
            request,
            budget=budget,
            department_sel=department_sel,
            results=results,
            error=error,
        ),
        status_code=status_code,
    )


def _safe_department_selection(department: str) -> str:
    if department in ALLOWED_DEPARTMENTS:
        return department
    return DEFAULT_DEPARTMENT


def _to_error_message(error: ValueError) -> str:
    if str(error) == "Unsupported department filter":
        return INVALID_DEPARTMENT_ERROR
    return str(error)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main interface."""
    return _render_index(request)


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    budget: Annotated[float, Query(gt=0, le=MAX_BUDGET)],
    department: Annotated[str, Query(max_length=64)] = DEFAULT_DEPARTMENT,
    service: SearchActiveTenders = Depends(get_tender_service),
):
    """Search endpoint that orchestrates the use case and renders the view."""
    try:
        selected_department = _safe_department_selection(department)
        results = service.execute(budget=budget, department=department)
        return _render_index(
            request,
            budget=int(budget),
            department_sel=selected_department,
            results=results,
        )
    except ValueError as error:
        return _render_index(
            request,
            budget=int(budget),
            department_sel=DEFAULT_DEPARTMENT,
            results=[],
            error=_to_error_message(error),
            status_code=400,
        )
    except Exception:
        logger.exception("Unexpected error while processing the tender search.")
        return _render_index(
            request,
            budget=int(budget),
            department_sel=_safe_department_selection(department),
            results=[],
            error=UNEXPECTED_SEARCH_ERROR,
            status_code=500,
        )
