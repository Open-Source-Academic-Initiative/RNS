from src.infrastructure.repositories import SocrataTenderRepository

class SecopExtractor:
    """Compatibility CLI wrapper over the shared repository implementation."""

    def __init__(self, repository=None):
        self.repository = repository or SocrataTenderRepository()
        self.base_url = self.repository.BASE_URL
        self.dataset_id = "p6dx-8zbt"

    def fetch_data(self, max_budget=100000000, department=None, limit=1000):
        """Fetches raw records using the shared repository query logic."""
        return self.repository.fetch_raw_records(
            max_budget=max_budget,
            department=department,
            limit=limit,
        )

    def process_data(self, raw_data):
        """Applies the shared semantic mapping and adapts the result for CLI output."""
        final_results = []

        tenders = self.repository._map_to_domain(raw_data)
        for tender in sorted(tenders, key=lambda item: item.base_price, reverse=True):
            final_results.append({
                "entity": tender.entity,
                "publish_date": tender.publish_date.strftime("%Y-%m-%d"),
                "closing_date": tender.closing_date.strftime("%Y-%m-%d"),
                "base_price": tender.base_price,
                "name": tender.name,
                "url": tender.url,
            })

        return final_results

if __name__ == "__main__":
    extractor = SecopExtractor()
    print("Starting query to SECOP II (Colombia Compra Eficiente)...")
    data = extractor.fetch_data()
    
    # If API fails due to network, use a small simulated example to demonstrate functionality
    if not data:
        print("\n--- Simulation Mode (Connection Failure Detected) ---")
        data = [
            {
                "entidad": "TEST MINISTRY",
                "precio_base": "85000000",
                "nombre_del_procedimiento": "Custom Software Development",
                "descripci_n_del_procedimiento": "Management RESTful API",
                "urlproceso": "https://secop.gov.co/simulated"
            }
        ]
    
    results = extractor.process_data(data)
    
    if results:
        print(f"\nFound {len(results)} IT processes matching criteria:")
        print("-" * 80)
        for r in results:
            print(f"ENTITY: {r['entity']}")
            print(f"PRICE:  ${r['base_price']:,.2f} COP")
            print(f"NAME:   {r['name']}")
            print(f"URL:    {r['url']}")
            print("-" * 80)
    else:
        print("\nNo processes found matching today's filters.")
