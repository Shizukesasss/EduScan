"""Versioned policies for the approved three-term subject workbooks."""
import json

from sqlalchemy import select

from ..models import SchoolYear
from ..models_grading import AssessmentItem, GradingPolicy
from .academic_context import subject_policy_category

VERSION = 'Updated-Excel-3Term-v1'


def policy_components(kind):
    if kind == 'gmrc':
        groups = [('Written Work Cognitive', 'Written Work', 10, 5),
                  ('Written Work Affective', 'Written Work', 10, 5),
                  ('Performance Task Cognitive', 'Performance Task', 10, 3),
                  ('Performance Task Affective', 'Performance Task', 10, 3),
                  ('Performance Task Behavioral', 'Performance Task', 30, 3)]
    else:
        groups = [('Written Work', 'Written Work', 20, 5),
                  ('Performance Tasks', 'Performance Task', 50 if kind == 'core' else 60, 3)]
    groups.append(('Term Examinations', 'Term Examinations', 30 if kind in {'core', 'gmrc'} else 20, 3))
    return [dict(name=name, component_type=type_, weight=weight, max_items=count,
                 description='ST1 30%, ST2 30%, TE 40%' if type_ == 'Term Examinations' else '')
            for name, type_, weight, count in groups]


def ensure_template_policies(db, school_year, actor):
    from .class_record_export import template_table
    from .reports import TEMPLATES_DIR
    db.scalar(select(SchoolYear).where(SchoolYear.name == school_year).with_for_update())
    policies = {}
    for category, kind, filename in (
        ('Languages/AP/EsP', 'core', 'ENGLISH - Grade 7-10 Class Record.xlsx'),
        ('Math/Science', 'core', 'MATHEMATICS - Grade 7-10 Class Record.xlsx'),
        ('MAPEH/TLE', 'performance', 'SPA - Grade 7-10 Class Record.xlsx'),
        ('GMRC/Values', 'gmrc', 'GMRC - Grade 7-10 Class Record.xlsx'),
    ):
        policy = db.scalar(select(GradingPolicy).where(
            GradingPolicy.school_year == school_year, GradingPolicy.subject_category == category,
            GradingPolicy.version == VERSION))
        if policy is None:
            table = [{**row, 'min': round(row['min'], 2), 'max': round(row['max'], 2)}
                     for row in template_table(TEMPLATES_DIR / 'SUBJECT CLASS RECORDS' / filename)]
            policy = GradingPolicy(name=f'Updated Excel class record — {category}', version=VERSION,
                                   school_year=school_year, grade_levels='7,8,9,10', subject_category=category,
                                   component_definitions_json=json.dumps(policy_components(kind)),
                                   transmutation_table_json=json.dumps(table), rounding_decimal_places=2,
                                   rounding_final_decimal_places=0, rounding_method='half_up', passing_grade=75,
                                   status='Active', created_by=actor.id, created_by_name=actor.full_name)
            db.add(policy)
            db.flush()
        policies[category] = policy
    return policies


def align_open_gradebook(db, book, actor, policies):
    """Preserve all activity IDs/maxima and score rows; never reopen a locked record."""
    from .class_record_export import subject_template, assessment_groups
    from .grading import add_gradebook_audit
    from .reports import _assessment_category
    if book.status in {'Finalized', 'Locked'}:
        raise ValueError(f'Finalized record {book.id} requires an explicit teacher reopening before policy alignment.')
    kind, _ = subject_template(book.subject.name)
    definitions = policy_components(kind)
    before = {'policy_id': book.grading_policy_id, 'components': [(c.id, c.name, c.weight, c.component_type) for c in book.components]}
    if kind == 'gmrc':
        # Domain identity cannot be inferred from saved generic WW/PT scores.
        groups = assessment_groups({'components': [dict(id=c.id, name=c.name, component_type=c.component_type,
                                                       description=c.description) for c in book.components]}, kind)
        by_key = {key: next(c for c in book.components if c.id == value['id']) for key, value in groups.items()}
        keys = ('ww_cognitive', 'ww_affective', 'pt_cognitive', 'pt_affective', 'pt_behavioral', 'exam')
        if set(by_key) != set(keys):
            raise ValueError('Existing GMRC domains require teacher identification; no scores were changed.')
        components = [by_key[key] for key in keys]
    else:
        by_key = {}
        for component in book.components:
            key = 'exam' if component.component_type == 'Term Examinations' else _assessment_category({'name': component.name})
            if key in by_key or key not in {'ww', 'pt', 'exam'}:
                raise ValueError(f'Unexpected component in record {book.id}; manual mapping is required.')
            by_key[key] = component
        if set(by_key) != {'ww', 'pt', 'exam'}:
            raise ValueError(f'Incomplete assessment structure in record {book.id}.')
        components = [by_key[key] for key in ('ww', 'pt', 'exam')]
    exams = components[-1]
    if len(exams.items) == 1:
        exams.items[0].label = 'TE'
        exams.items[0].sequence = 2
        for index, label in enumerate(('ST1', 'ST2')):
            exams.items.append(AssessmentItem(label=label, max_score=exams.items[0].max_score, sequence=index))
    elif {item.label for item in exams.items} != {'ST1', 'ST2', 'TE'}:
        raise ValueError(f'Examination roles in record {book.id} require manual mapping.')
    for component, definition in zip(components, definitions):
        if kind == 'gmrc' or definition['component_type'] == 'Term Examinations':
            component.name = definition['name']
        component.weight = definition['weight']
        component.component_type = definition['component_type']
        component.description = definition['description']
    category = subject_policy_category(book.subject.name, book.subject.category)
    book.grading_policy_id = policies[category].id
    after = {'policy_id': book.grading_policy_id, 'components': [(c.id, c.name, c.weight, c.component_type) for c in components]}
    if before != after:
        add_gradebook_audit(db, book.id, 'PolicyAlignment', actor,
                           reason='User-approved updated Excel policy alignment; saved scores and activity maxima preserved; existing Quarterly Assessment retained as TE; ST1/ST2 added blank.',
                           old_value=json.dumps(before), new_value=json.dumps(after))
    db.flush()
