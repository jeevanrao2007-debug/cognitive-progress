"""Execution Memory Service.

Preserves verified project execution knowledge in structured, queryable, and auditable models
without fabricating causes or presenting predictions.
"""

from __future__ import annotations

import math
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ai.interfaces import EmbeddingProvider
from app.ai.registry import get_embedding_provider
from app.database.models import (
    Activity,
    ActivityStatus,
    ConflictSeverity,
    DelayCategory,
    DeviationType,
    Evidence,
    EvidenceConflict,
    EvidenceInterpretation,
    ExecutionDeviation,
    ExecutionRecord,
    ObservationMatchCandidate,
    ObservationMatchResult,
    PlannerReview,
    Project,
    Reconciliation,
    ReconciliationDecision,
    ReviewDecision,
)
from app.modules.memory.schemas import (
    ActivityExecutionHistoryResponse,
    ContractorPerformanceItem,
    CrossProjectMemoryResponse,
    DelayCauseFrequencyItem,
    DisciplinePerformanceItem,
    ExecutionDeviationItem,
    ExecutionRecordResponse,
    HistoricalReferenceItem,
    ProjectPerformanceSummary,
    SimilarExecutionSearchResponse,
)


class ExecutionMemoryService:
    """Core domain service for institutional project execution memory."""

    def __init__(self, session: Session, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.session = session
        self.embedding_provider = embedding_provider or get_embedding_provider()

    @staticmethod
    def calculate_duration(start_date: date | None, end_date: date | None) -> float | None:
        """Deterministic duration in calendar days (inclusive). Returns None if dates are unknown."""
        if start_date is None or end_date is None:
            return None
        if end_date < start_date:
            return None
        return float((end_date - start_date).days + 1)

    @staticmethod
    def calculate_variance(planned_duration: float | None, actual_duration: float | None) -> float | None:
        """Deterministic schedule variance in days: actual_duration - planned_duration."""
        if planned_duration is None or actual_duration is None:
            return None
        return round(float(actual_duration - planned_duration), 2)

    def sync_project_memory(self, project_id: uuid.UUID) -> list[ExecutionRecord]:
        """Compile verified actuals, deviations, delay causes, and planner actions into ExecutionRecords."""
        project = self.session.get(Project, project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # Load activities with reconciliations, conflicts, reviews, and predecessors
        stmt = (
            select(Activity)
            .where(Activity.project_id == project_id)
            .options(
                selectinload(Activity.reconciliations),
                selectinload(Activity.conflicts),
                selectinload(Activity.reviews),
                selectinload(Activity.predecessors),
            )
        )
        activities = list(self.session.scalars(stmt))

        existing_records = {
            r.activity_id: r
            for r in self.session.scalars(
                select(ExecutionRecord)
                .where(ExecutionRecord.project_id == project_id)
                .options(selectinload(ExecutionRecord.deviations))
            )
        }

        updated_records: list[ExecutionRecord] = []

        for act in activities:
            # 1. Determine planned and actual values
            p_start = act.planned_start
            p_finish = act.planned_finish
            a_start = act.actual_start
            a_end = act.actual_end

            p_dur = self.calculate_duration(p_start, p_finish)
            a_dur = self.calculate_duration(a_start, a_end)
            variance = self.calculate_variance(p_dur, a_dur)

            # 2. Extract contractor and evidence citations from matched observations
            matched_obs_stmt = (
                select(EvidenceInterpretation)
                .join(ObservationMatchCandidate, ObservationMatchCandidate.result_id == ObservationMatchCandidate.result_id)
                .join(ObservationMatchResult, ObservationMatchCandidate.result_id == ObservationMatchResult.result_id)
                .where(
                    ObservationMatchCandidate.activity_id == act.activity_id,
                    ObservationMatchResult.observation_id == EvidenceInterpretation.observation_id,
                )
                .options(selectinload(EvidenceInterpretation.evidence))
            )
            matched_obs = list(self.session.scalars(matched_obs_stmt))

            contractor = "UNKNOWN"
            evidence_citations: list[str] = []
            delay_cause: str | None = None
            delay_category: str | None = None
            delay_source_evidence: str | None = None
            delay_confidence: float | None = None

            for obs in matched_obs:
                if obs.contractor and obs.contractor.strip() and contractor == "UNKNOWN":
                    contractor = obs.contractor.strip()
                if obs.evidence and obs.evidence.source_name:
                    if obs.evidence.source_name not in evidence_citations:
                        evidence_citations.append(obs.evidence.source_name)
                if obs.delay_cause:
                    if delay_cause is None or (obs.delay_confidence or 0) > (delay_confidence or 0):
                        delay_cause = obs.delay_cause
                        delay_category = obs.delay_category or "UNKNOWN"
                        delay_source_evidence = f"{obs.evidence.source_name}: {obs.delay_cause}"
                        delay_confidence = obs.delay_confidence

            # 3. Check reconciliation & conflicts
            latest_rec = act.reconciliations[-1] if act.reconciliations else None
            unresolved_conflicts = [c for c in act.conflicts if c.resolution_status.value == "open"]

            dep_status = "VALID"
            if any(c.conflict_type.value == "dependency" for c in unresolved_conflicts):
                dep_status = "CONFLICT"
            elif not act.predecessors:
                dep_status = "UNCONSTRAINED"

            # 4. Check planner reviews
            planner_override = False
            planner_notes: str | None = None
            for rev in act.reviews:
                if rev.reviewer_decision in (ReviewDecision.ACCEPT, ReviewDecision.OVERRIDE):
                    planner_override = True
                    planner_notes = rev.reviewer_comment or rev.reason

            # 5. Classify deviations
            deviation_type = DeviationType.UNKNOWN.value
            deviation_items: list[tuple[str, float | None, str]] = []

            if unresolved_conflicts:
                deviation_type = DeviationType.CONFLICT.value
                for c in unresolved_conflicts:
                    deviation_items.append((
                        DeviationType.CONFLICT.value,
                        None,
                        f"Conflict ({c.conflict_type.value}): {c.description}",
                    ))
            elif act.status == ActivityStatus.COMPLETED:
                if a_end and p_finish:
                    if a_end < p_finish:
                        deviation_type = DeviationType.EARLY.value
                        delta = float((p_finish - a_end).days)
                        deviation_items.append((DeviationType.EARLY.value, -delta, f"Completed {int(delta)} days earlier than baseline"))
                    elif a_end > p_finish:
                        deviation_type = DeviationType.LATE.value
                        delta = float((a_end - p_finish).days)
                        deviation_items.append((DeviationType.LATE.value, delta, f"Completed {int(delta)} days later than baseline"))
                    else:
                        deviation_type = DeviationType.ON_TIME.value
                elif variance is not None:
                    if variance > 0:
                        deviation_type = DeviationType.EXTENDED.value
                        deviation_items.append((DeviationType.EXTENDED.value, variance, f"Execution extended by {variance} days"))
                    elif variance < 0:
                        deviation_type = DeviationType.EARLY.value
                        deviation_items.append((DeviationType.EARLY.value, variance, f"Executed in {abs(variance)} days less than planned"))
                    else:
                        deviation_type = DeviationType.ON_TIME.value
                else:
                    deviation_type = DeviationType.ON_TIME.value
            elif act.status == ActivityStatus.IN_PROGRESS:
                if a_start and p_start and a_start > p_start:
                    deviation_type = DeviationType.LATE.value
                    delta = float((a_start - p_start).days)
                    deviation_items.append((DeviationType.LATE.value, delta, f"Start delayed by {int(delta)} days"))
                else:
                    deviation_type = DeviationType.ON_TIME.value

            # If delayed, ensure delay_cause is marked if absent
            if deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value):
                if not delay_cause:
                    delay_cause = "UNKNOWN"
                    delay_category = "UNKNOWN"

            # 6. Create or update ExecutionRecord
            record = existing_records.get(act.activity_id)
            if not record:
                record = ExecutionRecord(
                    project_id=project_id,
                    activity_id=act.activity_id,
                    external_activity_id=act.external_activity_id,
                    activity_name=act.description,
                )
                self.session.add(record)

            record.external_activity_id = act.external_activity_id
            record.activity_name = act.description
            record.discipline = act.discipline
            record.contractor = contractor
            record.location = act.location
            record.planned_start = p_start
            record.planned_finish = p_finish
            record.actual_start = a_start
            record.actual_end = a_end
            record.planned_duration_days = p_dur
            record.actual_duration_days = a_dur
            record.variance_days = variance
            record.status = act.status
            record.percent_complete = act.actual_progress
            record.reconciliation_decision = latest_rec.decision.value if latest_rec else None
            record.confidence = latest_rec.confidence if latest_rec else None
            record.evidence_reference = ", ".join(evidence_citations) if evidence_citations else None
            record.source_timestamp = datetime.utcnow()
            record.dependency_status = dep_status
            record.deviation_type = deviation_type
            record.delay_cause = delay_cause
            record.delay_category = delay_category
            record.delay_source_evidence = delay_source_evidence
            record.delay_confidence = delay_confidence
            record.planner_override = planner_override
            record.planner_notes = planner_notes

            # Recreate deviation items
            record.deviations.clear()
            for dev_type, metric, desc in deviation_items:
                record.deviations.append(
                    ExecutionDeviation(
                        deviation_type=dev_type,
                        metric_days=metric,
                        description=desc,
                    )
                )

            updated_records.append(record)

        self.session.commit()
        return updated_records

    def get_project_summary(self, project_id: uuid.UUID) -> ProjectPerformanceSummary:
        """Compute deterministic project performance KPI summary and breakdown."""
        project = self.session.get(Project, project_id)
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # Ensure execution memory is synchronized with active data
        records = self.sync_project_memory(project_id)

        total_activities = len(records)
        completed = [r for r in records if r.status == ActivityStatus.COMPLETED]
        on_time = [r for r in records if r.deviation_type in (DeviationType.ON_TIME.value, DeviationType.EARLY.value)]
        late = [r for r in records if r.deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value)]
        conflicts = [r for r in records if r.deviation_type == DeviationType.CONFLICT.value]

        planned_durs = [r.planned_duration_days for r in records if r.planned_duration_days is not None]
        actual_durs = [r.actual_duration_days for r in completed if r.actual_duration_days is not None]
        variances = [r.variance_days for r in records if r.variance_days is not None]

        avg_planned = round(sum(planned_durs) / len(planned_durs), 1) if planned_durs else None
        avg_actual = round(sum(actual_durs) / len(actual_durs), 1) if actual_durs else None
        avg_variance = round(sum(variances) / len(variances), 1) if variances else None

        # Top recorded delay causes
        cause_map: dict[str, list[str]] = {}
        for r in records:
            if r.delay_category and r.delay_category != "UNKNOWN":
                cat = r.delay_category
                cause_map.setdefault(cat, [])
                if r.delay_cause and r.delay_cause != "UNKNOWN" and r.delay_cause not in cause_map[cat]:
                    cause_map[cat].append(r.delay_cause)

        top_causes = [
            DelayCauseFrequencyItem(category=cat, count=len(causes) or 1, sample_causes=causes[:3])
            for cat, causes in sorted(cause_map.items(), key=lambda item: -len(item[1]))
        ]

        # Discipline breakdown
        disc_groups: dict[str, list[ExecutionRecord]] = {}
        for r in records:
            disc = r.discipline or "Unassigned"
            disc_groups.setdefault(disc, []).append(r)

        discipline_perf: list[DisciplinePerformanceItem] = []
        for disc, grp in sorted(disc_groups.items()):
            comp = [r for r in grp if r.status == ActivityStatus.COMPLETED]
            v_list = [r.variance_days for r in grp if r.variance_days is not None]
            avg_v = round(sum(v_list) / len(v_list), 1) if v_list else None
            delayed = sum(1 for r in grp if r.deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value))
            discipline_perf.append(
                DisciplinePerformanceItem(
                    discipline=disc,
                    total_activities=len(grp),
                    completed_activities=len(comp),
                    average_variance_days=avg_v,
                    delayed_count=delayed,
                )
            )

        # Contractor breakdown
        cont_groups: dict[str, list[ExecutionRecord]] = {}
        for r in records:
            if r.contractor and r.contractor != "UNKNOWN":
                cont_groups.setdefault(r.contractor, []).append(r)

        contractor_perf: list[ContractorPerformanceItem] = []
        for cont, grp in sorted(cont_groups.items()):
            comp = [r for r in grp if r.status == ActivityStatus.COMPLETED]
            v_list = [r.variance_days for r in grp if r.variance_days is not None]
            avg_v = round(sum(v_list) / len(v_list), 1) if v_list else None
            delayed = sum(1 for r in grp if r.deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value))
            contractor_perf.append(
                ContractorPerformanceItem(
                    contractor=cont,
                    total_activities=len(grp),
                    completed_activities=len(comp),
                    average_variance_days=avg_v,
                    delayed_count=delayed,
                )
            )

        return ProjectPerformanceSummary(
            project_id=project.project_id,
            project_name=project.name,
            total_activities=total_activities,
            completed_activities=len(completed),
            on_time_activities=len(on_time),
            late_activities=len(late),
            conflict_count=len(conflicts),
            average_planned_duration_days=avg_planned,
            average_actual_duration_days=avg_actual,
            average_variance_days=avg_variance,
            top_delay_causes=top_causes,
            discipline_performance=discipline_perf,
            contractor_performance=contractor_perf,
        )

    def get_activity_history(self, project_id: uuid.UUID, activity_id: uuid.UUID) -> ActivityExecutionHistoryResponse:
        """Trace full historical execution provenance for an activity."""
        activity = self.session.get(Activity, activity_id)
        if not activity or activity.project_id != project_id:
            raise ValueError(f"Activity '{activity_id}' not found in project '{project_id}'.")

        # Query execution record
        record = self.session.scalar(
            select(ExecutionRecord)
            .where(ExecutionRecord.activity_id == activity_id)
            .options(selectinload(ExecutionRecord.deviations))
        )
        if not record:
            self.sync_project_memory(project_id)
            record = self.session.scalar(
                select(ExecutionRecord)
                .where(ExecutionRecord.activity_id == activity_id)
                .options(selectinload(ExecutionRecord.deviations))
            )

        # Query reviews
        reviews = list(
            self.session.scalars(
                select(PlannerReview).where(PlannerReview.activity_id == activity_id)
            )
        )
        review_audit = [
            {
                "review_id": str(r.review_id),
                "reviewer": r.reviewer or "Project Planner",
                "proposed_decision": r.proposed_decision.value,
                "reviewer_decision": r.reviewer_decision.value,
                "reviewer_comment": r.reviewer_comment or r.reason,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in reviews
        ]

        citations = [c.strip() for c in (record.evidence_reference or "").split(",") if c.strip()] if record else []
        deviations = [d.description for d in record.deviations] if record else []

        return ActivityExecutionHistoryResponse(
            activity_id=activity.activity_id,
            external_activity_id=activity.external_activity_id,
            activity_name=activity.description,
            discipline=activity.discipline,
            contractor=record.contractor if record else "UNKNOWN",
            location=activity.location,
            planned_start=activity.planned_start,
            planned_finish=activity.planned_finish,
            actual_start=activity.actual_start,
            actual_end=activity.actual_end,
            planned_duration_days=record.planned_duration_days if record else None,
            actual_duration_days=record.actual_duration_days if record else None,
            variance_days=record.variance_days if record else None,
            status=activity.status.value,
            percent_complete=activity.actual_progress,
            execution_evidence_citations=citations,
            recorded_deviations=deviations,
            recorded_cause=record.delay_cause if record else "UNKNOWN",
            delay_category=record.delay_category if record else None,
            cause_source_reference=record.delay_source_evidence if record else None,
            cause_confidence=record.delay_confidence if record else None,
            planner_decisions=review_audit,
        )

    def find_similar_executions(
        self, query: str | None = None, discipline: str | None = None, limit: int = 5
    ) -> SimilarExecutionSearchResponse:
        """Retrieve similar past completed activities using embedding similarity as historical reference."""
        stmt = (
            select(ExecutionRecord)
            .join(Project, ExecutionRecord.project_id == Project.project_id)
            .where(ExecutionRecord.status == ActivityStatus.COMPLETED)
            .options(selectinload(ExecutionRecord.project))
        )
        if discipline:
            stmt = stmt.where(ExecutionRecord.discipline.ilike(f"%{discipline}%"))

        candidates = list(self.session.scalars(stmt))
        results: list[HistoricalReferenceItem] = []

        if not candidates:
            return SimilarExecutionSearchResponse(
                query=query or "",
                discipline=discipline,
                results=[],
                disclaimer="HISTORICAL REFERENCE ONLY — NOT A PREDICTION",
            )

        query_text = (query or discipline or "piping installation").strip()
        query_vector = self.embedding_provider.embed(query_text)

        scored: list[tuple[ExecutionRecord, float]] = []
        for cand in candidates:
            cand_vec = self.embedding_provider.embed(cand.activity_name)
            sim = self._cosine_similarity(query_vector, cand_vec)
            scored.append((cand, sim))

        scored.sort(key=lambda item: -item[1])

        for cand, score in scored[:limit]:
            results.append(
                HistoricalReferenceItem(
                    activity_name=cand.activity_name,
                    external_activity_id=cand.external_activity_id,
                    project_name=cand.project.name if cand.project else "Unknown Project",
                    discipline=cand.discipline,
                    contractor=cand.contractor,
                    planned_duration_days=cand.planned_duration_days,
                    actual_duration_days=cand.actual_duration_days,
                    variance_days=cand.variance_days,
                    delay_cause=cand.delay_cause,
                    delay_category=cand.delay_category,
                    evidence_reference=cand.evidence_reference,
                    similarity_score=round(score, 3),
                    disclaimer="HISTORICAL REFERENCE ONLY — NOT A PREDICTION",
                )
            )

        return SimilarExecutionSearchResponse(
            query=query_text,
            discipline=discipline,
            results=results,
            disclaimer="HISTORICAL REFERENCE ONLY — NOT A PREDICTION",
        )

    def query_cross_project(
        self, discipline: str | None = None, query: str | None = None, limit: int = 10
    ) -> CrossProjectMemoryResponse:
        """Deterministic institutional knowledge query across all historical projects."""
        stmt = (
            select(ExecutionRecord)
            .join(Project, ExecutionRecord.project_id == Project.project_id)
            .options(selectinload(ExecutionRecord.project))
        )
        if discipline:
            stmt = stmt.where(ExecutionRecord.discipline.ilike(f"%{discipline}%"))
        if query:
            stmt = stmt.where(ExecutionRecord.activity_name.ilike(f"%{query}%"))

        records = list(self.session.scalars(stmt))
        completed = [r for r in records if r.status == ActivityStatus.COMPLETED]
        variances = [r.variance_days for r in records if r.variance_days is not None]
        avg_variance = round(sum(variances) / len(variances), 1) if variances else None

        # Delay causes
        cause_map: dict[str, list[str]] = {}
        for r in records:
            if r.delay_category and r.delay_category != "UNKNOWN":
                cat = r.delay_category
                cause_map.setdefault(cat, [])
                if r.delay_cause and r.delay_cause != "UNKNOWN" and r.delay_cause not in cause_map[cat]:
                    cause_map[cat].append(r.delay_cause)

        top_causes = [
            DelayCauseFrequencyItem(category=cat, count=len(causes) or 1, sample_causes=causes[:3])
            for cat, causes in sorted(cause_map.items(), key=lambda item: -len(item[1]))
        ]

        # Discipline breakdown
        disc_groups: dict[str, list[ExecutionRecord]] = {}
        for r in records:
            d = r.discipline or "Unassigned"
            disc_groups.setdefault(d, []).append(r)

        disc_items = [
            DisciplinePerformanceItem(
                discipline=d,
                total_activities=len(grp),
                completed_activities=sum(1 for x in grp if x.status == ActivityStatus.COMPLETED),
                average_variance_days=round(sum(x.variance_days for x in grp if x.variance_days is not None) / len([x for x in grp if x.variance_days is not None]), 1)
                if any(x.variance_days is not None for x in grp) else None,
                delayed_count=sum(1 for x in grp if x.deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value)),
            )
            for d, grp in sorted(disc_groups.items())
        ]

        sample_items = [
            HistoricalReferenceItem(
                activity_name=r.activity_name,
                external_activity_id=r.external_activity_id,
                project_name=r.project.name if r.project else "Historical Project",
                discipline=r.discipline,
                contractor=r.contractor,
                planned_duration_days=r.planned_duration_days,
                actual_duration_days=r.actual_duration_days,
                variance_days=r.variance_days,
                delay_cause=r.delay_cause,
                delay_category=r.delay_category,
                evidence_reference=r.evidence_reference,
                similarity_score=1.0,
                disclaimer="HISTORICAL REFERENCE ONLY — NOT A PREDICTION",
            )
            for r in completed[:limit]
        ]

        return CrossProjectMemoryResponse(
            query_filter=query,
            discipline_filter=discipline,
            total_matching_records=len(records),
            completed_matching_records=len(completed),
            average_variance_days=avg_variance,
            top_delay_causes=top_causes,
            discipline_breakdown=disc_items,
            sample_records=sample_items,
            disclaimer="HISTORICAL REFERENCE ONLY — NOT A PREDICTION",
        )

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))
