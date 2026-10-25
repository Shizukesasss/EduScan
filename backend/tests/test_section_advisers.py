import unittest
from tests import test_grading_regressions as fixtures
from app.models import SchoolYear, SchoolSection
from app.services.section_advisers import assign_section_adviser, adviser_for_section


class SectionAdviserTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ClassRecordRegressionTest()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_years_keep_separate_advisers(self):
        f = self.f
        following = SchoolYear(name='2027-2028', starts_on=fixtures.date(2027, 6, 1), ends_on=fixtures.date(2028, 3, 31))
        f.db.add(following)
        f.db.flush()
        assign_section_adviser(f.db, f.year.id, f.section.id, f.teacher.id)
        self.assertIsNone(adviser_for_section(f.db, following.id, f.section.id))
        assign_section_adviser(f.db, following.id, f.section.id, f.teacher.id)
        self.assertEqual(adviser_for_section(f.db, f.year.id, f.section.id).id, f.teacher.id)
        self.assertEqual(adviser_for_section(f.db, following.id, f.section.id).id, f.teacher.id)

    def test_one_advisory_section_per_year(self):
        f = self.f
        other = SchoolSection(grade_level_id=f.grade.id, name='Other Section')
        f.db.add(other)
        f.db.flush()
        assign_section_adviser(f.db, f.year.id, f.section.id, f.teacher.id)
        with self.assertRaisesRegex(ValueError, 'one section per school year'):
            assign_section_adviser(f.db, f.year.id, other.id, f.teacher.id)

    def test_lookup_does_not_borrow_legacy_or_another_year(self):
        f = self.f
        from app.models import SectionAdviserAssignment
        from sqlalchemy import delete
        f.db.execute(delete(SectionAdviserAssignment))
        f.db.flush()
        self.assertEqual(f.section.adviser_user_id, f.teacher.id)
        self.assertIsNone(adviser_for_section(f.db, f.year.id, f.section.id))

    def test_inactive_teacher_is_rejected(self):
        f = self.f
        f.teacher.active = False
        f.db.flush()
        with self.assertRaisesRegex(ValueError, 'active teacher'):
            assign_section_adviser(f.db, f.year.id, f.section.id, f.teacher.id)

    def test_legacy_gradebook_access_uses_saved_year(self):
        from app.main import ensure_legacy_gradebook_access
        from app.models import GradebookState, User
        from fastapi import HTTPException
        f = self.f
        next_year = SchoolYear(name='2027-2028', starts_on=fixtures.date(2027, 6, 1), ends_on=fixtures.date(2028, 3, 31))
        replacement = User(username='replacement', full_name='Next Adviser', role='teacher', password_hash='unused')
        f.db.add_all([next_year, replacement])
        f.db.flush()
        assign_section_adviser(f.db, next_year.id, f.section.id, replacement.id)
        f.db.add(GradebookState(class_key='historical', grade=f.grade.name, section=f.section.name, school_year=next_year.name, term_order=1, subject='Core'))
        f.db.flush()
        ensure_legacy_gradebook_access(f.db, replacement, 'historical')
        with self.assertRaises(HTTPException) as denied:
            ensure_legacy_gradebook_access(f.db, f.teacher, 'historical')
        self.assertEqual(denied.exception.status_code, 403)


    def test_migration_backfills_2026_only_and_is_idempotent(self):
        from app.migrations import MIGRATIONS, run_migrations
        from app.models import SectionAdviserAssignment
        from sqlalchemy import text, select, delete
        f = self.f
        f.db.execute(delete(SectionAdviserAssignment))
        f.db.add(SchoolYear(name='2027-2028', starts_on=fixtures.date(2027, 6, 1), ends_on=fixtures.date(2028, 3, 31)))
        f.db.commit()
        with f.engine.begin() as connection:
            connection.execute(text('CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description VARCHAR(255), applied_at TIMESTAMP)'))
            for version, description in MIGRATIONS:
                if version == '0022_annual_advisers_demo_setup':
                    continue
                connection.execute(text('INSERT INTO schema_migrations VALUES (:v,:d,CURRENT_TIMESTAMP)'), {'v':version,'d':description})
        self.assertEqual(run_migrations(f.engine), ['0022_annual_advisers_demo_setup'])
        self.assertEqual(run_migrations(f.engine), [])
        f.db.expire_all()
        rows = f.db.scalars(select(SectionAdviserAssignment)).all()
        self.assertEqual([(r.school_year_id, r.section_id, r.teacher_user_id) for r in rows], [(f.year.id,f.section.id,f.teacher.id)])
        self.assertFalse(f.teacher.is_demo)

    def test_report_scope_follows_report_year(self):
        from app.main import report_sections
        from app.models import User
        f = self.f
        next_year = SchoolYear(name='2027-2028', starts_on=fixtures.date(2027,6,1), ends_on=fixtures.date(2028,3,31))
        replacement = User(username='next', full_name='Next Adviser', role='teacher', password_hash='unused')
        f.db.add_all([next_year,replacement]); f.db.flush()
        assign_section_adviser(f.db,next_year.id,f.section.id,replacement.id)
        self.assertTrue(report_sections(f.db,f.teacher,school_year_name=f.year.name))
        self.assertFalse(report_sections(f.db,f.teacher,school_year_name=next_year.name))
        self.assertTrue(report_sections(f.db,replacement,school_year_name=next_year.name))

    def test_migration_rejects_duplicate_legacy_advisers_without_losing_links(self):
        from app.migrations import MIGRATIONS, run_migrations
        from app.models import SectionAdviserAssignment
        from sqlalchemy import text, delete
        f = self.f
        f.db.execute(delete(SectionAdviserAssignment))
        second = SchoolSection(grade_level_id=f.grade.id, name='Second Legacy', adviser_user_id=f.teacher.id)
        f.db.add(second); f.db.commit()
        with f.engine.begin() as connection:
            connection.execute(text('CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description VARCHAR(255), applied_at TIMESTAMP)'))
            for version, description in MIGRATIONS:
                if version == '0022_annual_advisers_demo_setup':
                    continue
                connection.execute(text('INSERT INTO schema_migrations VALUES (:v,:d,CURRENT_TIMESTAMP)'), {'v':version,'d':description})
        with self.assertRaisesRegex(ValueError, 'multiple sections'):
            run_migrations(f.engine)
        f.db.expire_all()
        self.assertEqual(f.db.get(SchoolSection,second.id).adviser_user_id,f.teacher.id)
        self.assertEqual(f.db.get(SchoolSection,f.section.id).adviser_user_id,f.teacher.id)

    def test_migration_keeps_deleted_section_links_archived(self):
        from app.migrations import MIGRATIONS, run_migrations
        from app.models import SectionAdviserAssignment
        from sqlalchemy import text, select, delete
        from datetime import datetime
        f=self.f
        f.db.execute(delete(SectionAdviserAssignment))
        archived=SchoolSection(grade_level_id=f.grade.id,name='Archived',adviser_user_id=f.teacher.id,deleted_at=datetime.utcnow())
        f.db.add(archived); f.db.commit()
        with f.engine.begin() as connection:
            connection.execute(text('CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description VARCHAR(255), applied_at TIMESTAMP)'))
            for version, description in MIGRATIONS:
                if version == '0022_annual_advisers_demo_setup':
                    continue
                connection.execute(text('INSERT INTO schema_migrations VALUES (:v,:d,CURRENT_TIMESTAMP)'), {'v':version,'d':description})
        run_migrations(f.engine)
        f.db.expire_all()
        rows=f.db.scalars(select(SectionAdviserAssignment)).all()
        self.assertEqual([row.section_id for row in rows],[f.section.id])
        self.assertEqual(f.db.get(SchoolSection,archived.id).adviser_user_id,f.teacher.id)
