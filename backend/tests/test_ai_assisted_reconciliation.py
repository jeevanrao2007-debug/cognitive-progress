import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

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
    SourceType,
)
from app.modules.reconciliation.service import ReconciliationService


def create_test_activity(
    session: Any,
    external_id: str = "GENERIC-ACT-001",
    description: str = "Erect 24-inch process piping",
    discipline: str = "Piping",
    location: str = "Area 4",
) -> Activity:
    project = Project(name=f"Project-{uuid.uuid4().hex[:6]}")
    activity = Activity(
        project=project,
        external_activity_id=external_id,
        description=description,
        discipline=discipline,
        location=location,
        level=5,
        status=ActivityStatus.NOT_STARTED,
        actual_progress=0.0,
    )
    session.add(activity)
    session.commit()
    return activity


def add_test_observation(
    session: Any,
    activity: Activity,
    source_type: SourceType,
    source_name: str,
    timestamp: datetime,
    status: ActivityStatus,
    progress: float | None,
    raw_text: str = "Observation text",
    confidence: float = 0.95,
    match_score: float = 0.95,
    actual_start: date | None = None,
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
    observation = EvidenceInterpretation(
        evidence=evidence,
        original_evidence=raw_text,
        original_reference=evidence.raw_reference,
        discipline=activity.discipline,
        location=activity.location,
        activity_description=activity.description,
        status=status,
        actual_start=actual_start,
        actual_end=actual_end,
        progress=progress,
        confidence=confidence,
        provider_name="test-provider",
        model_name="test-model",
        raw_provider_response={},
    )
    outcome = (
        ObservationMatchOutcome.MATCHED
        if match_score >= 0.70
        else ObservationMatchOutcome.NEEDS_REVIEW
    )
    result = ObservationMatchResult(
        interpretation=observation,
        outcome=outcome,
        ambiguity_flag=False,
        best_score=match_score,
        high_confidence_threshold=0.70,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.45,
    )
    candidate = ObservationMatchCandidate(
        result=result,
        activity=activity,
        rank=1,
        similarity_score=match_score,
        contextual_score=match_score,
        final_score=match_score,
        explanation="Test match score",
    )
    session.add(candidate)
    session.commit()
    return observation


class MockMalformedProvider(LLMProvider):
    def extract_evidence(self, raw_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def normalize_activity(self, activity_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def explain_reconciliation(self, prompt_or_data: Any) -> dict[str, Any] | str:
        return "MALFORMED_NON_JSON_RESPONSE: <!DOCTYPE html><html>500 Server Error</html>"


class MockSpecificRecommendationProvider(LLMProvider):
    def __init__(self, response_dict: dict[str, Any]) -> None:
        self.response_dict = response_dict

    def extract_evidence(self, raw_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def normalize_activity(self, activity_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def explain_reconciliation(self, prompt_or_data: Any) -> dict[str, Any] | str:
        return json.dumps(self.response_dict)


# Test 1: Multiple agreeing sources -> high-confidence completion -> auto-accepted
def test_agreeing_evidence_sources_auto_accepted(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-101")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="24-inch process piping erection 100% completed and inspected.",
        actual_end=date(2026, 9, 10),
    )
    add_test_observation(
        session,
        activity,
        source_type=SourceType.DISCIPLINE_SPREADSHEET,
        source_name="QA/QC Register",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Line 24 erection complete, signed off.",
        actual_end=date(2026, 9, 10),
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.AUTO_ACCEPT
    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0
    assert result.conflict_detected is False
    assert len(result.supporting_evidence) == 2
    assert len(result.conflicting_evidence) == 0

    # Deterministic schedule actuation check
    assert activity.status is ActivityStatus.COMPLETED
    assert activity.actual_progress == 100.0


# Test 2: Conflicting evidence -> conflict detected (killer conflict case)
def test_killer_conflicting_evidence_conflict_detected(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-102")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    # Observation A: Supervisor -> 100% completed
    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor Report",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="24-inch line erection completed.",
    )
    # Observation B: Contractor spreadsheet -> 80% in_progress
    add_test_observation(
        session,
        activity,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="Contractor Spreadsheet",
        timestamp=now,
        status=ActivityStatus.IN_PROGRESS,
        progress=80.0,
        raw_text="Line 24 installation = 80%.",
    )
    # Observation C: Site diary -> None in_progress
    add_test_observation(
        session,
        activity,
        source_type=SourceType.SITE_DIARY,
        source_name="Site Diary",
        timestamp=now,
        status=ActivityStatus.IN_PROGRESS,
        progress=None,
        raw_text="Line erection ongoing.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.conflict_detected is True
    assert len(result.conflicting_evidence) > 0


# Test 3: Conflicting evidence -> planner review recommended with clear explanation
def test_conflicting_evidence_routes_to_planner_review(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-103")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor Daily",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Line erection completed.",
    )
    add_test_observation(
        session,
        activity,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="Contractor Sheet",
        timestamp=now,
        status=ActivityStatus.IN_PROGRESS,
        progress=80.0,
        raw_text="Line 24 at 80%.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert "Planner review required" in result.recommended_action or "review" in result.recommended_action.lower()
    assert len(result.explanation) > 20

    # Verify PlannerReview entry created
    reviews = list(
        session.scalars(
            select(PlannerReview).where(PlannerReview.reconciliation_id == result.reconciliation_id)
        )
    )
    assert len(reviews) == 1
    assert reviews[0].activity_id == activity.activity_id

    # Verify EvidenceConflict created
    conflicts = list(
        session.scalars(
            select(EvidenceConflict).where(EvidenceConflict.activity_id == activity.activity_id)
        )
    )
    assert len(conflicts) > 0


# Test 4: Low match confidence -> no automatic schedule update
def test_low_match_confidence_blocks_automatic_update(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-104")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    # Observation with low match score (< 0.70 threshold)
    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Vague DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Some piping was worked on.",
        match_score=0.62,
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert "low" in result.explanation.lower() or "confidence" in result.explanation.lower()
    # Schedule must NOT be auto-updated
    assert activity.status is ActivityStatus.NOT_STARTED
    assert activity.actual_progress == 0.0


# Test 5: Invalid date sequence returned by Gemini -> rejected or planner review
def test_invalid_date_sequence_routes_to_planner_review(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-105")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Erection finished.",
    )

    # Provider returning invalid temporal sequence: actual_end (Sept 5) < actual_start (Sept 15)
    invalid_dates_provider = MockSpecificRecommendationProvider({
        "recommended_status": "completed",
        "recommended_progress": 100.0,
        "recommended_actual_start": "2026-09-15",
        "recommended_actual_end": "2026-09-05",
        "evidence_assessment": "Invalid date sequence test",
        "conflict_detected": False,
        "conflict_summary": None,
        "reasoning": "Completed test with inverted dates.",
        "confidence": 0.95,
        "supporting_observations": [],
        "contradictory_observations": [],
    })

    service = ReconciliationService(session, llm_provider=invalid_dates_provider)
    result = service.reconcile_activity(activity.activity_id)

    # Must be routed to review or rejected; never auto accepted
    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    assert "temporal" in result.explanation.lower() or "invalid" in result.explanation.lower()
    assert activity.status is ActivityStatus.NOT_STARTED


# Test 6: Invalid progress value returned by Gemini (<0 or >100) -> rejected
def test_invalid_progress_value_rejected(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-106")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.IN_PROGRESS,
        progress=50.0,
        raw_text="Progressing.",
    )

    invalid_progress_provider = MockSpecificRecommendationProvider({
        "recommended_status": "in_progress",
        "recommended_progress": 145.0,  # Invalid: > 100%
        "recommended_actual_start": None,
        "recommended_actual_end": None,
        "evidence_assessment": "Out of range progress",
        "conflict_detected": False,
        "conflict_summary": None,
        "reasoning": "Progress reported over 100%",
        "confidence": 0.9,
        "supporting_observations": [],
        "contradictory_observations": [],
    })

    service = ReconciliationService(session, llm_provider=invalid_progress_provider)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.REJECT
    assert "outside valid range" in result.explanation.lower()
    assert activity.status is ActivityStatus.NOT_STARTED
    assert activity.actual_progress == 0.0


# Test 7: Gemini provider malformed response -> safe failure, no crash
def test_gemini_malformed_response_safe_failure(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-107")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Line erection completed.",
    )

    malformed_provider = MockMalformedProvider()
    service = ReconciliationService(session, llm_provider=malformed_provider)

    # Must complete safely without unhandled exception
    result = service.reconcile_activity(activity.activity_id)
    assert result.reconciliation_id is not None
    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0


# Test 8: Gemini recommendation cannot directly update schedule (schedule unchanged on review/reject)
def test_gemini_cannot_directly_update_schedule_on_review(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-108")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    # Two conflicting observations
    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Line erection completed.",
    )
    add_test_observation(
        session,
        activity,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="Contractor Report",
        timestamp=now,
        status=ActivityStatus.IN_PROGRESS,
        progress=80.0,
        raw_text="Line 24 at 80%.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.PLANNER_REVIEW
    # Verify schedule state was NOT altered directly by Gemini or reconciliation
    assert activity.status is ActivityStatus.NOT_STARTED
    assert activity.actual_progress == 0.0


# Test 9: Audit trail records all evidence and reasoning
def test_audit_trail_records_all_evidence_and_reasoning(session: Any) -> None:
    activity = create_test_activity(session, external_id="ACT-PIPE-109")
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    obs = add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Supervisor DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Line 24 erection complete.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    audit_event = session.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == result.reconciliation_id)
    )
    assert audit_event is not None
    assert audit_event.entity_type == "reconciliation"
    assert audit_event.action.value == "created" or audit_event.action == "created"
    assert audit_event.after_value is not None
    assert "activity_id" in audit_event.after_value
    assert "decision" in audit_event.after_value
    assert "confidence" in audit_event.after_value
    assert "supporting_evidence" in audit_event.after_value
    assert "deterministic_validation" in audit_event.after_value
    assert str(obs.observation_id) in audit_event.after_value["supporting_evidence"]


# Test 10: No hard-coded demo activity logic (works with generic activity IDs)
def test_generic_activity_ids_no_hardcoded_logic(session: Any) -> None:
    # Completely arbitrary ID and discipline
    activity = create_test_activity(
        session,
        external_id="TURB-ELEC-XYZ-9999",
        description="Assemble cryogenic turbine manifold sensor harness",
        discipline="Instrumentation",
        location="Zone B - Substation 9",
    )
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)

    add_test_observation(
        session,
        activity,
        source_type=SourceType.DAILY_REPORT,
        source_name="Specialist DPR",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Turbine manifold sensor harness assembly completed.",
    )
    add_test_observation(
        session,
        activity,
        source_type=SourceType.SITE_DIARY,
        source_name="Shift Log",
        timestamp=now,
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        raw_text="Sensor harness assembled and tested.",
    )

    service = ReconciliationService(session)
    result = service.reconcile_activity(activity.activity_id)

    assert result.decision is ReconciliationDecision.AUTO_ACCEPT
    assert result.reconciled_status is ActivityStatus.COMPLETED
    assert result.reconciled_progress == 100.0
    assert activity.external_activity_id == "TURB-ELEC-XYZ-9999"
    assert activity.status is ActivityStatus.COMPLETED
