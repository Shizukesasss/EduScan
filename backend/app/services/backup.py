from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
import uuid
import zlib
from datetime import datetime
from pathlib import Path, PureWindowsPath

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import HTTPException
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session

from ..archive_limits import check_archive_size, expanded_chunks
from ..config import BIOMETRIC_DIR, DATA_DIR, MODEL_DIR, TEMPLATE_DIR, settings
from ..database import engine
from ..models import AuthSession, BackupRun, BiometricModel, User
from ..postgres_access import application_tables
from ..request_limits import MAX_BACKUP_ARCHIVE_BYTES, MIB
from ..storage_quota import LOCK_NAME, atomic_write_path, require_capacity, storage_lock


MAGIC = b"EDUSCAN1"
BACKUP_DIR = DATA_DIR / "backups"
PENDING_DIR = DATA_DIR / "pending_restore"
MAX_BACKUP_EXPANDED_BYTES = 1024 * MIB
MAX_BACKUP_MANIFEST_BYTES = 8 * MIB


def _fernet(passphrase: str, salt: bytes) -> Fernet:
    if len(passphrase) < 12:
        raise HTTPException(status_code=422, detail="Backup passphrase must contain at least 12 characters")
    derived = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000).derive(passphrase.encode())
    return Fernet(base64.urlsafe_b64encode(derived))


def database_backend() -> str:
    return engine.url.get_backend_name()


def _sqlite_path() -> Path:
    return Path(engine.url.database).resolve()


def find_mysql_program(program: str) -> Path:
    executable = f"{program}.exe" if os.name == "nt" else program
    configured = os.getenv("EDUSCAN_MYSQL_BIN", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured) / executable)
    located = shutil.which(executable) or shutil.which(program)
    if located:
        candidates.append(Path(located))
    if os.name == "nt":
        for root_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.getenv(root_name, "").strip()
            if root:
                candidates.extend(sorted(Path(root).glob(f"MySQL/MySQL Server */bin/{executable}"), reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise HTTPException(
        status_code=409,
        detail=f"{executable} was not found. Install MySQL client tools or set EDUSCAN_MYSQL_BIN to the MySQL bin folder.",
    )


def write_mysql_defaults_file(directory: Path, username: str | None = None,
                              password: str | None = None) -> Path:
    url = engine.url
    selected_username = username if username is not None else url.username
    selected_password = password if password is not None else (url.password or "")
    if not selected_username or not url.database:
        raise HTTPException(status_code=409, detail="DATABASE_URL must include a MySQL username and database name")

    def quote(value: object) -> str:
        escaped = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    path = directory / "mysql-client.cnf"
    lines = [
        "[client]",
        f"host={quote(url.host or '127.0.0.1')}",
        f"port={int(url.port or 3306)}",
        f"user={quote(selected_username)}",
        f"password={quote(selected_password)}",
        "protocol=tcp",
        "default-character-set=utf8mb4",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mysql_dump(temporary_dir: Path) -> bytes:
    dump_tool = find_mysql_program("mysqldump")
    defaults_file = write_mysql_defaults_file(temporary_dir)
    target = temporary_dir / "mysql.sql"
    command = [
        str(dump_tool),
        f"--defaults-extra-file={defaults_file}",
        "--single-transaction",
        "--quick",
        "--skip-lock-tables",
        "--no-tablespaces",
        "--set-gtid-purged=OFF",
        "--hex-blob",
        "--add-drop-table",
        f"--ignore-table={engine.url.database}.auth_sessions",
        f"--result-file={target}",
        str(engine.url.database),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=f"MySQL backup tool could not run: {exc}") from exc
    if result.returncode != 0 or not target.exists():
        message = (result.stderr or result.stdout or "unknown mysqldump error").strip()
        raise HTTPException(status_code=500, detail=f"MySQL backup failed: {message[-600:]}")
    return target.read_bytes()


def find_postgres_program(program: str) -> Path:
    executable = f"{program}.exe" if os.name == "nt" else program
    configured = os.getenv("EDUSCAN_POSTGRES_BIN", "").strip()
    candidates = [Path(configured) / executable] if configured else []
    located = shutil.which(executable)
    if located:
        candidates.append(Path(located))
    if os.name == "nt":
        root = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "PostgreSQL"
        candidates.extend(sorted(root.glob(f"*/bin/{executable}"),
                                 key=lambda path: tuple(int(n) for n in path.parents[1].name.split(".") if n.isdigit()),
                                 reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise HTTPException(status_code=409, detail=f"{executable} was not found. Install PostgreSQL client tools or set EDUSCAN_POSTGRES_BIN to their bin folder.")


def postgres_environment(database_url=None) -> dict[str, str]:
    url = database_url or engine.url
    if not url.username or not url.database:
        raise HTTPException(status_code=409, detail="DATABASE_URL must include a PostgreSQL username and database name")
    # Credentials stay out of process arguments and tool error messages.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("PG") and key not in {"DATABASE_URL", "EDUSCAN_MIGRATION_DATABASE_URL"}}
    env.update(PGHOST=url.host or "127.0.0.1", PGPORT=str(url.port or 5432),
               PGUSER=url.username, PGPASSWORD=url.password or "", PGDATABASE=url.database,
               PGCONNECT_TIMEOUT="15", PGSSLMODE=str(url.query.get("sslmode", "prefer")))
    for option in ("sslrootcert", "sslcert", "sslkey"):
        if option in url.query:
            env[f"PG{option.upper()}"] = str(url.query[option])
    return env


def run_postgres_tool(program: str, arguments: list[str], *, database_url=None) -> None:
    try:
        result = subprocess.run([str(find_postgres_program(program)), "--no-password", *arguments],
                                env=postgres_environment(database_url), capture_output=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL {program} could not complete; the operation was stopped") from exc
    if result.returncode:
        # libpq diagnostics can contain connection details; do not return them to clients.
        raise HTTPException(status_code=500, detail=f"PostgreSQL {program} failed. Check server connectivity, client version, and database permissions.")


def _postgres_dump(temporary_dir: Path) -> bytes:
    target = temporary_dir / "postgres.dump"
    tables = [f"--table=public.{name}" for name in application_tables()]
    run_postgres_tool("pg_dump", ["--format=custom", *tables, "--no-owner", "--no-acl",
                                  "--exclude-table-data=public.auth_sessions", f"--file={target}"])
    return target.read_bytes()


def clear_restored_sessions(connection) -> None:
    if inspect(connection).has_table(AuthSession.__tablename__):
        connection.execute(delete(AuthSession))


def _database_snapshot(temporary_dir: Path) -> tuple[str, bytes, str]:
    backend = database_backend()
    if backend == "sqlite":
        snapshot = temporary_dir / "eduscan.db"
        source = sqlite3.connect(_sqlite_path())
        destination = sqlite3.connect(snapshot)
        try:
            source.backup(destination)
            if destination.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_sessions'").fetchone():
                destination.execute("DELETE FROM auth_sessions")
                destination.commit()
        finally:
            destination.close()
            source.close()
        return "eduscan.db", snapshot.read_bytes(), backend
    if backend == "mysql":
        return "mysql.sql", _mysql_dump(temporary_dir), backend
    if backend == "postgresql":
        return "postgres.dump", _postgres_dump(temporary_dir), backend
    raise HTTPException(status_code=409, detail=f"Secure backup is not implemented for database backend: {backend}")


def create_secure_backup(passphrase: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="eduscan-backup-") as temporary:
        database_name, database_data, backend = _database_snapshot(Path(temporary))
        key_path = DATA_DIR / ".encryption_key"
        if not key_path.exists():
            raise HTTPException(status_code=409, detail="The biometric encryption key is missing")
        files: dict[str, bytes] = {database_name: database_data, ".encryption_key": key_path.read_bytes()}
        app_secret = DATA_DIR / ".app_secret"
        if app_secret.exists():
            files[".app_secret"] = app_secret.read_bytes()
        for directory, prefix in ((BIOMETRIC_DIR, "biometrics"), (MODEL_DIR, "models"), (TEMPLATE_DIR, "templates")):
            for path in directory.rglob("*"):
                if path.name != LOCK_NAME and path.is_file():
                    files[f"{prefix}/{path.relative_to(directory).as_posix()}"] = path.read_bytes()
        manifest = {
            "format": 2,
            "database_backend": backend,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        if len(manifest_bytes) > MAX_BACKUP_MANIFEST_BYTES:
            raise HTTPException(413, "Backup manifest exceeds the 8 MiB decompressed size limit")
        if len(manifest_bytes) + sum(map(len, files.values())) > MAX_BACKUP_EXPANDED_BYTES:
            raise HTTPException(413, "Backup exceeds the 1 GiB decompressed size limit")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", manifest_bytes)
            for name, data in files.items():
                archive.writestr(name, data)
        salt = os.urandom(16)
        encrypted = MAGIC + salt + _fernet(passphrase, salt).encrypt(stream.getvalue())
        if len(encrypted) > MAX_BACKUP_ARCHIVE_BYTES:
            raise HTTPException(413, "Encrypted backup exceeds the 250 MiB recovery upload limit")
        target = BACKUP_DIR / f"EduScan-secure-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}.edubak"
        with storage_lock(BACKUP_DIR):
            require_capacity(BACKUP_DIR, "Backup", settings.backup_storage_mib, len(encrypted),
                             suffix=".edubak", recursive=False)
            with atomic_write_path(target) as temporary_path:
                temporary_path.write_bytes(encrypted)
        return target


def run_managed_backup(db: Session, passphrase: str, trigger: str = "Manual", user: User | None = None,
                       destination: str = "") -> BackupRun:
    key_path = DATA_DIR / ".encryption_key"
    key_fingerprint = hashlib.sha256(key_path.read_bytes()).hexdigest() if key_path.exists() else "missing"
    active_model = db.scalar(select(BiometricModel).where(BiometricModel.active.is_(True)).order_by(BiometricModel.id.desc()))
    run = BackupRun(
        id=str(uuid.uuid4()), trigger=trigger, status="Running", database_backend=database_backend(),
        encryption_key_fingerprint=key_fingerprint, model_version=active_model.version if active_model else None,
        actor_user_id=user.id if user else None, actor_name=user.full_name if user else "EduScan scheduler",
    )
    db.add(run)
    db.commit()
    path = None
    try:
        destination_path = None
        if destination.strip():
            requested_destination = Path(destination).expanduser()
            if not requested_destination.is_absolute():
                raise HTTPException(status_code=422, detail="Off-device backup destination must be an existing absolute folder")
            destination_path = requested_destination.resolve()
            if not destination_path.is_dir():
                raise HTTPException(status_code=422, detail="Off-device backup destination must be an existing absolute folder")
            if destination_path == DATA_DIR or DATA_DIR in destination_path.parents:
                raise HTTPException(status_code=422, detail="Off-device destination cannot be inside EduScan's local data folder")
        path = create_secure_backup(passphrase)
        size = path.stat().st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        final_path = path
        if destination_path is not None:
            final_path = destination_path / path.name
            with storage_lock(destination_path):
                require_capacity(destination_path, "Backup", settings.backup_storage_mib, size,
                                 suffix=".edubak", recursive=False)
                with atomic_write_path(final_path) as temporary_path:
                    shutil.copy2(path, temporary_path)
        run.status = "Completed"
        run.filename = path.name
        run.file_sha256 = digest
        run.size_bytes = size
        run.destination = str(final_path)
    except Exception as exc:
        if path is not None:
            path.unlink(missing_ok=True)
        run.status = "Failed"
        run.error = str(getattr(exc, "detail", exc))[:2000]
    db.commit()
    db.refresh(run)
    return run


def rotate_scheduled_backups(db: Session, retention_count: int) -> int:
    completed = db.scalars(select(BackupRun).where(
        BackupRun.trigger == "Scheduled", BackupRun.status == "Completed",
    ).order_by(BackupRun.created_at.desc())).all()
    removed = 0
    for run in completed[retention_count:]:
        local = BACKUP_DIR / (run.filename or "")
        if local.is_file():
            local.unlink(missing_ok=True)
            removed += 1
    return removed


def _restore_path(name: str) -> Path:
    parts = name.replace("\\", "/").split("/")
    if (parts[0].casefold() == "ready.json"
            or any(not part or part.endswith((".", " ")) or ":" in part or PureWindowsPath(part).is_reserved()
                   for part in parts)):
        raise ValueError("unsafe archive path")
    return Path(name)


def _stage_verified_files(archive: zipfile.ZipFile, manifest: dict) -> None:
    pending_conflict = HTTPException(
        status_code=409, detail="A restore is already staged; complete or cancel it through the recovery procedure",
    )
    if PENDING_DIR.exists():
        raise pending_conflict

    with tempfile.TemporaryDirectory(prefix=".restore-", dir=PENDING_DIR.parent) as temporary:
        staging = Path(temporary)
        for name, expected in manifest["files"].items():
            target = staging / _restore_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with target.open("xb") as output:
                for chunk in expanded_chunks(archive, archive.getinfo(name)):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != expected:
                raise HTTPException(status_code=422, detail=f"Backup integrity check failed for {name}")
        with (staging / "ready.json").open("x", encoding="utf-8") as marker:
            json.dump({"staged_at": datetime.utcnow().isoformat() + "Z", "manifest": manifest}, marker, indent=2)
        try:
            staging.rename(PENDING_DIR)
        except OSError as exc:
            if PENDING_DIR.exists():
                raise pending_conflict from exc
            raise


def stage_secure_restore(data: bytes, passphrase: str) -> dict:
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 17:
        raise HTTPException(status_code=422, detail="File is not an EduScan encrypted backup")
    salt = data[len(MAGIC):len(MAGIC) + 16]
    try:
        plaintext = _fernet(passphrase, salt).decrypt(data[len(MAGIC) + 16:])
    except InvalidToken as exc:
        raise HTTPException(status_code=422, detail="Backup passphrase is incorrect or the backup is damaged") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(plaintext)) as archive:
            entries = check_archive_size(archive, MAX_BACKUP_EXPANDED_BYTES, "Backup")
            names = {entry.filename for entry in entries}
            if any(name.startswith(("/", "\\")) or ".." in Path(name.replace("\\", "/")).parts for name in names):
                raise ValueError("unsafe archive path")
            manifest_entry = archive.getinfo("manifest.json")
            if manifest_entry.file_size > MAX_BACKUP_MANIFEST_BYTES:
                raise HTTPException(413, "Backup manifest exceeds the 8 MiB decompressed size limit")
            manifest = json.loads(b"".join(expanded_chunks(archive, manifest_entry)))
            if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
                raise ValueError("invalid backup manifest")
            backup_backend = manifest.get("database_backend", "sqlite")
            database_name = {"mysql": "mysql.sql", "postgresql": "postgres.dump", "sqlite": "eduscan.db"}.get(backup_backend)
            if database_name is None:
                raise ValueError("unsupported database backend")
            required = {database_name, ".encryption_key"}
            if not required.issubset(manifest["files"]):
                raise ValueError("database or encryption key is missing")
            if not manifest["files"].keys() <= names:
                raise ValueError("unsafe or missing manifest file")
            current_backend = database_backend()
            if backup_backend != current_backend:
                raise HTTPException(
                    status_code=409,
                    detail=f"This is a {backup_backend} backup, but the current EduScan deployment uses {current_backend}.",
                )
            _stage_verified_files(archive, manifest)
    except HTTPException:
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError, ValueError, TypeError, KeyError, RuntimeError,
            FileExistsError, IsADirectoryError, NotADirectoryError) as exc:
        raise HTTPException(status_code=422, detail="Backup archive validation failed") from exc
    offline_restore = backup_backend in {"mysql", "postgresql"}
    return {
        "staged": True,
        "file_count": len(manifest["files"]),
        "restart_required": not offline_restore,
        "offline_restore_required": offline_restore,
        "apply_command": {"mysql": ".\\scripts\\apply-mysql-restore.ps1", "postgresql": ".\\scripts\\apply-postgres-restore.ps1"}.get(backup_backend),
        "created_at": manifest.get("created_at"),
        "database_backend": backup_backend,
    }
