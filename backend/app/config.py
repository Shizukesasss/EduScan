from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("EDUSCAN_DATA_DIR", str(BASE_DIR / "data"))).resolve()
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
    if key_path.exists():
        return key_path.read_bytes().strip()
    key = Fernet.generate_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def _application_secret() -> str:
    supplied = os.getenv("EDUSCAN_SECRET_KEY", "").strip()
    if supplied and supplied != "eduscan-development-secret-change-before-production":
        return supplied
    secret_path = DATA_DIR / ".app_secret"
    if secret_path.exists():
        existing = secret_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 48:
            return existing
    generated = secrets.token_urlsafe(64)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(generated, encoding="utf-8")
    return generated


_load_dotenv()
DATA_DIR.mkdir(parents=True, exist_ok=True)
_apply_pending_restore()
for directory in (DATA_DIR, BIOMETRIC_DIR, MODEL_DIR, TEMPLATE_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/eduscan.db")
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
    attendance_scheduler_enabled: bool = os.getenv("ATTENDANCE_SCHEDULER_ENABLED", "true").lower() == "true"


settings = Settings()
