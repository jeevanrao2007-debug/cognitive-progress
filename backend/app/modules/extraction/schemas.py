from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.database.models import ActivityStatus


class ExtractedObservation(BaseModel):
    """Strict contract required from every LLM extraction response."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    discipline: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    activity_description: str = Field(min_length=2, max_length=2000)
    status: ActivityStatus
    actual_start: date | None = None
    actual_end: date | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    source_span: str | None = Field(default=None, max_length=4000)
    additional_context: str | None = Field(default=None, max_length=4000)
    confidence: float = Field(ge=0, le=1)

    contractor: str | None = Field(default=None, max_length=255)
    equipment_or_tag: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    evidence_timestamp: datetime | None = None
    source: str | None = Field(default=None, max_length=255)
    source_reference: str | None = Field(default=None, max_length=2048)
    delay_cause: str | None = Field(default=None, max_length=1000)
    delay_category: str | None = Field(default=None, max_length=50)
    constraint: str | None = Field(default=None, max_length=1000)
    impact_description: str | None = Field(default=None, max_length=1000)
    delay_confidence: float | None = Field(default=None, ge=0, le=1)

    @property
    def progress_percent(self) -> float | None:
        return self.progress


    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: object) -> object:
        if value is None or value == "":
            return ActivityStatus.UNKNOWN.value
        if isinstance(value, str):
            cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
            mapping = {
                "complete": ActivityStatus.COMPLETED.value,
                "completed": ActivityStatus.COMPLETED.value,
                "done": ActivityStatus.COMPLETED.value,
                "finished": ActivityStatus.COMPLETED.value,
                "in_progress": ActivityStatus.IN_PROGRESS.value,
                "ongoing": ActivityStatus.IN_PROGRESS.value,
                "started": ActivityStatus.IN_PROGRESS.value,
                "commenced": ActivityStatus.IN_PROGRESS.value,
                "underway": ActivityStatus.IN_PROGRESS.value,
                "active": ActivityStatus.IN_PROGRESS.value,
                "not_started": ActivityStatus.NOT_STARTED.value,
                "pending": ActivityStatus.NOT_STARTED.value,
                "unstarted": ActivityStatus.NOT_STARTED.value,
                "on_hold": ActivityStatus.ON_HOLD.value,
                "paused": ActivityStatus.ON_HOLD.value,
                "stopped": ActivityStatus.ON_HOLD.value,
                "unknown": ActivityStatus.UNKNOWN.value,
            }
            return mapping.get(cleaned, cleaned)
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> object:
        if value is None:
            return 0.85
        if isinstance(value, (int, float)):
            if 1.0 < value <= 100.0:
                return value / 100.0
        return value

    @field_validator("delay_category", mode="before")
    @classmethod
    def _normalize_delay_category(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            cleaned = value.strip().upper().replace(" ", "_").replace("-", "_")
            allowed = {
                "MATERIAL", "MANPOWER", "EQUIPMENT", "DESIGN", "APPROVAL",
                "INSPECTION", "SAFETY", "WEATHER", "ACCESS", "LOGISTICS",
                "CONTRACTOR", "DEPENDENCY", "OTHER", "UNKNOWN",
            }
            if cleaned in allowed:
                return cleaned
            if any(w in cleaned for w in ["INSPECT", "NDT", "QC", "TEST"]):
                return "INSPECTION"
            if any(w in cleaned for w in ["APPROV", "PERMIT", "CLEARANCE"]):
                return "APPROVAL"
            if any(w in cleaned for w in ["MATER", "DELIVERY", "SPOOL", "VALVE"]):
                return "MATERIAL"
            if any(w in cleaned for w in ["LABOR", "MANPOWER", "CREW"]):
                return "MANPOWER"
            if any(w in cleaned for w in ["CRANE", "EQUIP", "RIGG"]):
                return "EQUIPMENT"
            if any(w in cleaned for w in ["WEATHER", "RAIN", "WIND"]):
                return "WEATHER"
            if any(w in cleaned for w in ["ACCESS", "FRONT", "SCAFFOLD"]):
                return "ACCESS"
            if any(w in cleaned for w in ["PREDECESSOR", "DEPEND"]):
                return "DEPENDENCY"
            return "OTHER"
        return value

    @model_validator(mode="after")
    def _check_completed_progress(self) -> "ExtractedObservation":
        if self.status == ActivityStatus.COMPLETED and (self.progress is None or self.progress == 1.0):
            self.progress = 100.0
        return self



class ExtractionBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    observations: list[ExtractedObservation] = Field(min_length=1, max_length=50)

