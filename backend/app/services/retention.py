from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import BASE_DIR, BIOMETRIC_DIR, MODEL_DIR
from ..models import BiometricSample, LegalHold, Person, RecognitionReview, RetentionExecution, SmsOutbox, User
from ..storage_quota import LOCK_NAME
from .audit import add_audit
from .settings_store import get_json


DEFAULT_POLICY = {
    "sms_days": 90,
    "recognition_review_days": 30,
    "biometric_staging_days": 30,
    "operational_log_days": 30,
    "enabled": False,
    "approved_schedule_reference": "",
}


def retention_policy(db: Session) -> dict:
    return {**DEFAULT_POLICY, **get_json(db, "retention", {})}


def active_holds(db: Session) -> list[LegalHold]:
    return db.scalars(select(LegalHold).where(LegalHold.active.is_(True))).all()


def _scope_held(holds: list[LegalHold], scope: str) -> bool:
    return any(item.scope in {"All", scope} for item in holds)


def _person_held(holds: list[LegalHold], person: Person | None) -> bool:
    if not person:
        return False
    references = {str(person.id), person.external_id, person.lrn or ""}
    return any(item.scope == "Person" and (item.subject_reference or "") in references for item in holds)


def _expired_files(root: Path, cutoff: datetime, referenced: set[Path] | None = None,
                   name_prefix: str | None = None) -> list[Path]:
    result = []
    for path in root.rglob("*") if root.exists() else []:
        if path.name == LOCK_NAME or not path.is_file() or (name_prefix and not path.name.startswith(name_prefix)):
            continue
        if referenced and path.resolve() in referenced:
            continue
        if datetime.utcfromtimestamp(path.stat().st_mtime) < cutoff:
            result.append(path)
    return result


def retention_preview(db: Session, now: datetime | None = None) -> dict:
    current = now or datetime.utcnow()
    policy = retention_policy(db)
    holds = active_holds(db)
    sms_cutoff = current - timedelta(days=int(policy["sms_days"]))
    review_cutoff = current - timedelta(days=int(policy["recognition_review_days"]))
    sms_items = db.scalars(select(SmsOutbox).where(SmsOutbox.created_at < sms_cutoff)).all()
    if _scope_held(holds, "SMS"):
        sms_items = []
    else:
        sms_items = [item for item in sms_items if not _person_held(holds, item.person)]
    reviews = [] if _scope_held(holds, "Recognition Review") else db.scalars(
        select(RecognitionReview).where(RecognitionReview.last_seen_at < review_cutoff)
    ).all()
    sample_paths = {Path(item.encrypted_path).resolve() for item in db.scalars(select(BiometricSample)).all()}
    staging_cutoff = current - timedelta(days=int(policy["biometric_staging_days"]))
    staging_files = [] if _scope_held(holds, "All") else (
        _expired_files(BIOMETRIC_DIR, staging_cutoff, sample_paths) +
        _expired_files(MODEL_DIR, staging_cutoff, name_prefix="load-")
    )
    logs_dir = BASE_DIR.parent / "logs"
    log_cutoff = current - timedelta(days=int(policy["operational_log_days"]))
    log_files = [] if _scope_held(holds, "Operational Logs") else _expired_files(logs_dir, log_cutoff)
    return {
        "policy": policy,
        "active_hold_count": len(holds),
        "eligible": {
            "sms_records": len(sms_items), "recognition_reviews": len(reviews),
            "biometric_staging_files": len(staging_files), "operational_log_files": len(log_files),
        },
        "cutoffs": {"sms": sms_cutoff.isoformat(), "recognition_reviews": review_cutoff.isoformat(),
                    "biometric_staging": staging_cutoff.isoformat(), "operational_logs": log_cutoff.isoformat()},
        "_sms_ids": [item.id for item in sms_items],
        "_review_ids": [item.id for item in reviews],
        "_staging_files": [str(item) for item in staging_files],
        "_log_files": [str(item) for item in log_files],
    }


def public_preview(preview: dict) -> dict:
    result = {key: value for key, value in preview.items() if not key.startswith("_")}
    result["total"] = sum(int(value) for value in result.get("eligible", {}).values())
    return result


def execute_retention(db: Session, authorization_reference: str, actor: User | None = None) -> RetentionExecution:
    preview = retention_preview(db)
    policy = preview["policy"]
    if not policy.get("enabled"):
        raise HTTPException(status_code=409, detail="Retention execution is disabled in the approved policy")
    if not str(policy.get("approved_schedule_reference") or "").strip():
        raise HTTPException(status_code=409, detail="Record the approved records-disposition schedule before execution")
    counts = {"sms_records": 0, "recognition_reviews": 0, "biometric_staging_files": 0, "operational_log_files": 0}
    if preview["_sms_ids"]:
        result = db.execute(delete(SmsOutbox).where(SmsOutbox.id.in_(preview["_sms_ids"])))
        counts["sms_records"] = result.rowcount or 0
    if preview["_review_ids"]:
        result = db.execute(delete(RecognitionReview).where(RecognitionReview.id.in_(preview["_review_ids"])))
        counts["recognition_reviews"] = result.rowcount or 0
    for key, paths in (("biometric_staging_files", preview["_staging_files"]),
                       ("operational_log_files", preview["_log_files"])):
        for raw_path in paths:
            try:
                Path(raw_path).unlink(missing_ok=True)
                counts[key] += 1
            except OSError:
                continue
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    record = RetentionExecution(
        id=str(uuid.uuid4()), policy_snapshot_json=json.dumps(policy, sort_keys=True),
        preview_json=json.dumps(public_preview(preview), sort_keys=True), removed_counts_json=json.dumps(counts, sort_keys=True),
        authorization_reference=authorization_reference.strip(),
        certificate_reference=f"EDUSCAN-DISPOSAL-{stamp}-{uuid.uuid4().hex[:6].upper()}",
        actor_user_id=actor.id if actor else None, actor_name=actor.full_name if actor else "EduScan scheduler",
    )
    db.add(record)
    add_audit(db, actor, "Execute", "RetentionPolicy", record.id,
              f"Retention execution {record.certificate_reference}", public_preview(preview), counts)
    db.commit()
    db.refresh(record)
    return record
