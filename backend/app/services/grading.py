"""Grading service layer for EduScan.

This module bridges the database models and the stateless grading engine.
It queries data from the ORM, converts it to plain dicts for the engine,
and writes results back.
"""
from __future__ import annotations
from .section_advisers import adviser_for_section

import json
import math
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..models import (
    GradeLevel, GradingPeriod, Person, SchoolSection, SchoolYear, Subject,
    SubjectTeachingAssignment, User,
)
from ..models_grading import (
    AssessmentItem, Gradebook, GradebookAuditEntry, GradebookComponent,
    GradeAdjustmentRequest, GradeCriteriaAdjustmentRequest, GradingPolicy, StudentScore, SCORE_STATUSES,
)
from .grading_engine import (
    DEFAULT_TRANSMUTATION_TABLE, apply_transmutation, build_default_transmutation_table,
    calculate_student_grade, generate_calculation_breakdown, round_value,
    reporting_method_for_school_year,
    validate_gradebook as engine_validate,
    normalize_component_weights,
)
from .academic_context import elective_track_for_subject, grade_name_aliases, normalize_grade_name, subject_policy_category, is_senior_high
from .settings_store import get_json

# --- Legacy compatibility imports (kept for old endpoints) ---
from ..models import GradeComponent, GradeScore, GradebookState


def transmute_grade(initial_grade: float) -> int:
    """Legacy transmutation using the piecewise formula.
    Kept for backward compatibility with old class_key endpoints.
    """
    return apply_transmutation(initial_grade) or 60


def _gradebook_for_update(db: Session, gradebook_id: int) -> Gradebook | None:
    book = db.scalar(
        select(Gradebook)
        .where(Gradebook.id == gradebook_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if book and book.is_legacy_readonly:
        raise ValueError("This legacy MAPEH record is read-only. Use the new learning-area gradebooks.")
    return book


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------

def get_policy(db: Session, policy_id: int | None) -> GradingPolicy | None:
    if not policy_id:
        return None
    return db.get(GradingPolicy, policy_id)


def get_active_policy_for(
    db: Session,
    school_year: str,
    grade_level_name: str,
    subject_category: str = "General",
) -> GradingPolicy | None:
    """Find the best matching active grading policy for a context."""
    policies = db.scalars(
        select(GradingPolicy)
        .where(GradingPolicy.status == "Active", GradingPolicy.school_year == school_year)
        .order_by(GradingPolicy.created_at.desc())
    ).all()

    general = None
    for policy in policies:
        grade_levels = [normalize_grade_name(g) for g in policy.grade_levels.split(",") if g.strip()]
        if grade_levels and normalize_grade_name(grade_level_name) not in grade_levels:
            continue
        if policy.subject_category.lower() == subject_category.lower():
            return policy
        if policy.subject_category.lower() == "general" and general is None:
            general = policy
    return general


def policy_transmutation_table(policy: GradingPolicy | None) -> list[dict] | None:
    """Extract the transmutation table from a policy, or use the default."""
    if not policy or not policy.transmutation_table_json:
        return None  # Engine will use built-in fallback
    try:
        table = json.loads(policy.transmutation_table_json)
        return table if isinstance(table, list) and table else None
    except (json.JSONDecodeError, TypeError):
        return None


def policy_component_definitions(policy: GradingPolicy | None) -> list[dict]:
    """Extract component definitions from a policy."""
    if not policy or not policy.component_definitions_json:
        return []
    try:
        defs = json.loads(policy.component_definitions_json)
        return normalize_component_weights(defs) if isinstance(defs, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Gradebook queries
# ---------------------------------------------------------------------------

def get_gradebook(db: Session, gradebook_id: int) -> Gradebook | None:
    return db.get(Gradebook, gradebook_id)


def get_gradebook_by_class_key(db: Session, class_key: str) -> Gradebook | None:
    return db.scalar(
        select(Gradebook).where(Gradebook.class_key == class_key)
    )


def gradebook_roster_query(book: Gradebook, roster_person_ids: list[int] | None = None):
    query = select(Person).where(Person.role == "Student")
    if roster_person_ids is None:
        query = query.where(
            Person.active.is_(True),
            func.lower(func.trim(Person.grade)).in_(grade_name_aliases(book.grade_name)),
            func.lower(func.trim(Person.section)) == book.section_name.strip().lower(),
        )
    else:
        query = query.where(Person.id.in_(roster_person_ids))
    return query.order_by(Person.full_name, Person.external_id)


def teacher_grading_section_ids(db: Session, user: User) -> set[int]:
    """Sections where the teacher is adviser or has a subject assignment."""
    from ..models import SectionAdviserAssignment
    adviser_ids = set(db.scalars(select(SectionAdviserAssignment.section_id).where(SectionAdviserAssignment.teacher_user_id == user.id)).all())
    teaching_ids = set(db.scalars(select(SubjectTeachingAssignment.section_id).join(
        SchoolSection, SchoolSection.id == SubjectTeachingAssignment.section_id,
    ).where(
        SubjectTeachingAssignment.teacher_user_id == user.id,
        SubjectTeachingAssignment.active.is_(True),
        SchoolSection.active.is_(True),
        SchoolSection.deleted_at.is_(None),
    )).all())
    return adviser_ids | teaching_ids


def teacher_can_access_gradebook_context(
    db: Session, user: User, school_year_id: int, section_id: int, subject_id: int,
) -> bool:
    """Check the exact subject/section/year; section membership alone is insufficient."""
    teacher_subject_ids = set(db.scalars(select(SubjectTeachingAssignment.subject_id).join(
        SchoolSection, SchoolSection.id == SubjectTeachingAssignment.section_id,
    ).join(GradeLevel, GradeLevel.id == SchoolSection.grade_level_id).join(
        Subject, Subject.id == SubjectTeachingAssignment.subject_id,
    ).where(
        SubjectTeachingAssignment.school_year_id == school_year_id,
        SubjectTeachingAssignment.teacher_user_id == user.id,
        SubjectTeachingAssignment.active.is_(True),
        SchoolSection.active.is_(True), SchoolSection.deleted_at.is_(None),
        GradeLevel.active.is_(True), GradeLevel.deleted_at.is_(None),
        Subject.active.is_(True), Subject.deleted_at.is_(None),
    )).all())
    if len(teacher_subject_ids) > 1:
        return False

    assignment = db.scalar(select(SubjectTeachingAssignment).where(
        SubjectTeachingAssignment.school_year_id == school_year_id,
        SubjectTeachingAssignment.section_id == section_id,
        SubjectTeachingAssignment.subject_id == subject_id,
        SubjectTeachingAssignment.active.is_(True),
    ))
    if assignment:
        return assignment.teacher_user_id == user.id
    # Subject assignments are the source of truth for teacher gradebooks.
    # An adviser must not gain access to every subject when no assignment exists.
    return False


def _validate_subject_teacher(db: Session, school_year_id: int, subject_id: int,
                              teacher_id: int | None, exclude_gradebook_id: int | None = None, section_id: int | None = None) -> None:
    if teacher_id is None:
        return
    query = select(Gradebook).where(
        Gradebook.school_year_id == school_year_id,
        Gradebook.subject_id == subject_id,
        Gradebook.teacher_user_id.is_not(None),
        Gradebook.teacher_user_id != teacher_id,
    )
    if exclude_gradebook_id is not None:
        query = query.where(Gradebook.id != exclude_gradebook_id)
    if section_id is not None:
        query = query.where(Gradebook.section_id == section_id)
    existing = db.scalars(query).first()
    if existing:
        assigned = db.get(User, existing.teacher_user_id)
        teacher_name = assigned.full_name if assigned else existing.teacher_name or "another teacher"
        subject = db.get(Subject, subject_id)
        raise ValueError(
            f"{subject.name if subject else 'This subject'} is already assigned to {teacher_name} "
                "for this section and school year."
        )


def validate_score_value(item: AssessmentItem, score: float | None, status: str) -> float | None:
    if status not in SCORE_STATUSES:
        raise ValueError('Invalid assessment score status')
    if status != 'Scored':
        return None
    if score is None:
        raise ValueError(f"Score required for item '{item.label}' with status 'Scored'")
    value = float(score)
    if not math.isfinite(value) or not 0 <= value <= item.max_score:
        raise ValueError(f'Score {value} out of bounds (0 - {item.max_score}) for {item.label}')
    return value


def get_gradebook_full(db: Session, gradebook_id: int, *, include_mapeh_summary=True,
                       roster_person_ids: list[int] | None = None) -> dict | None:
    """Load a gradebook with all components, items, scores, and calculations."""
    book = db.scalar(
        select(Gradebook)
        .options(
            joinedload(Gradebook.components).joinedload(GradebookComponent.items),
        )
        .where(Gradebook.id == gradebook_id)
    )
    if not book:
        return None

    # Load students for this grade/section
    students = db.scalars(gradebook_roster_query(book, roster_person_ids)).all()

    # Collect all assessment item IDs
    all_item_ids = []
    components_data = []
    items_by_component: dict[int, list[dict]] = {}

    for comp in book.components:
        comp_items = []
        for item in comp.items:
            comp_items.append({
                "id": item.id,
                "label": item.label,
                "max_score": item.max_score,
                "assessment_date": str(item.assessment_date) if item.assessment_date else None,
                "sequence": item.sequence,
                "description": item.description,
            })
            all_item_ids.append(item.id)
        items_by_component[comp.id] = comp_items
        components_data.append({
            "id": comp.id,
            "name": comp.name,
            "component_type": comp.component_type,
            "weight": comp.weight,
            "sequence": comp.sequence,
            "description": comp.description,
            "items": comp_items,
        })

    components_data = normalize_component_weights(components_data)

    # Load all scores for these items
    scores = db.scalars(
        select(StudentScore).where(StudentScore.assessment_item_id.in_(all_item_ids))
    ).all() if all_item_ids else []

    # Assessment Setup defines capacity; only activities used by this class
    # contribute to grades or become required for every learner.
    roster_ids = {student.id for student in students}
    active_item_ids = {
        score.assessment_item_id for score in scores
        if score.person_id in roster_ids and (score.score is not None or score.status != "Missing")
    }
    active_item_ids.update(item['id'] for component in components_data
                           if component['component_type'] == 'Term Examinations' for item in component['items'])
    items_by_component = {
        component_id: [item for item in items if item["id"] in active_item_ids]
        for component_id, items in items_by_component.items()
    }
    for component in components_data:
        for item in component["items"]:
            item["active"] = item["id"] in active_item_ids

    # Group scores by person
    scores_by_person: dict[int, list[dict]] = defaultdict(list)
    for s in scores:
        scores_by_person[s.person_id].append({
            "item_id": s.assessment_item_id,
            "score": s.score,
            "status": s.status,
            "reason": s.reason,
        })

    # Get policy
    policy = get_policy(db, book.grading_policy_id)
    trans_table = policy_transmutation_table(policy)

    rounding_dp = policy.rounding_decimal_places if policy else 2
    rounding_final_dp = policy.rounding_final_decimal_places if policy else 0
    rounding_method = policy.rounding_method if policy else "half_up"
    reporting_method = policy.reporting_method if policy else reporting_method_for_school_year(book.school_year or book.school_year_name)

    # Calculate grades for each student
    student_rows = []
    completed_grades = []
    for student in students:
        student_score_list = scores_by_person.get(student.id, [])
        calc = calculate_student_grade(
            student_scores=student_score_list,
            components=components_data,
            items_by_component=items_by_component,
            transmutation_table=trans_table,
            passing_grade=book.passing_grade,
            rounding_decimal_places=rounding_dp,
            rounding_final_decimal_places=rounding_final_dp,
            rounding_method=rounding_method,
            reporting_method=reporting_method,
        )

        # Build per-item score map for the student
        score_map = {}
        status_map = {}
        reason_map = {}
        for s_data in student_score_list:
            item_id_str = str(s_data["item_id"])
            score_map[item_id_str] = s_data["score"]
            status_map[item_id_str] = s_data["status"]
            if s_data.get("reason"):
                reason_map[item_id_str] = s_data["reason"]

        student_rows.append({
            "person_id": student.id,
            "external_id": student.external_id,
            "lrn": student.lrn,
            "full_name": student.full_name,
            "sex": student.sex,
            "scores": score_map,
            "score_statuses": status_map,
            "score_reasons": reason_map,
            "initial_grade": calc["initial_grade"],
            "reported_grade": calc["reported_grade"],
            "status": calc["status"],
            "complete": calc["complete"],
            "component_grades": calc["component_grades"],
            "component_details": calc["component_details"],
        })

        if calc["reported_grade"] is not None:
            completed_grades.append(calc["reported_grade"])

    # Statistics
    distribution = defaultdict(int)
    for g in completed_grades:
        bucket = "90-100" if g >= 90 else "85-89" if g >= 85 else "80-84" if g >= 80 else "75-79" if g >= 75 else "Below 75"
        distribution[bucket] += 1

    statistics = {
        "learners": len(student_rows),
        "complete": len(completed_grades),
        "incomplete": len(student_rows) - len(completed_grades),
        "passed": sum(1 for g in completed_grades if g >= book.passing_grade),
        "below_passing": sum(1 for g in completed_grades if g < book.passing_grade),
        "average": round(sum(completed_grades) / len(completed_grades), 2) if completed_grades else None,
        "highest": max(completed_grades) if completed_grades else None,
        "lowest": min(completed_grades) if completed_grades else None,
        "distribution": dict(distribution),
    }

    return {
        "gradebook": {
            "id": book.id,
            "school_year_id": book.school_year_id,
            "grading_period_id": book.grading_period_id,
            "section_id": book.section_id,
            "subject_id": book.subject_id,
            "teacher_user_id": book.teacher_user_id,
            "school_year_name": book.school_year_name,
            "school_head": get_json(db, "school.heads", {}).get(str(book.school_year_id), {}).get("full_name", ""),
            "term_order": book.term_order,
            "grade_name": normalize_grade_name(book.grade_name),
            "section_name": book.section_name,
            "subject_name": book.subject_name,
            "learning_area": book.learning_area,
            "is_legacy_readonly": book.is_legacy_readonly,
            "teacher_name": book.teacher_name,
            "grading_period_name": book.grading_period.name if book.grading_period else None,
            "class_key": book.class_key,
            "status": book.status,
            "passing_grade": book.passing_grade,
            "grading_policy_id": book.grading_policy_id,
            "policy_name": policy.name if policy else None,
            "policy_version": policy.version if policy else None,
            "submitted_at": book.submitted_at,
            "submitted_by_name": book.submitted_by_name,
            "finalized_at": book.finalized_at,
            "finalized_by_name": book.finalized_by_name,
            "locked_at": book.locked_at,
            "locked_by_name": book.locked_by_name,
            "reopened_at": book.reopened_at,
            "reopened_by_name": book.reopened_by_name,
            "reopen_reason": book.reopen_reason,
            "created_at": book.created_at,
            "updated_at": book.updated_at,
        },
        "components": components_data,
        "policy": {
            "transmutation_table": trans_table,
            "reporting_method": reporting_method,
            "rounding_decimal_places": rounding_dp,
            "rounding_final_decimal_places": rounding_final_dp,
            "rounding_method": rounding_method,
        },
        "students": student_rows,
        "statistics": statistics,
        "mapeh_summary": mapeh_combined_summary(db, book) if include_mapeh_summary and book.learning_area else None,
    }


def mapeh_combined_summary(db, book):
    siblings = db.scalars(select(Gradebook).where(
        Gradebook.school_year_id == book.school_year_id,
        Gradebook.grade_level_id == book.grade_level_id,
        Gradebook.section_id == book.section_id, Gradebook.subject_id == book.subject_id,
        Gradebook.teacher_user_id == book.teacher_user_id,
        Gradebook.learning_area.in_(['music_arts', 'pe_health']),
        Gradebook.is_legacy_readonly.is_(False))).all()
    rows = {}
    for sibling in siblings:
        full = get_gradebook_full(db, sibling.id, include_mapeh_summary=False)
        for student in full['students']:
            row = rows.setdefault(student['person_id'], {'person_id': student['person_id'], 'full_name': student['full_name'], 'terms': {}})
            term = row['terms'].setdefault(sibling.term_order, {})
            term[sibling.learning_area] = student['reported_grade'] if sibling.status in {'Finalized', 'Locked'} else None
    for row in rows.values():
        combined = []
        for number in (1, 2, 3):
            term = row['terms'].setdefault(number, {})
            values = [term.get(area) for area in ('music_arts', 'pe_health')]
            term['combined'] = round_value(sum(values)/2, 0, 'half_up') if all(v is not None for v in values) else None
            combined.append(term['combined'])
        row['final'] = round_value(sum(combined)/3, 0, 'half_up') if all(v is not None for v in combined) else None
    return list(rows.values())


def get_student_breakdown(
    db: Session, gradebook_id: int, person_id: int,
) -> dict | None:
    """Generate a calculation breakdown for a single student."""
    full = get_gradebook_full(db, gradebook_id)
    if not full:
        return None

    student = None
    for row in full["students"]:
        if row["person_id"] == person_id:
            student = row
            break
    if not student:
        return None

    policy_name = full["gradebook"].get("policy_name", "")
    breakdown = generate_calculation_breakdown(
        student_name=student["full_name"],
        calculation_result={
            "initial_grade": student["initial_grade"],
            "reported_grade": student["reported_grade"],
            "status": student["status"],
            "complete": student["complete"],
            "component_grades": student["component_grades"],
        },
        policy_name=policy_name or "Default DepEd K-12",
        passing_grade=full["gradebook"]["passing_grade"],
    )
    for line, detail in zip(breakdown['components'], student['component_details']):
        line['name'] = line['component']
        line['total_score'] = detail['total_earned'] if detail['complete'] else None
        line['total_max'] = detail['total_possible'] if detail['complete'] else None
    return breakdown


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def add_gradebook_audit(
    db: Session,
    gradebook_id: int,
    action: str,
    actor: User,
    reason: str = "",
    person_id: int | None = None,
    person_name: str | None = None,
    assessment_item_id: int | None = None,
    assessment_label: str | None = None,
    component_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> GradebookAuditEntry:
    entry = GradebookAuditEntry(
        gradebook_id=gradebook_id,
        person_id=person_id,
        person_name=person_name,
        assessment_item_id=assessment_item_id,
        assessment_label=assessment_label,
        component_name=component_name,
        action=action,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        actor_user_id=actor.id,
        actor_name=actor.full_name,
        actor_role=actor.role,
    )
    db.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Gradebook creation and lifecycle operations
# ---------------------------------------------------------------------------

def create_or_get_gradebook(
    db: Session,
    school_year_id: int,
    grading_period_id: int,
    grade_level_id: int,
    section_id: int,
    subject_id: int,
    user: User,
    grading_policy_id: int | None = None,
    learning_area: str = "",
    commit: bool = True,
) -> Gradebook:
    sy = db.get(SchoolYear, school_year_id)
    gp = db.get(GradingPeriod, grading_period_id)
    gl = db.get(GradeLevel, grade_level_id)
    sec = db.get(SchoolSection, section_id)
    subj = db.get(Subject, subject_id)

    if not all([sy, gp, gl, sec, subj]):
        raise ValueError("Invalid academic structure references")
    if any(item.deleted_at is not None for item in (sy, gp, gl, sec, subj)):
        raise ValueError("Restore the deleted academic setup item before using it for a class record")
    if gp.school_year_id != sy.id:
        raise ValueError("The grading period does not belong to the selected school year")
    if sec.grade_level_id != gl.id:
        raise ValueError("The section does not belong to the selected grade level")
    if is_senior_high(gl.name) != (subj.category or "JHS").strip().upper().startswith("SHS"):
        raise ValueError("The subject does not belong to the selected junior/senior high level")
    required_track = elective_track_for_subject(subj.category, subj.is_elective, subj.elective_track)
    if required_track and (sec.track or "").strip().casefold() != required_track.casefold():
        scope = "track" if (subj.category or "JHS").strip().upper().startswith("SHS") else "program"
        raise ValueError(f"This elective is available only to the {required_track} {scope}")

    class_key = f"{sy.name}-q{gp.term_order}-{gl.name}-{sec.name}-{subj.name}".lower().replace(" ", "-")
    if learning_area:
        from .mapeh_learning_areas import validate_area
        validate_area(subj, gl.name, learning_area)
        class_key += f"--{learning_area}"

    book = db.scalars(
        select(Gradebook).where(
            (
                (Gradebook.school_year_id == school_year_id) &
                (Gradebook.grading_period_id == grading_period_id) &
                (Gradebook.grade_level_id == grade_level_id) &
                (Gradebook.section_id == section_id) &
                (Gradebook.subject_id == subject_id) &
                (Gradebook.learning_area == learning_area)
            ) | (Gradebook.class_key == class_key)
        )
    ).first()

    assignment = db.scalar(select(SubjectTeachingAssignment).where(
        SubjectTeachingAssignment.school_year_id == school_year_id,
        SubjectTeachingAssignment.subject_id == subject_id,
        SubjectTeachingAssignment.section_id == section_id,
        SubjectTeachingAssignment.active.is_(True),
    ))
    if user.role == "teacher" and not teacher_can_access_gradebook_context(
        db, user, school_year_id, section_id, subject_id,
    ):
        raise ValueError("This subject and section are not assigned to your teacher account")
    assigned_teacher = (db.get(User, assignment.teacher_user_id) if assignment else
                        adviser_for_section(db, school_year_id, section_id) or
                        (user if user.role == "teacher" else None))
    teacher_id = assigned_teacher.id if assigned_teacher else (book.teacher_user_id if book else None)
    if not assignment:
        _validate_subject_teacher(db, school_year_id, subject_id, teacher_id,
                                  exclude_gradebook_id=book.id if book else None, section_id=section_id)

    if book and book.is_legacy_readonly:
        return book
    if book:
        # Update references if they changed (e.g. subject recreated)
        book.school_year_id = school_year_id
        book.grading_period_id = grading_period_id
        book.grade_level_id = grade_level_id
        book.section_id = section_id
        book.subject_id = subject_id
        book.school_year_name = sy.name
        book.term_order = gp.term_order
        book.grade_name = gl.name
        book.section_name = sec.name
        book.subject_name = subj.name

        # Sync teacher_name / teacher_user_id from the section's assigned adviser.
        # This prevents a stale "System Administrator" name from appearing when an
        # admin first opened the page and created the record, but the class is actually
        # managed by the teacher linked as section adviser.
        if assigned_teacher:
            book.teacher_user_id = assigned_teacher.id
            book.teacher_name = assigned_teacher.full_name
        if commit: db.commit()
        return book

    from .academic_context import subject_matches_grade
    if not subject_matches_grade(subj, gl.name):
        raise ValueError('This elective is not allowed for the selected grade level')
    policy = None
    if learning_area:
        from .mapeh_learning_areas import area_policy
        policy = area_policy(db, sy.name, user)
    if grading_policy_id and not learning_area:
        policy = db.get(GradingPolicy, grading_policy_id)
    if not policy:
        if not is_senior_high(gl.name):
            from .template_policies import ensure_template_policies
            ensure_template_policies(db, sy.name, user)
        policy = get_active_policy_for(db, sy.name, gl.name, subject_policy_category(subj.name, subj.category))

    class_key = f"{sy.name}-q{gp.term_order}-{gl.name}-{sec.name}-{subj.name}".lower().replace(" ", "-")
    if learning_area:
        from .mapeh_learning_areas import validate_area
        validate_area(subj, gl.name, learning_area)
        class_key += f"--{learning_area}"

    book = Gradebook(
        school_year_id=school_year_id,
        grading_period_id=grading_period_id,
        grade_level_id=grade_level_id,
        section_id=section_id,
        subject_id=subject_id,
        grading_policy_id=policy.id if policy else None,
        teacher_user_id=assigned_teacher.id if assigned_teacher else None,
        school_year_name=sy.name,
        term_order=gp.term_order,
        grade_name=gl.name,
        section_name=sec.name,
        subject_name=subj.name,
        teacher_name=assigned_teacher.full_name if assigned_teacher else "",
        class_key=class_key,
        learning_area=learning_area,
        status="Draft",
        passing_grade=policy.passing_grade if policy else 75,
    )
    db.add(book)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Gradebook).where(
            Gradebook.school_year_id == school_year_id,
            Gradebook.grading_period_id == grading_period_id,
            Gradebook.grade_level_id == grade_level_id,
            Gradebook.section_id == section_id,
            Gradebook.subject_id == subject_id,
            Gradebook.learning_area == learning_area,
        ))
        if existing:
            return existing
        raise

    comp_defs = policy_component_definitions(policy)
    if comp_defs:
        for seq, cdef in enumerate(comp_defs):
            comp = GradebookComponent(
                gradebook_id=book.id,
                name=cdef.get("name", f"Component {seq + 1}"),
                component_type=cdef.get("component_type", "Quarterly Assessment" if "Quarterly" in cdef.get("name", "") else "Performance Task" if "Performance" in cdef.get("name", "") else "Written Work"),
                weight=float(cdef.get("weight", 0.0)),
                sequence=seq,
                description=cdef.get("description", ""),
            )
            db.add(comp)
            db.flush()
            item_count = max(1, min(100, int(cdef.get("max_items", 1 if "Quarterly Assessment" in comp.name else 5))))
            if comp.component_type == 'Term Examinations':
                item_count = 3
            for i in range(item_count):
                item = AssessmentItem(
                    component_id=comp.id,
                    label=('ST1', 'ST2', 'TE')[i] if comp.component_type == 'Term Examinations' else f"{comp.name} {i + 1}" if item_count > 1 else comp.name,
                    max_score=20.0 if "Written" in comp.name else 50.0,
                    sequence=i,
                )
                db.add(item)
    else:
        default_defs = [
            ("Written Work", "Written Work", 30.0, 20.0),
            ("Performance Tasks", "Performance Task", 50.0, 50.0),
            ("Quarterly Assessment", "Quarterly Assessment", 20.0, 50.0),
        ]
        for seq, (cname, ctype, cweight, cmax) in enumerate(default_defs):
            comp = GradebookComponent(
                gradebook_id=book.id,
                name=cname,
                component_type=ctype,
                weight=cweight,
                sequence=seq,
            )
            db.add(comp)
            db.flush()
            item_count = 1 if cname == "Quarterly Assessment" else 5
            for i in range(item_count):
                item = AssessmentItem(
                    component_id=comp.id,
                    label=f"{cname} {i + 1}" if item_count > 1 else cname,
                    max_score=cmax,
                    sequence=i,
                )
                db.add(item)

    add_gradebook_audit(
        db, book.id, "Create", user,
        reason="Gradebook initialized",
    )
    if commit: db.commit()
    else: db.flush()
    return book


def update_gradebook_components(
    db: Session,
    gradebook_id: int,
    user: User,
    components_payload: list[dict],
    reason: str,
) -> Gradebook:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status in {"Finalized", "Locked"}:
        raise ValueError(f"Cannot edit components in {book.status} gradebook")

    if book.learning_area:
        from .template_policies import policy_components
        expected = policy_components('mapeh')
        actual = [(c.get('component_type'), float(c['weight'])) for c in components_payload]
        if actual != [(c['component_type'], float(c['weight'])) for c in expected]:
            raise ValueError('MAPEH learning areas use fixed 20/60/20 criteria.')
        exams = components_payload[-1].get('items', [])
        if [item['label'] for item in exams] != ['ST1','ST2','TE']:
            raise ValueError('MAPEH examinations require ST1, ST2 and TE.')
    total_weight = sum(float(c.get("weight", 0)) for c in components_payload)
    if abs(total_weight - 100.0) > 0.01:
        raise ValueError(f"Component weights must total exactly 100% (currently {total_weight:.2f}%)")

    existing_comps = {c.id: c for c in book.components}
    seen_components = set()
    seen_items = set()
    retained_items = set()
    all_items = {item.id: item for component in book.components for item in component.items}
    # Validate the whole request before deleting or altering any saved activity.
    for component in components_payload:
        comp_id = component.get('id')
        if comp_id and (comp_id not in existing_comps or comp_id in seen_components):
            raise ValueError('Assessment components must belong to this class record and cannot be repeated')
        if comp_id:
            seen_components.add(comp_id)
        weight = float(component.get('weight', 0))
        if not math.isfinite(weight) or not 0 <= weight <= 100 or not component.get('name', '').strip():
            raise ValueError('Components require a name and a weight between 0 and 100')
        if not component.get('items'):
            raise ValueError('Each component must contain at least one assessment item')
        if component.get('component_type') == 'Term Examinations' and (
            len(component['items']) != 3 or {item.get('label') for item in component['items']} != {'ST1', 'ST2', 'TE'}
        ):
            raise ValueError('Term Examinations requires exactly ST1, ST2, and TE; their scores may be saved as drafts.')
        for item in component['items']:
            item_id = item.get('id')
            max_score = float(item['max_score'])
            if not item.get('label', '').strip() or not math.isfinite(max_score) or max_score <= 0:
                raise ValueError('Assessments require a label and a positive maximum score')
            if item_id:
                if item_id not in all_items or all_items[item_id].component_id != comp_id or item_id in seen_items:
                    raise ValueError('Assessment items must belong to their component and cannot be repeated')
                seen_items.add(item_id)
                retained_items.add(item_id)
                highest = db.scalar(select(func.max(StudentScore.score)).where(
                    StudentScore.assessment_item_id == item_id, StudentScore.status == 'Scored'))
                if highest is not None and highest > max_score:
                    raise ValueError(f"Cannot lower the maximum for '{item['label']}' below a saved score ({highest})")
    removed_ids = set(all_items) - retained_items
    if removed_ids and db.scalar(select(StudentScore.id).where(
        StudentScore.assessment_item_id.in_(removed_ids), StudentScore.status != 'Missing').limit(1)):
        raise ValueError('Cannot remove an assessment with recorded scores or statuses. Clear its entries before removing it.')
    kept_comp_ids = {c.get("id") for c in components_payload if c.get("id")}

    # Delete removed components first
    for old_c_id, old_comp in list(existing_comps.items()):
        if old_c_id not in kept_comp_ids:
            db.delete(old_comp)
    db.flush()

    # Re-fetch existing components after deletion
    existing_comps = {c.id: c for c in book.components if c.id in kept_comp_ids}

    for c_seq, c_data in enumerate(components_payload):
        c_id = c_data.get("id")
        comp = existing_comps.get(c_id) if c_id else None
        if not comp:
            comp = GradebookComponent(
                gradebook_id=book.id,
                name=c_data["name"].strip(),
                component_type=c_data.get("component_type", "Written Work"),
                weight=float(c_data["weight"]),
                sequence=c_seq,
                description=c_data.get("description", ""),
            )
            db.add(comp)
            db.flush()
        else:
            comp.name = c_data["name"].strip()
            comp.component_type = c_data.get("component_type", comp.component_type)
            comp.weight = float(c_data["weight"])
            comp.sequence = c_seq
            comp.description = c_data.get("description", comp.description)

        items_payload = c_data.get("items", [])
        existing_items = {item.id: item for item in comp.items}
        kept_item_ids = {item.get("id") for item in items_payload if item.get("id")}

        # Delete removed items under this component first
        for old_item_id, old_item in list(existing_items.items()):
            if old_item_id not in kept_item_ids:
                db.delete(old_item)
        db.flush()

        existing_items = {item.id: item for item in comp.items if item.id in kept_item_ids}

        for i_seq, i_data in enumerate(items_payload):
            i_id = i_data.get("id")
            item = existing_items.get(i_id) if i_id else None
            max_score = float(i_data["max_score"])
            if max_score <= 0:
                raise ValueError(f"Maximum score must be positive for '{i_data.get('label')}'")

            if not item:
                item = AssessmentItem(
                    component_id=comp.id,
                    label=i_data["label"].strip(),
                    max_score=max_score,
                    assessment_date=i_data.get("assessment_date"),
                    sequence=i_seq,
                    description=i_data.get("description", ""),
                )
                db.add(item)
                db.flush()
            else:
                item.label = i_data["label"].strip()
                item.max_score = max_score
                item.assessment_date = i_data.get("assessment_date")
                item.sequence = i_seq
                item.description = i_data.get("description", item.description)

    book.updated_at = datetime.utcnow()
    add_gradebook_audit(
        db, gradebook_id, "ComponentsUpdate", user,
        reason=reason,
    )
    db.commit()
    return book


def save_gradebook_scores(
    db: Session,
    gradebook_id: int,
    user: User,
    scores_dict: dict[str, list[dict]],
    reason: str,
) -> dict:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status in {"Finalized", "Locked"}:
        raise ValueError(f"Cannot edit scores in {book.status} gradebook")

    items = db.scalars(
        select(AssessmentItem)
        .join(GradebookComponent)
        .where(GradebookComponent.gradebook_id == gradebook_id)
    ).all()
    item_map = {item.id: item for item in items}

    existing_scores = db.scalars(
        select(StudentScore).where(
            StudentScore.assessment_item_id.in_(list(item_map.keys()))
        )
    ).all() if item_map else []
    existing_map = {(s.person_id, s.assessment_item_id): s for s in existing_scores}
    roster_ids = {person.id for person in db.scalars(gradebook_roster_query(book)).all()}
    seen_scores = set()
    for person_id_str, entries in scores_dict.items():
        person_id = int(person_id_str)
        if person_id not in roster_ids:
            raise ValueError("Scores can only be saved for active students in this gradebook's class")
        for entry in entries:
            item_id = entry.get('assessment_item_id')
            if item_id not in item_map:
                raise ValueError('The assessment item does not belong to this gradebook')
            if (person_id, item_id) in seen_scores:
                raise ValueError('A learner cannot have duplicate entries for the same assessment')
            seen_scores.add((person_id, item_id))
            validate_score_value(item_map[item_id], entry.get('score'), entry.get('status', 'Scored'))

    updated_count = 0
    for person_id_str, entry_list in scores_dict.items():
        person_id = int(person_id_str)
        if person_id not in roster_ids:
            raise ValueError("Scores can only be saved for active students in this gradebook's class")
        person = db.get(Person, person_id)
        person_name = person.full_name if person else None

        for entry in entry_list:
            item_id = entry.get("assessment_item_id")
            if item_id not in item_map:
                raise ValueError("The assessment item does not belong to this gradebook")
            item = item_map[item_id]
            raw_score = entry.get("score")
            status = entry.get("status", "Scored")
            entry_reason = entry.get("reason")

            numeric_score = validate_score_value(item, raw_score, status)

            key = (person_id, item_id)
            if key in existing_map:
                existing = existing_map[key]
                old_desc = f"{existing.status}:{existing.score}"
                new_desc = f"{status}:{numeric_score}"
                if old_desc != new_desc:
                    existing.score = numeric_score
                    existing.status = status
                    existing.reason = entry_reason
                    existing.updated_by = user.id
                    existing.updated_at = datetime.utcnow()
                    updated_count += 1
                    add_gradebook_audit(
                        db, gradebook_id, "ScoreUpdate", user,
                        reason=reason,
                        person_id=person_id,
                        person_name=person_name,
                        assessment_item_id=item_id,
                        assessment_label=item.label,
                        component_name=item.component.name if item.component else None,
                        old_value=old_desc,
                        new_value=new_desc,
                    )
            else:
                new_score = StudentScore(
                    person_id=person_id,
                    assessment_item_id=item_id,
                    score=numeric_score,
                    status=status,
                    reason=entry_reason,
                    updated_by=user.id,
                )
                db.add(new_score)
                updated_count += 1
                add_gradebook_audit(
                    db, gradebook_id, "ScoreEntry", user,
                    reason=reason,
                    person_id=person_id,
                    person_name=person_name,
                    assessment_item_id=item_id,
                    assessment_label=item.label,
                    component_name=item.component.name if item.component else None,
                    new_value=f"{status}:{numeric_score}",
                )

    book.updated_at = datetime.utcnow()
    db.commit()
    return {"saved": True, "updated_count": updated_count}


def submit_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status != "Draft":
        raise ValueError(f"Can only submit Draft gradebooks (currently {book.status})")
    book.status = "Submitted"
    book.submitted_by = user.id
    book.submitted_by_name = user.full_name
    book.submitted_at = datetime.utcnow()
    add_gradebook_audit(db, book.id, "Submit", user, reason=reason)
    db.commit()
    return book


def incomplete_gradebook_message(full: dict) -> str:
    lines = ["Cannot finalize: the following grades are missing or incomplete."]
    active_item_ids = set()
    for component in full["components"]:
        items = [item for item in component["items"]
                 if item.get("active", True) or component["component_type"] == "Term Examinations"]
        active_item_ids.update(item["id"] for item in items)
        if not items:
            labels = ", ".join(item["label"] for item in component["items"])
            lines.append(f"{component['name']}: enter a score for at least one activity ({labels}).")

    for student in full["students"]:
        missing = []
        for component in full["components"]:
            for item in component["items"]:
                if item["id"] not in active_item_ids:
                    continue
                item_id = str(item["id"])
                score = student["scores"].get(item_id)
                status = student["score_statuses"].get(item_id, "Missing")
                try:
                    numeric_score = float(score)
                    valid_score = (status == "Scored" and math.isfinite(numeric_score)
                                   and 0 <= numeric_score <= float(item["max_score"]))
                except (TypeError, ValueError):
                    valid_score = False
                if not valid_score:
                    detail = "invalid score" if status == "Scored" else (
                        "score missing" if status in (None, "Missing") else f"{status} (score required)")
                    missing.append(f"{item['label']} ({detail})")
        if missing:
            lines.append(f"{student['full_name']}: {', '.join(missing)}")
    return "\n".join(lines)


def finalize_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status in {"Finalized", "Locked"}:
        return book

    full = get_gradebook_full(db, gradebook_id)
    if not full or not full["students"]:
        raise ValueError("Cannot finalize a class record without active students")
    if not full["components"] or abs(sum(component["weight"] for component in full["components"]) - 100.0) > 0.01:
        raise ValueError("Component weights must total 100% before finalizing")
    if full and full["statistics"]["incomplete"] > 0:
        error = ValueError(incomplete_gradebook_message(full))
        error.code = "INCOMPLETE_GRADEBOOK"
        raise error
    if book.learning_area:
        from .mapeh_learning_areas import partner_gradebook_issue
        issue = partner_gradebook_issue(db, book)
        if issue:
            raise ValueError(issue)

    book.status = "Finalized"
    book.finalized_by = user.id
    book.finalized_by_name = user.full_name
    book.finalized_at = datetime.utcnow()
    book.reopen_reason = None
    add_gradebook_audit(db, book.id, "Finalize", user, reason=reason)
    db.commit()
    return book


def lock_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status != "Finalized":
        raise ValueError("Only finalized gradebooks can be locked")
    book.status = "Locked"
    book.locked_by = user.id
    book.locked_by_name = user.full_name
    book.locked_at = datetime.utcnow()
    add_gradebook_audit(db, book.id, "Lock", user, reason=reason)
    db.commit()
    return book


def reopen_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status not in {"Finalized", "Submitted", "Locked"}:
        raise ValueError("Only finalized, submitted, or locked gradebooks can be reopened")
    if not reason or len(reason.strip()) < 8:
        raise ValueError("A specific reason (minimum 8 characters) is required to reopen")

    book.status = "Draft"
    book.reopened_by = user.id
    book.reopened_by_name = user.full_name
    book.reopened_at = datetime.utcnow()
    book.reopen_reason = reason.strip()
    add_gradebook_audit(db, book.id, "Reopen", user, reason=reason)
    db.commit()
    return book


def create_adjustment_request(
    db: Session,
    gradebook_id: int,
    user: User,
    person_id: int,
    assessment_item_id: int,
    new_score: float | None,
    new_status: str,
    reason: str,
) -> GradeAdjustmentRequest:
    book = _gradebook_for_update(db, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if user.role != 'teacher':
        raise ValueError('Only teachers can request grade adjustments')
    if book.status not in {'Finalized', 'Locked'}:
        raise ValueError('Grade adjustments are available for finalized or locked class records')
    item = db.get(AssessmentItem, assessment_item_id)
    if not item or item.component.gradebook_id != gradebook_id:
        raise ValueError('The assessment item does not belong to this gradebook')
    if person_id not in {person.id for person in db.scalars(gradebook_roster_query(book)).all()}:
        raise ValueError('The learner does not belong to this class record')
    if len(reason.strip()) < 8:
        raise ValueError('Provide a specific reason of at least 8 characters for the adjustment')
    new_score = validate_score_value(item, new_score, new_status)
    if new_status != 'Scored' or new_score is None:
        raise ValueError('A finalized class-record adjustment must include a numeric scored grade')

    score_rec = db.scalar(
        select(StudentScore).where(
            StudentScore.person_id == person_id,
            StudentScore.assessment_item_id == assessment_item_id,
        )
    )
    old_score = score_rec.score if score_rec else None
    old_status = score_rec.status if score_rec else "Missing"

    req = GradeAdjustmentRequest(
        gradebook_id=gradebook_id,
        person_id=person_id,
        assessment_item_id=assessment_item_id,
        old_score=old_score,
        old_status=old_status,
        new_score=new_score,
        new_status=new_status,
        reason=reason.strip(),
        requested_by=user.id,
        requested_by_name=user.full_name,
        status="Pending",
    )
    db.add(req)
    person = db.get(Person, person_id)
    add_gradebook_audit(
        db, gradebook_id, "AdjustmentRequested", user,
        reason=reason,
        person_id=person_id,
        person_name=person.full_name if person else None,
        assessment_item_id=assessment_item_id,
        assessment_label=item.label,
        old_value=f"{old_status}:{old_score}",
        new_value=f"{new_status}:{new_score}",
    )
    db.commit()
    return req


def create_criteria_adjustment_request(
    db: Session,
    gradebook_id: int,
    user: User,
    components: list[dict],
    reason: str,
) -> GradeCriteriaAdjustmentRequest:
    book = _gradebook_for_update(db, gradebook_id)
    if book and book.learning_area:
        raise ValueError('MAPEH learning-area criteria are fixed at 20/60/20.')
    if not book:
        raise ValueError("Gradebook not found")
    if user.role != "teacher":
        raise ValueError("Only teachers can request criteria adjustments")
    if book.status not in {"Finalized", "Locked"}:
        raise ValueError("Criteria adjustment requests are available for finalized or locked class records")
    if len(reason.strip()) < 8:
        raise ValueError("Provide a specific reason of at least 8 characters for the criteria adjustment")

    current = {component.id: component for component in book.components}
    if not current or len(components) != len(current):
        raise ValueError("A criteria request must include every existing assessment component")
    requested = {}
    for entry in components:
        component_id = entry.get("component_id")
        weight = float(entry.get("weight", -1))
        if component_id not in current or component_id in requested or not math.isfinite(weight) or not 0 <= weight <= 100:
            raise ValueError("Criteria requests must contain valid weights for the existing components only")
        requested[component_id] = weight
    if set(requested) != set(current) or abs(sum(requested.values()) - 100.0) > 0.01:
        raise ValueError("Requested assessment weights must include all components and total exactly 100%")
    old = [{"component_id": item.id, "name": item.name, "weight": item.weight} for item in book.components]
    new = [{"component_id": item.id, "name": item.name, "weight": requested[item.id]} for item in book.components]
    if all(math.isclose(current[component_id].weight, requested[component_id], abs_tol=0.001) for component_id in current):
        raise ValueError("The requested criteria are unchanged")

    req = GradeCriteriaAdjustmentRequest(
        gradebook_id=book.id,
        old_criteria_json=json.dumps(old),
        new_criteria_json=json.dumps(new),
        reason=reason.strip(),
        requested_by=user.id,
        requested_by_name=user.full_name,
    )
    db.add(req)
    add_gradebook_audit(db, book.id, "CriteriaAdjustmentRequested", user,
                        reason=reason.strip(), component_name="Assessment weights",
                        old_value=json.dumps(old), new_value=json.dumps(new))
    db.commit()
    return req


def review_criteria_adjustment_request(
    db: Session,
    request_id: int,
    user: User,
    status: str,
    note: str,
) -> GradeCriteriaAdjustmentRequest:
    req = db.scalar(select(GradeCriteriaAdjustmentRequest).where(
        GradeCriteriaAdjustmentRequest.id == request_id).with_for_update())
    if not req:
        raise ValueError("Criteria adjustment request not found")
    book = _gradebook_for_update(db, req.gradebook_id)
    if book and book.learning_area:
        raise ValueError('MAPEH learning-area criteria are fixed at 20/60/20.')
    if not book:
        raise ValueError("Gradebook not found")
    if req.status != "Pending":
        raise ValueError(f"Request is already {req.status}")
    requester = db.get(User, req.requested_by)
    if not requester or requester.role != "teacher":
        raise ValueError("Only teacher criteria requests can be reviewed")
    if status not in {"Approved", "Rejected"} or len(note.strip()) < 5:
        raise ValueError("Select Approve or Reject and enter a review note of at least 5 characters")

    old = json.loads(req.old_criteria_json)
    new = json.loads(req.new_criteria_json)
    if status == "Approved":
        if book.status not in {"Finalized", "Locked"}:
            raise ValueError("Only a finalized or locked class record can receive an approved criteria adjustment")
        current = {component.id: component for component in book.components}
        if set(current) != {entry["component_id"] for entry in old} or set(current) != {entry["component_id"] for entry in new}:
            raise ValueError("The assessment structure changed after this request. Reject it and submit a new request.")
        if any(not math.isclose(current[entry["component_id"]].weight, entry["weight"], abs_tol=0.001) for entry in old):
            raise ValueError("Assessment weights changed after this request. Reject it and submit a new request.")
        new_weights = [float(entry["weight"]) for entry in new]
        if any(not math.isfinite(weight) or not 0 <= weight <= 100 for weight in new_weights) or abs(sum(new_weights) - 100.0) > 0.01:
            raise ValueError("Requested assessment weights must total exactly 100%")

    req.status = status
    req.reviewed_by = user.id
    req.reviewed_by_name = user.full_name
    req.reviewed_at = datetime.utcnow()
    req.review_note = note.strip()
    req.requester_seen_at = None
    if status == "Approved":
        for entry in new:
            current[entry["component_id"]].weight = entry["weight"]
        book.updated_at = datetime.utcnow()
    add_gradebook_audit(db, book.id,
                        "CriteriaAdjustmentApproved" if status == "Approved" else "CriteriaAdjustmentRejected",
                        user, reason=note.strip(), component_name="Assessment weights",
                        old_value=req.old_criteria_json, new_value=req.new_criteria_json)
    db.commit()
    return req


def review_adjustment_request(
    db: Session,
    request_id: int,
    user: User,
    status: str,
    note: str,
) -> GradeAdjustmentRequest:
    req = db.get(GradeAdjustmentRequest, request_id)
    if not req:
        raise ValueError("Adjustment request not found")
    book = _gradebook_for_update(db, req.gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    req = db.scalar(
        select(GradeAdjustmentRequest)
        .where(GradeAdjustmentRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not req:
        raise ValueError("Adjustment request not found")
    if req.status != "Pending":
        raise ValueError(f"Request is already {req.status}")
    requester = db.get(User, req.requested_by)
    if not requester or requester.role != 'teacher':
        raise ValueError('Only teacher adjustment requests can be reviewed')
    if status not in {'Approved', 'Rejected'} or len(note.strip()) < 5:
        raise ValueError('Select Approve or Reject and enter a review note of at least 5 characters')
    score_rec = db.scalar(select(StudentScore).where(
        StudentScore.person_id == req.person_id,
        StudentScore.assessment_item_id == req.assessment_item_id))
    if status == 'Approved':
        item = db.get(AssessmentItem, req.assessment_item_id)
        if book.status not in {'Finalized', 'Locked'}:
            raise ValueError('Only a finalized or locked class record can receive an approved adjustment')
        if not item or item.component.gradebook_id != book.id:
            raise ValueError('The assessment item does not belong to this gradebook')
        if req.person_id not in {person.id for person in db.scalars(gradebook_roster_query(book)).all()}:
            raise ValueError('The learner does not belong to this class record')
        req.new_score = validate_score_value(item, req.new_score, req.new_status)
        if req.new_status != 'Scored' or req.new_score is None:
            raise ValueError('An approved adjustment must leave a numeric scored grade on a finalized class record')
        if (score_rec.score if score_rec else None, score_rec.status if score_rec else 'Missing') != (req.old_score, req.old_status):
            raise ValueError('This score changed after the request was submitted. Reject it and submit a new request for the current score.')

    req.status = status
    req.reviewed_by = user.id
    req.reviewed_by_name = user.full_name
    req.reviewed_at = datetime.utcnow()
    req.review_note = note.strip()
    req.requester_seen_at = None

    if status == "Approved":
        score_rec = db.scalar(
            select(StudentScore).where(
                StudentScore.person_id == req.person_id,
                StudentScore.assessment_item_id == req.assessment_item_id,
            )
        )
        if score_rec:
            score_rec.score = req.new_score
            score_rec.status = req.new_status
            score_rec.updated_by = user.id
            score_rec.updated_at = datetime.utcnow()
        else:
            db.add(StudentScore(
                person_id=req.person_id,
                assessment_item_id=req.assessment_item_id,
                score=req.new_score,
                status=req.new_status,
                updated_by=user.id,
            ))

        person = db.get(Person, req.person_id)
        item = db.get(AssessmentItem, req.assessment_item_id)
        add_gradebook_audit(
            db, req.gradebook_id, "AdjustmentApproved", user,
            reason=f"Adjustment approved: {note}",
            person_id=req.person_id,
            person_name=person.full_name if person else None,
            assessment_item_id=req.assessment_item_id,
            assessment_label=item.label if item else None,
            old_value=f"{req.old_status}:{req.old_score}",
            new_value=f"{req.new_status}:{req.new_score}",
        )
        book.updated_at = datetime.utcnow()
    else:
        add_gradebook_audit(db, req.gradebook_id, 'AdjustmentRejected', user, reason=note.strip(),
                           person_id=req.person_id, assessment_item_id=req.assessment_item_id)

    db.commit()
    return req


def delete_adjustment_request(db: Session, request_id: int, user: User) -> bool:
    req = db.get(GradeAdjustmentRequest, request_id)
    if not req:
        raise ValueError("Adjustment request not found")
    _gradebook_for_update(db, req.gradebook_id)
    if req.status != 'Pending':
        raise ValueError('Reviewed adjustment requests must be retained for the audit history')
    if user.role not in {"admin", "records_officer"} and req.requested_by != user.id:
        raise ValueError("You don't have permission to delete this request")
    
    db.delete(req)
    db.commit()
    return True


def delete_criteria_adjustment_request(db: Session, request_id: int, user: User) -> bool:
    req = db.get(GradeCriteriaAdjustmentRequest, request_id)
    if not req:
        raise ValueError("Criteria adjustment request not found")
    _gradebook_for_update(db, req.gradebook_id)
    if req.status != "Pending":
        raise ValueError("Reviewed adjustment requests must be retained for the audit history")
    if user.role not in {"admin", "records_officer"} and req.requested_by != user.id:
        raise ValueError("You don't have permission to delete this request")
    db.delete(req)
    db.commit()
    return True

# Legacy gradebook_summary (kept for old endpoints)
# ---------------------------------------------------------------------------

def gradebook_state(db: Session, class_key: str) -> GradebookState | None:
    return db.get(GradebookState, class_key)


def gradebook_summary(db: Session, class_key: str) -> dict:
    """Legacy summary function for old class_key-based endpoints."""
    components = db.scalars(
        select(GradeComponent).where(GradeComponent.class_key == class_key).order_by(GradeComponent.sequence)
    ).all()
    component_ids = [item.id for item in components]
    scores = db.scalars(select(GradeScore).where(GradeScore.component_id.in_(component_ids))).all() if component_ids else []
    score_map = {(item.person_id, item.component_id): item for item in scores}
    state = gradebook_state(db, class_key)
    rules = get_json(db, f"gradebook:{class_key}:rules", {})
    grade = state.grade if state else rules.get("grade", "")
    section = state.section if state else rules.get("section", "")
    people = db.scalars(select(Person).where(
        Person.role == "Student", Person.active.is_(True), Person.grade == grade, Person.section == section,
    ).order_by(Person.full_name, Person.external_id)).all() if grade and section else []

    manual = next((item for item in components if item.category == "Manual Overall"), None)
    weighted = [item for item in components if item.category != "Manual Overall"]
    rows = []
    for person in people:
        component_results: dict[str, dict] = {}
        completed = bool(weighted)
        initial = 0.0
        manual_score = score_map.get((person.id, manual.id)) if manual else None
        if manual_score and manual_score.status == "Scored":
            initial = (manual_score.score / manual.max_score) * 100
            component_results[manual.label] = {"score": manual_score.score, "max_score": manual.max_score,
                                                "status": manual_score.status, "percentage": initial}
        else:
            for component in weighted:
                record = score_map.get((person.id, component.id))
                status = record.status if record else "Missing"
                percentage = None
                if record and status == "Scored":
                    percentage = (record.score / component.max_score) * 100
                    initial += percentage * (component.weight / 100)
                else:
                    completed = False
                component_results[component.label] = {
                    "score": record.score if record and status == "Scored" else None,
                    "max_score": component.max_score,
                    "status": status,
                    "percentage": percentage,
                }
        transmuted = transmute_grade(initial) if completed or (manual_score and manual_score.status == "Scored") else None
        passing = state.passing_grade if state else int(rules.get("passing_grade", 75))
        rows.append({
            "person_id": person.id, "external_id": person.external_id, "lrn": person.lrn,
            "full_name": person.full_name, "components": component_results,
            "initial_grade": round(initial, 2) if transmuted is not None else None,
            "transmuted_grade": transmuted,
            "status": "Passed" if transmuted is not None and transmuted >= passing else "Below rule" if transmuted is not None else "Incomplete",
            "complete": transmuted is not None,
        })
    completed_grades = [item["transmuted_grade"] for item in rows if item["transmuted_grade"] is not None]
    distribution = defaultdict(int)
    for value in completed_grades:
        distribution["90-100" if value >= 90 else "85-89" if value >= 85 else "80-84" if value >= 80 else "75-79" if value >= 75 else "Below 75"] += 1
    metadata = {
        "class_key": class_key,
        "school_year": state.school_year if state else rules.get("school_year", ""),
        "term_order": state.term_order if state else rules.get("term_order", rules.get("quarter", 1)),
        "subject": state.subject if state else rules.get("subject", ""),
        "grade": grade,
        "section": section,
        "passing_grade": state.passing_grade if state else int(rules.get("passing_grade", 75)),
        "gradebook_status": state.status if state else "Draft",
        "finalized_at": state.finalized_at if state else None,
        "finalized_by_name": state.finalized_by_name if state else None,
    }
    statistics = {
        "learners": len(rows), "complete": len(completed_grades), "incomplete": len(rows) - len(completed_grades),
        "passed": sum(value >= metadata["passing_grade"] for value in completed_grades),
        "below_rule": sum(value < metadata["passing_grade"] for value in completed_grades),
        "average": round(sum(completed_grades) / len(completed_grades), 2) if completed_grades else None,
        "highest": max(completed_grades) if completed_grades else None,
        "lowest": min(completed_grades) if completed_grades else None,
        "distribution": dict(distribution),
    }
    return {"metadata": metadata, "components": components, "rows": rows, "statistics": statistics}
