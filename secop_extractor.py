import requests
from datetime import datetime
import re
import json

class SecopExtractor:
    def __init__(self):
        self.base_url = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
        self.dataset_id = "p6dx-8zbt"
        # IT Keyword Matrix
        self.it_pattern = re.compile(r'\b(software|informátic[ao]|sistemas|computación|desarrollo web|api|datos|programación|cloud|nube|tecnologí[ao]s de la información|tic|ciberseguridad|machine learning|hardware)\b', re.IGNORECASE)

    def fetch_data(self, max_budget=100000000, department=None, limit=1000):
        """
        Query aligned with the technical column name: fecha_de_recepcion_de.
        """
        # Current date to validate active processes
        today_iso = datetime.now().strftime('%Y-%m-%dT00:00:00.000')
        
        # Robust filter: fecha_de_recepcion_de
        where_clause = (
            f"precio_base <= {max_budget} "
            f"AND estado_de_apertura_del_proceso = 'Abierto' "
            f"AND fecha_de_recepcion_de >= '{today_iso}'"
        )
        
        if department and department != "Todos":
            where_clause += f" AND departamento_entidad = '{department}'"

        params = {
            "$where": where_clause,
            "$limit": limit
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0'
        }

        try:
            print(f"DEBUG: Querying SODA API with budget <= {max_budget}...")
            response = requests.get(self.base_url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                print(f"DEBUG: API responded successfully with {len(data)} raw records.")
                return data
            else:
                print(f"API ERROR: {response.status_code} - {response.text[:100]}")
                return []
        except Exception as e:
            print(f"NETWORK EXCEPTION: {e}")
            return []

    def process_data(self, raw_data):
        """
        Applies semantic filtering and data cleaning without depending on pandas.
        """
        final_results = []
        
        for item in raw_data:
            # Get and normalize critical fields
            name = item.get('nombre_del_procedimiento', '')
            description = item.get('descripci_n_del_procedimiento', '')
            entity = item.get('entidad', 'N/A')
            url = item.get('urlproceso', 'N/A')
            
            try:
                price = float(item.get('precio_base', 0))
            except ValueError:
                price = 0.0

            # Heuristic concatenation for semantic search
            analysis_text = f"{name} {description}"

            # Filter by IT Regex
            if self.it_pattern.search(analysis_text):
                # Clean dates (ISO 8601 to YYYY-MM-DD)
                pub_date = item.get('fecha_de_publicacion_del', 'N/A').split('T')[0]
                closing_date = item.get('fecha_de_recepcion_de', 'N/A').split('T')[0]
                
                final_results.append({
                    'entity': entity,
                    'publish_date': pub_date,
                    'closing_date': closing_date,
                    'base_price': price,
                    'name': name,
                    'url': url
                })

        # Sort by price descending
        final_results.sort(key=lambda x: x['base_price'], reverse=True)
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
