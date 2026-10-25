import unittest
from unittest.mock import patch
from tests import test_grading_regressions as fixtures
from app.models import Subject
from app.services.academic_context import subject_matches_grade
from app.main import save_subject
from app.schemas import SubjectPayload
from fastapi import HTTPException


class ElectiveGradeTests(unittest.TestCase):
    def test_new_assignment_and_schedule_reject_disallowed_grade(self):
        from types import SimpleNamespace
        from app.main import save_schedule, save_subject_teaching_assignments
        f = fixtures.ClassRecordRegressionTest()
        f.setUp()
        try:
            f.configure_subject_export()
            f.subject.is_elective = True
            f.subject.allowed_grades = [8]
            f.section.track = 'STE'
            f.db.commit()
            with self.assertRaises(HTTPException) as schedule_error:
                save_schedule(SimpleNamespace(teacher_user_id=f.teacher.id, grade='7', section=f.section.name, subject=f.subject.name), db=f.db, user=f.admin)
            self.assertEqual(schedule_error.exception.status_code, 422)
            with self.assertRaises(HTTPException) as assignment_error:
                save_subject_teaching_assignments(SimpleNamespace(school_year_id=f.year.id, subject_id=f.subject.id, teacher_user_id=f.teacher.id, section_ids=[f.section.id]), db=f.db, actor=f.admin)
            self.assertEqual(assignment_error.exception.status_code, 422)
        finally:
            f.tearDown()

    def test_single_multiple_and_legacy_grades(self):
        subject = Subject(category='JHS', is_elective=True)
        self.assertTrue(subject_matches_grade(subject, 'Grade 8'))
        subject.allowed_grades = [7]
        self.assertTrue(subject_matches_grade(subject, 'Grade 7'))
        self.assertFalse(subject_matches_grade(subject, '8'))
        subject.allowed_grades = [7, 8]
        self.assertTrue(subject_matches_grade(subject, 'Grade 8'))
        self.assertFalse(subject_matches_grade(subject, '11'))

    def test_invalid_selections_are_rejected(self):
        for grades in ([], [11], [7, 12]):
            with self.subTest(grades=grades), self.assertRaises(HTTPException):
                save_subject(SubjectPayload(code='R1', name='Research 1', is_elective=True, allowed_grades=grades))

    def test_existing_record_survives_narrowing_but_new_record_is_blocked(self):
        f = fixtures.ClassRecordRegressionTest()
        f.setUp()
        try:
            f.configure_subject_export()
            f.subject.is_elective = True
            f.section.track = 'STE'
            f.db.commit()
            book = f.create(f.general)
            before = fixtures.grading.get_gradebook_full(f.db, book.id)
            f.subject.allowed_grades = [8]
            f.db.commit()
            self.assertEqual(before, fixtures.grading.get_gradebook_full(f.db, book.id))
            self.assertEqual(f.create(f.general).id, book.id)
            period = fixtures.GradingPeriod(school_year_id=f.year.id, term_order=2, name='Term 2', starts_on=fixtures.date(2026, 6, 1), ends_on=fixtures.date(2027, 3, 31))
            f.db.add(period)
            f.db.commit()
            with self.assertRaisesRegex(ValueError, 'not allowed'):
                f.create(f.general, grading_period_id=period.id)
        finally:
            f.tearDown()

    def test_migration_is_idempotent(self):
        from sqlalchemy import create_engine, inspect
        from app.migrations import run_migrations
        engine = create_engine('sqlite://')
        try:
            run_migrations(engine)
            self.assertIn('allowed_grades_json', [c['name'] for c in inspect(engine).get_columns('subjects')])
            self.assertEqual(run_migrations(engine), [])
        finally:
            engine.dispose()
