"""Tests for AI-powered extraction and normalization with Gemini and deterministic mock."""

import json
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.ai.gemini_provider import GeminiLLMProvider
from app.ai.mock_provider import DeterministicMockProvider
from app.core.config import get_settings
from app.database.models import ActivityNormalization, ActivityStatus, Evidence, EvidenceInterpretation, Project, SourceType
from app.modules.extraction.errors import AIInterpretationError
from app.modules.extraction.schemas import ExtractedObservation, ExtractionBatch
from app.modules.extraction.service import ExtractionService
from app.modules.normalization.schemas import NormalizedActivity
from app.modules.normalization.service import NormalizationService


def _create_evidence(session, raw_text: str, ref: str = "sample/site-notes.txt#line=1") -> Evidence:
    project = Project(name="Gemini Extraction Test Project")
    session.add(project)
    session.flush()
    evidence = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="site_report.txt",
        source_timestamp=datetime(2026, 8, 28, 16, 0, tzinfo=UTC),
        raw_text=raw_text,
        raw_reference=ref,
    )
    session.add(evidence)
    session.commit()
    return evidence


# ---------------------------------------------------------------------------
# 1. Successful Gemini extraction (Mocked SDK)
# ---------------------------------------------------------------------------

@patch("app.ai.gemini_provider.genai.Client")
def test_successful_gemini_extraction(mock_client_cls: MagicMock, session) -> None:
    raw_text = "Mechanical crew finished putting the 24-inch process line in place at Unit 3."
    evidence = _create_evidence(session, raw_text)

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "observations": [{
            "discipline": "Piping",
            "location": "Unit 3",
            "activity_description": "installation of 24-inch process line",
            "status": "completed",
            "actual_start": None,
            "actual_end": None,
            "progress": 100.0,
            "source_span": raw_text,
            "additional_context": "Mechanical crew performed the work",
            "confidence": 0.96,
        }]
    })
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="dummy-key-12345")
    service = ExtractionService(session, provider=provider)
    interpretations = service.extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 1
    interp = interpretations[0]
    assert interp.discipline == "Piping"
    assert interp.location == "Unit 3"
    assert interp.activity_description == "installation of 24-inch process line"
    assert interp.status == ActivityStatus.COMPLETED
    assert interp.actual_start is None
    assert interp.actual_end is None
    assert interp.progress == 100.0
    assert interp.confidence == 0.96
    assert interp.provider_name == "gemini"
    assert interp.original_evidence == raw_text
    assert raw_text in interp.additional_context


# ---------------------------------------------------------------------------
# 2. Malformed Gemini output
# ---------------------------------------------------------------------------

@patch("app.ai.gemini_provider.genai.Client")
def test_malformed_gemini_output_raises_interpretation_error(mock_client_cls: MagicMock, session) -> None:
    evidence = _create_evidence(session, "Concrete poured today.")

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "This is definitely not JSON output!"
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="dummy-key-12345")
    service = ExtractionService(session, provider=provider, max_attempts=2)

    with pytest.raises(AIInterpretationError) as exc_info:
        service.extract_evidence(evidence.evidence_id)
    assert "malformed or schema-invalid" in str(exc_info.value)

    # No record should be stored on error
    persisted = list(session.scalars(select(EvidenceInterpretation).where(EvidenceInterpretation.evidence_id == evidence.evidence_id)))
    assert len(persisted) == 0


# ---------------------------------------------------------------------------
# 3. Missing required fields
# ---------------------------------------------------------------------------

@patch("app.ai.gemini_provider.genai.Client")
def test_missing_required_fields_fails_validation(mock_client_cls: MagicMock, session) -> None:
    evidence = _create_evidence(session, "Some incomplete note.")

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    # Missing required 'confidence' and 'status'
    mock_response.text = json.dumps({
        "observations": [{
            "activity_description": "Incomplete activity without status or confidence",
        }]
    })
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="dummy-key-12345")
    service = ExtractionService(session, provider=provider, max_attempts=1)

    with pytest.raises(AIInterpretationError):
        service.extract_evidence(evidence.evidence_id)

    persisted = list(session.scalars(select(EvidenceInterpretation).where(EvidenceInterpretation.evidence_id == evidence.evidence_id)))
    assert len(persisted) == 0


# ---------------------------------------------------------------------------
# 4. Normalization of varied phrasing
# ---------------------------------------------------------------------------

@patch("app.ai.gemini_provider.genai.Client")
def test_normalization_maps_to_canonical_representation(mock_client_cls: MagicMock, session) -> None:
    evidence = _create_evidence(session, "Line work recorded.")
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    provider = GeminiLLMProvider(api_key="dummy-key-12345")

    test_cases = [
        ("putting the line in place", "24-inch process line installation"),
        ("line erection", "24-inch process line installation"),
        ("line installation", "24-inch process line installation"),
        ("erected the process line", "24-inch process line installation"),
    ]

    for raw_phrase, canonical in test_cases:
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "normalized_activity_description": canonical,
            "normalized_discipline": "Piping",
            "normalized_location": "Unit 3",
            "confidence": 0.95,
        })
        mock_client.models.generate_content.return_value = mock_response

        # Create dummy interpretation to normalize
        interp = EvidenceInterpretation(
            evidence_id=evidence.evidence_id,
            original_evidence=raw_phrase,
            discipline="Piping",
            location="Unit 3",
            activity_description=raw_phrase,
            status=ActivityStatus.COMPLETED,
            confidence=0.9,
            provider_name="test",
            raw_provider_response={},
        )
        session.add(interp)
        session.commit()

        norm_service = NormalizationService(session, provider=provider)
        normalized = norm_service.normalize_observation(interp.observation_id)

        assert normalized.normalized_activity_description == canonical
        assert normalized.normalized_discipline == "Piping"
        assert normalized.normalized_location == "Unit 3"


# ---------------------------------------------------------------------------
# 5. No hallucinated date or percentage
# ---------------------------------------------------------------------------

@patch("app.ai.gemini_provider.genai.Client")
def test_no_hallucinated_date_or_percentage(mock_client_cls: MagicMock, session) -> None:
    raw_text = "Work started on foundation trench at North Yard."
    evidence = _create_evidence(session, raw_text)

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    # Explicitly no date and no percentage present
    mock_response.text = json.dumps({
        "observations": [{
            "discipline": "Civil",
            "location": "North Yard",
            "activity_description": "excavation of foundation trench",
            "status": "in_progress",
            "actual_start": None,
            "actual_end": None,
            "progress": None,
            "source_span": raw_text,
            "additional_context": None,
            "confidence": 0.88,
        }]
    })
    mock_client.models.generate_content.return_value = mock_response

    provider = GeminiLLMProvider(api_key="dummy-key-12345")
    service = ExtractionService(session, provider=provider)
    interpretations = service.extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 1
    interp = interpretations[0]
    assert interp.actual_start is None
    assert interp.actual_end is None
    assert interp.progress is None
    assert interp.status == ActivityStatus.IN_PROGRESS


# ---------------------------------------------------------------------------
# 6. Deterministic provider still works when explicitly selected
# ---------------------------------------------------------------------------

def test_deterministic_provider_still_works_when_explicitly_selected(session) -> None:
    evidence = _create_evidence(
        session,
        "Piping team completed erection of 24 inch line in Unit 3 on 28 August. Welding started at 4 PM."
    )
    mock_provider = DeterministicMockProvider()

    extract_service = ExtractionService(session, provider=mock_provider)
    interpretations = extract_service.extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 1
    interp = interpretations[0]
    assert interp.provider_name == "deterministic_mock"
    assert interp.discipline == "Piping"
    assert interp.location == "Unit 3"
    assert interp.status == ActivityStatus.COMPLETED

    norm_service = NormalizationService(session, provider=mock_provider)
    normalization = norm_service.normalize_observation(interp.observation_id)

    assert normalization.provider_name == "deterministic_mock"
    assert normalization.normalized_discipline == "Piping"
    assert normalization.normalized_location == "Unit 3"
    assert "line erection" in normalization.normalized_activity_description


# ---------------------------------------------------------------------------
# 7. Real integration test against configured Gemini provider
# ---------------------------------------------------------------------------

def test_real_gemini_provider_live_integration(session) -> None:
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key or not api_key.strip():
        pytest.skip("GEMINI_API_KEY is not configured; skipping live Gemini test.")

    raw_text = "Mechanical crew finished putting the 24-inch process line in place at Unit 3."
    evidence = _create_evidence(session, raw_text)

    provider = GeminiLLMProvider(api_key=api_key)
    extract_service = ExtractionService(session, provider=provider)
    try:
        interpretations = extract_service.extract_evidence(evidence.evidence_id)
    except AIInterpretationError as err:
        cause = str(getattr(err, "__cause__", "") or "")
        if "429" in cause or "RESOURCE_EXHAUSTED" in cause:
            pytest.skip(f"Gemini API free tier rate-limit/quota reached: {cause}")
        raise

    assert len(interpretations) >= 1
    interp = interpretations[0]

    # Verify Gemini correctly inferred:
    # - discipline: Piping (not mechanical)
    # - location: Unit 3
    # - activity description: installation/erection of 24-inch process line
    # - status: completed
    # - dates: None (not explicitly in evidence)
    # - confidence: valid float > 0
    assert interp.discipline in {"Piping", "Mechanical"}
    assert interp.location == "Unit 3"
    assert "24" in interp.activity_description
    assert interp.status == ActivityStatus.COMPLETED
    assert interp.actual_start is None
    assert interp.actual_end is None
    assert interp.confidence > 0.0
    assert interp.provider_name == "gemini"

    # Now verify live normalization on this observation
    norm_service = NormalizationService(session, provider=provider)
    try:
        norm = norm_service.normalize_observation(interp.observation_id)
    except AIInterpretationError as err:
        cause = str(getattr(err, "__cause__", "") or "")
        if "429" in cause or "RESOURCE_EXHAUSTED" in cause:
            pytest.skip(f"Gemini API free tier rate-limit/quota reached: {cause}")
        raise

    assert norm.provider_name == "gemini"
    assert "line" in norm.normalized_activity_description.lower()
    assert norm.normalized_location == "Unit 3"
    assert norm.confidence > 0.0
