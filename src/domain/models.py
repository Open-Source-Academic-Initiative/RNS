from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Protocol


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
        if self.opening_status and self.opening_status.strip().casefold() != "abierto":
            return False
        if not self.closing_date_known:
            return True
        return self.closing_date >= datetime.now()


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
