from typing import Optional

DEFAULT_DEPARTMENT = "Todos"
ALLOWED_DEPARTMENTS = (
    DEFAULT_DEPARTMENT,
    "Distrito Capital de Bogotá",
    "Antioquia",
    "Valle del Cauca",
    "Atlantico",
    "Santander",
    "Cundinamarca",
)


def normalize_department(department: Optional[str]) -> str:
    """Validates and normalizes the department filter accepted by the UI."""
    if department is None:
        return DEFAULT_DEPARTMENT

    normalized = department.strip()
    if not normalized or normalized == DEFAULT_DEPARTMENT:
        return DEFAULT_DEPARTMENT

    if normalized not in ALLOWED_DEPARTMENTS:
        raise ValueError("Unsupported department filter")

    return normalized
