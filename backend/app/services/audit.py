from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from ..models import SystemAuditEvent, User


def json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return "[binary data omitted]"
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    if hasattr(value, "__table__"):
        return model_snapshot(value)
    return value


def model_snapshot(item: Any) -> dict:
    if item is None:
        return {}
    return {
        column.key: json_value(getattr(item, column.key))
        for column in sqlalchemy_inspect(item).mapper.column_attrs
        if column.key not in {"password_hash", "encrypted_value", "recovery_email"}
    }


def add_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    summary: str,
    before: Any = None,
    after: Any = None,
    *,
    commit: bool = False,
) -> SystemAuditEvent:
    event = SystemAuditEvent(
        id=str(uuid.uuid4()),
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        summary=summary[:500],
        before_json=json.dumps(json_value(before or {}), ensure_ascii=False, sort_keys=True),
        after_json=json.dumps(json_value(after or {}), ensure_ascii=False, sort_keys=True),
        actor_user_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else "EduScan scheduler",
        actor_role=actor.role if actor else "system",
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event
