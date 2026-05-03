import unittest

from src.infrastructure.constants import GENERIC_NEGATIVE_PATTERN, IT_KEYWORD_PATTERN, MATCH_PROFILES, SOCRATA_LIKE_SEEDS
from src.infrastructure.repositories import DEFAULT_MAX_SEED_CLAUSE_LENGTH, SocrataTenderRepository


class TestLexemeMatrixConformity(unittest.TestCase):
    def setUp(self):
        self.repository = SocrataTenderRepository(snapshot_db_path=":memory:")

        self.positive_samples = [
            "Administración de campus virtual Moodle",
            "Manual de instalación y configuración de OpenEDX",
            "Virtualización de infraestructura Linux con KVM y Libvirt",
            "Gobernanza de datos y tableros de control en AWS",
            "Accesibilidad web WCAG y asistencia por voz",
            "Transferencia tecnológica y alfabetización digital",
            "Centro de operación de seguridad y ciberseguridad",
            "Servicios de mesa de ayuda y soporte de infraestructura TIC",
        ]

        self.negative_samples = [
            "Suministro de papelería y útiles de oficina",
            "Mantenimiento de zonas verdes y jardinería",
            "Servicio de cafetería y alimentación",
            "Adquisición de plántulas incluida la siembra",
            "Servicio de grúa canasta para luminarias",
            "Obras eléctricas complementarias y tableros eléctricos",
        ]

    def tearDown(self):
        self.repository._snapshot_store.close()

    def test_matrix_positive_matches(self):
        for sample in self.positive_samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    IT_KEYWORD_PATTERN.search(sample),
                    f"Sample failed to match IT Matrix: '{sample}'",
                )

    def test_matrix_negative_exclusions(self):
        for sample in self.negative_samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    GENERIC_NEGATIVE_PATTERN.search(sample),
                    f"Negative exclusion failed: '{sample}'",
                )

    def test_repository_filtering_logic_ignores_negative_exclusions(self):
        raw_data = []
        for i, text in enumerate(self.positive_samples + self.negative_samples):
            raw_data.append(
                {
                    "id_del_proceso": f"ID-{i}",
                    "referencia_del_proceso": f"REF-{i}",
                    "nombre_del_procedimiento": text,
                    "descripci_n_del_procedimiento": f"Description for {text}",
                    "precio_base": "100000000",
                    "fecha_de_publicacion_del": "2026-04-01T00:00:00.000",
                    "fecha_de_recepcion_de": "2026-12-31T00:00:00.000",
                    "entidad": "Test Entity",
                    "urlproceso": {"url": "http://test.com"},
                    "estado_de_apertura_del_proceso": "Abierto",
                    "estado_del_procedimiento": "Publicado",
                    "fase": "Presentación de oferta",
                    "departamento_entidad": "Distrito Capital de Bogotá",
                }
            )

        mapped_results = self.repository.map_raw_records(raw_data)

        expected_count = len(self.positive_samples)
        self.assertEqual(len(mapped_results), expected_count)
        for tender in mapped_results:
            self.assertIn(tender.name, self.positive_samples)

    def test_socrata_prefilter_covers_representative_positive_samples(self):
        upper_seeds = [seed.upper() for seed in SOCRATA_LIKE_SEEDS]
        representative_samples = [
            "Campus virtual Moodle",
            "Virtualización Linux con KVM",
            "Gobernanza de datos y machine learning",
            "Accesibilidad WCAG",
        ]
        for sample in representative_samples:
            with self.subTest(sample=sample):
                self.assertTrue(any(seed in sample.upper() for seed in upper_seeds))

    def test_socrata_prefilter_covers_each_it_category(self):
        upper_seeds = [seed.upper() for seed in SOCRATA_LIKE_SEEDS]
        category_samples = {
            "civic_tech": "Plataforma de datos abiertos para transparencia",
            "lms_learning": "Implementación de Moodle como campus virtual",
            "accessibility": "Auditoría de accesibilidad WCAG",
            "linux_infra": "Servicios de virtualización Linux con KVM y Libvirt",
            "ai_data_science": "Servicios de machine learning sobre big data",
            "academic_management": "Repositorio digital institucional",
            "core_it": "Servicio de ciberseguridad y antivirus corporativo",
        }
        for category, sample in category_samples.items():
            with self.subTest(category=category):
                self.assertTrue(
                    any(seed in sample.upper() for seed in upper_seeds),
                    f"Ninguna seed cubre la categoría '{category}' (sample: '{sample}'). "
                    "El prefilter Socrata debe ser tan ancho como IT_KEYWORD_PATTERN.",
                )

    def test_socrata_seed_clause_fits_within_budget(self):
        clause = self.repository._build_seed_clause()
        self.assertGreater(len(clause), 0, "La cláusula seed no debe estar vacía")
        self.assertLessEqual(
            len(clause),
            DEFAULT_MAX_SEED_CLAUSE_LENGTH,
            f"Cláusula seed mide {len(clause)} chars, supera el límite "
            f"{DEFAULT_MAX_SEED_CLAUSE_LENGTH}; el repositorio la desactivaría.",
        )

    def test_socrata_seeds_avoid_short_substrings(self):
        # Seeds <4 caracteres pueden producir falsos positivos masivos vía LIKE '%X%'.
        # Excepción: 'lms' y 'kvm' son siglas de dominio suficientemente únicas.
        allowed_short = {"lms", "kvm"}
        for seed in SOCRATA_LIKE_SEEDS:
            with self.subTest(seed=seed):
                if len(seed) < 4:
                    self.assertIn(seed, allowed_short, f"Seed '{seed}' es demasiado corta")

    def test_opensai_profile_uses_calibrated_high_fit_threshold(self):
        opensai_profile = MATCH_PROFILES["opensai"]
        self.assertEqual(opensai_profile["label"], "OpenSAI")
        self.assertEqual(opensai_profile["high_fit_threshold"], 60)
        self.assertGreater(len(opensai_profile["categories"]), 4)

    def test_profiles_declare_valid_scope(self):
        valid_scopes = {"all_it", "profile_only"}
        for name, profile in MATCH_PROFILES.items():
            with self.subTest(profile=name):
                scope = profile.get("scope", "all_it")
                self.assertIn(scope, valid_scopes)

    def test_generic_it_scope_keeps_full_it_universe(self):
        # generic_it = "Radar TI": el universo es todo IT (IT_KEYWORD_PATTERN)
        self.assertEqual(MATCH_PROFILES["generic_it"].get("scope", "all_it"), "all_it")
        raw_records = [
            self._raw_record("kvm-1", "Renovación licenciamiento antivirus ESET"),
            self._raw_record("kvm-2", "Servicios de ciberseguridad y monitoreo SIEM"),
            self._raw_record("kvm-3", "Mantenimiento Moodle institucional"),
        ]
        results = self.repository.map_raw_records(raw_records, profile="generic_it")
        self.assertEqual(len(results), 3)

    def test_opensai_scope_filters_to_profile_categories(self):
        # opensai = "OpenSAI": solo procesos cuyo objeto encaja en alguna categoría
        # del perfil. Procesos IT genéricos (antivirus, ciberseguridad) sin patrones
        # OpenSAI son excluidos.
        self.assertEqual(MATCH_PROFILES["opensai"].get("scope"), "profile_only")
        in_scope = self._raw_record("op-1", "Administración de campus virtual Moodle")
        out_of_scope = self._raw_record(
            "op-2", "Renovación licenciamiento antivirus ESET para entidad pública"
        )
        results = self.repository.map_raw_records([in_scope, out_of_scope], profile="opensai")
        names = [tender.name for tender in results]
        self.assertIn("Administración de campus virtual Moodle", names)
        self.assertNotIn(
            "Renovación licenciamiento antivirus ESET para entidad pública", names
        )

    def _raw_record(self, ident: str, text: str) -> dict:
        return {
            "id_del_proceso": ident,
            "referencia_del_proceso": ident,
            "nombre_del_procedimiento": text,
            "descripci_n_del_procedimiento": f"Description for {text}",
            "precio_base": "100000000",
            "fecha_de_publicacion_del": "2026-04-01T00:00:00.000",
            "fecha_de_recepcion_de": "2026-12-31T00:00:00.000",
            "entidad": "Test Entity",
            "urlproceso": {"url": "http://test.com"},
            "estado_de_apertura_del_proceso": "Abierto",
            "estado_del_procedimiento": "Publicado",
            "fase": "Presentación de oferta",
            "departamento_entidad": "Distrito Capital de Bogotá",
        }

    def test_word_boundary_security(self):
        self.assertFalse(IT_KEYWORD_PATTERN.search("Industria"))
        self.assertFalse(IT_KEYWORD_PATTERN.search("Asmático"))
        self.assertTrue(IT_KEYWORD_PATTERN.search("Software-less"))
        self.assertTrue(IT_KEYWORD_PATTERN.search("Seguridad informática"))


if __name__ == "__main__":
    unittest.main()
