"""Internal schedule database updates for the prototype; no external scheduler integration."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.database.models import Activity, ActivityStatus, AuditAction, PlannerReview, Reconciliation, ScheduleUpdate
from app.modules.audit.service import AuditService


class ScheduleUpdateService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def apply(self, activity: Activity, reconciliation: Reconciliation, *, decision_source: str,
              reason: str, review: PlannerReview | None = None, status: ActivityStatus | None = None,
              progress: float | None = None, actual_start: date | None = None,
              actual_end: date | None = None) -> ScheduleUpdate:
        previous = self._state(activity)
        new_status = status or reconciliation.reconciled_status
        new_progress = reconciliation.reconciled_progress if progress is None else progress
        new_start = reconciliation.actual_start if actual_start is None else actual_start
        new_end = reconciliation.actual_end if actual_end is None else actual_end
        activity.status = new_status
        activity.actual_progress = new_progress
        activity.actual_start = new_start
        activity.actual_end = new_end
        new_value = self._state(activity)
        update = ScheduleUpdate(activity_id=activity.activity_id, reconciliation_id=reconciliation.reconciliation_id,
            review_id=review.review_id if review else None, previous_value=previous, new_value=new_value,
            reason=reason, evidence=reconciliation.supporting_evidence + reconciliation.conflicting_evidence,
            decision_source=decision_source)
        self.session.add(update)
        self.session.flush()
        AuditService(self.session).record("schedule_update", update.update_id, AuditAction.UPDATED, previous,
            new_value, reason, decision_source)
        return update

    @staticmethod
    def _state(activity: Activity) -> dict[str, object]:
        return {
            "status": activity.status.value,
            "actual_progress": activity.actual_progress,
            "actual_start": activity.actual_start.isoformat() if activity.actual_start else None,
            "actual_end": activity.actual_end.isoformat() if activity.actual_end else None,
        }
