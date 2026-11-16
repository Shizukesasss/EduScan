from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet


BASE_DIR = Path(__file__).resolve().parents[1]
_is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
_default_data_dir = "/tmp/eduscan_data" if _is_serverless else str(BASE_DIR / "data")
DATA_DIR = Path(os.getenv("EDUSCAN_DATA_DIR", _default_data_dir)).resolve()
BIOMETRIC_DIR = DATA_DIR / "biometrics"
MODEL_DIR = DATA_DIR / "models"
TEMPLATE_DIR = DATA_DIR / "templates"
EXPORT_DIR = DATA_DIR / "exports"


def _apply_pending_restore() -> None:
    pending = DATA_DIR / "pending_restore"
    marker = pending / "ready.json"
    if not marker.exists():
        return
    try:
        restore_state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if restore_state.get("manifest", {}).get("database_backend", "sqlite") != "sqlite":
        # A server database restore must be performed while the API is stopped by the
        # controlled restore tool. Importing SQL during module import could
        # leave a partially restored live database.
        return
    restored_db = pending / "eduscan.db"
    if not restored_db.is_file():
        return
    with closing(sqlite3.connect(restored_db)) as connection, connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_sessions'").fetchone():
            connection.execute("DELETE FROM auth_sessions")
    stamp = __import__("datetime").datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    recovery = DATA_DIR / f"pre_restore_{stamp}"
    recovery.mkdir(parents=True, exist_ok=True)
    for name in ("eduscan.db", ".encryption_key", ".app_secret", "biometrics", "models", "templates"):
        current = DATA_DIR / name
        restored = pending / name
        if name == ".app_secret" and not restored.exists():
            continue
        if current.exists():
            current.replace(recovery / name)
        if restored.exists():
            restored.replace(current)
    marker.replace(recovery / "restore_applied.json")
    try:
        pending.rmdir()
    except OSError:
        pass


def _load_dotenv() -> None:
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _encryption_key() -> bytes:
    supplied = os.getenv("EDUSCAN_ENCRYPTION_KEY", "").strip()
    if supplied:
        return supplied.encode()
    key_path = DATA_DIR / ".encryption_key"
    try:
        if key_path.exists():
            return key_path.read_bytes().strip()
    except OSError:
        pass
    key = Fernet.generate_key()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
    except OSError:
        pass
    return key


def _application_secret() -> str:
    supplied = os.getenv("EDUSCAN_SECRET_KEY", "").strip()
    if supplied and supplied != "eduscan-development-secret-change-before-production":
        return supplied
    secret_path = DATA_DIR / ".app_secret"
    try:
        if secret_path.exists():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if len(existing) >= 48:
                return existing
    except OSError:
        pass
    generated = secrets.token_urlsafe(64)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(generated, encoding="utf-8")
    except OSError:
        pass
    return generated


_load_dotenv()
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _apply_pending_restore()
    for directory in (DATA_DIR, BIOMETRIC_DIR, MODEL_DIR, TEMPLATE_DIR, EXPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
except OSError:
    DATA_DIR = Path("/tmp/eduscan_data").resolve()
    BIOMETRIC_DIR = DATA_DIR / "biometrics"
    MODEL_DIR = DATA_DIR / "models"
    TEMPLATE_DIR = DATA_DIR / "templates"
    EXPORT_DIR = DATA_DIR / "exports"
    for directory in (DATA_DIR, BIOMETRIC_DIR, MODEL_DIR, TEMPLATE_DIR, EXPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class Settings:
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    # Enable after explicitly linking existing privileged accounts; see the rollout guide.
    deped_only: bool = os.getenv("EDUSCAN_DEPED_ONLY", "false").lower() == "true"
    deped_password_recovery: bool = os.getenv("EDUSCAN_DEPED_PASSWORD_RECOVERY", "false").lower() == "true"
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT") or "587")
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "").strip()
    database_url: str = os.getenv("DATABASE_URL", "sqlite:////tmp/eduscan_data/eduscan.db" if _is_serverless else "sqlite:///./data/eduscan.db")
    seed_demo_accounts: bool = os.getenv(
        "EDUSCAN_SEED_DEMO_ACCOUNTS", "true" if database_url.startswith("sqlite") else "false"
    ).lower() == "true"
    enable_api_docs: bool = os.getenv(
        "EDUSCAN_ENABLE_API_DOCS", "true" if database_url.startswith("sqlite") else "false"
    ).lower() == "true"
    secret_key: str = _application_secret()
    encryption_key: bytes = _encryption_key()
    lbph_threshold: float = float(os.getenv("LBPH_THRESHOLD", "65"))
    min_samples: int = int(os.getenv("BIOMETRIC_MIN_SAMPLES", "15"))
    biometric_enabled: bool = os.getenv("BIOMETRIC_ENABLED", "true").lower() == "true"
    allowed_origins: tuple[str, ...] = tuple(item.strip() for item in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://127.0.0.1:5174").split(",") if item.strip())
    sf2_template_path: str = os.getenv("SF2_TEMPLATE_PATH", "")
    sms_gateway_enabled: bool = os.getenv("SMS_GATEWAY_ENABLED", "false").lower() == "true"
    sms_gateway_url: str = os.getenv("SMS_GATEWAY_URL", "http://192.168.1.100:8080")
    sms_gateway_username: str = os.getenv("SMS_GATEWAY_USERNAME", "")
    sms_gateway_password: str = os.getenv("SMS_GATEWAY_PASSWORD", "")
    attendance_scheduler_enabled: bool = os.getenv("ATTENDANCE_SCHEDULER_ENABLED", "false" if _is_serverless else "true").lower() == "true"
    biometric_storage_mib: int = _positive_int("EDUSCAN_BIOMETRIC_STORAGE_MIB", 1024)
    report_storage_mib: int = _positive_int("EDUSCAN_REPORT_STORAGE_MIB", 2048)
    backup_storage_mib: int = _positive_int("EDUSCAN_BACKUP_STORAGE_MIB", 4096)
    camera_requests_per_minute: int = _positive_int("EDUSCAN_CAMERA_REQUESTS_PER_MINUTE", 120)
    report_requests_per_minute: int = _positive_int("EDUSCAN_REPORT_REQUESTS_PER_MINUTE", 30)
    backup_requests_per_minute: int = _positive_int("EDUSCAN_BACKUP_REQUESTS_PER_MINUTE", 6)
    password_sign_in_requests_per_minute: int = _positive_int("EDUSCAN_PASSWORD_SIGN_IN_REQUESTS_PER_MINUTE", 30)
    google_sign_in_requests_per_minute: int = _positive_int("EDUSCAN_GOOGLE_SIGN_IN_REQUESTS_PER_MINUTE", 30)
    reset_requests_per_minute: int = _positive_int("EDUSCAN_RESET_REQUESTS_PER_MINUTE", 12)
    reset_confirmations_per_minute: int = _positive_int("EDUSCAN_RESET_CONFIRMATIONS_PER_MINUTE", 30)
    sms_requests_per_minute: int = _positive_int("EDUSCAN_SMS_REQUESTS_PER_MINUTE", 20)
    sms_gateway_requests_per_minute: int = _positive_int("EDUSCAN_SMS_GATEWAY_REQUESTS_PER_MINUTE", 30)


settings = Settings()
