"""Shared interpretation of academic labels without changing stored records."""
import re


def normalize_grade_name(value: str) -> str:
    return re.sub(r"^grade\s*", "", str(value).strip(), flags=re.IGNORECASE).strip()


def grade_name_aliases(value: str) -> list[str]:
    name = normalize_grade_name(value).lower()
    return [name, f"grade {name}", f"grade{name}"]


def is_senior_high(value: str) -> bool:
    return normalize_grade_name(value) in {"11", "12"}


def is_junior_high(value: str) -> bool:
    return normalize_grade_name(value) in {"7", "8", "9", "10"}


def elective_track_for_subject(category: str, is_elective: bool, elective_track: str | None) -> str | None:
    if not is_elective:
        return None
    if (category or "JHS").strip().upper().startswith("SHS"):
        return (elective_track or "").strip() or None
    return "STE"


def subject_policy_category(name: str, category: str = "JHS") -> str:
    category = (category or "JHS").strip()
    if category.upper().startswith("SHS"):
        return category if category.upper() != "SHS" else "SHS-Core"
    if category.upper() != "JHS":
        return category
    name = name.strip().upper()
    if name in {'GMRC', 'VALUES EDUCATION', 'EDUKASYON SA PAGPAPAKATAO', 'ESP'}:
        return 'GMRC/Values'
    if name in {"MATHEMATICS", "MATH", "SCIENCE"}:
        return "Math/Science"
    if name.startswith("MAPEH") or name in {"MUSIC", "ARTS", "PE", "P.E.", "PHYSICAL EDUCATION", "HEALTH", "MUSIC AND ARTS", "MUSIC & ARTS", "PHYSICAL EDUCATION AND HEALTH", "PHYSICAL EDUCATION & HEALTH", "PE AND HEALTH", "PE & HEALTH", "SPA", "SPS", "SPECIAL PROGRAM IN THE ARTS", "SPECIAL PROGRAM IN SPORTS"}:
        return "MAPEH/TLE"
    return "Languages/AP/EsP"
