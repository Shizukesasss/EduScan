from __future__ import annotations

import hashlib
import csv
import io
import json
import math
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .auth import create_token, current_user, hash_password, require_roles, seed_users, verify_password
from .config import settings
from .database import SessionLocal, engine, get_db
from .migrations import run_migrations
from .models import (
    AttendanceCorrection, AttendanceEvent, AttendanceResetAudit, BiometricAuditEvent, BiometricModel, BiometricSample, CalendarException,
    BackupRun, ClassSchedule, ExcusedAbsence, GeneratedReport, GradeChangeAudit, GradeComponent, GradebookState,
    GradeLevel, GradeScore, GradingPeriod, Intervention, LegalHold, Person, PersonnelSchedule, RecognitionReview,
    RecordDisposalAudit, RetentionExecution, RosterImportAudit, SchoolSection, SchoolYear, SmsOutbox,
    Subject, SystemAuditEvent, User,
)
from .schemas import (
    AttendanceCorrectionPayload, AttendanceResetPayload, AttendanceSettingsPayload, BiometricChangeReason, CalendarExceptionPayload,
    BackupSchedulePayload, BiometricRuntimeSettingsPayload, CompliancePayload, ExcusedAbsencePayload,
    GradebookActionPayload, GradebookPayload, GradeLevelPayload, GradingPeriodPayload, LegalHoldPayload,
    LegalHoldReleasePayload, RecognitionReviewResolutionPayload, ReportReviewPayload, RetentionExecutionPayload,
    RetentionPolicyPayload,
    InterventionPayload, LoginRequest, LoginResponse, PasswordChangePayload, PersonCreate, PersonnelSchedulePayload, RecognitionResult,
    RecordDisposalPayload, SchedulePayload, SchoolYearPayload, SectionPayload, SmsSettingsPayload, SubjectPayload,
    UserCreate, UserUpdate,
)
from .services.attendance import close_day, latest_day_reset, list_rows, record_gate_match, reset_day, save_correction
from .services.audit import add_audit, model_snapshot
from .services.backup import BACKUP_DIR, database_backend, run_managed_backup, stage_secure_restore
from .services.biometrics import biometric_service
from .services.disposal import dispose_person_records
from .services.roster import import_roster
from .services.scheduler import attendance_scheduler
from .services import grading as grading_service
from .services.grading import gradebook_summary
from .models_grading import (
    AssessmentItem, GradeAdjustmentRequest, Gradebook, GradebookAuditEntry,
    GradebookComponent, GradingPolicy, StudentScore,
)
from .schemas_grading import (
    GradeAdjustmentCreate, GradeAdjustmentReview, GradebookComponentsUpdate,
    GradebookCreate, GradebookScoresUpdate, GradebookWorkflowPayload,
    GradingPolicyCreate, GradingPolicyUpdate,
)
from .services.reports import (
    attendance_report_html, generate_attendance_range_xlsx, generate_grade_report_xlsx,
    grade_report_html, register_report, generate_gradebook_report_xlsx, gradebook_report_html
)
from .services.retention import execute_retention, public_preview, retention_policy, retention_preview
from .services.settings_store import get_json, get_secret, set_json, set_secret
from .services.sf2 import generate_sf2, generate_temporary_log, save_template, template_path
from .services.sms import (
    cancel_record, dispatch_outbox, dispatch_queued, dispatch_record_by_id, gateway_diagnostics,
    mask_phone, reconcile_outbox, requeue_record, send_record, sms_config,
)


app = FastAPI(title="EduScan API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    run_migrations(engine)
    with SessionLocal() as db:
        seed_users(db)
        biometric_service.purge_obsolete_models(db)
        seed_reference_data(db)
    if settings.attendance_scheduler_enabled:
        attendance_scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if settings.attendance_scheduler_enabled:
        attendance_scheduler.stop()


def seed_reference_data(db: Session) -> None:
    today = date.today()
    start_year = today.year if today.month >= 6 else today.year - 1
    school_year_name = f"{start_year}-{start_year + 1}"
    school_year = db.scalar(select(SchoolYear).where(
        SchoolYear.name == school_year_name))
    if not school_year:
        school_year = SchoolYear(name=school_year_name, starts_on=date(start_year, 6, 1),
                                 ends_on=date(start_year + 1, 3, 31), active=True)
        db.add(school_year)
        db.flush()
        quarter_starts = (date(start_year, 6, 1), date(start_year, 8, 16), date(
            start_year, 10, 16), date(start_year + 1, 1, 2))
        quarter_ends = (date(start_year, 8, 15), date(start_year, 10, 15), date(
            start_year, 12, 20), date(start_year + 1, 3, 31))
        for quarter in range(1, 5):
            db.add(GradingPeriod(school_year_id=school_year.id, name=f"Quarter {quarter}", quarter=quarter,
                                 starts_on=quarter_starts[quarter - 1], ends_on=quarter_ends[quarter - 1], active=True))
    grade = db.scalar(select(GradeLevel).where(GradeLevel.name == "10"))
    if not grade:
        grade = GradeLevel(name="10", sequence=10, active=True)
        db.add(grade)
        db.flush()
    if not db.scalar(select(SchoolSection).where(SchoolSection.grade_level_id == grade.id, SchoolSection.name == "Rizal")):
        db.add(SchoolSection(grade_level_id=grade.id, name="Rizal", active=True))
    if not db.scalar(select(Subject).where(Subject.code == "MATH")):
        db.add(Subject(code="MATH", name="Mathematics", active=True))
    db.commit()


def person_json(person: Person, db: Session, include_private: bool = True) -> dict:
    count = db.scalar(select(func.count(BiometricSample.id)).where(
        BiometricSample.person_id == person.id)) or 0
    return {
        "id": person.id, "external_id": person.external_id, "lrn": person.lrn, "full_name": person.full_name,
        "sex": person.sex, "role": person.role, "grade": person.grade, "section": person.section,
        "assignment": person.assignment, "guardian_phone": person.guardian_phone if include_private else None,
        "enrollment_status": person.enrollment_status, "enrollment_start_date": person.enrollment_start_date,
        "enrollment_end_date": person.enrollment_end_date, "transfer_school": person.transfer_school,
        "biometric_consent": person.biometric_consent, "active": person.active,
        "sample_count": count, "enrolled": count >= settings.min_samples,
    }


def correction_json(item: AttendanceCorrection) -> dict:
    return {
        "id": item.id, "person_id": item.person_id, "person_name": item.person.full_name,
        "attendance_date": item.attendance_date, "status": item.status, "time_in": item.time_in,
        "time_out": item.time_out, "reason": item.reason, "actor_name": item.actor_name,
        "actor_role": item.actor_role, "before": json.loads(item.before_json), "created_at": item.created_at,
    }


def reset_json(item: AttendanceResetAudit) -> dict:
    return {
        "id": item.id, "attendance_date": item.attendance_date, "reason": item.reason,
        "actor_name": item.actor_name, "actor_role": item.actor_role,
        "superseded_event_count": item.superseded_event_count,
        "superseded_correction_count": item.superseded_correction_count, "created_at": item.created_at,
    }


def adviser_sections(db: Session, user: User) -> list[SchoolSection]:
    if user.role in {"admin", "records_officer"}:
        return db.scalars(select(SchoolSection).where(SchoolSection.active.is_(True))).all()
    return [item for item in db.scalars(select(SchoolSection).where(SchoolSection.active.is_(True))).all()
            if item.adviser_user_id == user.id or (
                item.adviser_user_id is None and (item.adviser_name or "").strip(
                ).casefold() == user.full_name.strip().casefold()
    )]


def ensure_adviser_access(db: Session, user: User, grade: str, section: str) -> None:
    if user.role in {"admin", "records_officer"}:
        return
    allowed = {(item.grade_level.name, item.name)
               for item in adviser_sections(db, user)}
    if (grade, section) not in allowed:
        raise HTTPException(
            status_code=403, detail="This section is not assigned to the signed-in adviser")


def biometric_enrollment_json(person: Person, db: Session, include_samples: bool = False) -> dict:
    snapshot = biometric_service.enrollment_snapshot(db, person)
    result = {
        "person_id": person.id, "external_id": person.external_id, "full_name": person.full_name,
        "role": person.role, "grade": person.grade, "section": person.section,
        "assignment": person.assignment, "biometric_consent": person.biometric_consent,
        **snapshot,
    }
    if include_samples:
        samples = db.scalars(
            select(BiometricSample).where(
                BiometricSample.person_id == person.id)
            .order_by(BiometricSample.created_at, BiometricSample.id)
        ).all()
        result["samples"] = [{"id": item.id, "quality_score": item.quality_score,
                              "created_at": item.created_at} for item in samples]
    return result


def biometric_audit_json(item: BiometricAuditEvent) -> dict:
    return {
        "id": item.id, "person_id": item.person_id, "external_id": item.person_external_id,
        "person_name": item.person_name, "action": item.action, "reason": item.reason,
        "actor_name": item.actor_name, "actor_role": item.actor_role,
        "before": json.loads(item.before_json), "after": json.loads(item.after_json),
        "model_version": item.model_version, "created_at": item.created_at,
    }


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    active_model = db.scalar(select(BiometricModel).where(
        BiometricModel.active.is_(True)).order_by(BiometricModel.id.desc()))
    return {
        "ok": True,
        "database": engine.url.get_backend_name(),
        "biometric_enabled": settings.biometric_enabled,
        "active_model": active_model.version if active_model else None,
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(func.lower(
        User.username) == payload.username.strip().lower()))
    now = datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        remaining = max(
            1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=423, detail=f"Account temporarily locked; try again in {remaining} minute(s)")
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        if user and user.active:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(
            status_code=401, detail="Invalid username or password")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    return LoginResponse(access_token=create_token(user), role=user.role, full_name=user.full_name,
                         must_change_password=user.must_change_password)


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "full_name": user.full_name,
            "must_change_password": user.must_change_password, "password_changed_at": user.password_changed_at}


@app.post("/api/auth/change-password")
def change_password(payload: PasswordChangePayload, db: Session = Depends(get_db),
                    user: User = Depends(current_user)) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=422, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=422, detail="New password must be different")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    add_audit(db, user, "PasswordChange", "User", user.id,
              "Account owner changed their password", {}, {"must_change_password": False})
    db.commit()
    return {"changed": True, "role": user.role, "full_name": user.full_name,
            "must_change_password": False}


@app.get("/api/admin/users")
def admin_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> list[dict]:
    return [{"id": item.id, "username": item.username, "role": item.role, "full_name": item.full_name,
             "active": item.active, "must_change_password": item.must_change_password,
             "locked_until": item.locked_until, "last_login_at": item.last_login_at,
             "created_at": item.created_at}
            for item in db.scalars(select(User).order_by(User.full_name)).all()]


@app.post("/api/admin/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles("admin"))) -> dict:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(
            status_code=409, detail="Username is already in use")
    item = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role,
                full_name=payload.full_name, active=payload.active, must_change_password=True,
                failed_login_count=0)
    db.add(item)
    db.flush()
    add_audit(db, actor, "Create", "User", item.id,
              f"Account {item.username} created", {}, model_snapshot(item))
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                actor: User = Depends(require_roles("admin"))) -> dict:
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Account was not found")
    if payload.role not in {"admin", "teacher", "scanner", "records_officer", "privacy_officer", "ict"}:
        raise HTTPException(status_code=422, detail="Unsupported account role")
    if item.id == actor.id and (not payload.active or payload.role != "admin"):
        raise HTTPException(
            status_code=422, detail="You cannot remove your own active administrator access")
    before = model_snapshot(item)
    item.role, item.full_name, item.active = payload.role, payload.full_name, payload.active
    if payload.new_password:
        item.password_hash = hash_password(payload.new_password)
        item.must_change_password = True
        item.password_changed_at = None
        item.failed_login_count = 0
        item.locked_until = None
    add_audit(db, actor, "Update", "User", item.id,
              f"Account {item.username} updated", before, model_snapshot(item))
    db.commit()
    return {"saved": True}


@app.delete("/api/admin/users/{user_id}")
def deactivate_user(user_id: int, db: Session = Depends(get_db),
                    actor: User = Depends(require_roles("admin"))) -> dict:
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Account was not found")
    if item.id == actor.id:
        raise HTTPException(
            status_code=422, detail="You cannot deactivate your own account")
    before = model_snapshot(item)
    item.active = False
    add_audit(db, actor, "Deactivate", "User", item.id,
              f"Account {item.username} deactivated", before, model_snapshot(item))
    db.commit()
    return {"deactivated": True}


@app.post("/api/admin/users/{user_id}/unlock")
def unlock_user(user_id: int, db: Session = Depends(get_db),
                actor: User = Depends(require_roles("admin"))) -> dict:
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Account was not found")
    before = model_snapshot(item)
    item.failed_login_count = 0
    item.locked_until = None
    add_audit(db, actor, "Unlock", "User", item.id,
              f"Account {item.username} unlocked", before, model_snapshot(item))
    db.commit()
    return {"unlocked": True}


@app.get("/api/persons")
def persons(role: str | None = None, grade: str | None = None, section: str | None = None,
            db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> list[dict]:
    query = select(Person).where(
        Person.active.is_(True)).order_by(Person.full_name)
    if role:
        query = query.where(Person.role == role)
    if grade:
        query = query.where(Person.grade == grade)
    if section:
        query = query.where(Person.section == section)
    items = db.scalars(query).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        items = [item for item in items if item.role ==
                 "Student" and (item.grade, item.section) in allowed]
    return [person_json(item, db) for item in items]


@app.post("/api/persons")
def create_person(payload: PersonCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    if db.scalar(select(Person).where(Person.external_id == payload.external_id)):
        raise HTTPException(
            status_code=409, detail="External ID is already registered")
    if payload.lrn and db.scalar(select(Person).where(Person.lrn == payload.lrn)):
        raise HTTPException(
            status_code=409, detail="LRN is already registered")
    if payload.role == "Student" and (not payload.grade or not payload.section):
        raise HTTPException(
            status_code=422, detail="Student grade and section are required")
    person = Person(**payload.model_dump())
    db.add(person)
    db.flush()
    add_audit(db, actor, "Create", "Person", person.id,
              f"School record created for {person.full_name}", {}, model_snapshot(person))
    db.commit()
    db.refresh(person)
    return person_json(person, db)


@app.patch("/api/persons/{person_id}")
def update_person(person_id: int, payload: PersonCreate, db: Session = Depends(get_db),
                  actor: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    duplicate_id = db.scalar(select(Person).where(
        Person.external_id == payload.external_id, Person.id != person_id))
    duplicate_lrn = db.scalar(select(Person).where(
        Person.lrn == payload.lrn, Person.id != person_id)) if payload.lrn else None
    if duplicate_id:
        raise HTTPException(
            status_code=409, detail="External ID is already registered")
    if duplicate_lrn:
        raise HTTPException(
            status_code=409, detail="LRN is already registered")
    before = model_snapshot(person)
    for key, value in payload.model_dump().items():
        setattr(person, key, value)
    add_audit(db, actor, "Update", "Person", person.id,
              f"School record updated for {person.full_name}", before, model_snapshot(person))
    db.commit()
    return person_json(person, db)


@app.get("/api/admin/persons")
def admin_persons(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> list[dict]:
    people = db.scalars(select(Person).order_by(
        Person.active.desc(), Person.full_name, Person.external_id)).all()
    name_counts: dict[str, int] = {}
    for person in people:
        if person.active and person.role == "Student":
            key = re.sub(r"[^a-z0-9]", "", person.full_name.casefold())
            name_counts[key] = name_counts.get(key, 0) + 1
    result = []
    for person in people:
        item = person_json(person, db)
        key = re.sub(r"[^a-z0-9]", "", person.full_name.casefold())
        item["possible_duplicate"] = person.active and person.role == "Student" and name_counts.get(
            key, 0) > 1
        result.append(item)
    return result


@app.get("/api/my/advisory-sections")
def my_advisory_sections(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> list[dict]:
    return [{"id": item.id, "grade": item.grade_level.name, "section": item.name,
             "adviser_name": item.adviser_name} for item in adviser_sections(db, user)]


@app.post("/api/admin/persons/{person_id}/active")
def set_person_active(person_id: int, active: bool = Form(...), db: Session = Depends(get_db),
                      actor: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    before = model_snapshot(person)
    person.active = active
    add_audit(db, actor, "Activate" if active else "Deactivate", "Person", person.id,
              f"School record {'activated' if active else 'deactivated'} for {person.full_name}", before, model_snapshot(person))
    db.commit()
    return person_json(person, db)


@app.delete("/api/admin/persons/{person_id}/records")
def dispose_person(person_id: int, payload: RecordDisposalPayload, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    return dispose_person_records(db, person, user, payload.reason, payload.authorization_reference, payload.confirmation)


@app.get("/api/admin/disposals")
def disposal_audits(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> list[dict]:
    items = db.scalars(select(RecordDisposalAudit).order_by(
        RecordDisposalAudit.created_at.desc()).limit(500)).all()
    return [{"id": item.id, "disposal_reference": item.subject_reference_hash[:12], "reason": item.reason,
             "authorization_reference": item.authorization_reference, "removed_counts": json.loads(item.removed_counts_json),
             "actor_name": item.actor_name, "actor_role": item.actor_role, "created_at": item.created_at} for item in items]


@app.post("/api/admin/roster/import")
async def roster_import(file: UploadFile = File(...), approved_reference: str = Form(...),
                        dry_run: bool = Form(True), db: Session = Depends(get_db),
                        user: User = Depends(require_roles("admin"))) -> dict:
    filename = file.filename or "roster.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422, detail="Upload an approved .xlsx roster workbook")
    return import_roster(db, await file.read(), filename, approved_reference, user, dry_run)


@app.get("/api/admin/roster/imports")
def roster_imports(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> list[dict]:
    items = db.scalars(select(RosterImportAudit).order_by(
        RosterImportAudit.created_at.desc()).limit(200)).all()
    return [{"id": item.id, "filename": item.filename, "file_sha256": item.file_sha256,
             "approved_reference": item.approved_reference, "inserted_count": item.inserted_count,
             "updated_count": item.updated_count, "skipped_count": item.skipped_count,
             "actor_name": item.actor_name, "created_at": item.created_at} for item in items]


@app.get("/api/admin/backups")
def list_backups(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "ict"))) -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    runs = db.scalars(select(BackupRun).where(
        BackupRun.status == "Completed", BackupRun.filename.is_not(None),
    ).order_by(BackupRun.created_at.desc()).limit(500)).all()
    result = [{"id": item.id, "trigger": item.trigger, "status": item.status,
               "filename": item.filename, "size_bytes": item.size_bytes, "sha256": item.file_sha256,
               "database_backend": item.database_backend,
               "encryption_key_fingerprint": item.encryption_key_fingerprint,
               "model_version": item.model_version, "destination": item.destination,
               "error": item.error, "actor_name": item.actor_name, "created_at": item.created_at}
              for item in runs]
    registered = {item.filename for item in runs}
    for path in sorted(BACKUP_DIR.glob("*.edubak"), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.name not in registered:
            result.append({"id": f"legacy:{path.name}", "trigger": "Legacy", "status": "Completed",
                           "filename": path.name, "size_bytes": path.stat().st_size, "sha256": None,
                           "database_backend": "unknown", "encryption_key_fingerprint": "unknown",
                           "model_version": None, "destination": str(path), "error": None,
                           "actor_name": "Pre-inventory backup", "created_at": datetime.fromtimestamp(path.stat().st_mtime)})
    return sorted(result, key=lambda item: item["created_at"], reverse=True)


@app.get("/api/admin/backup-runs")
def backup_run_inventory(db: Session = Depends(get_db),
                         _: User = Depends(require_roles("admin", "ict"))) -> list[dict]:
    runs = db.scalars(select(BackupRun).order_by(
        BackupRun.created_at.desc()).limit(1000)).all()
    return [{"id": item.id, "trigger": item.trigger, "status": item.status,
             "filename": item.filename, "size_bytes": item.size_bytes, "sha256": item.file_sha256,
             "database_backend": item.database_backend,
             "encryption_key_fingerprint": item.encryption_key_fingerprint,
             "model_version": item.model_version, "destination": item.destination,
             "error": item.error, "actor_name": item.actor_name, "created_at": item.created_at}
            for item in runs]


@app.post("/api/admin/backups")
def create_backup(passphrase: str = Form(...), destination: str = Form(""), db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "ict"))) -> dict:
    run = run_managed_backup(db, passphrase, "Manual", user, destination)
    add_audit(db, user, "Backup", "BackupRun", run.id, f"Manual backup {run.status.lower()}", {},
              model_snapshot(run), commit=True)
    if run.status == "Failed":
        raise HTTPException(
            status_code=500, detail=run.error or "Backup failed")
    return {"created": True, "run_id": run.id, "filename": run.filename,
            "size_bytes": run.size_bytes, "sha256": run.file_sha256,
            "database_backend": run.database_backend, "destination": run.destination}


@app.get("/api/admin/backups/{filename}")
def download_backup(filename: str, _: User = Depends(require_roles("admin", "ict"))):
    if Path(filename).name != filename or not filename.endswith(".edubak"):
        raise HTTPException(status_code=404, detail="Backup was not found")
    path = BACKUP_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup was not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@app.post("/api/admin/backups/restore")
async def restore_backup(file: UploadFile = File(...), passphrase: str = Form(...),
                         confirmation: str = Form(...), db: Session = Depends(get_db),
                         user: User = Depends(require_roles("admin", "ict"))) -> dict:
    if confirmation != "STAGE RESTORE":
        raise HTTPException(
            status_code=422, detail="Type STAGE RESTORE to confirm recovery staging")
    if not (file.filename or "").lower().endswith(".edubak"):
        raise HTTPException(
            status_code=422, detail="Upload an EduScan .edubak file")
    data = await file.read(251 * 1024 * 1024)
    if len(data) > 250 * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail="Backup exceeds the 250 MB recovery limit")
    result = stage_secure_restore(data, passphrase)
    add_audit(db, user, "Stage Restore", "BackupRestore", file.filename,
              "Integrity-checked restore package staged for controlled application", {}, result, commit=True)
    return result


@app.get("/api/admin/backup-schedule")
def backup_schedule(db: Session = Depends(get_db),
                    _: User = Depends(require_roles("admin", "ict"))) -> dict:
    value = get_json(db, "backup.schedule", {"enabled": False, "frequency": "Daily", "run_time": "18:00:00",
                                             "retention_count": 14, "destination": ""})
    return {**value, "passphrase_configured": bool(get_secret(db, "backup.schedule.passphrase", ""))}


@app.put("/api/admin/backup-schedule")
def save_backup_schedule(payload: BackupSchedulePayload, db: Session = Depends(get_db),
                         user: User = Depends(require_roles("admin", "ict"))) -> dict:
    before = get_json(db, "backup.schedule", {})
    if payload.enabled and not (payload.passphrase or get_secret(db, "backup.schedule.passphrase", "")):
        raise HTTPException(
            status_code=422, detail="A backup passphrase is required before scheduling backups")
    value = {"enabled": payload.enabled, "frequency": payload.frequency,
             "run_time": payload.run_time.isoformat(), "retention_count": payload.retention_count,
             "destination": payload.destination.strip()}
    set_json(db, "backup.schedule", value, commit=False)
    if payload.passphrase:
        set_secret(db, "backup.schedule.passphrase", payload.passphrase)
    add_audit(db, user, "Update", "BackupSchedule", "backup.schedule",
              "Encrypted backup schedule updated", before, value, commit=True)
    return {**value, "passphrase_configured": bool(get_secret(db, "backup.schedule.passphrase", ""))}


@app.post("/api/biometrics/enroll/{person_id}")
async def enroll(person_id: int, frames: list[UploadFile] = File(...),
                 reason: str = Form("Initial facial enrollment"), db: Session = Depends(get_db),
                 user: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    if len(frames) > 40:
        raise HTTPException(
            status_code=422, detail="Enrollment accepts at most 40 frames")
    contents = [await frame.read() for frame in frames]
    return biometric_service.enroll(db, person, contents, user, reason)


@app.get("/api/biometrics/enrollments")
def biometric_enrollments(db: Session = Depends(get_db),
                          _: User = Depends(require_roles("admin"))) -> list[dict]:
    people = db.scalars(
        select(Person).join(BiometricSample).group_by(
            Person.id).order_by(Person.full_name)
    ).all()
    return [biometric_enrollment_json(person, db) for person in people]


@app.get("/api/biometrics/enrollments/audit")
def biometric_audit(person_id: int | None = None, limit: int = Query(default=500, ge=1, le=2000),
                    db: Session = Depends(get_db),
                    _: User = Depends(require_roles("admin"))) -> list[dict]:
    query = select(BiometricAuditEvent)
    if person_id is not None:
        query = query.where(BiometricAuditEvent.person_id == person_id)
    query = query.order_by(BiometricAuditEvent.created_at.desc()).limit(limit)
    return [biometric_audit_json(item) for item in db.scalars(query).all()]


@app.get("/api/biometrics/enrollments/{person_id}")
def biometric_enrollment(person_id: int, db: Session = Depends(get_db),
                         _: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    result = biometric_enrollment_json(person, db, include_samples=True)
    if not result["sample_count"]:
        raise HTTPException(
            status_code=404, detail="This person does not have a facial enrollment")
    return result


@app.post("/api/biometrics/enrollments/{person_id}")
async def create_biometric_enrollment(person_id: int, frames: list[UploadFile] = File(...),
                                      reason: str = Form(
                                          "Initial facial enrollment"),
                                      db: Session = Depends(get_db),
                                      user: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    if len(frames) > 40:
        raise HTTPException(
            status_code=422, detail="Enrollment accepts at most 40 frames")
    return biometric_service.enroll(db, person, [await frame.read() for frame in frames], user, reason,
                                    require_existing=False)


@app.put("/api/biometrics/enrollments/{person_id}")
async def update_biometric_enrollment(person_id: int, frames: list[UploadFile] = File(...),
                                      reason: str = Form(...), db: Session = Depends(get_db),
                                      user: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    if len(frames) > 40:
        raise HTTPException(
            status_code=422, detail="Enrollment accepts at most 40 frames")
    return biometric_service.enroll(db, person, [await frame.read() for frame in frames], user, reason,
                                    require_existing=True)


@app.delete("/api/biometrics/enrollments/{person_id}")
def delete_biometric_enrollment(person_id: int, payload: BiometricChangeReason,
                                db: Session = Depends(get_db),
                                user: User = Depends(require_roles("admin"))) -> dict:
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    return biometric_service.delete_enrollment(db, person, user, payload.reason)


@app.post("/api/biometrics/train")
def train(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> dict:
    return biometric_service.train(db)


@app.get("/api/biometrics/status")
def biometric_status(db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    active = db.scalar(select(BiometricModel).where(
        BiometricModel.active.is_(True)).order_by(BiometricModel.id.desc()))
    runtime = biometric_service.runtime_config(db)
    return {
        "enabled": settings.biometric_enabled, "minimum_samples": settings.min_samples,
        **runtime,
        "model": None if not active else {"version": active.version, "person_count": active.person_count,
                                          "sample_count": active.sample_count, "created_at": active.created_at},
    }


@app.put("/api/biometrics/runtime-settings")
def save_biometric_runtime_settings(payload: BiometricRuntimeSettingsPayload, db: Session = Depends(get_db),
                                    user: User = Depends(require_roles("admin"))) -> dict:
    before = biometric_service.runtime_config(db)
    value = payload.model_dump()
    set_json(db, "biometric.runtime", value, commit=False)
    add_audit(db, user, "Update", "BiometricRuntimeSettings", "biometric.runtime",
              "Recognition threshold and liveness controls updated", before, value)
    db.commit()
    return value


@app.get("/api/biometrics/reviews")
def recognition_reviews(status: str | None = "Open", db: Session = Depends(get_db),
                        _: User = Depends(require_roles("admin", "records_officer", "privacy_officer"))) -> list[dict]:
    query = select(RecognitionReview)
    if status:
        query = query.where(RecognitionReview.status == status)
    items = db.scalars(query.order_by(
        RecognitionReview.last_seen_at.desc()).limit(1000)).all()
    return [{"id": item.id, "candidate_person_id": item.candidate_person_id,
             "candidate_name": item.candidate_name, "review_type": item.review_type,
             "reason": item.reason, "distance": item.distance, "quality_score": item.quality_score,
             "occurrence_count": item.occurrence_count, "status": item.status,
             "resolution_note": item.resolution_note, "resolved_by_name": item.resolved_by_name,
             "last_seen_at": item.last_seen_at, "created_at": item.created_at,
             "resolved_at": item.resolved_at} for item in items]


@app.post("/api/biometrics/reviews/{review_id}/resolve")
def resolve_recognition_review(review_id: str, payload: RecognitionReviewResolutionPayload,
                               db: Session = Depends(get_db),
                               user: User = Depends(require_roles("admin", "records_officer", "privacy_officer"))) -> dict:
    item = db.get(RecognitionReview, review_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Recognition review was not found")
    before = model_snapshot(item)
    item.status = payload.status
    item.resolution_note = payload.note.strip()
    item.resolved_by = user.id
    item.resolved_by_name = user.full_name
    item.resolved_at = datetime.utcnow()
    add_audit(db, user, "Resolve", "RecognitionReview", item.id,
              f"Recognition review marked {payload.status}", before, model_snapshot(item))
    db.commit()
    return {"id": item.id, "status": item.status}


@app.get("/api/station/health")
def station_health(db: Session = Depends(get_db),
                   _: User = Depends(require_roles("admin", "scanner", "records_officer", "privacy_officer", "ict"))) -> dict:
    database_ok = True
    try:
        db.execute(select(1))
    except Exception:
        database_ok = False
    active = db.scalar(select(BiometricModel).where(
        BiometricModel.active.is_(True)).order_by(BiometricModel.id.desc()))
    gateway = gateway_diagnostics(db)
    return {"api": True, "database": database_ok,
            "recognition_model": bool(active), "model_version": active.version if active else None,
            "gateway_enabled": gateway["enabled"], "gateway_reachable": gateway["reachable"],
            "checked_at": datetime.utcnow()}


@app.post("/api/biometrics/recognize", response_model=RecognitionResult)
async def recognize(background_tasks: BackgroundTasks, frame: UploadFile = File(...), db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "scanner"))) -> RecognitionResult:
    person, distance, quality = biometric_service.recognize(db, await frame.read())
    if person is None:
        return RecognitionResult(recognized=False, message="Face was not recognized with sufficient confidence",
                                 distance=round(distance, 2), quality_score=quality)
    event = record_gate_match(db, person, distance)
    if event.get("recorded"):
        generate_temporary_log(db, date.fromisoformat(event["date"]))
        if event.get("sms_id"):
            background_tasks.add_task(dispatch_record_by_id, event["sms_id"])
    return RecognitionResult(recognized=True, message=event["message"] if not event.get("recorded") else "Identity verified and attendance recorded",
                             person={
                                 "id": person.id, "full_name": person.full_name, "role": person.role},
                             distance=round(distance, 2), quality_score=quality,
                             attendance_event=event)


@app.post("/api/biometrics/recognize-many")
async def recognize_many(background_tasks: BackgroundTasks, frame: UploadFile = File(...),
                         db: Session = Depends(get_db),
                         user: User = Depends(require_roles("admin", "scanner"))) -> dict:
    matches = biometric_service.recognize_many(db, await frame.read())
    results = []
    for match in matches:
        person, distance, quality, box = match["person"], match["distance"], match["quality"], match["box"]
        if person is None:
            results.append({"recognized": False, "liveness_verified": False,
                            "message": match["message"], "review_id": match["review_id"],
                            "distance": round(distance, 2), "quality_score": quality, "box": box})
            continue
        if not match["liveness_verified"]:
            results.append({"recognized": True, "liveness_verified": False, "message": match["message"],
                            "review_id": match["review_id"],
                            "person": {"id": person.id, "full_name": person.full_name, "role": person.role},
                            "distance": round(distance, 2), "quality_score": quality,
                            "attendance_event": {"recorded": False}, "box": box})
            continue
        event = record_gate_match(db, person, distance)
        if event.get("recorded"):
            if event.get("sms_id"):
                background_tasks.add_task(
                    dispatch_record_by_id, event["sms_id"])
        results.append({"recognized": True, "liveness_verified": True,
                        "message": event["message"] if not event.get("recorded") else "Identity and liveness verified; attendance recorded",
                        "person": {"id": person.id, "full_name": person.full_name, "role": person.role},
                        "distance": round(distance, 2), "quality_score": quality,
                        "attendance_event": event, "box": box})
    if any(item.get("attendance_event", {}).get("recorded") for item in results):
        generate_temporary_log(db, date.today())
    return {"face_count": len(matches), "recognized_count": sum(item["recognized"] for item in results),
            "results": results}


@app.get("/api/attendance")
def attendance(day: date = Query(alias="date"), grade: str | None = None, section: str | None = None,
               db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> list[dict]:
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        if grade and section:
            ensure_adviser_access(db, user, grade, section)
            return list_rows(db, day, grade, section, students_only=True)
        return [row for row in list_rows(db, day, students_only=True) if (row["grade"], row["section"]) in allowed]
    return list_rows(db, day, grade, section, students_only=bool(grade or section))


@app.get("/api/gate/recent")
def gate_recent(day: date = Query(alias="date"), db: Session = Depends(get_db),
                _: User = Depends(require_roles("admin", "scanner"))) -> list[dict]:
    query = select(AttendanceEvent).where(
        AttendanceEvent.event_date == day, AttendanceEvent.direction.in_(
            ["Time In", "Time Out"]),
    )
    reset = latest_day_reset(db, day)
    if reset:
        query = query.where(AttendanceEvent.created_at > reset.created_at)
    events = db.scalars(query.order_by(
        AttendanceEvent.created_at.desc()).limit(30)).all()
    return [{"id": item.id, "name": item.person.full_name, "role": item.person.role,
             "direction": item.direction, "status": item.status, "time": item.event_time} for item in events]


@app.post("/api/attendance/close")
def attendance_close(background_tasks: BackgroundTasks, day: date = Query(alias="date"), grade: str | None = None,
                     section: str | None = None, db: Session = Depends(get_db),
                     user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Teachers must select their assigned grade and section")
        ensure_adviser_access(db, user, grade, section)
    created = close_day(db, day, grade, section)
    generate_temporary_log(db, day)
    background_tasks.add_task(dispatch_outbox)
    return {"created": created}


@app.get("/api/attendance/corrections")
def corrections(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher"))) -> list[dict]:
    items = db.scalars(select(AttendanceCorrection).order_by(
        AttendanceCorrection.created_at.desc()).limit(500)).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        items = [item for item in items if (
            item.person.grade, item.person.section) in allowed]
    return [correction_json(item) for item in items]


@app.post("/api/attendance/corrections")
def correct(payload: AttendanceCorrectionPayload, db: Session = Depends(get_db),
            user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    person = db.get(Person, payload.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, person.grade or "", person.section or "")
    item = save_correction(db, payload, user)
    generate_temporary_log(db, payload.attendance_date)
    return correction_json(item)


@app.get("/api/attendance/temporary-log")
def temporary_log(day: date = Query(alias="date"), grade: str | None = None, section: str | None = None,
                  db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> FileResponse:
    if bool(grade) != bool(section):
        raise HTTPException(
            status_code=422, detail="Select both grade and section, or neither for the all-school log")
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Teachers must select an assigned grade and section")
        ensure_adviser_access(db, user, grade, section)
    path = generate_temporary_log(db, day, grade, section)
    report = register_report(db, path, "Temporary Attendance Log", {
                             "date": day, "grade": grade, "section": section}, user)
    return FileResponse(report.file_path, filename=report.filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/attendance/report.xlsx")
def attendance_report_xlsx(starts_on: date, ends_on: date, role: str | None = None, grade: str | None = None,
                           section: str | None = None, person_id: int | None = None,
                           db: Session = Depends(get_db),
                           user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> FileResponse:
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Teachers must select an assigned grade and section")
        ensure_adviser_access(db, user, grade, section)
        role = "Student"
    path = generate_attendance_range_xlsx(
        db, starts_on, ends_on, role, grade, section, person_id)
    parameters = {"starts_on": starts_on, "ends_on": ends_on, "role": role, "grade": grade,
                  "section": section, "person_id": person_id}
    report = register_report(db, path, "Attendance Range", parameters, user)
    return FileResponse(report.file_path, filename=report.filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/attendance/report/print", response_class=HTMLResponse)
def attendance_report_print(starts_on: date, ends_on: date, role: str | None = None, grade: str | None = None,
                            section: str | None = None, person_id: int | None = None,
                            db: Session = Depends(get_db),
                            user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> HTMLResponse:
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Teachers must select an assigned grade and section")
        ensure_adviser_access(db, user, grade, section)
        role = "Student"
    return HTMLResponse(attendance_report_html(db, starts_on, ends_on, role, grade, section, person_id))


@app.post("/api/attendance/reset")
def attendance_reset(payload: AttendanceResetPayload, db: Session = Depends(get_db),
                     user: User = Depends(require_roles("admin"))) -> dict:
    if payload.confirmation != payload.attendance_date.isoformat():
        raise HTTPException(
            status_code=422, detail="Type the attendance date exactly to confirm the clean slate")
    audit = reset_day(db, payload.attendance_date, payload.reason, user)
    generate_temporary_log(db, payload.attendance_date)
    return reset_json(audit)


@app.get("/api/attendance/resets")
def attendance_resets(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> list[dict]:
    items = db.scalars(select(AttendanceResetAudit).order_by(
        AttendanceResetAudit.created_at.desc()).limit(200)).all()
    return [reset_json(item) for item in items]


@app.get("/api/schedules")
def schedules(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher"))) -> list[dict]:
    items = db.scalars(select(ClassSchedule).order_by(
        ClassSchedule.grade, ClassSchedule.section, ClassSchedule.start_time,
    )).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        items = [item for item in items if (
            item.grade, item.section) in allowed]
    return [{"id": item.id, "grade": item.grade, "section": item.section, "subject": item.subject,
             "teacher_name": item.teacher_name, "weekdays": item.weekdays, "start_time": item.start_time,
             "end_time": item.end_time, "late_grace_minutes": item.late_grace_minutes,
             "absence_cutoff": item.absence_cutoff, "active": item.active}
            for item in items]


@app.post("/api/schedules")
def save_schedule(payload: SchedulePayload, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    grade_level = db.scalar(select(GradeLevel).where(
        GradeLevel.name == payload.grade, GradeLevel.active.is_(True)))
    if not grade_level or not db.scalar(select(SchoolSection.id).where(
        SchoolSection.grade_level_id == grade_level.id, SchoolSection.name == payload.section,
        SchoolSection.active.is_(True),
    )):
        raise HTTPException(
            status_code=422, detail="Select an active grade level and section")
    if not db.scalar(select(Subject.id).where(Subject.name == payload.subject, Subject.active.is_(True))):
        raise HTTPException(status_code=422, detail="Select an active subject")
    if user.role == "teacher":
        ensure_adviser_access(db, user, payload.grade, payload.section)
    record = db.get(
        ClassSchedule, payload.id) if payload.id else ClassSchedule()
    if payload.id and not record:
        raise HTTPException(status_code=404, detail="Schedule was not found")
    if user.role == "teacher" and payload.id:
        ensure_adviser_access(db, user, record.grade, record.section)
    duplicate = db.scalar(select(ClassSchedule.id).where(
        ClassSchedule.grade == payload.grade, ClassSchedule.section == payload.section,
        ClassSchedule.subject == payload.subject, ClassSchedule.weekdays == payload.weekdays,
        ClassSchedule.id != (payload.id or 0),
    ))
    if duplicate:
        raise HTTPException(
            status_code=409, detail="An equivalent class schedule already exists")
    before = model_snapshot(record) if payload.id else {}
    for key, value in payload.model_dump(exclude={"id"}).items():
        setattr(record, key, value)
    if user.role == "teacher":
        record.teacher_name = user.full_name
    db.add(record)
    db.flush()
    add_audit(db, user, "Update" if payload.id else "Create", "ClassSchedule", record.id,
              f"Class schedule {'updated' if payload.id else 'created'} for Grade {record.grade} {record.section}",
              before, model_snapshot(record))
    db.commit()
    db.refresh(record)
    return {"id": record.id}


@app.delete("/api/schedules/{schedule_id}")
def remove_schedule(schedule_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    record = db.get(ClassSchedule, schedule_id)
    if not record:
        raise HTTPException(status_code=404, detail="Schedule was not found")
    if user.role == "teacher":
        ensure_adviser_access(db, user, record.grade, record.section)
    before = model_snapshot(record)
    db.delete(record)
    add_audit(db, user, "Delete", "ClassSchedule", record.id,
              f"Class schedule removed for Grade {record.grade} {record.section}", before, {})
    db.commit()
    return {"deleted": True}


@app.get("/api/personnel-schedules")
def personnel_schedules(db: Session = Depends(get_db),
                        _: User = Depends(require_roles("admin"))) -> list[dict]:
    items = db.scalars(select(PersonnelSchedule).order_by(
        PersonnelSchedule.role, PersonnelSchedule.assignment, PersonnelSchedule.start_time,
    )).all()
    return [{"id": item.id, "role": item.role, "assignment": item.assignment,
             "weekdays": item.weekdays, "start_time": item.start_time, "end_time": item.end_time,
             "late_grace_minutes": item.late_grace_minutes, "absence_cutoff": item.absence_cutoff,
             "active": item.active} for item in items]


@app.post("/api/personnel-schedules")
def save_personnel_schedule(payload: PersonnelSchedulePayload, db: Session = Depends(get_db),
                            actor: User = Depends(require_roles("admin"))) -> dict:
    assignment = payload.assignment.strip(
    ) if payload.assignment and payload.assignment.strip() else None
    item = db.get(PersonnelSchedule,
                  payload.id) if payload.id else PersonnelSchedule()
    if payload.id and not item:
        raise HTTPException(
            status_code=404, detail="Personnel schedule was not found")
    duplicate = db.scalar(select(PersonnelSchedule.id).where(
        PersonnelSchedule.role == payload.role,
        PersonnelSchedule.assignment == assignment,
        PersonnelSchedule.weekdays == payload.weekdays,
        PersonnelSchedule.id != (payload.id or 0),
    ))
    if duplicate:
        raise HTTPException(
            status_code=409, detail="An equivalent personnel schedule already exists")
    before = model_snapshot(item) if payload.id else {}
    for key, value in payload.model_dump(exclude={"id", "assignment"}).items():
        setattr(item, key, value)
    item.assignment = assignment
    db.add(item)
    db.flush()
    add_audit(db, actor, "Update" if payload.id else "Create", "PersonnelSchedule", item.id,
              f"Personnel schedule {'updated' if payload.id else 'created'} for {item.role}", before, model_snapshot(item))
    db.commit()
    db.refresh(item)
    return {"id": item.id}


@app.delete("/api/personnel-schedules/{schedule_id}")
def remove_personnel_schedule(schedule_id: int, db: Session = Depends(get_db),
                              actor: User = Depends(require_roles("admin"))) -> dict:
    item = db.get(PersonnelSchedule, schedule_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Personnel schedule was not found")
    before = model_snapshot(item)
    db.delete(item)
    add_audit(db, actor, "Delete", "PersonnelSchedule", item.id,
              f"Personnel schedule removed for {item.role}", before, {})
    db.commit()
    return {"deleted": True}


@app.get("/api/calendar/exceptions")
def calendar_exceptions(db: Session = Depends(get_db),
                        _: User = Depends(require_roles("admin"))) -> list[dict]:
    items = db.scalars(select(CalendarException).order_by(
        CalendarException.event_date.desc())).all()
    return [{"id": item.id, "event_date": item.event_date, "event_type": item.event_type,
             "reason": item.reason, "start_time": item.start_time, "end_time": item.end_time,
             "absence_cutoff": item.absence_cutoff, "actor_name": item.actor_name,
             "created_at": item.created_at} for item in items]


@app.post("/api/calendar/exceptions")
def save_calendar_exception(payload: CalendarExceptionPayload, db: Session = Depends(get_db),
                            user: User = Depends(require_roles("admin"))) -> dict:
    item = db.scalar(select(CalendarException).where(
        CalendarException.event_date == payload.event_date))
    before = model_snapshot(item) if item else {}
    if not item:
        item = CalendarException(id=str(uuid.uuid4()), event_date=payload.event_date,
                                 actor_user_id=user.id, actor_name=user.full_name)
    if payload.event_type == "Special Schedule" and not payload.start_time:
        raise HTTPException(
            status_code=422, detail="A special schedule requires a start time")
    for key, value in payload.model_dump(exclude={"event_date"}).items():
        setattr(item, key, value)
    db.add(item)
    add_audit(db, user, "Update" if before else "Create", "CalendarException", item.id,
              f"{payload.event_type} calendar exception saved for {payload.event_date}", before, model_snapshot(item))
    db.commit()
    return {"id": item.id}


@app.delete("/api/calendar/exceptions/{exception_id}")
def delete_calendar_exception(exception_id: str, db: Session = Depends(get_db),
                              actor: User = Depends(require_roles("admin"))) -> dict:
    item = db.get(CalendarException, exception_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Calendar exception was not found")
    before = model_snapshot(item)
    db.delete(item)
    add_audit(db, actor, "Delete", "CalendarException", item.id,
              f"Calendar exception removed for {item.event_date}", before, {})
    db.commit()
    return {"deleted": True}


@app.get("/api/attendance/excused")
def excused_absences(db: Session = Depends(get_db),
                     user: User = Depends(require_roles("admin", "teacher"))) -> list[dict]:
    items = db.scalars(select(ExcusedAbsence).order_by(
        ExcusedAbsence.event_date.desc(), ExcusedAbsence.created_at.desc())).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        items = [item for item in items if (
            item.person.grade, item.person.section) in allowed]
    return [{"id": item.id, "person_id": item.person_id, "person_name": item.person.full_name,
             "event_date": item.event_date, "reason": item.reason, "actor_name": item.actor_name,
             "created_at": item.created_at} for item in items]


@app.post("/api/attendance/excused")
def save_excused_absence(payload: ExcusedAbsencePayload, db: Session = Depends(get_db),
                         user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    person = db.get(Person, payload.person_id)
    if not person or person.role != "Student":
        raise HTTPException(status_code=404, detail="Student was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, person.grade or "", person.section or "")
    item = db.scalar(select(ExcusedAbsence).where(
        ExcusedAbsence.person_id == payload.person_id, ExcusedAbsence.event_date == payload.event_date,
    ))
    if not item:
        item = ExcusedAbsence(id=str(uuid.uuid4()), person_id=person.id, event_date=payload.event_date,
                              actor_user_id=user.id, actor_name=user.full_name)
    item.reason = payload.reason.strip()
    db.add(item)
    db.commit()
    return {"id": item.id}


@app.delete("/api/attendance/excused/{excused_id}")
def delete_excused_absence(excused_id: str, db: Session = Depends(get_db),
                           user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    item = db.get(ExcusedAbsence, excused_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Excused absence was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, item.person.grade or "", item.person.section or "")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@app.get("/api/admin/academic-structure")
def academic_structure(context: str = "", db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> dict:
    years = db.scalars(select(SchoolYear).order_by(
        SchoolYear.starts_on.desc())).all()
    periods = db.scalars(select(GradingPeriod).order_by(
        GradingPeriod.school_year_id.desc(), GradingPeriod.quarter)).all()
    grades = db.scalars(select(GradeLevel).order_by(
        GradeLevel.sequence, GradeLevel.name)).all()
    sections = db.scalars(select(SchoolSection).order_by(
        SchoolSection.grade_level_id, SchoolSection.name)).all()
    subjects = db.scalars(select(Subject).order_by(Subject.name)).all()
    if user.role == "teacher":
        allowed_sections = adviser_sections(db, user)
        allowed_section_ids = {item.id for item in allowed_sections}
        allowed_grade_ids = {item.grade_level_id for item in allowed_sections}
        sections = [item for item in sections if item.id in allowed_section_ids]
        grades = [item for item in grades if item.id in allowed_grade_ids]
    return {
        "school_years": [{"id": item.id, "name": item.name, "starts_on": item.starts_on, "ends_on": item.ends_on, "active": item.active} for item in years],
        "grading_periods": [{"id": item.id, "school_year_id": item.school_year_id, "school_year": item.school_year.name,
                             "name": item.name, "quarter": item.quarter, "starts_on": item.starts_on,
                             "ends_on": item.ends_on, "active": item.active} for item in periods],
        "grade_levels": [{"id": item.id, "name": item.name, "sequence": item.sequence, "active": item.active} for item in grades],
        "sections": [{"id": item.id, "grade_level_id": item.grade_level_id, "grade": item.grade_level.name,
                      "name": item.name, "adviser_user_id": item.adviser_user_id,
                      "adviser_name": item.adviser_name, "active": item.active} for item in sections],
        "subjects": [{"id": item.id, "code": item.code, "name": item.name, "active": item.active} for item in subjects],
    }


def _save_reference(db: Session, model, payload, actor: User, exclude: set[str] = {"id"}) -> dict:
    item = db.get(model, payload.id) if payload.id else model()
    if payload.id and not item:
        raise HTTPException(
            status_code=404, detail="Reference record was not found")
    before = model_snapshot(item) if payload.id else {}
    for key, value in payload.model_dump(exclude=exclude).items():
        setattr(item, key, value)
    try:
        db.add(item)
        db.flush()
        add_audit(db, actor, "Update" if payload.id else "Create", model.__name__, item.id,
                  f"{model.__name__} {'updated' if payload.id else 'created'}", before, model_snapshot(item))
        db.commit()
        db.refresh(item)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A matching reference record already exists") from exc
    return {"id": item.id}


@app.post("/api/admin/school-years")
def save_school_year(payload: SchoolYearPayload, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    if payload.ends_on <= payload.starts_on:
        raise HTTPException(
            status_code=422, detail="School year end date must follow its start date")
    return _save_reference(db, SchoolYear, payload, actor)


@app.post("/api/admin/grading-periods")
def save_grading_period(payload: GradingPeriodPayload, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    if payload.ends_on <= payload.starts_on or not db.get(SchoolYear, payload.school_year_id):
        raise HTTPException(
            status_code=422, detail="Grading-period dates or school year are invalid")
    return _save_reference(db, GradingPeriod, payload, actor)


@app.post("/api/admin/grade-levels")
def save_grade_level(payload: GradeLevelPayload, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    return _save_reference(db, GradeLevel, payload, actor)


@app.post("/api/admin/sections")
def save_section(payload: SectionPayload, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    if not db.get(GradeLevel, payload.grade_level_id):
        raise HTTPException(
            status_code=422, detail="Grade level was not found")
    if payload.adviser_user_id is not None:
        adviser = db.get(User, payload.adviser_user_id)
        if not adviser or adviser.role != "teacher" or not adviser.active:
            raise HTTPException(
                status_code=422, detail="Select an active teacher account as adviser")
        payload.adviser_name = adviser.full_name
    else:
        payload.adviser_name = None
    return _save_reference(db, SchoolSection, payload, actor)


@app.post("/api/admin/subjects")
def save_subject(payload: SubjectPayload, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))) -> dict:
    return _save_reference(db, Subject, payload, actor)


@app.delete("/api/admin/reference/{kind}/{record_id}")
def delete_reference(kind: str, record_id: int, db: Session = Depends(get_db),
                     actor: User = Depends(require_roles("admin"))) -> dict:
    models = {"school-years": SchoolYear, "grading-periods": GradingPeriod, "grade-levels": GradeLevel,
              "sections": SchoolSection, "subjects": Subject}
    model = models.get(kind)
    if not model:
        raise HTTPException(
            status_code=404, detail="Reference type was not found")
    item = db.get(model, record_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Reference record was not found")
    before = model_snapshot(item)
    try:
        db.delete(item)
        add_audit(db, actor, "Delete", model.__name__, record_id,
                  f"{model.__name__} deleted", before, {})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This record is still referenced; deactivate it instead") from exc
    return {"deleted": True}


@app.get("/api/settings")
def read_settings(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> dict:
    sms = sms_config(db)
    return {
        "attendance": {"absence_cutoff": "09:00", "duplicate_cooldown_seconds": 45,
                       "auto_close_enabled": True, **get_json(db, "attendance", {})},
        "sms": {**sms, "password": "", "password_configured": bool(sms["password"])},
        "compliance": get_json(db, "compliance", {}),
        "retention": get_json(db, "retention", {"sms_days": 90, "correction_audit_years": 5}),
    }


@app.put("/api/settings/attendance")
def save_attendance_settings(payload: AttendanceSettingsPayload, db: Session = Depends(get_db),
                             user: User = Depends(require_roles("admin"))) -> dict:
    before = get_json(db, "attendance", {})
    value = {"absence_cutoff": payload.absence_cutoff.strftime("%H:%M"),
             "duplicate_cooldown_seconds": payload.duplicate_cooldown_seconds,
             "auto_close_enabled": payload.auto_close_enabled}
    set_json(db, "attendance", value)
    add_audit(db, user, "Update", "AttendanceSettings", "attendance",
              "Attendance settings updated", before, value, commit=True)
    return value


@app.post("/api/attendance/auto-close/run")
def run_automatic_close(_: User = Depends(require_roles("admin"))) -> dict:
    return attendance_scheduler.run_once()


@app.put("/api/settings/sms")
def save_sms_settings(payload: SmsSettingsPayload, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin"))) -> dict:
    before = {key: value for key, value in sms_config(
        db).items() if key != "password"}
    set_json(db, "sms", {"enabled": payload.enabled, "gateway_url": payload.gateway_url, "username": payload.username,
                         "school_contact": payload.school_contact,
                         "max_messages_per_30_minutes": payload.max_messages_per_30_minutes,
                         "templates": {"time_in": payload.time_in_template, "time_out": payload.time_out_template,
                                       "tardiness": payload.tardiness_template, "absence": payload.absence_template}})
    if payload.password is not None:
        set_secret(db, "sms.password", payload.password)
    after = {key: value for key, value in sms_config(
        db).items() if key != "password"}
    add_audit(db, user, "Update", "SmsSettings", "sms",
              "SMS gateway settings updated", before, after, commit=True)
    return {"saved": True}


@app.put("/api/settings/compliance")
def save_compliance(payload: CompliancePayload, db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    before = get_json(db, "compliance", {})
    set_json(db, "compliance", payload.model_dump())
    add_audit(db, user, "Update", "ComplianceSettings", "compliance",
              "Compliance evidence register updated", before, payload.model_dump(), commit=True)
    return payload.model_dump()


@app.get("/api/settings/compliance")
def read_compliance(db: Session = Depends(get_db),
                    _: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    return get_json(db, "compliance", {})


@app.get("/api/retention")
def get_retention(db: Session = Depends(get_db),
                  _: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    return retention_policy(db)


@app.put("/api/retention")
def save_retention(payload: RetentionPolicyPayload, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    before = retention_policy(db)
    value = payload.model_dump()
    set_json(db, "retention", value)
    add_audit(db, user, "Update", "RetentionPolicy", "retention",
              "Retention policy updated", before, value, commit=True)
    return value


@app.get("/api/retention/preview")
def preview_retention(db: Session = Depends(get_db),
                      _: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    return public_preview(retention_preview(db))


@app.post("/api/retention/execute")
def run_retention(payload: RetentionExecutionPayload, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    if payload.confirmation != "EXECUTE RETENTION":
        raise HTTPException(
            status_code=422, detail="Type EXECUTE RETENTION to confirm the approved cleanup")
    item = execute_retention(db, payload.authorization_reference, user)
    return {"id": item.id, "certificate_reference": item.certificate_reference,
            "removed_counts": json.loads(item.removed_counts_json), "created_at": item.created_at}


@app.get("/api/retention/executions")
def retention_executions(db: Session = Depends(get_db),
                         _: User = Depends(require_roles("admin", "privacy_officer"))) -> list[dict]:
    items = db.scalars(select(RetentionExecution).order_by(
        RetentionExecution.created_at.desc()).limit(500)).all()
    return [{"id": item.id, "certificate_reference": item.certificate_reference,
             "authorization_reference": item.authorization_reference,
             "removed_counts": json.loads(item.removed_counts_json), "actor_name": item.actor_name,
             "created_at": item.created_at} for item in items]


@app.get("/api/legal-holds")
def legal_holds(db: Session = Depends(get_db),
                _: User = Depends(require_roles("admin", "privacy_officer"))) -> list[dict]:
    items = db.scalars(select(LegalHold).order_by(
        LegalHold.active.desc(), LegalHold.created_at.desc())).all()
    return [{"id": item.id, "scope": item.scope, "subject_reference": item.subject_reference,
             "reason": item.reason, "authority_reference": item.authority_reference, "active": item.active,
             "placed_by_name": item.placed_by_name, "released_by_name": item.released_by_name,
             "release_reason": item.release_reason, "released_at": item.released_at,
             "created_at": item.created_at} for item in items]


@app.post("/api/legal-holds")
def create_legal_hold(payload: LegalHoldPayload, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    item = LegalHold(id=str(uuid.uuid4()), scope=payload.scope, subject_reference=payload.subject_reference,
                     reason=payload.reason.strip(), authority_reference=payload.authority_reference.strip(),
                     placed_by=user.id, placed_by_name=user.full_name)
    db.add(item)
    add_audit(db, user, "Create", "LegalHold", item.id,
              f"Legal hold placed for {payload.scope}", {}, model_snapshot(item))
    db.commit()
    return {"id": item.id}


@app.post("/api/legal-holds/{hold_id}/release")
def release_legal_hold(hold_id: str, payload: LegalHoldReleasePayload, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("admin", "privacy_officer"))) -> dict:
    item = db.get(LegalHold, hold_id)
    if not item or not item.active:
        raise HTTPException(
            status_code=404, detail="Active legal hold was not found")
    before = model_snapshot(item)
    item.active = False
    item.released_by = user.id
    item.released_by_name = user.full_name
    item.release_reason = payload.reason.strip()
    item.released_at = datetime.utcnow()
    add_audit(db, user, "Release", "LegalHold", item.id,
              payload.reason, before, model_snapshot(item))
    db.commit()
    return {"released": True}


@app.get("/api/audit")
def system_audit(entity_type: str | None = None, action: str | None = None,
                 limit: int = Query(default=500, ge=1, le=2000), db: Session = Depends(get_db),
                 _: User = Depends(require_roles("admin", "records_officer", "privacy_officer"))) -> list[dict]:
    query = select(SystemAuditEvent)
    if entity_type:
        query = query.where(SystemAuditEvent.entity_type == entity_type)
    if action:
        query = query.where(SystemAuditEvent.action == action)
    items = db.scalars(query.order_by(
        SystemAuditEvent.created_at.desc()).limit(limit)).all()
    return [{"id": item.id, "action": item.action, "entity_type": item.entity_type,
             "entity_id": item.entity_id, "summary": item.summary,
             "before": json.loads(item.before_json), "after": json.loads(item.after_json),
             "actor_name": item.actor_name, "actor_role": item.actor_role,
             "created_at": item.created_at} for item in items]


@app.get("/api/sms/outbox")
def outbox(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "records_officer"))) -> list[dict]:
    items = db.scalars(select(SmsOutbox).order_by(
        SmsOutbox.created_at.desc()).limit(500)).all()
    return [{"id": item.id, "event_type": item.event_type, "recipient": mask_phone(item.recipient),
             "message": item.message, "status": item.status, "attempts": item.attempts,
             "last_error": item.last_error, "next_attempt_at": item.next_attempt_at,
             "gateway_message_id": item.gateway_message_id,
             "created_at": item.created_at, "sent_at": item.sent_at,
             "delivered_at": item.delivered_at, "cancelled_at": item.cancelled_at,
             "exhausted_at": item.exhausted_at,
             "gateway_status_checked_at": item.gateway_status_checked_at} for item in items]


@app.get("/api/sms/gateway/check")
def check_sms_gateway(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> dict:
    return gateway_diagnostics(db)


@app.post("/api/sms/dispatch")
def dispatch(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> dict:
    records = dispatch_queued(db)
    return {"processed": len(records), "accepted": sum(record.status == "accepted" for record in records)}


@app.post("/api/sms/reconcile")
def reconcile_sms(db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "records_officer"))) -> dict:
    records = reconcile_outbox(db)
    add_audit(db, user, "Reconcile", "SmsOutbox", None,
              f"Reconciled {len(records)} Android gateway message(s)", {},
              {"processed": len(records)}, commit=True)
    return {"processed": len(records), "statuses": {
        status: sum(item.status == status for item in records)
        for status in ("accepted", "processed", "sent", "delivered", "failed", "cancelled")
    }}


@app.post("/api/sms/outbox/{record_id}/requeue")
def requeue_sms(record_id: str, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin", "records_officer"))) -> dict:
    record = db.get(SmsOutbox, record_id)
    if not record:
        raise HTTPException(
            status_code=404, detail="SMS outbox record was not found")
    before = model_snapshot(record)
    requeue_record(db, record)
    add_audit(db, user, "Requeue", "SmsOutbox", record.id,
              "Authorized SMS message requeue", before, model_snapshot(record), commit=True)
    return {"id": record.id, "status": record.status}


@app.post("/api/sms/outbox/{record_id}/cancel")
def cancel_sms(record_id: str, db: Session = Depends(get_db),
               user: User = Depends(require_roles("admin", "records_officer"))) -> dict:
    record = db.get(SmsOutbox, record_id)
    if not record:
        raise HTTPException(
            status_code=404, detail="SMS outbox record was not found")
    before = model_snapshot(record)
    cancel_record(db, record)
    add_audit(db, user, "Cancel", "SmsOutbox", record.id,
              "Authorized obsolete SMS cancellation", before, model_snapshot(record), commit=True)
    return {"id": record.id, "status": record.status}


@app.get("/api/sms/outbox.csv")
def export_sms_outbox(db: Session = Depends(get_db),
                      _: User = Depends(require_roles("admin", "records_officer"))) -> StreamingResponse:
    items = db.scalars(select(SmsOutbox).order_by(
        SmsOutbox.created_at.desc())).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Created", "Event", "Recipient", "Status", "Attempts", "Gateway ID",
                     "Accepted/Sent", "Delivered", "Cancelled", "Last error", "Message"])
    for item in items:
        writer.writerow([item.created_at, item.event_type, item.recipient, item.status, item.attempts,
                         item.gateway_message_id or "", item.sent_at or "", item.delivered_at or "",
                         item.cancelled_at or "", item.last_error or "", item.message])
    filename = f"EduScan-SMS-delivery-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/sms/test")
def test_sms(phone: str = Form(...), message: str = Form("EduScan Android gateway connection test."),
             db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))) -> dict:
    from .models import SmsOutbox
    from .services.sms import normalize_phone
    record = SmsOutbox(id=__import__("uuid").uuid4().hex, event_type="test",
                       recipient=normalize_phone(phone), message=message, status="queued")
    db.add(record)
    db.commit()
    send_record(db, record)
    return {"status": record.status, "error": record.last_error}


@app.get("/api/sf2/template")
def sf2_status(_: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> dict:
    try:
        path = template_path()
        return {"configured": True, "filename": path.name}
    except HTTPException:
        return {"configured": False, "filename": None}


@app.post("/api/sf2/template")
async def upload_sf2(file: UploadFile = File(...), _: User = Depends(require_roles("admin"))) -> dict:
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=422, detail="Upload an .xlsx SF2 workbook")
    path = save_template(await file.read())
    return {"configured": True, "filename": path.name}


@app.get("/api/sf2/export")
def sf2_export(year: int, month: int, grade: str, section: str, school_id: str = "",
               school_year: str = "", school_name: str = "SAN JOSE NATIONAL HIGH SCHOOL",
               db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> FileResponse:
    if not 1 <= month <= 12:
        raise HTTPException(
            status_code=422, detail="Month must be between 1 and 12")
    ensure_adviser_access(db, user, grade, section)
    path = generate_sf2(db, year, month, grade, section,
                        school_id, school_year, school_name)
    report = register_report(db, path, "Official SF2", {"year": year, "month": month, "grade": grade,
                                                        "section": section, "school_id": school_id,
                                                        "school_year": school_year}, user)
    return FileResponse(report.file_path, filename=report.filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def report_json(item: GeneratedReport) -> dict:
    return {"id": item.id, "report_type": item.report_type, "filename": item.filename,
            "sha256": item.file_sha256, "parameters": json.loads(item.parameters_json),
            "status": item.status, "generated_by_name": item.generated_by_name,
            "reviewed_by_name": item.reviewed_by_name, "review_note": item.review_note,
            "reviewed_at": item.reviewed_at, "created_at": item.created_at}


@app.get("/api/reports/history")
def report_history(db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher", "records_officer", "privacy_officer"))) -> list[dict]:
    items = db.scalars(select(GeneratedReport).order_by(
        GeneratedReport.created_at.desc()).limit(1000)).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        items = [item for item in items if item.generated_by == user.id or
                 (lambda p: (str(p.get("grade") or ""), str(p.get("section") or "")) in allowed)(json.loads(item.parameters_json))]
    return [report_json(item) for item in items]


@app.get("/api/reports/history/{report_id}/download")
def download_generated_report(report_id: str, db: Session = Depends(get_db),
                              user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> FileResponse:
    item = db.get(GeneratedReport, report_id)
    if not item or not Path(item.file_path).is_file():
        raise HTTPException(
            status_code=404, detail="Generated report file was not found")
    if user.role == "teacher":
        parameters = json.loads(item.parameters_json)
        ensure_adviser_access(db, user, str(parameters.get(
            "grade") or ""), str(parameters.get("section") or ""))
    return FileResponse(item.file_path, filename=item.filename)


@app.post("/api/reports/history/{report_id}/review")
def review_generated_report(report_id: str, payload: ReportReviewPayload, db: Session = Depends(get_db),
                            user: User = Depends(require_roles("admin", "records_officer"))) -> dict:
    item = db.get(GeneratedReport, report_id)
    if not item:
        raise HTTPException(
            status_code=404, detail="Generated report was not found")
    before = model_snapshot(item)
    item.status = payload.status
    item.reviewed_by = user.id
    item.reviewed_by_name = user.full_name
    item.review_note = payload.note.strip()
    item.reviewed_at = datetime.utcnow()
    add_audit(db, user, "Review", "GeneratedReport", item.id,
              f"Report marked {payload.status}: {payload.note}", before, model_snapshot(item))
    db.commit()
    return report_json(item)


def gradebook_data(class_key: str, db: Session) -> dict:
    components = db.scalars(select(GradeComponent).where(
        GradeComponent.class_key == class_key).order_by(GradeComponent.sequence)).all()
    component_ids = [item.id for item in components]
    scores = db.scalars(select(GradeScore).where(
        GradeScore.component_id.in_(component_ids))).all() if component_ids else []
    grouped_scores: dict[str, dict[str, float]] = {}
    grouped_statuses: dict[str, dict[str, str]] = {}
    for score in scores:
        grouped_scores.setdefault(str(score.person_id), {})[
            str(score.component_id)] = score.score
        grouped_statuses.setdefault(str(score.person_id), {})[
            str(score.component_id)] = score.status
    rules = get_json(db, f"gradebook:{class_key}:rules", {"passing_grade": 75, "school_year": "2026-2027",
                                                          "quarter": 1, "subject": "Unspecified"})
    state = db.get(GradebookState, class_key)
    return {
        "class_key": class_key,
        "passing_grade": state.passing_grade if state else rules.get("passing_grade", 75),
        "school_year": state.school_year if state else rules.get("school_year", "2026-2027"),
        "quarter": state.quarter if state else rules.get("quarter", 1),
        "subject": state.subject if state else rules.get("subject", "Unspecified"),
        "grade": state.grade if state else rules.get("grade", ""),
        "section": state.section if state else rules.get("section", ""),
        "status": state.status if state else "Draft",
        "finalized_at": state.finalized_at if state else None,
        "finalized_by_name": state.finalized_by_name if state else None,
        "components": [{"id": str(item.id), "category": item.category, "label": item.label, "weight": item.weight,
                        "max_score": item.max_score, "sequence": item.sequence} for item in components],
        "scores": grouped_scores,
        "score_statuses": grouped_statuses,
    }


@app.get("/api/gradebook/{class_key}")
def read_gradebook(class_key: str, grade: str = "", section: str = "", db: Session = Depends(get_db),
                   user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> dict:
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Grade and section are required for adviser access control")
        ensure_adviser_access(db, user, grade, section)
    return gradebook_data(class_key, db)


@app.put("/api/gradebook/{class_key}")
def save_gradebook(class_key: str, payload: GradebookPayload, db: Session = Depends(get_db),
                   user: User = Depends(require_roles("teacher"))) -> dict:
    if payload.class_key != class_key:
        raise HTTPException(
            status_code=422, detail="Class key does not match URL")
    ensure_adviser_access(db, user, payload.grade, payload.section)
    existing_state = db.get(GradebookState, class_key)
    if existing_state and existing_state.status == "Finalized":
        raise HTTPException(
            status_code=409, detail="This gradebook is finalized. An administrator or records officer must reopen it with a reason before changes are allowed")
    year = db.scalar(select(SchoolYear).where(
        SchoolYear.name == payload.school_year, SchoolYear.active.is_(True)))
    if not year or not db.scalar(select(GradingPeriod.id).where(
        GradingPeriod.school_year_id == year.id, GradingPeriod.quarter == payload.quarter,
        GradingPeriod.active.is_(True),
    )):
        raise HTTPException(
            status_code=422, detail="Select an active school year and grading period")
    grade_level = db.scalar(select(GradeLevel).where(
        GradeLevel.name == payload.grade, GradeLevel.active.is_(True)))
    school_section = db.scalar(select(SchoolSection).where(
        SchoolSection.grade_level_id == grade_level.id, SchoolSection.name == payload.section,
        SchoolSection.active.is_(True),
    )) if grade_level else None
    if not school_section:
        raise HTTPException(
            status_code=422, detail="Select an active grade level and section")
    if not db.scalar(select(Subject.id).where(Subject.name == payload.subject, Subject.active.is_(True))):
        raise HTTPException(status_code=422, detail="Select an active subject")

    component_ids = [item.id for item in payload.components]
    if len(component_ids) != len(set(component_ids)):
        raise HTTPException(
            status_code=422, detail="Grade component identifiers must be unique")
    manual = [item for item in payload.components if item.category ==
              "Manual Overall"]
    if len(manual) > 1 or any(item.weight != 0 for item in manual):
        raise HTTPException(
            status_code=422, detail="Only one zero-weight Manual Overall component is allowed")
    weighted = [
        item for item in payload.components if item.category != "Manual Overall"]
    if not weighted or round(sum(item.weight for item in weighted), 4) != 100:
        raise HTTPException(
            status_code=422, detail="Grade component weights must total exactly 100%")
    allowed_people = set(db.scalars(select(Person.id).where(
        Person.role == "Student", Person.active.is_(
            True), Person.grade == payload.grade,
        Person.section == payload.section,
    )).all())
    submitted_people = {int(person_id) for person_id in payload.scores}
    if not submitted_people.issubset(allowed_people):
        raise HTTPException(
            status_code=422, detail="Gradebook contains a learner outside the selected active section")
    before = gradebook_data(class_key, db)
    old_ids = list(db.scalars(select(GradeComponent.id).where(
        GradeComponent.class_key == class_key)).all())
    if old_ids:
        db.execute(delete(GradeScore).where(
            GradeScore.component_id.in_(old_ids)))
        db.execute(delete(GradeComponent).where(
            GradeComponent.id.in_(old_ids)))
    key_map: dict[str, int] = {}
    maximums: dict[str, float] = {}
    for sequence, item in enumerate(payload.components):
        record = GradeComponent(class_key=class_key, category=item.category.strip(), label=item.label.strip(),
                                weight=item.weight, max_score=item.max_score, sequence=sequence)
        db.add(record)
        db.flush()
        key_map[item.id] = record.id
        maximums[item.id] = item.max_score
    for person_id, person_scores in payload.scores.items():
        submitted_statuses = payload.score_statuses.get(person_id, {})
        for client_id in set(person_scores) | set(submitted_statuses):
            score = person_scores.get(client_id)
            if client_id not in key_map:
                continue
            status = submitted_statuses.get(
                client_id, "Scored" if score not in ("", None) else "Missing")
            if status != "Scored":
                db.add(GradeScore(person_id=int(person_id), component_id=key_map[client_id], score=0,
                                  status=status, updated_by=user.id))
                continue
            if score in ("", None):
                raise HTTPException(
                    status_code=422, detail="A score marked Scored must contain a numeric value")
            try:
                numeric = float(score)
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail="Every entered score must be numeric") from exc
            if not math.isfinite(numeric) or numeric < 0 or numeric > maximums[client_id]:
                raise HTTPException(
                    status_code=422, detail=f"A score must be between 0 and {maximums[client_id]:g}")
            db.add(GradeScore(person_id=int(person_id), component_id=key_map[client_id], score=numeric,
                              status="Scored", updated_by=user.id))
    db.flush()
    set_json(db, f"gradebook:{class_key}:rules", {"passing_grade": payload.passing_grade,
             "school_year": payload.school_year, "quarter": payload.quarter, "subject": payload.subject,
                                                  "grade": payload.grade, "section": payload.section}, commit=False)
    state = existing_state or GradebookState(class_key=class_key)
    state.school_year = payload.school_year
    state.quarter = payload.quarter
    state.subject = payload.subject
    state.grade = payload.grade
    state.section = payload.section
    state.passing_grade = payload.passing_grade
    state.status = "Draft"
    db.add(state)
    after = gradebook_data(class_key, db)
    db.add(GradeChangeAudit(id=str(uuid.uuid4()), class_key=class_key, school_year=payload.school_year,
                            quarter=payload.quarter, subject=payload.subject, reason=payload.change_reason.strip(),
                            actor_user_id=user.id, actor_name=user.full_name, actor_role=user.role,
                            before_json=json.dumps(before, default=str), after_json=json.dumps(after, default=str)))
    db.commit()
    return {"saved": True, "component_count": len(key_map)}


@app.post("/api/gradebook/{class_key}/finalize")
def finalize_gradebook(class_key: str, payload: GradebookActionPayload, db: Session = Depends(get_db),
                       user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    state = db.get(GradebookState, class_key)
    if not state:
        raise HTTPException(
            status_code=404, detail="Save the gradebook before finalizing it")
    ensure_adviser_access(db, user, state.grade, state.section)
    if state.status == "Finalized":
        return {"finalized": True, "already_finalized": True}
    summary = gradebook_summary(db, class_key)
    if summary["statistics"]["incomplete"]:
        raise HTTPException(
            status_code=409, detail=f"{summary['statistics']['incomplete']} learner(s) still have missing, excused, incomplete, or blank assessment results")
    before = model_snapshot(state)
    state.status = "Finalized"
    state.finalized_by = user.id
    state.finalized_by_name = user.full_name
    state.finalized_at = datetime.utcnow()
    state.reopen_reason = None
    add_audit(db, user, "Finalize", "Gradebook", class_key,
              payload.reason, before, model_snapshot(state))
    db.commit()
    return {"finalized": True, "finalized_at": state.finalized_at}


@app.post("/api/gradebook/{class_key}/reopen")
def reopen_gradebook(class_key: str, payload: GradebookActionPayload, db: Session = Depends(get_db),
                     user: User = Depends(require_roles("admin", "records_officer"))) -> dict:
    state = db.get(GradebookState, class_key)
    if not state:
        raise HTTPException(status_code=404, detail="Gradebook was not found")
    if state.status != "Finalized":
        raise HTTPException(
            status_code=409, detail="Only a finalized gradebook can be reopened")
    before = model_snapshot(state)
    state.status = "Draft"
    state.reopened_by = user.id
    state.reopened_by_name = user.full_name
    state.reopened_at = datetime.utcnow()
    state.reopen_reason = payload.reason.strip()
    add_audit(db, user, "Reopen", "Gradebook", class_key,
              payload.reason, before, model_snapshot(state))
    db.commit()
    return {"reopened": True}


@app.get("/api/gradebook/{class_key}/report.xlsx")
def gradebook_report_xlsx(class_key: str, grade: str = "", section: str = "", db: Session = Depends(get_db),
                          user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> FileResponse:
    state = db.get(GradebookState, class_key)
    if not state:
        raise HTTPException(status_code=404, detail="Gradebook was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, grade or state.grade, section or state.section)
    path = generate_grade_report_xlsx(db, class_key)
    report = register_report(db, path, "Grading Summary", {"class_key": class_key, "grade": state.grade, "section": state.section,
                                                           "school_year": state.school_year, "quarter": state.quarter,
                                                           "subject": state.subject}, user)
    return FileResponse(report.file_path, filename=report.filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/gradebook/{class_key}/report/print", response_class=HTMLResponse)
def gradebook_report_print(class_key: str, grade: str = "", section: str = "", db: Session = Depends(get_db),
                           user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> HTMLResponse:
    state = db.get(GradebookState, class_key)
    if not state:
        raise HTTPException(status_code=404, detail="Gradebook was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, grade or state.grade, section or state.section)
    return HTMLResponse(grade_report_html(db, class_key))


@app.get("/api/gradebook/{class_key}/audit")
def gradebook_audit(class_key: str, grade: str = "", section: str = "", db: Session = Depends(get_db),
                    user: User = Depends(require_roles("admin", "teacher", "records_officer"))) -> list[dict]:
    if user.role == "teacher":
        if not grade or not section:
            raise HTTPException(
                status_code=422, detail="Grade and section are required for adviser access control")
        ensure_adviser_access(db, user, grade, section)
    items = db.scalars(select(GradeChangeAudit).where(GradeChangeAudit.class_key == class_key)
                       .order_by(GradeChangeAudit.created_at.desc()).limit(200)).all()
    return [{"id": item.id, "school_year": item.school_year, "quarter": item.quarter,
             "subject": item.subject, "reason": item.reason, "actor_name": item.actor_name,
             "actor_role": item.actor_role, "before": json.loads(item.before_json),
             "after": json.loads(item.after_json), "created_at": item.created_at} for item in items]


# ---------------------------------------------------------------------------
# Policy-Configurable Grading Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/grading-policies")
def list_grading_policies(
    school_year: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    query = select(GradingPolicy).order_by(GradingPolicy.created_at.desc())
    if school_year:
        query = query.where(GradingPolicy.school_year == school_year)
    if status:
        query = query.where(GradingPolicy.status == status)
    policies = db.scalars(query).all()
    results = []
    for p in policies:
        results.append({
            "id": p.id,
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "school_year": p.school_year,
            "grade_levels": p.grade_levels,
            "subject_category": p.subject_category,
            "component_definitions": json.loads(p.component_definitions_json or "[]"),
            "transmutation_table": json.loads(p.transmutation_table_json) if p.transmutation_table_json else None,
            "rounding_decimal_places": p.rounding_decimal_places,
            "rounding_final_decimal_places": p.rounding_final_decimal_places,
            "rounding_method": p.rounding_method,
            "passing_grade": p.passing_grade,
            "status": p.status,
            "effective_date": str(p.effective_date) if p.effective_date else None,
            "created_by_name": p.created_by_name,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })
    return results


@app.post("/api/grading-policies")
def create_grading_policy(
    payload: GradingPolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    p = GradingPolicy(
        name=payload.name.strip(),
        description=payload.description.strip(),
        school_year=payload.school_year.strip(),
        grade_levels=payload.grade_levels.strip(),
        subject_category=payload.subject_category.strip(),
        component_definitions_json=json.dumps(
            [c.model_dump() for c in payload.component_definitions]),
        transmutation_table_json=json.dumps(
            payload.transmutation_table) if payload.transmutation_table else None,
        rounding_decimal_places=payload.rounding_decimal_places,
        rounding_final_decimal_places=payload.rounding_final_decimal_places,
        rounding_method=payload.rounding_method,
        passing_grade=payload.passing_grade,
        status="Active",
        created_by=user.id,
        created_by_name=user.full_name,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "id": p.id,
        "name": p.name,
        "version": p.version,
        "status": p.status,
    }


@app.get("/api/grading-policies/{policy_id}")
def get_grading_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    p = db.get(GradingPolicy, policy_id)
    if not p:
        raise HTTPException(status_code=404, detail="Grading policy not found")
    return {
        "id": p.id,
        "name": p.name,
        "version": p.version,
        "description": p.description,
        "school_year": p.school_year,
        "grade_levels": p.grade_levels,
        "subject_category": p.subject_category,
        "component_definitions": json.loads(p.component_definitions_json or "[]"),
        "transmutation_table": json.loads(p.transmutation_table_json) if p.transmutation_table_json else None,
        "rounding_decimal_places": p.rounding_decimal_places,
        "rounding_final_decimal_places": p.rounding_final_decimal_places,
        "rounding_method": p.rounding_method,
        "passing_grade": p.passing_grade,
        "status": p.status,
        "effective_date": str(p.effective_date) if p.effective_date else None,
        "created_by_name": p.created_by_name,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


@app.put("/api/grading-policies/{policy_id}")
def update_grading_policy(
    policy_id: int,
    payload: GradingPolicyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    p = db.get(GradingPolicy, policy_id)
    if not p:
        raise HTTPException(status_code=404, detail="Grading policy not found")
    p.name = payload.name.strip()
    p.description = payload.description.strip()
    p.school_year = payload.school_year.strip()
    p.grade_levels = payload.grade_levels.strip()
    p.subject_category = payload.subject_category.strip()
    p.component_definitions_json = json.dumps(
        [c.model_dump() for c in payload.component_definitions])
    p.transmutation_table_json = json.dumps(
        payload.transmutation_table) if payload.transmutation_table else None
    p.rounding_decimal_places = payload.rounding_decimal_places
    p.rounding_final_decimal_places = payload.rounding_final_decimal_places
    p.rounding_method = payload.rounding_method
    p.passing_grade = payload.passing_grade
    p.status = payload.status
    db.commit()
    return {"updated": True, "id": p.id}


@app.get("/api/gradebooks")
def list_gradebooks(
    school_year: str = "",
    quarter: int | None = None,
    grade: str = "",
    section: str = "",
    subject: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    query = select(Gradebook).order_by(Gradebook.grade_name,
                                       Gradebook.section_name, Gradebook.subject_name)
    if school_year:
        query = query.where(Gradebook.school_year_name == school_year)
    if quarter:
        query = query.where(Gradebook.quarter == quarter)
    if grade:
        query = query.where(Gradebook.grade_name == grade)
    if section:
        query = query.where(Gradebook.section_name == section)
    if subject:
        query = query.where(Gradebook.subject_name == subject)

    books = db.scalars(query).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        books = [b for b in books if (
            b.grade_name, b.section_name) in allowed or b.teacher_user_id == user.id]

    results = []
    for b in books:
        policy = db.get(
            GradingPolicy, b.grading_policy_id) if b.grading_policy_id else None
        results.append({
            "id": b.id,
            "school_year_id": b.school_year_id,
            "grading_period_id": b.grading_period_id,
            "grade_level_id": b.grade_level_id,
            "section_id": b.section_id,
            "subject_id": b.subject_id,
            "school_year_name": b.school_year_name,
            "quarter": b.quarter,
            "grade_name": b.grade_name,
            "section_name": b.section_name,
            "subject_name": b.subject_name,
            "teacher_name": b.teacher_name,
            "class_key": b.class_key,
            "status": b.status,
            "policy_name": policy.name if policy else None,
            "policy_version": policy.version if policy else None,
            "created_at": b.created_at,
        })
    return results


@app.post("/api/gradebooks")
def create_gradebook_endpoint(
    payload: GradebookCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
):
    sec = db.get(SchoolSection, payload.section_id)
    gl = db.get(GradeLevel, payload.grade_level_id)
    try:
        book = grading_service.create_or_get_gradebook(
            db=db,
            school_year_id=payload.school_year_id,
            grading_period_id=payload.grading_period_id,
            grade_level_id=payload.grade_level_id,
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            user=user,
            grading_policy_id=payload.grading_policy_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": book.id, "status": book.status, "class_key": book.class_key}


@app.get("/api/gradebooks/{gradebook_id}")
def get_gradebook_endpoint(
    gradebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    full = grading_service.get_gradebook_full(db, gradebook_id)
    if not full:
        raise HTTPException(
            status_code=404, detail="Gradebook details could not be loaded")
    return full


@app.put("/api/gradebooks/{gradebook_id}/components")
def update_components_endpoint(
    gradebook_id: int,
    payload: GradebookComponentsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    try:
        comp_payload_dicts = [c.model_dump() for c in payload.components]
        grading_service.update_gradebook_components(
            db, gradebook_id, user, comp_payload_dicts, payload.change_reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"updated": True, "id": gradebook_id}


@app.put("/api/gradebooks/{gradebook_id}/scores")
def save_scores_endpoint(
    gradebook_id: int,
    payload: GradebookScoresUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    try:
        scores_dict = {
            pid: [entry.model_dump() for entry in entries]
            for pid, entries in payload.scores.items()
        }
        res = grading_service.save_gradebook_scores(
            db, gradebook_id, user, scores_dict, payload.change_reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return res


@app.get("/api/gradebooks/{gradebook_id}/calculation/{person_id}")
def get_student_calculation_endpoint(
    gradebook_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    breakdown = grading_service.get_student_breakdown(
        db, gradebook_id, person_id)
    if not breakdown:
        raise HTTPException(
            status_code=404, detail="Student calculation breakdown not found")
    return breakdown


@app.post("/api/gradebooks/{gradebook_id}/validate")
def validate_gradebook_endpoint(
    gradebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    full = grading_service.get_gradebook_full(db, gradebook_id)
    if not full:
        raise HTTPException(
            status_code=404, detail="Gradebook could not be loaded")

    comp_weights = [c["weight"] for c in full["components"]]
    issues = []
    if abs(sum(comp_weights) - 100.0) > 0.01:
        issues.append({"level": "error", "code": "WEIGHT_MISMATCH",
                      "message": f"Component weights sum to {sum(comp_weights):.1f}%, must be 100%"})
    if not full["components"]:
        issues.append({"level": "error", "code": "NO_COMPONENTS",
                      "message": "Gradebook has no assessment components"})
    for comp in full["components"]:
        if not comp["items"]:
            issues.append({"level": "warning", "code": "EMPTY_COMPONENT",
                          "message": f"Component '{comp['name']}' has no assessment items", "component_id": comp["id"]})
    if full["statistics"]["incomplete"] > 0:
        issues.append({"level": "warning", "code": "INCOMPLETE_LEARNERS",
                      "message": f"{full['statistics']['incomplete']} learner(s) have missing or incomplete scores"})
    return {"valid": not any(i["level"] == "error" for i in issues), "issues": issues}


@app.post("/api/gradebooks/{gradebook_id}/submit")
def submit_gradebook_endpoint(
    gradebook_id: int,
    payload: GradebookWorkflowPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("teacher")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    try:
        grading_service.submit_gradebook(
            db, gradebook_id, user, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"submitted": True, "status": "Submitted"}


@app.post("/api/gradebooks/{gradebook_id}/finalize")
def finalize_gradebook_new_endpoint(
    gradebook_id: int,
    payload: GradebookWorkflowPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    try:
        grading_service.finalize_gradebook(
            db, gradebook_id, user, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"finalized": True, "status": "Finalized"}


@app.post("/api/gradebooks/{gradebook_id}/lock")
def lock_gradebook_endpoint(
    gradebook_id: int,
    payload: GradebookWorkflowPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "records_officer")),
):
    try:
        grading_service.lock_gradebook(db, gradebook_id, user, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"locked": True, "status": "Locked"}


@app.post("/api/gradebooks/{gradebook_id}/reopen")
def reopen_gradebook_new_endpoint(
    gradebook_id: int,
    payload: GradebookWorkflowPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "records_officer")),
):
    try:
        grading_service.reopen_gradebook(
            db, gradebook_id, user, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"reopened": True, "status": "Draft"}


@app.get("/api/gradebooks/{gradebook_id}/audit")
def gradebook_audit_new_endpoint(
    gradebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    entries = db.scalars(
        select(GradebookAuditEntry)
        .where(GradebookAuditEntry.gradebook_id == gradebook_id)
        .order_by(GradebookAuditEntry.created_at.desc())
        .limit(200)
    ).all()
    return [{
        "id": e.id,
        "action": e.action,
        "person_name": e.person_name,
        "assessment_label": e.assessment_label,
        "component_name": e.component_name,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "reason": e.reason,
        "actor_name": e.actor_name,
        "actor_role": e.actor_role,
        "created_at": e.created_at,
    } for e in entries]


@app.post("/api/gradebooks/{gradebook_id}/adjustments")
def create_adjustment_endpoint(
    gradebook_id: int,
    payload: GradeAdjustmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    try:
        req = grading_service.create_adjustment_request(
            db, gradebook_id, user,
            person_id=payload.person_id,
            assessment_item_id=payload.assessment_item_id,
            new_score=payload.new_score,
            new_status=payload.new_status,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": req.id, "status": req.status}


@app.get("/api/gradebooks/{gradebook_id}/adjustments")
def list_adjustments_endpoint(
    gradebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook not found")
    reqs = db.scalars(
        select(GradeAdjustmentRequest)
        .where(GradeAdjustmentRequest.gradebook_id == gradebook_id)
        .order_by(GradeAdjustmentRequest.created_at.desc())
    ).all()
    return [{
        "id": r.id,
        "person_id": r.person_id,
        "person_name": r.person.full_name if r.person else None,
        "assessment_item_id": r.assessment_item_id,
        "assessment_label": r.assessment_item.label if r.assessment_item else None,
        "old_score": r.old_score,
        "old_status": r.old_status,
        "new_score": r.new_score,
        "new_status": r.new_status,
        "reason": r.reason,
        "requested_by_name": r.requested_by_name,
        "status": r.status,
        "reviewed_by_name": r.reviewed_by_name,
        "review_note": r.review_note,
        "reviewed_at": r.reviewed_at,
        "created_at": r.created_at,
    } for r in reqs]


@app.get("/api/admin/grade-adjustments")
def list_global_adjustments_endpoint(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "records_officer")),
):
    reqs = db.scalars(
        select(GradeAdjustmentRequest)
        .options(
            joinedload(GradeAdjustmentRequest.gradebook),
            joinedload(GradeAdjustmentRequest.person),
            joinedload(GradeAdjustmentRequest.assessment_item)
        )
        .order_by(GradeAdjustmentRequest.created_at.desc())
    ).all()
    return [{
        "id": r.id,
        "gradebook_id": r.gradebook_id,
        "grade_name": r.gradebook.grade_name if r.gradebook else None,
        "section_name": r.gradebook.section_name if r.gradebook else None,
        "subject_name": r.gradebook.subject_name if r.gradebook else None,
        "person_id": r.person_id,
        "person_name": r.person.full_name if r.person else None,
        "assessment_item_id": r.assessment_item_id,
        "assessment_label": r.assessment_item.label if r.assessment_item else None,
        "old_score": r.old_score,
        "old_status": r.old_status,
        "new_score": r.new_score,
        "new_status": r.new_status,
        "reason": r.reason,
        "requested_by_name": r.requested_by_name,
        "status": r.status,
        "reviewed_by_name": r.reviewed_by_name,
        "review_note": r.review_note,
        "reviewed_at": r.reviewed_at,
        "created_at": r.created_at,
    } for r in reqs]


@app.put("/api/adjustment-requests/{request_id}")
def review_adjustment_endpoint(
    request_id: int,
    payload: GradeAdjustmentReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "records_officer")),
):
    try:
        req = grading_service.review_adjustment_request(
            db, request_id, user, payload.status, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": req.id, "status": req.status}


@app.delete("/api/adjustment-requests/{request_id}")
def delete_adjustment_endpoint(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    try:
        grading_service.delete_adjustment_request(db, request_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "deleted"}


@app.get("/api/gradebooks/{gradebook_id}/report.xlsx")
def gradebook_report_xlsx_new(
    gradebook_id: int,
    region: str = "",
    division: str = "",
    school_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook was not found")
    path = generate_gradebook_report_xlsx(db, book.id, region=region, division=division, school_id=school_id)
    report = register_report(db, path, "Grading Summary", {
        "gradebook_id": book.id, "grade": book.grade_name, "section": book.section_name,
        "school_year": book.school_year_name, "quarter": book.quarter, "subject": book.subject_name,
    }, user)
    return FileResponse(report.file_path, filename=report.filename,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/gradebooks/{gradebook_id}/report/print", response_class=HTMLResponse)
def gradebook_report_print_new(
    gradebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "teacher", "records_officer")),
):
    book = db.get(Gradebook, gradebook_id)
    if not book:
        raise HTTPException(status_code=404, detail="Gradebook was not found")
    return HTMLResponse(gradebook_report_html(db, book.id))


@app.get("/api/dashboard")
def dashboard(day: date = Query(default_factory=date.today), db: Session = Depends(get_db),
              _: User = Depends(require_roles("admin"))) -> dict:
    rows = list_rows(db, day)
    events = db.scalars(select(AttendanceEvent).where(AttendanceEvent.event_date == day).order_by(
        AttendanceEvent.created_at.desc()).limit(20)).all()
    return {
        "rows": rows,
        "events": [{"id": item.id, "person": item.person.full_name, "role": item.person.role, "time": item.event_time,
                    "direction": item.direction, "status": item.status} for item in events],
        "sms": {status: db.scalar(select(func.count(SmsOutbox.id)).where(SmsOutbox.status == status)) or 0
                for status in ("queued", "accepted", "processed", "sent", "delivered", "failed", "exhausted", "cancelled")},
    }


@app.get("/api/interventions")
def interventions(days: int = 90, threshold: int = 5, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("admin", "teacher"))) -> list[dict]:
    if not 1 <= days <= 366 or not 1 <= threshold <= 100:
        raise HTTPException(
            status_code=422, detail="Intervention range is invalid")
    students = db.scalars(select(Person).where(Person.active.is_(
        True), Person.role == "Student").order_by(Person.full_name)).all()
    if user.role == "teacher":
        allowed = {(item.grade_level.name, item.name)
                   for item in adviser_sections(db, user)}
        students = [person for person in students if (
            person.grade, person.section) in allowed]
    end = date.today()
    start = end - timedelta(days=days - 1)
    absence_dates: dict[int, list[date]] = {
        person.id: [] for person in students}
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            for row in list_rows(db, cursor):
                if row["person_id"] in absence_dates and row["status"] == "Absent":
                    absence_dates[row["person_id"]].append(cursor)
        cursor += timedelta(days=1)
    result = []
    for person in students:
        absent_dates = absence_dates.get(person.id, [])
        if len(absent_dates) < threshold:
            continue
        logs = db.scalars(select(Intervention).where(
            Intervention.person_id == person.id).order_by(Intervention.created_at.desc())).all()
        result.append({"person": person_json(person, db), "absence_count": len(absent_dates),
                       "last_absence": max(absent_dates), "logs": [{"id": item.id, "intervention_type": item.intervention_type,
                                                                    "note": item.note, "actor_name": item.actor_name, "created_at": item.created_at} for item in logs]})
    return result


@app.post("/api/interventions")
def add_intervention(payload: InterventionPayload, db: Session = Depends(get_db),
                     user: User = Depends(require_roles("admin", "teacher"))) -> dict:
    person = db.get(Person, payload.person_id)
    if not person or person.role != "Student":
        raise HTTPException(status_code=404, detail="Student was not found")
    if user.role == "teacher":
        ensure_adviser_access(
            db, user, person.grade or "", person.section or "")
    import uuid
    item = Intervention(id=str(uuid.uuid4()), person_id=person.id, intervention_type=payload.intervention_type.strip(),
                        note=payload.note.strip(), actor_user_id=user.id, actor_name=user.full_name)
    db.add(item)
    db.commit()
    return {"id": item.id, "created_at": item.created_at}
