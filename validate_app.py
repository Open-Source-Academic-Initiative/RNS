import unittest
from fastapi.testclient import TestClient
from main import app
import os

class TestWebInterface(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_home_page_loads(self):
        """Verifies that the home page loads correctly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        # Assuming the template now says "SECOP II - IT Radar" or similar
        self.assertIn("SECOP II - IT Radar", response.text)

    def test_search_endpoint(self):
        """Verifies that the search endpoint returns results (or simulation)."""
        # Updated endpoint from /consultar to /search and param presupuesto to budget
        response = self.client.get("/search?budget=100000000")
        self.assertEqual(response.status_code, 200)
        # Updated template text assertion
        self.assertIn("Tenders Found", response.text)

    def test_templates_exist(self):
        """Verifies the existence of the template file."""
        self.assertTrue(os.path.exists("templates/index.html"))

if __name__ == "__main__":
    unittest.main()
