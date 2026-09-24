"""Focused tests for Prompt 17: Cognitive Progress Reconciliation Layer.

Test Scenarios:
A. Agreement: Supervisor + Contractor both report 100% complete -> No conflict, high confidence, auto-accept.
B. Contradiction: Supervisor reports completed vs Contractor reports in progress -> Conflict detected, planner review.
C. Stale evidence: New supervisor completion report + older spreadsheet showing in progress -> Newer direct evidence preferred, stale discrepancy explained.
D. Unknown activity: Low-confidence / unmapped evidence -> Unmatched / planner review required.
E. AI failure: Gemini raises exception / quota exhaustion -> Graceful deterministic safety fallback, never silently fabricate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.ai.interfaces import LLMProvider
from app.database.models import (
    Activity,
    ActivityStatus,
    AuditEvent,
    Evidence,
    EvidenceConflict,
    EvidenceInterpretation,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    PlannerReview,
    Project,
    ReconciliationDecision,
    ReviewDecision,
    SourceType,
)
from app.modules.reconciliation.service import ReconciliationService


def create_activity(
    session: Any,
    external_id: str = "PIP001",
    description: str = "Erect Line 24-XX Process Piping",
    discipline: str = "Piping",
    status: ActivityStatus = ActivityStatus.NOT_STARTED,
) -> Activity:
    project = Project(name=f"Cognitive-Project-{uuid.uuid4().hex[:6]}")
    activity = Activity(
        project=project,
        external_activity_id=external_id,
        description=description,
        discipline=discipline,
        location="Unit 3 - Pipe Rack",
        level=5,
        status=status,
        actual_progress=0.0,
        planned_start=date(2026, 8, 1),
        planned_finish=date(2026, 8, 30),
    )
    session.add(activity)
    session.commit()
    return activity


def add_observation(
    session: Any,
    activity: Activity,
    source_type: SourceType,
    source_name: str,
    timestamp: datetime,
    status: ActivityStatus,
    progress: float | None,
    raw_text: str,
    confidence: float = 0.95,
    match_score: float = 0.95,
    actual_end: date | None = None,
) -> EvidenceInterpretation:
    evidence = Evidence(
        project_id=activity.project_id,
        source_type=source_type,
        source_name=source_name,
        source_timestamp=timestamp,
        raw_text=raw_text,
        raw_reference=f"{source_name}#ref",
    )
    session.add(evidence)
    session.flush()

    observation = EvidenceInterpretation(
        evidence_id=evidence.evidence_id,
        original_evidence=raw_text,
        original_reference=evidence.raw_reference,
        discipline=activity.discipline or "General",
        location=activity.location or "Site",
        activity_description=activity.description,
        status=status,
        actual_start=date(2026, 8, 1) if progress and progress > 0 else None,
        actual_end=actual_end,
        progress=progress,
        confidence=confidence,
        provider_name="gemini",
        model_name="gemini-2.5-flash",
        raw_provider_response={},
    )
    session.add(observation)
    session.flush()

    outcome = ObservationMatchOutcome.MATCHED if match_score >= 0.70 else ObservationMatchOutcome.AMBIGUOUS
    match_result = ObservationMatchResult(
        interpretation=observation,
        outcome=outcome,
        ambiguity_flag=outcome is ObservationMatchOutcome.AMBIGUOUS,
        best_score=match_score,
        high_confidence_threshold=0.70,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.45,
    )
    session.add(match_result)
    session.flush()

    candidate = ObservationMatchCandidate(
        result=match_result,
        activity=activity,
        rank=1,
        similarity_score=match_score,
        contextual_score=match_score,
        final_score=match_score,
        explanation=f"Matched to {activity.external_activity_id}",
    )
    session.add(candidate)
    session.commit()
    return observation


# -------------------------------------------------------------------------
# Test A: Agreement
# Supervisor: "Line 24 erection completed"
# Contractor: "Line 24 erection 100%"
# Expected: No conflict / high-confidence completion / auto-accept.
# -------------------------------------------------------------------------
def test_scenario_a_agreement(session: Any) -> None:
    activity = create_activity(session, external_id="PIP001")
    now = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)

    # Supervisor direct report
    add_observation(
        session,
        activity,
        SourceType.DAILY_REPORT,
        "Supervisor Daily Log",
        now,
        ActivityStatus.COMPLETED,
        100.0,
        "Line 24 erection completed yesterday afternoon.",
        actual_end=date(2026, 8, 28),
    )

    # Contractor progress register
    add_observation(
        session,
        activity,
        SourceType.DISCIPLINE_SPREADSHEET,
        "Contractor Progress Tracker",
        now,
        ActivityStatus.COMPLETED,
        100.0,
        "Line 24 erection 100% complete and inspected.",
        actual_end=date(2026, 8, 28),
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0
    assert result.decision is ReconciliationDecision.AUTO_ACCEPT
    assert result.confidence >= 0.85
    assert len(result.supporting_evidence) == 2
    assert len(result.conflicting_evidence) == 0

    # Activity schedule updated
    session.refresh(activity)
    assert activity.status is ActivityStatus.COMPLETED
    assert activity.actual_progress == 100.0

    # Audit recorded
    audits = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id == result.reconciliation_id)))
    assert len(audits) >= 1
    assert "reconciled" in audits[0].explanation.lower() or "auto" in audits[0].explanation.lower()


# -------------------------------------------------------------------------
# Test B: Contradiction
# Supervisor: "Line 24 erection completed"
# Contractor: "Line 24 erection in progress"
# Expected: Conflict detected, planner review required.
# -------------------------------------------------------------------------
def test_scenario_b_contradiction(session: Any) -> None:
    activity = create_activity(session, external_id="PIP001")
    now = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)

    # Supervisor direct report
    add_observation(
        session,
        activity,
        SourceType.DAILY_REPORT,
        "Supervisor Report",
        now,
        ActivityStatus.COMPLETED,
        100.0,
        "Line 24 erection completed.",
        actual_end=date(2026, 8, 29),
    )

    # Contractor spreadsheet contradicts contemporary progress
    add_observation(
        session,
        activity,
        SourceType.DISCIPLINE_SPREADSHEET,
        "Contractor Report",
        now - timedelta(hours=2),
        ActivityStatus.IN_PROGRESS,
        60.0,
        "Line 24 erection in progress, welding ongoing.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    # Conflict must be detected and require planner review
    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert len(result.conflicting_evidence) >= 1
    assert len(result.supporting_evidence) >= 1

    # Conflict record created
    conflicts = list(session.scalars(select(EvidenceConflict).where(EvidenceConflict.activity_id == activity.activity_id)))
    assert len(conflicts) >= 1

    # Planner review queue item created
    reviews = list(session.scalars(select(PlannerReview).where(PlannerReview.activity_id == activity.activity_id)))
    assert len(reviews) >= 1
    assert reviews[0].reviewer_decision is ReviewDecision.PENDING

    # Schedule is not silently overwritten
    session.refresh(activity)
    assert activity.status is not ActivityStatus.COMPLETED


# -------------------------------------------------------------------------
# Test C: Stale evidence
# New supervisor completion report + older spreadsheet showing in-progress.
# Expected: Conflict recognized, newer/direct evidence preferred, stale evidence explained.
# -------------------------------------------------------------------------
def test_scenario_c_stale_evidence(session: Any) -> None:
    activity = create_activity(session, external_id="PIP001")
    fresh_time = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)
    stale_time = fresh_time - timedelta(days=16)  # Older than 14-day freshness window

    # Newer direct supervisor completion report
    add_observation(
        session,
        activity,
        SourceType.DAILY_REPORT,
        "Supervisor Fresh DPR",
        fresh_time,
        ActivityStatus.COMPLETED,
        100.0,
        "Line 24 erection completed today.",
        actual_end=date(2026, 8, 29),
    )

    # Older spreadsheet showing earlier in-progress state
    add_observation(
        session,
        activity,
        SourceType.DISCIPLINE_SPREADSHEET,
        "Old Subcontractor Tracker",
        stale_time,
        ActivityStatus.IN_PROGRESS,
        50.0,
        "Line 24 erection in progress.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    # Should recognize stale discrepancy and prefer the fresh supervisor report
    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0
    assert result.decision is ReconciliationDecision.PLANNER_REVIEW

    # Stale evidence flagged in conflicting_evidence metadata
    assert len(result.conflicting_evidence) >= 1
    stale_item = result.conflicting_evidence[0]
    assert stale_item.is_stale is True
    assert "stale" in result.explanation.lower() or "superseded" in result.explanation.lower()

    # Schedule is protected from silent overwrite until planner reviews
    session.refresh(activity)
    assert activity.status is ActivityStatus.NOT_STARTED


# -------------------------------------------------------------------------
# Test D: Unknown activity
# Evidence describes an activity that cannot confidently map to the schedule.
# Expected: Unmatched / planner review / schedule untouched.
# -------------------------------------------------------------------------
def test_scenario_d_unknown_activity(session: Any) -> None:
    activity = create_activity(session, external_id="PIP001", description="Line 24 Pipe Erection")
    now = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)

    # Low match confidence observation (score 0.40, below no_match / ambiguous threshold)
    add_observation(
        session,
        activity,
        SourceType.SITE_DIARY,
        "Handwritten Diary",
        now,
        ActivityStatus.IN_PROGRESS,
        40.0,
        "Poured concrete at substation perimeter fence.",
        match_score=0.40,
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    # Because match score is low (< 0.70 threshold), safety gate leaves in unmatched / planner review state
    assert result.decision in (ReconciliationDecision.NO_DECISION, ReconciliationDecision.PLANNER_REVIEW)
    assert result.confidence < 0.70

    # Schedule remains untouched
    session.refresh(activity)
    assert activity.status is ActivityStatus.NOT_STARTED
    assert activity.actual_progress == 0.0


# -------------------------------------------------------------------------
# Test E: AI Failure
# Gemini unavailable / raises an exception.
# Expected: Existing deterministic error handling remains safe.
# Never silently fabricate an AI explanation.
# -------------------------------------------------------------------------
def test_scenario_e_ai_failure_safe_fallback(session: Any) -> None:
    activity = create_activity(session, external_id="PIP001")
    now = datetime(2026, 8, 29, 17, 0, tzinfo=UTC)

    add_observation(
        session,
        activity,
        SourceType.DAILY_REPORT,
        "Supervisor DPR",
        now,
        ActivityStatus.COMPLETED,
        100.0,
        "Line 24 erection completed.",
        actual_end=date(2026, 8, 29),
    )

    # Mock an AI provider that fails (e.g. Quota exhausted or Network timeout)
    failing_ai = MagicMock(spec=LLMProvider)
    failing_ai.provider_name = "gemini"
    failing_ai.model_name = "gemini-2.5-flash"
    failing_ai.explain_reconciliation.side_effect = RuntimeError("ResourceExhausted: 429 Quota Exceeded")

    service = ReconciliationService(session, llm_provider=failing_ai)
    result = service.reconcile_activity(activity.activity_id)

    # Must not crash! Deterministic safety gate executes successfully
    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0
    assert result.decision is ReconciliationDecision.AUTO_ACCEPT
    assert "Supervisor DPR" in result.explanation
    # AI failure handled gracefully without crashing
    assert result.confidence > 0.0
