import re
from typing import Optional

DEFAULT_DEPARTMENT = "Todos"
DEFAULT_PROCESS_STATUS = "Todos"
DEFAULT_PHASE = "Todos"
DEFAULT_PROFILE = "opensai"
PRESENTATION_OFFER_PHASE = "Presentación de oferta"

DEPARTMENT_ALIASES = {
    "Atlantico": "Atlántico",
    "Bogota": "Distrito Capital de Bogotá",
    "Bogotá": "Distrito Capital de Bogotá",
}
PHASE_ALIASES = {
    "Presentacion de oferta": PRESENTATION_OFFER_PHASE,
    "Manifestacion de interes (Menor Cuantia)": "Manifestación de interés (Menor Cuantía)",
    "Presentación de Observaciones": "Presentación de observaciones",
}
PROCESS_STATUS_ALIASES = {
    "Abierto": DEFAULT_PROCESS_STATUS,
}
ALLOWED_PROCESS_STATUSES = (
    DEFAULT_PROCESS_STATUS,
    "Borrador",
    "Publicado",
)
ALLOWED_PHASES = (
    DEFAULT_PHASE,
    PRESENTATION_OFFER_PHASE,
    "Fase de ofertas",
    "Presentación de observaciones",
    "Manifestación de interés (Menor Cuantía)",
    "Fase de Selección (Presentación de ofertas)",
    "Clarification submission",
    "Estimate Phase",
    "Pré-Calificación de competidores",
    "Proceso de ofertas",
    "Selección de ofertas (borrador)",
    "Fase de Concurso",
    "Presentación de observaciones (precalificación)",
    "Presentación de oferta (precalificación)",
)
ALLOWED_PROFILES = (
    "generic_it",
    "opensai",
)
SAFE_FILTER_PATTERN = re.compile(r"^[0-9A-Za-zÀ-ÿ .,:;()/_+\-&]+$")


def _normalize_free_text(value: Optional[str], default: str, aliases: dict[str, str]) -> str:
    if value is None:
        return default

    normalized = value.strip()
    normalized = aliases.get(normalized, normalized)
    if not normalized or normalized == default:
        return default

    if not SAFE_FILTER_PATTERN.fullmatch(normalized):
        raise ValueError("Unsafe filter value")

    return normalized


def normalize_department(department: Optional[str]) -> str:
    """Validates and normalizes the department filter accepted by the UI/API."""
    return _normalize_free_text(department, DEFAULT_DEPARTMENT, DEPARTMENT_ALIASES)


def normalize_process_status(process_status: Optional[str]) -> str:
    """Validates and normalizes the SECOP procedural status filter."""
    normalized = _normalize_free_text(process_status, DEFAULT_PROCESS_STATUS, PROCESS_STATUS_ALIASES)
    if normalized == DEFAULT_PROCESS_STATUS:
        return normalized
    if normalized not in ALLOWED_PROCESS_STATUSES:
        raise ValueError("Unsupported process status filter")
    return normalized


def normalize_phase(phase: Optional[str]) -> str:
    """Validates and normalizes the SECOP phase filter."""
    normalized = _normalize_free_text(phase, DEFAULT_PHASE, PHASE_ALIASES)
    if normalized == DEFAULT_PHASE:
        return normalized
    if normalized not in ALLOWED_PHASES:
        raise ValueError("Unsupported phase filter")
    return normalized


def normalize_profile(profile: Optional[str]) -> str:
    """Validates and normalizes the matching profile."""
    if profile is None:
        return DEFAULT_PROFILE
    normalized = profile.strip().lower()
    if not normalized:
        return DEFAULT_PROFILE
    if normalized not in ALLOWED_PROFILES:
        raise ValueError("Unsupported profile filter")
    return normalized
