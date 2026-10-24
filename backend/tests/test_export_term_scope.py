import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from tests import test_grading_regressions as fixtures
from fastapi import HTTPException
from app.main import gradebook_report_xlsx_new
from app.models import GradingPeriod, SubjectTeachingAssignment, User


class ExportTermScopeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ClassRecordRegressionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def make_book(self, quarter):
        f = self.fixture
        period = GradingPeriod(school_year_id=f.year.id, quarter=quarter, name=f'Term {quarter}',
                               starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        f.db.add(period)
        f.db.commit()
        book = f.create(f.specific, grading_period_id=period.id)
        book.teacher_user_id, book.teacher_name, book.status = f.teacher.id, f.teacher.full_name, 'Finalized'
        if quarter == 2:
            f.db.add(SubjectTeachingAssignment(school_year_id=f.year.id, section_id=f.section.id,
                subject_id=f.subject.id, teacher_user_id=f.teacher.id, active=True))
        f.db.commit()
        return book

    def test_assigned_teacher_can_export_two_or_three_terms(self):
        f = self.fixture
        full = {'students': [{}], 'statistics': {'incomplete': 0}}
        with TemporaryDirectory(dir=Path(fixtures.TEST_DIR.name)) as directory:
            for quarter, scope in ((2, {'through_term': 2}), (3, {'all_terms': True})):
                book = self.make_book(quarter)
                path = Path(directory) / f'term-{quarter}.xlsx'
                path.write_bytes(b'isolated export')
                report = SimpleNamespace(file_path=str(path), filename=path.name)
                with self.subTest(scope=scope), \
                     patch('app.main.grading_service.get_gradebook_full', return_value=full), \
                     patch('app.main.generate_gradebook_report_xlsx', return_value=path) as export, \
                     patch('app.main.register_report', return_value=report):
                    response = gradebook_report_xlsx_new(book.id, db=f.db, user=f.teacher, **scope)
                    self.assertEqual(response.path, str(path))
                    self.assertEqual(export.call_args.kwargs['allowed_teacher_id'], f.teacher.id)
                    self.assertEqual(export.call_args.kwargs['through_term'], scope.get('through_term'))
                    self.assertEqual(export.call_args.kwargs['all_terms'], scope.get('all_terms', False))

    def test_unassigned_teacher_cannot_export_another_teachers_terms(self):
        f = self.fixture
        book = self.make_book(2)
        other = User(username='unassigned', full_name='Unassigned Teacher', password_hash='unused', role='teacher')
        f.db.add(other)
        f.db.commit()
        with self.assertRaises(HTTPException) as denied:
            gradebook_report_xlsx_new(book.id, through_term=2, db=f.db, user=other)
        self.assertEqual(denied.exception.status_code, 403)

    def test_admin_and_school_head_still_cannot_export_combined_terms(self):
        for role in ('school_head', 'admin'):
            with self.subTest(role=role), self.assertRaises(HTTPException) as denied:
                gradebook_report_xlsx_new(1, through_term=2, db=Mock(), user=SimpleNamespace(role=role))
            self.assertEqual(denied.exception.status_code, 403)

    def test_invalid_or_conflicting_scope_is_rejected(self):
        for arguments in ({'through_term': 1}, {'through_term': 3}, {'through_term': 2, 'all_terms': True}):
            with self.subTest(arguments=arguments), self.assertRaises(HTTPException) as denied:
                gradebook_report_xlsx_new(1, **arguments, db=Mock(), user=SimpleNamespace(role='records_officer'))
            self.assertEqual(denied.exception.status_code, 422)

    def test_two_terms_requires_selected_term_two(self):
        db = Mock()
        db.get.return_value = SimpleNamespace(quarter=1)
        with patch('app.main.ensure_gradebook_access'), self.assertRaises(HTTPException) as denied:
            gradebook_report_xlsx_new(1, through_term=2, db=db, user=SimpleNamespace(role='records_officer'))
        self.assertEqual(denied.exception.status_code, 422)
