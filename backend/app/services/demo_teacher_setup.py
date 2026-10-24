"""Preview first, then atomically create attributable demonstration accounts."""
import hashlib
import json
import secrets
from collections import defaultdict
from sqlalchemy import select
from ..auth import hash_password
from ..models import (User, SchoolYear, SchoolSection, Subject, GradeLevel, SubjectTeachingAssignment,
                      SectionAdviserAssignment, DemoTeacherSetupBatch)
from .academic_context import is_junior_high, subject_matches_grade, elective_track_for_subject, normalize_grade_name
from .section_advisers import assign_section_adviser
from .audit import add_audit
from ..models_grading import Gradebook


def _admin(actor):
    if actor.role != 'admin':
        raise PermissionError('Only administrators can set up demonstration teachers')


def _state(db, year_id):
    state = {}
    for model, columns in (
        (User, ('id', 'username', 'full_name', 'role', 'active', 'is_demo')),
        (GradeLevel, ('id', 'name', 'active', 'deleted_at')),
        (SchoolYear, ('id', 'name', 'active', 'deleted_at')),
        (SchoolSection, ('id', 'grade_level_id', 'name', 'track', 'active', 'deleted_at')),
        (Subject, ('id', 'name', 'category', 'is_elective', 'elective_track', 'allowed_grades_json', 'active', 'deleted_at')),
        (SubjectTeachingAssignment, ('id', 'school_year_id', 'subject_id', 'section_id', 'teacher_user_id', 'active')),
        (SectionAdviserAssignment, ('id', 'school_year_id', 'section_id', 'teacher_user_id')),
        (Gradebook, ('id', 'school_year_id', 'section_id', 'subject_id', 'teacher_user_id', 'status')),
    ):
        query = select(model).order_by(model.id)
        if model in (SubjectTeachingAssignment, SectionAdviserAssignment, Gradebook):
            query = query.where(model.school_year_id == year_id)
        state[model.__tablename__] = [[getattr(row, key) for key in columns] for row in db.scalars(query).all()]
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def _name_teachers(db, proposals):
    first_names = ('Lisa', 'Jennie', 'Rose', 'Jisoo', 'Maya', 'Adrian', 'Isabel', 'Gabriel', 'Sofia', 'Daniel', 'Clara', 'Ethan')
    surnames = ('Manoban', 'Kim', 'Park', 'Rivera', 'Reyes', 'Santos', 'Navarro', 'Torres', 'Cruz', 'Garcia', 'Flores', 'Ramos')
    used_names = {u.full_name.casefold() for u in db.scalars(select(User)).all()}
    used_usernames = {name.casefold() for name in db.scalars(select(User.username)).all()}
    for index, proposal in enumerate(proposals):
        name = next((f'{first} {last}' for first in first_names for last in surnames if f'{first} {last}'.casefold() not in used_names), None)
        if name is None:
            raise ValueError('The demonstration name pool is exhausted; reduce the selected sections.')
        used_names.add(name.casefold())
        username = 'demo.' + name.lower().replace(' ', '.')
        base, suffix = username, 2
        while username.casefold() in used_usernames:
            username = f'{base}.{suffix}'
            suffix += 1
        used_usernames.add(username.casefold())
        proposal.update(key=str(index), full_name=name, username=username, is_demo=True)


def preview_demo_teacher_setup(db, school_year_id, section_ids, actor):
    _admin(actor)
    year = db.get(SchoolYear, school_year_id)
    if not year or not year.active or year.deleted_at:
        raise ValueError('Choose an active school year')
    wanted = set(section_ids)
    if not wanted:
        raise ValueError('Choose at least one JHS section')
    sections = db.scalars(select(SchoolSection).where(SchoolSection.id.in_(wanted)).order_by(SchoolSection.id)).all()
    if len(sections) != len(wanted) or any(not s.active or s.deleted_at or not s.grade_level.active or s.grade_level.deleted_at or not is_junior_high(s.grade_level.name) for s in sections):
        raise ValueError('Choose active JHS sections only')
    subjects = db.scalars(select(Subject).where(Subject.active.is_(True), Subject.deleted_at.is_(None)).order_by(Subject.id)).all()
    assigned = {(a.section_id, a.subject_id) for a in db.scalars(select(SubjectTeachingAssignment).where(SubjectTeachingAssignment.school_year_id == year.id, SubjectTeachingAssignment.active.is_(True))).all()}
    reserved = {(a.section_id, a.subject_id) for a in db.scalars(select(SubjectTeachingAssignment).where(SubjectTeachingAssignment.school_year_id == year.id)).all()}
    reserved.update((book.section_id, book.subject_id) for book in db.scalars(select(Gradebook).where(Gradebook.school_year_id == year.id, Gradebook.teacher_user_id.is_not(None))).all())
    advised = {a.section_id for a in db.scalars(select(SectionAdviserAssignment).where(SectionAdviserAssignment.school_year_id == year.id)).all()}
    groups = defaultdict(list)
    section_map = {s.id: s for s in sections}
    subject_map = {s.id: s for s in subjects}
    for section in sections:
        for subject in subjects:
            track = elective_track_for_subject(subject.category, subject.is_elective, subject.elective_track)
            if subject_matches_grade(subject, section.grade_level.name) and (not track or track.casefold() == (section.track or '').casefold()) and (section.id, subject.id) not in reserved:
                groups[(section.grade_level_id, subject.id)].append(section.id)
    proposals = [dict(grade_level_id=grade, subject_id=subject, section_ids=ids, adviser_section_id=None) for (grade, subject), ids in sorted(groups.items())]
    unresolved = []
    for section in sections:
        if section.id in advised:
            continue
        candidate = next((p for p in proposals if section.id in p['section_ids'] and p['adviser_section_id'] is None), None)
        if candidate is None:
            split = next((p for p in proposals if section.id in p['section_ids'] and len(p['section_ids']) > 1), None)
            if split:
                split['section_ids'].remove(section.id)
                candidate = dict(grade_level_id=split['grade_level_id'], subject_id=split['subject_id'], section_ids=[section.id], adviser_section_id=None)
                proposals.append(candidate)
        if candidate:
            candidate['adviser_section_id'] = section.id
        else:
            unresolved.append({'section_id': section.id, 'section': section.name, 'reason': 'No missing eligible teaching slot remains for a new demo adviser. Existing assignments were preserved.'})
    _name_teachers(db, proposals)
    for proposal in proposals:
        proposal.update(
                        subject=subject_map[proposal['subject_id']].name,
                        grade=section_map[proposal['section_ids'][0]].grade_level.name,
                        sections=[section_map[i].name for i in proposal['section_ids']],
                        adviser_section=section_map[proposal['adviser_section_id']].name if proposal['adviser_section_id'] else None)
    proposal = {'school_year_id': year.id, 'school_year': year.name, 'section_ids': sorted(wanted), 'teachers': proposals, 'unresolved': unresolved,
                'preserved_teaching_assignments': sum(section_id in wanted for section_id, _ in assigned), 'preserved_adviser_assignments': len(advised & wanted)}
    batch = DemoTeacherSetupBatch(id=secrets.token_hex(16), school_year_id=year.id, created_by=actor.id,
        proposal_json=json.dumps(proposal), state_digest=_state(db, year.id))
    db.add(batch)
    db.commit()
    return {'batch_id': batch.id, **proposal}


ADVISORY_SUBJECTS = (
    ('Filipino', {'filipino'}),
    ('Science', {'science'}),
    ('Values Education', {'values education', 've'}),
    ('TLE', {'tle', 'technology and livelihood education'}),
    ('MAPEH', {'mapeh'}),
    ('Araling Panlipunan', {'araling panlipunan'}),
)


def _existing_advisory_setup(db, year_id):
    batches = db.scalars(select(DemoTeacherSetupBatch).where(
        DemoTeacherSetupBatch.school_year_id == year_id,
        DemoTeacherSetupBatch.applied.is_(True)).order_by(DemoTeacherSetupBatch.id)).all()
    for batch in batches:
        if json.loads(batch.proposal_json).get('kind') == 'six_advisory':
            return {**json.loads(batch.result_json), 'already_applied': True, 'credentials': []}
    return None


def preview_demo_advisory_setup(db, school_year_id, actor):
    _admin(actor)
    year = db.scalar(select(SchoolYear).where(SchoolYear.id == school_year_id).with_for_update())
    if not year or not year.active or year.deleted_at:
        raise ValueError('Choose an active school year')
    existing = _existing_advisory_setup(db, year.id)
    if existing:
        db.commit()
        return {**existing, 'kind': 'six_advisory', 'school_year': year.name}
    grades = [grade for grade in db.scalars(select(GradeLevel)).all()
              if grade.active and not grade.deleted_at and normalize_grade_name(grade.name) == '7']
    if len(grades) != 1:
        raise ValueError('Exactly one active Grade 7 is required for the demo classes')
    grade = grades[0]
    subjects = db.scalars(select(Subject).where(Subject.active.is_(True), Subject.deleted_at.is_(None))).all()
    proposals = []
    for label, aliases in ADVISORY_SUBJECTS:
        matches = [subject for subject in subjects if ' '.join(subject.name.casefold().split()) in aliases]
        if len(matches) != 1 or matches[0].category.strip().upper() != 'JHS' or matches[0].is_elective or not subject_matches_grade(matches[0], grade.name):
            raise ValueError(f'Choose exactly one active JHS core subject for {label}')
        section_name = f'Demo {label} {year.name}'
        if len(section_name) > 80 or db.scalar(select(SchoolSection.id).where(
                SchoolSection.grade_level_id == grade.id, SchoolSection.name == section_name)):
            raise ValueError(f'The section {section_name} already exists or its name is too long; review it manually')
        proposals.append(dict(grade_level_id=grade.id, grade='7', program='BEP', subject_id=matches[0].id,
            subject=matches[0].name, new_section_name=section_name, sections=[section_name],
            adviser_section=section_name, section_ids=[], adviser_section_id=None))
    _name_teachers(db, proposals)
    proposal = dict(kind='six_advisory', school_year_id=year.id, school_year=year.name,
        grade_level_id=grade.id, program='BEP', teachers=proposals, unresolved=[], section_ids=[],
        preserved_teaching_assignments=0, preserved_adviser_assignments=0)
    batch = DemoTeacherSetupBatch(id=secrets.token_hex(16), school_year_id=year.id, created_by=actor.id,
        proposal_json=json.dumps(proposal), state_digest=_state(db, year.id))
    db.add(batch)
    db.commit()
    return {'batch_id': batch.id, **proposal}


def apply_demo_teacher_setup(db, batch_id, actor):
    _admin(actor)
    try:
        batch = db.scalar(select(DemoTeacherSetupBatch).where(DemoTeacherSetupBatch.id == batch_id).with_for_update())
        if not batch or batch.created_by != actor.id:
            raise ValueError('Preview was not found for this administrator')
        if batch.applied:
            return {**json.loads(batch.result_json), 'already_applied': True, 'credentials': []}
        year = db.scalar(select(SchoolYear).where(SchoolYear.id == batch.school_year_id).with_for_update())
        if not year or not year.active or year.deleted_at:
            raise ValueError('The selected school year is no longer active')
        proposal = json.loads(batch.proposal_json)
        if proposal.get('kind') == 'six_advisory':
            existing = _existing_advisory_setup(db, year.id)
            if existing:
                db.commit()
                return existing
        for model in (SchoolSection, Subject, GradeLevel, User):
            db.scalars(select(model).order_by(model.id).with_for_update()).all()
        if _state(db, year.id) != batch.state_digest:
            raise ValueError('Assignments or school setup changed. Generate a new preview before confirming.')
        ids, credentials, section_ids_created = [], [], []
        for teacher in proposal['teachers']:
            password = 'Demo!' + secrets.token_urlsafe(18) + '7a'
            account = User(username=teacher['username'], full_name=teacher['full_name'], role='teacher',
                password_hash=hash_password(password), active=True, is_demo=True, must_change_password=True)
            db.add(account)
            db.flush()
            ids.append(account.id)
            section_ids = teacher['section_ids']
            adviser_section_id = teacher['adviser_section_id']
            if proposal.get('kind') == 'six_advisory':
                section = SchoolSection(grade_level_id=teacher['grade_level_id'], name=teacher['new_section_name'], track='BEP', active=True)
                db.add(section)
                db.flush()
                section_ids = [section.id]
                adviser_section_id = section.id
                section_ids_created.append(section.id)
            for section_id in section_ids:
                assignment = db.scalar(select(SubjectTeachingAssignment).where(SubjectTeachingAssignment.school_year_id == year.id,
                    SubjectTeachingAssignment.subject_id == teacher['subject_id'], SubjectTeachingAssignment.section_id == section_id))
                if assignment:
                    if assignment.active:
                        raise ValueError('A teaching slot was filled. Generate a new preview.')
                    # Inactive records may own historical gradebooks; do not recycle them.
                    raise ValueError('A selected teaching slot has inactive assignment history; review it manually.')
                db.add(SubjectTeachingAssignment(school_year_id=year.id, subject_id=teacher['subject_id'], section_id=section_id, teacher_user_id=account.id, active=True))
            if adviser_section_id:
                assign_section_adviser(db, year.id, adviser_section_id, account.id)
            credentials.append({'full_name': account.full_name, 'username': account.username, 'temporary_password': password})
        result = {'batch_id': batch.id, 'created_user_ids': ids, 'created_count': len(ids), 'unresolved': proposal['unresolved']}
        if proposal.get('kind') == 'six_advisory':
            result['created_section_ids'] = section_ids_created
        batch.applied, batch.result_json = True, json.dumps(result)
        add_audit(db, actor, 'Create', 'DemoTeacherSetup', batch.id, 'Confirmed demonstration teaching and annual adviser assignments', {}, result)
        db.commit()
        return {**result, 'credentials': credentials}
    except Exception:
        db.rollback()
        raise
