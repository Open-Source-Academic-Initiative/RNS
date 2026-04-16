import re
from pathlib import Path
from typing import List, Tuple

import yaml

LEXEME_MATRIX_PATH = Path(__file__).with_name("lexemes.yaml")


def _load_lexeme_matrix() -> Tuple[re.Pattern, List[str]]:
    """Loads the IT lexeme matrix and Socrata seeds from the YAML catalog."""
    with LEXEME_MATRIX_PATH.open(encoding="utf-8") as stream:
        matrix = yaml.safe_load(stream) or {}

    categories = matrix.get("categories") or {}
    fragments: List[str] = []
    for group in categories.values():
        fragments.extend(group or [])

    if not fragments:
        raise RuntimeError("IT lexeme matrix is empty — check lexemes.yaml")

    pattern = re.compile(r"\b(" + "|".join(fragments) + r")\b", re.IGNORECASE)
    seeds = list(matrix.get("socrata_seeds") or [])
    return pattern, seeds


IT_KEYWORD_PATTERN, SOCRATA_IT_SEEDS = _load_lexeme_matrix()
