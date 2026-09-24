"""Read-only project dashboard projections for the planner workspace."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.routes.imports import get_session
from app.database.models import (Activity, ActivityStatus, AuditEvent, Evidence,
    EvidenceConflict, EvidenceInterpretation, ObservationMatchCandidate, ObservationMatchResult,
    PlannerReview, Reconciliation, ReviewDecision, ScheduleUpdate)
from app.database.repositories import ProjectRepository

router = APIRouter(prefix="/projects/{project_id}/dashboard")


class ActivityRow(BaseModel):
    activity_id: uuid.UUID
    external_activity_id: str
    discipline: str | None
    description: str
    planned_start: date | None
    planned_finish: date | None
    actual_start: date | None
    actual_end: date | None
    progress: float | None
    status: ActivityStatus
    level: int | None = 5
    location: str | None = None
    confidence: float | None
    evidence_status: str
    dependency_status: str | None = "VALID"


class Overview(BaseModel):
    overall_progress: float
    planned_progress: float
    planned_vs_actual_delta: float
    total_activities: int
    completed_activities: int
    ongoing_activities: int
    delayed_activities: int
    conflicts: int
    planner_reviews: int
    high_risk_activities: int


class ConflictRow(BaseModel):
    conflict_id: uuid.UUID
    activity_id: uuid.UUID
    activity: str
    conflict_type: str
    sources: str
    severity: str
    resolution_status: str


class EvidenceRow(BaseModel):
    evidence_id: uuid.UUID
    source_name: str
    source_type: str
    source_timestamp: datetime
    raw_text: str | None
    raw_reference: str | None
    interpretations: list[dict[str, object]]


class AuditRow(BaseModel):
    audit_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    actor: str
    before_value: dict[str, object] | None
    after_value: dict[str, object] | None
    explanation: str | None
    created_at: datetime


class DashboardResponse(BaseModel):
    overview: Overview
    activities: list[ActivityRow]
    reconciliations: list[dict[str, object]]
    conflicts: list[ConflictRow]
    evidence: list[EvidenceRow]
    audit_trail: list[AuditRow]
    pipeline: list[dict[str, object]]


@router.get("", response_model=DashboardResponse)
def get_dashboard(project_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]) -> DashboardResponse:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    from app.database.models import ActivityDependency
    from app.modules.schedule.temporal_validation import TemporalValidationEngine

    activities = list(
        session.scalars(
            select(Activity)
            .where(Activity.project_id == project_id)
            .options(
                selectinload(Activity.predecessors).selectinload(ActivityDependency.predecessor)
            )
            .order_by(Activity.external_activity_id)
        )
    )
    activity_ids = [item.activity_id for item in activities]
    act_map = {item.activity_id: item for item in activities}
    recs = list(session.scalars(select(Reconciliation).where(Reconciliation.activity_id.in_(activity_ids)).order_by(Reconciliation.created_at.desc()))) if activity_ids else []
    latest: dict[uuid.UUID, Reconciliation] = {}
    for rec in recs:
        latest.setdefault(rec.activity_id, rec)
    interpretations = list(session.scalars(select(EvidenceInterpretation).join(Evidence).where(Evidence.project_id == project_id).options(selectinload(EvidenceInterpretation.evidence), selectinload(EvidenceInterpretation.match_results).selectinload(ObservationMatchResult.candidates))))
    evidence = list(
        session.scalars(
            select(Evidence)
            .where(Evidence.project_id == project_id)
            .options(
                selectinload(Evidence.interpretations)
                .selectinload(EvidenceInterpretation.match_results)
                .selectinload(ObservationMatchResult.candidates)
                .selectinload(ObservationMatchCandidate.activity)
            )
            .order_by(Evidence.source_timestamp.desc())
        )
    )
    conflicts = list(session.scalars(select(EvidenceConflict).where(EvidenceConflict.activity_id.in_(activity_ids)).options(selectinload(EvidenceConflict.activity)))) if activity_ids else []
    all_reviews = list(session.scalars(select(PlannerReview).join(PlannerReview.activity).where(Activity.project_id == project_id)))
    reviews = [item for item in all_reviews if item.reviewer_decision is ReviewDecision.PENDING]
    updates = list(session.scalars(select(ScheduleUpdate).where(ScheduleUpdate.activity_id.in_(activity_ids)))) if activity_ids else []
    audit_entity_ids = activity_ids + [item.reconciliation_id for item in recs] + [item.review_id for item in all_reviews] + [item.update_id for item in updates]
    audits = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id.in_(audit_entity_ids)).order_by(AuditEvent.created_at.desc()))) if audit_entity_ids else []
    today = datetime.now(UTC).date()
    rows: list[ActivityRow] = []
    for activity in activities:
        rec = latest.get(activity.activity_id)
        evidence_count = sum(1 for item in interpretations if any(candidate.activity_id == activity.activity_id for match in item.match_results for candidate in match.candidates))
        confidence = rec.confidence if rec else None
        dep_res = TemporalValidationEngine.validate(
            activity,
            proposed_status=rec.reconciled_status if rec else None,
            proposed_start=rec.actual_start if rec else None,
            proposed_end=rec.actual_end if rec else None,
            proposed_progress=rec.reconciled_progress if rec else None,
        )
        rows.append(ActivityRow(activity_id=activity.activity_id, external_activity_id=activity.external_activity_id, discipline=activity.discipline,
            description=activity.description, planned_start=activity.planned_start, planned_finish=activity.planned_finish,
            actual_start=activity.actual_start, actual_end=activity.actual_end, progress=activity.actual_progress,
            status=activity.status, level=activity.level, location=activity.location,
            confidence=confidence, evidence_status="linked" if evidence_count else "no_evidence",
            dependency_status=dep_res.dependency_status.value))
    total = len(activities)
    actual = sum(item.actual_progress or 0 for item in activities) / total if total else 0
    planned = sum(100 if item.planned_finish and item.planned_finish <= today else 0 for item in activities) / total if total else 0
    delayed = sum(1 for item in activities if item.planned_finish and item.planned_finish < today and item.status is not ActivityStatus.COMPLETED)
    high_risk = sum(1 for item in activities if item.activity_id in {conflict.activity_id for conflict in conflicts} or (latest.get(item.activity_id) is not None and latest[item.activity_id].confidence < .5))
    overview = Overview(overall_progress=round(actual, 1), planned_progress=round(planned, 1), planned_vs_actual_delta=round(actual - planned, 1),
        total_activities=total, completed_activities=sum(item.status is ActivityStatus.COMPLETED for item in activities),
        ongoing_activities=sum(item.status is ActivityStatus.IN_PROGRESS for item in activities), delayed_activities=delayed,
        conflicts=len(conflicts), planner_reviews=len(reviews), high_risk_activities=high_risk)
    reconciliation_rows = []
    for item in recs:
        act = act_map.get(item.activity_id)
        dep_val = (
            TemporalValidationEngine.validate(
                act,
                proposed_status=item.reconciled_status,
                proposed_start=item.actual_start,
                proposed_end=item.actual_end,
                proposed_progress=item.reconciled_progress,
            )
            if act
            else None
        )
        reconciliation_rows.append({
            "reconciliation_id": str(item.reconciliation_id),
            "activity_id": str(item.activity_id),
            "status": item.reconciled_status.value,
            "progress": item.reconciled_progress,
            "actual_start": item.actual_start.isoformat() if item.actual_start else None,
            "actual_end": item.actual_end.isoformat() if item.actual_end else None,
            "confidence": item.confidence,
            "supporting_evidence": item.supporting_evidence,
            "conflicting_evidence": item.conflicting_evidence,
            "explanation": item.explanation,
            "decision": item.decision.value,
            "recommended_action": item.recommended_action,
            "created_at": item.created_at,
            "dependency_status": dep_val.dependency_status.value if dep_val else "VALID",
            "dependency_details": [d.to_dict() for d in dep_val.details] if dep_val else [],
        })
    pipeline: list[dict[str, object]] = []
    rec_by_observation = {str(ref["observation_id"]): rec for rec in recs for ref in rec.supporting_evidence + rec.conflicting_evidence}
    for observation in interpretations:
        result = max(observation.match_results, key=lambda item: item.created_at, default=None)
        rec = rec_by_observation.get(str(observation.observation_id))
        pipeline.append({"evidence_id": str(observation.evidence_id), "source": observation.evidence.source_name,
            "observation_id": str(observation.observation_id), "observation": observation.activity_description,
            "match_outcome": result.outcome.value if result else "not_run",
            "matched_activity_id": str(result.candidates[0].activity_id) if result and result.candidates else None,
            "conflict": bool(rec and rec.conflicting_evidence), "reconciliation": rec.decision.value if rec else "not_run",
            "decision": "schedule_update" if rec and rec.decision.value == "auto_accept" else "planner_review" if rec and rec.decision.value == "planner_review" else "no_automatic_update" if rec else "not_run"})
    return DashboardResponse(overview=overview, activities=rows, reconciliations=reconciliation_rows,
        conflicts=[ConflictRow(conflict_id=item.conflict_id, activity_id=item.activity_id, activity=item.activity.external_activity_id,
            conflict_type=item.conflict_type.value, sources=item.description, severity=item.severity.value, resolution_status=item.resolution_status.value) for item in conflicts],
        evidence=[EvidenceRow(evidence_id=item.evidence_id, source_name=item.source_name, source_type=item.source_type.value,
            source_timestamp=item.source_timestamp, raw_text=item.raw_text, raw_reference=item.raw_reference,
            interpretations=[
                {
                    "observation_id": str(obs.observation_id),
                    "activity": obs.activity_description,
                    "discipline": obs.discipline,
                    "location": obs.location,
                    "status": obs.status.value,
                    "progress": obs.progress,
                    "actual_start": obs.actual_start.isoformat() if obs.actual_start else None,
                    "actual_end": obs.actual_end.isoformat() if obs.actual_end else None,
                    "confidence": obs.confidence,
                    "original_evidence": obs.original_evidence,
                    "contractor": obs.contractor,
                    "match_outcome": (
                        max(obs.match_results, key=lambda m: m.created_at).outcome.value
                        if obs.match_results
                        else "no_match"
                    ),
                    "best_score": (
                        max(obs.match_results, key=lambda m: m.created_at).best_score
                        if obs.match_results
                        else None
                    ),
                    "matched_activity": (
                        max(obs.match_results, key=lambda m: m.created_at).candidates[0].activity.external_activity_id
                        if obs.match_results and max(obs.match_results, key=lambda m: m.created_at).candidates and max(obs.match_results, key=lambda m: m.created_at).outcome.value == "matched"
                        else None
                    ),
                    "candidates_count": (
                        len(max(obs.match_results, key=lambda m: m.created_at).candidates)
                        if obs.match_results
                        else 0
                    ),
                }
                for obs in item.interpretations
            ]) for item in evidence],
        audit_trail=[AuditRow(audit_id=item.audit_id, entity_type=item.entity_type, entity_id=item.entity_id, action=item.action.value,
            actor=item.actor, before_value=item.before_value, after_value=item.after_value, explanation=item.explanation, created_at=item.created_at) for item in audits], pipeline=pipeline)
