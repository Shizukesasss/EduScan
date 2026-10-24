"""Six advisory classes, isolated from live school records."""
import json
import unittest
from unittest.mock import patch
from sqlalchemy import select, func
from tests import test_grading_regressions as fixtures
from app.models import User, Subject, SchoolSection, SectionAdviserAssignment, SubjectTeachingAssignment, DemoTeacherSetupBatch
from app.services import demo_teacher_setup as setup


class DemoAdvisoryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ClassRecordRegressionTest()
        self.f.setUp()
        f = self.f
        f.configure_subject_export()
        self.subjects = []
        for code, name in [('FIL','FILIPINO'),('SCI','SCIENCE'),('VE','VALUES EDUCATION'),('TLE','TECHNOLOGY AND LIVELIHOOD EDUCATION'),('MAP','MAPEH'),('AP','ARALING PANLIPUNAN')]:
            item = Subject(code=code,name=name,category='JHS')
            f.db.add(item); self.subjects.append(item)
        f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def preview(self):
        return setup.preview_demo_advisory_setup(self.f.db,self.f.year.id,self.f.admin)

    def test_preview_creates_no_accounts_or_sections(self):
        f=self.f
        before=(f.db.query(User).count(),f.db.query(SchoolSection).count())
        p=self.preview()
        self.assertEqual(p['kind'],'six_advisory')
        self.assertEqual(len(p['teachers']),6)
        self.assertEqual({t['subject_id'] for t in p['teachers']},{s.id for s in self.subjects})
        self.assertEqual(len({t['username'] for t in p['teachers']}),6)
        self.assertEqual(len({t['new_section_name'] for t in p['teachers']}),6)
        self.assertTrue(all(t['grade']=='7' and t['program']=='BEP' and f.year.name in t['new_section_name'] for t in p['teachers']))
        self.assertEqual(before,(f.db.query(User).count(),f.db.query(SchoolSection).count()))

    def test_missing_subject_or_archived_collision_creates_nothing(self):
        f=self.f
        self.subjects[0].active=False; f.db.commit()
        with self.assertRaisesRegex(ValueError,'Filipino'):
            self.preview()
        self.assertEqual(f.db.query(DemoTeacherSetupBatch).count(),0)
        self.subjects[0].active=True
        from datetime import datetime
        f.db.add(SchoolSection(grade_level_id=f.grade.id,name=f'Demo Filipino {f.year.name}',deleted_at=datetime.utcnow()))
        f.db.commit()
        with self.assertRaisesRegex(ValueError,'already exists'):
            self.preview()

    def test_apply_has_six_advisers_and_does_not_repeat_credentials(self):
        f=self.f
        p=self.preview()
        result=setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        self.assertEqual(result['created_count'],6)
        self.assertEqual(len(result['created_section_ids']),6)
        self.assertEqual(len(result['credentials']),6)
        for uid,sid in zip(result['created_user_ids'],result['created_section_ids']):
            account=f.db.get(User,uid); section=f.db.get(SchoolSection,sid)
            self.assertTrue(account.is_demo and account.must_change_password)
            from app.auth import verify_password
            from app.main import my_advisory_sections
            credential=next(c for c in result['credentials'] if c['username']==account.username)
            self.assertTrue(verify_password(credential['temporary_password'],account.password_hash))
            self.assertEqual([row['id'] for row in my_advisory_sections(f.year.id,f.db,account)],[sid])
            self.assertEqual(section.track,'BEP')
            self.assertEqual(section.grade_level_id,f.grade.id)
            self.assertEqual(f.db.scalar(select(SectionAdviserAssignment.teacher_user_id).where(SectionAdviserAssignment.section_id==sid,SectionAdviserAssignment.school_year_id==f.year.id)),uid)
            self.assertEqual(f.db.scalar(select(func.count()).select_from(SubjectTeachingAssignment).where(SubjectTeachingAssignment.teacher_user_id==uid)),1)
        again=setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        self.assertTrue(again['already_applied']); self.assertEqual(again['credentials'],[])
        self.assertNotIn('temporary_password',f.db.get(DemoTeacherSetupBatch,p['batch_id']).result_json)
        existing=self.preview()
        self.assertTrue(existing['already_applied']); self.assertEqual(existing['credentials'],[])

    def test_second_preview_cannot_create_more_accounts(self):
        f=self.f
        one,two=self.preview(),self.preview()
        first=setup.apply_demo_teacher_setup(f.db,one['batch_id'],f.admin)
        second=setup.apply_demo_teacher_setup(f.db,two['batch_id'],f.admin)
        self.assertTrue(second['already_applied'])
        self.assertEqual(first['created_user_ids'],second['created_user_ids'])
        self.assertEqual(second['credentials'],[])
        self.assertEqual(f.db.query(User).filter(User.is_demo.is_(True)).count(),6)

    def test_failure_rolls_back_sections_and_accounts(self):
        f=self.f; p=self.preview()
        before=(f.db.query(User).count(),f.db.query(SchoolSection).count())
        with patch.object(setup,'assign_section_adviser',side_effect=ValueError('simulated')):
            with self.assertRaisesRegex(ValueError,'simulated'):
                setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        self.assertEqual(before,(f.db.query(User).count(),f.db.query(SchoolSection).count()))
        self.assertFalse(f.db.get(DemoTeacherSetupBatch,p['batch_id']).applied)

    def test_stale_preview_and_non_admin_are_rejected(self):
        f=self.f; p=self.preview()
        self.subjects[0].name='Changed Filipino'; f.db.commit()
        with self.assertRaisesRegex(ValueError,'new preview'):
            setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        with self.assertRaises(PermissionError):
            setup.preview_demo_advisory_setup(f.db,f.year.id,f.teacher)

    def test_preview_endpoint_is_admin_only_and_validates_year(self):
        from app.main import app
        from fastapi import HTTPException
        from pydantic import ValidationError
        from app import schemas
        route=next((route for route in app.routes if getattr(route,'path',None)=='/api/admin/demo-teacher-setup/advisory-preview'),None)
        self.assertIsNotNone(route)
        auth=next(d.call for d in route.dependant.dependencies if d.name=='actor')
        self.f.admin.must_change_password=False
        self.assertIs(auth(user=self.f.admin),self.f.admin)
        for role in ('teacher','records_officer','school_head'):
            with self.assertRaises(HTTPException):
                auth(user=User(role=role,full_name='Denied',username=role,password_hash='unused'))
        with self.assertRaises(ValidationError):
            schemas.DedicatedDemoAdvisoryPayload(school_year_id=0)

    def test_apply_preserves_existing_records_and_credential_secrecy(self):
        from app.models import Person,AttendanceEvent,SystemAuditEvent
        from app.models_grading import Gradebook,StudentScore
        from sqlalchemy import inspect
        f=self.f
        def snapshot():
            return {m.__tablename__: [[getattr(row,c.key) for c in inspect(m).columns] for row in f.db.scalars(select(m).order_by(m.id)).all()] for m in (Person,AttendanceEvent,Gradebook,StudentScore,SchoolSection,SectionAdviserAssignment,SubjectTeachingAssignment)}
        before=snapshot(); p=self.preview()
        result=setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        after=snapshot()
        for name,rows in before.items():
            self.assertEqual(after[name][:len(rows)],rows)
        stored=f.db.get(DemoTeacherSetupBatch,p['batch_id'])
        audits=' '.join(row.before_json+row.after_json for row in f.db.scalars(select(SystemAuditEvent)).all())
        for credential in result['credentials']:
            self.assertNotIn(credential['temporary_password'],stored.proposal_json+stored.result_json+audits)

    def test_invalid_context_and_ambiguous_aliases_fail_closed(self):
        from app.models import GradeLevel
        f=self.f
        f.year.active=False; f.db.commit()
        with self.assertRaisesRegex(ValueError,'active school year'): self.preview()
        f.year.active=True
        duplicate=GradeLevel(name='Grade 7')
        f.db.add(duplicate); f.db.commit()
        with self.assertRaisesRegex(ValueError,'Exactly one active Grade 7'): self.preview()
        duplicate.active=False
        alias=Subject(code='OTHER-VE',name='VE',category='JHS')
        f.db.add(alias); f.db.commit()
        with self.assertRaisesRegex(ValueError,'Values Education'): self.preview()
        alias.active=False
        self.subjects[0].category='SHS'
        f.db.commit()
        with self.assertRaisesRegex(ValueError,'Filipino'): self.preview()
        self.assertEqual(f.db.query(DemoTeacherSetupBatch).count(),0)

    def test_year_lock_precedes_sibling_batch_check(self):
        from sqlalchemy import event
        from sqlalchemy.dialects import postgresql
        f=self.f; p=self.preview(); seen=[]
        def trace(state):
            if state.is_select:
                seen.append(str(state.statement.compile(dialect=postgresql.dialect())))
        event.listen(f.db,'do_orm_execute',trace)
        try:
            setup.apply_demo_teacher_setup(f.db,p['batch_id'],f.admin)
        finally:
            event.remove(f.db,'do_orm_execute',trace)
        year_lock=next(i for i,sql in enumerate(seen) if 'FROM school_years' in sql and 'FOR UPDATE' in sql)
        siblings=next(i for i,sql in enumerate(seen) if 'demo_teacher_setup_batches.applied IS true' in sql)
        self.assertLess(year_lock,siblings)
