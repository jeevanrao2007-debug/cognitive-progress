"""Schemas for execution memory, deviations, project knowledge, and historical references."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionDeviationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    deviation_id: uuid.UUID
    deviation_type: str
    metric_days: float | None = None
    description: str


class ExecutionRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: uuid.UUID
    project_id: uuid.UUID
    activity_id: uuid.UUID
    external_activity_id: str
    activity_name: str
    discipline: str | None = None
    contractor: str | None = None
    location: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    planned_duration_days: float | None = None
    actual_duration_days: float | None = None
    variance_days: float | None = None
    status: str
    percent_complete: float | None = None
    reconciliation_decision: str | None = None
    confidence: float | None = None
    evidence_reference: str | None = None
    source_timestamp: datetime | None = None
    dependency_status: str | None = None
    deviation_type: str
    delay_cause: str | None = None
    delay_category: str | None = None
    delay_source_evidence: str | None = None
    delay_confidence: float | None = None
    planner_override: bool = False
    planner_notes: str | None = None
    deviations: list[ExecutionDeviationItem] = Field(default_factory=list)


class ActivityExecutionHistoryResponse(BaseModel):
    activity_id: uuid.UUID
    external_activity_id: str
    activity_name: str
    discipline: str | None = None
    contractor: str | None = None
    location: str | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    actual_start: date | None = None
    actual_end: date | None = None
    planned_duration_days: float | None = None
    actual_duration_days: float | None = None
    variance_days: float | None = None
    status: str
    percent_complete: float | None = None
    execution_evidence_citations: list[str] = Field(default_factory=list)
    recorded_deviations: list[str] = Field(default_factory=list)
    recorded_cause: str | None = None
    delay_category: str | None = None
    cause_source_reference: str | None = None
    cause_confidence: float | None = None
    planner_decisions: list[dict[str, Any]] = Field(default_factory=list)


class DisciplinePerformanceItem(BaseModel):
    discipline: str
    total_activities: int
    completed_activities: int
    average_variance_days: float | None = None
    delayed_count: int


class ContractorPerformanceItem(BaseModel):
    contractor: str
    total_activities: int
    completed_activities: int
    average_variance_days: float | None = None
    delayed_count: int


class DelayCauseFrequencyItem(BaseModel):
    category: str
    count: int
    sample_causes: list[str] = Field(default_factory=list)


class ProjectPerformanceSummary(BaseModel):
    project_id: uuid.UUID
    project_name: str
    total_activities: int
    completed_activities: int
    on_time_activities: int
    late_activities: int
    conflict_count: int
    average_planned_duration_days: float | None = None
    average_actual_duration_days: float | None = None
    average_variance_days: float | None = None
    top_delay_causes: list[DelayCauseFrequencyItem] = Field(default_factory=list)
    discipline_performance: list[DisciplinePerformanceItem] = Field(default_factory=list)
    contractor_performance: list[ContractorPerformanceItem] = Field(default_factory=list)


class HistoricalReferenceItem(BaseModel):
    activity_name: str
    external_activity_id: str | None = None
    project_name: str
    discipline: str | None = None
    contractor: str | None = None
    planned_duration_days: float | None = None
    actual_duration_days: float | None = None
    variance_days: float | None = None
    delay_cause: str | None = None
    delay_category: str | None = None
    evidence_reference: str | None = None
    similarity_score: float = 1.0
    disclaimer: str = "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"


class SimilarExecutionSearchResponse(BaseModel):
    query: str
    discipline: str | None = None
    results: list[HistoricalReferenceItem] = Field(default_factory=list)
    disclaimer: str = "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"


class CrossProjectMemoryResponse(BaseModel):
    query_filter: str | None = None
    discipline_filter: str | None = None
    total_matching_records: int
    completed_matching_records: int
    average_variance_days: float | None = None
    top_delay_causes: list[DelayCauseFrequencyItem] = Field(default_factory=list)
    discipline_breakdown: list[DisciplinePerformanceItem] = Field(default_factory=list)
    sample_records: list[HistoricalReferenceItem] = Field(default_factory=list)
    disclaimer: str = "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"
