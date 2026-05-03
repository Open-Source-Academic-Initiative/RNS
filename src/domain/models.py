from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Protocol
from zoneinfo import ZoneInfo

# SECOP II publishes Colombian local-time dates as naive strings; the repository
# converts "now" to Bogotá wall clock and strips tz before comparing. The domain
# entity mirrors that convention so `is_active` does not drift on a server with
# a different system timezone.
_RNS_TIMEZONE = ZoneInfo("America/Bogota")


def _rns_now_naive() -> datetime:
    return datetime.now(_RNS_TIMEZONE).replace(tzinfo=None, microsecond=0)


@dataclass
class Tender:
    """Domain Entity: Represents a business opportunity in SECOP II."""

    id: str
    reference: str
    entity: str
    name: str
    description: str
    base_price: float
    publish_date: datetime
    closing_date: datetime
    url: str
    department: Optional[str] = None
    status: str = "Open"
    opening_status: str = "Abierto"
    phase: Optional[str] = None
    modality: Optional[str] = None
    # Contract metadata
    tipo_de_contrato: Optional[str] = None
    ordenentidad: Optional[str] = None
    duracion: Optional[float] = None
    unidad_de_duracion: Optional[str] = None
    unspsc_code: Optional[str] = None
    adjudicado: bool = False
    last_updated_date: Optional[datetime] = None
    # Competitive intelligence
    proveedores_invitados: Optional[int] = None
    proveedores_que_manifestaron: Optional[int] = None
    respuestas_al_procedimiento: Optional[int] = None
    proveedores_unicos_con: Optional[int] = None
    competitive_density_score: float = 0.0
    # Action and scoring
    supplier_action_code: str = "review"
    supplier_action_label: str = "Revisar manualmente"
    supplier_action_detail: str = "Validar etapa, cronograma y requisitos habilitantes en SECOP II antes de actuar."
    supplier_action_rank: int = 60
    profile: str = "generic_it"
    match_score: float = 0.0
    match_label: str = "Bajo encaje"
    match_reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    freshness_score: float = 0.0
    days_since_publication: Optional[int] = None
    closing_date_known: bool = True
    deadline_confidence: str = "confirmada"
    cluster_id: str = ""
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    is_new: bool = False

    @property
    def is_active(self) -> bool:
        """Checks if the tender is still open for submission."""
        if self.adjudicado:
            return False
        if self.opening_status and self.opening_status.strip().casefold() != "abierto":
            return False
        if not self.closing_date_known:
            return True
        return self.closing_date >= _rns_now_naive()


class TenderRepository(Protocol):
    """Port (Interface) for Tender data access."""

    async def search_by_criteria(
        self,
        min_budget: float,
        max_budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 10000,
        process_status: Optional[str] = None,
        phase: Optional[str] = None,
        published_since_days: int = 60,
        profile: str = "opensai",
        only_high_fit: bool = False,
        only_new: bool = False,
    ) -> List[Tender]:
        ...
