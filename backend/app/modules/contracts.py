from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    source_id: str
    source_type: str
    filename: str


class ActivityObservation(BaseModel):
    description: str
    reported_status: str | None = None
    quantity: float | None = None
    unit: str | None = None
    source_id: str = Field(description="Links the observation back to the source document.")


class MatchCandidate(BaseModel):
    schedule_activity_id: str
    score: float
    rationale: str


class ReconciliationDecision(BaseModel):
    activity_id: str
    proposed_status: str
    confidence: float
    explanation: str
    requires_planner_review: bool
