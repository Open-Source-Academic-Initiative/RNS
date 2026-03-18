from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.application.services import SearchActiveTenders
from src.application.validators import ALLOWED_DEPARTMENTS, normalize_department
from src.infrastructure.repositories import SocrataTenderRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = 100000000
DEPARTMENT_OPTIONS = [
    {"value": "Todos", "label": "Todos (Nacional)"},
    {"value": "Distrito Capital de Bogotá", "label": "Bogotá D.C."},
    {"value": "Antioquia", "label": "Antioquia (Medellín)"},
    {"value": "Valle del Cauca", "label": "Valle del Cauca (Cali)"},
    {"value": "Atlantico", "label": "Atlántico (Barranquilla)"},
    {"value": "Santander", "label": "Santander"},
    {"value": "Cundinamarca", "label": "Cundinamarca"},
]

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))

app = FastAPI(
    title="SECOP II - IT Radar",
    description="Technology vigilance tool for public procurement.",
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
    department_sel: str = "Todos",
    results=None,
    error: str | None = None,
):
    return {
        "request": request,
        "results": results,
        "budget": budget,
        "department_sel": department_sel,
        "departments": DEPARTMENT_OPTIONS,
        "error": error,
        "is_simulation": False,
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main interface."""
    return templates.TemplateResponse(
        request,
        "index.html",
        _build_page_context(request),
    )


@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    budget: Annotated[float, Query(gt=0, le=100000000000)],
    department: Annotated[str, Query(max_length=64)] = "Todos",
    service: SearchActiveTenders = Depends(get_tender_service),
):
    """Search endpoint that orchestrates the use case and renders the view."""
    try:
        normalized_department = normalize_department(department)
        results = service.execute(budget=budget, department=normalized_department)
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_page_context(
                request,
                budget=int(budget),
                department_sel=normalized_department,
                results=results,
            ),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_page_context(
                request,
                budget=int(budget),
                department_sel="Todos",
                results=[],
                error=str(exc),
            ),
            status_code=400,
        )
    except Exception:
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_page_context(
                request,
                budget=int(budget),
                department_sel=department if department in ALLOWED_DEPARTMENTS else "Todos",
                results=[],
                error="Error processing request. Please try again later.",
            ),
            status_code=500,
        )
