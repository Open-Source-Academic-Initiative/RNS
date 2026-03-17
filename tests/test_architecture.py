import unittest
from datetime import datetime, timedelta
from typing import List, Optional
from src.domain.models import Licitacion, LicitacionRepository
from src.application.services import BuscarLicitacionesVigentes
from src.infrastructure.repositories import SocrataLicitacionRepository

# 1. Mock de Infraestructura (Para testear el Dominio/Aplicación aislados)
class MockLicitacionRepository(LicitacionRepository):
    def buscar_por_criterios(self, 
                             presupuesto_max: float, 
                             departamento: Optional[str] = None, 
                             limite: int = 1000) -> List[Licitacion]:
        # Retorna datos dummy controlados
        return [
            Licitacion(
                id="MOCK-001",
                referencia="REF-2026-X",
                entidad="Entidad Mock",
                nombre="Software Mock",
                descripcion="Desc",
                precio_base=50000000.0,
                fecha_publicacion=datetime.now(),
                fecha_cierre=datetime.now() + timedelta(days=5),
                url="http://mock.com",
                departamento="Bogotá"
            )
        ]

class TestArquitecturaHexagonal(unittest.TestCase):
    
    def test_entidad_dominio_vigencia(self):
        """Valida la lógica de negocio en la entidad Licitacion"""
        lic = Licitacion(
            id="1", referencia="REF-01", entidad="Test", nombre="T", descripcion="D", precio_base=100,
            fecha_publicacion=datetime.now(),
            fecha_cierre=datetime.now() + timedelta(days=1), # Futuro
            url="http"
        )
        self.assertTrue(lic.es_vigente)

        lic_vencida = Licitacion(
            id="2", referencia="REF-02", entidad="Test", nombre="T", descripcion="D", precio_base=100,
            fecha_publicacion=datetime.now(),
            fecha_cierre=datetime.now() - timedelta(days=1), # Pasado
            url="http"
        )
        self.assertFalse(lic_vencida.es_vigente)

    def test_caso_uso_buscar_licitaciones(self):
        """Valida el Caso de Uso con un Repositorio Mock (Aislamiento)"""
        repo = MockLicitacionRepository()
        servicio = BuscarLicitacionesVigentes(repo)
        
        resultados = servicio.ejecutar(presupuesto=100000000)
        
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].id, "MOCK-001")
        self.assertEqual(resultados[0].precio_base, 50000000.0)

    def test_validacion_negocio_presupuesto_negativo(self):
        """Valida que el Caso de Uso rechace presupuestos inválidos"""
        repo = MockLicitacionRepository()
        servicio = BuscarLicitacionesVigentes(repo)
        
        with self.assertRaises(ValueError):
            servicio.ejecutar(presupuesto=-100)

class TestInfraestructuraReal(unittest.TestCase):
    """
    Pruebas de Integración con Socrata.
    NOTA: Requiere conexión a internet.
    """
    def test_repositorio_socrata_mapeo(self):
        repo = SocrataLicitacionRepository()
        # Usamos un presupuesto alto para asegurar resultados
        resultados = repo.buscar_por_criterios(presupuesto_max=500000000, limite=5)
        
        # Si la API responde, validamos la estructura
        if resultados:
            item = resultados[0]
            self.assertIsInstance(item, Licitacion)
            self.assertIsInstance(item.fecha_cierre, datetime)
            self.assertGreaterEqual(item.precio_base, 0)

if __name__ == "__main__":
    unittest.main()
