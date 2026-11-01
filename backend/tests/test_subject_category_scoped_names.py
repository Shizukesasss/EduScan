from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests import test_grading_regressions as _fixtures
from app.migrations import MIGRATIONS, run_migrations
from app.models import Subject
from app.schemas import SubjectPayload
from app.main import save_subject
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
