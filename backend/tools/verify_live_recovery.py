"""Verify a live PostgreSQL backup by restoring only into a private local test cluster."""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Create an encrypted live backup and verify it on a disposable localhost server")
    args = parser.parse_args()
    if not args.run:
        parser.error("Explicit --run is required; the live database is never a restore target")
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    if (backend / "data/pending_restore/ready.json").exists():
        raise SystemExit("Finish the staged recovery before running this check.")
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine, text
    import app.config as config
    import app.database as database
    from app.services import backup

    live_engine = database.engine
    if live_engine.url.get_backend_name() != "postgresql":
        raise SystemExit("The configured source is not PostgreSQL.")
    private_root = config.DATA_DIR / "recovery_checks"
    private_root.mkdir(exist_ok=True)
    passphrase = secrets.token_urlsafe(36)
    report = {"live_restore_attempted": False}
    with tempfile.TemporaryDirectory(prefix="live-recovery-", dir=private_root) as temporary:
        work = Path(temporary).resolve()
        pg_bin = backup.find_postgres_program("pg_dump").parent
        suffix = ".exe" if os.name == "nt" else ""
        pg_ctl, initdb = pg_bin / ("pg_ctl" + suffix), pg_bin / ("initdb" + suffix)
        if not pg_ctl.is_file() or not initdb.is_file():
            raise SystemExit("Local PostgreSQL server tools are required for isolated recovery verification.")
        cluster, log = work / "cluster", work / "postgres.log"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        subprocess.run([str(initdb), "-D", str(cluster), "-U", "eduscan_recovery", "--auth=trust", "--no-locale", "--encoding=UTF8"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        subprocess.run([str(pg_ctl), "-D", str(cluster), "-l", str(log), "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        clone_engine = create_engine(f"postgresql+psycopg2://eduscan_recovery@127.0.0.1:{port}/postgres", connect_args={"connect_timeout": 5})
        try:
            original_tool = backup.run_postgres_tool
            with live_engine.connect() as source:
                source.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                assert source.scalar(text("SHOW transaction_read_only")) == "on"
                snapshot = source.scalar(text("SELECT pg_export_snapshot()"))
                tables = list(source.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")))
                expected = {table: source.scalar(text(f"SELECT count(*) FROM public.{live_engine.dialect.identifier_preparer.quote(table)}")) for table in tables}
                def snapshot_dump(program, arguments):
                    if program != "pg_dump":
                        raise RuntimeError("Only read-only pg_dump may access the live source")
                    original_tool(program, [*arguments, f"--snapshot={snapshot}"])
                with patch.object(backup, "run_postgres_tool", side_effect=snapshot_dump):
                    archive = backup.create_secure_backup(passphrase)
                source.rollback()
            # Retain the encrypted backup and protect its random passphrase with the existing local key.
            key_file = private_root / f"{archive.stem}-passphrase.enc"
            key_file.write_bytes(Fernet(config.settings.encryption_key).encrypt(passphrase.encode()))
            report.update(encrypted_backup=str(archive), protected_passphrase=str(key_file), source_read_only=True)
            clone_data = work / "app-data"
            clone_data.mkdir()
            for directory in ("biometrics", "models", "templates", "backups"):
                (clone_data / directory).mkdir()
            (clone_data / ".encryption_key").write_bytes(config.settings.encryption_key)
            restore_spec = importlib.util.spec_from_file_location("eduscan_verify_restore", backend / "tools/apply_postgres_restore.py")
            restore = importlib.util.module_from_spec(restore_spec)
            restore_spec.loader.exec_module(restore)
            with contextlib.ExitStack() as patches:
                patches.enter_context(patch.object(database, "engine", clone_engine))
                patches.enter_context(patch.object(config, "DATA_DIR", clone_data))
                for name, value in {
                    "engine": clone_engine, "DATA_DIR": clone_data, "BIOMETRIC_DIR": clone_data / "biometrics",
                    "MODEL_DIR": clone_data / "models", "TEMPLATE_DIR": clone_data / "templates",
                    "BACKUP_DIR": clone_data / "backups", "PENDING_DIR": clone_data / "pending_restore",
                }.items():
                    patches.enter_context(patch.object(backup, name, value))
                # The production restore function can only see the disposable localhost engine here.
                assert backup.engine.url.host == "127.0.0.1" and backup.engine.url.port == port
                staged = backup.stage_secure_restore(archive.read_bytes(), passphrase)
                patches.enter_context(patch.dict(os.environ, {"EDUSCAN_RESTORE_CONFIRM": "APPLY POSTGRES RESTORE", "EDUSCAN_BACKUP_PASSPHRASE": passphrase}))
                with contextlib.redirect_stdout(io.StringIO()):
                    restore.main()
                assert not (clone_data / "pending_restore").exists()
                report["archive_files_verified"] = staged["file_count"]
            with clone_engine.connect() as clone:
                restored = {table: clone.scalar(text(f"SELECT count(*) FROM public.{clone_engine.dialect.identifier_preparer.quote(table)}")) for table in tables}
                assert expected == restored, "Restored counts do not match the exported live snapshot"
            report.update(tables_verified=len(tables), rows_verified=sum(expected.values()), row_counts_match=True,
                          matching_local_encryption_key=(clone_data / ".encryption_key").read_bytes() == config.settings.encryption_key,
                          result="passed")
        finally:
            clone_engine.dispose()
            live_engine.dispose()
            subprocess.run([str(pg_ctl), "-D", str(cluster), "-m", "fast", "-w", "stop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True)
        # TemporaryDirectory removes only this newly created test cluster and plaintext staging files.
    target = private_root / f"{archive.stem}-verification.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Verification report: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
