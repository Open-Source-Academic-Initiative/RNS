import requests
from datetime import datetime
import re
import json

class SecopExtractor:
    def __init__(self):
        self.url_base = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
        self.dataset_id = "p6dx-8zbt"
        # Matriz de palabras clave para el dominio de TI
        self.patron_ti = re.compile(r'\b(software|informátic[ao]|sistemas|computación|desarrollo web|api|datos|programación|cloud|nube|tecnologí[ao]s de la información|tic|ciberseguridad|machine learning|hardware)\b', re.IGNORECASE)

    def consultar(self, presupuesto_max=100000000, departamento=None, limite=1000):
        """
        Consulta alineada con el nombre técnico real de la columna:
        fecha_de_recepcion_de.
        """
        from datetime import timedelta
        # Fecha actual para validar procesos vigentes
        hoy_iso = datetime.now().strftime('%Y-%m-%dT00:00:00.000')
        
        # Filtro robusto corregido: fecha_de_recepcion_de
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
            'User-Agent': 'Mozilla/5.0'
        }

        try:
            print(f"DEBUG: Consultando API SODA con presupuesto <= {presupuesto_max}...")
            response = requests.get(self.url_base, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                datos = response.json()
                print(f"DEBUG: API respondió exitosamente con {len(datos)} registros crudos.")
                return datos
            else:
                print(f"ERROR API: {response.status_code} - {response.text[:100]}")
                return []
        except Exception as e:
            print(f"EXCEPCION RED: {e}")
            return []

    def procesar_datos(self, datos_crudos):
        """
        Aplica filtrado semántico y limpieza de datos sin depender de pandas.
        """
        resultados_finales = []
        
        for item in datos_crudos:
            # Obtener y normalizar campos críticos
            nombre = item.get('nombre_del_procedimiento', '')
            descripcion = item.get('descripci_n_del_procedimiento', '')
            entidad = item.get('entidad', 'N/A')
            fecha = item.get('fecha_de_publicacion_del', 'N/A')
            url = item.get('urlproceso', 'N/A')
            
            try:
                precio = float(item.get('precio_base', 0))
            except ValueError:
                precio = 0.0

            # Concatenación heurística para búsqueda semántica
            texto_analisis = f"{nombre} {descripcion}"

            # Filtrado por Regex TI
            if self.patron_ti.search(texto_analisis):
                # Limpiar fechas (ISO 8601 a YYYY-MM-DD)
                fecha_pub = item.get('fecha_de_publicacion_del', 'N/A').split('T')[0]
                fecha_cierre = item.get('fecha_de_recepcion_de', 'N/A').split('T')[0]
                
                resultados_finales.append({
                    'entidad': entidad,
                    'fecha': fecha_pub,
                    'fecha_cierre': fecha_cierre,
                    'precio_base': precio,
                    'nombre': nombre,
                    'url': url
                })

        # Ordenar por precio descendente
        resultados_finales.sort(key=lambda x: x['precio_base'], reverse=True)
        return resultados_finales

if __name__ == "__main__":
    extractor = SecopExtractor()
    print("Iniciando consulta a SECOP II (Colombia Compra Eficiente)...")
    datos = extractor.consultar()
    
    # Si la API falla por red, usamos un pequeño ejemplo simulado para demostrar funcionalidad
    if not datos:
        print("\n--- Modo Simulación (Falla de Conexión Detectada) ---")
        datos = [
            {
                "entidad": "MINISTERIO DE PRUEBA",
                "precio_base": "85000000",
                "nombre_del_procedimiento": "Desarrollo de Software a la medida",
                "descripci_n_del_procedimiento": "API RESTful de gestión",
                "urlproceso": "https://secop.gov.co/simulado"
            }
        ]
    
    resultados = extractor.procesar_datos(datos)
    
    if resultados:
        print(f"\nSe hallaron {len(resultados)} procesos de TI que cumplen los criterios:")
        print("-" * 80)
        for r in resultados:
            print(f"ENTIDAD: {r['entidad']}")
            print(f"PRECIO:  ${r['precio_base']:,.2f} COP")
            print(f"NOMBRE:  {r['nombre']}")
            print(f"URL:     {r['url']}")
            print("-" * 80)
    else:
        print("\nNo se encontraron procesos que coincidan con los filtros de hoy.")
