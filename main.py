from fastapi import FastAPI, Request, Query, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from typing import Optional, Annotated

# Importaciones de Arquitectura Hexagonal
from src.infrastructure.repositories import SocrataLicitacionRepository
from src.application.services import BuscarLicitacionesVigentes

app = FastAPI(
    title="SECOP II - Radar TI",
    description="Herramienta de vigilancia tecnológica para contratación pública",
    version="2.0.0"
)

# Seguridad: Middleware para restringir hosts (OWASP)
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0"]
)

templates = Jinja2Templates(directory="templates")

# Inyección de Dependencias
def get_licitacion_service():
    """Factory para inyectar el repositorio en el caso de uso"""
    repo = SocrataLicitacionRepository()
    return BuscarLicitacionesVigentes(repo)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Interfaz principal"""
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "resultados": None,
        "presupuesto": 100000000,
        "departamento_sel": "Todos"
    })

@app.get("/consultar", response_class=HTMLResponse)
async def consultar(
    request: Request, 
    presupuesto: Annotated[float, Query(gt=0, le=100000000000)], # Validación Pydantic
    departamento: str = "Todos",
    service: BuscarLicitacionesVigentes = Depends(get_licitacion_service)
):
    """
    Endpoint de consulta que orquesta el Caso de Uso.
    Valida entradas y renderiza la vista.
    """
    try:
        # Ejecución del Caso de Uso Puro
        resultados = service.ejecutar(presupuesto=presupuesto, departamento=departamento)
        
        # Adaptación para la vista (si fuera necesario, aquí irían DTOs de vista)
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "resultados": resultados, 
            "presupuesto": int(presupuesto),
            "departamento_sel": departamento,
            "es_simulacion": False # Ya no simulamos, confiamos en el repo
        })
    except Exception as e:
        # Manejo de errores global para UI
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "resultados": [], 
            "error": f"Error procesando la solicitud: {str(e)}",
            "presupuesto": presupuesto
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
