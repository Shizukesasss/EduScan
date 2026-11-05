"""Typed TLE subjects use real assignments, gradebooks, and supplied workbooks."""
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import load_workbook

from tests import test_grading_regressions as fixtures
from app.main import save_subject, save_subject_teaching_assignments
from app.models import GradingPeriod, Subject, SubjectTeachingAssignment, User
from app.schemas import SubjectPayload, SubjectTeachingAssignmentPayload
from app.services import grading, reports
from app.services.class_record_export import subject_template


class TLESpecializationsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ClassRecordRegressionTest()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.fixture.grade.name = '7'
        self.fixture.first.grade = self.fixture.second.grade = '7'
        self.db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def save(self, name, **kwargs):
        saved = save_subject(SubjectPayload(code='TLE', name=name, category='JHS', **kwargs),
                             self.db, self.fixture.admin)
        return self.db.get(Subject, saved['id'])

    def test_multiple_typed_specializations_have_unique_codes_and_normalized_names(self):
        cookery = self.save('  tle  -  Cookery  ')
        ict = self.save('TLE - ICT')
        plain = self.save('TECHNOLOGY AND LIVELIHOOD EDUCATION')
        self.assertEqual(cookery.name, 'TLE - Cookery')
        self.assertEqual(ict.name, 'TLE - ICT')
        self.assertEqual(len({cookery.code, ict.code, plain.code}), 3)
        self.assertFalse(cookery.is_elective)
        self.assertEqual(subject_template(cookery.name), ('tle', 'TLE - Grade 7-10 Class Record.xlsx'))

    def test_tle_names_always_use_the_tle_workbook_even_if_marked_elective(self):
        self.assertEqual(subject_template('TLE - Cookery', is_elective=True),
                         ('tle', 'TLE - Grade 7-10 Class Record.xlsx'))

    def test_duplicate_specialization_is_rejected_ignoring_case_and_spacing(self):
        self.save('TLE - Food   Processing')
        with self.assertRaises(HTTPException) as error:
            self.save(' tle - food processing ')
        self.assertEqual(error.exception.status_code, 409)

    def test_whitespace_only_specialization_saves_as_plain_tle(self):
        subject = self.save('TLE -   ')
        self.assertEqual(subject.name, 'TECHNOLOGY AND LIVELIHOOD EDUCATION')
        self.assertEqual(subject.code, 'TLE')

    def test_unicode_specialization_duplicates_are_rejected_ignoring_case(self):
        self.save('TLE - Électricité')
        with self.assertRaises(HTTPException) as error:
            self.save('TLE - électricité')
        self.assertEqual(error.exception.status_code, 409)

    def test_readding_deleted_specialization_restores_identity_and_code(self):
        subject = self.save('TLE - Électricité')
        original_id, original_code = subject.id, subject.code
        subject.deleted_at = datetime(2026, 11, 5)
        self.db.commit()
        restored = self.save('TLE - électricité')
        self.assertEqual((restored.id, restored.code), (original_id, original_code))
        self.assertIsNone(restored.deleted_at)

    def test_generated_codes_handle_long_names_unicode_and_slug_collisions(self):
        subjects = [self.save('TLE - ' + name) for name in (
            'Food & Beverage', 'Food / Beverage', 'A' * 114, '農業', '烹飪',
        )]
        self.assertEqual(len({s.code for s in subjects}), 5)
        self.assertTrue(all(0 < len(s.code) <= 40 for s in subjects))

    def test_adding_specialization_to_plain_tle_frees_the_plain_code(self):
        plain = self.save('TLE')
        specialized = self.save('TLE - Cookery', id=plain.id)
        replacement = self.save('TLE')
        self.assertEqual(specialized.id, plain.id)
        self.assertNotEqual(specialized.code, replacement.code)
        self.assertEqual(replacement.code, 'TLE')

    def test_different_specializations_keep_assignments_gradebooks_and_edit_identity(self):
        fixture = self.fixture
        cookery, ict = self.save('TLE - Cookery'), self.save('TLE - ICT')
        other = User(username='ict-teacher', full_name='ICT Teacher', password_hash='unused', role='teacher')
        self.db.add(other)
        self.db.commit()
        books = []
        for subject, teacher in ((cookery, fixture.teacher), (ict, other)):
            save_subject_teaching_assignments(SubjectTeachingAssignmentPayload(
                school_year_id=fixture.year.id, subject_id=subject.id,
                teacher_user_id=teacher.id, section_ids=[fixture.section.id],
            ), self.db, fixture.admin)
            books.append(fixture.create(subject_id=subject.id, user=teacher))
        self.assertNotEqual(books[0].id, books[1].id)
        self.assertEqual([b.teacher_user_id for b in books], [fixture.teacher.id, other.id])
        self.assertEqual(books[0].grading_policy_id, books[1].grading_policy_id)
        with self.assertRaises(ValueError):
            fixture.create(subject_id=ict.id, user=fixture.teacher)
        original_code = cookery.code
        edited = self.save('TLE - Commercial Cookery', id=cookery.id)
        self.assertEqual(edited.id, cookery.id)
        self.assertEqual(edited.code, original_code)
        self.assertEqual(books[0].subject_id, cookery.id)
        self.assertEqual(self.db.query(SubjectTeachingAssignment).filter_by(subject_id=cookery.id).one().teacher_user_id,
                         fixture.teacher.id)
        plain = self.save('TLE')
        plain_book = fixture.create(subject_id=plain.id, user=fixture.admin)
        self.assertEqual(plain_book.grading_policy_id, books[0].grading_policy_id)

    def test_specializations_export_both_scopes_with_separate_labels_and_scores(self):
        fixture = self.fixture
        other = User(username='export-ict', full_name='ICT Teacher', password_hash='unused', role='teacher')
        self.db.add(other)
        periods = [fixture.period]
        for term in (2, 3):
            period = GradingPeriod(school_year_id=fixture.year.id, term_order=term, name=f'Term {term}',
                                   starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
            self.db.add(period)
            periods.append(period)
        self.db.commit()
        with TemporaryDirectory(dir=fixtures.TEST_DIR.name) as folder, patch.object(reports, 'EXPORT_DIR', Path(folder)):
            for name, teacher, score in (('Cookery', fixture.teacher, 80), ('ICT', other, 60)):
                subject = self.save(f'TLE - {name}')
                save_subject_teaching_assignments(SubjectTeachingAssignmentPayload(
                    school_year_id=fixture.year.id, subject_id=subject.id,
                    teacher_user_id=teacher.id, section_ids=[fixture.section.id],
                ), self.db, fixture.admin)
                books = []
                for period in periods:
                    book = fixture.create(subject_id=subject.id, grading_period_id=period.id, user=teacher)
                    fixture.score_student(book, score)
                    fixture.score_second_student(book, score)
                    book.status = 'Finalized'
                    self.db.commit()
                    books.append(book)
                full = grading.get_gradebook_full(self.db, books[0].id)
                self.assertEqual([c['weight'] for c in full['components']], [20, 60, 20])
                for all_terms in (False, True):
                    path = reports.generate_gradebook_report_xlsx(
                        self.db, books[0].id, 'V', 'Test Division', '123456',
                        allowed_teacher_id=teacher.id, all_terms=all_terms,
                    )
                    workbook = load_workbook(path, read_only=True, data_only=True)
                    try:
                        self.assertEqual(workbook['INPUT DATA']['E24'].value, f'TLE - {name}')
                        self.assertEqual(workbook['INPUT DATA']['E23'].value, teacher.full_name)
                        self.assertEqual(workbook['TERM 1']['M15'].value, 0.2)
                        self.assertEqual(workbook['TERM 1']['S15'].value, 0.6)
                        self.assertEqual(workbook['TERM 1']['AA15'].value, 0.2)
                        self.assertEqual(workbook['TERM 1']['F18'].value, score / 100 * full['components'][0]['items'][0]['max_score'])
                        if all_terms:
                            self.assertIsNotNone(workbook['TERM 3']['F18'].value)
                    finally:
                        workbook.close()

    def test_updating_open_tle_gradebook_preserves_scores_and_activity_ids(self):
        from app.services.template_policies import ensure_template_policies, align_open_gradebook
        fixture = self.fixture
        subject = self.save('TLE - ICT')
        book = fixture.create(subject_id=subject.id)
        fixture.score_student(book, 80)
        before_ids = [item.id for component in book.components for item in component.items]
        before_scores = grading.get_gradebook_full(self.db, book.id)['students'][0]['scores']
        for component, weight in zip(book.components, (20, 50, 30)):
            component.weight = weight
        self.db.commit()
        policies = ensure_template_policies(self.db, fixture.year.name, fixture.admin)
        align_open_gradebook(self.db, book, fixture.admin, policies)
        self.db.commit()
        self.assertEqual([c.weight for c in book.components], [20, 60, 20])
        self.assertEqual([item.id for c in book.components for item in c.items], before_ids)
        after = grading.get_gradebook_full(self.db, book.id)
        self.assertEqual(after['students'][0]['scores'], before_scores)
        self.assertEqual(after['students'][0]['initial_grade'], 80)
        entries = [dict(assessment_item_id=item.id, score=item.max_score * ratio, status='Scored')
                   for component, ratio in zip(book.components, (1, 0.5, 0)) for item in component.items]
        grading.save_gradebook_scores(self.db, book.id, fixture.admin,
                                     {str(fixture.first.id): entries}, 'Verify corrected TLE weights')
        recalculated = grading.get_gradebook_full(self.db, book.id)
        self.assertEqual(recalculated['students'][0]['initial_grade'], 50)


if __name__ == '__main__':
    unittest.main()
