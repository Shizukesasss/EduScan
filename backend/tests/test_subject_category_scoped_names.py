from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from openpyxl import load_workbook

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests import test_grading_regressions as _fixtures
from app.migrations import MIGRATIONS, run_migrations
from app.models import SchoolSection, Subject, SubjectTeachingAssignment
from app.schemas import SectionPayload, SubjectPayload
from app.main import save_section, save_subject
from app.services import reports
from app.services.shs_grading_policies import WORK_IMMERSION, ensure_shs_grading_policies
from fastapi import HTTPException


MIGRATION_VERSIONS = (
    "0030_subject_names_unique_by_category",
    "0031_subject_names_group_shs_categories",
)


class SubjectCategoryScopedNamesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _fixtures.ClassRecordRegressionTest()
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_work_immersion_can_be_created_for_each_track_without_a_cluster(self) -> None:
        for track, name in (
            ("Academic Track", "WORK IMMERSION FOR ACADEMIC TRACK"),
            ("Technical Professional (TechPro) Track", "WORK IMMERSION FOR TECH-PRO TRACK (320 HOURS)"),
            ("Technical Professional (TechPro) Track", "WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 1 TERM"),
            ("Technical Professional (TechPro) Track", "WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 1 TERM"),
            ("Technical Professional (TechPro) Track", "WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 2 TERMS"),
            ("Technical Professional (TechPro) Track", "WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 2 TERMS"),
        ):
            with self.subTest(track=track):
                saved = save_subject(SubjectPayload(
                    name=name, category="SHS", is_elective=True,
                    elective_track=track, elective_cluster=None,
                ), self.fixture.db, self.fixture.admin)
                subject = self.fixture.db.get(Subject, saved["id"])
                self.assertEqual(subject.elective_track, track)
                self.assertIsNone(subject.elective_cluster)

    def test_work_immersion_name_must_match_its_track_and_official_course(self) -> None:
        for name in ("WORK IMMERSION", "WORK IMMERSION FOR ACADEMIC TRACK"):
            with self.subTest(name=name), self.assertRaises(HTTPException) as error:
                save_subject(SubjectPayload(
                    name=name, category="SHS", is_elective=True,
                    elective_track="Technical Professional (TechPro) Track",
                ), self.fixture.db, self.fixture.admin)
            self.assertEqual(error.exception.status_code, 422)

    def _assert_grade12_work_immersion_export(self, track: str, name: str, cluster: str) -> None:
        fixture = self.fixture
        fixture.grade.name = "Grade 12"
        fixture.first.grade = fixture.second.grade = "12"
        fixture.outside.grade = "11"
        fixture.section.track = track
        fixture.section.track_cluster = cluster
        saved = save_subject(SubjectPayload(
            name=name, category="SHS", is_elective=True, elective_track=track,
        ), fixture.db, fixture.admin)
        fixture.subject = fixture.db.get(Subject, saved["id"])
        policy = ensure_shs_grading_policies(fixture.db, fixture.year, "12", fixture.admin)[WORK_IMMERSION]
        book = fixture.create(policy)
        fixture.score_student(book, 80)
        fixture.score_second_student(book, 80)
        book.status = "Finalized"
        fixture.db.commit()
        with TemporaryDirectory() as folder, patch.object(reports, "EXPORT_DIR", Path(folder)):
            path = reports.generate_gradebook_report_xlsx(
                fixture.db, book.id, "V", "Test Division", "123456",
            )
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                self.assertIn("Term 1", workbook.sheetnames)
                self.assertIn("HELPER", workbook.sheetnames)
                self.assertEqual(workbook["INPUT DATA"]["O11"].value, "First Student")
                self.assertEqual(workbook["INPUT DATA"]["S11"].value, "Second Student")
                self.assertEqual(workbook["Term 1"]["C17"].value, "First Student")
                self.assertEqual(workbook["Term 1"]["C68"].value, "Second Student")
            finally:
                workbook.close()
            formulas = load_workbook(path, read_only=True, data_only=False)
            try:
                self.assertIn("'INPUT DATA'!O11", formulas["Term 1"]["C17"].value)
                self.assertIn("'INPUT DATA'!S11", formulas["Term 1"]["C68"].value)
            finally:
                formulas.close()

    def test_grade12_academic_work_immersion_exports_official_ecr(self) -> None:
        self._assert_grade12_work_immersion_export(
            "Academic Track", "WORK IMMERSION FOR ACADEMIC TRACK", "Field Experience",
        )

    def test_grade12_techpro_work_immersion_exports_official_ecr(self) -> None:
        self._assert_grade12_work_immersion_export(
            "Technical Professional (TechPro) Track",
            "WORK IMMERSION FOR TECH-PRO TRACK (320 HOURS)",
            "Aesthetic, Wellness, and Human Care",
        )

    def test_section_reclassification_rejects_a_mismatched_active_elective_assignment(self) -> None:
        fixture = self.fixture
        fixture.section.track = "Academic Track"
        fixture.section.track_cluster = "Business and Entrepreneurship"
        elective = Subject(
            code="SHS-AC-BE-T1-TEST", name="BUSINESS TEST ELECTIVE", category="SHS",
            is_elective=True, elective_track="Academic Track",
            elective_cluster="Business and Entrepreneurship",
        )
        fixture.db.add(elective)
        fixture.db.flush()
        fixture.db.add(SubjectTeachingAssignment(
            school_year_id=fixture.year.id, subject_id=elective.id,
            section_id=fixture.section.id, teacher_user_id=fixture.teacher.id,
            active=True,
        ))
        fixture.db.commit()
        payload = SectionPayload(
            id=fixture.section.id, school_year_id=fixture.year.id,
            grade_level_id=fixture.grade.id, name=fixture.section.name,
            adviser_user_id=fixture.teacher.id, track="Academic Track",
            track_cluster="Science, Technology, Engineering, and Mathematics (STEM)",
        )
        with self.assertRaisesRegex(HTTPException, "active elective assignment"):
            save_section(payload, fixture.db, fixture.admin)
        self.assertEqual(fixture.db.get(SchoolSection, fixture.section.id).track_cluster,
                         "Business and Entrepreneurship")

    def _add_jhs_research(self) -> Subject:
        subject = Subject(
            code="RES1",
            name="RESEARCH 1",
            category="JHS",
            is_elective=True,
            elective_track="STE",
            allowed_grades=[7, 8, 9, 10],
        )
        self.fixture.db.add(subject)
        self.fixture.db.commit()
        return subject

    def test_same_subject_name_can_exist_once_in_jhs_and_shs(self) -> None:
        jhs_subject = self._add_jhs_research()
        payload = SubjectPayload(
            name="RESEARCH 1",
            category="SHS",
            is_elective=True,
            elective_track="Academic Track",
            elective_cluster="Field Experience",
        )

        result = save_subject(payload, self.fixture.db, self.fixture.admin)

        shs_subject = self.fixture.db.get(Subject, result["id"])
        self.assertEqual((shs_subject.name, shs_subject.category), ("RESEARCH 1", "SHS"))
        self.assertEqual(shs_subject.elective_track, "Academic Track")
        self.assertEqual(shs_subject.elective_cluster, "Field Experience")
        self.assertTrue(shs_subject.code.startswith("SHS-EL-"))
        self.assertEqual(
            (jhs_subject.name, jhs_subject.category, jhs_subject.code, jhs_subject.elective_track),
            ("RESEARCH 1", "JHS", "RES1", "STE"),
        )

    def test_duplicate_name_within_shs_category_is_rejected(self) -> None:
        payload = SubjectPayload(
            name="RESEARCH 1",
            category="SHS",
            is_elective=True,
            elective_track="Academic Track",
            elective_cluster="Field Experience",
        )
        save_subject(payload, self.fixture.db, self.fixture.admin)

        with self.assertRaises(HTTPException) as error:
            save_subject(payload.model_copy(update={"code": ""}), self.fixture.db, self.fixture.admin)

        self.assertEqual(error.exception.status_code, 409)

    def test_legacy_shs_category_label_uses_the_same_name_namespace(self) -> None:
        payload = SubjectPayload(
            name="RESEARCH 1",
            category="SHS",
            is_elective=True,
            elective_track="Academic Track",
            elective_cluster="Field Experience",
        )
        save_subject(payload, self.fixture.db, self.fixture.admin)

        legacy_label_payload = payload.model_copy(update={"category": "SHS-Core", "code": ""})
        with self.assertRaises(HTTPException) as error:
            save_subject(legacy_label_payload, self.fixture.db, self.fixture.admin)

        self.assertEqual(error.exception.status_code, 409)

    def test_subject_code_remains_unique_across_categories(self) -> None:
        self._add_jhs_research()
        payload = SubjectPayload(
            code="RES1",
            name="RESEARCH 2",
            category="SHS",
            is_elective=True,
            elective_track="Academic Track",
            elective_cluster="Field Experience",
        )

        with self.assertRaises(HTTPException) as error:
            save_subject(payload, self.fixture.db, self.fixture.admin)

        self.assertEqual(error.exception.status_code, 409)

    def test_migration_replaces_global_name_index_with_category_scoped_index(self) -> None:
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE subjects (id INTEGER PRIMARY KEY, code VARCHAR(40) NOT NULL, "
                    "name VARCHAR(120) NOT NULL, category VARCHAR(20) NOT NULL)"
                ))
                connection.execute(text("CREATE UNIQUE INDEX ix_subjects_name ON subjects (name)"))
                connection.execute(text("CREATE UNIQUE INDEX ix_subjects_code ON subjects (code)"))
                connection.execute(text(
                    "CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, "
                    "description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"
                ))
                for version, description in MIGRATIONS:
                    if version not in MIGRATION_VERSIONS:
                        connection.execute(text(
                            "INSERT INTO schema_migrations (version, description, applied_at) "
                            "VALUES (:version, :description, CURRENT_TIMESTAMP)"
                        ), {"version": version, "description": description})

            applied = run_migrations(engine)

            self.assertEqual(applied, list(MIGRATION_VERSIONS))
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO subjects (code, name, category) VALUES "
                    "('RES1', 'RESEARCH 1', 'JHS'), ('SHS-EL-RESEARCH-1', 'RESEARCH 1', 'SHS')"
                ))
            with self.assertRaises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO subjects (code, name, category) "
                        "VALUES ('SHS-EL-RESEARCH-1-2', 'research 1', 'SHS')"
                    ))
            with self.assertRaises(IntegrityError):
                with engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO subjects (code, name, category) "
                        "VALUES ('SHS-EL-RESEARCH-1-3', 'RESEARCH 1', 'SHS-Core')"
                    ))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
