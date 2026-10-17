"""Apply a verified PostgreSQL recovery only through the stopped-server wrapper."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    from app.config import DATA_DIR
    from app.database import engine
    from app.services.backup import create_secure_backup, find_postgres_program, run_postgres_tool

    if engine.url.get_backend_name() != "postgresql":
        raise SystemExit("The configured database is not PostgreSQL; restore was not applied.")
    if os.getenv("EDUSCAN_RESTORE_CONFIRM") != "APPLY POSTGRES RESTORE":
        raise SystemExit("Confirmation must be exactly: APPLY POSTGRES RESTORE")
    passphrase = os.getenv("EDUSCAN_BACKUP_PASSPHRASE", "")
    if len(passphrase) < 12:
        raise SystemExit("A safety-backup passphrase of at least 12 characters is required.")
    pending = DATA_DIR / "pending_restore"
    marker = pending / "ready.json"
    if not marker.is_file():
        raise SystemExit("No verified PostgreSQL restore is staged.")
    manifest = json.loads(marker.read_text(encoding="utf-8"))["manifest"]
    if manifest.get("database_backend") != "postgresql":
        raise SystemExit("The staged backup is not PostgreSQL.")
    files = manifest.get("files", {})
    if not {"postgres.dump", ".encryption_key"}.issubset(files):
        raise SystemExit("The staged database or encryption key is missing.")
    for name, digest in files.items():
        target = (pending / name).resolve()
        if not target.is_relative_to(pending.resolve()) or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise SystemExit("Staged restore integrity check failed; no restore was applied.")
    find_postgres_program("pg_restore")
    safety_backup = create_secure_backup(passphrase)
    print(f"Encrypted safety backup created: {safety_backup}")
    # One transaction leaves the current database intact if any restore statement fails.
    run_postgres_tool("pg_restore", ["--dbname=" + str(engine.url.database), "--clean", "--if-exists",
                                    "--no-owner", "--no-acl", "--single-transaction", "--exit-on-error",
                                    "--schema=public", str(pending / "postgres.dump")])
    engine.dispose()
    recovery = DATA_DIR / f"pre_restore_{datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')}"
    recovery.mkdir()
    for name in (".encryption_key", ".app_secret", "biometrics", "models", "templates"):
        restored, current = pending / name, DATA_DIR / name
        if name == ".app_secret" and not restored.exists():
            continue
        if current.exists():
            shutil.move(str(current), str(recovery / name))
        if restored.exists():
            shutil.move(str(restored), str(current))
        elif name in {"biometrics", "models", "templates"}:
            current.mkdir()
    # Retain the verified dump and manifest without blocking the next restore.
    pending.replace(recovery / "staged_restore")
    print(f"PostgreSQL restore applied. Previous local files: {recovery}")
    print("Keep the safety backup and verify the deployment before resuming scanning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
