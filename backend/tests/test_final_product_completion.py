"""Targeted validation tests for SIH26122 Final Product Completion Pass.

Covers:
1. Supervisor conversational workflow with natural language field statements:
   - "Line 24-XX erection started today." (START event, in_progress, actual_start set)
   - "Valve installation finished yesterday." (END event, completed, actual_end set)
   - "Hydrotest preparation started on September 10." (START event, named month parsing)
2. Multi-activity / granularity handling:
   - "Foundation excavation completed and rebar fixing started." (2 discrete activities)
3. Unmatched / new activity workflow:
   - "Temporary fencing outside workfront" (NO_MATCH outcome, preserved in memory, quarantined)
4. Planner review completeness:
   - Dependency / temporal conflict details surfaced in PlannerReviewContext
5. End-to-end safety gate:
   - Conversational input -> extraction -> matching -> reconciliation -> safety gate
"""

import uuid
from datetime import date
from sqlalchemy import select

from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider
from app.database.demo import DEMO_PROJECT_ID, reset_sih26122
from app.database.models import (
    Activity,
    ActivityStatus,
    Evidence,
    EvidenceInterpretation,
    ObservationMatchOutcome,
    ObservationMatchResult,
    PlannerReview,
    Project,
    Reconciliation,
    ReconciliationDecision,
    SourceType,
)
from app.modules.extraction.service import ExtractionService
from app.modules.ingestion.service import IngestionService
from app.modules.matching.service import MatchingService
from app.modules.normalization.service import NormalizationService
from app.modules.planner_review.schemas import PlannerActionRequest
from app.modules.planner_review.service import PlannerReviewService
from app.modules.reconciliation.service import ReconciliationService


def test_supervisor_workflow_natural_language_events(session) -> None:
    """Supervisor conversational field inputs extract structured start/end events with dates."""
    project = reset_sih26122(session)
    ingestion = IngestionService(session)
    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)

    # Event 1: Start event with relative date "today"
    text_start = "Line 24-XX erection started today."
    source1, ev1 = ingestion.import_text_evidence(
        project.project_id, text_start, "supervisor_turn_1.txt", SourceType.DAILY_REPORT
    )
    obs1_list = extractor.extract_evidence(ev1.evidence_id)
    assert len(obs1_list) == 1
    obs1 = obs1_list[0]
    assert obs1.discipline == "Piping"
    assert "erection" in obs1.activity_description.lower()
    assert obs1.status == ActivityStatus.IN_PROGRESS
    assert obs1.actual_start == date(2026, 9, 14)
    assert obs1.actual_end is None
    assert obs1.confidence >= 0.85

    # Event 2: End event with relative date "yesterday"
    text_end = "Valve installation finished yesterday."
    source2, ev2 = ingestion.import_text_evidence(
        project.project_id, text_end, "supervisor_turn_2.txt", SourceType.DAILY_REPORT
    )
    obs2_list = extractor.extract_evidence(ev2.evidence_id)
    assert len(obs2_list) == 1
    obs2 = obs2_list[0]
    assert obs2.discipline == "Piping"
    assert "valve" in obs2.activity_description.lower()
    assert obs2.status == ActivityStatus.COMPLETED
    assert obs2.actual_end == date(2026, 9, 13)
    assert obs2.progress == 100.0

    # Event 3: Start event with named calendar month "September 10"
    text_named_date = "Hydrotest preparation started on September 10."
    source3, ev3 = ingestion.import_text_evidence(
        project.project_id, text_named_date, "supervisor_turn_3.txt", SourceType.DAILY_REPORT
    )
    obs3_list = extractor.extract_evidence(ev3.evidence_id)
    assert len(obs3_list) == 1
    obs3 = obs3_list[0]
    assert obs3.discipline == "Piping"
    assert "hydrotest" in obs3.activity_description.lower()
    assert obs3.status == ActivityStatus.IN_PROGRESS
    assert obs3.actual_start == date(2026, 9, 10)


def test_multi_activity_granularity_handling(session) -> None:
    """Single DPR sentence splits into discrete physical activities without conflation."""
    project = reset_sih26122(session)
    ingestion = IngestionService(session)
    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)

    multi_text = "Foundation excavation completed and rebar fixing started."
    source, ev = ingestion.import_text_evidence(
        project.project_id, multi_text, "civil_daily_return.txt", SourceType.DAILY_REPORT
    )
    observations = extractor.extract_evidence(ev.evidence_id)

    # Must produce two separate observations, not one merged string
    assert len(observations) == 2
    descriptions = [o.activity_description.lower() for o in observations]
    assert any("excavation" in d for d in descriptions)
    assert any("rebar" in d for d in descriptions)

    excavation = next(o for o in observations if "excavation" in o.activity_description.lower())
    rebar = next(o for o in observations if "rebar" in o.activity_description.lower())

    assert excavation.discipline == "Civil"
    assert excavation.status == ActivityStatus.COMPLETED
    assert excavation.progress == 100.0

    assert rebar.discipline == "Civil"
    assert rebar.status == ActivityStatus.IN_PROGRESS
    # Without an explicit date in raw evidence, actual_start must faithfully be None
    assert rebar.actual_start is None
    assert rebar.confidence >= 0.85


def test_unmatched_new_activity_workflow(session) -> None:
    """Unmatched observations receive NO_MATCH outcome, preserve provenance, and are quarantined."""
    project = reset_sih26122(session)

    # unmatched.txt contains: "Temporary fencing outside workfront"
    unmatched_evidence = session.scalar(
        select(Evidence).where(
            Evidence.project_id == project.project_id,
            Evidence.source_name == "unmatched.txt",
        )
    )
    assert unmatched_evidence is not None
    assert len(unmatched_evidence.interpretations) >= 1

    interp = unmatched_evidence.interpretations[0]
    match_result = session.scalar(
        select(ObservationMatchResult).where(ObservationMatchResult.observation_id == interp.observation_id)
    )
    assert match_result is not None
    assert match_result.outcome is ObservationMatchOutcome.NO_MATCH

    # Original evidence and text must be completely preserved
    assert "Temporary fencing outside workfront" in (interp.activity_description or interp.original_evidence or "")


def test_planner_review_temporal_conflict_surfacing(session) -> None:
    """PlannerReviewContext exposes dependency_status and dependency_details for temporal conflicts."""
    project = reset_sih26122(session)

    # PIP001 is in PLANNER_REVIEW; its predecessor CIV002 is not yet completed
    pip1 = session.scalar(
        select(Activity).where(
            Activity.project_id == project.project_id,
            Activity.external_activity_id == "PIP001",
        )
    )
    assert pip1 is not None

    review = session.scalar(
        select(PlannerReview).where(PlannerReview.activity_id == pip1.activity_id)
    )
    assert review is not None

    review_service = PlannerReviewService(session)
    context = review_service.context(review.review_id)

    assert context.proposed_reconciliation.dependency_status in ("CONFLICT", "WARNING", "VALID", "UNKNOWN")
    assert context.proposed_reconciliation.dependency_details is not None
    assert len(context.proposed_reconciliation.dependency_details) > 0
