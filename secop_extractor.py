from typing import Optional

from src.infrastructure.repositories import SocrataTenderRepository

DEFAULT_BUDGET = 100000000
DEFAULT_LIMIT = 1000
SIMULATED_RAW_DATA = [
    {
        "entidad": "TEST MINISTRY",
        "precio_base": "85000000",
        "nombre_del_procedimiento": "Custom Software Development",
        "descripci_n_del_procedimiento": "Management RESTful API",
        "urlproceso": "https://secop.gov.co/simulated",
    }
]


class SecopExtractor:
    """Compatibility CLI wrapper over the shared repository implementation."""

    def __init__(self, repository: Optional[SocrataTenderRepository] = None):
        self.repository = repository or SocrataTenderRepository()
        self.base_url = self.repository.BASE_URL
        self.dataset_id = "p6dx-8zbt"

    def fetch_data(self, max_budget: float = DEFAULT_BUDGET, department=None, limit: int = DEFAULT_LIMIT):
        """Fetches raw records using the shared repository query logic."""
        return self.repository.fetch_raw_records(
            max_budget=max_budget,
            department=department,
            limit=limit,
        )

    def process_data(self, raw_data):
        """Applies the shared semantic mapping and adapts the result for CLI output."""
        formatted_results = []

        tenders = self.repository.map_raw_records(raw_data)
        for tender in sorted(tenders, key=lambda item: item.base_price, reverse=True):
            formatted_results.append({
                "entity": tender.entity,
                "publish_date": tender.publish_date.strftime("%Y-%m-%d"),
                "closing_date": tender.closing_date.strftime("%Y-%m-%d"),
                "base_price": tender.base_price,
                "name": tender.name,
                "url": tender.url,
            })

        return formatted_results


def _print_results(results):
    if not results:
        print("\nNo processes found matching today's filters.")
        return

    print(f"\nFound {len(results)} IT processes matching criteria:")
    print("-" * 80)
    for result in results:
        print(f"ENTITY: {result['entity']}")
        print(f"PRICE:  ${result['base_price']:,.2f} COP")
        print(f"NAME:   {result['name']}")
        print(f"URL:    {result['url']}")
        print("-" * 80)


def main():
    extractor = SecopExtractor()
    print("Starting query to SECOP II (Colombia Compra Eficiente)...")
    raw_records = extractor.fetch_data()

    if not raw_records:
        print("\n--- Simulation Mode (Connection Failure Detected) ---")
        raw_records = SIMULATED_RAW_DATA

    _print_results(extractor.process_data(raw_records))


if __name__ == "__main__":
    main()
