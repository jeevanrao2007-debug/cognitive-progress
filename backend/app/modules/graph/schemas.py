"""Schemas for execution evidence graph and activity execution context."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ActivitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_activity_id: str
    discipline: str | None
    description: str
    location: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    progress: float | None = None
    status: str
    level: int = 5


class DependencyContext(BaseModel):
    dependency_id: uuid.UUID
    activity_id: uuid.UUID
    external_activity_id: str
    description: str
    dependency_type: str
    lag_days: int
    status: str
    progress: float | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None


class CandidateActivityMatch(BaseModel):
    activity_id: uuid.UUID
    external_activity_id: str
    description: str
    similarity_score: float
    contextual_score: float
    final_score: float
    explanation: str


class ExecutionEventContext(BaseModel):
    event_id: uuid.UUID
    evidence_id: uuid.UUID
    source_name: str
    source_type: str
    source_timestamp: datetime
    field_description: str
    discipline: str | None = None
    location: str | None = None
    contractor: str | None = None
    status: str
    progress: float | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    extraction_confidence: float
    match_score: float | None = None
    match_outcome: str | None = None
    candidates: list[CandidateActivityMatch] = []
    reconciliation_decision: str | None = None
    is_supporting: bool = False
    is_conflicting: bool = False


class ProvenanceTrace(BaseModel):
    field: str
    value: str
    event_id: uuid.UUID
    evidence_id: uuid.UUID
    source_name: str
    source_type: str
    source_timestamp: datetime
    contractor: str | None = None
    rationale: str


class ReconciliationSummary(BaseModel):
    reconciliation_id: uuid.UUID
    decision: str
    status: str
    progress: float | None = None
    confidence: float
    explanation: str
    created_at: datetime


class TemporalValidationSummary(BaseModel):
    is_valid: bool
    status: str
    rule_name: str | None = None
    details: str | None = None


class ExecutionContextResponse(BaseModel):
    activity: ActivitySummary
    predecessors: list[DependencyContext]
    successors: list[DependencyContext]
    execution_events: list[ExecutionEventContext]
    reconciliation: ReconciliationSummary | None = None
    temporal_validation: TemporalValidationSummary
    provenance: list[ProvenanceTrace] = []
