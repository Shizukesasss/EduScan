from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    password_changed_at: Mapped[datetime |
                                None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class Person(Base):
    __tablename__ = "persons"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(
        String(80), unique=True, index=True)
    lrn: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(180), index=True)
    surname: Mapped[str] = mapped_column(String(80), default="")
    first_name: Mapped[str] = mapped_column(String(80), default="")
    middle_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sex: Mapped[str] = mapped_column(String(10))
    role: Mapped[str] = mapped_column(String(40), index=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    section: Mapped[str | None] = mapped_column(String(80), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True)
    enrollment_status: Mapped[str] = mapped_column(
        String(30), default="Regular")
    enrollment_start_date: Mapped[date |
                                  None] = mapped_column(Date, nullable=True)
    enrollment_end_date: Mapped[date |
                                None] = mapped_column(Date, nullable=True)
    transfer_school: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    biometric_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    samples: Mapped[list["BiometricSample"]] = relationship(
        back_populates="person", cascade="all, delete-orphan")


class ClassSchedule(Base):
    __tablename__ = "class_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    grade: Mapped[str] = mapped_column(String(20), index=True)
    section: Mapped[str] = mapped_column(String(80), index=True)
    subject: Mapped[str] = mapped_column(String(120))
    teacher_name: Mapped[str] = mapped_column(String(180))
    weekdays: Mapped[str] = mapped_column(String(40), default="0,1,2,3,4")
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    late_grace_minutes: Mapped[int] = mapped_column(Integer, default=15)
    absence_cutoff: Mapped[time | None] = mapped_column(Time, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PersonnelSchedule(Base):
    __tablename__ = "personnel_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    assignment: Mapped[str | None] = mapped_column(
        String(180), nullable=True, index=True)
    weekdays: Mapped[str] = mapped_column(String(40), default="0,1,2,3,4")
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    late_grace_minutes: Mapped[int] = mapped_column(Integer, default=15)
    absence_cutoff: Mapped[time | None] = mapped_column(Time, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class SchoolYear(Base):
    __tablename__ = "school_years"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class GradingPeriod(Base):
    __tablename__ = "grading_periods"
    __table_args__ = (UniqueConstraint("school_year_id",
                      "quarter", name="uq_school_year_quarter"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_year_id: Mapped[int] = mapped_column(
        ForeignKey("school_years.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    quarter: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    school_year: Mapped[SchoolYear] = relationship()


class GradeLevel(Base):
    __tablename__ = "grade_levels"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SchoolSection(Base):
    __tablename__ = "school_sections"
    __table_args__ = (UniqueConstraint("grade_level_id",
                      "name", name="uq_grade_level_section"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    grade_level_id: Mapped[int] = mapped_column(
        ForeignKey("grade_levels.id"), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    adviser_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    adviser_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    grade_level: Mapped[GradeLevel] = relationship()


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20), default="JHS")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CalendarException(Base):
    __tablename__ = "calendar_exceptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    absence_cutoff: Mapped[time | None] = mapped_column(Time, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class ExcusedAbsence(Base):
    __tablename__ = "excused_absences"
    __table_args__ = (UniqueConstraint(
        "person_id", "event_date", name="uq_person_excused_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    person: Mapped[Person] = relationship()


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_time: Mapped[time] = mapped_column(Time)
    direction: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    recognition_distance: Mapped[float |
                                 None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="Gate camera")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    person: Mapped[Person] = relationship()


class AttendanceCorrection(Base):
    __tablename__ = "attendance_corrections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30))
    time_in: Mapped[time | None] = mapped_column(Time, nullable=True)
    time_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    before_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    person: Mapped[Person] = relationship()


class AttendanceResetAudit(Base):
    __tablename__ = "attendance_reset_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    superseded_event_count: Mapped[int] = mapped_column(Integer, default=0)
    superseded_correction_count: Mapped[int] = mapped_column(
        Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class BiometricSample(Base):
    __tablename__ = "biometric_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    encrypted_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    quality_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    person: Mapped[Person] = relationship(back_populates="samples")


class BiometricModel(Base):
    __tablename__ = "biometric_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    file_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    threshold: Mapped[float] = mapped_column(Float)
    person_count: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class BiometricAuditEvent(Base):
    __tablename__ = "biometric_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    person_external_id: Mapped[str] = mapped_column(String(80))
    person_name: Mapped[str] = mapped_column(String(180))
    action: Mapped[str] = mapped_column(String(30), index=True)
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(
        String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    person: Mapped[Person] = relationship()


class SmsOutbox(Base):
    __tablename__ = "sms_outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160), unique=True, nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    recipient: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    gateway_message_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    exhausted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    gateway_status_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    person: Mapped[Person | None] = relationship()


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    encrypted_value: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GradeComponent(Base):
    __tablename__ = "grade_components"
    __table_args__ = (UniqueConstraint("class_key", "category",
                      "sequence", name="uq_grade_component_order"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    class_key: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(120))
    weight: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=100)
    sequence: Mapped[int] = mapped_column(Integer)


class GradeScore(Base):
    __tablename__ = "grade_scores"
    __table_args__ = (UniqueConstraint(
        "person_id", "component_id", name="uq_person_component_score"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("grade_components.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(30), default="Scored", index=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GradeChangeAudit(Base):
    __tablename__ = "grade_change_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    class_key: Mapped[str] = mapped_column(String(240), index=True)
    school_year: Mapped[str] = mapped_column(String(30))
    quarter: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class GradebookState(Base):
    __tablename__ = "gradebook_states"
    class_key: Mapped[str] = mapped_column(String(240), primary_key=True)
    school_year: Mapped[str] = mapped_column(String(30), index=True)
    quarter: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(120), index=True)
    grade: Mapped[str] = mapped_column(String(30), index=True)
    section: Mapped[str] = mapped_column(String(80), index=True)
    passing_grade: Mapped[int] = mapped_column(Integer, default=75)
    status: Mapped[str] = mapped_column(
        String(30), default="Draft", index=True)
    finalized_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    finalized_by_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    reopened_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    reopened_by_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemAuditEvent(Base):
    __tablename__ = "system_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String(500))
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class GeneratedReport(Base):
    __tablename__ = "generated_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(60), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(600))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    parameters_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30), default="Generated", index=True)
    generated_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True)
    generated_by_name: Mapped[str] = mapped_column(String(180))
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    reviewed_by_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class RecognitionReview(Base):
    __tablename__ = "recognition_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    face_signature: Mapped[str] = mapped_column(String(64), index=True)
    candidate_person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id"), nullable=True, index=True)
    candidate_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    review_type: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="Open", index=True)
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    resolved_by_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class LegalHold(Base):
    __tablename__ = "legal_holds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(80), index=True)
    subject_reference: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text)
    authority_reference: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    placed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    placed_by_name: Mapped[str] = mapped_column(String(180))
    released_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    released_by_name: Mapped[str | None] = mapped_column(
        String(180), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class RetentionExecution(Base):
    __tablename__ = "retention_executions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_snapshot_json: Mapped[str] = mapped_column(Text)
    preview_json: Mapped[str] = mapped_column(Text)
    removed_counts_json: Mapped[str] = mapped_column(Text)
    authorization_reference: Mapped[str] = mapped_column(String(300))
    certificate_reference: Mapped[str] = mapped_column(
        String(120), unique=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database_backend: Mapped[str] = mapped_column(String(30))
    encryption_key_fingerprint: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(
        String(80), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(600), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(
        String(180), default="EduScan scheduler")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class RosterImportAudit(Base):
    __tablename__ = "roster_import_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    approved_reference: Mapped[str] = mapped_column(String(300))
    inserted_count: Mapped[int] = mapped_column(Integer)
    updated_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class RecordDisposalAudit(Base):
    __tablename__ = "record_disposal_audits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_reference_hash: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text)
    authorization_reference: Mapped[str] = mapped_column(String(300))
    removed_counts_json: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)


class Intervention(Base):
    __tablename__ = "interventions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id"), index=True)
    intervention_type: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True)
    person: Mapped[Person] = relationship()


# Import new grading models so they are registered with SQLAlchemy metadata.
# Placed here to avoid circular imports while ensuring create_all picks them up.
from .models_grading import (  # noqa: E402, F401
    AssessmentItem, Gradebook, GradebookAuditEntry, GradebookComponent,
    GradeAdjustmentRequest, GradingPolicy, StudentScore,
)
