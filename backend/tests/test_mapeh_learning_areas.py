import unittest
from tests import test_grading_regressions as f
from app.services import grading
from app.models_grading import StudentScore
from sqlalchemy import select,func

class MapehAreasTests(unittest.TestCase):
 def setUp(self):
  self.f=f.ClassRecordRegressionTest();self.f.setUp()
  self.addCleanup(self.f.tearDown)
  x=self.f;x.grade.name='7';x.first.grade=x.second.grade='7';x.subject.name='MAPEH';x.subject.category='JHS';x.db.commit()
 def area(self,area):return self.f.create(learning_area=area)
 def test_separate_empty_area_records_and_idempotency(self):
  a=self.area('music_arts');b=self.area('pe_health')
  self.assertNotEqual(a.id,b.id);self.assertEqual(self.area('music_arts').id,a.id)
  self.assertEqual([c.weight for c in a.components],[20,60,20])
  self.assertEqual([i.label for i in a.components[-1].items],['ST1','ST2','TE'])
  self.assertEqual(self.f.db.scalar(select(func.count(StudentScore.id))),0)
 def test_invalid_area_rejected(self):
  with self.assertRaises(ValueError):self.area('unknown')
 def test_legacy_all_service_mutations_rejected(self):
  x=self.f;book=x.create(x.general);book.is_legacy_readonly=True;x.db.commit()
  for operation in (lambda:grading.save_gradebook_scores(x.db,book.id,x.teacher,{},'test'),lambda:grading.reopen_gradebook(x.db,book.id,x.admin,'test'),lambda:grading.finalize_gradebook(x.db,book.id,x.teacher,'test')):
   with self.assertRaises(ValueError):operation()

 def test_activation_preview_staleness_and_preservation(self):
  from app.services.mapeh_learning_areas import preview_mapeh_activation,apply_mapeh_activation
  x=self.f;old=x.create(x.general);x.score_student(old,80);x.score_second_student(old,70)
  old.status='Finalized';x.db.commit()
  before=grading.get_gradebook_full(x.db,old.id)
  preview=preview_mapeh_activation(x.db)
  self.assertFalse(old.is_legacy_readonly)
  with self.assertRaises(ValueError):apply_mapeh_activation(x.db,'wrong',x.admin)
  result=apply_mapeh_activation(x.db,preview['hash'],x.admin);x.db.commit()
  self.assertTrue(old.is_legacy_readonly);self.assertEqual(old.status,'Finalized')
  after=grading.get_gradebook_full(x.db,old.id)
  self.assertEqual(before['students'],after['students']);self.assertEqual(before['components'],after['components']);self.assertEqual(before['policy'],after['policy'])
  self.assertEqual(len(result['area_gradebook_ids']),0)  # No teaching assignment in this fixture.
  again=apply_mapeh_activation(x.db,preview_mapeh_activation(x.db)['hash'],x.admin);x.db.commit()
  self.assertEqual(again['area_gradebook_ids'],result['area_gradebook_ids'])
 def test_legacy_component_and_adjustment_paths_reject(self):
  x=self.f;book=x.create(x.general);book.is_legacy_readonly=True;x.db.commit()
  for op in (lambda:grading.update_gradebook_components(x.db,book.id,x.teacher,[],'Testing'),lambda:grading.create_criteria_adjustment_request(x.db,book.id,x.teacher,{},'Testing'),lambda:grading.submit_gradebook(x.db,book.id,x.teacher,'Testing'),lambda:grading.lock_gradebook(x.db,book.id,x.admin,'Testing')):
   with self.assertRaises(ValueError):op()
 def test_area_rejects_wrong_subject_and_schema_requires_approval(self):
  from app.migrations import upgrade_mapeh_area_schema
  x=self.f;x.subject.name='SCIENCE';x.db.commit()
  with self.assertRaises(ValueError):self.area('music_arts')
  with self.assertRaises(ValueError):upgrade_mapeh_area_schema(x.engine)

 def test_legacy_policy_alignment_rejected(self):
  from app.services.template_policies import align_open_gradebook
  x=self.f;book=x.create(x.general);book.is_legacy_readonly=True;x.db.commit()
  with self.assertRaises(ValueError):align_open_gradebook(x.db,book,x.admin,{})
 def test_activation_creates_six_empty_assigned_area_books(self):
  from app.models import SubjectTeachingAssignment,GradingPeriod
  from datetime import date
  from app.services.mapeh_learning_areas import preview_mapeh_activation,apply_mapeh_activation
  x=self.f;old=x.create(x.general)
  for term in (2,3):x.db.add(GradingPeriod(school_year_id=x.year.id,quarter=term,name=f'Term {term}',starts_on=date(2026,9,1),ends_on=date(2027,3,31)))
  x.db.add(SubjectTeachingAssignment(school_year_id=x.year.id,subject_id=x.subject.id,section_id=x.section.id,teacher_user_id=x.teacher.id,active=True));x.db.commit()
  with self.assertRaises(ValueError):apply_mapeh_activation(x.db,preview_mapeh_activation(x.db)['hash'],x.teacher)
  result=apply_mapeh_activation(x.db,preview_mapeh_activation(x.db)['hash'],x.admin);x.db.commit()
  self.assertEqual(len(result['area_gradebook_ids']),6)
  self.assertEqual(x.db.scalar(select(func.count(StudentScore.id))),0)
  self.assertTrue(old.is_legacy_readonly)

 def test_preview_preserves_existing_area_and_hashes_its_scores(self):
  from app.models import SubjectTeachingAssignment
  from app.services.mapeh_learning_areas import preview_mapeh_activation,apply_mapeh_activation
  x=self.f;x.create(x.general);area=self.area('music_arts')
  x.db.add(SubjectTeachingAssignment(school_year_id=x.year.id,subject_id=x.subject.id,section_id=x.section.id,teacher_user_id=x.teacher.id,active=True));x.db.commit()
  before=preview_mapeh_activation(x.db)
  self.assertIn(area.id,before['existing_area_ids'])
  self.assertNotIn('music_arts',[c['learning_area'] for c in before['planned_empty_area_contexts']])
  x.score_student(area,80)
  with self.assertRaises(ValueError):apply_mapeh_activation(x.db,before['hash'],x.admin)
