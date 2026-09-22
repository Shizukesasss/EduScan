"""Normalized grading models for the EduScan Gradebook Management System.

These models replace the flat GradeComponent/GradeScore/GradebookState tables
with a proper hierarchy: GradingPolicy → Gradebook → GradebookComponent →
AssessmentItem → StudentScore, plus audit and adjustment workflows.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class GradingPolicy(Base):
    """Administrator-configured grading policy that governs how grades are
    calculated for a given grade-level category, subject category, and school year.

    The ``component_definitions_json`` field stores the approved assessment
    component structure (e.g. Written Works 30%, Performance Tasks 50%,
    Quarterly Assessment 20%) as a JSON array.

    The ``transmutation_table_json`` field stores the piecewise transmutation
    lookup as a JSON array of ``{"min": float, "max": float, "value": int}``
    entries.  When ``null``, no transmutation is applied and the initial grade
    is used directly.
    """
    __tablename__ = "grading_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    version: Mapped[str] = mapped_column(String(30), default="1.0")
    description: Mapped[str] = mapped_column(Text, default="")
    school_year: Mapped[str] = mapped_column(String(30), index=True)
    grade_levels: Mapped[str] = mapped_column(Text, default="")  # comma-separated, e.g. "7,8,9,10"
    subject_category: Mapped[str] = mapped_column(String(80), default="General")  # e.g. General, MAPEH, TLE, SHS-Core
    component_definitions_json: Mapped[str] = mapped_column(Text, default="[]")
    transmutation_table_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    rounding_decimal_places: Mapped[int] = mapped_column(Integer, default=2)
    rounding_final_decimal_places: Mapped[int] = mapped_column(Integer, default=0)
    rounding_method: Mapped[str] = mapped_column(String(30), default="half_up")  # half_up, floor, ceiling
    passing_grade: Mapped[int] = mapped_column(Integer, default=75)
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)  # Active, Archived
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(180), default="System")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Gradebook(Base):
    """A single gradebook for one teacher's subject-section-quarter combination.

    Status lifecycle: Draft → Submitted → Finalized → Locked.
    Reopening (by admin/records_officer) returns to Draft with a reason.
    """
    __tablename__ = "gradebooks"
    __table_args__ = (
        UniqueConstraint(
            "school_year_id", "grading_period_id", "grade_level_id",
            "section_id", "subject_id",
            name="uq_gradebook_context",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # Foreign keys to academic structure
    school_year_id: Mapped[int] = mapped_column(ForeignKey("school_years.id"), index=True)
    grading_period_id: Mapped[int] = mapped_column(ForeignKey("grading_periods.id"), index=True)
    grade_level_id: Mapped[int] = mapped_column(ForeignKey("grade_levels.id"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("school_sections.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    grading_policy_id: Mapped[int | None] = mapped_column(ForeignKey("grading_policies.id"), nullable=True, index=True)
    teacher_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # Denormalized display fields for convenience
    school_year_name: Mapped[str] = mapped_column(String(30), default="")
    quarter: Mapped[int] = mapped_column(Integer, default=1)
    grade_name: Mapped[str] = mapped_column(String(30), default="")
    section_name: Mapped[str] = mapped_column(String(80), default="")
    subject_name: Mapped[str] = mapped_column(String(120), default="")
    teacher_name: Mapped[str] = mapped_column(String(180), default="")
    # Legacy class_key for backward compatibility
    class_key: Mapped[str | None] = mapped_column(String(240), unique=True, nullable=True, index=True)
    # Workflow
    status: Mapped[str] = mapped_column(String(30), default="Draft", index=True)
    passing_grade: Mapped[int] = mapped_column(Integer, default=75)
    # Finalization tracking
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_by_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    finalized_by_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    locked_by_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopened_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reopened_by_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Relationships
    school_year = relationship("SchoolYear", foreign_keys=[school_year_id])
    grading_period = relationship("GradingPeriod", foreign_keys=[grading_period_id])
    grade_level = relationship("GradeLevel", foreign_keys=[grade_level_id])
    section = relationship("SchoolSection", foreign_keys=[section_id])
    subject = relationship("Subject", foreign_keys=[subject_id])
    grading_policy = relationship("GradingPolicy", foreign_keys=[grading_policy_id])
    components: Mapped[list["GradebookComponent"]] = relationship(
        back_populates="gradebook", cascade="all, delete-orphan",
        order_by="GradebookComponent.sequence",
    )


class GradebookComponent(Base):
    """An assessment component (e.g. Written Works, Performance Tasks) belonging
    to a Gradebook.  Weight is the percentage weight for this component.
    """
    __tablename__ = "gradebook_components"
    id: Mapped[int] = mapped_column(primary_key=True)
    gradebook_id: Mapped[int] = mapped_column(ForeignKey("gradebooks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    component_type: Mapped[str] = mapped_column(String(60), default="Written Work")
    weight: Mapped[float] = mapped_column(Float)
    sequence: Mapped[int] = mapped_column(Integer, default=0, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # Relationships
    gradebook: Mapped["Gradebook"] = relationship(back_populates="components")
    items: Mapped[list["AssessmentItem"]] = relationship(
        back_populates="component", cascade="all, delete-orphan",
        order_by="AssessmentItem.sequence",
    )


class AssessmentItem(Base):
    """An individual assessment activity (e.g. Quiz 1, Written Activity 2)
    under a GradebookComponent.
    """
    __tablename__ = "assessment_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey("gradebook_components.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    max_score: Mapped[float] = mapped_column(Float)
    assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # Relationships
    component: Mapped["GradebookComponent"] = relationship(back_populates="items")
    scores: Mapped[list["StudentScore"]] = relationship(
        back_populates="assessment_item", cascade="all, delete-orphan",
    )


# Valid score statuses
SCORE_STATUSES = {"Scored", "Missing", "Absent", "Excused", "Incomplete", "Not Applicable"}


class StudentScore(Base):
    """One score per student per assessment item.

    ``score`` is nullable: a None score with status 'Scored' is invalid and
    must be rejected.  Non-Scored statuses store score=None.  An explicit zero
    is stored as score=0.0 with status='Scored'.
    """
    __tablename__ = "student_scores"
    __table_args__ = (
        UniqueConstraint("person_id", "assessment_item_id", name="uq_student_assessment_score"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    assessment_item_id: Mapped[int] = mapped_column(ForeignKey("assessment_items.id", ondelete="CASCADE"), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Missing", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Relationships
    person = relationship("Person", foreign_keys=[person_id])
    assessment_item: Mapped["AssessmentItem"] = relationship(back_populates="scores")


class GradeAdjustmentRequest(Base):
    """A request to modify a score after the gradebook has been finalized.

    Status lifecycle: Pending → Approved / Rejected.
    On approval, the system applies the new score and creates an audit entry.
    """
    __tablename__ = "grade_adjustment_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    gradebook_id: Mapped[int] = mapped_column(ForeignKey("gradebooks.id"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), index=True)
    assessment_item_id: Mapped[int] = mapped_column(ForeignKey("assessment_items.id", ondelete="CASCADE"), index=True)
    old_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    old_status: Mapped[str] = mapped_column(String(30), default="Scored")
    new_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), default="Scored")
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requested_by_name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(30), default="Pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_by_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # Relationships
    gradebook = relationship("Gradebook", foreign_keys=[gradebook_id])
    person = relationship("Person", foreign_keys=[person_id])
    assessment_item = relationship("AssessmentItem", foreign_keys=[assessment_item_id])


class GradebookAuditEntry(Base):
    """Fine-grained audit trail for gradebook changes.

    Records individual field-level changes rather than full JSON snapshots,
    making it easier to display "Quiz 2 score changed from 15 to 18" in the UI.
    """
    __tablename__ = "gradebook_audit_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    gradebook_id: Mapped[int] = mapped_column(ForeignKey("gradebooks.id"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"), nullable=True, index=True)
    person_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    assessment_item_id: Mapped[int | None] = mapped_column(ForeignKey("assessment_items.id", ondelete="SET NULL"), nullable=True)
    assessment_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    component_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(180))
    actor_role: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # Relationships
    gradebook = relationship("Gradebook", foreign_keys=[gradebook_id])


# Import models so all referenced tables (SchoolYear, User, etc.) are in registry
from . import models as _models  # noqa: F401, E402

