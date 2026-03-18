from typing import List, Optional
from src.domain.models import Tender, TenderRepository

class SearchActiveTenders:
    """Use Case: Search for active business opportunities filtered by budget and location."""
    
    def __init__(self, repository: TenderRepository):
        self.repository = repository

    def execute(self, budget: float, department: Optional[str] = None) -> List[Tender]:
        """
        Executes the search logic.
        
        Args:
            budget: Maximum allowed budget.
            department: Specific department to filter by.
            
        Returns:
            List of matching Tender entities.
            
        Raises:
            ValueError: If budget is negative.
        """
        if budget < 0:
            raise ValueError("Budget cannot be negative")
            
        return self.repository.search_by_criteria(
            max_budget=budget,
            department=department
        )
