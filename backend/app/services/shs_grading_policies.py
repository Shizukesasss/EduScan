"""DepEd Order No. 015, s. 2026 grading policies for the strengthened SHS curriculum."""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SchoolYear, Subject, User
from ..models_grading import GradingPolicy
from .academic_context import normalize_grade_name
from .grading_engine import reporting_method_for_school_year


POLICY_VERSION = "DO15-SHS-v1"
CORE = "SHS-Core-DO15"
ACADEMIC = "SHS-Academic-DO15"
ACADEMIC_PERFORMANCE = "SHS-Academic-Performance-DO15"
FIELD_EXPERIENCE = "SHS-Field-Experience-DO15"
RESEARCH_DESIGN = "SHS-Research-Design-DO15"
TECHPRO = "SHS-TechPro-DO15"
WORK_IMMERSION = "SHS-Work-Immersion-DO15"

_ACADEMIC_ASH = "arts, social sciences, and humanities"
_ACADEMIC_SPORTS = "sports, health, and wellness"
_ACADEMIC_FIELD = "field experience"
_ACADEMIC_PERFORMANCE_SUBJECTS = {
    re.sub(r"[^a-z0-9]+", "", name.casefold())
    for name in (
        "Art Criticism and Creative Markets",
        "Creative Industries - Applied and Traditional Arts",
        "Creative Industries - Dance",
        "Creative Industries - Literary Arts",
        "Creative Industries - Media Arts",
        "Creative Industries - Music",
        "Creative Industries - Theater Arts",
        "Creative Industries - Visual Arts",
        "Filipino Identity Through the Arts",
        "Leadership and Management in the Arts",
        "Performance Criticism and Creative Markets",
    )
}


def uses_strengthened_shs_grading(school_year: SchoolYear, grade_name: str) -> bool:
    """The local SSHS pilot uses the strengthened curriculum for both grades in 2026–2027."""
    try:
        start_year = school_year.starts_on.year
    except (AttributeError, TypeError):
        try:
            start_year = int(str(school_year).strip().split("-")[0])
        except (TypeError, ValueError):
            return False
    grade = normalize_grade_name(grade_name)
    return (start_year == 2026 and grade in {"11", "12"}) or start_year >= 2027


def policy_category_for_subject(subject: Subject) -> str:
    name = " ".join((subject.name or "").casefold().split())
    if "work immersion" in name:
        return WORK_IMMERSION
    if not subject.is_elective:
        return CORE

    track = (subject.elective_track or "").strip().casefold()
    cluster = (subject.elective_cluster or "").strip().casefold()
    if track == "technical professional (techpro) track".casefold():
        return TECHPRO
    if track != "academic track":
        raise ValueError(f"Cannot choose an SHS grading policy for elective '{subject.name}' without a supported track")

    if "creative production and presentation" in name:
        return FIELD_EXPERIENCE
    if cluster == _ACADEMIC_FIELD:
        return RESEARCH_DESIGN if "research" in name or "design and innovation" in name else FIELD_EXPERIENCE
    name_key = re.sub(r"[^a-z0-9]+", "", name)
    if cluster == _ACADEMIC_SPORTS or (
        cluster == _ACADEMIC_ASH
        and (name.startswith("arts ") or name_key in _ACADEMIC_PERFORMANCE_SUBJECTS)
    ):
        return ACADEMIC_PERFORMANCE
    return ACADEMIC


def _definitions(written: float, performance: float, exam: float = 0.0) -> list[dict]:
    components = [
        {"name": "Written Works", "component_type": "Written Work", "weight": written, "max_items": 5},
        {"name": "Performance Tasks", "component_type": "Performance Task", "weight": performance, "max_items": 3},
    ]
    if exam:
        components.append({
            "name": "Term Examinations",
            "component_type": "Term Examinations",
            "weight": exam,
            "max_items": 3,
            "description": "Within EX: ST1 30%, ST2 30%, and TE 40%.",
        })
    return components


_POLICY_SPECS = {
    CORE: ("SHS Core", "Core subjects: WW 20%, PT 50%, EX 30%.", _definitions(20, 50, 30)),
    ACADEMIC: ("SHS Academic Electives", "All other Academic electives: WW 20%, PT 50%, EX 30%.", _definitions(20, 50, 30)),
    ACADEMIC_PERFORMANCE: (
        "SHS Arts, Sports, Health and Wellness Electives",
        "Arts, Sports, Health and Wellness electives: WW 20%, PT 60%, EX 20%.",
        _definitions(20, 60, 20),
    ),
    FIELD_EXPERIENCE: (
        "SHS Field Experience",
        "Field Exposure, Arts Apprenticeship, Creative Production and Innovation: WW 15%, PT 70%, EX 15%.",
        _definitions(15, 70, 15),
    ),
    RESEARCH_DESIGN: (
        "SHS Research and Design Electives",
        "Research electives and Design and Innovation: WW 40%, PT 60%, no EX.",
        _definitions(40, 60),
    ),
    TECHPRO: ("SHS TechPro Electives", "TechPro electives: WW 15%, PT 65%, EX 20%.", _definitions(15, 65, 20)),
    WORK_IMMERSION: ("SHS Work Immersion", "Work Immersion: WW 20%, PT 80%, no EX.", _definitions(20, 80)),
}


def ensure_shs_grading_policies(db: Session, school_year: SchoolYear, grade_name: str, actor: User) -> dict[str, GradingPolicy]:
    """Create or return the versioned strengthened-SHS policies for this school year."""
    if not uses_strengthened_shs_grading(school_year, grade_name):
        return {}

    grade_levels = "11,12"
    reporting_method = reporting_method_for_school_year(school_year)
    transmutation_table = None
    if reporting_method == "adjusted_2026":
        from .class_record_export import template_table
        from .reports import TEMPLATES_DIR

        transmutation_table = template_table(
            TEMPLATES_DIR / "SUBJECT CLASS RECORDS" / "ENGLISH - Grade 7-10 Class Record.xlsx"
        )

    policies = {}
    for category, (label, description, components) in _POLICY_SPECS.items():
        policy = db.scalar(select(GradingPolicy).where(
            GradingPolicy.school_year == school_year.name,
            GradingPolicy.subject_category == category,
            GradingPolicy.version == POLICY_VERSION,
        ))
        definitions_json = json.dumps(components, sort_keys=True)
        table_json = json.dumps(transmutation_table) if transmutation_table else None
        if policy is None:
            policy = GradingPolicy(
                name=f"{school_year.name} — {label} (DO 015 s. 2026)",
                version=POLICY_VERSION,
                description=description,
                school_year=school_year.name,
                grade_levels=grade_levels,
                subject_category=category,
                reporting_method=reporting_method,
                component_definitions_json=definitions_json,
                transmutation_table_json=table_json,
                rounding_decimal_places=2,
                rounding_final_decimal_places=0,
                rounding_method="half_up",
                passing_grade=75,
                status="Active",
                effective_date=school_year.starts_on,
                created_by=actor.id,
                created_by_name=actor.full_name,
            )
            db.add(policy)
            db.flush()
        elif (
            (policy.grade_levels != grade_levels and not (school_year.starts_on.year == 2026 and policy.grade_levels == "11"))
            or policy.reporting_method != reporting_method
            or policy.component_definitions_json != definitions_json
            or policy.transmutation_table_json != table_json
            or policy.passing_grade != 75
        ):
            raise ValueError(f"Existing SHS grading policy '{category}' does not match DO 015 s. 2026")
        if policy.grade_levels != grade_levels:
            policy.grade_levels = grade_levels
            db.flush()
        policies[category] = policy
    return policies
