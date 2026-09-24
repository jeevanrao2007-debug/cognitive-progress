"""Human approval workflow for reconciliation recommendations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import (Activity, AuditAction, AuditEvent, EvidenceInterpretation,
    ObservationMatchCandidate, ObservationMatchResult, PlannerReview, Reconciliation, ReviewDecision,
    ScheduleUpdate)
from app.modules.audit.service import AuditService
from app.modules.matching.schemas import CandidateActivityResponse
from app.modules.planner_review.schemas import (ActivityState, AuditEntry, PlannerActionRequest,
    PlannerReviewContext)
from app.modules.reconciliation.service import ReconciliationService
from app.modules.schedule.updates import ScheduleUpdateService


class PlannerReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_review(self, reconciliation: Reconciliation, reason: str) -> PlannerReview:
        review = PlannerReview(activity_id=reconciliation.activity_id, reconciliation_id=reconciliation.reconciliation_id,
            reason=reason, proposed_decision=ReviewDecision.ACCEPT, reviewer_decision=ReviewDecision.PENDING)
        self.session.add(review)
        self.session.flush()
        AuditService(self.session).record("planner_review", review.review_id, AuditAction.CREATED, None,
            {"reconciliation_id": str(reconciliation.reconciliation_id), "reason": reason}, reason,
            "reconciliation-engine")
        return review

    def context(self, review_id: uuid.UUID) -> PlannerReviewContext:
        from app.database.models import ActivityDependency
        from app.modules.schedule.temporal_validation import TemporalValidationEngine

        review = self.session.scalar(
            select(PlannerReview)
            .where(PlannerReview.review_id == review_id)
            .options(
                selectinload(PlannerReview.activity)
                .selectinload(Activity.predecessors)
                .selectinload(ActivityDependency.predecessor),
                selectinload(PlannerReview.reconciliation),
            )
        )
        if review is None or review.reconciliation is None:
            raise ValueError("Planner review does not exist.")
        reconciliation = review.reconciliation
        evidence_ids = [uuid.UUID(item["observation_id"]) for item in (
            reconciliation.supporting_evidence + reconciliation.conflicting_evidence)]
        candidates = self._candidates(evidence_ids)
        update_ids = list(self.session.scalars(select(ScheduleUpdate.update_id).where(
            (ScheduleUpdate.review_id == review.review_id)
            | (ScheduleUpdate.reconciliation_id == reconciliation.reconciliation_id))))
        entity_ids = [review.review_id, reconciliation.reconciliation_id, review.activity_id, *update_ids]
        if review.selected_activity_id is not None:
            entity_ids.append(review.selected_activity_id)
        audit = list(self.session.scalars(select(AuditEvent).where(
            AuditEvent.entity_id.in_(entity_ids)).order_by(AuditEvent.created_at.desc())))

        temporal_result = (
            TemporalValidationEngine.validate(
                review.activity,
                proposed_status=reconciliation.reconciled_status,
                proposed_start=reconciliation.actual_start,
                proposed_end=reconciliation.actual_end,
                proposed_progress=reconciliation.reconciled_progress,
            )
            if review.activity
            else None
        )
        response = ReconciliationService._response(reconciliation, temporal_result=temporal_result)
        return PlannerReviewContext(review_id=review.review_id, reviewer_decision=review.reviewer_decision,
            reviewer_comment=review.reviewer_comment, reason=review.reason, current_activity=self._state(review.activity),
            proposed_reconciliation=response, supporting_evidence=response.supporting_evidence,
            conflicting_evidence=response.conflicting_evidence, match_candidates=candidates,
            audit_history=[AuditEntry(audit_id=item.audit_id, action=item.action.value, actor=item.actor,
                explanation=item.explanation, created_at=item.created_at) for item in audit])

    def act(self, review_id: uuid.UUID, request: PlannerActionRequest) -> PlannerReviewContext:
        review = self.session.get(PlannerReview, review_id)
        if review is None or review.reconciliation is None:
            raise ValueError("Planner review does not exist.")
        if review.reviewer_decision is not ReviewDecision.PENDING and request.action != "comment":
            raise ValueError("Planner review has already been decided.")
        reconciliation = review.reconciliation
        target = review.activity
        if request.selected_activity_id:
            target = self._valid_selected_activity(request.selected_activity_id, reconciliation)
            review.selected_activity_id = target.activity_id
        before = {"decision": review.reviewer_decision.value, "comment": review.reviewer_comment,
            "selected_activity_id": str(review.selected_activity_id) if review.selected_activity_id else None}
        review.reviewer = request.reviewer
        if request.comment is not None:
            review.reviewer_comment = request.comment
        reason = request.comment or review.reason
        if request.action == "comment":
            AuditService(self.session).record("planner_review", review.review_id, AuditAction.REVIEWED, before,
                {"comment": review.reviewer_comment}, "Planner comment added.", request.reviewer)
            self.session.commit()
            return self.context(review_id)
        if request.action == "reject":
            review.reviewer_decision = ReviewDecision.REJECT
            review.reviewed_at = self._now()
            AuditService(self.session).record("planner_review", review.review_id, AuditAction.REVIEWED, before,
                {"decision": "reject", "comment": review.reviewer_comment}, reason, request.reviewer)
        else:
            is_override = request.action in {"modify", "select_activity"}
            review.reviewer_decision = ReviewDecision.OVERRIDE if is_override else ReviewDecision.ACCEPT
            review.reviewed_at = self._now()
            ScheduleUpdateService(self.session).apply(target, reconciliation, review=review,
                decision_source=f"planner:{request.reviewer}", reason=reason,
                status=request.status, progress=request.progress, actual_start=request.actual_start,
                actual_end=request.actual_end)
            AuditService(self.session).record("planner_review", review.review_id, AuditAction.REVIEWED, before,
                {"decision": review.reviewer_decision.value, "target_activity_id": str(target.activity_id),
                 "comment": review.reviewer_comment}, reason, request.reviewer)
        self.session.commit()
        return self.context(review_id)

    def _valid_selected_activity(self, activity_id: uuid.UUID, reconciliation: Reconciliation) -> Activity:
        evidence_ids = [uuid.UUID(item["observation_id"]) for item in (
            reconciliation.supporting_evidence + reconciliation.conflicting_evidence)]
        candidate = self.session.scalar(select(ObservationMatchCandidate).join(ObservationMatchCandidate.result).where(
            ObservationMatchCandidate.activity_id == activity_id,
            ObservationMatchResult.observation_id.in_(evidence_ids)))
        if candidate is None:
            raise ValueError("Selected activity is not a candidate for this reconciliation evidence.")
        activity = self.session.get(Activity, activity_id)
        if activity is None:
            raise ValueError("Selected activity does not exist.")
        return activity

    def _candidates(self, observation_ids: list[uuid.UUID]) -> list[CandidateActivityResponse]:
        if not observation_ids:
            return []
        rows = self.session.execute(select(ObservationMatchCandidate).join(ObservationMatchCandidate.result).where(
            ObservationMatchResult.observation_id.in_(observation_ids)).options(
            selectinload(ObservationMatchCandidate.activity))).scalars()
        return [CandidateActivityResponse(activity_id=row.activity_id, external_activity_id=row.activity.external_activity_id,
            description=row.activity.description, discipline=row.activity.discipline, location=row.activity.location,
            level=row.activity.level, similarity_score=row.similarity_score, contextual_score=row.contextual_score,
            final_score=row.final_score, explanation=row.explanation) for row in rows]

    @staticmethod
    def _state(activity: Activity) -> ActivityState:
        return ActivityState(activity_id=activity.activity_id, external_activity_id=activity.external_activity_id,
            description=activity.description, status=activity.status, actual_progress=activity.actual_progress,
            actual_start=activity.actual_start, actual_end=activity.actual_end)

    @staticmethod
    def _now():
        from datetime import UTC, datetime
        return datetime.now(UTC)
