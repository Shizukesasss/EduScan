"""Guarded renaming of pilot SHS sections and their denormalized references."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import ClassSchedule, GradeComponent, GradebookState, GradeLevel, Person, SchoolSection, SystemSetting
from ..models_grading import AssessmentItem, Gradebook, GradebookComponent, StudentScore


SHS_SECTION_NAMES = {
    ("Academic Track", "Arts, Social Sciences, and Humanities"): "Lualhati",
    ("Academic Track", "Science, Technology, Engineering, and Mathematics (STEM)"): "Mabini",
    ("Academic Track", "Sports, Health, and Wellness"): "Magiting",
    ("Academic Track", "Business and Entrepreneurship"): "Lakandula",
    ("Academic Track", "Field Experience"): "Malaya",
    ("Technical Professional (TechPro) Track", "Aesthetic, Wellness, and Human Care"): "Liwayway",
    ("Technical Professional (TechPro) Track", "Agri-Fishery Business and Food Innovation"): "Luntian",
    ("Technical Professional (TechPro) Track", "Artisanry and Creative Enterprise"): "Likha",
    ("Technical Professional (TechPro) Track", "Automotive and Small Engine Technologies"): "Lapu-Lapu",
    ("Technical Professional (TechPro) Track", "Construction and Building Technologies"): "Matibay",
    ("Technical Professional (TechPro) Track", "Creative Arts and Design Technologies"): "Hiraya",
    ("Technical Professional (TechPro) Track", "Hospitality and Tourism"): "Masigla",
    ("Technical Professional (TechPro) Track", "ICT Support and Computer Programming Technologies"): "Talino",
    ("Technical Professional (TechPro) Track", "Industrial Technologies"): "Masikap",
    ("Technical Professional (TechPro) Track", "Maritime"): "Mandaragat",
}
_TRACKS = {track.casefold() for track, _ in SHS_SECTION_NAMES}


def section_name_for(track: str, cluster: str) -> str:
    key = (str(track or "").strip().casefold(), str(cluster or "").strip().casefold())
    for (mapped_track, mapped_cluster), name in SHS_SECTION_NAMES.items():
        if key == (mapped_track.casefold(), mapped_cluster.casefold()):
            return name
    raise ValueError(f"No Filipino section name is mapped for {track!r} / {cluster!r}.")


def _grade_number(value: object) -> str | None:
    match = re.search(r"(?<!\d)(11|12)(?!\d)", str(value or ""))
    return match.group(1) if match else None


def _slug(value: str) -> str:
    return str(value or "").lower().replace(" ", "-")


def _gradebook_class_key(book: Gradebook, section_name: str) -> str:
    key = f"{book.school_year_name}-q{book.term_order}-{book.grade_name}-{section_name}-{book.subject_name}".lower().replace(" ", "-")
    if book.learning_area:
        key += f"--{book.learning_area}"
    return key


def _replace_section_in_key(class_key: str, old_name: str, new_name: str) -> str:
    old_part, new_part = _slug(old_name), _slug(new_name)
    if old_part == new_part:
        return class_key
    if class_key.count(old_part) != 1:
        raise ValueError(f"Class key {class_key!r} does not contain exactly one section name {old_name!r}.")
    return class_key.replace(old_part, new_part, 1)


def _assert_unique_targets(records: list[dict], *, key: str, entity: str) -> None:
    targets: dict[str, int] = {}
    for row in records:
        value = row[key]
        if value is None:
            continue
        if value in targets and targets[value] != row["id"]:
            raise ValueError(f"The SHS rename would give multiple {entity} records the same key {value!r}.")
        targets[value] = row["id"]


def build_rename_plan(db: Session, *, enforce_baseline: bool = True) -> dict:
    """Read and validate all records before any write transaction is opened."""
    section_rows = db.execute(
        select(SchoolSection, GradeLevel.name)
        .join(GradeLevel, GradeLevel.id == SchoolSection.grade_level_id)
        .where(SchoolSection.deleted_at.is_(None))
    ).all()
    candidates = []
    for section, grade_name in section_rows:
        grade = _grade_number(grade_name)
        if grade not in {"11", "12"} or not (section.track or "").strip():
            continue
        if (section.track or "").strip().casefold() not in _TRACKS:
            # Preserve legacy programs such as ABM; this migration covers the
            # current Academic and TechPro track values only.
            continue
        if not section.active:
            raise ValueError(f"Tracked SHS section {section.id} is inactive; inspect it before renaming.")
        desired = section_name_for(section.track, section.track_cluster)
        candidates.append({
            "id": section.id,
            "grade_level_id": section.grade_level_id,
            "grade": grade,
            "track": section.track,
            "cluster": section.track_cluster,
            "old_name": section.name,
            "new_name": desired,
        })

    if enforce_baseline and len(candidates) != 30:
        raise ValueError(f"Expected 30 active tracked SHS sections; found {len(candidates)}. No records were changed.")
    if not candidates:
        raise ValueError("No active tracked SHS sections were found.")
    group_counts: dict[tuple[str, str, str], int] = {}
    for row in candidates:
        key = (row["grade"], row["track"].casefold(), (row["cluster"] or "").strip().casefold())
        group_counts[key] = group_counts.get(key, 0) + 1
    if any(count != 1 for count in group_counts.values()):
        raise ValueError("A Grade 11/12 track and cluster has duplicate sections; no records were changed.")
    for track, cluster in SHS_SECTION_NAMES:
        if {grade for grade in ("11", "12") if (grade, track.casefold(), cluster.casefold()) in group_counts} != {"11", "12"}:
            raise ValueError(f"The active sections do not include both grades for {track} / {cluster}.")

    all_sections = db.scalars(select(SchoolSection)).all()
    section_by_id = {row["id"]: row for row in candidates}
    for row in candidates:
        folded_target = row["new_name"].strip().casefold()
        if any(other.id != row["id"] and other.grade_level_id == row["grade_level_id"]
               and other.name.strip().casefold() == folded_target for other in all_sections):
            raise ValueError(f"Section name {row['new_name']!r} already exists in Grade {row['grade']}.")

    people = db.scalars(select(Person).where(Person.role == "Student")).all()
    person_updates = []
    active_person_ids: set[int] = set()
    for person in people:
        grade = _grade_number(person.grade)
        if grade not in {"11", "12"} or not person.section:
            continue
        matches = [row for row in candidates if row["grade"] == grade and person.section.strip().casefold() in {
            row["old_name"].strip().casefold(), row["new_name"].strip().casefold(),
        }]
        if len(matches) > 1:
            raise ValueError(f"Learner {person.id} matches more than one tracked SHS section.")
        if not matches:
            continue
        section = matches[0]
        if person.active:
            active_person_ids.add(person.id)
        if person.section != section["new_name"]:
            person_updates.append({"id": person.id, "grade": person.grade,
                                   "old_section": person.section, "new_section": section["new_name"]})
    if enforce_baseline and len(active_person_ids) != 95:
        raise ValueError(f"Expected 95 active SHS learners across tracked sections; found {len(active_person_ids)}. No records were changed.")

    gradebooks = db.scalars(select(Gradebook).options(joinedload(Gradebook.section))).all()
    gradebook_updates = []
    for book in gradebooks:
        section = section_by_id.get(book.section_id)
        if not section:
            continue
        expected_old_key = _gradebook_class_key(book, section["old_name"])
        if book.class_key and book.class_key != expected_old_key:
            raise ValueError(f"Gradebook {book.id} has an unexpected class key; inspect it before renaming.")
        gradebook_updates.append({
            "id": book.id,
            "old_section_name": book.section_name,
            "new_section_name": section["new_name"],
            "old_class_key": book.class_key,
            "new_class_key": _gradebook_class_key(book, section["new_name"]) if book.class_key else None,
            "status": book.status,
            "section_id": book.section_id,
            "track": section["track"],
        })
    if enforce_baseline and len(gradebook_updates) != 13:
        raise ValueError(f"Expected 13 gradebooks for tracked SHS sections; found {len(gradebook_updates)}. No records were changed.")
    if enforce_baseline:
        business_book = next((book for book in gradebooks if book.id == 87), None)
        business_section = section_by_id.get(business_book.section_id) if business_book else None
        if (business_book is None or business_section is None
                or business_section["track"] != "Academic Track"
                or business_section["cluster"] != "Business and Entrepreneurship"
                or business_book.status != "Finalized"):
            raise ValueError("Gradebook 87 is not the expected finalized Academic Business and Entrepreneurship record.")
        from .grading import gradebook_roster_query
        if len(db.scalars(gradebook_roster_query(business_book)).all()) != 20:
            raise ValueError("Gradebook 87 no longer resolves its expected 20 learners.")

    all_gradebooks = {book.id: book for book in gradebooks}
    _assert_unique_targets(gradebook_updates, key="new_class_key", entity="gradebook")
    planned_book_keys = {row["new_class_key"]: row["id"] for row in gradebook_updates if row["new_class_key"]}
    for book in gradebooks:
        owner = planned_book_keys.get(book.class_key)
        if owner is not None and owner != book.id:
            raise ValueError(f"The new class key for gradebook {owner} conflicts with gradebook {book.id}.")

    schedules = db.scalars(select(ClassSchedule)).all()
    schedule_updates = []
    for schedule in schedules:
        grade = _grade_number(schedule.grade)
        if grade not in {"11", "12"} or not schedule.section:
            continue
        matches = [row for row in candidates if row["grade"] == grade and schedule.section.strip().casefold() in {
            row["old_name"].strip().casefold(), row["new_name"].strip().casefold(),
        }]
        if len(matches) > 1:
            raise ValueError(f"Class schedule {schedule.id} matches multiple SHS sections.")
        if matches and schedule.section != matches[0]["new_name"]:
            schedule_updates.append({"id": schedule.id, "grade": schedule.grade,
                                    "old_section": schedule.section, "new_section": matches[0]["new_name"]})

    states = db.scalars(select(GradebookState)).all()
    state_updates = []
    for state in states:
        grade = _grade_number(state.grade)
        if grade not in {"11", "12"} or not state.section:
            continue
        matches = [row for row in candidates if row["grade"] == grade and state.section.strip().casefold() in {
            row["old_name"].strip().casefold(), row["new_name"].strip().casefold(),
        }]
        if len(matches) > 1:
            raise ValueError(f"Legacy gradebook state {state.class_key!r} matches multiple SHS sections.")
        if matches:
            target = matches[0]["new_name"]
            new_key = _replace_section_in_key(state.class_key, state.section, target)
            if state.section != target or state.class_key != new_key:
                state_updates.append({"old_class_key": state.class_key, "new_class_key": new_key,
                                      "old_section": state.section, "new_section": target,
                                      "grade": state.grade})
    _assert_unique_targets([{"id": index, "new_class_key": row["new_class_key"]}
                            for index, row in enumerate(state_updates)], key="new_class_key", entity="legacy gradebook state")
    state_new_keys = {row["new_class_key"] for row in state_updates}
    for state in states:
        if state.class_key in state_new_keys and state.class_key not in {row["old_class_key"] for row in state_updates}:
            raise ValueError(f"A legacy gradebook state conflicts with the new class key {state.class_key!r}.")

    old_to_new_keys: dict[str, str] = {}
    for row in gradebook_updates:
        if row["old_class_key"] and row["new_class_key"]:
            old_to_new_keys[row["old_class_key"]] = row["new_class_key"]
    for row in state_updates:
        old_to_new_keys[row["old_class_key"]] = row["new_class_key"]

    legacy_components = db.scalars(select(GradeComponent)).all()
    component_updates = [{"id": component.id, "old_class_key": component.class_key,
                          "new_class_key": old_to_new_keys[component.class_key]}
                         for component in legacy_components if component.class_key in old_to_new_keys
                         and component.class_key != old_to_new_keys[component.class_key]]
    component_targets = {(row["new_class_key"], next(c.category for c in legacy_components if c.id == row["id"]),
                          next(c.sequence for c in legacy_components if c.id == row["id"])) for row in component_updates}
    component_target_ids = {row["id"] for row in component_updates}
    if any((c.class_key, c.category, c.sequence) in component_targets and c.id not in component_target_ids
           for c in legacy_components):
        raise ValueError("A legacy grade-component key would conflict with an existing grade component.")

    settings = db.scalars(select(SystemSetting)).all()
    setting_updates = []
    for setting in settings:
        for old_key, new_key in old_to_new_keys.items():
            prefix = f"gradebook:{old_key}:"
            if setting.key.startswith(prefix) and old_key != new_key:
                setting_updates.append({"old_key": setting.key, "new_key": f"gradebook:{new_key}:" + setting.key[len(prefix):]})
                break
    setting_old_keys = {row["old_key"] for row in setting_updates}
    existing_setting_keys = {setting.key for setting in settings}
    if any(row["new_key"] in existing_setting_keys - setting_old_keys for row in setting_updates):
        raise ValueError("A legacy gradebook setting would conflict with an existing setting key.")

    if enforce_baseline and not any(row["track"].casefold().startswith("technical") for row in gradebook_updates):
        raise ValueError("No TechPro gradebook is available for post-rename roster verification.")
    candidates.sort(key=lambda row: row["id"])
    person_updates.sort(key=lambda row: row["id"])
    gradebook_updates.sort(key=lambda row: row["id"])
    schedule_updates.sort(key=lambda row: row["id"])
    state_updates.sort(key=lambda row: row["old_class_key"])
    component_updates.sort(key=lambda row: row["id"])
    setting_updates.sort(key=lambda row: row["old_key"])
    return {
        "sections": candidates,
        "persons": person_updates,
        "gradebooks": gradebook_updates,
        "schedules": schedule_updates,
        "states": state_updates,
        "components": component_updates,
        "settings": setting_updates,
        "counts": {
            "sections": len(candidates), "gradebooks": len(gradebook_updates),
            "active_learners": len(active_person_ids), "persons_updated": len(person_updates),
            "schedules_updated": len(schedule_updates), "legacy_states_updated": len(state_updates),
            "legacy_components_updated": len(component_updates), "legacy_settings_renamed": len(setting_updates),
        },
    }


def _gradebook_snapshot(db: Session, gradebook_ids: list[int]) -> dict:
    from .grading import get_gradebook_full

    snapshot = {}
    for gradebook_id in gradebook_ids:
        full = get_gradebook_full(db, gradebook_id)
        if full is None:
            raise ValueError(f"Gradebook {gradebook_id} could not be loaded for preservation checks.")
        meta = full["gradebook"]
        learners = tuple(sorted((row["person_id"], row["initial_grade"], row["reported_grade"],
                                 tuple(sorted(row["scores"].items())),
                                 tuple(sorted(row["score_statuses"].items())))
                                for row in full["students"]))
        snapshot[gradebook_id] = {"status": meta["status"], "learners": learners}
    return snapshot


def _apply_plan(db: Session, plan: dict, *, reverse: bool = False) -> None:
    sections = {row.id: row for row in db.scalars(select(SchoolSection)).all()}
    people = {row.id: row for row in db.scalars(select(Person)).all()}
    books = {row.id: row for row in db.scalars(select(Gradebook)).all()}
    schedules = {row.id: row for row in db.scalars(select(ClassSchedule)).all()}
    states = {row.class_key: row for row in db.scalars(select(GradebookState)).all()}
    components = {row.id: row for row in db.scalars(select(GradeComponent)).all()}
    settings = {row.key: row for row in db.scalars(select(SystemSetting)).all()}

    for item in plan["sections"]:
        section = sections[item["id"]]
        section.name = item["old_name"] if reverse else item["new_name"]
    for item in plan["persons"]:
        people[item["id"]].section = item["old_section"] if reverse else item["new_section"]
    for item in plan["gradebooks"]:
        book = books[item["id"]]
        book.section_name = item["old_section_name"] if reverse else item["new_section_name"]
        book.class_key = item["old_class_key"] if reverse else item["new_class_key"]
    for item in plan["schedules"]:
        schedules[item["id"]].section = item["old_section"] if reverse else item["new_section"]
    for item in plan["states"]:
        old_key, new_key = item["old_class_key"], item["new_class_key"]
        state = states[new_key if reverse else old_key]
        state.class_key = old_key if reverse else new_key
        state.section = item["old_section"] if reverse else item["new_section"]
    for item in plan["components"]:
        components[item["id"]].class_key = item["old_class_key"] if reverse else item["new_class_key"]
    for item in plan["settings"]:
        old_key, new_key = item["old_key"], item["new_key"]
        setting = settings[new_key if reverse else old_key]
        setting.key = old_key if reverse else new_key
    db.flush()


def apply_rename_plan(db: Session, plan: dict) -> None:
    gradebook_ids = [row["id"] for row in plan["gradebooks"]]
    before = _gradebook_snapshot(db, gradebook_ids)
    from .grading import gradebook_roster_query
    roster_before = {book_id: tuple(person.id for person in db.scalars(gradebook_roster_query(db.get(Gradebook, book_id))).all())
                     for book_id in gradebook_ids}
    _apply_plan(db, plan)
    db.expire_all()
    after = _gradebook_snapshot(db, gradebook_ids)
    roster_after = {book_id: tuple(person.id for person in db.scalars(gradebook_roster_query(db.get(Gradebook, book_id))).all())
                    for book_id in gradebook_ids}
    if after != before:
        raise ValueError("A gradebook status, learner mark, or calculated grade changed during section renaming.")
    if roster_after != roster_before:
        raise ValueError("A gradebook no longer resolves the same learners after section renaming.")
    verify_plan = build_rename_plan(db)
    if verify_plan["counts"]["sections"] != 30 or verify_plan["counts"]["gradebooks"] != 13 or verify_plan["counts"]["active_learners"] != 95:
        raise ValueError("Post-rename saved-record counts differ from the approved baseline.")
    business = next((row for row in plan["gradebooks"] if row["id"] == 87), None)
    if business:
        if before[87]["status"] != "Finalized" or len(before[87]["learners"]) != 20:
            raise ValueError("Gradebook 87 no longer matches the approved 20-learner Finalized baseline.")
    techpro_ids = [row["id"] for row in plan["gradebooks"] if row["track"].casefold().startswith("technical")]
    if not any(roster_after[gradebook_id] for gradebook_id in techpro_ids):
        raise ValueError("No TechPro gradebook resolves learners after the rename.")


def write_manifest(path: Path, plan: dict, *, status: str = "prepared") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": 1,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "plan": "2026-10-31-shs-track-display-and-filipino-section-names",
        "plan_data": plan,
        "historical_grade_change_audits": "left unchanged",
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
