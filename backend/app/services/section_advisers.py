"""School-year-specific adviser lookups; these functions never commit."""
from sqlalchemy import select
from ..models import SchoolYear, SchoolSection, SectionAdviserAssignment, User


def current_school_year_id(db, on_date=None):
    from datetime import date
    day = on_date or date.today()
    years = db.scalars(select(SchoolYear.id).where(SchoolYear.deleted_at.is_(None),
        SchoolYear.active.is_(True), SchoolYear.starts_on <= day, SchoolYear.ends_on >= day)).all()
    return years[0] if len(years) == 1 else None


def advised_section_ids(db, teacher_id, school_year_id=None):
    year_id = school_year_id or current_school_year_id(db)
    if year_id is None:
        return set()
    return set(db.scalars(select(SectionAdviserAssignment.section_id).where(
        SectionAdviserAssignment.school_year_id == year_id,
        SectionAdviserAssignment.teacher_user_id == teacher_id)).all())


def adviser_for_section(db, school_year_id, section_id):
    return db.scalar(select(User).join(SectionAdviserAssignment,
        SectionAdviserAssignment.teacher_user_id == User.id).where(
        SectionAdviserAssignment.school_year_id == school_year_id,
        SectionAdviserAssignment.section_id == section_id))


def assign_section_adviser(db, school_year_id, section_id, teacher_user_id):
    year = db.scalar(select(SchoolYear).where(SchoolYear.id == school_year_id).with_for_update())
    section = db.get(SchoolSection, section_id)
    if not year or year.deleted_at is not None or not year.active:
        raise ValueError('Select an active school year')
    if not section or section.deleted_at is not None or not section.active:
        raise ValueError('Select an active section')
    current = db.scalar(select(SectionAdviserAssignment).where(
        SectionAdviserAssignment.school_year_id == school_year_id,
        SectionAdviserAssignment.section_id == section_id))
    if teacher_user_id is None:
        if current:
            db.delete(current)
            db.flush()
        return None
    teacher = db.get(User, teacher_user_id)
    if not teacher or teacher.role != 'teacher' or not teacher.active:
        raise ValueError('Select an active teacher account')
    conflict = db.scalar(select(SectionAdviserAssignment.id).where(
        SectionAdviserAssignment.school_year_id == school_year_id,
        SectionAdviserAssignment.teacher_user_id == teacher_user_id,
        SectionAdviserAssignment.section_id != section_id))
    if conflict:
        raise ValueError('A teacher can advise only one section per school year')
    if current:
        current.teacher_user_id = teacher_user_id
    else:
        current = SectionAdviserAssignment(school_year_id=school_year_id,
            section_id=section_id, teacher_user_id=teacher_user_id)
        db.add(current)
    db.flush()
    return current
