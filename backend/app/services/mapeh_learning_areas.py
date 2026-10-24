"""Explicit learning-area policies and opt-in legacy activation; never run at startup."""
import hashlib
import json
from sqlalchemy import select
from ..models_grading import Gradebook, GradingPolicy
from .academic_context import is_junior_high

AREAS = {'music_arts': 'Music and Arts', 'pe_health': 'Physical Education and Health'}

def validate_area(subject, grade, area):
    if area not in AREAS or subject.name.strip().upper() != 'MAPEH' or not is_junior_high(grade):
        raise ValueError('Learning areas are available only for JHS MAPEH: Music and Arts or PE and Health.')

def partner_gradebook_issue(db, book):
    if book.learning_area not in AREAS:
        return None
    partner_area = 'pe_health' if book.learning_area == 'music_arts' else 'music_arts'
    matches = db.scalars(select(Gradebook).where(
        Gradebook.school_year_id == book.school_year_id,
        Gradebook.grading_period_id == book.grading_period_id,
        Gradebook.grade_level_id == book.grade_level_id,
        Gradebook.section_id == book.section_id,
        Gradebook.subject_id == book.subject_id,
        Gradebook.teacher_user_id == book.teacher_user_id,
        Gradebook.learning_area == partner_area,
        Gradebook.is_legacy_readonly.is_(False),
    )).all()
    partner_name = AREAS[partner_area]
    if len(matches) != 1:
        return f"Complete the matching {partner_name} gradebook for MAPEH Term {book.quarter} before finalizing."
    from .grading import get_gradebook_full
    full = get_gradebook_full(db, matches[0].id, include_mapeh_summary=False)
    if not full or not full['students'] or full['statistics']['incomplete']:
        return f"Enter and save complete {partner_name} grades for every learner in MAPEH Term {book.quarter} before finalizing."
    return None

def area_policy(db, year, actor):
    from .class_record_export import template_table
    from .reports import TEMPLATES_DIR
    from .template_policies import policy_components
    version = 'MAPEH-Areas-v1'
    policy = db.scalar(select(GradingPolicy).where(GradingPolicy.school_year == year, GradingPolicy.version == version))
    if policy is None:
        policy = GradingPolicy(name='MAPEH learning areas 20/60/20', version=version, school_year=year,
            grade_levels='7,8,9,10', subject_category='MAPEH-Areas',
            component_definitions_json=json.dumps(policy_components('mapeh')),
            transmutation_table_json=json.dumps(template_table(TEMPLATES_DIR / 'SUBJECT CLASS RECORDS' / 'MUSIC AND ARTS AND PE-HEALTH - Grade 7-10 Class Record.xlsx')),
            rounding_decimal_places=2, rounding_final_decimal_places=0, rounding_method='half_up', passing_grade=75,
            status='Active', created_by=actor.id, created_by_name=actor.full_name)
        db.add(policy); db.flush()
    return policy

def preview_mapeh_activation(db):
    from .grading import get_gradebook_full
    books = db.scalars(select(Gradebook).where(Gradebook.learning_area == '').order_by(Gradebook.id)).all()
    rows = []
    for book in books:
        if book.subject_name.strip().upper() != 'MAPEH' or not is_junior_high(book.grade_name): continue
        full = get_gradebook_full(db, book.id)
        rows.append({'id':book.id,'school_year':book.school_year_name,'term':book.quarter,'section':book.section_name,
            'teacher':book.teacher_name,'status':book.status,'policy_id':book.grading_policy_id,
            'legacy_marker':book.is_legacy_readonly,'policy':full['policy'],'components':full['components'],
            'grades':[{'person_id':s['person_id'],'initial':s['initial_grade'],'term':s['reported_grade']} for s in full['students']],
            'items':[{k:item[k] for k in ('id','label','max_score')} for c in full['components'] for item in c['items']],
            'scores':[{'person_id':s['person_id'],'scores':s['scores'],'statuses':s['score_statuses']} for s in full['students']],
            'planned_areas':list(AREAS)})
    from ..models import SubjectTeachingAssignment,User
    contexts=[]
    existing_areas=[]
    seen=set()
    for book in books:
        if book.subject_name.strip().upper()!='MAPEH' or not is_junior_high(book.grade_name): continue
        key=(book.school_year_id,book.grade_level_id,book.section_id,book.subject_id)
        if key in seen: continue
        seen.add(key)
        assignment=db.scalar(select(SubjectTeachingAssignment).where(SubjectTeachingAssignment.school_year_id==book.school_year_id,
            SubjectTeachingAssignment.section_id==book.section_id,SubjectTeachingAssignment.subject_id==book.subject_id,
            SubjectTeachingAssignment.active.is_(True)))
        teacher=db.get(User,assignment.teacher_user_id) if assignment else None
        refs=(book.school_year,book.grade_level,book.section,book.subject)
        if not teacher or not teacher.active or not all(r.active and r.deleted_at is None for r in refs): continue
        from ..models import GradingPeriod
        for period in db.scalars(select(GradingPeriod).where(GradingPeriod.school_year_id==book.school_year_id,
                GradingPeriod.quarter.in_([1,2,3]),GradingPeriod.active.is_(True),GradingPeriod.deleted_at.is_(None))).all():
            for area in AREAS:
                existing=db.scalar(select(Gradebook).where(Gradebook.school_year_id==book.school_year_id,
                    Gradebook.grading_period_id==period.id,Gradebook.grade_level_id==book.grade_level_id,
                    Gradebook.section_id==book.section_id,Gradebook.subject_id==book.subject_id,Gradebook.learning_area==area))
                if existing:
                    existing_areas.append(get_gradebook_full(db,existing.id,include_mapeh_summary=False))
                    continue
                contexts.append({'school_year_id':book.school_year_id,'grading_period_id':period.id,'grade_level_id':book.grade_level_id,
                    'section_id':book.section_id,'subject_id':book.subject_id,'learning_area':area,'teacher_id':teacher.id,
                    'teacher':teacher.full_name,'term':period.quarter,'section':book.section_name})
    digest=hashlib.sha256(json.dumps({'legacy':rows,'planned':contexts,'existing_areas':existing_areas},sort_keys=True,default=str).encode()).hexdigest()
    return {'hash':digest,'legacy_records':rows,'planned_empty_area_contexts':contexts,'existing_area_ids':[r['gradebook']['id'] for r in existing_areas],'live_changes_applied':False}

def apply_mapeh_activation(db, expected_preview_hash, actor):
    from .grading import add_gradebook_audit,create_or_get_gradebook
    if actor.role not in {'admin','records_officer'}: raise ValueError('Only an administrator or records officer can activate MAPEH learning areas.')
    # Lock the candidate contexts before revalidating the reviewed snapshot.
    db.scalars(select(Gradebook).where(Gradebook.learning_area == '').with_for_update()).all()
    preview=preview_mapeh_activation(db)
    if preview['hash'] != expected_preview_hash: raise ValueError('The gradebooks changed. Review a fresh activation preview first.')
    for row in preview['legacy_records']:
        book=db.get(Gradebook,row['id'])
        if not book.is_legacy_readonly:
            book.is_legacy_readonly=True
            add_gradebook_audit(db,book.id,'LegacyPreserved',actor,reason='Preserved combined MAPEH; new learning areas start empty')
    created=[]
    for context in preview['planned_empty_area_contexts']:
        area_book=create_or_get_gradebook(db,context['school_year_id'],context['grading_period_id'],context['grade_level_id'],
            context['section_id'],context['subject_id'],actor,learning_area=context['learning_area'],commit=False)
        created.append(area_book.id)
    # Caller commits markers and newly initialized empty records together.

    db.flush()
    return {'marked_legacy_ids':[r['id'] for r in preview['legacy_records']],'area_gradebook_ids':created}
