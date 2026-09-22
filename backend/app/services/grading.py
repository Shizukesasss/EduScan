"""Grading service layer for EduScan.

This module bridges the database models and the stateless grading engine.
It queries data from the ORM, converts it to plain dicts for the engine,
and writes results back.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import (
    GradeLevel, GradingPeriod, Person, SchoolSection, SchoolYear, Subject, User,
)
from ..models_grading import (
    AssessmentItem, Gradebook, GradebookAuditEntry, GradebookComponent,
    GradeAdjustmentRequest, GradingPolicy, StudentScore,
)
from .grading_engine import (
    DEFAULT_TRANSMUTATION_TABLE, apply_transmutation, build_default_transmutation_table,
    calculate_student_grade, generate_calculation_breakdown, round_value,
    validate_gradebook as engine_validate,
)
from .settings_store import get_json

# --- Legacy compatibility imports (kept for old endpoints) ---
from ..models import GradeComponent, GradeScore, GradebookState


def transmute_grade(initial_grade: float) -> int:
    """Legacy transmutation using the piecewise formula.
    Kept for backward compatibility with old class_key endpoints.
    """
    return apply_transmutation(initial_grade) or 60


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

    for policy in policies:
        grade_levels = [g.strip() for g in policy.grade_levels.split(",") if g.strip()]
        if grade_levels and grade_level_name not in grade_levels:
            continue
        if policy.subject_category != "General" and policy.subject_category != subject_category:
            continue
        return policy

    # Fallback: any active policy for this school year
    return policies[0] if policies else None


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
        return defs if isinstance(defs, list) else []
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


def get_gradebook_full(db: Session, gradebook_id: int) -> dict | None:
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
    students = db.scalars(
        select(Person).where(
            Person.role == "Student", Person.active.is_(True),
            Person.grade == book.grade_name, Person.section == book.section_name,
        ).order_by(Person.full_name, Person.external_id)
    ).all()

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

    # Load all scores for these items
    scores = db.scalars(
        select(StudentScore).where(StudentScore.assessment_item_id.in_(all_item_ids))
    ).all() if all_item_ids else []

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

    # Determine active items: an item is active if at least one student has a non-empty score or explicit status.
    active_item_ids = set()
    for s_id, s_scores in scores_by_person.items():
        for s in s_scores:
            if s["score"] is not None or s["status"] != "Missing":
                active_item_ids.add(s["item_id"])

    # Calculate grades for each student
    student_rows = []
    completed_grades = []
    for student in students:
        student_score_list = scores_by_person.get(student.id, [])
        
        filtered_items = {}
        for comp_id, items in items_by_component.items():
            filtered_items[comp_id] = [it for it in items if it["id"] in active_item_ids]
            
        filtered_components = []
        for c in components_data:
            c_copy = c.copy()
            c_copy["items"] = [it for it in c_copy.get("items", []) if it["id"] in active_item_ids]
            filtered_components.append(c_copy)

        calc = calculate_student_grade(
            student_scores=student_score_list,
            components=filtered_components,
            items_by_component=filtered_items,
            transmutation_table=trans_table,
            passing_grade=book.passing_grade,
            rounding_decimal_places=rounding_dp,
            rounding_final_decimal_places=rounding_final_dp,
            rounding_method=rounding_method,
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
            "school_year_name": book.school_year_name,
            "quarter": book.quarter,
            "grade_name": book.grade_name,
            "section_name": book.section_name,
            "subject_name": book.subject_name,
            "teacher_name": book.teacher_name,
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
        "students": student_rows,
        "statistics": statistics,
    }


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
    return generate_calculation_breakdown(
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
) -> Gradebook:
    sy = db.get(SchoolYear, school_year_id)
    gp = db.get(GradingPeriod, grading_period_id)
    gl = db.get(GradeLevel, grade_level_id)
    sec = db.get(SchoolSection, section_id)
    subj = db.get(Subject, subject_id)

    if not all([sy, gp, gl, sec, subj]):
        raise ValueError("Invalid academic structure references")

    class_key = f"{sy.name}-q{gp.quarter}-{gl.name}-{sec.name}-{subj.name}".lower().replace(" ", "-")

    book = db.scalars(
        select(Gradebook).where(
            (
                (Gradebook.school_year_id == school_year_id) &
                (Gradebook.grading_period_id == grading_period_id) &
                (Gradebook.grade_level_id == grade_level_id) &
                (Gradebook.section_id == section_id) &
                (Gradebook.subject_id == subject_id)
            ) | (Gradebook.class_key == class_key)
        )
    ).first()

    if book:
        # Update references if they changed (e.g. subject recreated)
        book.school_year_id = school_year_id
        book.grading_period_id = grading_period_id
        book.grade_level_id = grade_level_id
        book.section_id = section_id
        book.subject_id = subject_id

        # Sync teacher_name / teacher_user_id from the section's assigned adviser.
        # This prevents a stale "System Administrator" name from appearing when an
        # admin first opened the page and created the record, but the class is actually
        # managed by the teacher linked as section adviser.
        sec_for_sync = db.get(SchoolSection, section_id)
        if sec_for_sync:
            if sec_for_sync.adviser_user_id:
                # Section has an explicit adviser account linked — always use that.
                adviser = db.get(User, sec_for_sync.adviser_user_id)
                if adviser:
                    book.teacher_user_id = adviser.id
                    book.teacher_name = adviser.full_name
            elif user.role == "teacher":
                # No explicit adviser link; use the currently logged-in teacher.
                book.teacher_user_id = user.id
                book.teacher_name = user.full_name
            # If admin opened it and no adviser is assigned, leave as-is to avoid noise.
        db.commit()
        return book

    policy = None
    if grading_policy_id:
        policy = db.get(GradingPolicy, grading_policy_id)
    if not policy:
        policy = get_active_policy_for(db, sy.name, gl.name)

    class_key = f"{sy.name}-q{gp.quarter}-{gl.name}-{sec.name}-{subj.name}".lower().replace(" ", "-")

    book = Gradebook(
        school_year_id=school_year_id,
        grading_period_id=grading_period_id,
        grade_level_id=grade_level_id,
        section_id=section_id,
        subject_id=subject_id,
        grading_policy_id=policy.id if policy else None,
        teacher_user_id=user.id if user.role == "teacher" else None,
        school_year_name=sy.name,
        quarter=gp.quarter,
        grade_name=gl.name,
        section_name=sec.name,
        subject_name=subj.name,
        teacher_name=user.full_name,
        class_key=class_key,
        status="Draft",
        passing_grade=policy.passing_grade if policy else 75,
    )
    db.add(book)
    db.flush()

    comp_defs = policy_component_definitions(policy)
    if comp_defs:
        for seq, cdef in enumerate(comp_defs):
            comp = GradebookComponent(
                gradebook_id=book.id,
                name=cdef.get("name", f"Component {seq + 1}"),
                component_type=cdef.get("component_type", "Written Work"),
                weight=float(cdef.get("weight", 0.0)),
                sequence=seq,
                description=cdef.get("description", ""),
            )
            db.add(comp)
            db.flush()
            item_count = 1 if "Quarterly Assessment" in comp.name else 5
            for i in range(item_count):
                item = AssessmentItem(
                    component_id=comp.id,
                    label=f"{comp.name} {i + 1}" if item_count > 1 else comp.name,
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
    db.commit()
    return book


def update_gradebook_components(
    db: Session,
    gradebook_id: int,
    user: User,
    components_payload: list[dict],
    reason: str,
) -> Gradebook:
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status in {"Finalized", "Locked"}:
        raise ValueError(f"Cannot edit components in {book.status} gradebook")

    total_weight = sum(float(c.get("weight", 0)) for c in components_payload)
    if abs(total_weight - 100.0) > 0.01:
        raise ValueError(f"Component weights must total exactly 100% (currently {total_weight:.2f}%)")

    existing_comps = {c.id: c for c in book.components}
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
    book = db.get(Gradebook, gradebook_id)
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

    updated_count = 0
    for person_id_str, entry_list in scores_dict.items():
        person_id = int(person_id_str)
        person = db.get(Person, person_id)
        person_name = person.full_name if person else None

        for entry in entry_list:
            item_id = entry.get("assessment_item_id")
            if item_id not in item_map:
                continue
            item = item_map[item_id]
            raw_score = entry.get("score")
            status = entry.get("status", "Scored")
            entry_reason = entry.get("reason")

            numeric_score = None
            if status == "Scored":
                if raw_score is None:
                    raise ValueError(f"Score required for item '{item.label}' with status 'Scored'")
                numeric_score = float(raw_score)
                if numeric_score < 0 or numeric_score > item.max_score:
                    raise ValueError(f"Score {numeric_score} out of bounds (0 - {item.max_score}) for {item.label}")

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
    book = db.get(Gradebook, gradebook_id)
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


def finalize_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    if book.status in {"Finalized", "Locked"}:
        return book

    full = get_gradebook_full(db, gradebook_id)
    if full and full["statistics"]["incomplete"] > 0:
        inc = full["statistics"]["incomplete"]
        raise ValueError(f"{inc} learner(s) still have missing or incomplete scores")

    book.status = "Finalized"
    book.finalized_by = user.id
    book.finalized_by_name = user.full_name
    book.finalized_at = datetime.utcnow()
    book.reopen_reason = None
    add_gradebook_audit(db, book.id, "Finalize", user, reason=reason)
    db.commit()
    return book


def lock_gradebook(db: Session, gradebook_id: int, user: User, reason: str) -> Gradebook:
    book = db.get(Gradebook, gradebook_id)
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
    book = db.get(Gradebook, gradebook_id)
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
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise ValueError("Gradebook not found")
    item = db.get(AssessmentItem, assessment_item_id)
    if not item:
        raise ValueError("Assessment item not found")

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
    if req.status != "Pending":
        raise ValueError(f"Request is already {req.status}")

    req.status = status
    req.reviewed_by = user.id
    req.reviewed_by_name = user.full_name
    req.reviewed_at = datetime.utcnow()
    req.review_note = note.strip()

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

    db.commit()
    return req


def delete_adjustment_request(db: Session, request_id: int, user: User) -> bool:
    req = db.get(GradeAdjustmentRequest, request_id)
    if not req:
        raise ValueError("Adjustment request not found")
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
        completed = True
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
        "quarter": state.quarter if state else rules.get("quarter", 1),
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
