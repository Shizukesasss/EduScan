from __future__ import annotations

import json

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SystemSetting


fernet = Fernet(settings.encryption_key)


def get_json(db: Session, key: str, default):
    record = db.get(SystemSetting, key)
    if not record:
        return default
    try:
        return json.loads(record.value)
    except json.JSONDecodeError:
        return default


def set_json(db: Session, key: str, value, commit: bool = True) -> None:
    record = db.get(SystemSetting, key) or SystemSetting(key=key, value="")
    record.value = json.dumps(value)
    db.add(record)
    if commit:
        db.commit()
    else:
        db.flush()


def get_secret(db: Session, key: str, default: str = "") -> str:
    record = db.get(SystemSetting, key)
    if not record or not record.encrypted_value:
        return default
    return fernet.decrypt(record.encrypted_value).decode()


def set_secret(db: Session, key: str, value: str, commit: bool = True) -> None:
    record = db.get(SystemSetting, key) or SystemSetting(key=key, value="null")
    record.encrypted_value = fernet.encrypt(value.encode()) if value else None
    db.add(record)
    if commit:
        db.commit()
    else:
        db.flush()
