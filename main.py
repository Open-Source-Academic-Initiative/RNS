from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from typing import Optional, Annotated

# Hexagonal Architecture Imports
from src.infrastructure.repositories import SocrataTenderRepository
from src.application.services import SearchActiveTenders

app = FastAPI(
    title="SECOP II - IT Radar",
    description="Technology vigilance tool for public procurement.",
    version="2.0.0"
)

# Security: Middleware to restrict hosts (OWASP)
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "testserver"]
)

templates = Jinja2Templates(directory="templates")

# Dependency Injection
def get_tender_service():
    """Factory to inject the repository into the use case."""
    repo = SocrataTenderRepository()
    return SearchActiveTenders(repo)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main Interface."""
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "results": None,
        "budget": 100000000,
        "department_sel": "Todos"
    })

@app.get("/search", response_class=HTMLResponse)
async def search(
    request: Request, 
    budget: Annotated[float, Query(gt=0, le=100000000000)], # Pydantic Validation
    department: str = "Todos",
    service: SearchActiveTenders = Depends(get_tender_service)
):
    """
    Search endpoint that orchestrates the Use Case.
    Validates inputs and renders the view.
    """
    try:
        # Pure Use Case Execution
        results = service.execute(budget=budget, department=department)
        
        # Adaptation for the view
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "results": results, 
            "budget": int(budget),
            "department_sel": department,
            "is_simulation": False
        })
    except Exception as e:
        # Global error handling for UI
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "results": [], 
            "error": f"Error processing request: {str(e)}",
            "budget": budget
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
