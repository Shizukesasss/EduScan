import unittest

from sqlalchemy import create_engine, inspect, text

from app.migrations import MIGRATIONS, run_migrations


class PersonDateOfBirthMigrationTests(unittest.TestCase):
    def test_adds_nullable_birth_date_and_is_idempotent(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE schema_migrations (version VARCHAR(80) PRIMARY KEY, "
                "description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"
            ))
            for version, description in MIGRATIONS[:-2]:
                connection.execute(text(
                    "INSERT INTO schema_migrations VALUES (:version, :description, CURRENT_TIMESTAMP)"
                ), {"version": version, "description": description})
            connection.execute(text(
                "CREATE TABLE persons (id INTEGER PRIMARY KEY, full_name VARCHAR(180) NOT NULL)"
            ))
            connection.execute(text("INSERT INTO persons (id, full_name) VALUES (1, 'Legacy Learner')"))

        self.assertEqual(run_migrations(engine), ["0025_person_date_of_birth", "0026_annex_g_enrollment_and_comments"])
        with engine.connect() as connection:
            columns = {column["name"]: column for column in inspect(connection).get_columns("persons")}
            self.assertIn("date_of_birth", columns)
            self.assertTrue(columns["date_of_birth"]["nullable"])
            self.assertIsNone(connection.execute(
                text("SELECT date_of_birth FROM persons WHERE id = 1")
            ).scalar_one())
        self.assertEqual(run_migrations(engine), [])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
