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
        result = subprocess.run([str(initdb), "-D", str(cls.cluster), "-U", "eduscan_test", "--auth=trust", "--no-locale", "--encoding=UTF8"], capture_output=True, timeout=60)
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

    def test_encrypted_backup_stage_and_controlled_restore(self):
        passphrase = "isolated-backup-passphrase"
        with self.engine.begin() as db:
            db.execute(text("CREATE TABLE audit_parent (id SERIAL PRIMARY KEY, name TEXT NOT NULL)"))
            db.execute(text("CREATE TABLE audit_child (id SERIAL PRIMARY KEY, parent_id INTEGER REFERENCES audit_parent(id))"))
            db.execute(text("INSERT INTO audit_parent(name) VALUES ('original')"))
            db.execute(text("INSERT INTO audit_child(parent_id) VALUES (1)"))
        sample = backup.BIOMETRIC_DIR / "test.enc"
        sample.write_bytes(b"original encrypted face artifact")
        key = (backup.DATA_DIR / ".encryption_key").read_bytes()
        with patch.object(backup, "engine", self.engine), patch("app.database.engine", self.engine):
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
            with patch.dict(os.environ, {"EDUSCAN_RESTORE_CONFIRM": "APPLY POSTGRES RESTORE", "EDUSCAN_BACKUP_PASSPHRASE": passphrase}):
                self.assertEqual(tool.main(), 0)
        with self.engine.connect() as db:
            self.assertEqual(db.scalar(text("SELECT name FROM audit_parent")), "original")
            self.assertEqual(db.scalar(text("SELECT count(*) FROM audit_child")), 1)
        self.assertEqual(sample.read_bytes(), b"original encrypted face artifact")
        self.assertEqual((backup.DATA_DIR / ".encryption_key").read_bytes(), key)
        self.assertFalse(backup.PENDING_DIR.exists())
        self.assertTrue(list(backup.DATA_DIR.glob("pre_restore_*/staged_restore/postgres.dump")))


if __name__ == "__main__":
    unittest.main()
