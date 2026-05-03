import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

LEXEME_MATRIX_PATH = Path(__file__).with_name("lexemes.yaml")
PROFILE_MATRIX_PATH = Path(__file__).with_name("profiles.yaml")


def _compile_word_pattern(fragments: List[str]) -> re.Pattern:
    if not fragments:
        raise RuntimeError("Pattern fragments are empty")
    return re.compile(r"\b(?:" + "|".join(fragments) + r")\b", re.IGNORECASE)


def _compile_free_pattern(fragments: List[str]) -> re.Pattern:
    if not fragments:
        raise RuntimeError("Pattern fragments are empty")
    return re.compile(r"(?:" + "|".join(fragments) + r")", re.IGNORECASE)


def _load_lexeme_matrix() -> Tuple[re.Pattern, re.Pattern, List[str]]:
    """Loads the IT lexeme matrix, exclusions and Socrata seeds."""
    with LEXEME_MATRIX_PATH.open(encoding="utf-8") as stream:
        matrix = yaml.safe_load(stream) or {}

    categories = matrix.get("categories") or {}
    fragments: List[str] = []
    for group in categories.values():
        fragments.extend(group or [])

    negative_fragments = list(matrix.get("negative_exclusions") or [])
    seeds = list(matrix.get("socrata_like_seeds") or [])

    if not fragments:
        raise RuntimeError("IT lexeme matrix is empty — check lexemes.yaml")
    if not negative_fragments:
        raise RuntimeError("Negative exclusion matrix is empty — check lexemes.yaml")

    return (
        _compile_word_pattern(fragments),
        _compile_free_pattern(negative_fragments),
        seeds,
    )


def _load_match_profiles() -> Dict[str, Dict[str, Any]]:
    """Loads scoring profiles from YAML."""
    with PROFILE_MATRIX_PATH.open(encoding="utf-8") as stream:
        payload = yaml.safe_load(stream) or {}

    profiles = payload.get("profiles") or {}
    if not profiles:
        raise RuntimeError("Match profile catalog is empty — check profiles.yaml")

    for profile_name, profile in profiles.items():
        for bucket_name in ("categories", "entity_bonuses", "risk_penalties"):
            for rule in profile.get(bucket_name, []) or []:
                fragments = list(rule.get("patterns") or [])
                rule["compiled_patterns"] = _compile_free_pattern(fragments) if fragments else None
        profile["name"] = profile_name
    return profiles


IT_KEYWORD_PATTERN, GENERIC_NEGATIVE_PATTERN, SOCRATA_LIKE_SEEDS = _load_lexeme_matrix()
MATCH_PROFILES = _load_match_profiles()
