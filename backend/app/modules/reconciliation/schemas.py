import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import ActivityStatus, ReconciliationDecision, SourceType


class ReconciliationThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)
    auto_accept: float = Field(ge=0, le=1)
    review: float = Field(ge=0, le=1)
    no_decision: float = Field(ge=0, le=1)
    freshness_half_life_days: float = Field(gt=0)
    source_reliability: dict[SourceType, float]


class EvidenceReference(BaseModel):
    observation_id: uuid.UUID
    evidence_id: uuid.UUID
    source_name: str
    source_type: SourceType
    source_timestamp: datetime
    status: ActivityStatus
    progress: float | None
    weight: float
    raw_text: str | None = None
    reliability_score: float | None = None
    freshness_score: float | None = None
    is_stale: bool = False
    is_duplicate: bool = False
    contradiction_reason: str | None = None


class AIReconciliationRecommendation(BaseModel):
    recommended_status: ActivityStatus | None = None
    recommended_progress: float | None = None
    recommended_actual_start: date | None = None
    recommended_actual_end: date | None = None
    evidence_assessment: str | None = None
    conflict_detected: bool = False
    conflict_summary: str | None = None
    source_reliability_reasoning: str | None = None
    schedule_context_reasoning: str | None = None
    reasoning: str = ""
    confidence: float = 0.0
    recommended_action: str | None = None
    supporting_observations: list[str] = Field(default_factory=list)
    contradictory_observations: list[str] = Field(default_factory=list)


class DependencyValidationDetailResponse(BaseModel):
    predecessor_activity_id: str | None = None
    predecessor_activity_name: str | None = None
    successor_activity_id: str | None = None
    successor_activity_name: str | None = None
    relevant_actual_start: date | None = None
    relevant_actual_end: date | None = None
    rule: str | None = None
    status: str
    reason: str | None = None


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    reconciliation_id: uuid.UUID
    activity_id: uuid.UUID
    reconciled_status: ActivityStatus
    reconciled_progress: float | None
    actual_start: date | None
    actual_end: date | None
    confidence: float
    decision: ReconciliationDecision
    explanation: str
    supporting_evidence: list[EvidenceReference]
    conflicting_evidence: list[EvidenceReference]
    recommended_action: str
    created_at: datetime
    ai_recommendation: AIReconciliationRecommendation | None = None
    conflict_detected: bool = False
    conflict_types: list[str] = Field(default_factory=list)
    reasoning_factors: dict[str, object] = Field(default_factory=dict)
    dependency_status: str | None = None
    dependency_details: list[DependencyValidationDetailResponse] = Field(default_factory=list)

