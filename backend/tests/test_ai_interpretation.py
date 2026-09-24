import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.ai.mock_provider import DeterministicMockProvider
from app.database.models import ActivityNormalization, Evidence, EvidenceInterpretation, Project, SourceType
from app.modules.extraction.errors import AIInterpretationError
from app.modules.extraction.service import ExtractionService
from app.modules.normalization.service import NormalizationService


class MockProvider:
    provider_name = "mock_llm"
    model_name = "test-model"

    def __init__(self, extraction_responses: list[str], normalization_response: str | None = None) -> None:
        self.extraction_responses = extraction_responses
        self.normalization_response = normalization_response or json.dumps({
            "normalized_activity_description": "24 inch line erection",
            "normalized_discipline": "Piping",
            "normalized_location": "Unit 3",
            "confidence": 0.93,
        })
        self.extraction_calls = 0

    def extract_progress(self, prompt: str) -> str:
        response = self.extraction_responses[self.extraction_calls]
        self.extraction_calls += 1
        return response

    def normalize_activity(self, prompt: str) -> str:
        return self.normalization_response

    def explain_reconciliation(self, prompt: str) -> str:
        return "{}"


def create_evidence(session) -> Evidence:  # type: ignore[no-untyped-def]
    project = Project(name="AI interpretation test")
    evidence = Evidence(
        project=project,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-2026-08-28.txt",
        source_timestamp=datetime(2026, 8, 28, 16, 30, tzinfo=UTC),
        raw_text="Piping team completed erection of 24 inch line in Unit 3 on 28 August. Welding started at 4 PM.",
        raw_reference="sample/DPR-2026-08-28.txt#line=12",
    )
    session.add(evidence)
    session.commit()
    return evidence


def expected_extraction_json() -> str:
    return json.dumps({
        "observations": [{
            "discipline": "Piping",
            "location": "Unit 3",
            "activity_description": "24 inch line erection",
            "status": "completed",
            "actual_start": None,
            "actual_end": "2026-08-28",
            "progress": 100.0,
            "additional_context": "Welding started at 16:00",
            "confidence": 0.94,
        }]
    })


def test_extraction_persists_validated_interpretation_without_mutating_evidence(session) -> None:  # type: ignore[no-untyped-def]
    evidence = create_evidence(session)
    original_raw_text = evidence.raw_text
    provider = MockProvider([expected_extraction_json()])

    interpretations = ExtractionService(session, provider).extract_evidence(evidence.evidence_id)

    stored_evidence = session.get(Evidence, evidence.evidence_id)
    interpretation = interpretations[0]
    assert stored_evidence is not None
    assert stored_evidence.raw_text == original_raw_text
    assert interpretation.original_evidence == original_raw_text
    assert interpretation.original_reference == "sample/DPR-2026-08-28.txt#line=12"
    assert interpretation.activity_description == "24 inch line erection"
    assert interpretation.actual_end.isoformat() == "2026-08-28"
    assert interpretation.additional_context == "Welding started at 16:00"
    assert interpretation.provider_name == "mock_llm"
    assert interpretation.raw_provider_response["observations"][0]["progress"] == 100.0


def test_extraction_retries_malformed_response_then_succeeds(session) -> None:  # type: ignore[no-untyped-def]
    evidence = create_evidence(session)
    provider = MockProvider(["not json", expected_extraction_json()])

    interpretations = ExtractionService(session, provider, max_attempts=2).extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 1
    assert provider.extraction_calls == 2


def test_extraction_retries_provider_failure_then_succeeds(session) -> None:  # type: ignore[no-untyped-def]
    class TransientProvider(MockProvider):
        def extract_progress(self, prompt: str) -> str:
            if self.extraction_calls == 0:
                self.extraction_calls += 1
                raise ConnectionError("temporary provider outage")
            self.extraction_calls += 1
            return self.extraction_responses[0]

    evidence = create_evidence(session)
    provider = TransientProvider([expected_extraction_json()])

    interpretations = ExtractionService(session, provider, max_attempts=2).extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 1
    assert provider.extraction_calls == 2


def test_invalid_extraction_response_creates_no_interpretation(session) -> None:  # type: ignore[no-untyped-def]
    evidence = create_evidence(session)
    invalid_response = json.dumps({"observations": [{"activity_description": "Missing required fields"}]})
    provider = MockProvider([invalid_response, invalid_response])

    with pytest.raises(AIInterpretationError):
        ExtractionService(session, provider, max_attempts=2).extract_evidence(evidence.evidence_id)

    assert list(session.scalars(select(EvidenceInterpretation))) == []


def test_normalization_persists_a_second_traceable_record(session) -> None:  # type: ignore[no-untyped-def]
    evidence = create_evidence(session)
    provider = MockProvider([expected_extraction_json()])
    interpretation = ExtractionService(session, provider).extract_evidence(evidence.evidence_id)[0]

    normalization = NormalizationService(session, provider).normalize_observation(interpretation.observation_id)

    assert normalization.normalized_activity_description == "24 inch line erection"
    assert normalization.provider_name == "mock_llm"
    assert session.get(ActivityNormalization, normalization.normalization_id) is not None


def test_normalization_retries_malformed_response_then_succeeds(session) -> None:  # type: ignore[no-untyped-def]
    class RetryingNormalizationProvider(MockProvider):
        def __init__(self) -> None:
            super().__init__([expected_extraction_json()])
            self.normalization_calls = 0

        def normalize_activity(self, prompt: str) -> str:
            self.normalization_calls += 1
            if self.normalization_calls == 1:
                return "not json"
            return self.normalization_response

    evidence = create_evidence(session)
    provider = RetryingNormalizationProvider()
    interpretation = ExtractionService(session, provider).extract_evidence(evidence.evidence_id)[0]

    normalization = NormalizationService(session, provider, max_attempts=2).normalize_observation(interpretation.observation_id)

    assert normalization.normalized_activity_description == "24 inch line erection"
    assert provider.normalization_calls == 2


def test_deterministic_provider_runs_without_api_key(session) -> None:  # type: ignore[no-untyped-def]
    evidence = create_evidence(session)

    interpretation = ExtractionService(session, DeterministicMockProvider()).extract_evidence(evidence.evidence_id)[0]

    assert interpretation.provider_name == "deterministic_mock"
    assert interpretation.status.value == "completed"
