import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.migrations import MIGRATIONS, run_migrations


class GradingTermOrderMigrationTests(unittest.TestCase):
    def test_renames_term_columns_and_preserves_values_idempotently(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, "
                "description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"
            ))
            for version, description in MIGRATIONS:
                if version == "0024_replace_quarter_with_term_order":
                    continue
                connection.execute(text(
                    "INSERT INTO schema_migrations VALUES (:version, :description, CURRENT_TIMESTAMP)"
                ), {"version": version, "description": description})
            connection.execute(text(
                "CREATE TABLE grading_policies (id INTEGER PRIMARY KEY, school_year VARCHAR(30), "
                "version VARCHAR(30), transmutation_table_json TEXT, rounding_method VARCHAR(30), "
                "rounding_final_decimal_places INTEGER)"
            ))
            for table, identity_column in (
                ("grading_periods", "id"),
                ("gradebooks", "id"),
                ("gradebook_states", "class_key"),
                ("grade_change_audits", "id"),
            ):
                identity_type = "VARCHAR(80)" if identity_column in {"class_key", "id"} and table in {"gradebook_states", "grade_change_audits"} else "INTEGER"
                connection.execute(text(
                    f"CREATE TABLE {table} ({identity_column} {identity_type} PRIMARY KEY, quarter INTEGER NOT NULL)"
                ))
            connection.execute(text("INSERT INTO grading_periods VALUES (1, 1)"))
            connection.execute(text("INSERT INTO gradebooks VALUES (1, 2)"))
            connection.execute(text("INSERT INTO gradebook_states VALUES ('legacy', 3)"))
            connection.execute(text("INSERT INTO grade_change_audits VALUES ('audit', 4)"))

        self.assertEqual(run_migrations(engine), ["0024_replace_quarter_with_term_order"])
        with engine.connect() as connection:
            for table, identity, expected in (
                ("grading_periods", "id", 1),
                ("gradebooks", "id", 2),
                ("gradebook_states", "class_key", 3),
                ("grade_change_audits", "id", 4),
            ):
                columns = {column["name"] for column in inspect(connection).get_columns(table)}
                self.assertIn("term_order", columns)
                self.assertNotIn("quarter", columns)
                value = connection.execute(text(
                    f"SELECT term_order FROM {table} WHERE {identity} = :identity"
                ), {"identity": "legacy" if identity == "class_key" else ("audit" if table == "grade_change_audits" else 1)}).scalar_one()
                self.assertEqual(value, expected)

        self.assertEqual(run_migrations(engine), [])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
