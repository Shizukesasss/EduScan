from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import nullcontext

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (AttendanceCorrection, AttendanceEvent, BiometricAuditEvent, BiometricSample,
                      ExcusedAbsence, GradeChangeAudit, GradeScore, Intervention, Person,
                      RecordDisposalAudit, SmsOutbox, User)
from .biometrics import biometric_service


def dispose_person_records(db: Session, person: Person, actor: User, reason: str,
                           authorization_reference: str, confirmation: str) -> dict:
    if confirmation != person.external_id:
        raise HTTPException(status_code=422, detail="Confirmation must exactly match the school/employee ID")
    if len(reason.strip()) < 12 or len(authorization_reference.strip()) < 5:
        raise HTTPException(status_code=422, detail="A detailed reason and disposal authorization reference are required")
    has_samples = db.scalar(select(BiometricSample.id).where(BiometricSample.person_id == person.id).limit(1))
    enrollment = biometric_service.deleting_enrollment(
        db, person, actor, f"Full record disposal: {reason.strip()}"
    ) if has_samples else nullcontext()
    try:
        with enrollment:
            counts = {
                "attendance_events": db.query(AttendanceEvent).filter_by(person_id=person.id).count(),
                "attendance_corrections": db.query(AttendanceCorrection).filter_by(person_id=person.id).count(),
                "excused_absences": db.query(ExcusedAbsence).filter_by(person_id=person.id).count(),
                "grade_scores": db.query(GradeScore).filter_by(person_id=person.id).count(),
                "sms_records": db.query(SmsOutbox).filter_by(person_id=person.id).count(),
                "interventions": db.query(Intervention).filter_by(person_id=person.id).count(),
                "biometric_audits": db.query(BiometricAuditEvent).filter_by(person_id=person.id).count(),
            }
            db.execute(delete(AttendanceEvent).where(AttendanceEvent.person_id == person.id))
            db.execute(delete(AttendanceCorrection).where(AttendanceCorrection.person_id == person.id))
            db.execute(delete(ExcusedAbsence).where(ExcusedAbsence.person_id == person.id))
            db.execute(delete(GradeScore).where(GradeScore.person_id == person.id))
            db.execute(delete(SmsOutbox).where(SmsOutbox.person_id == person.id))
            db.execute(delete(Intervention).where(Intervention.person_id == person.id))
            db.execute(delete(BiometricAuditEvent).where(BiometricAuditEvent.person_id == person.id))
            from ..models import RecognitionReview
            from ..models_grading import StudentScore, GradeAdjustmentRequest, GradebookAuditEntry
            db.execute(delete(RecognitionReview).where(RecognitionReview.candidate_person_id == person.id))
            db.execute(delete(StudentScore).where(StudentScore.person_id == person.id))
            db.execute(delete(GradeAdjustmentRequest).where(GradeAdjustmentRequest.person_id == person.id))
            db.execute(delete(GradebookAuditEntry).where(GradebookAuditEntry.person_id == person.id))
            for audit in db.scalars(select(GradeChangeAudit)).all():
                before = json.loads(audit.before_json)
                after = json.loads(audit.after_json)
                if str(person.id) in before.get("scores", {}) or str(person.id) in after.get("scores", {}):
                    db.delete(audit)
            reference_hash = hashlib.sha256(f"{person.id}:{person.external_id}".encode()).hexdigest()
            db.delete(person)
            db.flush()
            db.add(RecordDisposalAudit(id=str(uuid.uuid4()), subject_reference_hash=reference_hash,
                                       reason=reason.strip(), authorization_reference=authorization_reference.strip(),
                                       removed_counts_json=json.dumps({**counts, "person_record": 1}),
                                       actor_user_id=actor.id, actor_name=actor.full_name, actor_role=actor.role))
            db.commit()
            return {"disposed": True, "removed_counts": {**counts, "person_record": 1},
                    "disposal_reference": reference_hash[:12]}
    except Exception:
        db.rollback()
        raise
