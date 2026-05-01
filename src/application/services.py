from typing import List, Optional

from src.application.validators import (
    normalize_department,
    normalize_phase,
    normalize_process_status,
    normalize_profile,
)
from src.domain.models import Tender, TenderRepository


class SearchActiveTenders:
    """Use Case: Search for active business opportunities filtered by budget, location and keyword."""

    def __init__(self, repository: TenderRepository):
        self.repository = repository

    async def execute(
        self,
        budget: float,
        min_budget: float = 0,
        department: Optional[str] = None,
        keyword: Optional[str] = None,
        process_status: Optional[str] = None,
        phase: Optional[str] = None,
        published_since_days: int = 60,
        profile: str = "opensai",
        only_high_fit: bool = False,
        only_new: bool = False,
    ) -> List[Tender]:
        """Executes the search use case and returns the matching tenders.

        Raises ValueError if the budget is negative, the department is unsupported,
        or the process status/phase filter is unsupported.
        """
        if budget < 0:
            raise ValueError("Budget cannot be negative")
        if min_budget < 0:
            raise ValueError("Minimum budget cannot be negative")
        if min_budget > budget:
            raise ValueError("Minimum budget cannot exceed maximum budget")
        if published_since_days <= 0:
            raise ValueError("Published-since window must be positive")

        normalized_department = normalize_department(department)
        normalized_process_status = normalize_process_status(process_status)
        normalized_phase = normalize_phase(phase)
        normalized_profile = normalize_profile(profile)

        return await self.repository.search_by_criteria(
            min_budget=min_budget,
            max_budget=budget,
            department=normalized_department,
            keyword=keyword,
            process_status=normalized_process_status,
            phase=normalized_phase,
            published_since_days=published_since_days,
            profile=normalized_profile,
            only_high_fit=only_high_fit,
            only_new=only_new,
        )
