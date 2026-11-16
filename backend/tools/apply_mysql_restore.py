from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import BIOMETRIC_DIR, DATA_DIR, MODEL_DIR, TEMPLATE_DIR
from app.database import engine
from app.models import AuthSession
from app.services.backup import clear_restored_sessions, create_secure_backup, find_mysql_program, write_mysql_defaults_file


def main() -> int:
    if engine.url.get_backend_name() != "mysql":
        raise SystemExit("The configured EduScan database is not MySQL; restore was not applied.")
    if os.getenv("EDUSCAN_RESTORE_CONFIRM", "") != "APPLY MYSQL RESTORE":
        raise SystemExit("Confirmation text must be exactly: APPLY MYSQL RESTORE")
    safety_passphrase = os.getenv("EDUSCAN_BACKUP_PASSPHRASE", "")
    if len(safety_passphrase) < 12:
        raise SystemExit("A pre-restore backup passphrase of at least 12 characters is required.")
    admin_username = os.getenv("EDUSCAN_MYSQL_ADMIN_USER", "root").strip()
    admin_password = os.getenv("EDUSCAN_MYSQL_ADMIN_PASSWORD", "")
    if not admin_username or not admin_password:
        raise SystemExit("MySQL administrator credentials are required for the controlled table replacement.")

    pending = DATA_DIR / "pending_restore"
    marker = pending / "ready.json"
    sql_path = pending / "mysql.sql"
    if not marker.is_file() or not sql_path.is_file():
        raise SystemExit("No verified MySQL restore is staged. Stage an .edubak file from Administration first.")
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"The staged restore marker is invalid: {exc}") from exc
    if state.get("manifest", {}).get("database_backend") != "mysql":
        raise SystemExit("The staged backup is not a MySQL backup.")

    print("Creating a fresh encrypted safety backup of the current deployment...")
    safety_backup = create_secure_backup(safety_passphrase)
    print(f"Safety backup created: {safety_backup}")

    mysql = find_mysql_program("mysql")
    with tempfile.TemporaryDirectory(prefix="eduscan-mysql-restore-") as temporary:
        defaults_file = write_mysql_defaults_file(Path(temporary), admin_username, admin_password)
        command = [
            str(mysql),
            f"--defaults-extra-file={defaults_file}",
            "--binary-mode",
            "--default-character-set=utf8mb4",
            f"--database={engine.url.database}",
        ]
        try:
            with sql_path.open("rb") as sql_stream:
                result = subprocess.run(command, stdin=sql_stream, capture_output=True, timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SystemExit(f"MySQL restore tool could not complete: {exc}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or b"unknown mysql error").decode(errors="replace").strip()
        raise SystemExit(
            "MySQL import failed. Local encryption artifacts were not changed. "
            f"The pre-restore safety backup remains available. Details: {message[-800:]}"
        )

    engine.dispose()
    with engine.begin() as connection:
        AuthSession.__table__.create(bind=connection, checkfirst=True)
        clear_restored_sessions(connection)
        revision_count = connection.scalar(text("SELECT COUNT(*) FROM schema_migrations"))
        user_count = connection.scalar(text("SELECT COUNT(*) FROM users"))

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    recovery = DATA_DIR / f"pre_restore_{stamp}"
    recovery.mkdir(parents=True, exist_ok=False)
    directory_names = {"biometrics", "models", "templates"}
    for name in (".encryption_key", ".app_secret", *sorted(directory_names)):
        current = DATA_DIR / name
        restored = pending / name
        if name == ".app_secret" and not restored.exists():
            continue
        if current.exists():
            shutil.move(str(current), str(recovery / name))
        if restored.exists():
            shutil.move(str(restored), str(current))
        elif name in directory_names:
            current.mkdir(parents=True, exist_ok=True)

    marker.replace(recovery / "restore_applied.json")
    sql_path.unlink()
    try:
        pending.rmdir()
    except OSError:
        pass

    # Ensure expected runtime directories also exist when the backup contained no files.
    for directory in (BIOMETRIC_DIR, MODEL_DIR, TEMPLATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    print("EDUSCAN MYSQL RESTORE APPLIED")
    print(f"Schema migration rows: {revision_count}")
    print(f"User rows: {user_count}")
    print(f"Previous local artifacts: {recovery}")
    print(f"Encrypted rollback backup: {safety_backup}")
    print("Start EduScan and complete the documented recovery verification checklist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
