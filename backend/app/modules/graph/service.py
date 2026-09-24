"""Execution Evidence Graph service.

Provides relational execution graph queries linking:
Project -> WBS -> L5/L6 Activity -> Execution Event (EvidenceInterpretation) -> Evidence -> Discipline / Location / Contractor.
Along with predecessor and successor activity execution relationships and provenance tracing.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import (
    Activity,
    ActivityDependency,
    Evidence,
    EvidenceInterpretation,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    Reconciliation,
)
from app.modules.graph.schemas import (
    ActivitySummary,
    CandidateActivityMatch,
    DependencyContext,
    ExecutionContextResponse,
    ExecutionEventContext,
    ProvenanceTrace,
    ReconciliationSummary,
    TemporalValidationSummary,
)
from app.modules.schedule.temporal_validation import DependencyStatus, TemporalValidationEngine


class ExecutionGraphService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_activity_execution_context(
        self, project_id: uuid.UUID, activity_id: uuid.UUID
    ) -> ExecutionContextResponse:
        """Constructs immediate execution context graph around a specific activity."""
        activity = self.session.scalar(
            select(Activity)
            .where(Activity.activity_id == activity_id, Activity.project_id == project_id)
            .options(
                selectinload(Activity.predecessors).selectinload(ActivityDependency.predecessor),
                selectinload(Activity.successors).selectinload(ActivityDependency.successor),
                selectinload(Activity.reconciliations),
            )
        )
        if activity is None:
            raise ValueError("Activity not found in project.")

        # 1. Activity summary
        act_summary = ActivitySummary(
            activity_id=activity.activity_id,
            external_activity_id=activity.external_activity_id,
            discipline=activity.discipline,
            description=activity.description,
            location=activity.location,
            planned_start=activity.planned_start,
            planned_finish=activity.planned_finish,
            actual_start=activity.actual_start,
            actual_end=activity.actual_end,
            progress=activity.actual_progress,
            status=activity.status.value,
            level=activity.level,
        )

        # 2. Dependencies
        predecessors: list[DependencyContext] = []
        for dep in sorted(activity.predecessors, key=lambda d: d.predecessor.external_activity_id):
            pred = dep.predecessor
            predecessors.append(
                DependencyContext(
                    dependency_id=dep.dependency_id,
                    activity_id=pred.activity_id,
                    external_activity_id=pred.external_activity_id,
                    description=pred.description,
                    dependency_type=dep.dependency_type.value,
                    lag_days=dep.lag_days,
                    status=pred.status.value,
                    progress=pred.actual_progress,
                    actual_start=pred.actual_start,
                    actual_end=pred.actual_end,
                    planned_start=pred.planned_start,
                    planned_finish=pred.planned_finish,
                )
            )

        successors: list[DependencyContext] = []
        for dep in sorted(activity.successors, key=lambda d: d.successor.external_activity_id):
            succ = dep.successor
            successors.append(
                DependencyContext(
                    dependency_id=dep.dependency_id,
                    activity_id=succ.activity_id,
                    external_activity_id=succ.external_activity_id,
                    description=succ.description,
                    dependency_type=dep.dependency_type.value,
                    lag_days=dep.lag_days,
                    status=succ.status.value,
                    progress=succ.actual_progress,
                    actual_start=succ.actual_start,
                    actual_end=succ.actual_end,
                    planned_start=succ.planned_start,
                    planned_finish=succ.planned_finish,
                )
            )

        # 3. Latest Reconciliation
        recs = sorted(activity.reconciliations, key=lambda r: r.created_at, reverse=True)
        latest_rec: Reconciliation | None = recs[0] if recs else None
        rec_summary: ReconciliationSummary | None = None
        supporting_obs_ids: set[str] = set()
        conflicting_obs_ids: set[str] = set()

        if latest_rec is not None:
            rec_summary = ReconciliationSummary(
                reconciliation_id=latest_rec.reconciliation_id,
                decision=latest_rec.decision.value,
                status=latest_rec.reconciled_status.value,
                progress=latest_rec.reconciled_progress,
                confidence=latest_rec.confidence,
                explanation=latest_rec.explanation,
                created_at=latest_rec.created_at,
            )
            for item in latest_rec.supporting_evidence or []:
                if isinstance(item, dict) and item.get("observation_id"):
                    supporting_obs_ids.add(str(item["observation_id"]))
            for item in latest_rec.conflicting_evidence or []:
                if isinstance(item, dict) and item.get("observation_id"):
                    conflicting_obs_ids.add(str(item["observation_id"]))

        # 4. Execution Events (EvidenceInterpretations associated with this activity)
        # Query match candidates linking this activity to observations
        candidate_rows = list(
            self.session.execute(
                select(EvidenceInterpretation, ObservationMatchCandidate, ObservationMatchResult)
                .join(
                    ObservationMatchResult,
                    ObservationMatchResult.observation_id == EvidenceInterpretation.observation_id,
                )
                .join(
                    ObservationMatchCandidate,
                    ObservationMatchCandidate.result_id == ObservationMatchResult.result_id,
                )
                .where(ObservationMatchCandidate.activity_id == activity_id)
                .options(
                    selectinload(EvidenceInterpretation.evidence),
                    selectinload(ObservationMatchResult.candidates).selectinload(
                        ObservationMatchCandidate.activity
                    ),
                )
            ).all()
        )

        seen_obs_ids: set[uuid.UUID] = set()
        execution_events: list[ExecutionEventContext] = []

        for obs, cand, result in candidate_rows:
            if obs.observation_id in seen_obs_ids:
                continue
            seen_obs_ids.add(obs.observation_id)

            candidates_list = [
                CandidateActivityMatch(
                    activity_id=c.activity_id,
                    external_activity_id=c.activity.external_activity_id,
                    description=c.activity.description,
                    similarity_score=c.similarity_score,
                    contextual_score=c.contextual_score,
                    final_score=c.final_score,
                    explanation=c.explanation,
                )
                for c in sorted(result.candidates, key=lambda x: x.rank)
            ]

            obs_id_str = str(obs.observation_id)
            is_sup = obs_id_str in supporting_obs_ids
            is_conf = obs_id_str in conflicting_obs_ids
            rec_decision = None
            if is_sup and latest_rec:
                rec_decision = latest_rec.decision.value
            elif is_conf:
                rec_decision = "CONFLICT"

            execution_events.append(
                ExecutionEventContext(
                    event_id=obs.observation_id,
                    evidence_id=obs.evidence_id,
                    source_name=obs.evidence.source_name,
                    source_type=obs.evidence.source_type.value,
                    source_timestamp=obs.evidence.source_timestamp,
                    field_description=obs.activity_description,
                    discipline=obs.discipline,
                    location=obs.location,
                    contractor=obs.contractor,
                    status=obs.status.value,
                    progress=obs.progress,
                    actual_start=obs.actual_start,
                    actual_end=obs.actual_end,
                    extraction_confidence=obs.confidence,
                    match_score=cand.final_score,
                    match_outcome=result.outcome.value,
                    candidates=candidates_list,
                    reconciliation_decision=rec_decision,
                    is_supporting=is_sup,
                    is_conflicting=is_conf,
                )
            )

        # Sort events by source timestamp descending
        execution_events.sort(key=lambda e: e.source_timestamp, reverse=True)

        # 5. Temporal validation
        validation_res = TemporalValidationEngine.validate(
            activity,
            proposed_status=latest_rec.reconciled_status if latest_rec else activity.status,
            proposed_start=latest_rec.actual_start if latest_rec else activity.actual_start,
            proposed_end=latest_rec.actual_end if latest_rec else activity.actual_end,
            proposed_progress=latest_rec.reconciled_progress if latest_rec else activity.actual_progress,
        )
        temp_summary = TemporalValidationSummary(
            is_valid=validation_res.dependency_status is DependencyStatus.VALID,
            status=validation_res.dependency_status.value,
            rule_name=validation_res.rule,
            details=validation_res.reason
            or ("Temporal and predecessor dependencies satisfied." if validation_res.dependency_status is DependencyStatus.VALID else None),
        )

        # 6. Provenance traces
        provenance: list[ProvenanceTrace] = []

        # Provenance for actual_start
        if activity.actual_start:
            matching_start_ev = next(
                (ev for ev in execution_events if ev.actual_start == activity.actual_start),
                execution_events[0] if execution_events else None,
            )
            if matching_start_ev is not None:
                contractor_part = f" by {matching_start_ev.contractor}" if matching_start_ev.contractor else ""
                provenance.append(
                    ProvenanceTrace(
                        field="actual_start",
                        value=activity.actual_start.isoformat(),
                        event_id=matching_start_ev.event_id,
                        evidence_id=matching_start_ev.evidence_id,
                        source_name=matching_start_ev.source_name,
                        source_type=matching_start_ev.source_type,
                        source_timestamp=matching_start_ev.source_timestamp,
                        contractor=matching_start_ev.contractor,
                        rationale=(
                            f"Actual start {activity.actual_start} confirmed from "
                            f"{matching_start_ev.source_name} ({matching_start_ev.discipline or 'Field'}{contractor_part}) "
                            f"at {matching_start_ev.location or 'Site'} with match score {round((matching_start_ev.match_score or 0) * 100)}%."
                        ),
                    )
                )

        # Provenance for actual_end
        if activity.actual_end:
            matching_end_ev = next(
                (ev for ev in execution_events if ev.actual_end == activity.actual_end),
                execution_events[0] if execution_events else None,
            )
            if matching_end_ev is not None:
                contractor_part = f" by {matching_end_ev.contractor}" if matching_end_ev.contractor else ""
                provenance.append(
                    ProvenanceTrace(
                        field="actual_end",
                        value=activity.actual_end.isoformat(),
                        event_id=matching_end_ev.event_id,
                        evidence_id=matching_end_ev.evidence_id,
                        source_name=matching_end_ev.source_name,
                        source_type=matching_end_ev.source_type,
                        source_timestamp=matching_end_ev.source_timestamp,
                        contractor=matching_end_ev.contractor,
                        rationale=(
                            f"Actual completion {activity.actual_end} verified from "
                            f"{matching_end_ev.source_name} ({matching_end_ev.discipline or 'Field'}{contractor_part}) "
                            f"with status '{matching_end_ev.status}' and confidence {round(matching_end_ev.extraction_confidence * 100)}%."
                        ),
                    )
                )

        # Provenance for actual_progress
        if activity.actual_progress is not None and not provenance:
            primary_ev = execution_events[0] if execution_events else None
            if primary_ev is not None:
                provenance.append(
                    ProvenanceTrace(
                        field="actual_progress",
                        value=f"{activity.actual_progress}%",
                        event_id=primary_ev.event_id,
                        evidence_id=primary_ev.evidence_id,
                        source_name=primary_ev.source_name,
                        source_type=primary_ev.source_type,
                        source_timestamp=primary_ev.source_timestamp,
                        contractor=primary_ev.contractor,
                        rationale=(
                            f"Progress {activity.actual_progress}% reconciled from {primary_ev.source_name} "
                            f"reporting field activity '{primary_ev.field_description}'."
                        ),
                    )
                )

        return ExecutionContextResponse(
            activity=act_summary,
            predecessors=predecessors,
            successors=successors,
            execution_events=execution_events,
            reconciliation=rec_summary,
            temporal_validation=temp_summary,
            provenance=provenance,
        )
