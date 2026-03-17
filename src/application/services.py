from typing import List, Optional
from src.domain.models import Licitacion, LicitacionRepository

class BuscarLicitacionesVigentes:
    """Caso de Uso: Buscar oportunidades de negocio vigentes filtradas por presupuesto y ubicación"""
    
    def __init__(self, repositorio: LicitacionRepository):
        self.repositorio = repositorio

    def ejecutar(self, presupuesto: float, departamento: Optional[str] = None) -> List[Licitacion]:
        # Validaciones de negocio podrían ir aquí (ej. presupuesto no negativo)
        if presupuesto < 0:
            raise ValueError("El presupuesto no puede ser negativo")
            
        return self.repositorio.buscar_por_criterios(
            presupuesto_max=presupuesto,
            departamento=departamento
        )
