from typing import List, Optional

from src.application.validators import normalize_department
from src.domain.models import Tender, TenderRepository


class SearchActiveTenders:
    """Use Case: Search for active business opportunities filtered by budget, location and keyword."""

    def __init__(self, repository: TenderRepository):
        self.repository = repository

    async def execute(
        self,
        budget: float,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Tender]:
        """Executes the search use case and returns the matching tenders.

        Raises ValueError if the budget is negative or the department is unsupported.
        """
        if budget < 0:
            raise ValueError("Budget cannot be negative")

        normalized_department = normalize_department(department)

        return await self.repository.search_by_criteria(
            max_budget=budget,
            department=normalized_department,
            keyword=keyword,
        )
