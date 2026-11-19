"""Encrypted backup/recovery round trip against a disposable local PostgreSQL cluster."""
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

TEST_DIR = tempfile.TemporaryDirectory(prefix="eduscan-postgres-backup-")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["EDUSCAN_DATA_DIR"] = str(Path(TEST_DIR.name) / "app-data")
os.environ["EDUSCAN_SECRET_KEY"] = "isolated-postgres-backup-tests"
os.environ["ATTENDANCE_SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.services import backup


class PostgresBackupUnitTest(unittest.TestCase):
    def test_maintenance_url_requires_same_supabase_project_and_a_different_role(self):
        from app.postgres_access import maintenance_url

        runtime = make_url("postgresql://eduscan_app.project@aws-0-example.pooler.supabase.com:5432/postgres")
        owner = runtime.set(username="postgres.project")
        self.assertEqual(maintenance_url(runtime, owner), owner)
        with self.assertRaisesRegex(RuntimeError, "same Supabase project"):
            maintenance_url(runtime, owner.set(username="postgres.other-project"))
        with self.assertRaisesRegex(RuntimeError, "separate EduScan logins"):
            maintenance_url(runtime, runtime.set(password="different"))

    def test_creation_does_not_publish_a_backup_that_exceeds_the_restore_budget(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR.name) as temporary:
            root = Path(temporary)
            (root / ".encryption_key").write_bytes(b"synthetic fixture key")
            destination = root / "backups"
            with (patch.object(backup, "DATA_DIR", root),
                  patch.object(backup, "BACKUP_DIR", destination),
                  patch.object(backup, "BIOMETRIC_DIR", root / "biometrics"),
                  patch.object(backup, "MODEL_DIR", root / "models"),
                  patch.object(backup, "TEMPLATE_DIR", root / "templates"),
                  patch.object(backup, "_database_snapshot", return_value=("eduscan.db", b"synthetic snapshot", "sqlite")),
                  patch.object(backup, "MAX_BACKUP_EXPANDED_BYTES", 64)):
                with self.assertRaises(HTTPException) as error:
                    backup.create_secure_backup("Synthetic restore passphrase")
            self.assertEqual(error.exception.status_code, 413)
            self.assertEqual(list(destination.iterdir()), [])

    def test_password_is_not_in_arguments_or_returned_errors(self):
        fake_engine = type("Engine", (), {"url": make_url("postgresql://test:secret-password@127.0.0.1/test?sslmode=require")})()
        result = subprocess.CompletedProcess([], 1, stderr=b"secret-password")
        with patch.object(backup, "engine", fake_engine), patch.object(backup, "find_postgres_program", return_value=Path("pg_dump")), patch.object(backup.subprocess, "run", return_value=result) as run:
            with self.assertRaises(HTTPException) as error:
                backup.run_postgres_tool("pg_dump", ["--format=custom"])
            self.assertNotIn("secret-password", str(error.exception.detail))
            self.assertNotIn("secret-password", str(run.call_args.args))
            self.assertEqual(run.call_args.kwargs["env"]["PGPASSWORD"], "secret-password")
            self.assertEqual(run.call_args.kwargs["env"]["PGSSLMODE"], "require")

    def test_wrong_passphrase_and_unsupported_manifest_fail_before_staging(self):
        salt = b"0" * 16
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("manifest.json", json.dumps({"database_backend": "unknown", "files": {}}))
        data = backup.MAGIC + salt + backup._fernet("test-passphrase-2026", salt).encrypt(archive.getvalue())
        with self.assertRaises(HTTPException):
            backup.stage_secure_restore(data, "wrong-passphrase-2026")
        with self.assertRaises(HTTPException):
            backup.stage_secure_restore(data, "test-passphrase-2026")
        self.assertFalse(backup.PENDING_DIR.exists())


class PostgresBackupRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.bin_dir = backup.find_postgres_program("pg_dump").parent
        except HTTPException:
            raise unittest.SkipTest("PostgreSQL server/client tools are not installed")
        suffix = ".exe" if os.name == "nt" else ""
        cls.pg_ctl = cls.bin_dir / ("pg_ctl" + suffix)
        initdb = cls.bin_dir / ("initdb" + suffix)
        if not initdb.is_file() or not cls.pg_ctl.is_file():
            raise unittest.SkipTest("Local PostgreSQL server tools are not installed")
        cls.cluster = Path(TEST_DIR.name) / "cluster"
        cls.log = Path(TEST_DIR.name) / "postgres.log"
        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            cls.port = port_socket.getsockname()[1]
        result = subprocess.run([str(initdb), "-D", str(cls.cluster), "-U", "eduscan_test", "--auth=trust",
                                 "--no-locale", "--encoding=UTF8", "--no-sync"], capture_output=True, timeout=300)
        if result.returncode:
            raise RuntimeError("Isolated PostgreSQL initdb failed: " + result.stderr.decode(errors="replace"))
        result = subprocess.run([str(cls.pg_ctl), "-D", str(cls.cluster), "-l", str(cls.log), "-o", f"-h 127.0.0.1 -p {cls.port}", "-w", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if result.returncode:
            raise RuntimeError("Isolated PostgreSQL start failed; see the test cluster log")
        cls.engine = create_engine(f"postgresql+psycopg2://eduscan_test@127.0.0.1:{cls.port}/postgres", connect_args={"connect_timeout": 5})

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        subprocess.run([str(cls.pg_ctl), "-D", str(cls.cluster), "-m", "fast", "-w", "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)

    def test_restricted_runtime_can_read_schema_and_write_app_data_but_cannot_run_ddl(self):
        from dataclasses import replace
        from app import main
        from app.auth import SESSION_REQUEST_HEADER, hash_password
        from app.database import get_db
        from app.migrations import initialize_database, run_migrations
        from app.postgres_access import audit_postgres_access, configure_postgres_access
        from sqlalchemy.exc import ProgrammingError
        from sqlalchemy.orm import sessionmaker
        from fastapi.testclient import TestClient

        run_migrations(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("CREATE ROLE eduscan_test_runtime LOGIN"))
            conn.execute(text("CREATE ROLE anon NOLOGIN"))
            conn.execute(text("CREATE ROLE authenticated NOLOGIN"))
            conn.execute(text("CREATE ROLE service_role NOLOGIN"))
            conn.execute(text("GRANT SELECT ON public.users TO anon, authenticated, service_role"))
            conn.execute(text("GRANT UPDATE (full_name) ON public.users TO anon"))
            conn.execute(text("CREATE TABLE public.other_project_table (id integer)"))
            conn.execute(text("GRANT SELECT ON public.other_project_table TO anon"))
            configure_postgres_access(conn, "eduscan_test_runtime")
            audit = audit_postgres_access(conn, "eduscan_test_runtime")
            self.assertEqual(audit["data_api_grants"], [])
            self.assertEqual(audit["runtime_issues"], [])
            self.assertTrue(conn.scalar(text("SELECT has_table_privilege('anon', 'public.other_project_table', 'SELECT')")))
        runtime = create_engine(self.engine.url.set(username="eduscan_test_runtime"))
        try:
            initialize_database(runtime)
            from app.models import User
            sessions = sessionmaker(bind=runtime)
            password = "Runtime-Test-Password2026!"
            with sessions() as db:
                db.add(User(username="runtime_test", full_name="Runtime Test", role="teacher",
                            password_hash=hash_password(password), must_change_password=False))
                db.commit()
                self.assertEqual(db.scalar(text("SELECT full_name FROM public.users WHERE username='runtime_test'")), "Runtime Test")

            def runtime_db():
                with sessions() as db:
                    yield db

            settings = replace(main.settings, seed_demo_accounts=False, attendance_scheduler_enabled=False)
            with (patch.object(main, "engine", runtime), patch.object(main, "SessionLocal", sessions),
                  patch.object(main, "settings", settings),
                  patch.dict(main.app.dependency_overrides, {get_db: runtime_db})):
                with TestClient(main.app, base_url="https://testserver", headers={SESSION_REQUEST_HEADER: "1"}) as client:
                    login = client.post("/api/auth/login", json={"username": "runtime_test", "password": password})
                    self.assertEqual(login.status_code, 200, login.text)
                    profile = client.get("/api/auth/me")
                    self.assertEqual(profile.status_code, 200, profile.text)
                    self.assertEqual(profile.json()["role"], "teacher")
            with tempfile.TemporaryDirectory(dir=TEST_DIR.name) as temporary, patch.object(backup, "engine", runtime):
                self.assertTrue(backup._postgres_dump(Path(temporary)).startswith(b"PGDMP"))
            with self.assertRaises(ProgrammingError), runtime.begin() as conn:
                conn.execute(text("CREATE TABLE public.unauthorized_runtime_table (id integer)"))
            with self.assertRaises(ProgrammingError), runtime.begin() as conn:
                conn.execute(text("DELETE FROM public.schema_migrations"))
        finally:
            runtime.dispose()

    def test_encrypted_backup_stage_and_controlled_restore(self):
        passphrase = "isolated-backup-passphrase"
        with self.engine.begin() as db:
            db.execute(text("CREATE ROLE eduscan_restore_runtime LOGIN"))
            db.execute(text("CREATE TABLE audit_parent (id SERIAL PRIMARY KEY, name TEXT NOT NULL)"))
            db.execute(text("CREATE TABLE audit_child (id SERIAL PRIMARY KEY, parent_id INTEGER REFERENCES audit_parent(id))"))
            db.execute(text("INSERT INTO audit_parent(name) VALUES ('original')"))
            db.execute(text("INSERT INTO audit_child(parent_id) VALUES (1)"))
        sample = backup.BIOMETRIC_DIR / "test.enc"
        sample.write_bytes(b"original encrypted face artifact")
        key = (backup.DATA_DIR / ".encryption_key").read_bytes()
        with (patch.object(backup, "engine", self.engine), patch("app.database.engine", self.engine),
              patch.object(backup, "application_tables", return_value=["audit_parent", "audit_child"])):
            archive = backup.create_secure_backup(passphrase)
            result = backup.stage_secure_restore(archive.read_bytes(), passphrase)
            self.assertTrue(result["offline_restore_required"])
            self.assertFalse(result["restart_required"])
            self.assertIn("apply-postgres-restore.ps1", result["apply_command"])
            # Restarting/importing configuration must never apply a server restore.
            from app.config import _apply_pending_restore
            _apply_pending_restore()
            self.assertEqual((backup.DATA_DIR / ".encryption_key").read_bytes(), key)
            self.assertTrue((backup.PENDING_DIR / "ready.json").exists())
            with self.engine.begin() as db:
                db.execute(text("UPDATE audit_parent SET name='changed'"))
                db.execute(text("CREATE SCHEMA restore_blocker"))
                db.execute(text("CREATE TABLE restore_blocker.dependency (parent_id INTEGER REFERENCES public.audit_parent(id))"))
            restore_args = ["--dbname=postgres", "--clean", "--if-exists", "--no-owner", "--no-acl",
                            "--single-transaction", "--exit-on-error", "--schema=public", str(backup.PENDING_DIR / "postgres.dump")]
            with self.assertRaises(HTTPException):
                backup.run_postgres_tool("pg_restore", restore_args)
            with self.engine.begin() as db:
                self.assertEqual(db.scalar(text("SELECT name FROM audit_parent")), "changed")
                self.assertEqual(db.scalar(text("SELECT count(*) FROM audit_child")), 1)
                db.execute(text("DROP TABLE restore_blocker.dependency"))
                db.execute(text("DROP SCHEMA restore_blocker"))
            sample.write_bytes(b"changed local artifact")
            path = Path(__file__).resolve().parents[1] / "tools/apply_postgres_restore.py"
            spec = importlib.util.spec_from_file_location("test_postgres_restore_tool", path)
            tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
            runtime = create_engine(self.engine.url.set(username="eduscan_restore_runtime"))
            try:
                with (patch("app.database.engine", runtime),
                      patch.dict(os.environ, {"EDUSCAN_RESTORE_CONFIRM": "APPLY POSTGRES RESTORE",
                                              "EDUSCAN_BACKUP_PASSPHRASE": passphrase,
                                              "EDUSCAN_MIGRATION_DATABASE_URL": self.engine.url.render_as_string(hide_password=False)})):
                    self.assertEqual(tool.main(), 0)
            finally:
                runtime.dispose()
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text("SELECT name FROM audit_parent")), "original")
            self.assertEqual(db.scalar(text("SELECT count(*) FROM audit_child")), 1)
        self.assertEqual(sample.read_bytes(), b"original encrypted face artifact")
        self.assertEqual((backup.DATA_DIR / ".encryption_key").read_bytes(), key)
        self.assertFalse(backup.PENDING_DIR.exists())
        self.assertTrue(list(backup.DATA_DIR.glob("pre_restore_*/staged_restore/postgres.dump")))


if __name__ == "__main__":
    unittest.main()
