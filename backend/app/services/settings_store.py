from __future__ import annotations

import json

from cryptography.fernet import Fernet
from sqlalchemy import case
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SystemSetting


fernet = Fernet(settings.encryption_key)


def upsert_value(db: Session, key: str, value: str, updated_at, *, preserve: str | None = None) -> None:
    values = {"key": key, "value": value, "updated_at": updated_at}
    dialect = db.get_bind().dialect.name
    if dialect in {"mysql", "mariadb"}:
        new_value = case((SystemSetting.value == preserve, preserve), else_=value) if preserve is not None else value
        statement = mysql_insert(SystemSetting).values(**values).on_duplicate_key_update(
            value=new_value, updated_at=updated_at,
        )
    else:
        insert = postgres_insert if dialect == "postgresql" else sqlite_insert
        statement = insert(SystemSetting).values(**values).on_conflict_do_update(
            index_elements=[SystemSetting.key], set_={"value": value, "updated_at": updated_at},
            where=SystemSetting.value != preserve if preserve is not None else None,
        )
    db.execute(statement)


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
    try:
        return fernet.decrypt(record.encrypted_value).decode()
    except Exception:
        return default


def set_secret(db: Session, key: str, value: str, commit: bool = True) -> None:
    record = db.get(SystemSetting, key) or SystemSetting(key=key, value="null")
    record.encrypted_value = fernet.encrypt(value.encode()) if value else None
    db.add(record)
    if commit:
        db.commit()
    else:
        db.flush()
