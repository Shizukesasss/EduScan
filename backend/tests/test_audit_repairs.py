"""Security and transaction regressions using only disposable test records."""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

TEST_DIR = tempfile.TemporaryDirectory(prefix="eduscan-audit-repairs-")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = TEST_DIR.name
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-audit-repairs"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"
os.environ["SMS_GATEWAY_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import (AttendanceEvent, BiometricModel, BiometricSample, GradeComponent,
                        GradeLevel, GradebookState, GradingPeriod, Person, PersonnelSchedule,
                        SchoolSection, SchoolYear, Subject, User)
from app.services.attendance import applicable_schedule
from app.services.biometrics import biometric_service
from app.services.disposal import dispose_person_records
from app.services.roster import import_roster
from app.services.settings_store import set_json


class AuditRepairsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="admin", role="admin", full_name="Admin", password_hash="unused", must_change_password=False)
        self.teacher = User(username="teacher", role="teacher", full_name="Teacher", password_hash="unused", must_change_password=False)
        self.other = User(username="other", role="teacher", full_name="Other", password_hash="unused", must_change_password=False)
        self.grade = GradeLevel(name="10")
        self.db.add_all([self.admin, self.teacher, self.other, self.grade])
        self.db.flush()
        self.db.add_all([SchoolSection(grade_level_id=self.grade.id, name="Own", adviser_user_id=self.teacher.id),
                         SchoolSection(grade_level_id=self.grade.id, name="Other", adviser_user_id=self.other.id),
                         GradebookState(class_key="other-book", school_year="2026-2027", quarter=1,
                                        subject="Mathematics", grade="10", section="Other")])
        self.db.commit()
        def override():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = override
        self.client = TestClient(app)
        self.teacher_headers = {"Authorization": f"Bearer {create_token(self.teacher)}"}
        self.admin_headers = {"Authorization": f"Bearer {create_token(self.admin)}"}

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def payload(self, key="other-book"):
        return {"class_key": key, "grade": "10", "section": "Own", "subject": "Mathematics",
                "components": [{"id": "one", "category": "Written Work", "label": "Quiz", "weight": 100, "max_score": 10}], "scores": {}}

    def test_teacher_cannot_spoof_scope_for_read_audit_or_save(self):
        for suffix in ("", "/audit", "/report.xlsx", "/report/print"):
            response = self.client.get(f"/api/gradebook/other-book{suffix}?grade=10&section=Own", headers=self.teacher_headers)
            self.assertEqual(response.status_code, 403, response.text)
        response = self.client.put("/api/gradebook/other-book", headers=self.teacher_headers, json=self.payload())
        self.assertEqual(response.status_code, 403, response.text)
        self.db.expire_all()
        self.assertEqual(self.db.get(GradebookState, "other-book").section, "Other")
        for action in ("reopen", "finalize"):
            response = self.client.post(f"/api/gradebook/other-book/{action}", headers=self.teacher_headers, json={"reason": "Attempted foreign class action"})
            self.assertEqual(response.status_code, 403, response.text)

    def test_admin_can_read_but_cannot_save(self):
        response = self.client.get("/api/gradebook/other-book", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.put("/api/gradebook/other-book", headers=self.admin_headers, json=self.payload())
        self.assertEqual(response.status_code, 403, response.text)

    def test_teacher_can_still_create_save_and_read_own_legacy_book(self):
        year = SchoolYear(name="2026-2027", starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        student = Person(external_id="OWN-STUDENT", full_name="Own Learner", sex="Male", role="Student", grade="10", section="Own")
        self.db.add_all([year, student, Subject(code="MATH", name="Mathematics")]); self.db.flush()
        self.db.add(GradingPeriod(school_year_id=year.id, name="Quarter 1", quarter=1, starts_on=year.starts_on, ends_on=year.ends_on))
        self.db.commit()
        payload = self.payload("own-book")
        payload["scores"] = {str(student.id): {"one": 0}}
        for _ in range(2):
            response = self.client.put("/api/gradebook/own-book", headers=self.teacher_headers, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
        response = self.client.get("/api/gradebook/own-book", headers=self.teacher_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["section"], "Own")
        self.assertEqual(list(response.json()["scores"][str(student.id)].values()), [0])

    def test_own_empty_book_still_loads_and_unscoped_existing_book_is_denied(self):
        response = self.client.get("/api/gradebook/new-book?grade=10&section=Own", headers=self.teacher_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.add(GradeComponent(class_key="orphan-book", category="Written Work", label="Quiz", weight=100, max_score=10, sequence=0))
        self.db.commit()
        response = self.client.get("/api/gradebook/orphan-book?grade=10&section=Own", headers=self.teacher_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def test_legacy_rules_are_checked_when_state_is_missing(self):
        set_json(self.db, "gradebook:rules-book:rules", {"grade": "10", "section": "Other"})
        response = self.client.get("/api/gradebook/rules-book?grade=10&section=Own", headers=self.teacher_headers)
        self.assertEqual(response.status_code, 403, response.text)

    def workbook(self, assignment_column=False):
        book = Workbook()
        book.active.append(["School ID", "Full Name", "Sex", "Role", "Grade", "Section"] + (["Assignment"] if assignment_column else []))
        book.active.append(["STUDENT-1", "Test Learner", "Male", "Student", "10", "Own"] + ([None] if assignment_column else []))
        book.active.append(["STAFF-1", "Test Faculty", "Female", "Faculty", None, None] + (["Science"] if assignment_column else []))
        stream = io.BytesIO(); book.save(stream); book.close()
        return stream.getvalue()

    def test_roster_preview_and_new_student_and_faculty_import(self):
        data = self.workbook(True)
        self.assertEqual(import_roster(self.db, data, "roster.xlsx", "Approved test", self.admin, True)["valid_rows"], 2)
        self.assertEqual(import_roster(self.db, data, "roster.xlsx", "Approved test", self.admin, False)["inserted"], 2)
        self.db.expire_all()
        staff = self.db.scalar(select(Person).where(Person.external_id == "STAFF-1"))
        self.assertEqual(staff.assignment, "Science")
        import_roster(self.db, self.workbook(), "roster.xlsx", "Approved test", self.admin, False)
        self.db.expire_all()
        self.assertEqual(self.db.get(Person, staff.id).assignment, "Science")

    def test_person_api_persists_assignment(self):
        payload = {"external_id": "PERSONNEL-1", "first_name": "Test", "sex": "Female", "role": "Faculty", "assignment": "Science"}
        response = self.client.post("/api/persons", json=payload, headers=self.admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["assignment"], "Science")
        self.db.expire_all()
        self.assertEqual(self.db.get(Person, response.json()["id"]).assignment, "Science")

    def test_assignment_migration_is_idempotent_and_preserves_existing_values(self):
        from app.migrations import MIGRATIONS, run_migrations
        for existing in (False, True):
            with self.subTest(existing_assignment_column=existing):
                engine = create_engine("sqlite://")
                with engine.begin() as connection:
                    connection.execute(text("CREATE TABLE persons (id INTEGER PRIMARY KEY, full_name TEXT" + (", assignment TEXT" if existing else "") + ")"))
                    connection.execute(text("INSERT INTO persons VALUES (1, 'Preserved person'" + (", 'Science'" if existing else "") + ")"))
                    connection.execute(text("CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, description VARCHAR(255), applied_at TIMESTAMP)"))
                    for version, description in MIGRATIONS:
                        if version != "0014_person_assignment":
                            connection.execute(text("INSERT INTO schema_migrations VALUES (:version, :description, CURRENT_TIMESTAMP)"), {"version": version, "description": description})
                self.assertEqual(run_migrations(engine), ["0014_person_assignment"])
                self.assertEqual(run_migrations(engine), [])
                with engine.connect() as connection:
                    row = connection.execute(text("SELECT full_name, assignment FROM persons")).one()
                    self.assertEqual(tuple(row), ("Preserved person", "Science" if existing else None))
                engine.dispose()

    def test_assignment_then_role_default_and_no_other_assignment(self):
        person = Person(external_id="STAFF", full_name="Staff", sex="Male", role="Faculty", assignment=" Science ")
        default = PersonnelSchedule(role="Faculty", assignment=None, weekdays="0", start_time=time(8), end_time=time(17))
        other = PersonnelSchedule(role="Faculty", assignment="Math", weekdays="0", start_time=time(7), end_time=time(16))
        match = PersonnelSchedule(role="Faculty", assignment="science", weekdays="0", start_time=time(9), end_time=time(18))
        self.db.add_all([person, default, other, match]); self.db.commit()
        monday = date(2026, 10, 12)
        self.assertEqual(applicable_schedule(self.db, person, monday).id, match.id)
        person.assignment = "Unknown"
        self.assertEqual(applicable_schedule(self.db, person, monday).id, default.id)
        default.active = False; self.db.flush()
        self.assertIsNone(applicable_schedule(self.db, person, monday))
        person.assignment = "Science"
        self.assertIsNone(applicable_schedule(self.db, person, date(2026, 10, 13)))

    def enrolled_person(self):
        person = Person(external_id="FACE-1", full_name="Face Test", sex="Male", role="Student", biometric_consent=True)
        self.db.add(person); self.db.flush()
        folder = Path(TEST_DIR.name) / "biometrics" / f"person_{person.id}"
        folder.mkdir(parents=True, exist_ok=True)
        sample_path = folder / "sample.enc"; sample_path.write_bytes(b"test sample")
        model_path = Path(TEST_DIR.name) / "models" / "old.enc"; model_path.write_bytes(b"test model")
        sample = BiometricSample(id="sample", person_id=person.id, encrypted_path=str(sample_path), sha256="test", quality_score=1)
        model = BiometricModel(version="test", file_path=str(model_path), sha256="test", threshold=65, person_count=1, sample_count=1, active=True)
        self.db.add_all([sample, model, AttendanceEvent(id="scan", person_id=person.id, event_date=date(2026, 10, 12), event_time=time(8), direction="Time In", status="Present", source="Test")])
        self.db.commit()
        return person, sample_path, model_path

    def test_disposal_failure_preserves_records_face_files_and_model(self):
        person, sample, model = self.enrolled_person()
        with patch("app.services.disposal.RecordDisposalAudit", side_effect=RuntimeError("injected final-stage failure")):
            with self.assertRaisesRegex(RuntimeError, "final-stage"):
                dispose_person_records(self.db, person, self.admin, "Test disposal failure", "Test authorization", person.external_id)
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Person, person.id))
        self.assertIsNotNone(self.db.get(BiometricSample, "sample"))
        self.assertIsNotNone(self.db.get(AttendanceEvent, "scan"))
        self.assertTrue(self.db.scalar(select(BiometricModel)).active)
        self.assertTrue(sample.exists()); self.assertTrue(model.exists())

    def test_disposal_commits_once_then_removes_only_test_files(self):
        person, sample, model = self.enrolled_person()
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            result = dispose_person_records(self.db, person, self.admin, "Authorized test disposal", "Test authorization", person.external_id)
        self.assertTrue(result["disposed"])
        self.assertEqual(commit.call_count, 1)
        self.assertFalse(sample.exists()); self.assertFalse(model.exists())

    def test_disposal_reports_file_cleanup_failure(self):
        person, sample, model = self.enrolled_person()
        with patch.object(biometric_service, '_unlink_files'):
            result = dispose_person_records(self.db, person, self.admin, 'Authorized test disposal', 'Test authorization', person.external_id)
        self.assertEqual(result['file_cleanup_pending'], 2)
        self.assertEqual(result['removed_counts']['face_samples'], 1)
        self.assertTrue(sample.exists())

    def test_disposal_removes_relocated_face_samples(self):
        person, sample, model = self.enrolled_person()
        record = self.db.get(BiometricSample, 'sample')
        record.encrypted_path = r'Z:\old-computer\sample.enc'
        self.db.commit()
        result = dispose_person_records(self.db, person, self.admin, 'Authorized test disposal', 'Test authorization', person.external_id)
        self.assertFalse(sample.exists())
        self.assertEqual(result['file_cleanup_pending'], 0)

    def test_startup_preserves_inactive_model_records_and_files(self):
        import app.main as main
        person, sample, model_path = self.enrolled_person()
        model = self.db.scalar(select(BiometricModel))
        model.active = False
        self.db.commit()
        with patch.object(main, "engine", self.engine), patch.object(main, "SessionLocal", side_effect=lambda: Session(self.engine)):
            main.startup()
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(Person, person.id))
        self.assertFalse(self.db.get(BiometricModel, model.id).active)
        self.assertTrue(sample.exists())
        self.assertTrue(model_path.exists())

    def test_disposal_rollback_discards_replacement_model_and_keeps_other_enrollment(self):
        person, sample, old_model = self.enrolled_person()
        other = Person(external_id="FACE-2", full_name="Other Face", sex="Female", role="Student", biometric_consent=True)
        self.db.add(other); self.db.flush()
        self.db.add(BiometricSample(id="other-sample", person_id=other.id, encrypted_path="unused", sha256="test", quality_score=1))
        self.db.commit()
        replacement = Path(TEST_DIR.name) / "models/lbph-replacement.yml.enc"
        def train(db, commit):
            biometric_service._deactivate_models(db)
            replacement.write_bytes(b"replacement test model")
            db.add(BiometricModel(version="replacement", file_path=str(replacement), sha256="test", threshold=65, person_count=1, sample_count=1, active=True))
            db.flush()
            return {"version": "replacement"}
        with patch.object(biometric_service, "train", side_effect=train), patch("app.services.disposal.RecordDisposalAudit", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                dispose_person_records(self.db, person, self.admin, "Authorized test disposal", "Test authorization", person.external_id)
        self.db.expire_all()
        self.assertTrue(sample.exists()); self.assertTrue(old_model.exists())
        self.assertFalse(replacement.exists())
        self.assertEqual(len(self.db.scalars(select(BiometricSample)).all()), 2)
        self.assertTrue(self.db.scalar(select(BiometricModel)).active)

    def test_maintenance_scripts_are_import_safe(self):
        root = Path(__file__).resolve().parents[2]
        for name in ("test.py", "delete_old_mapeh.py", "delete_old_mapeh_hard.py", "delete_mapeh_gradebooks.py", "replace_script.py", "fix_mapeh_weights.py", "test_export.py"):
            spec = importlib.util.spec_from_file_location("audit_maintenance", root / name)
            with patch("builtins.open", side_effect=AssertionError("file access during import")), patch("sqlalchemy.create_engine", side_effect=AssertionError("database access during import")):
                spec.loader.exec_module(importlib.util.module_from_spec(spec))


if __name__ == "__main__":
    unittest.main()
