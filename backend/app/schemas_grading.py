"""Pydantic schemas for the EduScan Grading Management API."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Grading Policy
# ---------------------------------------------------------------------------

class ComponentDefinition(BaseModel):
    """A single component definition within a grading policy."""
    name: str = Field(min_length=1, max_length=120)
    component_type: str = Field(default="Written Work", max_length=60)
    weight: float = Field(ge=0, le=100)
    description: str = ""


class GradingPolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = ""
    school_year: str = Field(min_length=4, max_length=30)
    grade_levels: str = Field(default="", max_length=200)
    subject_category: str = Field(default="General", max_length=80)
    component_definitions: list[ComponentDefinition] = Field(min_length=1)
    transmutation_table: list[dict] | None = None
    rounding_decimal_places: int = Field(default=2, ge=0, le=6)
    rounding_final_decimal_places: int = Field(default=0, ge=0, le=6)
    rounding_method: str = "half_up"
    passing_grade: int = Field(default=75, ge=60, le=100)

    @field_validator("rounding_method")
    @classmethod
    def valid_rounding_method(cls, value: str) -> str:
        if value not in {"half_up", "floor", "ceiling"}:
            raise ValueError("Rounding method must be half_up, floor, or ceiling")
        return value

    @model_validator(mode="after")
    def validate_weights(self):
        total = sum(c.weight for c in self.component_definitions)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Component weights total {total:.2f}% but must be exactly 100%")
        return self


class GradingPolicyUpdate(GradingPolicyCreate):
    status: str = "Active"

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"Active", "Archived"}:
            raise ValueError("Policy status must be Active or Archived")
        return value


class GradingPolicyResponse(BaseModel):
    id: int
    name: str
    version: str
    description: str
    school_year: str
    grade_levels: str
    subject_category: str
    component_definitions: list[dict]
    transmutation_table: list[dict] | None
    rounding_decimal_places: int
    rounding_final_decimal_places: int
    rounding_method: str
    passing_grade: int
    status: str
    effective_date: date | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Assessment Items
# ---------------------------------------------------------------------------

class AssessmentItemPayload(BaseModel):
    id: int | None = None  # None = new
    label: str = Field(min_length=1, max_length=120)
    max_score: float = Field(gt=0, le=1_000_000)
    assessment_date: date | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Gradebook Components
# ---------------------------------------------------------------------------

class GradebookComponentPayload(BaseModel):
    id: int | None = None  # None = new
    name: str = Field(min_length=1, max_length=120)
    component_type: str = Field(default="Written Work", max_length=60)
    weight: float = Field(ge=0, le=100)
    description: str = ""
    items: list[AssessmentItemPayload] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Gradebook
# ---------------------------------------------------------------------------

class GradebookCreate(BaseModel):
    school_year_id: int
    grading_period_id: int
    grade_level_id: int
    section_id: int
    subject_id: int
    grading_policy_id: int | None = None


class GradebookComponentsUpdate(BaseModel):
    """Payload for updating gradebook components and their assessment items."""
    components: list[GradebookComponentPayload] = Field(min_length=1, max_length=50)
    change_reason: str = Field(default="Updated assessment components", min_length=8, max_length=1000)

    @model_validator(mode="after")
    def validate_weights(self):
        total = sum(c.weight for c in self.components)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"Component weights total {total:.2f}% but must be exactly 100%")
        return self


# ---------------------------------------------------------------------------
# Score Entry
# ---------------------------------------------------------------------------

VALID_SCORE_STATUSES = {"Scored", "Missing", "Absent", "Excused", "Incomplete", "Not Applicable"}


class ScoreEntry(BaseModel):
    """A single score entry for one student on one assessment item."""
    assessment_item_id: int
    score: float | None = None
    status: str = "Scored"
    reason: str | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in VALID_SCORE_STATUSES:
            raise ValueError(f"Score status must be one of: {', '.join(sorted(VALID_SCORE_STATUSES))}")
        return value

    @model_validator(mode="after")
    def score_required_when_scored(self):
        if self.status == "Scored" and self.score is None:
            raise ValueError("A score value is required when status is 'Scored'")
        return self


class GradebookScoresUpdate(BaseModel):
    """Payload for saving scores for one or more students."""
    scores: dict[str, list[ScoreEntry]]  # {person_id_str: [ScoreEntry, ...]}
    change_reason: str = Field(default="Updated student scores", min_length=8, max_length=1000)


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class GradebookWorkflowPayload(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)


# ---------------------------------------------------------------------------
# Grade Adjustment
# ---------------------------------------------------------------------------

class GradeAdjustmentCreate(BaseModel):
    person_id: int
    assessment_item_id: int
    new_score: float | None = None
    new_status: str = "Scored"
    reason: str = Field(min_length=8, max_length=2000)

    @field_validator("new_status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in VALID_SCORE_STATUSES:
            raise ValueError(f"Score status must be one of: {', '.join(sorted(VALID_SCORE_STATUSES))}")
        return value


class GradeCriteriaWeight(BaseModel):
    component_id: int = Field(gt=0)
    weight: float = Field(ge=0, le=100, allow_inf_nan=False)


class GradeCriteriaAdjustmentCreate(BaseModel):
    components: list[GradeCriteriaWeight] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=8, max_length=2000)


class GradeAdjustmentReview(BaseModel):
    status: str
    note: str = Field(min_length=5, max_length=2000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"Approved", "Rejected"}:
            raise ValueError("Adjustment review status must be Approved or Rejected")
        return value


class GradeAdjustmentNotificationsRead(BaseModel):
    request_ids: list[int] = Field(min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

class GradebookSummaryResponse(BaseModel):
    id: int
    school_year_name: str
    quarter: int
    grade_name: str
    section_name: str
    subject_name: str
    teacher_name: str
    status: str
    policy_name: str | None = None
    created_at: datetime


class CalculationBreakdownResponse(BaseModel):
    student_name: str
    policy_name: str
    passing_grade: int
    components: list[dict]
    initial_grade: float | None
    reported_grade: int | None
    status: str
    complete: bool


class ValidationIssue(BaseModel):
    level: str
    code: str
    message: str
    component_id: int | None = None
    person_id: int | None = None


class GradebookValidationResponse(BaseModel):
    valid: bool
    issues: list[ValidationIssue]
