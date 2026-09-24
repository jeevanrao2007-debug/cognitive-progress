"""Tests for real semantic embeddings (SentenceTransformers all-MiniLM-L6-v2)
and context-aware L5/L6 activity matching.
"""

from datetime import UTC, date, datetime
import inspect

import pytest
from sqlalchemy import select

from app.ai.exceptions import AIConfigurationError, AIProviderError
from app.ai.mock_provider import DeterministicEmbeddingProvider
from app.ai.registry import get_embedding_provider
from app.ai.sentence_transformer_provider import SentenceTransformersEmbeddingProvider
from app.core.config import Settings
from app.database.models import (
    Activity,
    ActivityNormalization,
    ActivityStatus,
    Evidence,
    EvidenceInterpretation,
    ObservationMatchOutcome,
    Project,
    SourceType,
)
from app.modules.matching.schemas import MatchThresholds
from app.modules.matching.service import MatchingService
import app.modules.matching.service as matching_service_module


THRESHOLDS = MatchThresholds(high_confidence=0.70, ambiguous_delta=0.08, no_match=0.45, candidate_limit=10)


def create_observation(
    session,
    description: str,
    original_evidence: str | None = None,
    normalized_desc: str | None = None,
    location: str = "Unit 3",
    discipline: str = "Piping",
) -> EvidenceInterpretation:
    raw = original_evidence or description
    project = Project(name="Semantic Matching Project")
    evidence = Evidence(
        project=project,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-Unit3.txt",
        source_timestamp=datetime(2026, 8, 28, tzinfo=UTC),
        raw_text=raw,
        raw_reference="DPR-Unit3.txt#line=1",
    )
    observation = EvidenceInterpretation(
        evidence=evidence,
        original_evidence=raw,
        original_reference="DPR-Unit3.txt#line=1",
        activity_description=description,
        discipline=discipline,
        location=location,
        status=ActivityStatus.COMPLETED,
        actual_end=date(2026, 8, 28),
        progress=100,
        confidence=0.92,
        provider_name="gemini",
        model_name="gemini-2.5-flash",
        raw_provider_response={"observations": []},
    )
    session.add(observation)
    session.flush()

    if normalized_desc:
        normalization = ActivityNormalization(
            observation_id=observation.observation_id,
            normalized_activity_description=normalized_desc,
            normalized_discipline=discipline,
            normalized_location=location,
            confidence=0.95,
            provider_name="gemini",
            model_name="gemini-2.5-flash",
            raw_provider_response={},
        )
        session.add(normalization)

    session.commit()
    return observation


def add_schedule_activity(
    session,
    project: Project,
    external_id: str,
    description: str,
    location: str = "Unit 3",
    discipline: str = "Piping",
    level: int = 6,
) -> Activity:
    activity = Activity(
        project=project,
        external_activity_id=external_id,
        description=description,
        location=location,
        discipline=discipline,
        level=level,
        planned_start=date(2026, 8, 1),
        planned_finish=date(2026, 8, 31),
        status=ActivityStatus.NOT_STARTED,
    )
    session.add(activity)
    session.commit()
    return activity


# ==============================================================================
# 1. Sentence Transformer provider initialization (lazy loading)
# ==============================================================================

def test_sentence_transformer_lazy_initialization() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    # Fresh instance has not yet loaded its model into memory
    fresh_provider = SentenceTransformersEmbeddingProvider.__new__(SentenceTransformersEmbeddingProvider)
    fresh_provider.model_name = "all-MiniLM-L6-v2"
    fresh_provider._model = None
    assert fresh_provider._model is None
    # Accessing .model triggers lazy load
    loaded_model = fresh_provider.model
    assert loaded_model is not None
    assert fresh_provider._model is loaded_model


# ==============================================================================
# 2. Real embedding generation
# ==============================================================================

def test_real_embedding_generation() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    vec = provider.embed("Mechanical crew finished putting the 24-inch process line in place at Unit 3.")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(val, float) for val in vec)
    # Check that vector is normalized (magnitude approx 1.0)
    magnitude = sum(x * x for x in vec) ** 0.5
    assert pytest.approx(magnitude, rel=1e-3) == 1.0


# ==============================================================================
# 3. Embedding dimensions
# ==============================================================================

def test_embedding_dimensions() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")
    assert provider.dimensions == 384

    vec1 = provider.embed("Erect Line 24-XX")
    vec2 = provider.embed("24-inch process line installation")
    assert len(vec1) == 384
    assert len(vec2) == 384


# ==============================================================================
# 4. Cosine similarity
# ==============================================================================

def test_cosine_similarity() -> None:
    # Identical vectors
    v1 = [0.6, 0.8]
    assert pytest.approx(MatchingService._cosine(v1, v1), rel=1e-4) == 1.0

    # Orthogonal vectors
    v2 = [-0.8, 0.6]
    assert pytest.approx(MatchingService._cosine(v1, v2), abs=1e-5) == 0.0

    # Opposite vectors
    v3 = [-0.6, -0.8]
    assert pytest.approx(MatchingService._cosine(v1, v3), rel=1e-4) == -1.0

    # Dimension mismatch returns 0.0
    assert MatchingService._cosine([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# ==============================================================================
# 5. Semantic paraphrase similarity
# ==============================================================================

def test_semantic_paraphrase_similarity() -> None:
    provider = SentenceTransformersEmbeddingProvider(model_name="all-MiniLM-L6-v2")

    evidence_text = "Mechanical crew finished putting the 24-inch process line in place at Unit 3."
    piping_schedule = "Erect Line 24-XX"
    electrical_schedule = "Install lighting cables in the administration building."
    catering_text = "Catering staff prepared lunch in the canteen."

    e_ev = provider.embed(evidence_text)
    e_pipe = provider.embed(piping_schedule)
    e_elec = provider.embed(electrical_schedule)
    e_cat = provider.embed(catering_text)

    sim_piping = MatchingService._cosine(e_ev, e_pipe)
    sim_elec = MatchingService._cosine(e_ev, e_elec)
    sim_cat = MatchingService._cosine(e_ev, e_cat)

    # The piping erection activity must be substantially closer semantically than electrical or catering
    assert sim_piping > sim_elec + 0.20
    assert sim_piping > sim_cat + 0.20


# ==============================================================================
# 6. Novel wording -> correct schedule candidate (Part 5 test)
# ==============================================================================

def test_novel_wording_matches_correct_schedule_candidate(session) -> None:
    """Novel phrasing:
    'Mechanical crew finished putting the 24-inch process line in place at Unit 3.'
    Normalized:
    '24-inch process line installation'
    Must match PIP001 'Erect Line 24-XX' as candidate #1 through real semantic embeddings.
    """
    obs = create_observation(
        session,
        description="24-inch process line installation",
        original_evidence="Mechanical crew finished putting the 24-inch process line in place at Unit 3.",
        normalized_desc="24-inch process line installation",
        location="Unit 3",
        discipline="Piping",
    )
    project = obs.evidence.project

    pip001 = add_schedule_activity(session, project, "PIP001", "Erect Line 24-XX", location="Unit 3", discipline="Piping", level=6)
    pip099 = add_schedule_activity(session, project, "PIP099", "Install 8 inch utility pipe", location="Unit 3", discipline="Piping", level=6)
    elec001 = add_schedule_activity(session, project, "ELEC001", "Install lighting cables in the administration building", location="Admin Building", discipline="Electrical", level=6)
    mech001 = add_schedule_activity(session, project, "MECH001", "Cooling tower motor alignment", location="Cooling Tower", discipline="Mechanical", level=6)

    service = MatchingService(session, thresholds=THRESHOLDS)
    result = service.match_observation(obs.observation_id)

    # PIP001 must rank as candidate 1
    assert len(result.candidates) >= 1
    top_candidate = result.candidates[0]
    assert top_candidate.activity_id == pip001.activity_id
    assert top_candidate.external_activity_id == "PIP001"
    assert top_candidate.rank == 1

    # Real similarity score must be strong
    assert top_candidate.similarity_score > 0.35
    assert top_candidate.final_score > 0.50
    assert result.outcome in {ObservationMatchOutcome.MATCHED, ObservationMatchOutcome.NEEDS_REVIEW}

    # Verify PIP001 ranks higher than PIP099, ELEC001, MECH001
    candidate_ids = [c.external_activity_id for c in result.candidates]
    assert candidate_ids[0] == "PIP001"
    assert top_candidate.final_score > result.candidates[1].final_score


# ==============================================================================
# 7. Unrelated wording -> low similarity (Part 5 negative test)
# ==============================================================================

def test_unrelated_wording_low_similarity(session) -> None:
    """'Install lighting cables in the administration building.'
    Must NOT rank PIP001 as top candidate or with high confidence.
    """
    obs = create_observation(
        session,
        description="Install lighting cables in the administration building",
        original_evidence="Electricians pulled and installed lighting cables across corridor 2B.",
        location="Admin Building",
        discipline="Electrical",
    )
    project = obs.evidence.project

    pip001 = add_schedule_activity(session, project, "PIP001", "Erect Line 24-XX", location="Unit 3", discipline="Piping", level=6)
    elec001 = add_schedule_activity(session, project, "ELEC001", "Install lighting cables in the administration building", location="Admin Building", discipline="Electrical", level=6)

    service = MatchingService(session, thresholds=THRESHOLDS)
    result = service.match_observation(obs.observation_id)

    # ELEC001 must rank #1, not PIP001
    assert result.candidates[0].external_activity_id == "ELEC001"

    # PIP001 similarity to lighting cables must be low (< 0.25)
    pip_candidate = next(c for c in result.candidates if c.external_activity_id == "PIP001")
    assert pip_candidate.similarity_score < 0.25
    assert pip_candidate.final_score < 0.35


# ==============================================================================
# 8. Anti-hardcoding audit test: NO hard-coded PIP001 mapping
# ==============================================================================

def test_no_hardcoded_pip001_mapping(session) -> None:
    """Verify that PIP001 is NOT hard-coded anywhere in the matching service logic."""
    # 1. Source code check
    source = inspect.getsource(matching_service_module)
    assert "PIP001" not in source
    assert "PIP099" not in source
    assert "ELEC001" not in source

    # 2. Functional equivalence test with a randomized activity ID
    obs = create_observation(
        session,
        description="24-inch process line installation",
        original_evidence="Mechanical crew finished putting the 24-inch process line in place at Unit 3.",
        location="Unit 3",
        discipline="Piping",
    )
    project = obs.evidence.project

    # Use arbitrary, non-standard activity ID
    custom_act = add_schedule_activity(
        session, project, "ARBITRARY_PIPE_9999", "Erect Line 24-XX", location="Unit 3", discipline="Piping", level=6
    )
    add_schedule_activity(
        session, project, "OTHER_ACT_1111", "Install 8 inch utility pipe", location="Unit 3", discipline="Piping", level=6
    )

    service = MatchingService(session, thresholds=THRESHOLDS)
    result = service.match_observation(obs.observation_id)

    # Must rank ARBITRARY_PIPE_9999 as #1
    assert result.candidates[0].activity_id == custom_act.activity_id
    assert result.candidates[0].external_activity_id == "ARBITRARY_PIPE_9999"
    assert result.candidates[0].rank == 1


# ==============================================================================
# 9. Deterministic embedding provider still works when explicitly selected
# ==============================================================================

def test_deterministic_embedding_provider_explicit_selection(session) -> None:
    det_provider = DeterministicEmbeddingProvider()
    assert det_provider.dimensions == 128
    vec = det_provider.embed("Erect Line 24-XX")
    assert len(vec) == 128
    assert all(isinstance(x, float) for x in vec)

    obs = create_observation(session, "24 inch line erection completed in Unit 3")
    act = add_schedule_activity(session, obs.evidence.project, "DET_ACT_001", "Erect Line 24-XX")

    service = MatchingService(session, embedding_provider=det_provider, thresholds=THRESHOLDS)
    result = service.match_observation(obs.observation_id)
    assert result.candidates[0].activity_id == act.activity_id


# ==============================================================================
# 10. No silent fallback when sentence_transformers is configured
# ==============================================================================

def test_no_silent_fallback_on_sentence_transformers() -> None:
    """If AI_EMBEDDING_PROVIDER=sentence_transformers, registry must return
    SentenceTransformersEmbeddingProvider, NOT silently fall back to DeterministicEmbeddingProvider.
    """
    settings = Settings(ai_embedding_provider="sentence_transformers", ai_embedding_model="all-MiniLM-L6-v2")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.ai.registry.get_settings", lambda: settings)
        provider = get_embedding_provider()
        assert isinstance(provider, SentenceTransformersEmbeddingProvider)
        assert not isinstance(provider, DeterministicEmbeddingProvider)
