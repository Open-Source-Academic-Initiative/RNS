from dataclasses import dataclass
from typing import List, Protocol, Optional
from datetime import datetime

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

    @property
    def is_active(self) -> bool:
        """Checks if the tender is still open for submission."""
        return self.closing_date >= datetime.now()

class TenderRepository(Protocol):
    """Port (Interface) for Tender data access."""
    def search_by_criteria(self, 
                           max_budget: float, 
                           department: Optional[str] = None, 
                           limit: int = 1000) -> List[Tender]:
        ...
