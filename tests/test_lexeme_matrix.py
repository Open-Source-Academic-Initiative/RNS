import unittest
from src.infrastructure.constants import IT_KEYWORD_PATTERN
from src.infrastructure.repositories import SocrataTenderRepository

class TestLexemeMatrixConformity(unittest.TestCase):
    """
    Specific test suite to ensure that search results strictly conform 
    to the Extended IT Lexeme Matrix (V2.4).
    """

    def setUp(self):
        self.repository = SocrataTenderRepository()
        
        # 1. Positive Samples: These MUST match the matrix
        self.positive_samples = [
            "Desarrollo de software a la medida",
            "Mantenimiento preventivo de hardware",
            "Suscripción de servicios cloud computing",
            "Implementación de firma digital y biometría",
            "Consultoría en arquitectura empresarial y gobierno de datos",
            "Auditoría informática y ciberseguridad",
            "Fábrica de software con metodología DevOps",
            "Análisis predictivo mediante machine learning",
            "Transformación digital y hoja de ruta tecnológica",
            "Adquisición de licencias de software privativo",
            "Instalación de cluster de Kubernetes (K8s)",
            "Gestión del conocimiento y propiedad intelectual",
            "Desarrollo de MVP y pruebas de concepto (POC)",
            "Interoperabilidad y estándares técnicos",
            "Infraestructura crítica y hardening de servidores"
        ]

        # 2. Negative Samples: These MUST NOT match the matrix
        self.negative_samples = [
            "Suministro de papelería y útiles de oficina",
            "Mantenimiento de zonas verdes y jardinería",
            "Prestación de servicios de vigilancia privada",
            "Compra de uniformes para personal administrativo",
            "Servicio de cafetería y alimentación",
            "Arrendamiento de vehículos de carga",
            "Construcción de obras civiles y alcantarillado",
            "Suministro de combustible para flota vehicular",
            "Organización de eventos sociales y logística",
            "Servicio de limpieza y aseo general"
        ]

    def test_matrix_positive_matches(self):
        """Validates that all representative IT terms match the pattern."""
        for sample in self.positive_samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    IT_KEYWORD_PATTERN.search(sample),
                    f"Sample failed to match IT Matrix: '{sample}'"
                )

    def test_matrix_negative_matches(self):
        """Validates that non-IT terms are correctly ignored by the pattern."""
        for sample in self.negative_samples:
            with self.subTest(sample=sample):
                self.assertFalse(
                    IT_KEYWORD_PATTERN.search(sample),
                    f"Non-IT sample incorrectly matched the Matrix: '{sample}'"
                )

    def test_repository_filtering_logic(self):
        """
        Validates that the Repository correctly filters out non-IT items
        when mapping raw data to domain entities.
        """
        raw_data = []
        # Create raw items for all samples
        for i, text in enumerate(self.positive_samples + self.negative_samples):
            raw_data.append({
                'id_del_proceso': f"ID-{i}",
                'nombre_del_procedimiento': text,
                'descripci_n_del_procedimiento': f"Description for {text}",
                'precio_base': "1000000",
                'fecha_de_publicacion_del': '2026-01-01T00:00:00.000',
                'fecha_de_recepcion_de': '2026-12-31T00:00:00.000',
                'entidad': 'Test Entity',
                'urlproceso': 'http://test.com'
            })

        # Process through repository mapping
        mapped_results = self.repository._map_to_domain(raw_data)

        # Assertions
        expected_count = len(self.positive_samples)
        self.assertEqual(
            len(mapped_results), 
            expected_count,
            f"Expected {expected_count} IT results, but got {len(mapped_results)}"
        )

        # Verify that all results are indeed from the positive list
        for tender in mapped_results:
            self.assertIn(tender.name, self.positive_samples)

    def test_word_boundary_security(self):
        """
        Ensures that keywords don't trigger false positives by matching 
        parts of unrelated words (e.g., 'ia' in 'industria').
        """
        false_positive_candidates = [
            "Industria manufacturera", # 'ia' is inside 'Industria'
            "Asmático",                # 'tic' is inside 'Asmático'
            "Ecléctico",               # 'tic' is inside 'Ecléctico'
            "Software-less approach"    # Should match because of word boundary
        ]
        
        self.assertFalse(IT_KEYWORD_PATTERN.search("Industria"))
        self.assertFalse(IT_KEYWORD_PATTERN.search("Asmático"))
        self.assertTrue(IT_KEYWORD_PATTERN.search("Software-less"))

if __name__ == "__main__":
    unittest.main()
