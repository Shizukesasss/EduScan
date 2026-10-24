"""Fill subject templates without replacing their grading formulas."""
import math
import re
from decimal import Decimal
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from fastapi import HTTPException
from sqlalchemy import select

from ..models_grading import Gradebook
from ..models import GradingPeriod, Subject
from .academic_context import is_junior_high
from .grading import get_gradebook_full
from .grading_engine import round_value
from .settings_store import get_json


def subject_template(subject, is_elective=False):
    if is_elective:
        return 'core', 'ENGLISH - Grade 7-10 Class Record.xlsx'
    name = re.sub(r'\s+', ' ', subject.strip().upper())
    aliases = {'MATH': 'MATHEMATICS', 'AP': 'ARALING PANLIPUNAN',
               'TECHNOLOGY AND LIVELIHOOD EDUCATION': 'TLE', 'ESP': 'VALUES EDUCATION',
               'EDUKASYON SA PAGPAPAKATAO': 'VALUES EDUCATION',
               'SPECIAL PROGRAM IN THE ARTS': 'SPA', 'SPECIAL PROGRAM IN SPORTS': 'SPS'}
    name = aliases.get(name, name)
    if name in {'ENGLISH', 'SCIENCE', 'MATHEMATICS', 'FILIPINO', 'ARALING PANLIPUNAN', 'TLE', 'ROBOTICS'}:
        kind = 'core'
    elif name in {'GMRC', 'VALUES EDUCATION'}:
        kind = 'gmrc'
    elif name in {'SPA', 'SPS'}:
        kind = name.lower()
    elif name in {'MAPEH', 'MUSIC AND ARTS', 'MUSIC & ARTS', 'MAPEH - MUSIC AND ARTS',
                  'PHYSICAL EDUCATION AND HEALTH', 'PHYSICAL EDUCATION & HEALTH', 'PE AND HEALTH', 'PE & HEALTH', 'MAPEH - PE AND HEALTH'}:
        return 'mapeh', 'MUSIC AND ARTS AND PE-HEALTH - Grade 7-10 Class Record.xlsx'
    else:
        raise HTTPException(409, f"No matching updated DepEd class-record workbook is available for '{subject}'. Use a combined Music and Arts or PE and Health subject for the combined workbook.")
    return kind, f'{name} - Grade 7-10 Class Record.xlsx'


def template_table(template):
    from .reports import _xlsx_sheet_paths, _SHEET_MAIN_NS
    with ZipFile(template) as package:
        sheet = ET.fromstring(package.read(_xlsx_sheet_paths(package)['HELPER']))
        cells = {c.get('r'): c.find(f'{{{_SHEET_MAIN_NS}}}v') for c in sheet.iter(f'{{{_SHEET_MAIN_NS}}}c')}
        return [{'min': float(cells[f'B{row}'].text), 'max': float(cells[f'C{row}'].text),
                 'value': int(float(cells[f'D{row}'].text))} for row in range(8, 49)]


def assessment_groups(full, kind):
    from .reports import _assessment_category
    result = {}
    for component in full['components']:
        category = _assessment_category(component)
        key = category
        if kind == 'gmrc' and category in {'ww', 'pt'}:
            text = f"{component['name']} {component.get('description', '')} {component.get('component_type', '')}".lower()
            domains = [domain for domain in ('cognitive', 'affective', 'behavioral') if domain in text]
            if len(domains) != 1:
                raise HTTPException(409, 'GMRC/Values export requires explicitly named cognitive, affective, and behavioral assessment components. Saved scores were not changed.')
            key = f'{category}_{domains[0]}'
        if not key or key in result:
            raise HTTPException(409, 'Each workbook assessment group must have one explicitly identified component.')
        result[key] = component
    return result


def _rounded_template_grade_formula(initial_col, grade_row):
    initial = f'{initial_col}{grade_row}'
    precise = f'ROUND({initial},12)'
    return (f'IF({initial}="","",IFERROR(INDEX(HELPER!$D$8:$D$48,'
            f'IF({precise}>=HELPER!$B$8,1,MATCH({precise},HELPER!$B$8:$B$48,-1)+1)),""))')


def fill_saved_core(full, sheet_name, changes, cached, males, females, formulas):
    """Keep the supplied layout while reflecting an older saved WW/PT/QA policy."""
    from decimal import Decimal
    from .reports import _assessment_category, _column_name
    from .adaptive_class_record import _round
    groups = {}
    for component in full['components']:
        key = _assessment_category({'name': component['name']})
        if key is None or key in groups:
            raise HTTPException(409, 'The supplied template needs one Written Work, Performance Tasks, and Quarterly Assessment component.')
        groups[key] = component
    if set(groups) != {'ww', 'pt', 'exam'}:
        raise HTTPException(409, 'The saved components do not fit the supplied subject template.')
    policy = full['policy']
    if len(policy['transmutation_table'] or []) > 60:
        raise HTTPException(409, 'This grade conversion table exceeds the supplied template formula capacity.')
    sheet, cache, edits = changes.setdefault(sheet_name, {}), cached.setdefault(sheet_name, {}), formulas.setdefault(sheet_name, {})
    layout = {'ww': (6, 5, 'K', 'L', 'M'), 'pt': (14, 3, 'Q', 'R', 'S'), 'exam': (20, 3, None, 'Z', 'AA')}
    items_by_group = {}
    for key, component in groups.items():
        first, capacity, total, ps, ws = layout[key]
        items = [item for item in component['items'] if item['active']]
        if not 1 <= len(items) <= capacity:
            raise HTTPException(409, f"{component['name']} exceeds the activity capacity of the supplied template.")
        items_by_group[key] = items
        sheet[f'{_column_name(first)}12'] = component['name']
        sheet[f'{ws}15'] = component['weight'] / 100
        for index in range(capacity):
            col = _column_name(first + index)
            sheet[f'{col}14'] = (index + 1 if key in {'ww', 'pt'} else items[index]['label']) if index < len(items) else None
            sheet[f'{col}15'] = items[index]['max_score'] if index < len(items) else None
    # The old QA policy pools scores; it must not inherit the template's 30/30/40 exam split.
    for col in ('W', 'X', 'Y'):
        sheet[f'{col}14'] = sheet[f'{col}15'] = None
    student_map = {student['person_id']: student for student in full['students']}
    for roster, start in ((males, 18), (females, 69)):
        for index, person in enumerate(roster):
            student = student_map.get(person['person_id'])
            if student is None:
                continue
            row, expressions, raw = start + index, [], Decimal('0')
            for key, component in groups.items():
                first, capacity, total, ps, ws = layout[key]
                items = items_by_group[key]
                scores = [student['scores'].get(str(item['id'])) for item in items]
                if any(value is None for value in scores):
                    raise HTTPException(409, 'A required exported assessment score is missing.')
                begin, end = _column_name(first), _column_name(first + len(items) - 1)
                score_range, max_range = f'{begin}{row}:{end}{row}', f'{begin}$15:{end}$15'
                percentage = f'SUM({score_range})/SUM({max_range})*100'
                weighted = f'({percentage})*{ws}$15'
                for offset, value in enumerate(scores):
                    sheet[f'{_column_name(first + offset)}{row}'] = value
                if total:
                    edits[f'{total}{row}'] = f'SUM({score_range})'
                    cache[f'{total}{row}'] = sum(scores)
                edits[f'{ps}{row}'], edits[f'{ws}{row}'] = _round(percentage, policy), _round(weighted, policy)
                pct = sum(scores) / sum(item['max_score'] for item in items) * 100
                weighted_value = Decimal(str(pct)) * Decimal(str(component['weight'])) / 100
                raw += weighted_value
                cache[f'{ps}{row}'] = round_value(pct, policy['rounding_decimal_places'], policy['rounding_method'])
                cache[f'{ws}{row}'] = round_value(weighted_value, policy['rounding_decimal_places'], policy['rounding_method'])
                expressions.append(weighted)
            for col in ('W', 'X', 'Y'):
                sheet[f'{col}{row}'] = None
            assert round_value(raw, policy['rounding_decimal_places'], policy['rounding_method']) == student['initial_grade']
            edits[f'AB{row}'] = _round(f'SUM({",".join(expressions)})', policy)
            grade = f'MAX(0,MIN(100,AB{row}))'
            conversion = f'IF({grade}>=100,100,"")'
            table = policy['transmutation_table']
            if table:
                for entry in reversed(table):
                    conversion = f'IF(AND({grade}>={float(entry["min"])},{grade}<={float(entry["max"])}),{int(entry["value"])},{conversion})'
            else:
                conversion = f'IF({grade}>=100,100,IF({grade}>=60,INT(({grade}-60+0.000000001)/1.6)+75,INT(({grade}+0.000000001)/4)+60))'
            edits[f'AC{row}'] = conversion
            cache[f'AB{row}'], cache[f'AC{row}'] = student['initial_grade'], student['reported_grade']


def fill_term(full, kind, sheet_name, changes, cached, males, females, table, formulas=None):
    if kind in {'core', 'mapeh'} and not any(c.get('component_type') == 'Term Examinations' for c in full['components']):
        return fill_saved_core(full, sheet_name, changes, cached, males, females, formulas)
    groups = assessment_groups(full, kind)
    if full['policy']['rounding_method'] != 'half_up' or full['policy']['rounding_decimal_places'] != 2:
        raise HTTPException(409, 'The fixed workbook cannot represent this saved rounding policy.')
    if groups.get('exam', {}).get('component_type') != 'Term Examinations':
        raise HTTPException(409, 'The fixed workbook uses ST1/ST2/TE proportions; use the saved gradebook calculation instead.')
    layout = ({'ww_cognitive': (6, 5, 10), 'ww_affective': (14, 5, 10),
               'pt_cognitive': (22, 3, 10), 'pt_affective': (28, 3, 10),
               'pt_behavioral': (34, 3, 30), 'exam': (40, 3, 30)} if kind == 'gmrc' else
              {'ww': (6, 5, 20), 'pt': (14, 3, 50 if kind == 'core' else 60),
               'exam': (20, 3, 30 if kind == 'core' else 20)})
    if set(groups) != set(layout):
        raise HTTPException(409, 'Assessment Setup does not match the selected workbook groups. Existing grading rules and scores were preserved.')
    for key, component in groups.items():
        if not math.isclose(float(component['weight']), layout[key][2], abs_tol=0.001):
            raise HTTPException(409, f"Workbook policy mismatch: {component['name']} requires {layout[key][2]}%, but this saved class record uses {component['weight']}%. An approved matching policy is needed; no grades were changed.")
    actual_table = sorted(full['policy']['transmutation_table'], key=lambda row: row['min'])
    expected_table = sorted(table, key=lambda row: row['min'])
    normalize_table = lambda rows: [(round(float(row['min']), 2), round(float(row['max']), 2), int(row['value'])) for row in rows]
    if normalize_table(actual_table) != normalize_table(expected_table):
        raise HTTPException(409, 'The saved grade conversion table differs from this workbook (for example, the workbook converts an initial 80 to 83). Export was stopped to preserve correct grades; approve a matching policy before exporting.')
    sheet = changes.setdefault(sheet_name, {})
    cache = cached.setdefault(sheet_name, {})
    formula_overrides = (formulas if formulas is not None else {}).setdefault(sheet_name, {})
    hps, male_start, female_start, initial_col, grade_col = (16, 19, 70, 'AV', 'AW') if kind == 'gmrc' else (15, 18, 69, 'AB', 'AC')
    from .reports import _column_name
    items_by_group = {}
    for key, component in groups.items():
        items = [item for item in component['items'] if item.get('active')]
        first, capacity, _ = layout[key]
        if not items or len(items) > capacity:
            raise HTTPException(409, f"{component['name']} must contain 1–{capacity} used activities for this workbook. Activities will not be silently merged.")
        if key == 'exam':
            roles = {}
            for item in items:
                label = re.sub(r'[^A-Z0-9]', '', item['label'].upper())
                role = {'ST1': 0, 'SUMMATIVETEST1': 0, 'ST2': 1, 'SUMMATIVETEST2': 1,
                        'TE': 2, 'TERMEXAM': 2, 'TERMEXAMINATION': 2}.get(label)
                if role is None or role in roles:
                    raise HTTPException(409, 'Name the three used examination activities ST1, ST2, and TE so they match the workbook’s 30/30/40 examination calculation.')
                roles[role] = item
            if set(roles) != {0, 1, 2}:
                raise HTTPException(409, 'This workbook requires ST1, ST2, and TE examination results. The saved assessment setup was not changed.')
            items = [roles[index] for index in range(3)]
        items_by_group[key] = items
        for index, item in enumerate(items):
            sheet[f'{_column_name(first + index)}{hps}'] = item['max_score']
    student_map = {student['person_id']: student for student in full['students']}
    for roster, start in ((males, male_start), (females, female_start)):
        for index, person in enumerate(roster):
            student = student_map.get(person['person_id'])
            if student is None:
                continue
            initial = Decimal('0')
            for key, items in items_by_group.items():
                first, _, weight = layout[key]
                scores = [student['scores'].get(str(item['id'])) for item in items]
                if any(score is None for score in scores):
                    raise HTTPException(409, 'A required exported assessment score is missing.')
                for offset, score in enumerate(scores):
                    sheet[f'{_column_name(first + offset)}{start + index}'] = score
                if key == 'exam':
                    percentage = sum((Decimal(str(score)) / Decimal(str(item['max_score'])) * Decimal(str(portion))
                                      for score, item, portion in zip(scores, items, (30, 30, 40))), Decimal('0'))
                else:
                    percentage = (sum((Decimal(str(score)) for score in scores), Decimal('0'))
                                  / sum((Decimal(str(item['max_score'])) for item in items), Decimal('0')) * 100)
                initial += percentage * Decimal(str(weight)) / 100
            converted = next((row['value'] for row in sorted(table, key=lambda row: row['min'], reverse=True)
                              if initial >= Decimal(str(row['min']))), None)
            if converted is None or student['reported_grade'] != converted or round_value(float(initial), 2) != student['initial_grade']:
                raise HTTPException(409, f"The workbook calculation differs from the saved grade for {student['full_name']}. Check the examination weighting and rounding policy. No grades were changed.")
            cache[f'{initial_col}{start + index}'] = student['initial_grade']
            cache[f'{grade_col}{start + index}'] = student['reported_grade']
            formula_overrides[f'{grade_col}{start + index}'] = _rounded_template_grade_formula(initial_col, start + index)


def export_jhs(db, book, full, kind, template, region, division, school_id, allowed_teacher_id=None, all_terms=False, through_term=None):
    from .reports import _student_groups, _complete_finalized_record, _write_class_record_workbook, _safe_name, new_report_path, EXPORT_DIR
    if not template.is_file():
        raise HTTPException(409, f"The required subject workbook '{template.name}' is missing.")
    if not region.strip() or not division.strip() or not school_id.strip().isdigit():
        raise HTTPException(422, 'Enter the region, actual division name, and numeric school ID before exporting.')
    if not _complete_finalized_record(full):
        raise HTTPException(409, 'Finalize the complete class record before exporting.')
    if allowed_teacher_id is not None and book.teacher_user_id != allowed_teacher_id:
        raise HTTPException(403, 'This saved class record belongs to another teacher.')
    gb = full['gradebook']
    if not is_junior_high(gb['grade_name']):
        raise HTTPException(409, 'These subject workbooks support Grade 7 through Grade 10 only.')
    if int(gb['quarter']) not in (1, 2, 3):
        raise HTTPException(409, 'The subject workbook supports Terms 1, 2, and 3 only.')
    males, females = _student_groups(full['students'])
    for roster in (males, females):
        roster.sort(key=lambda student: (student['full_name'].casefold(), student.get('lrn') or student['external_id']))
    changes = {'INPUT DATA': {'E10': region.strip(), 'E11': division.strip(), 'E13': school_id.strip(),
                             'E14': 'San Jose National High School', 'E15': gb['school_year_name'],
                             'E16': get_json(db, 'school.heads', {}).get(str(book.school_year_id), {}).get('full_name', ''),
                             'E23': gb['teacher_name'], 'E24': gb['subject_name'],
                             'E25': int(gb['grade_name']), 'E26': gb['section_name']}}
    for roster, column in ((males, 'K'), (females, 'N')):
        for index, student in enumerate(roster):
            changes['INPUT DATA'][f'{column}{11 + index}'] = student['full_name']
    query = select(Gradebook).where(Gradebook.school_year_id == book.school_year_id,
                                   Gradebook.grade_level_id == book.grade_level_id, Gradebook.section_id == book.section_id,
                                   Gradebook.grading_period.has(GradingPeriod.deleted_at.is_(None)),
                                   Gradebook.subject.has(Subject.deleted_at.is_(None)))
    if kind != 'mapeh':
        query = query.where(Gradebook.subject_id == book.subject_id)
    if book.learning_area:
        query = query.where(Gradebook.subject_id == book.subject_id,
                            Gradebook.learning_area.in_(['music_arts','pe_health']),
                            Gradebook.teacher_user_id == book.teacher_user_id,
                            Gradebook.is_legacy_readonly.is_(False))
    elif kind == 'mapeh':
        # Legacy combined records may export alone, but never stand in for new areas.
        query = query.where(Gradebook.learning_area == '')
        if book.is_legacy_readonly:
            query = query.where(Gradebook.subject_id == book.subject_id,
                                Gradebook.teacher_user_id == book.teacher_user_id)
    if allowed_teacher_id is not None:
        query = query.where(Gradebook.teacher_user_id == allowed_teacher_id)
    periods = tuple(range(1, (through_term or 3) + 1)) if all_terms or through_term else (book.quarter,)
    query = query.where(Gradebook.quarter.in_(periods))
    if all_terms or through_term:
        query = query.where(Gradebook.teacher_user_id == book.teacher_user_id)
    cached, formulas = {}, {}
    table = template_table(template)
    written_sheets, exported_terms = set(), {}
    for sibling in db.scalars(query).all():
        try:
            sibling_kind, _ = subject_template(sibling.subject_name, sibling.subject.is_elective is True)
        except HTTPException:
            continue
        if sibling_kind != kind or sibling.quarter not in (1, 2, 3):
            continue
        term = get_gradebook_full(db, sibling.id)
        if not _complete_finalized_record(term):
            continue
        suffix = (' PE and H' if sibling.learning_area == 'pe_health' or (not sibling.learning_area and 'HEALTH' in sibling.subject_name.upper()) else ' M and A') if kind == 'mapeh' else ''
        sheet_name = f'TERM {sibling.quarter}{suffix}'
        if sheet_name in written_sheets:
            raise HTTPException(409, 'Multiple finalized records match the same learning area and term. Resolve the subject assignment before exporting.')
        fill_term(term, kind, sheet_name, changes, cached, males, females, table, formulas)
        written_sheets.add(sheet_name)
        exported_terms[(sibling.quarter, sibling.learning_area)] = term
        if term['gradebook']['teacher_name'] != gb['teacher_name']:
            changes[sheet_name]['AB10' if kind == 'gmrc' else 'Q10'] = term['gradebook']['teacher_name']
    suffix = (' PE and H' if book.learning_area == 'pe_health' or (not book.learning_area and 'HEALTH' in gb['subject_name'].upper()) else ' M and A') if kind == 'mapeh' else ''
    required = ({f'TERM {period}{area}' for period in periods for area in (' M and A',' PE and H')} if book.learning_area else {f'TERM {period}{suffix}' for period in periods})
    if not required.issubset(written_sheets):
        raise HTTPException(409, 'All requested terms must be complete and finalized or locked for this teacher, subject, section, and school year before exporting.')
    period_name = 'Terms1-2' if through_term == 2 else 'AllTerms' if all_terms else f"Term{gb['quarter']}"
    target = new_report_path(EXPORT_DIR, f"ClassRecord-{'Legacy-' if book.is_legacy_readonly else ''}{_safe_name(gb['school_year_name'])}-{period_name}-Grade{gb['grade_name']}-{_safe_name(gb['section_name'])}-{_safe_name(gb['subject_name'])}.xlsx")
    guards = {}
    if kind == 'mapeh':
        changes['FINAL GRADES'] = {}
        guards['FINAL GRADES'] = {}
        for roster, first_row in ((males, 15), (females, 66)):
            for index, _ in enumerate(roster):
                row = first_row + index
                for column, pair in (('H', f'F{row}:G{row}'), ('K', f'I{row}:J{row}'), ('N', f'L{row}:M{row}')):
                    guards['FINAL GRADES'][f'{column}{row}'] = f'COUNT({pair})=2'
                if book.learning_area:
                    term_grades=[]
                    for period,first_col,combined_col in ((1,'F','H'),(2,'I','K'),(3,'L','N')):
                        if period not in periods: continue
                        area_grades=[]
                        for area,col in zip(('music_arts','pe_health'),(first_col,chr(ord(first_col)+1))):
                            student=next((s for s in exported_terms[(period,area)]['students'] if s['person_id']==roster[index]['person_id']),None)
                            if student is None: raise HTTPException(409,'Both learning areas must have the same learner roster.')
                            area_grades.append(student['reported_grade'])
                            cached.setdefault('FINAL GRADES',{})[f'{col}{row}']=student['reported_grade']
                        combined=round_value(sum(area_grades)/2,0,'half_up')
                        cached['FINAL GRADES'][f'{combined_col}{row}']=combined
                        term_grades.append(combined)
                    if len(term_grades)==3:
                        cached['FINAL GRADES'][f'O{row}']=round_value(sum(term_grades)/3,0,'half_up')

    _write_class_record_workbook(template, target, changes, formula_values=cached, formula_guards=guards, formula_overrides=formulas)
    return target
