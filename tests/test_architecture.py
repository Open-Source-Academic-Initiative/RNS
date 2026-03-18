import unittest
from datetime import datetime, timedelta
from typing import List, Optional
from src.domain.models import Tender, TenderRepository
from src.application.services import SearchActiveTenders
from src.infrastructure.repositories import SocrataTenderRepository

# 1. Infrastructure Mock (To test Domain/Application in isolation)
class MockTenderRepository(TenderRepository):
    def search_by_criteria(self, 
                           max_budget: float, 
                           department: Optional[str] = None, 
                           limit: int = 1000) -> List[Tender]:
        # Returns controlled dummy data
        return [
            Tender(
                id="MOCK-001",
                reference="REF-2026-X",
                entity="Mock Entity",
                name="Mock Software",
                description="Desc",
                base_price=50000000.0,
                publish_date=datetime.now(),
                closing_date=datetime.now() + timedelta(days=5),
                url="http://mock.com",
                department="Bogotá"
            )
        ]

class TestHexagonalArchitecture(unittest.TestCase):
    
    def test_domain_entity_validity(self):
        """Validates business logic in the Tender entity"""
        tender = Tender(
            id="1", reference="REF-01", entity="Test", name="T", description="D", base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() + timedelta(days=1), # Future
            url="http"
        )
        self.assertTrue(tender.is_active)

        expired_tender = Tender(
            id="2", reference="REF-02", entity="Test", name="T", description="D", base_price=100,
            publish_date=datetime.now(),
            closing_date=datetime.now() - timedelta(days=1), # Past
            url="http"
        )
        self.assertFalse(expired_tender.is_active)

    def test_use_case_search_tenders(self):
        """Validates the Use Case with a Mock Repository (Isolation)"""
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)
        
        results = service.execute(budget=100000000)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "MOCK-001")
        self.assertEqual(results[0].base_price, 50000000.0)

    def test_business_validation_negative_budget(self):
        """Validates that the Use Case rejects invalid budgets"""
        repo = MockTenderRepository()
        service = SearchActiveTenders(repo)
        
        with self.assertRaises(ValueError):
            service.execute(budget=-100)

class TestRealInfrastructure(unittest.TestCase):
    """
    Integration Tests with Socrata.
    NOTE: Requires internet connection.
    """
    def test_socrata_repository_mapping(self):
        repo = SocrataTenderRepository()
        # Use a high budget to ensure results
        results = repo.search_by_criteria(max_budget=500000000, limit=5)
        
        # If API responds, validate structure
        if results:
            item = results[0]
            self.assertIsInstance(item, Tender)
            self.assertIsInstance(item.closing_date, datetime)
            self.assertGreaterEqual(item.base_price, 0)

if __name__ == "__main__":
    unittest.main()
