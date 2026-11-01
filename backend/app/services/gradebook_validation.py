from __future__ import annotations

import math

from fastapi import HTTPException

from .academic_context import is_senior_high


def create_validation_issue(
    code: str,
    group: str,
    location: dict,
    message: str,
    correction: str,
    blocks: tuple[str, ...] | list[str],
    *,
    severity: str = "blocker",
    details: dict | None = None,
) -> dict:
    issue = {
        "code": code,
        "group": group,
        "severity": severity,
        "location": location,
        "message": message,
        "correction": correction,
        "blocks": list(dict.fromkeys(blocks)),
    }
    if details is not None:
        issue["details"] = details
    return issue


def collect_school_detail_issues(region: str, division: str, school_id: str) -> list[dict]:
    region_value = str(region or "").strip()
    division_value = str(division or "").strip()
    school_id_value = str(school_id or "").strip()
    issues = []

    if not region_value or not all(char.upper() in "IVXLCDM -" for char in region_value):
        missing = not region_value
        issues.append(create_validation_issue(
            "SCHOOL_REGION_REQUIRED" if missing else "SCHOOL_REGION_INVALID",
            "school_details",
            {"type": "setting", "field": "Region"},
            "Region is missing." if missing else "Region must use Roman numerals.",
            "Enter the school region using Roman numerals, for example V or IV-A.",
            ["export"],
        ))
    if not division_value:
        issues.append(create_validation_issue(
            "SCHOOL_DIVISION_REQUIRED",
            "school_details",
            {"type": "setting", "field": "Division"},
            "Division is missing.",
            "Enter the school division.",
            ["export"],
        ))
    if not school_id_value.isdigit():
        missing = not school_id_value
        issues.append(create_validation_issue(
            "SCHOOL_ID_REQUIRED" if missing else "SCHOOL_ID_INVALID",
            "school_details",
            {"type": "setting", "field": "School ID"},
            "School ID is missing." if missing else "School ID must contain digits only.",
            "Enter the numeric school ID.",
            ["export"],
        ))
    return issues


def collect_common_export_issues(
    full: dict,
    region: str,
    division: str,
    school_id: str,
    *,
    draft_preview: bool = False,
) -> list[dict]:
    """Collect read-only blockers shared by fixed and adaptive gradebook exports."""
    gradebook = full.get("gradebook", {})
    students = full.get("students", [])
    components = full.get("components", [])
    issues = collect_school_detail_issues(region, division, school_id)

    status = gradebook.get("status") or "Draft"
    if draft_preview:
        if status != "Draft":
            issues.append(create_validation_issue(
                "DRAFT_PREVIEW_STATUS_INVALID", "export_requirements",
                {"type": "gradebook", "field": "Status", "value": status},
                "Draft preview is available only while the saved class record is Draft.",
                "Use the official export after finalizing the class record.", ["export"],
            ))
    elif status not in {"Finalized", "Locked"}:
        issues.append(create_validation_issue(
            "GRADEBOOK_NOT_FINALIZED", "export_requirements",
            {"type": "gradebook", "field": "Status", "value": status},
            f"The class record is {status}.",
            "Finalize or lock the complete class record before exporting the official workbook.", ["export"],
        ))
    if not str(gradebook.get("teacher_name") or "").strip():
        issues.append(create_validation_issue(
            "GRADEBOOK_TEACHER_MISSING", "export_requirements",
            {"type": "setting", "field": "Assigned teacher"},
            "No teacher is assigned to this class record.",
            "Assign a teacher before exporting the official workbook.", ["export"],
        ))
    if is_senior_high(gradebook.get("grade_name")):
        supported_tracks = {"Academic Track", "Technical Professional (TechPro) Track"}
        track = str(gradebook.get("section_track") or "").strip()
        if track not in supported_tracks:
            issues.append(create_validation_issue(
                "SHS_TRACK_UNSUPPORTED", "shs_track_ecr",
                {"type": "section", "sectionName": gradebook.get("section_name") or "Selected section", "field": "SHS track"},
                f"Section {gradebook.get('section_name') or ''} does not have a supported SHS track.".strip(),
                "Assign Academic Track or Technical Professional (TechPro) Track to the section.", ["export"],
            ))
        if gradebook.get("subject_is_elective") and not str(gradebook.get("subject_elective_cluster") or "").strip():
            issues.append(create_validation_issue(
                "SHS_ELECTIVE_CLUSTER_MISSING", "shs_track_ecr",
                {"type": "subject", "subjectName": gradebook.get("subject_name") or "Selected subject", "field": "Elective cluster"},
                "This SHS elective does not have an elective cluster.",
                "Assign the subject to its approved SHS elective cluster.", ["export"],
            ))
    if not students:
        issues.append(create_validation_issue(
            "NO_ACTIVE_LEARNERS", "export_requirements",
            {"type": "setting", "field": "Learners"},
            "This class record has no active learners.",
            "Add at least one active learner to the section before exporting.", ["export"],
        ))

    if not components:
        issues.append(create_validation_issue(
            "ASSESSMENT_COMPONENTS_MISSING", "assessment_setup",
            {"type": "setting", "field": "Assessment setup"},
            "No assessment components are configured.",
            "Configure assessment components before entering grades or exporting.", ["finalization", "export"],
        ))
    total_weight = sum(float(component.get("weight") or 0) for component in components)
    if components and (not math.isfinite(total_weight) or not math.isclose(total_weight, 100, abs_tol=0.01)):
        issues.append(create_validation_issue(
            "ASSESSMENT_WEIGHTS_INVALID", "assessment_setup",
            {"type": "setting", "field": "Component weights"},
            f"Assessment component weights total {total_weight:.2f}%.",
            "Adjust the component weights so they total exactly 100%.", ["finalization", "export"],
            details={"totalWeight": total_weight},
        ))

    for component in components:
        used_items = [item for item in component.get("items", []) if item.get("active", True)]
        if not used_items:
            issues.append(create_validation_issue(
                "ASSESSMENT_ACTIVITIES_MISSING", "assessment_setup",
                {"type": "component", "componentName": component.get("name") or "Unnamed component"},
                f"{component.get('name') or 'This assessment component'} has no used activities.",
                "Add and score at least one activity in this component.", ["finalization", "export"],
            ))
        for student in students:
            for item in used_items:
                item_key = str(item.get("id"))
                value = (student.get("scores") or {}).get(item_key)
                score_status = (student.get("score_statuses") or {}).get(item_key, "Missing")
                try:
                    numeric_value = float(value)
                    maximum = float(item.get("max_score"))
                    valid = math.isfinite(numeric_value) and math.isfinite(maximum) and 0 <= numeric_value <= maximum
                except (TypeError, ValueError):
                    numeric_value, maximum, valid = None, item.get("max_score"), False
                if score_status == "Scored" and valid:
                    continue
                invalid = score_status == "Scored" and not valid
                learner_name = str(student.get("full_name") or "Unnamed learner")
                activity_name = str(item.get("label") or "Unnamed activity")
                max_value = maximum if isinstance(maximum, (int, float)) else item.get("max_score")
                score_range = f"a score from 0 to {max_value:g}" if isinstance(max_value, (int, float)) else "a valid score"
                correction = (
                    f"Replace the score for {activity_name} with {score_range}." if invalid else
                    f"Change {activity_name}'s status from {score_status} to Scored and enter {score_range}."
                    if score_status != "Missing" else
                    f"Enter {score_range} for {activity_name} and mark its status Scored."
                )
                issues.append(create_validation_issue(
                    "SCORE_INVALID" if invalid else "SCORE_MISSING",
                    "scores",
                    {"type": "learner_activity", "learnerId": student.get("person_id"),
                     "learnerName": learner_name, "activityName": activity_name},
                    f"{activity_name} has an invalid score for {learner_name}." if invalid
                    else f"{activity_name} is {str(score_status).lower()} for {learner_name}.",
                    correction,
                    ["finalization", "export"],
                    details={"status": score_status, "maxScore": max_value},
                ))
    return issues


def collect_grade_calculation_issues(
    students: list[dict],
    calculated_grades: dict[int, dict],
    *,
    template_name: str = "export template",
    allowed_initial_variance: float = 0.01,
) -> list[dict]:
    issues = []
    maximum_variance = allowed_initial_variance + 0.0000001
    for student in students:
        person_id = student.get("person_id")
        calculated = calculated_grades.get(person_id)
        if calculated is None:
            continue
        saved_initial = student.get("initial_grade")
        saved_reported = student.get("reported_grade")
        template_initial = calculated.get("initial")
        template_reported = calculated.get("reported")
        initial_difference = (
            abs(float(saved_initial) - float(template_initial))
            if saved_initial is not None and template_initial is not None else None
        )
        initial_mismatch = initial_difference is None or initial_difference > maximum_variance
        reported_mismatch = saved_reported is None or template_reported is None or int(saved_reported) != int(template_reported)
        if not initial_mismatch and not reported_mismatch:
            continue

        learner_name = str(student.get("full_name") or "Unnamed learner")
        if initial_difference is None:
            message = f"{template_name} cannot compare {learner_name}'s initial grade because the saved initial grade is missing."
        else:
            message = (
                f"{template_name} initial grade {float(template_initial):.2f} differs from the saved grade "
                f"{float(saved_initial):.2f} by {initial_difference:.2f}; the allowed variance is {allowed_initial_variance:.2f}."
            )
        if reported_mismatch:
            message += f" The reported grade is {template_reported!s} in {template_name} and {saved_reported!s} in the saved record."
        issues.append(create_validation_issue(
            "ECR_GRADE_CALCULATION_MISMATCH" if template_name == "ECR" else "GRADE_CALCULATION_MISMATCH",
            "grade_calculation",
            {"type": "learner", "learnerId": person_id, "learnerName": learner_name},
            message,
            f"Review {learner_name}'s saved scores and grading policy; correct the source values so the saved and {template_name} grades agree.",
            ["export"],
            details={
                "savedInitial": saved_initial,
                "templateInitial": template_initial,
                "savedReported": saved_reported,
                "templateReported": template_reported,
                "allowedInitialVariance": allowed_initial_variance,
            },
        ))
    return issues


def export_rule_issue(
    detail: str,
    full: dict,
    *,
    template_name: str = "export workbook",
    group: str | None = None,
    location: dict | None = None,
) -> dict:
    text = str(detail or f"The saved record does not match the {template_name} requirements.")
    normalized = text.casefold()
    if group is None:
        if "score" in normalized:
            group = "scores"
            correction = "Enter a valid score within the activity's highest possible score."
        elif "weight" in normalized or "assessment" in normalized or "component" in normalized or "exam" in normalized:
            group = "assessment_setup"
            correction = "Adjust the assessment setup to match the workbook's groups and weights."
        elif "grade" in normalized or "calculation" in normalized or "rounding" in normalized:
            group = "grade_calculation"
            correction = "Review the learner's saved scores and grading policy so the workbook grade matches."
        else:
            group = "export_requirements"
            correction = f"Correct the saved setting described above for the {template_name}."
    else:
        correction = f"Correct the saved setting described above for the {template_name}."

    gradebook = full.get("gradebook", {})
    if location is None:
        location = {"type": "subject", "subjectName": gradebook.get("subject_name") or "Selected subject",
                    "sectionName": gradebook.get("section_name"), "term": gradebook.get("term_order")}
        if group == "grade_calculation":
            for student in full.get("students", []):
                learner_name = str(student.get("full_name") or "")
                if learner_name and learner_name.casefold() in text.casefold():
                    location = {"type": "learner", "learnerId": student.get("person_id"), "learnerName": learner_name}
                    break
    return create_validation_issue(
        "GRADE_CALCULATION_MISMATCH" if group == "grade_calculation" else "EXPORT_RULE_MISMATCH",
        group,
        location,
        text,
        correction,
        ["export"],
    )


def raise_export_validation(issues: list[dict]) -> None:
    if issues:
        raise HTTPException(409, detail={
            "code": "EXPORT_VALIDATION_FAILED",
            "message": "Resolve the listed validation blockers before exporting.",
            "issues": issues,
        })
