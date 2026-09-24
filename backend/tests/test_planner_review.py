from datetime import UTC, datetime

from sqlalchemy import select

from app.database.models import ActivityStatus, AuditEvent, PlannerReview, ReviewDecision, ScheduleUpdate, SourceType
from app.modules.planner_review.schemas import PlannerActionRequest
from app.modules.planner_review.service import PlannerReviewService
from app.modules.reconciliation.service import ReconciliationService
from tests.test_reconciliation import add_matched_observation, setup_activity


def create_conflicted_review(session):  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    timestamp = datetime(2026, 8, 28, tzinfo=UTC)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "supervisor", timestamp,
        ActivityStatus.COMPLETED, 100)
    add_matched_observation(session, activity, SourceType.CONTRACTOR_SPREADSHEET, "contractor", timestamp,
        ActivityStatus.IN_PROGRESS, 70)
    reconciliation = ReconciliationService(session).reconcile_activity(activity.activity_id)
    review = session.scalar(select(PlannerReview).where(PlannerReview.reconciliation_id == reconciliation.reconciliation_id))
    assert review is not None
    return activity, reconciliation, review


def test_automatic_high_confidence_update_preserves_values_and_source(session) -> None:  # type: ignore[no-untyped-def]
    activity = setup_activity(session)
    add_matched_observation(session, activity, SourceType.DAILY_REPORT, "supervisor", datetime(2026, 8, 28, tzinfo=UTC),
        ActivityStatus.COMPLETED, 100)

    reconciliation = ReconciliationService(session).reconcile_activity(activity.activity_id)
    update = session.scalar(select(ScheduleUpdate).where(ScheduleUpdate.reconciliation_id == reconciliation.reconciliation_id))

    assert update is not None
    assert update.previous_value["status"] == "not_started"
    assert update.new_value["status"] == "completed"
    assert update.decision_source == "automatic:reconciliation"
    assert update.evidence


def test_planner_approval_applies_reconciliation(session) -> None:  # type: ignore[no-untyped-def]
    activity, reconciliation, review = create_conflicted_review(session)

    context = PlannerReviewService(session).act(review.review_id, PlannerActionRequest(
        action="approve", reviewer="planner.a", comment="Verified against field call."))

    assert context.reviewer_decision is ReviewDecision.ACCEPT
    assert activity.actual_progress == reconciliation.reconciled_progress
    update = session.scalar(select(ScheduleUpdate).where(ScheduleUpdate.review_id == review.review_id))
    assert update is not None
    assert update.decision_source == "planner:planner.a"


def test_planner_rejection_keeps_schedule_unchanged(session) -> None:  # type: ignore[no-untyped-def]
    activity, _reconciliation, review = create_conflicted_review(session)

    context = PlannerReviewService(session).act(review.review_id, PlannerActionRequest(
        action="reject", reviewer="planner.b", comment="Awaiting inspected quantity."))

    assert context.reviewer_decision is ReviewDecision.REJECT
    assert activity.status is ActivityStatus.NOT_STARTED
    assert session.scalar(select(ScheduleUpdate).where(ScheduleUpdate.review_id == review.review_id)) is None


def test_planner_modification_applies_override(session) -> None:  # type: ignore[no-untyped-def]
    activity, _reconciliation, review = create_conflicted_review(session)

    context = PlannerReviewService(session).act(review.review_id, PlannerActionRequest(
        action="modify", reviewer="planner.c", comment="Verified 90 percent completed.",
        status=ActivityStatus.IN_PROGRESS, progress=90))

    assert context.reviewer_decision is ReviewDecision.OVERRIDE
    assert activity.status is ActivityStatus.IN_PROGRESS
    assert activity.actual_progress == 90


def test_planner_action_and_schedule_update_are_audited(session) -> None:  # type: ignore[no-untyped-def]
    _activity, _reconciliation, review = create_conflicted_review(session)
    PlannerReviewService(session).act(review.review_id, PlannerActionRequest(
        action="approve", reviewer="planner.audit", comment="Approved."))

    events = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id == review.review_id)))
    assert any(event.action.value == "reviewed" for event in events)
    assert session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "schedule_update")) is not None
    assert any(item.action == "updated" for item in PlannerReviewService(session).context(review.review_id).audit_history)
