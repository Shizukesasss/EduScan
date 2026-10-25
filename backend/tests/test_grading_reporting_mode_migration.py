import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.migrations import MIGRATIONS, run_migrations


class GradingReportingModeMigrationTests(unittest.TestCase):
    def test_backfills_policy_mode_by_school_year_without_rewriting_legacy_policies(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text(
                'CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, '
                'description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)'
            ))
            for version, description in MIGRATIONS:
                if version == '0023_school_year_grading_reporting_mode':
                    continue
                connection.execute(text(
                    'INSERT INTO schema_migrations VALUES (:version, :description, CURRENT_TIMESTAMP)'
                ), {'version': version, 'description': description})
            connection.execute(text(
                'CREATE TABLE grading_policies (id INTEGER PRIMARY KEY, school_year VARCHAR(30), '
                'version VARCHAR(30), transmutation_table_json TEXT, rounding_method VARCHAR(30), '
                'rounding_final_decimal_places INTEGER)'
            ))
            connection.execute(text(
                'INSERT INTO grading_policies VALUES '
                "(1, '2026-2027', 'Updated-Excel-3Term-v1', '[{}]', 'floor', 2), "
                "(2, '2026-2027', '1.0', '[{}]', 'floor', 2), "
                "(3, '2027-2028', '1.0', '[{}]', 'floor', 2), "
                "(4, '2025-2026', 'Updated-Excel-3Term-v1', '[{}]', 'floor', 2)"
            ))

        self.assertEqual(run_migrations(engine), ['0023_school_year_grading_reporting_mode'])
        with engine.connect() as connection:
            methods = dict(connection.execute(text(
                'SELECT id, reporting_method FROM grading_policies'
            )).all())
            direct_rounding = connection.execute(text(
                'SELECT rounding_method, rounding_final_decimal_places FROM grading_policies WHERE id=3'
            )).one()
        self.assertEqual(methods, {1: 'adjusted_2026', 2: 'legacy', 3: 'direct', 4: 'legacy'})
        self.assertEqual(direct_rounding, ('half_up', 0))
        self.assertEqual(run_migrations(engine), [])
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
