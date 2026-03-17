import re
import requests
from datetime import datetime, timedelta
from typing import List, Optional
from src.domain.models import Licitacion, LicitacionRepository

class SocrataLicitacionRepository(LicitacionRepository):
    """Adaptador de Infraestructura para consumir la API de Socrata (SECOP II)"""
    
    URL_BASE = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
    
    # Matriz Extensa de Lexemas TI (Arquitectura de Alta Fidelidad V2.4)
    PATRON_TI = re.compile(
        r'\b('
        r'software|informátic[ao]|sistemas|computación|desarrollo|web|api|datos|programación|cloud|nube|tecnologí[ao]s de la información|tic|ciberseguridad|machine learning|hardware|'
        r'i\+d\+i|investigación aplicada|investigación y desarrollo|ciencia de datos|análisis predictivo|algoritmos|inteligencia artificial|ia|'
        r'innovación abierta|gestión tecnológica|prospectiva tecnológica|vigilancia tecnológica|transferencia de tecnología|madurez tecnológica|trl|'
        r'prototipado|mvp|prueba de concepto|poc|fábrica de software|laboratorio de innovación|sandbox|'
        r'gestión del conocimiento|propiedad intelectual|patente|derecho de autor|licenciamiento abierto|creative commons|repositorio digital|'
        r'transformación digital|hoja de ruta|roadmap tecnológico|estándares técnicos|interoperabilidad|analítica avanzada|'
        r'diseño web|página web|sitio web|portal web|e-commerce|tienda virtual|interfaz|ux/ui|'
        r'firma digital|certificado digital|biometría|identidad digital|autenticación|'
        r'consultoría especializada|asesoría técnica|apoyo a la gestión tics|arquitectura empresarial|gobierno de datos|auditoría informática|'
        r'mantenimiento preventivo|mantenimiento correctivo|soporte técnico|mesa de ayuda|help desk|reparación|'
        r'adquisición de licencias|suscripción de software|compra de equipos|suministro tecnológico|renovación tecnológica|'
        r'linux|gnu|ubuntu|debian|redhat|rhel|fedora|centos|kernel|bash|shell|terminal|'
        r'sysadmin|devops|sre|kubernetes|k8s|openshift|container|docker|podman|oci|helm|operator|cluster|node|pod|namespace|ingress|service|deployment|configmap|secret|'
        r'ci/cd|git|gitlab|github|pipeline|iac|ansible|terraform|virtualización|kvm|xen|qemu|'
        r'apache|nginx|php|python|javascript|typescript|backend|frontend|fullstack|rest|microservicios|monolito|'
        r'postgresql|mysql|mariadb|joomla|wordpress|cms|plugin|theme|template|hosting|dominio|ssl|https|dns|ldap|'
        r'yaml|json|markdown|opensource|foss|licencia|licenciamiento|gpl|mit|apache-2.0|automatización|'
        r'observabilidad|logging|monitoring|prometheus|grafana|elk|seguridad|hardening|firewall|selinux|apparmor|'
        r'paquete|repositorio|snap|flatpak|soluciones|aplicaciones'
        r')\b', 
        re.IGNORECASE
    )

    def buscar_por_criterios(self, 
                             presupuesto_max: float, 
                             departamento: Optional[str] = None, 
                             limite: int = 1000) -> List[Licitacion]:
        """
        Consulta la API de Socrata aplicando filtros de negocio y mapea a Entidades de Dominio.
        """
        hoy_iso = datetime.now().strftime('%Y-%m-%dT00:00:00.000')
        
        # Filtro SoQL Alineado al Marco Metodológico (Apertura + Vigencia)
        where_clause = (
            f"precio_base <= {presupuesto_max} "
            f"AND estado_de_apertura_del_proceso = 'Abierto' "
            f"AND fecha_de_recepcion_de >= '{hoy_iso}'"
        )
        
        if departamento and departamento != "Todos":
            where_clause += f" AND departamento_entidad = '{departamento}'"

        params = {
            "$where": where_clause,
            "$limit": limite
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            response = requests.get(self.URL_BASE, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return self._mapear_a_dominio(data)
        except requests.exceptions.RequestException as e:
            print(f"Error de Infraestructura (Socrata): {e}")
            return []

    def _mapear_a_dominio(self, data: List[dict]) -> List[Licitacion]:
        resultados = []
        for item in data:
            nombre = item.get('nombre_del_procedimiento', '')
            descripcion = item.get('descripci_n_del_procedimiento', '')
            texto_analisis = f"{nombre} {descripcion}"

            # Filtrado de Dominio (TI Only)
            if self.PATRON_TI.search(texto_analisis):
                try:
                    # Extracción y limpieza segura de fechas
                    f_pub_str = item.get('fecha_de_publicacion_del', '').split('T')[0]
                    f_cierre_str = item.get('fecha_de_recepcion_de', '').split('T')[0]
                    
                    f_pub = datetime.strptime(f_pub_str, '%Y-%m-%d') if f_pub_str else datetime.min
                    f_cierre = datetime.strptime(f_cierre_str, '%Y-%m-%d') if f_cierre_str else datetime.max
                    
                    # Extracción segura de URL (puede venir como dict o str)
                    raw_url = item.get('urlproceso', '#')
                    url_final = raw_url.get('url', '#') if isinstance(raw_url, dict) else raw_url

                    licitacion = Licitacion(
                        id=item.get('id_del_proceso', 'N/A'),
                        referencia=item.get('referencia_del_proceso', 'N/A'),
                        entidad=item.get('entidad', 'N/A'),
                        nombre=nombre,
                        descripcion=descripcion,
                        precio_base=float(item.get('precio_base', 0)),
                        fecha_publicacion=f_pub,
                        fecha_cierre=f_cierre,
                        url=url_final,
                        departamento=item.get('departamento_entidad'),
                        estado_apertura=item.get('estado_de_apertura_del_proceso', 'Desconocido')
                    )
                    resultados.append(licitacion)
                except (ValueError, TypeError) as e:
                    # Log de error de mapeo silenciado para no romper flujo
                    continue
        
        # Ordenar por Cierre (Urgencia)
        return sorted(resultados, key=lambda x: x.fecha_cierre)
