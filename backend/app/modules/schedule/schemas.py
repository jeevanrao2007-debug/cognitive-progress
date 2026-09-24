from __future__ import annotations

import enum
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ScheduleDecisionState(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PLANNER_REVIEW = "PLANNER_REVIEW"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    UNCHANGED = "UNCHANGED"


class ScheduleChangeItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_activity_id: str
    activity_name: str
    discipline: str | None = None
    location: str | None = None
    field: str
    old_value: str
    new_value: str
    source_evidence: str
    match_confidence: float | None = None
    reconciliation_confidence: float | None = None
    temporal_status: str
    decision: ScheduleDecisionState
    decision_source: str
    rationale: str
    updated_at: datetime | None = None


class ScheduleExportSummary(BaseModel):
    activities_evaluated: int
    verified_updates: int
    planner_review: int
    conflicts: int
    rejected: int
    unchanged: int


class ScheduleChangePreviewResponse(BaseModel):
    project_id: uuid.UUID
    summary: ScheduleExportSummary
    changes: list[ScheduleChangeItem]
    deferral_notice: str = "P6 XML deferred; verified schedule export available through CSV/XLSX."
