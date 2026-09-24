from sqlalchemy import select

from app.database.demo import DEMO_NAME, reset_sih26122
from app.database.models import (Activity, ActivityStatus, Evidence, EvidenceInterpretation, ObservationMatchCandidate,
    ObservationMatchOutcome, ObservationMatchResult, PlannerReview, Reconciliation, ReconciliationDecision, ScheduleUpdate)


def test_sih26122_demo_executes_full_chain_and_resets(session) -> None:  # type: ignore[no-untyped-def]
    project = reset_sih26122(session)
    assert project.name == DEMO_NAME
    assert len(list(session.scalars(select(Activity).where(Activity.project_id == project.project_id)))) == 10
    assert len(list(session.scalars(select(Evidence).where(Evidence.project_id == project.project_id)))) == 8
    pip = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "PIP001"))
    assert pip is not None
    reconciliation = session.scalar(select(Reconciliation).where(Reconciliation.activity_id == pip.activity_id))
    assert reconciliation is not None
    assert reconciliation.decision is ReconciliationDecision.PLANNER_REVIEW
    assert session.scalar(select(PlannerReview).where(PlannerReview.reconciliation_id == reconciliation.reconciliation_id)) is not None
    auto = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "ELEC001"))
    assert auto is not None and auto.status is ActivityStatus.COMPLETED
    assert session.scalar(select(ScheduleUpdate).where(ScheduleUpdate.activity_id == auto.activity_id)) is not None
    outcomes = set(session.scalars(select(ObservationMatchResult.outcome).join(ObservationMatchResult.interpretation).join(Evidence).where(Evidence.project_id == project.project_id)))
    assert ObservationMatchOutcome.AMBIGUOUS in outcomes
    assert ObservationMatchOutcome.NO_MATCH in outcomes
    replacement = reset_sih26122(session)
    assert replacement.project_id == project.project_id
    assert len(list(session.scalars(select(Activity).where(Activity.project_id == replacement.project_id)))) == 10
