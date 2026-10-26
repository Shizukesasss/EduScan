from __future__ import annotations

import io
import json
import tempfile
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app.migrations import MIGRATIONS, run_migrations
from app.models import AttendanceEvent, GeneratedReport, GradeLevel, GradingPeriod, LearnerEnrollment, Person, RosterImportAudit, SchoolSection, SchoolYear, SectionAdviserAssignment, Subject, SubjectTeachingAssignment, User
from app.models_grading import AssessmentItem, Gradebook, GradebookComponent, GradingPolicy, StudentScore
from app.services.grading_engine import DEFAULT_TRANSMUTATION_TABLE
from app.services.annex_g import backfill_annex_g_dobs, import_annex_g_enrollments
from app.services.annex_g import age_on, build_annex_g_section, first_friday_of_june, render_annex_g_html
from app.schemas import AnnexGCommentPayload, AnnexGPlacementPayload, PersonCreate
from app import main


def workbook(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


class AnnexGImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.admin = User(username="annex-admin", password_hash="x", role="admin", full_name="Admin User")
        self.teacher = User(username="annex-teacher", password_hash="x", role="teacher", full_name="Adviser Teacher")
        self.records = User(username="annex-records", password_hash="x", role="records_officer", full_name="Records Officer")
        self.year = SchoolYear(name="2026-2027", starts_on=date(2026, 6, 1), ends_on=date(2027, 3, 31))
        self.grade = GradeLevel(name="7")
        self.db.add_all([self.admin, self.teacher, self.records, self.year, self.grade])
        self.db.flush()
        self.section = SchoolSection(grade_level_id=self.grade.id, name="Jose")
        self.db.add(self.section)
        self.db.flush()
        self.db.add(SectionAdviserAssignment(school_year_id=self.year.id, section_id=self.section.id,
                                             teacher_user_id=self.teacher.id))
        self.periods = {}
        for number, day in ((1, date(2026, 6, 1)), (2, date(2026, 8, 3)), (3, date(2027, 1, 4))):
            period = GradingPeriod(school_year_id=self.year.id, name=f"Term {number}", term_order=number,
                                   starts_on=day, ends_on=day)
            self.db.add(period)
            self.periods[number] = period
        self.math = Subject(code="MATH", name="Mathematics", category="JHS")
        self.mapeh = Subject(code="MAPEH", name="MAPEH", category="JHS")
        self.policy = GradingPolicy(name="Test adjusted", school_year=self.year.name, grade_levels="7",
            subject_category="General", reporting_method="adjusted_2026",
            transmutation_table_json=json.dumps(DEFAULT_TRANSMUTATION_TABLE))
        self.db.add_all([self.math, self.mapeh, self.policy])
        self.learner = Person(external_id="STU-1", lrn="123456789012", full_name="Test Learner", surname="Learner",
                              first_name="Test", sex="Female", role="Student", grade="7", section="Legacy Jose")
        self.other = Person(external_id="STU-2", lrn="234567890123", full_name="Other Learner", surname="Learner",
                            first_name="Other", sex="Male", role="Student", grade="8", section="Old Section",
                            date_of_birth=date(2011, 5, 4), guardian_phone="09170000000")
        self.db.add_all([self.learner, self.other])
        self.db.commit()

    def add_enrollment(self, person=None, dob=date(2012, 6, 5)):
        person = person or self.learner
        person.date_of_birth = dob
        record = LearnerEnrollment(person_id=person.id, school_year_id=self.year.id,
            grade_level_id=self.grade.id, section_id=self.section.id,
            starts_on=date(2026, 6, 1), ends_on=None, source_reference="Verified SF1",
            source_sha256="a" * 64, imported_by=self.admin.id, imported_by_name=self.admin.full_name)
        self.db.add(record)
        self.db.commit()
        return record

    def test_native_student_creation_adds_year_specific_placement(self):
        payload = PersonCreate(external_id="NATIVE-ENROLL-1", first_name="New", surname="Learner",
            sex="Female", date_of_birth=date(2012, 1, 2), role="Student", grade="7", section="Jose",
            school_year_id=self.year.id, enrollment_start_date=date(2026, 6, 1))
        person = main._new_person_record(payload, self.db, self.admin)
        self.db.commit()

        placement = self.db.scalar(select(LearnerEnrollment).where(LearnerEnrollment.person_id == person.id))
        self.assertIsNotNone(placement)
        self.assertEqual((placement.school_year_id, placement.grade_level_id, placement.section_id,
            placement.starts_on, placement.person.date_of_birth),
            (self.year.id, self.grade.id, self.section.id, date(2026, 6, 1), date(2012, 1, 2)))
        self.assertEqual(placement.source_reference, "EduScan student enrollment form")
        self.assertEqual(len(placement.source_sha256), 64)

    def test_native_student_creation_requires_year_and_start_date(self):
        for field in ("school_year_id", "enrollment_start_date"):
            values = {"external_id": f"MISSING-{field}", "first_name": "New", "surname": "Learner",
                "sex": "Female", "date_of_birth": date(2012, 1, 2), "role": "Student", "grade": "7",
                "section": "Jose", "school_year_id": self.year.id,
                "enrollment_start_date": date(2026, 6, 1)}
            values[field] = None
            with self.subTest(field=field), self.assertRaises(HTTPException) as failure:
                main._new_person_record(PersonCreate(**values), self.db, self.admin)
            self.assertEqual(failure.exception.status_code, 422)
            self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == values["external_id"])))

    def test_native_student_creation_rejects_date_outside_school_year(self):
        payload = PersonCreate(external_id="OUTSIDE-NATIVE", first_name="New", surname="Learner",
            sex="Female", date_of_birth=date(2012, 1, 2), role="Student", grade="7", section="Jose",
            school_year_id=self.year.id, enrollment_start_date=date(2027, 4, 1))
        with self.assertRaises(HTTPException) as failure:
            main._new_person_record(payload, self.db, self.admin)
        self.assertEqual(failure.exception.status_code, 422)
        self.assertIsNone(self.db.scalar(select(Person).where(Person.external_id == "OUTSIDE-NATIVE")))

    def test_native_student_placement_rolls_back_with_person(self):
        payload = PersonCreate(external_id="ROLLBACK-NATIVE", first_name="New", surname="Learner",
            sex="Female", date_of_birth=date(2012, 1, 2), role="Student", grade="7", section="Jose",
            school_year_id=self.year.id, enrollment_start_date=date(2026, 6, 1))
        person = main._new_person_record(payload, self.db, self.admin)
        person_id = person.id
        self.db.rollback()
        self.assertIsNone(self.db.get(Person, person_id))
        self.assertIsNone(self.db.scalar(select(LearnerEnrollment).where(LearnerEnrollment.person_id == person_id)))

    def test_placement_candidates_exclude_learners_already_placed_in_selected_year(self):
        self.add_enrollment(self.learner)
        result = main.annex_g_placement_candidates(self.year.id, self.db, self.admin)
        self.assertEqual([item["id"] for item in result["candidates"]], [self.other.id])
        self.assertNotIn("date_of_birth", result["candidates"][0])

    def test_annex_g_options_include_year_bounds_and_grade_level_ids(self):
        result = main.annex_g_options(self.db, self.admin)
        year = next(item for item in result["school_years"] if item["id"] == self.year.id)
        section = next(item for item in year["sections"] if item["id"] == self.section.id)
        self.assertEqual((year["starts_on"], year["ends_on"]), (self.year.starts_on, self.year.ends_on))
        self.assertEqual(section["grade_level_id"], self.grade.id)

    def test_admin_placement_review_saves_target_without_changing_person_profile(self):
        original = (self.other.grade, self.other.section, self.other.date_of_birth, self.other.guardian_phone)
        payload = AnnexGPlacementPayload(person_id=self.other.id, school_year_id=self.year.id,
            grade_level_id=self.grade.id, section_id=self.section.id, starts_on=date(2026, 6, 1), confirmed=True)
        result = main.create_annex_g_placement(payload, self.db, self.admin)

        placement = self.db.scalar(select(LearnerEnrollment).where(LearnerEnrollment.person_id == self.other.id))
        self.assertEqual(result["person_id"], self.other.id)
        self.assertEqual((placement.grade_level_id, placement.section_id, placement.starts_on),
            (self.grade.id, self.section.id, date(2026, 6, 1)))
        self.assertEqual(placement.source_reference, "Administrator verified against official school records")
        self.assertEqual((self.other.grade, self.other.section, self.other.date_of_birth, self.other.guardian_phone), original)

    def test_admin_placement_review_requires_confirmation(self):
        payload = AnnexGPlacementPayload(person_id=self.other.id, school_year_id=self.year.id,
            grade_level_id=self.grade.id, section_id=self.section.id, starts_on=date(2026, 6, 1), confirmed=False)
        with self.assertRaises(HTTPException) as failure:
            main.create_annex_g_placement(payload, self.db, self.admin)
        self.assertEqual(failure.exception.status_code, 422)
        self.assertIsNone(self.db.scalar(select(LearnerEnrollment).where(LearnerEnrollment.person_id == self.other.id)))

    def test_admin_placement_review_rejects_duplicate_year_placement(self):
        payload = AnnexGPlacementPayload(person_id=self.other.id, school_year_id=self.year.id,
            grade_level_id=self.grade.id, section_id=self.section.id, starts_on=date(2026, 6, 1), confirmed=True)
        main.create_annex_g_placement(payload, self.db, self.admin)
        with self.assertRaises(HTTPException) as failure:
            main.create_annex_g_placement(payload, self.db, self.admin)
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(len(self.db.scalars(select(LearnerEnrollment).where(
            LearnerEnrollment.person_id == self.other.id, LearnerEnrollment.school_year_id == self.year.id)).all()), 1)

    def test_admin_placement_routes_require_admin_role(self):
        teacher = User(username="placement-review-teacher", password_hash="x", role="teacher",
                       full_name="Teacher", must_change_password=False)
        for path in ("/api/admin/annex-g/placement-candidates", "/api/admin/annex-g/placements"):
            route = next(item for item in main.app.routes if getattr(item, "path", None) == path)
            guard = next(item.call for item in route.dependant.dependencies if item.name == "user")
            with self.subTest(path=path), self.assertRaises(HTTPException) as failure:
                guard(user=teacher)
            self.assertEqual(failure.exception.status_code, 403)

    def add_gradebook(self, subject, term, score, *, status="Finalized", learning_area=""):
        assignment = self.db.scalar(select(SubjectTeachingAssignment).where(
            SubjectTeachingAssignment.school_year_id == self.year.id,
            SubjectTeachingAssignment.subject_id == subject.id,
            SubjectTeachingAssignment.section_id == self.section.id,
        ))
        if not assignment:
            self.db.add(SubjectTeachingAssignment(school_year_id=self.year.id, subject_id=subject.id,
                section_id=self.section.id, teacher_user_id=self.admin.id))
        book = Gradebook(school_year_id=self.year.id, grading_period_id=self.periods[term].id,
            grade_level_id=self.grade.id, section_id=self.section.id, subject_id=subject.id,
            school_year_name=self.year.name, term_order=term, grade_name="7", section_name="Jose",
            subject_name=subject.name, teacher_name="Test Teacher", teacher_user_id=self.admin.id,
            learning_area=learning_area, status=status, grading_policy_id=self.policy.id)
        component = GradebookComponent(name="Written Works", component_type="Written Work", weight=100, sequence=0)
        item = AssessmentItem(label="Quiz 1", max_score=100, sequence=0)
        component.items.append(item)
        book.components.append(component)
        self.db.add(book)
        self.db.flush()
        self.db.add(StudentScore(person_id=self.learner.id, assessment_item_id=item.id, score=score,
            status="Scored", updated_by=self.admin.id))
        self.db.commit()
        return book

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_enrollment_import_uses_exact_lrn_and_does_not_rewrite_current_placement(self):
        data = workbook([
            ["LRN", "School Year", "Grade", "Section", "Enrollment Start", "Enrollment End"],
            [self.learner.lrn, "2026-2027", "7", "Jose", date(2026, 6, 1), None],
        ])
        preview = import_annex_g_enrollments(self.db, data, "placement.xlsx", "Approved roster 2026", self.admin, True)
        self.assertEqual((preview["valid_rows"], preview["invalid_rows"]), (1, 0))
        self.assertEqual(self.learner.grade, "7")
        self.assertEqual(self.learner.section, "Legacy Jose")
        applied = import_annex_g_enrollments(self.db, data, "placement.xlsx", "Approved roster 2026", self.admin, False)
        self.assertEqual(applied["inserted"], 1)
        enrollment = self.db.scalar(select(LearnerEnrollment))
        self.assertEqual(enrollment.person_id, self.learner.id)
        self.assertEqual(enrollment.source_reference, "Approved roster 2026")
        audit = self.db.scalar(select(RosterImportAudit).where(RosterImportAudit.import_mode == "annex_g_enrollment"))
        self.assertEqual(audit.approved_reference, "Approved roster 2026")
        self.assertEqual(len(audit.file_sha256), 64)

    def test_dob_backfill_fills_only_blank_dates_without_touching_other_fields(self):
        data = workbook([["LRN", "Date of Birth"],
                         [self.learner.lrn, date(2012, 2, 3)],
                         [self.other.lrn, date(2010, 1, 2)]])
        result = backfill_annex_g_dobs(self.db, data, "dob.xlsx", "Verified SF1 2026", self.admin, False)
        self.assertEqual((result["updated"], result["skipped"]), (1, 1))
        self.assertEqual(self.learner.date_of_birth, date(2012, 2, 3))
        self.assertEqual(self.other.date_of_birth, date(2011, 5, 4))
        self.assertEqual(self.other.guardian_phone, "09170000000")
        audit = self.db.scalar(select(RosterImportAudit).where(RosterImportAudit.import_mode == "annex_g_dob"))
        self.assertEqual(audit.updated_count, 1)

    def test_dob_import_rejects_unmatched_lrn_atomically(self):
        data = workbook([["LRN", "DOB"], ["999999999999", date(2012, 2, 3)]])
        with self.assertRaises(Exception):
            backfill_annex_g_dobs(self.db, data, "dob.xlsx", "Verified SF1 2026", self.admin, False)
        self.assertIsNone(self.learner.date_of_birth)
        self.assertIsNone(self.db.scalar(select(RosterImportAudit).where(RosterImportAudit.import_mode == "annex_g_dob")))

    def test_enrollment_rejects_section_in_wrong_grade_without_applying_any_row(self):
        data = workbook([["LRN", "School Year", "Grade", "Section", "Start Date"],
                         [self.learner.lrn, "2026-2027", "8", "Jose", date(2026, 6, 1)]])
        with self.assertRaises(Exception):
            import_annex_g_enrollments(self.db, data, "placement.xlsx", "Approved roster 2026", self.admin, False)
        self.assertIsNone(self.db.scalar(select(LearnerEnrollment)))

    def test_migration_creates_annex_g_tables_and_import_mode_idempotently(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE annex_g_term_comments"))
            connection.execute(text("DROP TABLE learner_enrollments"))
            connection.execute(text("DROP INDEX ix_roster_import_audits_import_mode"))
            connection.execute(text("ALTER TABLE roster_import_audits DROP COLUMN import_mode"))
            connection.execute(text(
                "CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, "
                "description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"
            ))
            for version, description in MIGRATIONS[:-1]:
                connection.execute(text("INSERT INTO schema_migrations VALUES (:version, :description, CURRENT_TIMESTAMP)"),
                                   {"version": version, "description": description})
        self.assertEqual(run_migrations(self.engine), ["0026_annex_g_enrollment_and_comments"])
        tables = set(inspect(self.engine).get_table_names())
        self.assertIn("learner_enrollments", tables)
        self.assertIn("annex_g_term_comments", tables)
        self.assertIn("import_mode", {column["name"] for column in inspect(self.engine).get_columns("roster_import_audits")})
        self.assertEqual(run_migrations(self.engine), [])

    def test_age_uses_first_friday_of_june_reference(self):
        self.assertEqual(first_friday_of_june(self.year), date(2026, 6, 5))
        self.assertEqual(age_on(date(2012, 6, 5), date(2026, 6, 5)), 14)
        self.assertEqual(age_on(date(2012, 6, 6), date(2026, 6, 5)), 13)

    def test_report_uses_verified_historical_roster_and_finalized_gradebook(self):
        enrollment = self.add_enrollment()
        book = self.add_gradebook(self.math, 1, 100)
        report = build_annex_g_section(self.db, self.year.id, "7", "Jose", 1)
        learner = next(row for row in report["learners"] if row["person_id"] == self.learner.id)
        math = next(row for row in learner["learning_areas"] if row["name"] == "Mathematics")
        self.assertEqual(learner["enrollment_id"], enrollment.id)
        self.assertEqual(learner["age"], 14)
        self.assertNotIn("date_of_birth", learner)
        self.assertEqual(math["term_grades"]["1"], 100)
        self.assertNotIn("3", math["term_grades"])
        self.assertIsNone(math["final_grade"])
        self.assertTrue(any("attendance" in value.lower() for value in learner["blockers"]))
        self.assertEqual(self.db.get(Gradebook, book.id).status, "Finalized")

    def test_printable_report_has_valid_row_structure_and_no_raw_dob(self):
        enrollment = self.add_enrollment(dob=date(2012, 6, 5))
        self.add_gradebook(self.math, 1, 100)
        report = build_annex_g_section(self.db, self.year.id, "7", "Jose", 1)
        document = render_annex_g_html(report, enrollment.id)
        self.assertIn("Age (as of 2026-06-05)", document)
        self.assertIn("Descriptor scale", document)
        self.assertNotIn("2012-06-05", document)
        self.assertNotRegex(document, r"<tr[^>]*>[^<]*<tr")
        self.assertIn("Final Grade", document)
        self.assertIn("Cancellation of Transfer", document)

    def test_report_ignores_future_term_and_draft_gradebooks(self):
        self.add_enrollment()
        self.add_gradebook(self.math, 1, 100)
        self.add_gradebook(self.math, 2, 85, status="Draft")
        self.add_gradebook(self.math, 3, 90)
        report = build_annex_g_section(self.db, self.year.id, "7", "Jose", 2)
        learner = next(row for row in report["learners"] if row["person_id"] == self.learner.id)
        math = next(row for row in learner["learning_areas"] if row["name"] == "Mathematics")
        self.assertEqual(math["term_grades"]["1"], 100)
        self.assertIsNone(math["term_grades"]["2"])
        self.assertNotIn("3", math["term_grades"])
        self.assertIsNone(math["final_grade"])
        self.assertTrue(any("Mathematics" in value and "Term 2" in value for value in learner["blockers"]))

    def test_mapeh_is_shown_as_subareas_and_counted_once_in_general_average(self):
        self.add_enrollment()
        books = []
        for term in (1, 2, 3):
            books.append(self.add_gradebook(self.math, term, 100))
            books.append(self.add_gradebook(self.mapeh, term, 100, learning_area="music_arts"))
            books.append(self.add_gradebook(self.mapeh, term, 80, learning_area="pe_health"))
        from app.services.grading import get_gradebook_full
        expected_areas = [get_gradebook_full(self.db, book.id, include_mapeh_summary=False,
                          roster_person_ids=[self.learner.id])["students"][0]["reported_grade"]
                          for book in books if book.subject_id == self.mapeh.id]
        expected_mapeh_term = round(sum(expected_areas[:2]) / 2)
        report = build_annex_g_section(self.db, self.year.id, "7", "Jose", 3)
        learner = report["learners"][0]
        mapeh = next(row for row in learner["learning_areas"] if row["name"] == "MAPEH")
        math = next(row for row in learner["learning_areas"] if row["name"] == "Mathematics")
        self.assertEqual(mapeh["term_grades"]["1"], expected_mapeh_term)
        self.assertEqual({item["name"] for item in mapeh["subareas"]}, {"Music and Arts", "Physical Education and Health"})
        self.assertEqual(mapeh["final_grade"], expected_mapeh_term)
        self.assertEqual(learner["general_average"], round((math["final_grade"] + mapeh["final_grade"]) / 2))

    def test_teacher_can_save_adviser_comment_but_cannot_edit_other_section(self):
        from app.main import _annex_g_access, save_annex_g_comment
        enrollment = self.add_enrollment()
        other_section = SchoolSection(grade_level_id=self.grade.id, name="Other")
        self.db.add(other_section)
        self.db.flush()
        other_enrollment = LearnerEnrollment(person_id=self.other.id, school_year_id=self.year.id,
            grade_level_id=self.grade.id, section_id=other_section.id, starts_on=self.year.starts_on,
            source_reference="Verified roster", source_sha256="b" * 64,
            imported_by=self.admin.id, imported_by_name=self.admin.full_name)
        self.db.add(other_enrollment)
        self.db.commit()
        saved = save_annex_g_comment(AnnexGCommentPayload(enrollment_id=enrollment.id,
            term_order=1, comment="Shows consistent effort."), self.db, self.teacher)
        self.assertEqual(saved["comment"], "Shows consistent effort.")
        with self.assertRaises(HTTPException) as denied:
            _annex_g_access(self.db, self.teacher, other_enrollment)
        self.assertEqual(denied.exception.status_code, 403)

    def test_only_records_officer_can_release_and_incomplete_report_is_blocked(self):
        from app.main import release_annex_g
        from app.auth import require_roles
        enrollment = self.add_enrollment(dob=None)
        with self.assertRaises(HTTPException) as denied:
            require_roles("records_officer")(self.teacher)
        self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(HTTPException) as blocked:
            release_annex_g(enrollment.id, 1, self.db, self.records)
        self.assertEqual(blocked.exception.status_code, 409)
        self.assertIn("date of birth", blocked.exception.detail["blockers"][0].lower())
        self.assertEqual(self.db.scalar(select(GeneratedReport.id)), None)

    def test_records_release_registers_immutable_snapshot_without_changing_scores(self):
        from app.main import annex_g_released_file, release_annex_g
        import app.services.reports as reports_service
        enrollment = self.add_enrollment()
        for term in (1, 2, 3):
            self.add_gradebook(self.math, term, 100)
        before_scores = self.db.query(StudentScore).count()
        before_attendance = self.db.query(AttendanceEvent).count()
        with tempfile.TemporaryDirectory(prefix="annex-g-report-", dir=Path(__file__).parent) as folder, \
             patch.object(reports_service, "REPORT_DIR", Path(folder)), \
             patch("app.main.REPORT_DIR", Path(folder)), \
             patch("app.services.annex_g.local_now", return_value=datetime(2026, 5, 1)):
            released = release_annex_g(enrollment.id, 3, self.db, self.records)
            record = self.db.get(GeneratedReport, released["id"])
            self.assertEqual(record.status, "Released")
            content = Path(record.file_path).read_text(encoding="utf-8")
            self.assertIn("Final Grade", content)
            self.assertIn("General Average", content)
            self.assertNotIn("2012-06-05", content)
            response = annex_g_released_file(record.id, self.db, self.records)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.query(StudentScore).count(), before_scores)
        self.assertEqual(self.db.query(AttendanceEvent).count(), before_attendance)


if __name__ == "__main__":
    unittest.main()
