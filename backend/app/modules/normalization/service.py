import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.ai.interfaces import LLMProvider
from app.ai.registry import get_llm_provider
from app.database.models import ActivityNormalization, EvidenceInterpretation
from app.modules.extraction.errors import AIInterpretationError
from app.modules.normalization.schemas import NormalizedActivity

logger = logging.getLogger(__name__)


class NormalizationService:
    """Creates append-only normalized descriptions from validated interpretations."""

    def __init__(self, session: Session, provider: LLMProvider | None = None, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        self.session = session
        self.provider = provider or get_llm_provider()
        self.max_attempts = max_attempts

    def normalize_observation(self, observation_id: uuid.UUID) -> ActivityNormalization:
        interpretation = self.session.get(EvidenceInterpretation, observation_id)
        if interpretation is None:
            raise AIInterpretationError("Evidence interpretation does not exist.")
        response_json, normalized = self._normalize_with_retry(interpretation)
        record = ActivityNormalization(
            observation_id=interpretation.observation_id,
            normalized_activity_description=normalized.normalized_activity_description,
            normalized_discipline=normalized.normalized_discipline,
            normalized_location=normalized.normalized_location,
            confidence=normalized.confidence,
            provider_name=self.provider.provider_name,
            model_name=self.provider.model_name,
            raw_provider_response=response_json,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def _normalize_with_retry(
        self, interpretation: EvidenceInterpretation
    ) -> tuple[dict[str, object], NormalizedActivity]:
        last_error: Exception | None = None
        prompt = self._build_prompt(interpretation)
        for _attempt in range(self.max_attempts):
            try:
                raw_response = self.provider.normalize_activity(prompt)
                response_json = json.loads(raw_response)
                normalized = NormalizedActivity.model_validate_json(raw_response)
                if not isinstance(response_json, dict):
                    raise ValueError("Provider response must be a JSON object.")
                return response_json, normalized
            # Retrying provider failures here keeps normalization behavior aligned
            # with extraction and prevents partial writes.
            except Exception as error:
                last_error = error
                logger.warning("Activity normalization provider response was invalid on attempt %s", _attempt + 1)
        raise AIInterpretationError(
            f"Provider returned malformed or schema-invalid normalization JSON after {self.max_attempts} attempts."
        ) from last_error

    @staticmethod
    def _build_prompt(interpretation: EvidenceInterpretation) -> str:
        input_json = json.dumps(
            {
                "activity_description": interpretation.activity_description,
                "discipline": interpretation.discipline,
                "location": interpretation.location,
            }
        )
        return (
            "You are an expert construction engineering AI.\n"
            "Normalize the provided construction activity description into a canonical, standardized industry representation.\n\n"
            "Normalization Rules:\n"
            "1. normalized_activity_description: Standardize colloquial or informal field terminology into standard construction activity phrasing. "
            "Phrasing variations such as 'putting the line in place', 'line assembly', 'line installation', and 'erected the process line' "
            "must produce semantically similar canonical activity descriptions (e.g. process line installation). "
            "Preserve key technical identifiers like sizes or equipment tags.\n"
            "2. normalized_discipline: Standardize the engineering discipline to a canonical name (e.g. 'Piping', 'Civil', 'Mechanical', 'Electrical', 'Instrumentation'). "
            "If discipline is null or cannot be determined, return null. Do NOT invent disciplines.\n"
            "3. normalized_location: Standardize the location name (e.g. 'Unit 3', 'East Foundation'). If location is null or cannot be determined, return null. Do NOT invent locations.\n"
            "4. confidence: Float between 0.0 and 1.0 indicating confidence in this normalization.\n\n"
            "CRITICAL: Do NOT invent missing facts.\n\n"
            "Return only JSON matching:\n"
            "{\"normalized_activity_description\":string,\"normalized_discipline\":string|null,"
            "\"normalized_location\":string|null,\"confidence\":number}\n\n"
            f"INPUT_JSON: {input_json}"
        )
