import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import ObservationMatchOutcome


class MatchThresholds(BaseModel):
    model_config = ConfigDict(frozen=True)

    high_confidence: float = Field(ge=0, le=1)
    ambiguous_delta: float = Field(ge=0, le=1)
    no_match: float = Field(ge=0, le=1)
    candidate_limit: int = Field(ge=1, le=100)


class CandidateActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: uuid.UUID
    external_activity_id: str
    description: str
    discipline: str | None
    location: str | None
    level: int
    similarity_score: float
    contextual_score: float
    final_score: float
    explanation: str
    rank: int = 1


class ObservationMatchResponse(BaseModel):
    result_id: uuid.UUID
    observation_id: uuid.UUID
    outcome: ObservationMatchOutcome
    ambiguity_flag: bool
    best_score: float | None
    selected_activity_id: uuid.UUID | None
    created_at: datetime
    candidates: list[CandidateActivityResponse]
