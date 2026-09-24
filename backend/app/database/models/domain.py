import enum
import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.base import Base, TimestampedModel


class StrEnum(str, enum.Enum):
    pass


class SourceType(StrEnum):
    DAILY_REPORT = "daily_report"
    CONTRACTOR_SPREADSHEET = "contractor_spreadsheet"
    DISCIPLINE_SPREADSHEET = "discipline_spreadsheet"
    SITE_DIARY = "site_diary"
    MANUAL_ENTRY = "manual_entry"


class ImportStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportKind(StrEnum):
    SCHEDULE = "schedule"
    EVIDENCE = "evidence"


class ActivityStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    UNKNOWN = "unknown"


class MatchStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ObservationMatchOutcome(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NEEDS_REVIEW = "needs_review"
    NO_MATCH = "no_match"


class ReconciliationDecision(StrEnum):
    AUTO_ACCEPT = "auto_accept"
    PLANNER_REVIEW = "planner_review"
    REJECT = "reject"
    NO_DECISION = "no_decision"
    # Legacy states remain readable for existing records.
    AUTO_ACCEPTED = "auto_accepted"
    PLANNER_REVIEW_REQUIRED = "planner_review_required"
    PLANNER_ACCEPTED = "planner_accepted"
    PLANNER_REJECTED = "planner_rejected"


class DependencyType(StrEnum):
    FINISH_TO_START = "finish_to_start"
    START_TO_START = "start_to_start"
    FINISH_TO_FINISH = "finish_to_finish"
    START_TO_FINISH = "start_to_finish"


class ConflictType(StrEnum):
    STATUS = "status"
    PROGRESS = "progress"
    DATES = "dates"
    LOCATION = "location"
    DISCIPLINE = "discipline"
    DEPENDENCY = "dependency"


class ConflictSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResolutionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewDecision(StrEnum):
    PENDING = "pending"
    ACCEPT = "accept"
    REJECT = "reject"
    OVERRIDE = "override"


class AuditAction(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    REVIEWED = "reviewed"
    IMPORTED = "imported"


class DeviationType(StrEnum):
    EARLY = "EARLY"
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    EXTENDED = "EXTENDED"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class DelayCategory(StrEnum):
    MATERIAL = "MATERIAL"
    MANPOWER = "MANPOWER"
    EQUIPMENT = "EQUIPMENT"
    DESIGN = "DESIGN"
    APPROVAL = "APPROVAL"
    INSPECTION = "INSPECTION"
    SAFETY = "SAFETY"
    WEATHER = "WEATHER"
    ACCESS = "ACCESS"
    LOGISTICS = "LOGISTICS"
    CONTRACTOR = "CONTRACTOR"
    DEPENDENCY = "DEPENDENCY"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class Project(TimestampedModel, Base):
    __tablename__ = "projects"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    schedules: Mapped[list["Schedule"]] = relationship(back_populates="project")
    activities: Mapped[list["Activity"]] = relationship(back_populates="project")
    evidence_records: Mapped[list["Evidence"]] = relationship(back_populates="project")
    imported_sources: Mapped[list["ImportedSource"]] = relationship(back_populates="project")
    execution_records: Mapped[list["ExecutionRecord"]] = relationship(back_populates="project")


class ImportedSource(TimestampedModel, Base):
    __tablename__ = "imported_sources"
    __table_args__ = (
        Index("ix_imported_sources_project_status", "project_id", "status"),
        Index("ix_imported_sources_project_created", "project_id", "created_at"),
    )

    import_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    import_kind: Mapped[ImportKind] = mapped_column(
        Enum(ImportKind, name="import_kind"), nullable=False
    )
    source_type: Mapped[SourceType | None] = mapped_column(
        Enum(SourceType, name="source_type"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_reference: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status"), nullable=False, default=ImportStatus.PROCESSING
    )
    records_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="imported_sources")


class Schedule(TimestampedModel, Base):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    schedule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    source_file: Mapped[str] = mapped_column(String(1024), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped[Project] = relationship(back_populates="schedules")


class Activity(TimestampedModel, Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("project_id", "external_activity_id"),
        Index("ix_activities_project_discipline", "project_id", "discipline"),
        Index("ix_activities_project_status", "project_id", "status"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    external_activity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    discipline: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    parent_activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.activity_id"))
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ActivityStatus] = mapped_column(Enum(ActivityStatus, name="activity_status"), nullable=False, default=ActivityStatus.NOT_STARTED)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    actual_progress: Mapped[float | None] = mapped_column(Float)
    # Nullable and not queried in this phase; pgvector is prepared for future matching.
    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector().with_variant(JSON(), "sqlite"), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="activities")
    parent_activity: Mapped["Activity | None"] = relationship(remote_side="Activity.activity_id")
    matches: Mapped[list["ActivityMatch"]] = relationship(back_populates="activity")
    reconciliations: Mapped[list["Reconciliation"]] = relationship(back_populates="activity")
    conflicts: Mapped[list["EvidenceConflict"]] = relationship(back_populates="activity")
    reviews: Mapped[list["PlannerReview"]] = relationship(
        back_populates="activity", foreign_keys="PlannerReview.activity_id"
    )
    schedule_updates: Mapped[list["ScheduleUpdate"]] = relationship(back_populates="activity")
    execution_records: Mapped[list["ExecutionRecord"]] = relationship(back_populates="activity")
    predecessors: Mapped[list["ActivityDependency"]] = relationship(
        "ActivityDependency",
        foreign_keys="ActivityDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
    )
    successors: Mapped[list["ActivityDependency"]] = relationship(
        "ActivityDependency",
        foreign_keys="ActivityDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan",
    )


class ActivityDependency(TimestampedModel, Base):
    """Explicit predecessor-successor execution order dependency between activities."""

    __tablename__ = "activity_dependencies"
    __table_args__ = (
        UniqueConstraint("predecessor_id", "successor_id", name="uq_dependency_pair"),
        Index("ix_dependencies_successor", "successor_id"),
        Index("ix_dependencies_predecessor", "predecessor_id"),
    )

    dependency_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    predecessor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id", ondelete="CASCADE"), nullable=False)
    successor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id", ondelete="CASCADE"), nullable=False)
    dependency_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, name="dependency_type"), nullable=False, default=DependencyType.FINISH_TO_START
    )
    lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    predecessor: Mapped["Activity"] = relationship("Activity", foreign_keys=[predecessor_id], back_populates="successors")
    successor: Mapped["Activity"] = relationship("Activity", foreign_keys=[successor_id], back_populates="predecessors")
    project: Mapped["Project"] = relationship("Project")


class Evidence(TimestampedModel, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("raw_text IS NOT NULL OR raw_reference IS NOT NULL", name="evidence_raw_content"),
        CheckConstraint("extracted_progress IS NULL OR extracted_progress BETWEEN 0 AND 100", name="evidence_progress_range"),
        CheckConstraint("extraction_confidence IS NULL OR extraction_confidence BETWEEN 0 AND 1", name="evidence_confidence_range"),
        Index("ix_evidence_project_source_timestamp", "project_id", "source_timestamp"),
        Index("ix_evidence_project_source_type", "project_id", "source_type"),
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_reference: Mapped[str | None] = mapped_column(String(2048))
    extracted_activity_description: Mapped[str | None] = mapped_column(Text)
    extracted_status: Mapped[ActivityStatus | None] = mapped_column(Enum(ActivityStatus, name="extracted_activity_status"))
    extracted_start: Mapped[date | None] = mapped_column(Date)
    extracted_end: Mapped[date | None] = mapped_column(Date)
    extracted_progress: Mapped[float | None] = mapped_column(Float)
    discipline: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255))
    extraction_confidence: Mapped[float | None] = mapped_column(Float)

    project: Mapped[Project] = relationship(back_populates="evidence_records")
    matches: Mapped[list["ActivityMatch"]] = relationship(back_populates="evidence")
    interpretations: Mapped[list["EvidenceInterpretation"]] = relationship(back_populates="evidence")


class EvidenceInterpretation(Base):
    """A validated AI interpretation with an immutable copy of its source evidence."""

    __tablename__ = "evidence_interpretations"
    __table_args__ = (
        CheckConstraint("progress IS NULL OR progress BETWEEN 0 AND 100", name="interpretation_progress_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="interpretation_confidence_range"),
        Index("ix_evidence_interpretations_evidence_created", "evidence_id", "created_at"),
    )

    observation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.evidence_id"), nullable=False)
    # Keep a source snapshot on every observation.  The FK makes the originating
    # evidence navigable, while the snapshot preserves what the model actually saw.
    original_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    original_reference: Mapped[str | None] = mapped_column(String(2048))
    discipline: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255))
    contractor: Mapped[str | None] = mapped_column(String(255))
    activity_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus, name="activity_status"), nullable=False
    )
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    progress: Mapped[float | None] = mapped_column(Float)
    additional_context: Mapped[str | None] = mapped_column(Text)
    delay_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    constraint: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255))
    raw_provider_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence: Mapped[Evidence] = relationship(back_populates="interpretations")
    normalizations: Mapped[list["ActivityNormalization"]] = relationship(back_populates="interpretation")
    match_results: Mapped[list["ObservationMatchResult"]] = relationship(back_populates="interpretation")


class ActivityNormalization(Base):
    __tablename__ = "activity_normalizations"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="normalization_confidence_range"),
        Index("ix_activity_normalizations_observation_created", "observation_id", "created_at"),
    )

    normalization_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_interpretations.observation_id"), nullable=False
    )
    normalized_activity_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_discipline: Mapped[str | None] = mapped_column(String(100))
    normalized_location: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(255))
    raw_provider_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    interpretation: Mapped[EvidenceInterpretation] = relationship(back_populates="normalizations")


class ObservationMatchResult(Base):
    """An append-only matching decision, including ambiguous and unmatched observations."""

    __tablename__ = "observation_match_results"
    __table_args__ = (
        CheckConstraint("best_score IS NULL OR best_score BETWEEN 0 AND 1", name="match_result_best_score_range"),
        Index("ix_observation_match_results_outcome_created", "outcome", "created_at"),
        Index("ix_observation_match_results_observation_created", "observation_id", "created_at"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_interpretations.observation_id"), nullable=False)
    outcome: Mapped[ObservationMatchOutcome] = mapped_column(
        Enum(ObservationMatchOutcome, name="observation_match_outcome"), nullable=False
    )
    ambiguity_flag: Mapped[bool] = mapped_column(nullable=False, default=False)
    best_score: Mapped[float | None] = mapped_column(Float)
    high_confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    ambiguous_score_delta: Mapped[float] = mapped_column(Float, nullable=False)
    no_match_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    interpretation: Mapped[EvidenceInterpretation] = relationship(back_populates="match_results")
    candidates: Mapped[list["ObservationMatchCandidate"]] = relationship(
        back_populates="result", cascade="all, delete-orphan"
    )


class ObservationMatchCandidate(Base):
    __tablename__ = "observation_match_candidates"
    __table_args__ = (
        CheckConstraint("similarity_score BETWEEN 0 AND 1", name="observation_candidate_similarity_range"),
        CheckConstraint("contextual_score BETWEEN 0 AND 1", name="observation_candidate_context_range"),
        CheckConstraint("final_score BETWEEN 0 AND 1", name="observation_candidate_final_range"),
        UniqueConstraint("result_id", "activity_id"),
        Index("ix_observation_match_candidates_result_rank", "result_id", "rank"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observation_match_results.result_id"), nullable=False)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    contextual_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    result: Mapped[ObservationMatchResult] = relationship(back_populates="candidates")
    activity: Mapped[Activity] = relationship()


class ActivityMatch(TimestampedModel, Base):
    __tablename__ = "activity_matches"
    __table_args__ = (
        UniqueConstraint("evidence_id", "activity_id"),
        CheckConstraint("similarity_score BETWEEN 0 AND 1", name="match_similarity_range"),
        CheckConstraint("contextual_score BETWEEN 0 AND 1", name="match_contextual_range"),
        CheckConstraint("final_match_score BETWEEN 0 AND 1", name="match_final_range"),
        Index("ix_activity_matches_activity_status", "activity_id", "match_status"),
        Index("ix_activity_matches_evidence_score", "evidence_id", "final_match_score"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence.evidence_id"), nullable=False)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    contextual_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_match_score: Mapped[float] = mapped_column(Float, nullable=False)
    matching_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    match_status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus, name="match_status"), nullable=False, default=MatchStatus.CANDIDATE)

    evidence: Mapped[Evidence] = relationship(back_populates="matches")
    activity: Mapped[Activity] = relationship(back_populates="matches")


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    __table_args__ = (
        CheckConstraint("reconciled_progress IS NULL OR reconciled_progress BETWEEN 0 AND 100", name="reconciliation_progress_range"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="reconciliation_confidence_range"),
        Index("ix_reconciliations_activity_created", "activity_id", "created_at"),
    )

    reconciliation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    reconciled_status: Mapped[ActivityStatus] = mapped_column(Enum(ActivityStatus, name="reconciled_activity_status"), nullable=False)
    reconciled_progress: Mapped[float | None] = mapped_column(Float)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[ReconciliationDecision] = mapped_column(Enum(ReconciliationDecision, name="reconciliation_decision"), nullable=False)
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    conflicting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="Review reconciliation evidence.")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="reconciliations")
    reviews: Mapped[list["PlannerReview"]] = relationship(back_populates="reconciliation")


class EvidenceConflict(TimestampedModel, Base):
    __tablename__ = "evidence_conflicts"
    __table_args__ = (Index("ix_evidence_conflicts_activity_resolution", "activity_id", "resolution_status"),)

    conflict_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    conflict_type: Mapped[ConflictType] = mapped_column(Enum(ConflictType, name="conflict_type"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[ConflictSeverity] = mapped_column(Enum(ConflictSeverity, name="conflict_severity"), nullable=False)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(Enum(ResolutionStatus, name="resolution_status"), nullable=False, default=ResolutionStatus.OPEN)

    activity: Mapped[Activity] = relationship(back_populates="conflicts")


class PlannerReview(TimestampedModel, Base):
    __tablename__ = "planner_reviews"
    __table_args__ = (Index("ix_planner_reviews_activity_reviewed", "activity_id", "reviewed_at"),)

    review_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    reconciliation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reconciliations.reconciliation_id"))
    selected_activity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("activities.activity_id"))
    reviewer: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_decision: Mapped[ReviewDecision] = mapped_column(Enum(ReviewDecision, name="proposed_review_decision"), nullable=False)
    reviewer_decision: Mapped[ReviewDecision] = mapped_column(Enum(ReviewDecision, name="reviewer_decision"), nullable=False, default=ReviewDecision.PENDING)
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    activity: Mapped[Activity] = relationship(back_populates="reviews", foreign_keys=[activity_id])
    selected_activity: Mapped[Activity | None] = relationship(foreign_keys=[selected_activity_id])
    reconciliation: Mapped[Reconciliation | None] = relationship(back_populates="reviews")


class ScheduleUpdate(Base):
    """Internal prototype schedule update, retaining complete decision provenance."""

    __tablename__ = "schedule_updates"
    __table_args__ = (Index("ix_schedule_updates_activity_created", "activity_id", "created_at"),)

    update_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    reconciliation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reconciliations.reconciliation_id"))
    review_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("planner_reviews.review_id"))
    previous_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    new_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    decision_source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="schedule_updates")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_entity_created", "entity_type", "entity_id", "created_at"),)

    audit_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="audit_action"), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExecutionRecord(TimestampedModel, Base):
    """Historical execution record preserving institutional project knowledge."""

    __tablename__ = "execution_records"
    __table_args__ = (
        Index("ix_execution_records_project_activity", "project_id", "activity_id"),
        Index("ix_execution_records_discipline", "discipline"),
        Index("ix_execution_records_contractor", "contractor"),
        Index("ix_execution_records_deviation", "deviation_type"),
        Index("ix_execution_records_delay_category", "delay_category"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    activity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activities.activity_id"), nullable=False)
    external_activity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_name: Mapped[str] = mapped_column(Text, nullable=False)
    discipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_finish: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    planned_duration_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_duration_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    variance_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus, name="activity_status"), nullable=False, default=ActivityStatus.NOT_STARTED
    )
    percent_complete: Mapped[float | None] = mapped_column(Float, nullable=True)
    reconciliation_decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dependency_status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    deviation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    delay_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delay_source_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    planner_override: Mapped[bool] = mapped_column(nullable=False, default=False)
    planner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="execution_records")
    activity: Mapped["Activity"] = relationship("Activity", back_populates="execution_records")
    deviations: Mapped[list["ExecutionDeviation"]] = relationship(
        "ExecutionDeviation", back_populates="record", cascade="all, delete-orphan"
    )


class ExecutionDeviation(TimestampedModel, Base):
    """Specific recorded deviation instance associated with an execution record."""

    __tablename__ = "execution_deviations"
    __table_args__ = (
        Index("ix_deviations_record_type", "record_id", "deviation_type"),
    )

    deviation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("execution_records.record_id"), nullable=False)
    deviation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    record: Mapped["ExecutionRecord"] = relationship("ExecutionRecord", back_populates="deviations")
