"""The API integration fixture must enforce the same SQLite constraints as runtime."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"

from api_test_database import isolated_app_database


class ApiTestDatabaseTest(unittest.TestCase):
    def test_foreign_keys_reject_orphan_rows(self):
        from app.database import engine
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with isolated_app_database(root / "api.db", root):
                from app import database
                with database.engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar(), 1)
        self.assertIs(database.engine, engine)
