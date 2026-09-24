from pydantic import BaseModel, ConfigDict, Field, field_validator


class NormalizedActivity(BaseModel):
    """Strict contract required from every LLM normalization response."""

    model_config = ConfigDict(extra="ignore")

    normalized_activity_description: str = Field(min_length=3, max_length=2000)
    normalized_discipline: str | None = Field(default=None, max_length=100)
    normalized_location: str | None = Field(default=None, max_length=255)
    confidence: float = Field(ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> object:
        if isinstance(value, (int, float)):
            if 1.0 < value <= 100.0:
                return value / 100.0
        return value
