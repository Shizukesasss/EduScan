"""Admin setup deletion with real foreign keys, isolated from school data."""
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory(prefix="eduscan-academic-delete-", dir=os.environ.get("EDUSCAN_TEST_TEMP_DIR"))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = TEST_DIR.name
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-academic-deletion-tests"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import create_token
from app.database import Base, get_db
from app.main import app, seed_reference_data
from app.migrations import MIGRATIONS, run_migrations
from app.models import GradeLevel, GradingPeriod, Person, SchoolSection, SchoolYear, Subject, SubjectTeachingAssignment, SystemAuditEvent, User
from app.models_grading import AssessmentItem, Gradebook, GradebookComponent, StudentScore


class AcademicDeletionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="admin", role="admin", full_name="Admin", password_hash="unused", must_change_password=False)
        self.teacher = User(username="teacher", role="teacher", full_name="Teacher", password_hash="unused", must_change_password=False)
        self.records = User(username="records", role="records_officer", full_name="Records", password_hash="unused", must_change_password=False)
        self.grade = GradeLevel(name="10")
        self.subject = Subject(code="MATH", name="Mathematics")
        self.year = SchoolYear(name="2026-2027", starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        self.person = Person(external_id="TEST-STUDENT", full_name="Test Student", role="Student", sex="Male", grade="10", section="Rizal")
        self.db.add_all([self.admin, self.teacher, self.records, self.grade, self.subject, self.year, self.person])
        self.db.flush()
        self.section = SchoolSection(grade_level_id=self.grade.id, name="Rizal", adviser_user_id=self.teacher.id)
        self.period = GradingPeriod(school_year_id=self.year.id, name="Q1", quarter=1, starts_on=date(2026, 6, 1), ends_on=date(2026, 8, 31))
        self.db.add_all([self.section, self.period])
        self.db.flush()
        self.book = Gradebook(school_year_id=self.year.id, grading_period_id=self.period.id, grade_level_id=self.grade.id,
                             section_id=self.section.id, subject_id=self.subject.id, teacher_user_id=self.teacher.id,
                             school_year_name=self.year.name, grade_name=self.grade.name, section_name=self.section.name,
                             subject_name=self.subject.name, teacher_name=self.teacher.full_name, status="Finalized")
        self.db.add(self.book)
        self.db.flush()
        component = GradebookComponent(gradebook_id=self.book.id, name="Written Work", weight=100)
        self.db.add(component)
        self.db.flush()
        item = AssessmentItem(component_id=component.id, label="Quiz", max_score=20)
        self.db.add(item)
        self.db.flush()
        self.score = StudentScore(person_id=self.person.id, assessment_item_id=item.id, score=18, status="Scored", updated_by=self.teacher.id)
        self.db.add(self.score)
        self.db.commit()
        def session_override():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = session_override
        self.client = TestClient(app)  # No startup against the configured database.
        self.headers = {"Authorization": f"Bearer {create_token(self.admin)}"}
        self.teacher_headers = {"Authorization": f"Bearer {create_token(self.teacher)}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def remove(self, kind, item):
        response = self.client.delete(f"/api/admin/reference/{kind}/{item.id}", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_linked_grade_section_and_subject_can_be_deleted_and_restored(self):
        listed = self.client.get("/api/gradebooks", headers=self.headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertIn(self.book.id, [row["id"] for row in listed.json()])
        for kind, item, key in [("subjects", self.subject, "subjects"), ("sections", self.section, "sections"), ("grade-levels", self.grade, "grade_levels"), ("school-years", self.year, "school_years"), ("grading-periods", self.period, "grading_periods")]:
            with self.subTest(kind=kind):
                self.assertTrue(self.remove(kind, item).json()["records_preserved"])
                listed = self.client.get("/api/gradebooks", headers=self.headers)
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertNotIn(self.book.id, [row["id"] for row in listed.json()])
                for headers in (self.headers, self.teacher_headers):
                    visible = self.client.get("/api/admin/academic-structure?context=grading", headers=headers).json()
                    self.assertNotIn(item.id, [row["id"] for row in visible[key]])
                self.db.expire_all()
                self.assertIsNotNone(self.db.get(type(item), item.id))
                self.assertEqual(self.db.get(StudentScore, self.score.id).score, 18)
                self.assertEqual(self.db.get(Gradebook, self.book.id).status, "Finalized")
                self.assertIsNotNone(self.db.get(Person, self.person.id))
                self.assertEqual(self.client.get(f"/api/gradebooks/{self.book.id}", headers=self.teacher_headers).status_code, 200)
                deleted = self.client.get("/api/admin/reference-deleted", headers=self.headers).json()
                self.assertIn((kind, item.id), [(row["kind"], row["id"]) for row in deleted])
                restored = self.client.post(f"/api/admin/reference/{kind}/{item.id}/restore", headers=self.headers)
                self.assertEqual(restored.status_code, 200, restored.text)
                listed = self.client.get("/api/gradebooks", headers=self.headers)
                self.assertIn(self.book.id, [row["id"] for row in listed.json()])
                visible = self.client.get("/api/admin/academic-structure", headers=self.headers).json()
                self.assertIn(item.id, [row["id"] for row in visible[key]])

    def test_non_admin_roles_cannot_delete_restore_or_list_deleted(self):
        for user in (self.teacher, self.records):
            headers = {"Authorization": f"Bearer {create_token(user)}"}
            for kind, item in (("school-years", self.year), ("grading-periods", self.period), ("grade-levels", self.grade), ("sections", self.section), ("subjects", self.subject)):
                self.assertEqual(self.client.delete(f"/api/admin/reference/{kind}/{item.id}", headers=headers).status_code, 403)
                self.assertEqual(self.client.post(f"/api/admin/reference/{kind}/{item.id}/restore", headers=headers).status_code, 403)
            self.assertEqual(self.client.get("/api/admin/reference-deleted", headers=headers).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/admin/reference/subjects/{self.subject.id}").status_code, 401)

    def test_current_gradebook_list_only_returns_active_assigned_teacher_records(self):
        assignment = SubjectTeachingAssignment(
            school_year_id=self.year.id, subject_id=self.subject.id, section_id=self.section.id,
            teacher_user_id=self.teacher.id,
        )
        self.db.add(assignment)
        self.db.commit()
        response = self.client.get("/api/gradebooks?current_only=true", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(self.book.id, [row["id"] for row in response.json()])

        assignment.active = False
        self.db.commit()
        current = self.client.get("/api/gradebooks?current_only=true", headers=self.headers)
        all_saved = self.client.get("/api/gradebooks", headers=self.headers)
        self.assertNotIn(self.book.id, [row["id"] for row in current.json()])
        self.assertIn(self.book.id, [row["id"] for row in all_saved.json()])
        self.assertIsNotNone(self.db.get(Gradebook, self.book.id))

    def test_grade_deletion_hides_child_sections_and_restore_respects_separate_deletion(self):
        self.remove("sections", self.section)
        self.remove("grade-levels", self.grade)
        structure = self.client.get("/api/admin/academic-structure", headers=self.headers).json()
        self.assertEqual(structure["sections"], [])
        blocked = self.client.post(f"/api/admin/reference/sections/{self.section.id}/restore", headers=self.headers)
        self.assertEqual(blocked.status_code, 409)
        self.client.post(f"/api/admin/reference/grade-levels/{self.grade.id}/restore", headers=self.headers)
        self.assertEqual(self.client.get("/api/admin/academic-structure", headers=self.headers).json()["sections"], [])
        self.assertEqual(self.client.post(f"/api/admin/reference/sections/{self.section.id}/restore", headers=self.headers).status_code, 200)

    def test_parent_grade_hides_undeleted_section_and_preserves_inactive_state(self):
        self.section.active = False
        self.db.commit()
        self.remove("grade-levels", self.grade)
        self.assertEqual(self.client.get("/api/admin/academic-structure", headers=self.headers).json()["sections"], [])
        self.client.post(f"/api/admin/reference/grade-levels/{self.grade.id}/restore", headers=self.headers)
        sections = self.client.get("/api/admin/academic-structure", headers=self.headers).json()["sections"]
        self.assertEqual(sections[0]["id"], self.section.id)
        self.assertFalse(sections[0]["active"])

    def test_deleted_references_cannot_be_edited_or_used_by_stale_requests(self):
        self.remove("subjects", self.subject)
        edited = self.client.post("/api/admin/subjects", headers=self.headers, json={"id": self.subject.id, "code": "MATH", "name": "Changed"})
        self.assertEqual(edited.status_code, 409)
        created = self.client.post("/api/gradebooks", headers=self.teacher_headers, json={
            "school_year_id": self.year.id, "grading_period_id": self.period.id, "grade_level_id": self.grade.id,
            "section_id": self.section.id, "subject_id": self.subject.id})
        self.assertEqual(created.status_code, 422, created.text)
        self.remove("grade-levels", self.grade)
        section = self.client.post("/api/admin/sections", headers=self.headers, json={"grade_level_id": self.grade.id, "name": "New"})
        self.assertEqual(section.status_code, 422)

    def test_audited_idempotent_deletion_and_restart_does_not_resurrect_defaults(self):
        self.remove("grade-levels", self.grade)
        self.remove("sections", self.section)
        self.remove("subjects", self.subject)
        self.remove("subjects", self.subject)
        seed_reference_data(self.db)
        self.db.expire_all()
        for item in (self.grade, self.section, self.subject):
            self.assertIsNotNone(item.deleted_at)
        events = self.db.scalars(select(SystemAuditEvent).where(SystemAuditEvent.action == "Delete")).all()
        self.assertEqual(len(events), 3)
        self.assertTrue(all(event.actor_role == "admin" for event in events))

    def test_unknown_reference_returns_404(self):
        self.assertEqual(self.client.delete("/api/admin/reference/subjects/99999", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post("/api/admin/reference/unknown/1/restore", headers=self.headers).status_code, 404)

    def test_school_year_deletion_hides_periods_without_removing_class_history(self):
        self.remove("school-years", self.year)
        structure = self.client.get("/api/admin/academic-structure", headers=self.headers).json()
        self.assertEqual(structure['school_years'], [])
        self.assertEqual(structure['grading_periods'], [])
        self.assertEqual(self.db.get(StudentScore, self.score.id).score, 18)
        rejected = self.client.post('/api/admin/grading-periods', headers=self.headers, json={
            'school_year_id': self.year.id, 'name': 'New period', 'quarter': 2,
            'starts_on': '2026-09-01', 'ends_on': '2026-10-01'})
        self.assertEqual(rejected.status_code, 422)
        rejected = self.client.post('/api/gradebooks', headers=self.teacher_headers, json={
            'school_year_id': self.year.id, 'grading_period_id': self.period.id,
            'grade_level_id': self.grade.id, 'section_id': self.section.id, 'subject_id': self.subject.id})
        self.assertEqual(rejected.status_code, 422)
        seed_reference_data(self.db)
        self.assertEqual(self.client.get('/api/admin/academic-structure', headers=self.headers).json()['school_years'], [])
        self.assertEqual(self.client.post(f'/api/admin/reference/school-years/{self.year.id}/restore', headers=self.headers).status_code, 200)
        self.assertEqual(len(self.client.get('/api/admin/academic-structure', headers=self.headers).json()['grading_periods']), 1)

    def test_period_restore_requires_parent_year_and_separate_deletion_is_preserved(self):
        self.remove('grading-periods', self.period)
        self.remove('school-years', self.year)
        self.assertEqual(self.client.post(f'/api/admin/reference/grading-periods/{self.period.id}/restore', headers=self.headers).status_code, 409)
        deleted = self.client.get('/api/admin/reference-deleted', headers=self.headers).json()
        period_row = next(item for item in deleted if item['kind'] == 'grading-periods')
        self.assertEqual(period_row['restore_hint'], 'Restore school year first.')
        self.client.post(f'/api/admin/reference/school-years/{self.year.id}/restore', headers=self.headers)
        self.assertEqual(self.client.get('/api/admin/academic-structure', headers=self.headers).json()['grading_periods'], [])
        self.assertEqual(self.client.post(f'/api/admin/reference/grading-periods/{self.period.id}/restore', headers=self.headers).status_code, 200)

    def test_deleted_section_cannot_restore_duplicate_adviser_assignment(self):
        self.remove("sections", self.section)
        other = SchoolSection(grade_level_id=self.grade.id, name="Oslo", adviser_user_id=self.teacher.id)
        self.db.add(other)
        self.db.commit()
        response = self.client.post(f"/api/admin/reference/sections/{self.section.id}/restore", headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.db.delete(other)
        self.db.commit()
        restored = self.client.post(f"/api/admin/reference/sections/{self.section.id}/restore", headers=self.headers)
        self.assertEqual(restored.status_code, 200, restored.text)


class AcademicMigrationTest(unittest.TestCase):
    def test_additive_migration_is_idempotent_on_existing_tables(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description TEXT NOT NULL, applied_at TIMESTAMP NOT NULL)"))
            for version, description in MIGRATIONS:
                if version in {"0012_recoverable_academic_deletion", "0013_recoverable_academic_calendar_deletion"}:
                    continue
                connection.execute(text("INSERT INTO schema_migrations VALUES (:v, :d, CURRENT_TIMESTAMP)"), {"v": version, "d": description})
            for table in ("grade_levels", "school_sections", "subjects", "school_years", "grading_periods"):
                connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, name TEXT)"))
                connection.execute(text(f"INSERT INTO {table} VALUES (1, 'Keep this record')"))
        self.assertEqual(run_migrations(engine), ["0012_recoverable_academic_deletion", "0013_recoverable_academic_calendar_deletion"])
        self.assertEqual(run_migrations(engine), [])
        with engine.connect() as connection:
            for table in ("grade_levels", "school_sections", "subjects", "school_years", "grading_periods"):
                self.assertEqual(tuple(connection.execute(text(f"SELECT name, deleted_at FROM {table}")).one()), ("Keep this record", None))
        engine.dispose()

    def test_subject_teacher_and_elective_migration_is_additive_and_idempotent(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description TEXT NOT NULL, applied_at TIMESTAMP NOT NULL)"))
            for version, description in MIGRATIONS:
                if version != "0017_subject_teaching_assignments_and_electives":
                    connection.execute(text("INSERT INTO schema_migrations VALUES (:v, :d, CURRENT_TIMESTAMP)"), {"v": version, "d": description})
            connection.execute(text("CREATE TABLE school_sections (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
            connection.execute(text("INSERT INTO school_sections VALUES (1, 'Oslo')"))
            connection.execute(text("CREATE TABLE subjects (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
            connection.execute(text("INSERT INTO subjects VALUES (1, 'Science')"))

        self.assertEqual(run_migrations(engine), ["0017_subject_teaching_assignments_and_electives"])
        self.assertEqual(run_migrations(engine), [])
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT name, track FROM school_sections WHERE id = 1")).one(), ("Oslo", None))
            self.assertEqual(connection.execute(text("SELECT name, is_elective, elective_track FROM subjects WHERE id = 1")).one(), ("Science", 0, None))
            self.assertIn("subject_teaching_assignments", inspect(connection).get_table_names())
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
