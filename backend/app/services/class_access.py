"""SQL predicates for class access through annual adviser and subject assignments."""

from sqlalchemy import JSON, case, cast, func, or_, select, type_coerce
from fastapi import HTTPException

from ..models import GradeLevel, Person, SchoolSection, SchoolYear, SectionAdviserAssignment, SubjectTeachingAssignment


def section_query(*columns):
    return select(*columns).select_from(SchoolSection).join(GradeLevel).where(
        SchoolSection.active.is_(True), SchoolSection.deleted_at.is_(None), GradeLevel.deleted_at.is_(None),
    )


def adviser_sections_for_year(teacher_id, year_id):
    return select(SectionAdviserAssignment.section_id).where(
        SectionAdviserAssignment.teacher_user_id == teacher_id,
        SectionAdviserAssignment.school_year_id == year_id,
    )


def adviser_assignment(teacher_id, year_id, section_id):
    return adviser_sections_for_year(teacher_id, year_id).where(SectionAdviserAssignment.section_id == section_id).exists()


def school_year_for_date(day):
    # An ambiguous or missing active year grants no advisory access.
    return select(case((func.count(SchoolYear.id) == 1, func.min(SchoolYear.id)))).where(
        SchoolYear.deleted_at.is_(None), SchoolYear.active.is_(True),
        SchoolYear.starts_on <= day, SchoolYear.ends_on >= day,
    ).correlate_except(SchoolYear).scalar_subquery()


def report_section_scope(teacher_id, advisory_years, teaching_years):
    adviser = select(SectionAdviserAssignment.section_id).where(
        SectionAdviserAssignment.teacher_user_id == teacher_id,
        SectionAdviserAssignment.school_year_id.in_(advisory_years),
    )
    teacher = select(SubjectTeachingAssignment.section_id).where(
        SubjectTeachingAssignment.teacher_user_id == teacher_id, SubjectTeachingAssignment.active.is_(True),
        SubjectTeachingAssignment.school_year_id.in_(teaching_years),
    )
    return or_(SchoolSection.id.in_(adviser), SchoolSection.id.in_(teacher))


def assigned_roster_sections(teacher_id, day=None):
    years = select(SchoolYear.id).where(SchoolYear.active.is_(True), SchoolYear.deleted_at.is_(None))
    if day is not None:
        years = years.where(SchoolYear.starts_on <= day, SchoolYear.ends_on >= day)
    return section_query(SchoolSection.id).where(GradeLevel.active.is_(True), report_section_scope(teacher_id, years, years))


def person_in_sections(sections):
    return sections.where(GradeLevel.name == Person.grade, SchoolSection.name == Person.section).correlate(Person).exists()


def advised_people(teacher_id, year_id):
    sections = section_query(SchoolSection.id).where(
        SchoolSection.id.in_(adviser_sections_for_year(teacher_id, year_id)),
    )
    return person_in_sections(sections)


def json_columns(db, column):
    # PostgreSQL needs a JSON operand for ->>, while SQLite extracts JSON from text.
    return cast(column, JSON) if db.get_bind().dialect.name == "postgresql" else type_coerce(column, JSON)


def scoped_record(db, query, scope, identity, detail):
    record = db.scalar(query.where(scope))
    if record is None and db.scalar(query.with_only_columns(identity)) is not None:
        raise HTTPException(403, detail)
    return record
