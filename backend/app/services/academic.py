"""Recoverable removal of academic setup; foreign-key history stays intact."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GradeLevel, GradingPeriod, SchoolSection, SchoolYear, Subject, User
from .audit import add_audit, model_snapshot


RECOVERABLE_REFERENCES = {
    "school-years": SchoolYear,
    "grading-periods": GradingPeriod,
    "grade-levels": GradeLevel,
    "sections": SchoolSection,
    "subjects": Subject,
}


def change_deleted_reference(db: Session, kind: str, record_id: int, actor: User, *, restore: bool = False) -> dict:
    model = RECOVERABLE_REFERENCES.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="Reference type was not found")
    item = db.scalar(select(model).where(model.id == record_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Reference record was not found")
    if restore and isinstance(item, SchoolSection) and item.grade_level.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Restore this section's grade level first")
    if restore and isinstance(item, GradingPeriod) and item.school_year.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Restore this grading period's school year first")
    if (item.deleted_at is None) != restore:
        before = model_snapshot(item)
        item.deleted_at = None if restore else datetime.utcnow()
        action = "Restore" if restore else "Delete"
        add_audit(db, actor, action, model.__name__, item.id,
                  f"{model.__name__} {'restored' if restore else 'removed from academic setup; linked records preserved'}",
                  before, model_snapshot(item))
        db.commit()
    return {"id": item.id, "restored" if restore else "deleted": True, "records_preserved": True}


def deleted_references(db: Session) -> list[dict]:
    result = []
    for kind, model in RECOVERABLE_REFERENCES.items():
        for item in db.scalars(select(model).where(model.deleted_at.is_not(None)).order_by(model.name)):
            parent_deleted = ((isinstance(item, SchoolSection) and item.grade_level.deleted_at is not None)
                              or (isinstance(item, GradingPeriod) and item.school_year.deleted_at is not None))
            restore_hint = ("Restore school year first." if isinstance(item, GradingPeriod) else "Restore grade level first.") if parent_deleted else ""
            result.append({
                "kind": kind, "id": item.id, "name": item.name,
                "grade": item.grade_level.name if isinstance(item, SchoolSection) else None,
                "deleted_at": item.deleted_at, "can_restore": not parent_deleted,
                "restore_hint": restore_hint,
            })
    return result
