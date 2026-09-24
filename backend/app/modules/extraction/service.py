import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.ai.interfaces import LLMProvider
from app.ai.registry import get_llm_provider
from app.database.models import Evidence, EvidenceInterpretation
from app.modules.extraction.errors import AIInterpretationError
from app.modules.extraction.schemas import ExtractionBatch

logger = logging.getLogger(__name__)


class ExtractionService:
    """Creates validated, append-only interpretations for raw evidence."""

    def __init__(self, session: Session, provider: LLMProvider | None = None, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        self.session = session
        self.provider = provider or get_llm_provider()
        self.max_attempts = max_attempts

    def extract_evidence(self, evidence_id: uuid.UUID) -> list[EvidenceInterpretation]:
        evidence = self.session.get(Evidence, evidence_id)
        if evidence is None:
            raise AIInterpretationError("Evidence does not exist.")
        if not evidence.raw_text:
            raise AIInterpretationError("Evidence has no raw text available for extraction.")

        response_json, batch = self._extract_with_retry(evidence)
        interpretations = []
        for observation in batch.observations:
            meta_parts = []
            if observation.source_span:
                meta_parts.append(observation.source_span)
            if observation.contractor:
                meta_parts.append(f"Contractor: {observation.contractor}")
            if observation.equipment_or_tag:
                meta_parts.append(f"Tag: {observation.equipment_or_tag}")
            if observation.notes:
                meta_parts.append(observation.notes)
            if observation.additional_context and observation.additional_context not in meta_parts:
                meta_parts.append(observation.additional_context)
            context = " | ".join(meta_parts) if meta_parts else None
            interpretations.append(
                EvidenceInterpretation(
                    evidence_id=evidence.evidence_id,
                    original_evidence=evidence.raw_text,
                    original_reference=evidence.raw_reference,
                    discipline=observation.discipline,
                    location=observation.location,
                    contractor=observation.contractor,
                    activity_description=observation.activity_description,
                    status=observation.status,
                    actual_start=observation.actual_start,
                    actual_end=observation.actual_end,
                    progress=observation.progress,
                    additional_context=context or None,
                    delay_cause=observation.delay_cause,
                    delay_category=observation.delay_category,
                    constraint=observation.constraint,
                    impact_description=observation.impact_description,
                    delay_confidence=observation.delay_confidence,
                    confidence=observation.confidence,
                    provider_name=self.provider.provider_name,
                    model_name=self.provider.model_name,
                    raw_provider_response=response_json,
                )
            )

        self.session.add_all(interpretations)
        self.session.commit()
        return interpretations

    def _extract_with_retry(self, evidence: Evidence) -> tuple[dict[str, object], ExtractionBatch]:
        last_error: Exception | None = None
        prompt = self._build_prompt(evidence)
        for _attempt in range(self.max_attempts):
            try:
                raw_response = self.provider.extract_progress(prompt)
                response_json = json.loads(raw_response)
                batch = ExtractionBatch.model_validate_json(raw_response)
                if not isinstance(response_json, dict):
                    raise ValueError("Provider response must be a JSON object.")
                return response_json, batch
            # A provider can fail before it returns a response (for example, on a
            # transient transport error), so treat that exactly like malformed JSON.
            except Exception as error:
                last_error = error
                logger.warning("Evidence extraction provider response was invalid on attempt %s", _attempt + 1)
        raise AIInterpretationError(
            f"Provider returned malformed or schema-invalid extraction JSON after {self.max_attempts} attempts."
        ) from last_error

    @staticmethod
    def _build_prompt(evidence: Evidence) -> str:
        input_json = json.dumps(
            {
                "raw_text": evidence.raw_text,
                "source_name": evidence.source_name,
                "source_timestamp": evidence.source_timestamp.isoformat() if evidence.source_timestamp else None,
                "source_type": evidence.source_type.value if hasattr(evidence.source_type, "value") else str(evidence.source_type),
            }
        )
        return (
            "You are an expert construction engineering AI analyzing field progress evidence from industrial projects.\n"
            "Extract structured field-progress observations from the provided field evidence.\n\n"
            "Extraction Rules:\n"
            "1. Multiple Activities: If the evidence mentions multiple distinct construction activities or tasks, return a separate observation object for each activity in the observations array.\n"
            "2. discipline: Identify the engineering discipline (e.g. 'Piping', 'Civil', 'Electrical', 'Mechanical', 'Instrumentation', 'Structural'). "
            "Process lines, pipe spools, valves, and welds belong to 'Piping' even if worked on by a mechanical crew. If discipline is not evident, return null.\n"
            "3. location: Identify the specific site location or plant unit (e.g. 'Unit 3', 'East Foundation'). If not explicitly mentioned in the text, return null. Do NOT invent locations.\n"
            "4. activity_description: Provide a clear, factual description of the work performed (e.g. 'installation of 24-inch process line' or 'erection of 24-inch process line'). "
            "Interpret the meaning of the field evidence. Do NOT reference or select schedule activity codes (do NOT map to schedule IDs like PIP001).\n"
            "5. status: Must be one of: 'not_started', 'in_progress', 'completed', 'on_hold', 'unknown'. Infer from context (e.g. 'finished', 'completed' -> 'completed', 'started', 'underway', 'commenced' -> 'in_progress').\n"
            "6. actual_start / actual_end: Extract ISO date (YYYY-MM-DD) ONLY if explicitly stated in the evidence text or unambiguous report header. "
            "If a time appears without an unambiguous date, return null for actual_start/actual_end and preserve the time in notes/additional_context. DO NOT invent or hallucinate dates.\n"
            "7. progress: Numeric percentage from 0.0 to 100.0 (e.g. 100.0 for completed, 80.0 for 80%). If status is completed and the activity is finished, 100.0 is acceptable. "
            "If in progress and no percentage is explicitly given, return null. Do NOT invent arbitrary percentages.\n"
            "8. contractor: Name of contractor or subcontractor if explicitly mentioned, otherwise null.\n"
            "9. equipment_or_tag: Equipment tag or line ID (e.g. 'Line 24-XX', 'P-301') if explicitly mentioned, otherwise null.\n"
            "10. source_span: The exact text span or sentence from the raw evidence supporting this observation.\n"
            "11. additional_context / notes: Any relevant extra details (e.g. times, weather, equipment) explicitly mentioned in the text, or null.\n"
            "12. confidence: Float between 0.0 and 1.0 indicating confidence in this extraction.\n"
            "13. delay_cause: If the evidence explicitly states a reason/cause for delay, constraint, or stoppage (e.g. 'pending NDT clearance', 'material shortage', 'weather'), extract that exact reason. If a delay is mentioned without an explicit reason, return 'UNKNOWN'. If no delay is mentioned, return null. NEVER infer, guess, or fabricate causes.\n"
            "14. delay_category: One of ['MATERIAL', 'MANPOWER', 'EQUIPMENT', 'DESIGN', 'APPROVAL', 'INSPECTION', 'SAFETY', 'WEATHER', 'ACCESS', 'LOGISTICS', 'CONTRACTOR', 'DEPENDENCY', 'OTHER', 'UNKNOWN']. Only assign when explicitly supported by the evidence text. If no delay, return null.\n"
            "15. constraint / impact_description: Brief description of constraint or execution impact if explicitly stated, otherwise null.\n"
            "16. delay_confidence: Float between 0.0 and 1.0 indicating confidence in the delay cause extraction, or null.\n\n"
            "CRITICAL: Do NOT invent missing facts. If date, percentage, location, or status is not explicitly supported by the evidence, return null or unknown rather than hallucinating.\n\n"
            "Return only JSON matching this exact shape:\n"
            "{\"observations\":[{\"discipline\":string|null,\"location\":string|null,"
            "\"activity_description\":string,\"status\":\"not_started|in_progress|completed|on_hold|unknown\","
            "\"actual_start\":\"YYYY-MM-DD\"|null,\"actual_end\":\"YYYY-MM-DD\"|null,"
            "\"progress\":number|null,\"contractor\":string|null,\"equipment_or_tag\":string|null,"
            "\"source_span\":string|null,\"additional_context\":string|null,\"notes\":string|null,"
            "\"delay_cause\":string|null,\"delay_category\":string|null,\"constraint\":string|null,"
            "\"impact_description\":string|null,\"delay_confidence\":number|null,\"confidence\":number}]}\n\n"
            f"INPUT_JSON: {input_json}"
        )
