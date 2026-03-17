from dataclasses import dataclass
from typing import List, Protocol, Optional
from datetime import datetime

@dataclass
class Licitacion:
    """Entidad de Dominio: Representa una oportunidad de negocio en el SECOP II"""
    id: str
    referencia: str
    entidad: str
    nombre: str
    descripcion: str
    precio_base: float
    fecha_publicacion: datetime
    fecha_cierre: datetime
    url: str
    departamento: Optional[str] = None
    estado_apertura: str = "Abierto"

    @property
    def es_vigente(self) -> bool:
        return self.fecha_cierre >= datetime.now()

class LicitacionRepository(Protocol):
    """Puerto (Interface) para el acceso a datos de Licitaciones"""
    def buscar_por_criterios(self, 
                             presupuesto_max: float, 
                             departamento: Optional[str] = None, 
                             limite: int = 1000) -> List[Licitacion]:
        ...
