import requests
from datetime import datetime
from typing import List, Optional
from src.domain.models import Tender, TenderRepository
from src.infrastructure.constants import IT_KEYWORD_PATTERN

class SocrataTenderRepository(TenderRepository):
    """Infrastructure Adapter: Consumes the Socrata API (SECOP II) to fetch tenders."""
    
    BASE_URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
    
    def search_by_criteria(self, 
                           max_budget: float, 
                           department: Optional[str] = None, 
                           limit: int = 1000) -> List[Tender]:
        """
        Queries the Socrata API applying business filters and maps results to Domain Entities.
        """
        today_iso = datetime.now().strftime('%Y-%m-%dT00:00:00.000')
        
        # SoQL Filter Aligned with Methodological Framework (Open Status + Active Validity)
        # Note: API column names (Spanish) must match the remote dataset schema.
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return self._map_to_domain(data)
        except requests.exceptions.RequestException as e:
            print(f"Infrastructure Error (Socrata): {e}")
            return []

    def _map_to_domain(self, data: List[dict]) -> List[Tender]:
        results = []
        for item in data:
            name = item.get('nombre_del_procedimiento', '')
            description = item.get('descripci_n_del_procedimiento', '')
            analysis_text = f"{name} {description}"

            # Domain Filtering (IT Only)
            if IT_KEYWORD_PATTERN.search(analysis_text):
                try:
                    # Safe date extraction and cleaning
                    pub_date_str = item.get('fecha_de_publicacion_del', '').split('T')[0]
                    closing_date_str = item.get('fecha_de_recepcion_de', '').split('T')[0]
                    
                    pub_date = datetime.strptime(pub_date_str, '%Y-%m-%d') if pub_date_str else datetime.min
                    closing_date = datetime.strptime(closing_date_str, '%Y-%m-%d') if closing_date_str else datetime.max
                    
                    # Safe URL extraction (can be dict or str)
                    raw_url = item.get('urlproceso', '#')
                    final_url = raw_url.get('url', '#') if isinstance(raw_url, dict) else raw_url

                    tender = Tender(
                        id=item.get('id_del_proceso', 'N/A'),
                        reference=item.get('referencia_del_proceso', 'N/A'),
                        entity=item.get('entidad', 'N/A'),
                        name=name,
                        description=description,
                        base_price=float(item.get('precio_base', 0)),
                        publish_date=pub_date,
                        closing_date=closing_date,
                        url=final_url,
                        department=item.get('departamento_entidad'),
                        status=item.get('estado_de_apertura_del_proceso', 'Unknown')
                    )
                    results.append(tender)
                except (ValueError, TypeError):
                    # Silenced mapping error log to avoid breaking flow
                    continue
        
        # Sort by Closing Date (Urgency)
        return sorted(results, key=lambda x: x.closing_date)
