r"""Seed and verify a clearly marked, biometric-free November 2026 SF2 demo.

Run from backend with ``.venv\Scripts\python.exe tools\seed_sf2_demo.py`` to
preview, then add ``--apply`` to create the fixture and five report files.
Repeated --apply runs verify the existing fixture without duplicating records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import uuid
from datetime import date, time
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AttendanceCorrection, AttendanceResetAudit, GradeLevel, LearnerEnrollment,
    Person, SchoolSection, SchoolYear, User,
)
from app.schemas import PersonCreate  # noqa: E402
from app.services.attendance import is_instructional_day, rows_for_people  # noqa: E402
from app.services.sf2 import generate_sf2, generate_temporary_log  # noqa: E402


YEAR = 2026
MONTH = 11
SCHOOL_YEAR = "2026-2027"
GRADE = "7"
START = date(2026, 11, 1)
DAYS = (date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4))
SOURCE = "EduScan synthetic SF2 demo fixture"
NOTE = "SYNTHETIC DEMO STUDENT. Not a real school or biometric enrollment."
REPORT_DIR = Path(__file__).resolve().parents[2] / "demo-reports" / "2026-11"
SECTIONS = {
    "Demo Sampaguita": (
        ("Male", "Aguilar", "Mateo"),
        ("Male", "Bautista", "Enzo"),
        ("Male", "Dela Cruz", "Joaquin"),
        ("Male", "Mercado", "Liam"),
        ("Male", "Santos", "Rafael"),
        ("Female", "Aquino", "Isabella"),
        ("Female", "Castillo", "Bianca"),
        ("Female", "Flores", "Camille"),
        ("Female", "Ramos", "Julia"),
        ("Female", "Villanueva", "Sofia"),
    ),
    "Demo Rosal": (
        ("Male", "Alonzo", "Gabriel"),
        ("Male", "Domingo", "Lucas"),
        ("Male", "Garcia", "Adrian"),
        ("Male", "Navarro", "Marco"),
        ("Male", "Reyes", "Nathan"),
        ("Male", "Torres", "Paolo"),
        ("Female", "Cruz", "Andrea"),
        ("Female", "Evangelista", "Chloe"),
        ("Female", "Lim", "Elena"),
        ("Female", "Mendoza", "Maria"),
        ("Female", "Rivera", "Alyssa"),
        ("Female", "Tan", "Nicole"),
    ),
}


def planned_students(year_id: int) -> list[PersonCreate]:
    students = []
    for section_index, (section, names) in enumerate(SECTIONS.items(), start=1):
        for index, (sex, surname, first_name) in enumerate(names, start=1):
            students.append(PersonCreate(
                external_id=f"DEMO-SF2-202611-{section_index}-{index:02d}",
                lrn=None, surname=surname, first_name=first_name, sex=sex,
                date_of_birth=date(2012 + index % 2, (index % 12) + 1, 10 + index),
                role="Student", grade=GRADE, section=section,
                school_year_id=year_id, enrollment_start_date=START,
                enrollment_status="Regular", enrollment_note=NOTE,
                biometric_consent=False, guardian_phone=None,
            ))
    return students


def full_name(payload: PersonCreate) -> str:
    return f"{payload.surname}, {payload.first_name}"


def preflight(db):
    year = db.scalar(select(SchoolYear).where(SchoolYear.name == SCHOOL_YEAR,
                                               SchoolYear.deleted_at.is_(None)))
    grade = db.scalar(select(GradeLevel).where(GradeLevel.name == GRADE,
                                               GradeLevel.active.is_(True),
                                               GradeLevel.deleted_at.is_(None)))
    if not year or not year.active or not year.starts_on <= START <= year.ends_on or not grade:
        raise RuntimeError("The active 2026-2027 school year or Grade 7 is unavailable")
    if any(not is_instructional_day(db, day) for day in DAYS):
        raise RuntimeError("November 2–4 must be instructional days for this fixture")
    if db.scalar(select(AttendanceResetAudit.id).where(AttendanceResetAudit.attendance_date.in_(DAYS))):
        raise RuntimeError("A whole-school clean slate already exists on a demo date")
    planned = planned_students(year.id)
    ids = {item.external_id for item in planned}
    if len(ids) != len(planned):
        raise RuntimeError("Duplicate demo identifiers in the fixture")
    existing = db.scalars(select(Person).where(Person.external_id.in_(ids))).all()
    if existing and len(existing) != len(planned):
        raise RuntimeError("Only part of the demo fixture exists; no changes were made")
    other_names = {person.full_name.casefold() for person in db.scalars(
        select(Person).where(Person.external_id.not_in(ids))).all()}
    collisions = {full_name(item) for item in planned if full_name(item).casefold() in other_names}
    if collisions:
        raise RuntimeError(f"Demo names already belong to school records: {sorted(collisions)}")
    sections = {name: db.scalar(select(SchoolSection).where(
        SchoolSection.grade_level_id == grade.id, SchoolSection.name == name,
        SchoolSection.deleted_at.is_(None))) for name in SECTIONS}
    if not existing and any(sections.values()):
        raise RuntimeError("A demo section name is already in use; no changes were made")
    if existing and (not all(sections.values()) or any(not item.active for item in sections.values())):
        raise RuntimeError("An existing demo section is missing or inactive")
    admin = db.scalar(select(User).where(User.role == "admin", User.active.is_(True)).order_by(User.id))
    if not admin:
        raise RuntimeError("An active administrator account is required for placement references")
    return year, grade, planned, sections, admin, {person.external_id: person for person in existing}


def seed(db, year, grade, planned, sections, admin):
    for name in SECTIONS:
        section = SchoolSection(grade_level_id=grade.id, name=name, track="BEP", active=True)
        db.add(section)
        sections[name] = section
    db.flush()
    people = {}
    for item in planned:
        data = item.model_dump(exclude={"school_year_id"})
        person = Person(**data, full_name=full_name(item), active=True)
        db.add(person)
        people[item.external_id] = person
    db.flush()
    for item in planned:
        person = people[item.external_id]
        reference = f"{SOURCE}: {item.external_id}"
        db.add(LearnerEnrollment(
            person_id=person.id, school_year_id=year.id,
            grade_level_id=grade.id, section_id=sections[item.section].id,
            starts_on=START, source_reference=reference,
            source_sha256=hashlib.sha256(reference.encode()).hexdigest(),
            imported_by=admin.id, imported_by_name=SOURCE,
        ))
        for day in DAYS:
            present = day != DAYS[-1]
            offset = int(item.external_id[-2:])
            db.add(AttendanceCorrection(
                id=str(uuid.uuid4()),
                person_id=person.id, attendance_date=day,
                status="Present" if present else "Absent",
                time_in=time(7, 10 + offset) if present else None,
                time_out=time(15, 20 + offset) if present else None,
                reason=f"{SOURCE}; simulated {day.isoformat()} attendance, not an observed visit.",
                actor_user_id=admin.id, actor_name=SOURCE, actor_role="admin",
                before_json=json.dumps({"status": "No scan", "fixture": True}),
            ))
    db.flush()
    return people


def verify(db, planned, people):
    expected = {item.external_id: item for item in planned}
    if set(people) != set(expected):
        raise RuntimeError("Demo student identifiers differ from the plan")
    for external_id, person in people.items():
        item = expected[external_id]
        if (person.full_name, person.sex, person.grade, person.section, person.biometric_consent,
                person.enrollment_note) != (full_name(item), item.sex, GRADE, item.section, False, NOTE):
            raise RuntimeError(f"Demo school record differs from the plan: {external_id}")
        corrections = db.scalars(select(AttendanceCorrection).where(
            AttendanceCorrection.person_id == person.id,
            AttendanceCorrection.attendance_date.in_(DAYS),
            AttendanceCorrection.actor_name == SOURCE)).all()
        if len(corrections) != 3:
            raise RuntimeError(f"Expected three synthetic attendance rows for {external_id}")
    for day in DAYS:
        rows = {row["external_id"]: row for row in rows_for_people(db, list(people.values()), day)}
        expected_status = "Absent" if day == DAYS[-1] else "Present"
        if set(rows) != set(expected) or any(row["status"] != expected_status for row in rows.values()):
            raise RuntimeError(f"Incorrect demo attendance on {day}")


def generate_and_check(db, planned, generated):
    for section, names in SECTIONS.items():
        path = generate_sf2(db, YEAR, MONTH, GRADE, section, "DEMO", SCHOOL_YEAR,
                            "SAN JOSE NATIONAL HIGH SCHOOL")
        generated.append((path, f"SF2-2026-11-Grade-7-{section.replace(' ', '-')}.xlsx"))
        expected = [item for item in planned if item.section == section]
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook["School Form 2 (SF2)"]
            for sex, start_row, end_row, count_row in (("Male", 14, 34, 35), ("Female", 36, 60, 61)):
                group = sorted((full_name(item).upper() for item in expected if item.sex == sex))
                observed = [sheet.cell(row, 2).value for row in range(start_row, end_row + 1)]
                observed = [value for value in observed if value]
                if observed != group:
                    raise RuntimeError(f"{section}: {sex} names are not alphabetized in SF2")
                if [sheet.cell(count_row, column).value for column in (4, 5, 6)] != [len(group), len(group), 0]:
                    raise RuntimeError(f"{section}: {sex} daily totals are incorrect")
                for row in range(start_row, start_row + len(group)):
                    if [sheet.cell(row, column).value for column in (4, 5, 6)] != ["✓", "✓", "X"]:
                        raise RuntimeError(f"{section}: expected check, check, X on November 2–4")
            if [sheet.cell(62, column).value for column in (4, 5, 6)] != [len(expected), len(expected), 0]:
                raise RuntimeError(f"{section}: total attendance is incorrect")
        finally:
            workbook.close()
    for day in DAYS:
        path = generate_temporary_log(db, day, snapshot=True)
        generated.append((path, f"Attendance-{day.isoformat()}-All-School.xlsx"))
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook["All-School Attendance"]
            rows = {row[1]: row for row in sheet.iter_rows(min_row=2, values_only=True)
                    if isinstance(row[1], str) and row[1].startswith("DEMO-SF2-202611-")}
            status = "Absent" if day == DAYS[-1] else "Present"
            if len(rows) != len(planned) or any(row[14] != status for row in rows.values()):
                raise RuntimeError(f"All-school daily file is incorrect for {day}")
        finally:
            workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert demo records and generate reports")
    args = parser.parse_args()
    generated = []
    try:
        with SessionLocal.begin() as db:
            if args.apply and db.get_bind().dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(20261101)"))
            year, grade, planned, sections, admin, people = preflight(db)
            print(f"Demo plan: {len(planned)} fictional Grade 7 students in {', '.join(SECTIONS)}")
            print("November 2-3: Present with synthetic times; November 4: Absent")
            print("No faces, guardian numbers, SMS, or existing school records are changed")
            if not args.apply:
                print("Dry run only. Add --apply to seed the database and generate reports.")
                return
            if not people:
                people = seed(db, year, grade, planned, sections, admin)
                print("Created synthetic school records and attendance corrections")
            else:
                print("Existing complete fixture found; no new database rows created")
            verify(db, planned, people)
            generate_and_check(db, planned, generated)
    except Exception:
        for path, _name in generated:
            path.unlink(missing_ok=True)
        raise
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for path, name in generated:
        destination = REPORT_DIR / name
        shutil.copy2(path, destination)
        print(destination)
    print("Verified two distinct SF2 rosters, male/female order, daily marks, and three all-school logs")


if __name__ == "__main__":
    main()
