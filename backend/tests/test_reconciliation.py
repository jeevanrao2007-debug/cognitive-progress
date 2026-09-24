from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.database.models import (
    Activity, ActivityStatus, AuditEvent, Evidence, EvidenceConflict, EvidenceInterpretation,
    ObservationMatchCandidate, ObservationMatchOutcome, ObservationMatchResult, Project,
    ReconciliationDecision, SourceType,
)
from app.modules.reconciliation.service import ReconciliationService


def setup_activity(session) -> Activity:  # type: ignore[no-untyped-def]
    project = Project(name="Reconciliation project")
    activity = Activity(project=project, external_activity_id="PIP001", description="Erect Line 24-XX",
        discipline="Piping", location="Unit 3", level=6, status=ActivityStatus.NOT_STARTED)
    session.add(activity)
    session.commit()
    return activity


def add_matched_observation(session, activity: Activity, source_type: SourceType, source_name: str,
                            timestamp: datetime, status: ActivityStatus, progress: float | None,
                            confidence: float = 0.95, actual_end: date | None = None) -> EvidenceInterpretation:  # type: ignore[no-untyped-def]
    evidence = Evidence(project_id=activity.project_id, source_type=source_type, source_name=source_name,
        source_timestamp=timestamp, raw_text=f"{source_name} evidence", raw_reference=f"{source_name}#1")
    observation = EvidenceInterpretation(evidence=evidence, original_evidence=evidence.raw_text,
        original_reference=evidence.raw_reference, discipline="Piping", location="Unit 3",
        activity_description="24 inch line erection", status=status, actual_start=None, actual_end=actual_end,
        progress=progress, confidence=confidence, provider_name="test", model_name="test", raw_provider_response={})
    result = ObservationMatchResult(interpretation=observation, outcome=ObservationMatchOutcome.MATCHED,
        ambiguity_flag=False, best_score=0.95, high_confidence_threshold=.7,
        ambiguous_score_delta=.08, no_match_threshold=.45)
    candidate = ObservationMatchCandidate(result=result, activity=activity, rank=1, similarity_score=.95,
        contextual_score=.95, final_score=.95, explanation="exact test match")
    session.add(candidate)
    session.commit()
    return observation


def test_agreeing_independent_sources_auto_accept_and_audit(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    when = datetime(2026, 8, 28, 18, tzinfo=UTC)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "supervisor-DPR", when,
        ActivityStatus.COMPLETED, 100, actual_end=date(2026, 8, 28))
    add_matched_observation(session, activity, SourceType.DISCIPLINE_SPREADSHEET, "piping-register", when,
        ActivityStatus.COMPLETED, 100, actual_end=date(2026, 8, 28))

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100
    assert result.decision is ReconciliationDecision.AUTO_ACCEPT
    assert len(result.supporting_evidence) == 2
    assert not result.conflicting_evidence
    assert "supervisor-DPR" in result.explanation
    assert session.scalar(select(AuditEvent).where(AuditEvent.entity_id == result.reconciliation_id)) is not None
    assert activity.status is ActivityStatus.COMPLETED  # high-confidence result updates the internal prototype schedule


def test_contradictory_sources_create_conflict_and_require_planner_review(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    when = datetime(2026, 8, 28, 18, tzinfo=UTC)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "supervisor-report", when,
        ActivityStatus.COMPLETED, 100)
    add_matched_observation(session, activity, SourceType.CONTRACTOR_SPREADSHEET, "contractor-sheet", when,
        ActivityStatus.IN_PROGRESS, 80)
    add_matched_observation(session, activity, SourceType.SITE_DIARY, "site-diary", when,
        ActivityStatus.IN_PROGRESS, None)

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert result.conflicting_evidence
    assert "Conflicting evidence retained for review" in result.explanation
    assert session.scalar(select(EvidenceConflict).where(EvidenceConflict.activity_id == activity.activity_id)) is not None
    assert "Planner review required" in result.recommended_action


def test_fresher_reliable_evidence_wins_but_conflict_is_retained(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    current = datetime(2026, 8, 28, 18, tzinfo=UTC)
    add_matched_observation(session, activity, SourceType.CONTRACTOR_SPREADSHEET, "old-contract", current - timedelta(days=30),
        ActivityStatus.IN_PROGRESS, 80)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "recent-supervisor", current,
        ActivityStatus.COMPLETED, 100)

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert {item.source_name for item in result.conflicting_evidence} == {"old-contract"}


def test_progress_disagreement_without_status_change_is_a_conflict(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    when = datetime(2026, 8, 28, tzinfo=UTC)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "report-100", when,
        ActivityStatus.COMPLETED, 100)
    add_matched_observation(session, activity, SourceType.DISCIPLINE_SPREADSHEET, "register-70", when,
        ActivityStatus.COMPLETED, 70)

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert len(result.conflicting_evidence) == 1
    assert result.conflicting_evidence[0].source_name == "register-70"


def test_no_matched_evidence_creates_no_decision(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.NO_DECISION
    assert result.reconciled_status is ActivityStatus.UNKNOWN
    assert result.reconciled_progress is None
    assert result.supporting_evidence == []


def test_uninterpretable_matched_evidence_is_rejected(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "vague-note", datetime(2026, 8, 28, tzinfo=UTC),
        ActivityStatus.UNKNOWN, None)

    result = ReconciliationService(session).reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.REJECT
    assert result.reconciled_progress is None
