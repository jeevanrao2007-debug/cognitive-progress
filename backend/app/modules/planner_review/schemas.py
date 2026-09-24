import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.database.models import ActivityStatus, ReviewDecision
from app.modules.matching.schemas import CandidateActivityResponse
from app.modules.reconciliation.schemas import EvidenceReference, ReconciliationResponse


PlannerAction = Literal["approve", "reject", "modify", "select_activity", "comment"]


class PlannerActionRequest(BaseModel):
    action: PlannerAction
    reviewer: str = Field(min_length=1, max_length=255)
    comment: str | None = Field(default=None, max_length=4000)
    status: ActivityStatus | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    actual_start: date | None = None
    actual_end: date | None = None
    selected_activity_id: uuid.UUID | None = None


class ActivityState(BaseModel):
    activity_id: uuid.UUID
    external_activity_id: str
    description: str
    status: ActivityStatus
    actual_progress: float | None
    actual_start: date | None
    actual_end: date | None


class AuditEntry(BaseModel):
    audit_id: uuid.UUID
    action: str
    actor: str
    explanation: str | None
    created_at: datetime


class PlannerReviewContext(BaseModel):
    review_id: uuid.UUID
    reviewer_decision: ReviewDecision
    reviewer_comment: str | None
    reason: str
    current_activity: ActivityState
    proposed_reconciliation: ReconciliationResponse
    supporting_evidence: list[EvidenceReference]
    conflicting_evidence: list[EvidenceReference]
    match_candidates: list[CandidateActivityResponse]
    audit_history: list[AuditEntry]
