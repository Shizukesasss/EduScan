import json
import unittest
from unittest.mock import patch
from sqlalchemy import select, func
from tests import test_grading_regressions as fixtures
from app.models import User, SchoolSection, SubjectTeachingAssignment, SectionAdviserAssignment, DemoTeacherSetupBatch
from app.services.section_advisers import assign_section_adviser
from app.services.demo_teacher_setup import preview_demo_teacher_setup, apply_demo_teacher_setup


class DemoTeacherSetupTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ClassRecordRegressionTest()
        self.f.setUp()
        f = self.f
        f.configure_subject_export()
        self.other = SchoolSection(grade_level_id=f.grade.id, name='Second Demo Section', track='BEP')
        f.db.add(self.other)
        f.db.flush()
        assign_section_adviser(f.db, f.year.id, f.section.id, f.teacher.id)
        f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def preview(self):
        f = self.f
        return preview_demo_teacher_setup(f.db, f.year.id, [f.section.id, self.other.id], f.admin)

    def test_preview_and_confirm_preserve_existing_adviser_and_are_idempotent(self):
        f = self.f
        before = f.db.scalar(select(func.count(User.id)))
        preview = self.preview()
        self.assertEqual(f.db.scalar(select(func.count(User.id))), before)
        self.assertEqual(preview['preserved_adviser_assignments'], 1)
        self.assertTrue(preview['teachers'])
        self.assertTrue(all('TEST' not in item['full_name'] for item in preview['teachers']))
        result = apply_demo_teacher_setup(f.db, preview['batch_id'], f.admin)
        self.assertEqual(result['created_count'], len(preview['teachers']))
        self.assertEqual(len(result['credentials']), result['created_count'])
        for account in f.db.scalars(select(User).where(User.is_demo.is_(True))).all():
            self.assertEqual(account.role, 'teacher')
            self.assertTrue(account.must_change_password)
            self.assertNotEqual(account.password_hash, next(item['temporary_password'] for item in result['credentials'] if item['username'] == account.username))
            assignments = f.db.scalars(select(SubjectTeachingAssignment).where(SubjectTeachingAssignment.teacher_user_id == account.id)).all()
            self.assertEqual(len({a.subject_id for a in assignments}), 1)
        batch = f.db.get(DemoTeacherSetupBatch, preview['batch_id'])
        self.assertNotIn('temporary_password', batch.result_json)
        repeated = apply_demo_teacher_setup(f.db, preview['batch_id'], f.admin)
        self.assertTrue(repeated['already_applied'])
        self.assertEqual(repeated['credentials'], [])
        self.assertEqual(f.db.scalar(select(func.count(User.id))), before + result['created_count'])
        original = f.db.scalar(select(SectionAdviserAssignment).where(SectionAdviserAssignment.section_id == f.section.id))
        self.assertEqual(original.teacher_user_id, f.teacher.id)

    def test_stale_preview_creates_nothing(self):
        f = self.f
        preview = self.preview()
        self.other.name = 'Changed after preview'
        f.db.commit()
        with self.assertRaisesRegex(ValueError, 'Generate a new preview'):
            apply_demo_teacher_setup(f.db, preview['batch_id'], f.admin)
        self.assertEqual(f.db.scalar(select(func.count(User.id)).where(User.is_demo.is_(True))), 0)

    def test_failure_rolls_back_accounts_and_assignments(self):
        f = self.f
        preview = self.preview()
        with patch('app.services.demo_teacher_setup.assign_section_adviser', side_effect=ValueError('simulated failure')):
            with self.assertRaisesRegex(ValueError, 'simulated failure'):
                apply_demo_teacher_setup(f.db, preview['batch_id'], f.admin)
        self.assertEqual(f.db.scalar(select(func.count(User.id)).where(User.is_demo.is_(True))), 0)
        self.assertFalse(f.db.get(DemoTeacherSetupBatch, preview['batch_id']).applied)

    def test_non_admin_cannot_preview_or_apply(self):
        f = self.f
        with self.assertRaises(PermissionError):
            preview_demo_teacher_setup(f.db, f.year.id, [f.section.id], f.teacher)
        with self.assertRaises(PermissionError):
            apply_demo_teacher_setup(f.db, 'not-a-batch', f.teacher)

    def test_no_missing_slots_does_not_replace_existing_teacher_for_advisory(self):
        f = self.f
        f.db.add(SubjectTeachingAssignment(school_year_id=f.year.id, subject_id=f.subject.id, section_id=self.other.id, teacher_user_id=f.teacher.id, active=True))
        f.db.commit()
        preview = self.preview()
        self.assertTrue(any(row['section_id'] == self.other.id for row in preview['unresolved']))
        self.assertFalse(any(self.other.id in row['section_ids'] for row in preview['teachers']))

    def test_names_and_usernames_do_not_collide_with_existing_accounts(self):
        f = self.f
        f.db.add(User(username='DEMO.LISA.MANOBAN', full_name='Other Person', role='teacher', password_hash='unused'))
        f.db.commit()
        preview = self.preview()
        self.assertEqual(preview['teachers'][0]['full_name'], 'Lisa Manoban')
        self.assertNotEqual(preview['teachers'][0]['username'].casefold(), 'demo.lisa.manoban')

    def test_missing_advisers_split_subject_coverage_without_changing_existing_slots(self):
        f = self.f
        from sqlalchemy import delete
        f.db.execute(delete(SectionAdviserAssignment))
        f.db.execute(delete(SubjectTeachingAssignment))
        f.db.commit()
        preview = self.preview()
        advisers = [p['adviser_section_id'] for p in preview['teachers'] if p['adviser_section_id']]
        self.assertEqual(set(advisers), {f.section.id, self.other.id})
        self.assertEqual(len(advisers), 2)
        slots = [(section_id,p['subject_id']) for p in preview['teachers'] for section_id in p['section_ids']]
        self.assertEqual(len(slots),len(set(slots)))

    def test_unknown_batch_and_other_admin_are_rejected(self):
        f = self.f
        with self.assertRaisesRegex(ValueError, 'not found'):
            apply_demo_teacher_setup(f.db, 'missing', f.admin)
        other = User(username='admin-two', full_name='Other Admin', role='admin', password_hash='unused')
        f.db.add(other); f.db.commit()
        preview = self.preview()
        with self.assertRaisesRegex(ValueError, 'not found'):
            apply_demo_teacher_setup(f.db, preview['batch_id'], other)

    def test_elective_grade_and_program_restrictions_are_preserved(self):
        from app.models import Subject
        f = self.f
        allowed = Subject(code='DEMO-ELECTIVE',name='Demo Research',category='JHS',is_elective=True,elective_track='STE',allowed_grades_json='[7]')
        wrong_grade = Subject(code='DEMO-G8',name='Research Grade Eight',category='JHS',is_elective=True,elective_track='STE',allowed_grades_json='[8]')
        inactive = Subject(code='DEMO-INACTIVE',name='Inactive Subject',category='JHS',active=False)
        f.section.track='STE'
        f.db.add_all([allowed,wrong_grade,inactive]); f.db.commit()
        preview=self.preview()
        pairs={(section_id,p['subject_id']) for p in preview['teachers'] for section_id in p['section_ids']}
        self.assertIn((f.section.id,allowed.id),pairs)
        self.assertNotIn((self.other.id,allowed.id),pairs)
        self.assertFalse(any(subject_id in {wrong_grade.id,inactive.id} for _,subject_id in pairs))

    def test_apply_preserves_students_scores_attendance_and_gradebooks(self):
        from sqlalchemy import inspect
        from app.models import Person,AttendanceEvent
        from app.models_grading import Gradebook,StudentScore
        f=self.f
        def snapshot():
            return {model.__tablename__: [[getattr(row,column.key) for column in inspect(model).columns] for row in f.db.scalars(select(model).order_by(model.id)).all()] for model in (Person,AttendanceEvent,Gradebook,StudentScore)}
        before=snapshot()
        apply_demo_teacher_setup(f.db,self.preview()['batch_id'],f.admin)
        self.assertEqual(snapshot(),before)
