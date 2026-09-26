from __future__ import annotations

from datetime import date, datetime, time

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

USER_ROLES = {"admin", "teacher", "scanner",
              "records_officer", "privacy_officer", "ict"}


def strong_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if not re.search(r"[A-Z]", value) or not re.search(r"[a-z]", value):
        raise ValueError(
            "Password must contain uppercase and lowercase letters")
    if not re.search(r"\d", value) or not re.search(r"[^A-Za-z0-9]", value):
        raise ValueError("Password must contain a number and a symbol")
    return value


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    must_change_password: bool = False


class UserPublic(BaseModel):
    id: int
    username: str
    role: str
    full_name: str
    must_change_password: bool
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80,
                          pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=200)
    role: str
    full_name: str = Field(min_length=3, max_length=160)
    active: bool = True

    _strong_password = field_validator("password")(strong_password)

    @field_validator("role")
    @classmethod
    def valid_user_role(cls, value: str) -> str:
        if value not in USER_ROLES:
            raise ValueError(
                f"Role must be one of: {', '.join(sorted(USER_ROLES))}")
        return value


class UserUpdate(BaseModel):
    role: str
    full_name: str = Field(min_length=3, max_length=160)
    active: bool = True
    new_password: str | None = Field(
        default=None, min_length=12, max_length=200)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str | None) -> str | None:
        return strong_password(value) if value is not None else None

    @field_validator("role")
    @classmethod
    def valid_user_role(cls, value: str) -> str:
        if value not in USER_ROLES:
            raise ValueError(
                f"Role must be one of: {', '.join(sorted(USER_ROLES))}")
        return value


class PasswordChangePayload(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)

    _strong_password = field_validator("new_password")(strong_password)


class PersonCreate(BaseModel):
    external_id: str = Field(min_length=2, max_length=80)
    lrn: str | None = Field(default=None, max_length=20)
    surname: str = Field(default="", max_length=80)
    first_name: str = Field(min_length=1, max_length=80)
    middle_name: str | None = Field(default=None, max_length=80)
    name_extension: str | None = Field(default=None, max_length=20)
    sex: str
    role: str
    grade: str | None = None
    section: str | None = None
    guardian_phone: str | None = None
    enrollment_status: str = "Regular"
    enrollment_start_date: date | None = None
    enrollment_end_date: date | None = None
    transfer_school: str | None = Field(default=None, max_length=180)
    biometric_consent: bool = False

    @model_validator(mode="before")
    @classmethod
    def clean_na_values(cls, values: dict) -> dict:
        for k, v in values.items():
            if isinstance(v, str) and v.strip().upper() in {"N/A", "NA", "NONE", "-"}:
                values[k] = "" if k in {"surname", "first_name"} else None
        return values

    @field_validator("sex")
    @classmethod
    def valid_sex(cls, value: str) -> str:
        if value not in {"Male", "Female"}:
            raise ValueError("Sex must be Male or Female for SF2 placement")
        return value

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        allowed = {"Student", "Faculty", "Non-teaching Personnel"}
        if value not in allowed:
            raise ValueError(
                f"Role must be one of: {', '.join(sorted(allowed))}")
        return value

    @field_validator("enrollment_status")
    @classmethod
    def valid_enrollment_status(cls, value: str) -> str:
        allowed = {"Regular", "Transferred In", "Transferred Out"}
        if value not in allowed:
            raise ValueError(
                f"Enrollment status must be one of: {', '.join(sorted(allowed))}")
        return value


class PersonPublic(PersonCreate):
    id: int
    active: bool
    sample_count: int = 0
    enrolled: bool = False
    model_config = ConfigDict(from_attributes=True)


class SchedulePayload(BaseModel):
    id: int | None = None
    grade: str
    section: str
    subject: str
    teacher_name: str
    weekdays: str = "0,1,2,3,4"
    start_time: time
    end_time: time
    late_grace_minutes: int = Field(default=15, ge=0, le=180)
    absence_cutoff: time | None = None
    active: bool = True

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: str) -> str:
        try:
            days = sorted({int(item.strip())
                          for item in value.split(",") if item.strip()})
        except ValueError as exc:
            raise ValueError("Weekdays must use numbers 0 through 6") from exc
        if not days or any(day < 0 or day > 6 for day in days):
            raise ValueError(
                "Select at least one weekday from Monday through Sunday")
        return ",".join(str(day) for day in days)

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError(
                "Class end time must be later than its start time")
        if self.absence_cutoff and not self.start_time <= self.absence_cutoff <= self.end_time:
            raise ValueError(
                "Class absence cutoff must be within the class time")
        return self


class PersonnelSchedulePayload(BaseModel):
    id: int | None = None
    role: str
    assignment: str | None = Field(default=None, max_length=180)
    weekdays: str = "0,1,2,3,4"
    start_time: time
    end_time: time
    late_grace_minutes: int = Field(default=15, ge=0, le=180)
    absence_cutoff: time | None = None
    active: bool = True

    @field_validator("role")
    @classmethod
    def valid_personnel_role(cls, value: str) -> str:
        if value not in {"Faculty", "Non-teaching Personnel"}:
            raise ValueError(
                "Personnel role must be Faculty or Non-teaching Personnel")
        return value

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: str) -> str:
        try:
            days = sorted({int(item.strip())
                          for item in value.split(",") if item.strip()})
        except ValueError as exc:
            raise ValueError("Weekdays must use numbers 0 through 6") from exc
        if not days or any(day < 0 or day > 6 for day in days):
            raise ValueError(
                "Select at least one weekday from Monday through Sunday")
        return ",".join(str(day) for day in days)

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.end_time <= self.start_time:
            raise ValueError("Duty end time must be later than its start time")
        if self.absence_cutoff and not self.start_time <= self.absence_cutoff <= self.end_time:
            raise ValueError(
                "Personnel absence cutoff must be within the duty time")
        return self


class AttendanceCorrectionPayload(BaseModel):
    person_id: int
    attendance_date: date
    status: str
    time_in: time | None = None
    time_out: time | None = None
    reason: str = Field(min_length=8, max_length=1000)


class AttendanceResetPayload(BaseModel):
    attendance_date: date
    reason: str = Field(min_length=12, max_length=2000)
    confirmation: str


class AttendanceRow(BaseModel):
    person_id: int
    external_id: str
    lrn: str | None
    full_name: str
    sex: str
    role: str
    grade: str | None
    section: str | None
    assignment: str | None
    time_in: time | None
    time_out: time | None
    status: str
    source: str
    correction_reason: str | None = None


class RecognitionResult(BaseModel):
    recognized: bool
    message: str
    person: dict | None = None
    distance: float | None = None
    quality_score: float | None = None
    attendance_event: dict | None = None


class BiometricChangeReason(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


class RecordDisposalPayload(BaseModel):
    reason: str = Field(min_length=12, max_length=2000)
    authorization_reference: str = Field(min_length=5, max_length=300)
    confirmation: str = Field(min_length=1, max_length=80)


class SmsSettingsPayload(BaseModel):
    enabled: bool
    gateway_url: str
    username: str
    password: str | None = None
    school_contact: str
    time_in_template: str
    time_out_template: str
    tardiness_template: str
    absence_template: str
    max_messages_per_30_minutes: int = Field(default=50, ge=1, le=500)


class AttendanceSettingsPayload(BaseModel):
    absence_cutoff: time
    duplicate_cooldown_seconds: int = Field(ge=5, le=3600)
    auto_close_enabled: bool = True


class CalendarExceptionPayload(BaseModel):
    event_date: date
    event_type: str
    reason: str = Field(min_length=5, max_length=1000)
    start_time: time | None = None
    end_time: time | None = None
    absence_cutoff: time | None = None

    @field_validator("event_type")
    @classmethod
    def valid_event_type(cls, value: str) -> str:
        if value not in {"Holiday", "Suspended", "Special Schedule"}:
            raise ValueError(
                "Event type must be Holiday, Suspended, or Special Schedule")
        return value


class ExcusedAbsencePayload(BaseModel):
    person_id: int
    event_date: date
    reason: str = Field(min_length=5, max_length=1000)


class CompliancePayload(BaseModel):
    school_approval_reference: str = ""
    parent_consent_process_reference: str = ""
    dpo_pia_reference: str = ""
    sdo_deped_clearance_reference: str = ""
    ai_registry_reference: str = ""
    records_schedule_reference: str = ""
    acceptable_use_policy_reference: str = ""
    breach_response_reference: str = ""


class GradeComponentPayload(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=120)
    weight: float = Field(ge=0, le=100)
    max_score: float = Field(gt=0, le=1_000_000)


class GradebookPayload(BaseModel):
    class_key: str
    school_year: str = Field(default="2026-2027", min_length=4, max_length=30)
    quarter: int = Field(default=1, ge=1, le=4)
    subject: str = Field(default="Unspecified", min_length=2, max_length=120)
    grade: str = Field(min_length=1, max_length=30)
    section: str = Field(min_length=1, max_length=80)
    change_reason: str = Field(
        default="Authorized gradebook save", min_length=8, max_length=1000)
    passing_grade: int = Field(default=75, ge=60, le=100)
    components: list[GradeComponentPayload] = Field(
        min_length=1, max_length=500)
    scores: dict[str, dict[str, float | str]]
    score_statuses: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("score_statuses")
    @classmethod
    def valid_score_statuses(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        allowed = {"Scored", "Missing", "Excused", "Incomplete"}
        for statuses in value.values():
            if any(status not in allowed for status in statuses.values()):
                raise ValueError(
                    f"Score status must be one of: {', '.join(sorted(allowed))}")
        return value


class GradebookActionPayload(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


class ReportReviewPayload(BaseModel):
    status: str
    note: str = Field(min_length=5, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"Reviewed", "Approved", "Rejected", "Superseded"}:
            raise ValueError(
                "Report status must be Reviewed, Approved, Rejected, or Superseded")
        return value


class RecognitionReviewResolutionPayload(BaseModel):
    status: str
    note: str = Field(min_length=8, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"Resolved", "Dismissed"}:
            raise ValueError(
                "Recognition review status must be Resolved or Dismissed")
        return value


class BiometricRuntimeSettingsPayload(BaseModel):
    threshold: float = Field(ge=20, le=150)
    liveness_enabled: bool = True
    liveness_window_seconds: int = Field(default=8, ge=3, le=30)
    review_failure_threshold: int = Field(default=4, ge=2, le=20)


class RetentionPolicyPayload(BaseModel):
    sms_days: int = Field(default=90, ge=1, le=3650)
    recognition_review_days: int = Field(default=30, ge=1, le=3650)
    biometric_staging_days: int = Field(default=30, ge=1, le=365)
    operational_log_days: int = Field(default=30, ge=1, le=3650)
    enabled: bool = False
    approved_schedule_reference: str = Field(default="", max_length=300)


class LegalHoldPayload(BaseModel):
    scope: str
    subject_reference: str | None = Field(default=None, max_length=160)
    reason: str = Field(min_length=8, max_length=2000)
    authority_reference: str = Field(min_length=3, max_length=300)

    @field_validator("scope")
    @classmethod
    def valid_scope(cls, value: str) -> str:
        if value not in {"All", "SMS", "Recognition Review", "Operational Logs", "Person"}:
            raise ValueError("Unsupported legal-hold scope")
        return value


class LegalHoldReleasePayload(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)


class RetentionExecutionPayload(BaseModel):
    authorization_reference: str = Field(min_length=3, max_length=300)
    confirmation: str


class BackupSchedulePayload(BaseModel):
    enabled: bool = False
    frequency: str = "Daily"
    run_time: time = time(18, 0)
    retention_count: int = Field(default=14, ge=1, le=365)
    destination: str = Field(default="", max_length=600)
    passphrase: str | None = Field(default=None, min_length=12, max_length=300)

    @field_validator("frequency")
    @classmethod
    def valid_frequency(cls, value: str) -> str:
        if value not in {"Daily", "Weekly"}:
            raise ValueError("Backup frequency must be Daily or Weekly")
        return value


class SchoolYearPayload(BaseModel):
    id: int | None = None
    name: str = Field(min_length=4, max_length=30)
    starts_on: date
    ends_on: date
    active: bool = True


class GradingPeriodPayload(BaseModel):
    id: int | None = None
    school_year_id: int
    name: str = Field(min_length=2, max_length=80)
    quarter: int = Field(ge=1, le=4)
    starts_on: date
    ends_on: date
    active: bool = True


class GradeLevelPayload(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=30)
    sequence: int = Field(default=0, ge=0, le=100)
    active: bool = True


class SectionPayload(BaseModel):
    id: int | None = None
    grade_level_id: int
    name: str = Field(min_length=1, max_length=80)
    adviser_user_id: int | None = None
    adviser_name: str | None = Field(default=None, max_length=180)
    active: bool = True


class SubjectPayload(BaseModel):
    id: int | None = None
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="JHS", max_length=20)
    active: bool = True


class InterventionPayload(BaseModel):
    person_id: int
    intervention_type: str = Field(min_length=3, max_length=80)
    note: str = Field(min_length=8, max_length=3000)
