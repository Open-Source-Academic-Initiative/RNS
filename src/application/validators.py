from typing import Optional

DEFAULT_DEPARTMENT = "Todos"
DEFAULT_PROCESS_STATUS = "Todos"
DEPARTMENT_ALIASES = {
    "Atlantico": "Atlántico",
}
ALLOWED_DEPARTMENTS = (
    DEFAULT_DEPARTMENT,
    "Distrito Capital de Bogotá",
    "Antioquia",
    "Valle del Cauca",
    "Atlántico",
    "Santander",
    "Cundinamarca",
)
ALLOWED_PROCESS_STATUSES = (
    DEFAULT_PROCESS_STATUS,
    "Borrador",
    "Publicado",
)


def normalize_department(department: Optional[str]) -> str:
    """Validates and normalizes the department filter accepted by the UI."""
    if department is None:
        return DEFAULT_DEPARTMENT

    normalized = department.strip()
    normalized = DEPARTMENT_ALIASES.get(normalized, normalized)
    if not normalized or normalized == DEFAULT_DEPARTMENT:
        return DEFAULT_DEPARTMENT

    if normalized not in ALLOWED_DEPARTMENTS:
        raise ValueError("Unsupported department filter")

    return normalized


def normalize_process_status(process_status: Optional[str]) -> str:
    """Validates and normalizes the SECOP procedural status filter accepted by the UI."""
    if process_status is None:
        return DEFAULT_PROCESS_STATUS

    normalized = process_status.strip()
    if not normalized or normalized == DEFAULT_PROCESS_STATUS:
        return DEFAULT_PROCESS_STATUS

    if normalized not in ALLOWED_PROCESS_STATUSES:
        raise ValueError("Unsupported process status filter")

    return normalized
