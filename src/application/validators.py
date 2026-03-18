from typing import Optional

ALLOWED_DEPARTMENTS = (
    "Todos",
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
        return "Todos"

    normalized = department.strip()
    if not normalized or normalized == "Todos":
        return "Todos"

    if normalized not in ALLOWED_DEPARTMENTS:
        raise ValueError("Unsupported department filter")

    return normalized
