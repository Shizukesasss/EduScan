"""Fill the official strengthened-SHS ECR without rewriting its workbook."""
from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from fastapi import HTTPException

from .gradebook_validation import (
    collect_grade_calculation_issues,
    collect_school_detail_issues,
    create_validation_issue,
    raise_export_validation,
)
from sqlalchemy import select

from ..models import GradingPeriod, Subject
from ..models_grading import Gradebook, GradingPolicy
from .academic_context import normalize_grade_name
from .class_record_export import assessment_groups
from .grading import get_gradebook_full
from .grading_engine import apply_transmutation, normalize_component_weights, round_value
from .shs_grading_policies import (
    ACADEMIC,
    ACADEMIC_PERFORMANCE,
    CORE,
    FIELD_EXPERIENCE,
    RESEARCH_DESIGN,
    TECHPRO,
    WORK_IMMERSION,
    policy_category_for_subject,
)


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_CORE_COURSES = {
    "SHS-CORE-EC": ("EFFECTIVE COMMUNICATION / MABISANG KOMUNIKASYON", "Effective Communication"),
    "SHS-CORE-GM": ("GENERAL MATHEMATICS", "General Mathematics"),
    "SHS-CORE-GS": ("GENERAL SCIENCE", "General Science"),
    "SHS-CORE-LCS": ("LIFE AND CAREER SKILLS", "Life and Career Skills"),
    "SHS-CORE-PKLP": (
        "PAG-AARAL NG KASAYSAYAN AT LIPUNANG PILIPINO",
        "Pag-aaral ng Kasaysayan at Lipunang Pilipino",
    ),
}
_CODE_CLUSTER_PREFIXES = {
    "SHS-AC-ASH-T1-": ("Academic Track", "Arts, Social Sciences, and Humanities"),
    "SHS-AC-ASH-T2-": ("Academic Track", "Arts, Social Sciences, and Humanities"),
    "SHS-AC-BE-T1-": ("Academic Track", "Business and Entrepreneurship"),
    "SHS-AC-BE-T2-": ("Academic Track", "Business and Entrepreneurship"),
    "SHS-AC-STEM-T1-": ("Academic Track", "Science, Technology, Engineering, and Mathematics (STEM)"),
    "SHS-AC-SHW-T1-": ("Academic Track", "Sports, Health, and Wellness"),
    "SHS-AC-SHW-T2-": ("Academic Track", "Sports, Health, and Wellness"),
    "SHS-AC-FE-": ("Academic Track", "Field Experience"),
    "SHS-TP-AWHC-": ("Technical Professional (TechPro) Track", "Aesthetic, Wellness, and Human Care"),
    "SHS-TP-AFBI-": ("Technical Professional (TechPro) Track", "Agri-Fishery Business and Food Innovation"),
    "SHS-TP-ACE-": ("Technical Professional (TechPro) Track", "Artisanry and Creative Enterprise"),
    "SHS-TP-ASET-": ("Technical Professional (TechPro) Track", "Automotive and Small Engine Technologies"),
    "SHS-TP-CBT-": ("Technical Professional (TechPro) Track", "Construction and Building Technologies"),
    "SHS-TP-CADT-": ("Technical Professional (TechPro) Track", "Creative Arts and Design Technologies"),
    "SHS-TP-HT-": ("Technical Professional (TechPro) Track", "Hospitality and Tourism"),
    "SHS-TP-ICT-": ("Technical Professional (TechPro) Track", "ICT Support and Computer Programming Technologies"),
    "SHS-TP-IT-": ("Technical Professional (TechPro) Track", "Industrial Technologies"),
    "SHS-TP-MT-": ("Technical Professional (TechPro) Track", "Maritime"),
}
_WEIGHTS_BY_POLICY = {
    CORE: {"ww": 20, "pt": 50, "exam": 30},
    ACADEMIC: {"ww": 20, "pt": 50, "exam": 30},
    ACADEMIC_PERFORMANCE: {"ww": 20, "pt": 60, "exam": 20},
    FIELD_EXPERIENCE: {"ww": 15, "pt": 70, "exam": 15},
    RESEARCH_DESIGN: {"ww": 40, "pt": 60, "exam": 0},
    TECHPRO: {"ww": 15, "pt": 65, "exam": 20},
    WORK_IMMERSION: {"ww": 20, "pt": 80, "exam": 0},
}
_EXAM_PORTIONS = {"ST1": Decimal("30"), "ST2": Decimal("30"), "TE": Decimal("40")}
_CORE_CATEGORY = "SSHS - CORE"
_ACADEMIC_CATEGORY = "SSHS - ACADEMIC"
_TECHPRO_CATEGORY = "SSHS - TECH-PRO"
_SUPPORTED_SHS_TRACKS = {
    "Academic Track",
    "Technical Professional (TechPro) Track",
}


def _section_track_for_export(full: dict) -> str:
    track = str(full.get("gradebook", {}).get("section_track") or "").strip()
    if track not in _SUPPORTED_SHS_TRACKS:
        raise HTTPException(409, "The saved section does not have a supported SHS track.")
    return track


def collect_shs_export_header_issues(full: dict, region: str, division: str, school_id: str) -> list[dict]:
    gradebook = full.get("gradebook", {})
    issues = collect_school_detail_issues(region, division, school_id)
    track = str(gradebook.get("section_track") or "").strip()
    if track not in _SUPPORTED_SHS_TRACKS:
        issues.append(create_validation_issue(
            "SHS_TRACK_UNSUPPORTED",
            "shs_track_ecr",
            {"type": "section", "sectionName": gradebook.get("section_name") or "Selected section", "field": "SHS track"},
            f"Section {gradebook.get('section_name') or 'Selected section'} does not have a supported SHS track.",
            "Assign Academic Track or Technical Professional (TechPro) Track to the section.",
            ["export"],
        ))
    return issues


def _cell_value(cell: ET.Element, shared: list[str]) -> str | float | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t"))
    value = cell.find(f"{{{_MAIN_NS}}}v")
    if value is None or value.text is None:
        return None
    if cell_type == "s":
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError):
            return None
    if cell_type == "str":
        return value.text
    try:
        return float(value.text)
    except ValueError:
        return value.text


def _ecr_reference_data(template: Path) -> tuple[dict[tuple[str, str, str], list[dict]], list[dict]]:
    from .reports import _xlsx_sheet_paths

    if not template.is_file():
        raise HTTPException(409, f"The required SHS ECR template '{template.name}' is missing.")
    with ZipFile(template) as package:
        paths = _xlsx_sheet_paths(package)
        if "HELPER" not in paths:
            raise HTTPException(409, "The SHS ECR template is missing its helper catalog.")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in package.namelist():
            strings = ET.fromstring(package.read("xl/sharedStrings.xml"))
            shared = [
                "".join(text.text or "" for text in item.iter(f"{{{_MAIN_NS}}}t"))
                for item in strings.findall(f"{{{_MAIN_NS}}}si")
            ]
        helper = ET.fromstring(package.read(paths["HELPER"]))
        catalog: dict[tuple[str, str, str], list[dict]] = {}
        table: list[dict] = []
        for row in helper.iter(f"{{{_MAIN_NS}}}row"):
            row_number = int(row.get("r", "0"))
            if row_number < 7:
                continue
            values = {}
            for cell in row.findall(f"{{{_MAIN_NS}}}c"):
                match = re.match(r"([A-Z]+)", cell.get("r", ""))
                if match:
                    values[match.group(1)] = _cell_value(cell, shared)
            if 7 <= row_number <= 47:
                minimum, maximum, grade = values.get("B"), values.get("C"), values.get("D")
                if all(isinstance(value, (int, float)) for value in (minimum, maximum, grade)):
                    table.append({"min": float(minimum), "max": float(maximum), "value": int(grade)})
            course, track, cluster = values.get("L"), values.get("J"), values.get("K")
            if not isinstance(course, str) or not course.strip() or not isinstance(track, str) or not isinstance(cluster, str):
                continue
            allowed = _grade_levels(values.get("N"))
            key = (_normalize_text(track), _normalize_cluster(cluster), _normalize_course(course))
            weights = {
                group: float(values.get(column)) if isinstance(values.get(column), (int, float)) else 0.0
                for group, column in (("ww", "W"), ("pt", "X"), ("exam", "Y"))
            }
            exam_split = {
                label: float(values.get(column)) if isinstance(values.get(column), (int, float)) else 0.0
                for label, column in (("ST1", "AA"), ("ST2", "AB"), ("TE", "AC"))
            }
            term_counts = {
                11: int(values["P"]) if isinstance(values.get("P"), (int, float)) else 0,
                12: int(values["T"]) if isinstance(values.get("T"), (int, float)) else 0,
            }
            catalog.setdefault(key, []).append({
                "track": track.strip(), "cluster": cluster.strip(),
                "course": course.strip(), "grades": allowed, "weights": weights,
                "exam_split": exam_split, "term_counts": term_counts,
                "helper_row": row_number,
                "grade11_helper": {
                    column: values.get(column) for column in ("N", "P", "Q", "R")
                },
            })
    if not catalog or len(table) != 41:
        raise HTTPException(409, "The SHS ECR helper catalog or grading table is incomplete.")
    return catalog, table


def _grade_levels(value: object) -> set[int]:
    text = str(value or "").strip().casefold()
    if not text:
        return {11, 12}
    found = {int(level) for level in re.findall(r"\b(11|12)\b", text)}
    return found or {12} if "12" in text else found or {11, 12}


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _normalize_cluster(value: object) -> str:
    normalized = _normalize_text(value)
    return normalized[:-4] if normalized.endswith("stem") else normalized


def _normalize_course(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s*\(?\s*updated\s+as\s+of\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*[-–—]?\s*NC\s*(?:I{1,3}|IV|V)\s*$", "", text, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-z0-9]+", "", text.casefold())
    aliases = {
        "fishcapture": "fishcaptureoperation",
        "hoteloperationfrontofficeservices": "hoteloperationsfrontofficeservices",
        "hoteloperationhousekeepingservices": "hoteloperationshousekeepingservices",
        "automotiveservicingengineandchassisrepair": "automotiveservicingengineandchassisrepairs",
        "filipino2filinoparasalarangteknikalpropesyonal": "filipino2filipinosalarangteknikalpropesyonal",
        "filipino2filinoparasaisports": "filipino2filipinosaIsports".casefold(),
        "introductiontophilosophy": "introductiontothephilosophyofthehumanperson",
    }
    return aliases.get(normalized, normalized)


def _grade12_core_helper_changes(match: dict) -> dict[str, object]:
    helper = match.get("grade11_helper") or {}
    try:
        row = int(match["helper_row"])
        term_count = int(helper["P"])
        units_per_term = int(helper["Q"])
        units_per_year = int(helper["R"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(409, "The Grade 11 core ECR row is missing the helper schedule needed for Grade 12 reuse.")
    if term_count not in (1, 2, 3) or units_per_term <= 0 or units_per_year <= 0:
        raise HTTPException(409, "The Grade 11 core ECR row has an invalid schedule for Grade 12 reuse.")
    grade_label = str(helper.get("N") or "11").strip()
    if "12" not in _grade_levels(grade_label):
        grade_label = f"{grade_label} 12".strip()
    return {
        f"N{row}": grade_label,
        f"S{row}": 12,
        f"T{row}": term_count,
        f"U{row}": units_per_term,
        f"V{row}": units_per_year,
    }


def _course_selection(subject: Subject, grade_name: str, catalog: dict) -> tuple[str, str, str, dict[str, float], dict[str, float], int, str, dict[str, object]]:
    code = (subject.code or "").strip().upper()
    if not code:
        raise HTTPException(409, "This SHS subject has no stable code, so it cannot be mapped to the official ECR.")

    subject_name = (subject.name or "").strip()
    if "work immersion" in subject_name.casefold():
        track_name = (subject.elective_track or "").strip()
        if "academic" in subject_name.casefold():
            track_name = "Academic Track"
        elif "tech-pro" in subject_name.casefold() or "techpro" in subject_name.casefold():
            track_name = "Technical Professional (TechPro) Track"
        if track_name == "Academic Track":
            category, cluster = _ACADEMIC_CATEGORY, "FIELD EXPERIENCE"
        elif track_name == "Technical Professional (TechPro) Track":
            category, cluster = _TECHPRO_CATEGORY, "WORK IMMERSION"
        else:
            raise HTTPException(409, f"Work Immersion subject code '{code}' does not identify its SHS track.")
        course = subject_name
    elif not subject.is_elective:
        core = _CORE_COURSES.get(code)
        if core is None:
            raise HTTPException(409, f"SHS core subject code '{code}' is not in the approved ECR mapping.")
        expected_name, course = core
        if _normalize_course(subject.name) not in {_normalize_course(expected_name), _normalize_course(course)}:
            raise HTTPException(409, f"SHS core subject code '{code}' does not match its saved subject name.")
        category, cluster = _CORE_CATEGORY, "CORE"
    else:
        track = (subject.elective_track or "").strip()
        cluster = (subject.elective_cluster or "").strip()
        if track == "Academic Track":
            category = _ACADEMIC_CATEGORY
        elif track == "Technical Professional (TechPro) Track":
            category = _TECHPRO_CATEGORY
        else:
            raise HTTPException(409, f"SHS subject '{subject.name}' has no supported ECR track.")
        for prefix, expected in _CODE_CLUSTER_PREFIXES.items():
            if code.startswith(prefix) and (track, cluster) != expected:
                raise HTTPException(409, f"SHS subject code '{code}' conflicts with its saved track or cluster.")
        course = subject_name

    key = (_normalize_text(category), _normalize_cluster(cluster), _normalize_course(course))
    matches = catalog.get(key, [])
    if len(matches) != 1:
        raise HTTPException(
            409,
            f"Subject code '{code}' ({subject.name}) does not map to exactly one course in the official ECR for {cluster}.",
        )
    grade = int(normalize_grade_name(grade_name))
    match = matches[0]
    grade12_core_reuse = grade == 12 and not subject.is_elective and grade not in match["grades"] and 11 in match["grades"]
    if grade not in match["grades"] and not grade12_core_reuse:
        raise HTTPException(409, f"The official ECR does not list '{subject.name}' for Grade {grade}.")
    term_count = match["term_counts"][11] if grade12_core_reuse else match["term_counts"][grade]
    if term_count not in (1, 2, 3):
        raise HTTPException(409, f"The official ECR has no term schedule for '{subject.name}' in Grade {grade}.")
    helper_changes = _grade12_core_helper_changes(match) if grade12_core_reuse else {}
    return match["track"], match["cluster"], match["course"], match["weights"], match["exam_split"], term_count, code, helper_changes


def _normalize_policy_table(rows: list[dict] | None) -> list[tuple[float, float, int]]:
    return sorted(
        [(round(float(row["min"]), 2), round(float(row["max"]), 2), int(row["value"])) for row in (rows or [])],
        key=lambda row: row[0],
    )


def _policy_group(book: Gradebook, db) -> str:
    policy = db.get(GradingPolicy, book.grading_policy_id) if book.grading_policy_id else None
    try:
        expected = policy_category_for_subject(book.subject)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if policy is None or policy.subject_category != expected or policy.school_year != book.school_year_name:
        actual = policy.subject_category if policy else "none"
        raise HTTPException(409, f"Saved gradebook policy '{actual}' for this year does not match this subject's SHS policy '{expected}'.")
    return expected


def _assessment_layout(full: dict, expected_policy: str, ecr_exam_split: dict[str, float]) -> tuple[dict, dict[str, list[dict]]]:
    expected_weights = _WEIGHTS_BY_POLICY.get(expected_policy)
    if expected_weights is None:
        raise HTTPException(409, f"No ECR grading group is defined for '{expected_policy}'.")
    try:
        groups = assessment_groups(full, "shs")
    except HTTPException as exc:
        raise HTTPException(409, f"The ECR cannot represent this assessment setup: {exc.detail}") from exc
    if set(groups) != {key for key, weight in expected_weights.items() if weight > 0}:
        raise HTTPException(409, "The saved assessment groups do not match the ECR grading group.")
    items_by_group = {}
    normalized_weights = {
        component["id"]: float(component["weight"])
        for component in normalize_component_weights(full["components"])
    }
    for group_name, component in groups.items():
        weight = normalized_weights[component["id"]]
        if not math.isclose(weight, expected_weights[group_name], abs_tol=0.001):
            raise HTTPException(409, f"The ECR requires {expected_weights[group_name]}% for {group_name.upper()}, but this class record uses {weight}%.")
        items = [item for item in component["items"] if item.get("active")]
        capacity = 3 if group_name == "exam" else 10
        if not 1 <= len(items) <= capacity:
            raise HTTPException(409, f"The ECR supports 1–{capacity} active {group_name.upper()} assessments.")
        if group_name == "exam":
            if any(not math.isclose(ecr_exam_split.get(label, 0), float(portion), abs_tol=0.001)
                   for label, portion in _EXAM_PORTIONS.items()):
                raise HTTPException(409, "The selected ECR course uses a different ST1/ST2/TE split from the saved gradebook.")
            exam_items = {}
            for item in items:
                label = re.sub(r"[^A-Z0-9]", "", str(item.get("label", "")).upper())
                key = {"SUMMATIVETEST1": "ST1", "SUMMATIVETEST2": "ST2", "TERMEXAM": "TE", "TERMEXAMINATION": "TE"}.get(label, label)
                if key not in _EXAM_PORTIONS or key in exam_items:
                    raise HTTPException(409, "The ECR requires exactly one examination labelled ST1, ST2, and TE.")
                exam_items[key] = item
            if set(exam_items) != set(_EXAM_PORTIONS):
                raise HTTPException(409, "The ECR requires exactly three examinations labelled ST1, ST2, and TE.")
            items = [exam_items[label] for label in ("ST1", "ST2", "TE")]
        items_by_group[group_name] = items
    if not math.isclose(sum(expected_weights.values()), 100, abs_tol=0.001):
        raise HTTPException(409, "The ECR grading group weights do not total 100%.")
    return expected_weights, items_by_group


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _validate_template_grade_match(
    saved_initial: float | None,
    saved_reported: int | None,
    template_initial: float,
    template_reported: int,
    *,
    draft_preview: bool,
) -> bool:
    if saved_initial is None:
        raise HTTPException(409, "The saved class record is missing an initial grade.")
    initial_difference = abs(float(saved_initial) - float(template_initial))
    has_rounding_difference = not math.isclose(float(saved_initial), float(template_initial), abs_tol=0.001)
    # The ECR rounds intermediate components to two decimals, so its initial
    # grade can differ from EduScan's by 0.01 even when the reported grade agrees.
    if has_rounding_difference and initial_difference > 0.0100001:
        raise HTTPException(409, "The ECR initial grade differs from the saved grade by more than the allowed 0.01 rounding variance.")
    if saved_reported is None or int(saved_reported) != int(template_reported):
        raise HTTPException(409, "The ECR calculation differs from a saved reported grade.")
    return has_rounding_difference


def _student_template_grades(
    full: dict,
    weights: dict,
    items_by_group: dict,
    ecr_table: list[dict],
    *,
    draft_preview: bool = False,
) -> tuple[dict[int, tuple[float, int, dict, bool]], list[dict]]:
    output = {}
    issues = []
    policy = full["policy"]
    table = policy["transmutation_table"] or []
    if policy["rounding_method"] != "half_up" or policy["rounding_decimal_places"] != 2:
        issues.append(create_validation_issue(
            "ECR_ROUNDING_POLICY_MISMATCH", "shs_track_ecr",
            {"type": "setting", "field": "Rounding policy"},
            "The ECR requires half-up rounding to two decimal places.",
            "Select the approved SHS policy with half-up rounding to two decimal places.", ["export"],
        ))
    if policy["rounding_final_decimal_places"] != 0 or full["gradebook"]["passing_grade"] != 75:
        issues.append(create_validation_issue(
            "ECR_REPORTING_POLICY_MISMATCH", "shs_track_ecr",
            {"type": "setting", "field": "Reported grade policy"},
            "The ECR reports whole-number grades and uses 75 as the passing mark.",
            "Set the SHS reporting policy to whole-number grades with a passing mark of 75.", ["export"],
        ))
    if policy["reporting_method"] != "adjusted_2026" or _normalize_policy_table(table) != _normalize_policy_table(ecr_table):
        issues.append(create_validation_issue(
            "ECR_TRANSMUTATION_POLICY_MISMATCH", "shs_track_ecr",
            {"type": "setting", "field": "Grade conversion policy"},
            "The saved grade conversion policy differs from the official 2026–2027 SHS ECR.",
            "Select the approved 2026–2027 SHS grade conversion policy.", ["export"],
        ))
    for student in full["students"]:
        weighted_parts = {}
        group_scores = {}
        student_issues = []
        for group_name, items in items_by_group.items():
            scores = []
            for item in items:
                score = student["scores"].get(str(item["id"]))
                if score is None:
                    status = student.get("score_statuses", {}).get(str(item["id"])) or "Missing"
                    maximum = item["max_score"]
                    student_issues.append(create_validation_issue(
                        "SCORE_MISSING", "scores",
                        {"type": "learner_activity", "learnerId": student["person_id"],
                         "learnerName": student["full_name"], "activityName": item["label"]},
                        f"{item['label']} is {str(status).lower()} for this learner.",
                        f"Enter a score from 0 to {maximum} for {item['label']}.", ["finalization", "export"],
                        details={"status": status, "maxScore": maximum},
                    ))
                    continue
                try:
                    score_decimal, max_score = _decimal(score), _decimal(item["max_score"])
                except (InvalidOperation, TypeError, ValueError):
                    score_decimal, max_score = None, None
                if score_decimal is None or max_score is None or max_score <= 0 or score_decimal < 0 or score_decimal > max_score:
                    student_issues.append(create_validation_issue(
                        "SCORE_INVALID", "scores",
                        {"type": "learner_activity", "learnerId": student["person_id"],
                         "learnerName": student["full_name"], "activityName": item["label"]},
                        f"{item['label']} is outside its allowed score range.",
                        f"Enter a score from 0 to {item['max_score']} for {item['label']}.", ["finalization", "export"],
                        details={"maxScore": item["max_score"], "score": score},
                    ))
                    continue
                scores.append((item, score_decimal, max_score))
            if len(scores) != len(items):
                continue
            if group_name == "exam":
                components = []
                for (item, score, max_score), label in zip(scores, ("ST1", "ST2", "TE")):
                    portion = _EXAM_PORTIONS[label]
                    portion_score = round_value(float(score / max_score * portion), 2, "half_up")
                    components.append((portion_score, portion))
                percentage = sum((_decimal(value) for value, _ in components), Decimal("0"))
                weighted = round_value(float(percentage * _decimal(weights[group_name]) / 100), 2, "half_up")
                group_scores[group_name] = {"exam_portions": components, "percentage": percentage, "weighted": weighted}
            else:
                earned = sum((score for _, score, _ in scores), Decimal("0"))
                possible = sum((maximum for _, _, maximum in scores), Decimal("0"))
                percentage = _decimal(round_value(float(earned / possible * 100), 2, "half_up"))
                weighted = round_value(float(percentage * _decimal(weights[group_name]) / 100), 2, "half_up")
                group_scores[group_name] = {"scores": scores, "percentage": percentage, "weighted": weighted}
            weighted_parts[group_name] = _decimal(weighted)
        if student_issues:
            issues.extend(student_issues)
            continue
        initial = round_value(float(sum(weighted_parts.values(), Decimal("0"))), 2, "half_up")
        reported = apply_transmutation(initial, ecr_table, use_lower_bounds=True)
        if reported is None:
            issues.append(create_validation_issue(
                "ECR_GRADE_CONVERSION_FAILED", "grade_calculation",
                {"type": "learner", "learnerId": student["person_id"], "learnerName": student["full_name"]},
                f"The ECR could not convert {student['full_name']}'s calculated initial grade.",
                "Review the saved scores and confirm they produce an initial grade in the official ECR table.", ["export"],
                details={"templateInitial": initial},
            ))
            continue
        grade_issues = collect_grade_calculation_issues(
            [student], {student["person_id"]: {"initial": initial, "reported": reported}}, template_name="ECR",
        )
        issues.extend(grade_issues)
        has_rounding_difference = student.get("initial_grade") is not None and not math.isclose(
            float(student["initial_grade"]), float(initial), abs_tol=0.001,
        )
        output[student["person_id"]] = (initial, reported, group_scores, has_rounding_difference)
    return output, issues


def _term_changes(full: dict, items_by_group: dict, grade_cache: dict, males: list[dict], females: list[dict]) -> tuple[dict[str, object], dict[str, object]]:
    from .reports import _column_name

    changes: dict[str, object] = {}
    formula_values: dict[str, object] = {}
    max_columns = {"ww": 4, "pt": 17, "exam": 30}
    for group_name, items in items_by_group.items():
        start = max_columns[group_name]
        for offset, item in enumerate(items):
            column = _column_name(start + offset)
            changes[f"{column}14"] = float(item["max_score"])
    student_rows = {student["person_id"]: student for student in full["students"]}
    for roster, first_row in ((males, 17), (females, 68)):
        for offset, person in enumerate(roster):
            row = first_row + offset
            student = student_rows.get(person["person_id"])
            if student is None:
                raise HTTPException(409, "The requested terms do not have the same learner roster.")
            for group_name, items in items_by_group.items():
                start = max_columns[group_name]
                scores = [student["scores"].get(str(item["id"])) for item in items]
                for item_offset, (item, score) in enumerate(zip(items, scores)):
                    column = _column_name(start + item_offset)
                    changes[f"{column}{row}"] = float(score)
                group = grade_cache[person["person_id"]][2][group_name]
                if group_name == "ww":
                    total_col, ps_col, ws_col = "N", "O", "P"
                elif group_name == "pt":
                    total_col, ps_col, ws_col = "AA", "AB", "AC"
                else:
                    portions = group["exam_portions"]
                    for exam_index, column in enumerate(("AG", "AH", "AI")):
                        formula_values[f"{column}{row}"] = portions[exam_index][0]
                    formula_values[f"AJ{row}"] = float(group["percentage"])
                    formula_values[f"AK{row}"] = group["weighted"]
                    continue
                total = sum((score for score in scores), 0)
                formula_values[f"{total_col}{row}"] = total
                formula_values[f"{ps_col}{row}"] = float(group["percentage"])
                formula_values[f"{ws_col}{row}"] = group["weighted"]
            formula_values[f"AL{row}"] = grade_cache[person["person_id"]][0]
            formula_values[f"AM{row}"] = grade_cache[person["person_id"]][1]
    for group_name, items in items_by_group.items():
        if group_name == "ww":
            formula_values["N14"] = sum((float(item["max_score"]) for item in items), 0.0)
        elif group_name == "pt":
            formula_values["AA14"] = sum((float(item["max_score"]) for item in items), 0.0)
    return changes, formula_values


def _export_rule_issue(full: dict, detail: str) -> dict:
    text = str(detail or "The saved record does not match the official ECR requirements.")
    normalized = text.casefold()
    if "score" in normalized:
        group = "scores"
        correction = "Enter a valid score within the activity's highest possible score."
    elif "weight" in normalized or "assessment" in normalized or "component" in normalized or "exam" in normalized:
        group = "assessment_setup"
        correction = "Adjust the assessment setup to match the official ECR component groups and weights."
    elif any(term in normalized for term in ("grade", "transmutation", "rounding", "policy")):
        group = "shs_track_ecr" if "policy" in normalized or "rounding" in normalized else "grade_calculation"
        correction = "Review the saved grading policy and source scores against the official ECR requirements."
    else:
        group = "shs_track_ecr"
        correction = "Check the saved SHS subject, track, cluster, and term against the official ECR catalog."
    gradebook = full.get("gradebook", {})
    return create_validation_issue(
        "SHS_ECR_REQUIREMENT_MISMATCH",
        group,
        {"type": "subject", "subjectName": gradebook.get("subject_name") or "Selected subject",
         "sectionName": gradebook.get("section_name"), "term": gradebook.get("term_order")},
        text,
        correction,
        ["export"],
    )


def validate_shs_ecr_export(
    db,
    book: Gradebook,
    full: dict,
    region: str,
    division: str,
    school_id: str,
    allowed_teacher_id: int | None = None,
    all_terms: bool = False,
    through_term: int | None = None,
    draft_preview: bool = False,
) -> list[dict]:
    from .reports import TEMPLATES_DIR

    if allowed_teacher_id is not None and book.teacher_user_id != allowed_teacher_id:
        raise HTTPException(403, "This saved class record belongs to another teacher.")

    gradebook = full.get("gradebook", {})
    issues = collect_shs_export_header_issues(full, region, division, school_id)
    if draft_preview and (all_terms or through_term):
        issues.append(create_validation_issue(
            "DRAFT_EXPORT_SCOPE_INVALID", "export_requirements",
            {"type": "setting", "field": "Export term"},
            "Draft previews can export only the selected term.",
            "Select the current term only for a Draft preview.", ["export"],
        ))
    if draft_preview and gradebook.get("status") != "Draft":
        issues.append(create_validation_issue(
            "DRAFT_PREVIEW_STATUS_INVALID", "export_requirements",
            {"type": "gradebook", "field": "Status", "value": gradebook.get("status")},
            "Draft preview is available only while the saved class record is Draft.",
            "Use the official export after finalizing the class record.", ["export"],
        ))
    if not draft_preview and gradebook.get("status") not in {"Finalized", "Locked"}:
        issues.append(create_validation_issue(
            "GRADEBOOK_NOT_FINALIZED", "export_requirements",
            {"type": "gradebook", "field": "Status", "value": gradebook.get("status") or "Draft"},
            "The class record must be finalized or locked before official export.",
            "Finalize or lock the complete class record before exporting.", ["export"],
        ))
    if not str(gradebook.get("teacher_name") or "").strip():
        issues.append(create_validation_issue(
            "GRADEBOOK_TEACHER_MISSING", "export_requirements",
            {"type": "setting", "field": "Assigned teacher"},
            "No teacher is assigned to this class record.",
            "Assign a teacher before exporting the official ECR.", ["export"],
        ))
    try:
        grade = int(normalize_grade_name(gradebook.get("grade_name")))
    except (TypeError, ValueError):
        grade = 0
    if grade not in (11, 12) or not is_supported_shs_ecr_school_year(gradebook.get("school_year_name")):
        issues.append(create_validation_issue(
            "SHS_ECR_GRADE_YEAR_UNSUPPORTED", "export_requirements",
            {"type": "gradebook", "grade": gradebook.get("grade_name"), "schoolYear": gradebook.get("school_year_name")},
            "The official SHS ECR export supports Grade 11–12 in SY 2026–2027.",
            "Select a Grade 11 or Grade 12 record from SY 2026–2027.", ["export"],
        ))
    try:
        term_order = int(gradebook.get("term_order"))
    except (TypeError, ValueError):
        term_order = 0
    if term_order not in (1, 2, 3) or through_term not in (None, 2) or (through_term and all_terms):
        issues.append(create_validation_issue(
            "SHS_ECR_TERM_SCOPE_INVALID", "export_requirements",
            {"type": "setting", "field": "Export term", "term": term_order},
            "Choose the current term, Terms 1–2 from Term 2, or all three terms.",
            "Choose a term scope supported by the current gradebook and ECR.", ["export"],
        ))
    elif through_term == 2 and term_order != 2:
        issues.append(create_validation_issue(
            "SHS_ECR_TERM_SCOPE_INVALID", "export_requirements",
            {"type": "setting", "field": "Export term", "term": term_order},
            "Terms 1–2 can be exported together only from a Term 2 class record.",
            "Open the Term 2 class record to export Terms 1–2 together.", ["export"],
        ))
    if not full.get("students"):
        issues.append(create_validation_issue(
            "NO_ACTIVE_LEARNERS", "export_requirements",
            {"type": "setting", "field": "Learners"},
            "This class record has no active learners.",
            "Add at least one active learner before exporting.", ["export"],
        ))
    template_selection_blockers = {
        "SHS_TRACK_UNSUPPORTED",
        "SHS_ECR_GRADE_YEAR_UNSUPPORTED",
        "SHS_ECR_TERM_SCOPE_INVALID",
        "NO_ACTIVE_LEARNERS",
    }
    if any(issue["code"] in template_selection_blockers for issue in issues):
        return issues

    template = TEMPLATES_DIR / "SUBJECT CLASS RECORDS" / "ECR_3Term - SSHS - SY2026-2027.xlsx"
    try:
        catalog, ecr_table = _ecr_reference_data(template)
        category, cluster, course, ecr_weights, ecr_exam_split, course_terms, _, _ = _course_selection(
            book.subject, gradebook["grade_name"], catalog,
        )
        if course_terms == 1 and (all_terms or through_term == 2):
            issues.append(create_validation_issue(
                "SHS_ECR_TERM_COUNT_MISMATCH", "shs_track_ecr",
                {"type": "subject", "subjectName": course, "term": term_order},
                f"The official ECR lists '{course}' for one term.",
                "Export only the selected term for this subject.", ["export"],
            ))
        if course_terms == 2 and all_terms:
            issues.append(create_validation_issue(
                "SHS_ECR_TERM_COUNT_MISMATCH", "shs_track_ecr",
                {"type": "subject", "subjectName": course, "term": term_order},
                f"The official ECR lists '{course}' for two terms.",
                "Export one term or Terms 1–2 for this subject.", ["export"],
            ))
        policy_key = _policy_group(book, db)
        weights, items_by_group = _assessment_layout(full, policy_key, ecr_exam_split)
        if any(not math.isclose(weights[key], ecr_weights[key], abs_tol=0.001) for key in weights):
            issues.append(create_validation_issue(
                "SHS_ECR_WEIGHT_MISMATCH", "shs_track_ecr",
                {"type": "setting", "field": "Grading policy", "subjectName": course},
                f"The saved '{policy_key}' policy weights do not match the official ECR weights for '{course}'.",
                "Assign the SHS grading policy with the weights listed for this ECR subject.", ["export"],
            ))
        if not math.isclose(sum(weights.values()), 100, abs_tol=0.001):
            issues.append(create_validation_issue(
                "ASSESSMENT_WEIGHTS_INVALID", "assessment_setup",
                {"type": "setting", "field": "Component weights"},
                "The saved grading weights do not total 100%.",
                "Adjust assessment component weights to total exactly 100%.", ["export"],
            ))
    except HTTPException as exc:
        return issues + [_export_rule_issue(full, exc.detail)]

    periods = tuple(range(1, (through_term or 3) + 1)) if all_terms or through_term else (term_order,)
    query = select(Gradebook).where(
        Gradebook.school_year_id == book.school_year_id,
        Gradebook.grade_level_id == book.grade_level_id,
        Gradebook.section_id == book.section_id,
        Gradebook.subject_id == book.subject_id,
        Gradebook.grading_period.has(GradingPeriod.deleted_at.is_(None)),
        Gradebook.subject.has(Subject.deleted_at.is_(None)),
        Gradebook.term_order.in_((1, 2, 3)),
        Gradebook.learning_area == "",
    )
    if allowed_teacher_id is not None or all_terms or through_term or course_terms == 2:
        query = query.where(Gradebook.teacher_user_id == book.teacher_user_id)
    siblings = {}
    for sibling in db.scalars(query.order_by(Gradebook.term_order)).all():
        if sibling.term_order in siblings:
            issues.append(create_validation_issue(
                "SHS_ECR_DUPLICATE_TERM_RECORD", "export_requirements",
                {"type": "gradebook", "term": sibling.term_order, "subjectName": gradebook.get("subject_name")},
                f"Multiple class records match this SHS subject for Term {sibling.term_order}.",
                "Resolve the duplicate subject assignment for this term before exporting.", ["export"],
            ))
        siblings[sibling.term_order] = sibling
    missing_periods = [period for period in periods if period not in siblings]
    if missing_periods:
        issues.append(create_validation_issue(
            "SHS_ECR_TERM_RECORD_MISSING", "export_requirements",
            {"type": "gradebook", "subjectName": gradebook.get("subject_name"), "terms": missing_periods},
            f"No saved class record was found for requested Term(s) {', '.join(map(str, missing_periods))}.",
            "Complete and finalize the requested term records for this section, subject, and teacher.", ["export"],
        ))
    term_record_blockers = {
        "SHS_ECR_TERM_RECORD_MISSING",
        "SHS_ECR_DUPLICATE_TERM_RECORD",
        "SHS_ECR_TERM_COUNT_MISMATCH",
    }
    if any(issue["code"] in term_record_blockers for issue in issues):
        return issues

    if course_terms == 2 and term_order == 2 and through_term is None:
        first_block = 1 in siblings
        second_block = 3 in siblings
        if first_block == second_block:
            return [create_validation_issue(
                "SHS_ECR_TERM_BLOCK_AMBIGUOUS", "shs_track_ecr",
                {"type": "subject", "subjectName": course, "term": term_order},
                f"The ECR lists '{course}' for two terms, but the saved records do not identify its term block.",
                "Keep only the matching adjacent term records for this subject, or select a supported term scope.", ["export"],
            )]

    current_roster = {student["person_id"] for student in full["students"]}
    for term_order in periods:
        sibling = siblings[term_order]
        term_full = full if sibling.id == book.id else get_gradebook_full(db, sibling.id)
        if not term_full:
            issues.append(create_validation_issue(
                "SHS_ECR_TERM_RECORD_MISSING", "export_requirements",
                {"type": "gradebook", "term": term_order, "subjectName": course},
                f"Term {term_order} has no readable class record.",
                "Reload or restore this term's class record before exporting multiple terms.", ["export"],
            ))
            continue
        if term_full["gradebook"].get("status") not in {"Finalized", "Locked"} and not (draft_preview and sibling.id == book.id):
            issues.append(create_validation_issue(
                "SHS_ECR_TERM_NOT_FINALIZED", "export_requirements",
                {"type": "gradebook", "term": term_order, "subjectName": course},
                f"Term {term_order} is not finalized with complete learner scores.",
                "Finalize every requested term before exporting them together.", ["export"],
            ))
        sibling_roster = {student["person_id"] for student in term_full["students"]}
        if sibling_roster != current_roster:
            issues.append(create_validation_issue(
                "SHS_ECR_ROSTER_MISMATCH", "export_requirements",
                {"type": "gradebook", "term": term_order, "subjectName": course},
                f"Term {term_order} does not have the same learner roster as the selected record.",
                "Align the learner roster across the requested term records before exporting together.", ["export"],
            ))
        if sibling.teacher_user_id != book.teacher_user_id or sibling.subject_id != book.subject_id:
            issues.append(create_validation_issue(
                "SHS_ECR_ASSIGNMENT_MISMATCH", "export_requirements",
                {"type": "gradebook", "term": term_order, "subjectName": course},
                f"Term {term_order} uses a different teacher or subject assignment.",
                "Use the same assigned teacher and subject for every requested term.", ["export"],
            ))
        try:
            if _policy_group(sibling, db) != policy_key:
                issues.append(create_validation_issue(
                    "SHS_ECR_POLICY_MISMATCH", "shs_track_ecr",
                    {"type": "setting", "field": "Grading policy", "term": term_order},
                    f"Term {term_order} uses a different saved SHS grading policy.",
                    "Assign the same approved SHS grading policy to every requested term.", ["export"],
                ))
            sibling_weights, sibling_items = _assessment_layout(term_full, policy_key, ecr_exam_split)
            if sibling_weights != weights:
                issues.append(create_validation_issue(
                    "SHS_ECR_WEIGHT_MISMATCH", "assessment_setup",
                    {"type": "setting", "field": "Component weights", "term": term_order},
                    f"Term {term_order} uses different grading weights.",
                    "Use the same official ECR component weights for each requested term.", ["export"],
                ))
        except HTTPException as exc:
            issues.append(_export_rule_issue(term_full, exc.detail))
            continue
        _, grade_issues = _student_template_grades(
            term_full, weights, sibling_items, ecr_table, draft_preview=draft_preview,
        )
        issues.extend(grade_issues)
    return issues


def export_shs_ecr(
    db,
    book: Gradebook,
    full: dict,
    region: str,
    division: str,
    school_id: str,
    allowed_teacher_id: int | None = None,
    all_terms: bool = False,
    through_term: int | None = None,
    draft_preview: bool = False,
) -> Path:
    from .reports import (
        EXPORT_DIR,
        TEMPLATES_DIR,
        _complete_draft_preview_record,
        _complete_finalized_record,
        _student_groups,
        _write_class_record_workbook,
        _safe_name,
        new_report_path,
    )

    raise_export_validation(validate_shs_ecr_export(
        db, book, full, region, division, school_id, allowed_teacher_id,
        all_terms=all_terms, through_term=through_term, draft_preview=draft_preview,
    ))

    if allowed_teacher_id is not None and book.teacher_user_id != allowed_teacher_id:
        raise HTTPException(403, "This saved class record belongs to another teacher.")
    if draft_preview and (all_terms or through_term):
        raise HTTPException(422, "Draft previews can export only the selected term.")
    if draft_preview and not _complete_draft_preview_record(full):
        raise HTTPException(409, "A Draft preview requires a Draft class record with learners and complete scores.")
    if not draft_preview and not _complete_finalized_record(full):
        raise HTTPException(409, "Finalize the complete class record before exporting.")
    if not (full["gradebook"].get("teacher_name") or "").strip():
        raise HTTPException(409, "Assign a teacher to this class record before exporting the official ECR.")
    grade = int(normalize_grade_name(full["gradebook"]["grade_name"]))
    if grade not in (11, 12) or not is_supported_shs_ecr_school_year(full["gradebook"]["school_year_name"]):
        raise HTTPException(409, "The official SHS ECR export is available for Grade 11–12 in SY 2026–2027.")
    if not region.strip() or not division.strip() or not school_id.strip().isdigit():
        raise HTTPException(422, "Enter the region, division, and numeric school ID before exporting.")
    if int(full["gradebook"]["term_order"]) not in (1, 2, 3) or (through_term not in (None, 2)) or (through_term and all_terms):
        raise HTTPException(422, "Select the current term, Terms 1–2 from Term 2, or all three terms.")
    if through_term == 2 and int(full["gradebook"]["term_order"]) != 2:
        raise HTTPException(422, "Select Term 2 to export Terms 1–2 together.")

    template = TEMPLATES_DIR / "SUBJECT CLASS RECORDS" / "ECR_3Term - SSHS - SY2026-2027.xlsx"
    catalog, ecr_table = _ecr_reference_data(template)
    category, cluster, course, ecr_weights, ecr_exam_split, course_terms, _, helper_changes = _course_selection(
        book.subject, full["gradebook"]["grade_name"], catalog,
    )
    if course_terms == 1 and (all_terms or through_term == 2):
        raise HTTPException(409, f"The official ECR lists '{course}' for one term; export only its selected term.")
    if course_terms == 2 and all_terms:
        raise HTTPException(409, f"The official ECR lists '{course}' for two terms; export one term or Terms 1–2.")
    policy_key = _policy_group(book, db)
    weights, items_by_group = _assessment_layout(full, policy_key, ecr_exam_split)
    if any(not math.isclose(weights[key], ecr_weights[key], abs_tol=0.001) for key in weights):
        raise HTTPException(409, f"The saved '{policy_key}' policy does not match the official ECR weights for '{course}'.")
    if not math.isclose(sum(weights.values()), 100, abs_tol=0.001):
        raise HTTPException(409, "The saved grading weights do not total 100%.")

    current_males, current_females = _student_groups(full["students"])
    current_males.sort(key=lambda student: (student["full_name"].casefold(), student.get("lrn") or student["external_id"]))
    current_females.sort(key=lambda student: (student["full_name"].casefold(), student.get("lrn") or student["external_id"]))
    roster_key = {student["person_id"] for student in full["students"]}
    periods = tuple(range(1, (through_term or 3) + 1)) if all_terms or through_term else (int(book.term_order),)

    query = select(Gradebook).where(
        Gradebook.school_year_id == book.school_year_id,
        Gradebook.grade_level_id == book.grade_level_id,
        Gradebook.section_id == book.section_id,
        Gradebook.subject_id == book.subject_id,
        Gradebook.grading_period.has(GradingPeriod.deleted_at.is_(None)),
        Gradebook.subject.has(Subject.deleted_at.is_(None)),
        Gradebook.term_order.in_((1, 2, 3)),
        Gradebook.learning_area == "",
    )
    if allowed_teacher_id is not None or all_terms or through_term or course_terms == 2:
        query = query.where(Gradebook.teacher_user_id == book.teacher_user_id)
    siblings = {}
    for sibling in db.scalars(query.order_by(Gradebook.term_order)).all():
        if sibling.term_order in siblings:
            raise HTTPException(409, "Multiple class records match the same SHS subject and term.")
        siblings[sibling.term_order] = sibling
    if not set(periods).issubset(siblings):
        raise HTTPException(409, "All requested terms must be finalized for this subject, section, teacher, and school year.")

    template_term_start = None
    if course_terms == 1:
        template_term_start = ("FIRST TERM", "SECOND TERM", "THIRD TERM")[int(book.term_order) - 1]
    elif course_terms == 2:
        if through_term == 2:
            template_term_start = "FIRST TERM"
        elif book.term_order == 1:
            template_term_start = "FIRST TERM"
        elif book.term_order == 3:
            template_term_start = "SECOND TERM"
        else:
            # Term 2 belongs to the first or second two-term block. Use its saved
            # neighboring records to identify the block instead of guessing.
            has_first_block = 1 in siblings
            has_second_block = 3 in siblings
            if has_first_block == has_second_block:
                raise HTTPException(
                    409,
                    f"The ECR lists '{course}' for two terms, but the saved records do not identify whether it starts in Term 1 or Term 2.",
                )
            template_term_start = "FIRST TERM" if has_first_block else "SECOND TERM"

    changes: dict[str, dict[str, object]] = {"INPUT DATA": {
        "F10": region.strip(),
        "F11": division.strip(),
        "F13": school_id.strip(),
        "F14": "San Jose National High School",
        "F16": 2026,
        "F22": full["gradebook"]["teacher_name"],
        "F24": grade,
        "F25": full["gradebook"]["section_name"],
        "F26": _section_track_for_export(full),
        "F28": category,
        "F29": cluster,
        "F30": course,
    }}
    if helper_changes:
        changes["HELPER"] = helper_changes
    if draft_preview:
        draft_label = "DRAFT PREVIEW — NOT FINAL"
        changes["INPUT DATA"]["D5"] = draft_label
        changes[f"Term {book.term_order}"] = {"B4": draft_label}
    if template_term_start is not None:
        changes["INPUT DATA"]["H33"] = template_term_start

    term_metadata = {
        "H6": f"REGION: {region.strip().upper()}",
        "P6": f"DIVISION: {division.strip().upper()}",
        "AA6": f"SCHOOL ID: {school_id.strip()}",
    }
    for term_order in (1, 2, 3):
        changes.setdefault(f"Term {term_order}", {}).update(term_metadata)

    for roster, lrn_column, name_column in ((current_males, "N", "O"), (current_females, "R", "S")):
        for offset, student in enumerate(roster):
            row = 11 + offset
            changes["INPUT DATA"][f"{lrn_column}{row}"] = student.get("lrn") or ""
            changes["INPUT DATA"][f"{name_column}{row}"] = student["full_name"]

    formulas: dict[str, dict[str, object]] = {}
    for term_order in periods:
        sibling = siblings[term_order]
        term_full = full if sibling.id == book.id else get_gradebook_full(db, sibling.id)
        complete = (
            _complete_draft_preview_record(term_full)
            if draft_preview and sibling.id == book.id
            else _complete_finalized_record(term_full)
        )
        if not complete:
            raise HTTPException(409, f"Term {term_order} is not finalized with complete learner scores.")
        sibling_roster = {student["person_id"] for student in term_full["students"]}
        if sibling_roster != roster_key:
            raise HTTPException(409, "The requested terms do not share the same learner roster.")
        if sibling.teacher_user_id != book.teacher_user_id or sibling.subject_id != book.subject_id:
            raise HTTPException(409, "The requested terms must use the same assigned teacher and subject.")
        if _policy_group(sibling, db) != policy_key:
            raise HTTPException(409, "The requested terms use different saved SHS grading policies.")
        sibling_weights, sibling_items = _assessment_layout(term_full, policy_key, ecr_exam_split)
        if sibling_weights != weights:
            raise HTTPException(409, "The requested terms use different grading weights.")
        grade_cache, grade_issues = _student_template_grades(
            term_full, weights, sibling_items, ecr_table, draft_preview=draft_preview,
        )
        raise_export_validation(grade_issues)
        sheet_name = f"Term {term_order}"
        term_changes, term_formula_values = _term_changes(
            term_full, sibling_items, grade_cache, current_males, current_females,
        )
        for roster, first_row in ((current_males, 17), (current_females, 68)):
            for offset, student in enumerate(roster):
                term_formula_values[f"C{first_row + offset}"] = student["full_name"]
        changes[sheet_name].update(term_changes)
        formulas[sheet_name] = term_formula_values

    period_name = "Terms1-2" if through_term == 2 else "AllTerms" if all_terms else f"Term{book.term_order}"
    preview_prefix = "DRAFT-PREVIEW-NOT-FINAL-" if draft_preview else ""
    target = new_report_path(
        EXPORT_DIR,
        f"{preview_prefix}ClassRecord-{_safe_name(full['gradebook']['school_year_name'])}-{period_name}-Grade{grade}-{_safe_name(full['gradebook']['section_name'])}-{_safe_name(full['gradebook']['subject_name'])}.xlsx",
    )
    _write_class_record_workbook(template, target, changes, formula_values=formulas)
    return target


def is_supported_shs_ecr_school_year(value: object) -> bool:
    year = re.sub(r"^\s*SY\s*", "", str(value or ""), flags=re.IGNORECASE)
    year = re.sub(r"\s*[-–—]\s*", "-", year.strip())
    return year == "2026-2027"
