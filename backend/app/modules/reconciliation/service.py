"""Deterministic AI-assisted evidence reconciliation.

Combines AI reasoning with a strict deterministic safety gate.
Gemini never directly updates the schedule or database; schedule updates are
applied exclusively by the deterministic actuation layer following safety gate validation.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.gemini_provider import clean_json_response
from app.ai.interfaces import LLMProvider
from app.ai.registry import get_llm_provider
from app.core.config import get_settings
from app.database.models import (
    Activity,
    ActivityStatus,
    ConflictSeverity,
    ConflictType,
    EvidenceConflict,
    EvidenceInterpretation,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    Reconciliation,
    ReconciliationDecision,
    SourceType,
)
from app.modules.audit.service import AuditService
from app.modules.reconciliation.schemas import (
    AIReconciliationRecommendation,
    DependencyValidationDetailResponse,
    EvidenceReference,
    ReconciliationResponse,
    ReconciliationThresholds,
)
from app.modules.schedule.temporal_validation import (
    DependencyStatus,
    TemporalValidationEngine,
    TemporalValidationResult,
)

logger = logging.getLogger(__name__)

_STATUS_PROGRESS = {
    ActivityStatus.NOT_STARTED: 0.0,
    ActivityStatus.IN_PROGRESS: 50.0,
    ActivityStatus.COMPLETED: 100.0,
    ActivityStatus.ON_HOLD: 50.0,
    ActivityStatus.UNKNOWN: 50.0,
}


@dataclass(frozen=True)
class WeightedObservation:
    observation: EvidenceInterpretation
    match_score: float
    weight: float
    freshness: float
    reliability: float = 0.60
    is_stale: bool = False
    is_duplicate: bool = False
    is_direct: bool = True
    contradiction_reason: str | None = None

    @property
    def progress(self) -> float:
        return (
            self.observation.progress
            if self.observation.progress is not None
            else _STATUS_PROGRESS[self.observation.status]
        )


class ReconciliationService:
    """Cognitive progress reconciliation layer.
    
    Combines AI reasoning with transparent source reliability, activity knowledge
    context, multi-source conflict detection, and a strict deterministic safety gate.
    Gemini never directly updates the schedule or database; schedule updates are
    applied exclusively by the deterministic actuation layer following safety gate validation.
    """

    def __init__(
        self,
        session: Session,
        thresholds: ReconciliationThresholds | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.session = session
        self.llm_provider = llm_provider or get_llm_provider()
        settings = get_settings()
        self.thresholds = thresholds or ReconciliationThresholds(
            auto_accept=settings.reconciliation_auto_accept_threshold,
            review=settings.reconciliation_review_threshold,
            no_decision=settings.reconciliation_no_decision_threshold,
            freshness_half_life_days=settings.reconciliation_freshness_half_life_days,
            source_reliability={
                SourceType.DAILY_REPORT: settings.reliability_daily_report,
                SourceType.CONTRACTOR_SPREADSHEET: settings.reliability_contractor_spreadsheet,
                SourceType.DISCIPLINE_SPREADSHEET: settings.reliability_discipline_spreadsheet,
                SourceType.SITE_DIARY: settings.reliability_site_diary,
                SourceType.MANUAL_ENTRY: settings.reliability_manual_entry,
            },
        )
        if not self.thresholds.no_decision <= self.thresholds.review <= self.thresholds.auto_accept:
            raise ValueError("Reconciliation thresholds must be no_decision <= review <= auto_accept.")

    def reconcile_activity(self, activity_id: uuid.UUID) -> ReconciliationResponse:
        activity = self.session.get(Activity, activity_id)
        if activity is None:
            raise ValueError("Activity does not exist.")

        # 1. Collect all matched observations and calculate source reliability / freshness
        matched = self._matched_observations(activity_id)
        weighted = self._weight(matched)

        # 2. Empty evidence gate
        if not weighted:
            return self._record_no_decision(activity)

        # 3. Uninterpretable observations gate
        if all(
            item.observation.status is ActivityStatus.UNKNOWN and item.observation.progress is None
            for item in weighted
        ):
            return self._record_reject(
                activity,
                weighted,
                "Reject this evidence set for schedule updating because it does not state an interpretable progress condition.",
            )

        # 4. Progress bounds check on raw observation progress
        for item in weighted:
            if item.observation.progress is not None and (
                item.observation.progress < 0.0 or item.observation.progress > 100.0
            ):
                return self._record_reject(
                    activity,
                    weighted,
                    f"Reject this evidence set because observation reports invalid progress {item.observation.progress}% outside [0, 100].",
                )

        # 5. Deterministic baseline state estimation & cognitive conflict detection
        det_status, det_progress, agreement = self._proposed_state(weighted)
        det_conflicts, conflict_types, conflict_details = self._detect_conflicts(activity, weighted, det_status)
        det_confidence = self._confidence(weighted, agreement, bool(det_conflicts))

        # 6. AI Reasoning with Activity Knowledge Context & Source Reliability (Gemini)
        ai_rec = self._call_ai_reconciliation(activity, weighted, conflict_types, conflict_details)

        # 7. Deterministic Safety Gate Validation
        (
            decision,
            status,
            progress,
            actual_start,
            actual_end,
            final_confidence,
            supporting,
            conflicting,
            explanation,
            validation_details,
            reasoning_factors,
            temporal_result,
        ) = self._safety_gate_validate(
            activity=activity,
            weighted=weighted,
            det_status=det_status,
            det_progress=det_progress,
            det_conflicts=det_conflicts,
            det_confidence=det_confidence,
            conflict_types=conflict_types,
            conflict_details=conflict_details,
            ai_rec=ai_rec,
        )

        # 8. References & Recommended Action
        supporting_refs = [self._reference(item) for item in supporting]
        conflicting_refs = [self._reference(item) for item in conflicting]
        has_conflict = bool(conflicting)
        recommended_action = (
            ai_rec.recommended_action
            if (ai_rec and ai_rec.recommended_action)
            else self._recommended_action(decision, has_conflict)
        )

        # 9. Persist Reconciliation Record
        reconciliation = Reconciliation(
            activity_id=activity_id,
            reconciled_status=status,
            reconciled_progress=progress,
            actual_start=actual_start,
            actual_end=actual_end,
            confidence=final_confidence,
            explanation=explanation,
            decision=decision,
            supporting_evidence=[item.model_dump(mode="json") for item in supporting_refs],
            conflicting_evidence=[item.model_dump(mode="json") for item in conflicting_refs],
            recommended_action=recommended_action,
        )
        self.session.add(reconciliation)
        self.session.flush()

        # 10. Persist Conflicts if any
        if temporal_result.dependency_status == DependencyStatus.CONFLICT:
            self.session.add(
                EvidenceConflict(
                    activity_id=activity.activity_id,
                    conflict_type=ConflictType.DEPENDENCY,
                    severity=ConflictSeverity.HIGH,
                    description=f"Schedule dependency violation: {temporal_result.reason}",
                )
            )
        self._create_conflicts(activity, conflicting_refs, status, progress, conflict_types)

        # 11. Deterministic Actuation: Schedule Update OR Planner Review
        if decision is ReconciliationDecision.AUTO_ACCEPT:
            from app.modules.schedule.updates import ScheduleUpdateService

            ScheduleUpdateService(self.session).apply(
                activity,
                reconciliation,
                decision_source="automatic:reconciliation",
                reason=explanation,
            )
        elif decision is ReconciliationDecision.PLANNER_REVIEW:
            from app.modules.planner_review.service import PlannerReviewService

            PlannerReviewService(self.session).create_review(reconciliation, recommended_action)

        # 12. Audit Trail
        AuditService(self.session).record_created(
            "reconciliation",
            reconciliation.reconciliation_id,
            {
                "activity_id": str(activity_id),
                "external_activity_id": activity.external_activity_id,
                "decision": decision.value,
                "confidence": final_confidence,
                "conflict_detected": has_conflict or temporal_result.dependency_status == DependencyStatus.CONFLICT,
                "conflict_types": conflict_types,
                "supporting_evidence": [str(item.observation_id) for item in supporting_refs],
                "conflicting_evidence": [str(item.observation_id) for item in conflicting_refs],
                "source_types": list({item.source_type.value for item in supporting_refs + conflicting_refs}),
                "source_reliability_breakdown": {
                    item.source_name: {
                        "reliability": item.reliability_score,
                        "freshness": item.freshness_score,
                        "is_stale": item.is_stale,
                        "is_duplicate": item.is_duplicate,
                    }
                    for item in supporting_refs + conflicting_refs
                },
                "source_reliability_reasoning": reasoning_factors.get("source_reliability"),
                "schedule_context_reasoning": reasoning_factors.get("schedule_context"),
                "ai_involved": ai_rec is not None,
                "ai_recommendation": ai_rec.model_dump(mode="json") if ai_rec else None,
                "deterministic_validation": validation_details,
                "dependency_validation": {
                    "activity_id": str(activity.activity_id),
                    "external_activity_id": activity.external_activity_id,
                    "result": temporal_result.dependency_status.value,
                    "rule_evaluated": temporal_result.rule,
                    "reason": temporal_result.reason,
                    "decision": decision.value,
                    "timestamp_of_validation": datetime.now(UTC).isoformat(),
                    "details": [d.to_dict() for d in temporal_result.details],
                },
            },
            explanation,
        )
        self.session.commit()
        return self._response(
            reconciliation,
            ai_rec=ai_rec,
            conflict_detected=has_conflict or temporal_result.dependency_status == DependencyStatus.CONFLICT,
            conflict_types=conflict_types,
            reasoning_factors=reasoning_factors,
            temporal_result=temporal_result,
        )

    def _matched_observations(self, activity_id: uuid.UUID) -> list[tuple[EvidenceInterpretation, float]]:
        statement = (
            select(ObservationMatchCandidate, EvidenceInterpretation)
            .join(ObservationMatchCandidate.result)
            .join(ObservationMatchResult.interpretation)
            .join(EvidenceInterpretation.evidence)
            .where(
                ObservationMatchCandidate.activity_id == activity_id,
                ObservationMatchResult.outcome.in_(
                    [ObservationMatchOutcome.MATCHED, ObservationMatchOutcome.NEEDS_REVIEW]
                ),
                ObservationMatchCandidate.rank == 1,
            )
            .options(selectinload(EvidenceInterpretation.evidence))
        )
        return [(observation, candidate.final_score) for candidate, observation in self.session.execute(statement)]

    def _weight(self, observations: list[tuple[EvidenceInterpretation, float]]) -> list[WeightedObservation]:
        if not observations:
            return []
        newest = max(item.evidence.source_timestamp for item, _ in observations)
        
        # Detect exact duplicates across reports
        seen_reports: dict[str, uuid.UUID] = {}
        duplicates: set[uuid.UUID] = set()
        for obs, _ in observations:
            raw_norm = (obs.original_evidence or obs.activity_description or "").strip().lower()
            key = f"{raw_norm}::{obs.evidence.source_name}"
            if key in seen_reports:
                duplicates.add(obs.observation_id)
            else:
                seen_reports[key] = obs.observation_id

        result: list[WeightedObservation] = []
        for observation, match_score in observations:
            age = max(0.0, (newest - observation.evidence.source_timestamp).total_seconds() / 86400)
            freshness = math.pow(0.5, age / self.thresholds.freshness_half_life_days)
            reliability = self.thresholds.source_reliability.get(observation.evidence.source_type, 0.60)
            is_stale = (age >= self.thresholds.freshness_half_life_days and len(observations) > 1 and freshness < 0.50)
            is_duplicate = observation.observation_id in duplicates
            is_direct = observation.evidence.source_type in (SourceType.DAILY_REPORT, SourceType.SITE_DIARY)
            dup_factor = 0.40 if is_duplicate else 1.0

            computed_weight = (
                reliability * (0.65 + 0.35 * freshness) * observation.confidence * match_score * dup_factor
            )
            result.append(
                WeightedObservation(
                    observation=observation,
                    match_score=match_score,
                    weight=computed_weight,
                    freshness=freshness,
                    reliability=reliability,
                    is_stale=is_stale,
                    is_duplicate=is_duplicate,
                    is_direct=is_direct,
                )
            )
        return result

    @staticmethod
    def _proposed_state(weighted: list[WeightedObservation]) -> tuple[ActivityStatus, float | None, float]:
        if not weighted:
            return ActivityStatus.UNKNOWN, None, 0.0
        totals: dict[ActivityStatus, float] = {}
        for item in weighted:
            totals[item.observation.status] = totals.get(item.observation.status, 0.0) + item.weight
        status = max(totals, key=lambda candidate: (totals[candidate], candidate.value))
        total = sum(item.weight for item in weighted)
        if all(item.observation.status is ActivityStatus.UNKNOWN and item.observation.progress is None for item in weighted):
            return ActivityStatus.UNKNOWN, None, 0.0
        if status is ActivityStatus.COMPLETED:
            progress = 100.0
        else:
            progress = sum(item.progress * item.weight for item in weighted) / total if total else None
        return status, round(progress, 2) if progress is not None else None, totals[status] / total if total else 0.0

    def _detect_conflicts(
        self,
        activity: Activity,
        weighted: list[WeightedObservation],
        status: ActivityStatus,
    ) -> tuple[list[WeightedObservation], list[str], dict[str, str]]:
        """Multi-source conflict detection engine.
        
        Evaluates:
        - conflicting completion states (completed vs in_progress)
        - conflicting progress percentages (variance >= 20%)
        - conflicting dates (actual_end < actual_start)
        - duplicate evidence reports
        - stale evidence vs fresh supervisor reports
        - incompatible discipline descriptions
        """
        if not weighted:
            return [], [], {}

        conflicts: list[WeightedObservation] = []
        conflict_types: list[str] = []
        details: dict[str, str] = {}

        # 1. Completion state & Progress percentage variance
        highest_progress = max(item.progress for item in weighted)
        lowest_progress = min(item.progress for item in weighted)
        progress_variance = highest_progress - lowest_progress

        has_completed = any(item.observation.status is ActivityStatus.COMPLETED or item.progress >= 100.0 for item in weighted)
        has_in_progress = any(item.observation.status is ActivityStatus.IN_PROGRESS and item.progress <= 85.0 for item in weighted)

        if has_completed and has_in_progress:
            conflict_types.append("conflicting_completion_state")
            details["completion_state"] = "One source reports completed (100%) while another reports in_progress."
            for item in weighted:
                if item.observation.status != status:
                    conflicts.append(item)

        if progress_variance >= 20.0 and "conflicting_completion_state" not in conflict_types:
            conflict_types.append("progress_percentage_variance")
            details["progress_variance"] = f"Progress estimates differ by {progress_variance:.1f}% ({lowest_progress}% vs {highest_progress}%)."
            for item in weighted:
                if highest_progress - item.progress >= 20.0 and item not in conflicts:
                    conflicts.append(item)

        # 2. Stale evidence detection
        stale_items = [item for item in weighted if item.is_stale]
        fresh_items = [item for item in weighted if not item.is_stale]
        if stale_items and fresh_items:
            conflict_types.append("stale_evidence_detected")
            stale_names = ", ".join(item.observation.evidence.source_name for item in stale_items)
            fresh_names = ", ".join(item.observation.evidence.source_name for item in fresh_items)
            details["stale_evidence"] = (
                f"Older evidence from {stale_names} exceeds freshness threshold compared to newer reports from {fresh_names}."
            )

        # 3. Duplicate reports
        duplicate_items = [item for item in weighted if item.is_duplicate]
        if duplicate_items:
            conflict_types.append("duplicate_evidence_detected")
            dup_names = ", ".join(item.observation.evidence.source_name for item in duplicate_items)
            details["duplicates"] = f"Duplicate observation reports identified across {dup_names}; duplicate weight discounted."

        # 4. Incompatible discipline mismatch
        if activity.discipline:
            act_disc = activity.discipline.strip().lower()
            for item in weighted:
                if item.observation.discipline and item.observation.discipline.strip().lower() != act_disc:
                    conflict_types.append("discipline_mismatch")
                    details["discipline_mismatch"] = (
                        f"Observation from {item.observation.evidence.source_name} reports discipline "
                        f"'{item.observation.discipline}' which differs from planned activity discipline '{activity.discipline}'."
                    )
                    if item not in conflicts:
                        conflicts.append(item)

        # 5. Fallback check for status mismatch
        for item in weighted:
            if item.observation.status != status and item not in conflicts:
                conflicts.append(item)

        return conflicts, conflict_types, details

    def _confidence(self, weighted: list[WeightedObservation], agreement: float, has_conflict: bool) -> float:
        if not weighted:
            return 0.0
        total = sum(item.weight for item in weighted)
        quality = sum(item.observation.confidence * item.match_score for item in weighted) / len(weighted)
        freshness = sum(item.freshness * item.weight for item in weighted) / total if total else 0.0
        diversity = min(1.0, len({item.observation.evidence.source_type for item in weighted}) / 2)

        # If genuine conflict exists, confidence is penalized so safety gates route to planner review
        conflict_penalty = 0.20 if has_conflict else 0.0
        raw_conf = 0.50 * agreement + 0.25 * quality + 0.15 * freshness + 0.10 * diversity - conflict_penalty
        return round(max(0.0, min(1.0, raw_conf)), 3)

    def _call_ai_reconciliation(
        self,
        activity: Activity,
        weighted: list[WeightedObservation],
        conflict_types: list[str],
        conflict_details: dict[str, str],
    ) -> AIReconciliationRecommendation | None:
        if not weighted:
            return None
        prompt = self._build_reconciliation_prompt(activity, weighted, conflict_types, conflict_details)
        try:
            raw_response = self.llm_provider.explain_reconciliation(prompt)
            return self._parse_ai_recommendation(raw_response)
        except Exception as err:
            logger.warning("AI reconciliation call failed or returned unparseable output: %s", err)
            return None

    def _build_reconciliation_prompt(
        self,
        activity: Activity,
        weighted: list[WeightedObservation],
        conflict_types: list[str],
        conflict_details: dict[str, str],
    ) -> str:
        evidence_lines = []
        for item in weighted:
            obs = item.observation
            ev = obs.evidence
            direct_label = "Direct Field Observation" if item.is_direct else "Secondary Aggregated Report"
            stale_label = "STALE (>14d)" if item.is_stale else "Fresh"
            dup_label = " [DUPLICATE]" if item.is_duplicate else ""
            evidence_lines.append(
                f"- Observation ID: {obs.observation_id}\n"
                f"  Source: {ev.source_name} ({ev.source_type.value}) - {direct_label} - {stale_label}{dup_label}\n"
                f"  Timestamp: {ev.source_timestamp.isoformat()}\n"
                f"  Reported Text: \"{obs.original_evidence or ev.raw_text}\"\n"
                f"  Reported Discipline: {obs.discipline or 'Unspecified'}\n"
                f"  Extracted Status: {obs.status.value}\n"
                f"  Extracted Progress: {obs.progress if obs.progress is not None else 'None'}%\n"
                f"  Actual Start: {obs.actual_start}\n"
                f"  Actual End: {obs.actual_end}\n"
                f"  Reliability Score: {item.reliability:.2f}\n"
                f"  Freshness Factor: {item.freshness:.2f}\n"
                f"  Match Score: {item.match_score:.2f}\n"
                f"  Assigned Weight: {item.weight:.3f}"
            )
        evidence_text = "\n\n".join(evidence_lines)
        conflicts_summary_text = (
            "Detected conflict types: " + ", ".join(conflict_types) + "\n"
            + "\n".join(f"- {k}: {v}" for k, v in conflict_details.items())
            if conflict_types
            else "No baseline evidence conflicts detected; all observations agree."
        )

        parent_wbs = (
            f"{activity.parent_activity.external_activity_id} ({activity.parent_activity.description})"
            if activity.parent_activity
            else "None"
        )

        return (
            "You are the Cognitive Progress Reconciliation Engine for an infrastructure project controls system.\n"
            "Your job is to reconcile multiple field evidence sources against the planned schedule activity.\n"
            "Reason about source reliability, temporal consistency, discipline consistency, and contradictions.\n\n"
            "SCHEDULE ACTIVITY KNOWLEDGE CONTEXT:\n"
            f"- Activity ID: {activity.external_activity_id}\n"
            f"- Description: {activity.description}\n"
            f"- Discipline: {activity.discipline}\n"
            f"- Location: {activity.location or 'Unspecified'}\n"
            f"- Planned Start: {activity.planned_start}\n"
            f"- Planned Finish: {activity.planned_finish}\n"
            f"- WBS Parent: {parent_wbs}\n"
            f"- Current Schedule Status: {activity.status.value}\n"
            f"- Current Schedule Progress: {activity.actual_progress}%\n\n"
            "EVIDENCE OBSERVATIONS & RELIABILITY PROFILES:\n"
            f"{evidence_text}\n\n"
            "AUTOMATED CONFLICT ANALYSIS:\n"
            f"{conflicts_summary_text}\n\n"
            "REASONING INSTRUCTIONS:\n"
            "1. Source Reliability: A direct site supervisor report (DPR, 0.90) has higher direct authority than an unverified contractor spreadsheet (0.75) or informal site diary (0.65). Explain why one source is trusted more.\n"
            "2. Temporal Consistency & Stale Evidence: If a newer direct supervisor report confirms completion, while an older spreadsheet (e.g. 14 days earlier) reports in-progress, recognize that the spreadsheet is stale evidence reflecting an earlier stage, NOT a current contradiction.\n"
            "3. Active Contradictions: If contemporary sources actively contradict each other on completion status or progress (e.g. 100% vs 80% on same date), conflict_detected MUST be true, and recommended_action must specify planner review.\n"
            "4. Progress Advancement: Moving an activity from 'not_started' to 'in_progress' or 'completed' based on evidence is EXPECTED schedule progress, not an evidence conflict.\n\n"
            "Return a valid JSON object matching these exact keys:\n"
            "{\n"
            '  "recommended_status": "completed" | "in_progress" | "not_started" | "on_hold" | "unknown",\n'
            '  "recommended_progress": float between 0.0 and 100.0 or null,\n'
            '  "recommended_actual_start": "YYYY-MM-DD" or null,\n'
            '  "recommended_actual_end": "YYYY-MM-DD" or null,\n'
            '  "conflict_detected": boolean,\n'
            '  "conflict_summary": string description of conflict or null,\n'
            '  "source_reliability_reasoning": string explaining why specific sources were prioritized,\n'
            '  "schedule_context_reasoning": string explaining how schedule timeline, discipline, and WBS informed the decision,\n'
            '  "explanation": transparent, traceable narrative of the decision,\n'
            '  "confidence": float between 0.0 and 1.0,\n'
            '  "recommended_action": string describing next action for planner or actuation layer,\n'
            '  "supporting_observations": [list of observation ID strings],\n'
            '  "contradictory_observations": [list of observation ID strings]\n'
            "}"
        )

    @staticmethod
    def _parse_ai_recommendation(raw: str) -> AIReconciliationRecommendation | None:
        try:
            cleaned = clean_json_response(raw)
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return None

            status_val = data.get("recommended_status")
            status = None
            if status_val:
                try:
                    status = ActivityStatus(str(status_val).lower())
                except ValueError:
                    status = None

            prog_val = data.get("recommended_progress")
            progress = float(prog_val) if prog_val is not None else None

            start_val = data.get("recommended_actual_start")
            actual_start = date.fromisoformat(start_val) if start_val else None
            end_val = data.get("recommended_actual_end")
            actual_end = date.fromisoformat(end_val) if end_val else None

            return AIReconciliationRecommendation(
                recommended_status=status,
                recommended_progress=progress,
                recommended_actual_start=actual_start,
                recommended_actual_end=actual_end,
                evidence_assessment=data.get("evidence_assessment"),
                conflict_detected=bool(data.get("conflict_detected", False)),
                conflict_summary=data.get("conflict_summary"),
                source_reliability_reasoning=data.get("source_reliability_reasoning"),
                schedule_context_reasoning=data.get("schedule_context_reasoning"),
                reasoning=str(data.get("reasoning") or data.get("explanation") or ""),
                confidence=float(data.get("confidence", 0.0)),
                recommended_action=data.get("recommended_action"),
                supporting_observations=[str(x) for x in data.get("supporting_observations", [])],
                contradictory_observations=[str(x) for x in data.get("contradictory_observations", [])],
            )
        except Exception:
            return None

    def _safety_gate_validate(
        self,
        activity: Activity,
        weighted: list[WeightedObservation],
        det_status: ActivityStatus,
        det_progress: float | None,
        det_conflicts: list[WeightedObservation],
        det_confidence: float,
        conflict_types: list[str],
        conflict_details: dict[str, str],
        ai_rec: AIReconciliationRecommendation | None,
    ) -> tuple[
        ReconciliationDecision,
        ActivityStatus,
        float | None,
        date | None,
        date | None,
        float,
        list[WeightedObservation],
        list[WeightedObservation],
        str,
        dict[str, Any],
        dict[str, Any],
        TemporalValidationResult,
    ]:
        validation: dict[str, Any] = {
            "ai_invoked": ai_rec is not None,
            "progress_valid": True,
            "dates_valid": True,
            "match_confidence_ok": True,
            "has_conflict": False,
        }

        # 1. Validate progress range
        if ai_rec and ai_rec.recommended_progress is not None:
            if ai_rec.recommended_progress < 0.0 or ai_rec.recommended_progress > 100.0:
                validation["progress_valid"] = False
                return (
                    ReconciliationDecision.REJECT,
                    ActivityStatus.UNKNOWN,
                    None,
                    None,
                    None,
                    0.0,
                    [],
                    weighted,
                    f"Rejected: AI recommended progress {ai_rec.recommended_progress}% is outside valid range [0, 100].",
                    validation,
                    {},
                    TemporalValidationResult(dependency_status=DependencyStatus.UNKNOWN),
                )

        # 2. Conflict Evaluation (incorporating AI reasoning + deterministic baseline)
        conflicting = list(det_conflicts)
        if ai_rec and ai_rec.conflict_detected and len(weighted) > 1:
            contradictory_ids = set(ai_rec.contradictory_observations)
            for item in weighted:
                if str(item.observation.observation_id) in contradictory_ids and item not in conflicting:
                    conflicting.append(item)
            if not conflicting and len(weighted) > 1:
                conflicting.extend(weighted[1:])

        # Stale evidence resolution check:
        # If the only conflict is a stale spreadsheet and newer supervisor report confirms completion,
        # we do not block progress if supervisor reliability is high and fresh
        stale_superseded = False
        if (
            "stale_evidence_detected" in conflict_types
            and len(conflicting) > 0
            and all(item.is_stale for item in conflicting)
            and any(item.is_direct and item.freshness > 0.80 and (item.observation.status is ActivityStatus.COMPLETED or item.progress >= 100.0) for item in weighted if item not in conflicting)
        ):
            stale_superseded = True

        has_conflict = bool(conflicting)
        validation["has_conflict"] = has_conflict
        validation["stale_superseded"] = stale_superseded

        supporting = [item for item in weighted if item not in conflicting]

        # 3. Determine reconciled status & progress
        if not has_conflict and ai_rec and ai_rec.recommended_status is not None:
            status = ai_rec.recommended_status
            progress = ai_rec.recommended_progress if ai_rec.recommended_progress is not None else det_progress
        else:
            status = det_status
            progress = det_progress

        # 4. Determine dates & run deterministic temporal / dependency validation
        det_start, det_end = self._actual_dates(supporting, status)
        actual_start = (
            ai_rec.recommended_actual_start
            if (ai_rec and ai_rec.recommended_actual_start is not None)
            else det_start
        )
        actual_end = (
            ai_rec.recommended_actual_end
            if (ai_rec and ai_rec.recommended_actual_end is not None)
            else det_end
        )

        temporal_result = TemporalValidationEngine.validate(
            activity=activity,
            proposed_status=status,
            proposed_start=actual_start,
            proposed_end=actual_end,
            proposed_progress=progress,
        )
        validation["dependency_status"] = temporal_result.dependency_status.value
        validation["dependency_rule"] = temporal_result.rule
        validation["dependency_reason"] = temporal_result.reason
        validation["dependency_details"] = [d.to_dict() for d in temporal_result.details]

        has_dependency_conflict = (temporal_result.dependency_status == DependencyStatus.CONFLICT)
        if has_dependency_conflict:
            validation["dates_valid"] = False
            if "dependency_conflict" not in conflict_types:
                conflict_types.append("dependency_conflict")
            conflict_details["dependency"] = temporal_result.reason or "Dependency conflict detected."

        if temporal_result.dependency_status == DependencyStatus.WARNING:
            if "dependency_warning" not in conflict_types:
                conflict_types.append("dependency_warning")
            conflict_details["dependency_warning"] = temporal_result.reason or "Dependency warning."

        # 5. Check match confidence of candidates
        min_match_score = min(item.match_score for item in weighted)
        match_blocked = min_match_score < 0.70
        validation["match_confidence_ok"] = not match_blocked

        # 6. Synthesize confidence
        if has_conflict or has_dependency_conflict:
            final_confidence = min(
                det_confidence,
                ai_rec.confidence if (ai_rec and ai_rec.confidence > 0) else det_confidence,
            )
        elif match_blocked:
            final_confidence = min(det_confidence, 0.65)
        elif stale_superseded:
            final_confidence = max(det_confidence, 0.86)
        else:
            final_confidence = det_confidence

        validation["final_confidence"] = final_confidence

        # 7. Decision gate: hard dependency conflicts strictly route to PLANNER_REVIEW and block AUTO_ACCEPT
        if has_conflict or has_dependency_conflict:
            decision = ReconciliationDecision.PLANNER_REVIEW
        elif match_blocked:
            decision = ReconciliationDecision.PLANNER_REVIEW
        elif final_confidence >= self.thresholds.auto_accept:
            decision = ReconciliationDecision.AUTO_ACCEPT
        elif final_confidence >= self.thresholds.review:
            decision = ReconciliationDecision.PLANNER_REVIEW
        elif final_confidence < self.thresholds.no_decision:
            decision = ReconciliationDecision.NO_DECISION
        else:
            decision = ReconciliationDecision.PLANNER_REVIEW

        # 8. Build reasoning factors & transparent explanation
        supporting_refs = [self._reference(item) for item in supporting]
        conflicting_refs = [self._reference(item) for item in conflicting]

        reasoning_factors = self._build_reasoning_factors(
            activity=activity,
            weighted=weighted,
            conflict_types=conflict_types,
            conflict_details=conflict_details,
            stale_superseded=stale_superseded,
            ai_rec=ai_rec,
        )

        explanation = self._explanation(
            activity=activity,
            status=status,
            progress=progress,
            supporting=supporting_refs,
            conflicting=conflicting_refs,
            confidence=final_confidence,
            conflict_types=conflict_types,
            reasoning_factors=reasoning_factors,
            ai_rec=ai_rec,
            has_conflict=has_conflict,
            stale_superseded=stale_superseded,
        )
        if match_blocked:
            explanation += f" Match confidence for candidate activity is low ({min_match_score:.2f} < 0.70); automatic schedule update blocked."
        if has_dependency_conflict:
            explanation += f" Schedule dependency violation detected: {temporal_result.reason} Automatic schedule update blocked; routed to Planner Review."
        elif temporal_result.dependency_status == DependencyStatus.WARNING:
            explanation += f" Schedule dependency note: {temporal_result.reason}"

        return (
            decision,
            status,
            progress,
            actual_start,
            actual_end,
            final_confidence,
            supporting,
            conflicting,
            explanation,
            validation,
            reasoning_factors,
            temporal_result,
        )


    def _build_reasoning_factors(
        self,
        activity: Activity,
        weighted: list[WeightedObservation],
        conflict_types: list[str],
        conflict_details: dict[str, str],
        stale_superseded: bool,
        ai_rec: AIReconciliationRecommendation | None,
    ) -> dict[str, Any]:
        """Construct transparent source reliability and schedule context factors."""
        # Source reliability breakdown
        rel_parts = []
        for item in weighted:
            direct_str = "direct on-site" if item.is_direct else "secondary"
            stale_str = ", STALE" if item.is_stale else ""
            rel_parts.append(
                f"{item.observation.evidence.source_name} ({item.observation.evidence.source_type.value}: "
                f"reliability {item.reliability:.2f}, freshness {item.freshness:.2f}, {direct_str}{stale_str})"
            )
        source_rel_summary = "; ".join(rel_parts)

        # Schedule context
        sched_context = (
            f"Activity {activity.external_activity_id} ('{activity.description}', {activity.discipline or 'General'}), "
            f"planned {activity.planned_start or 'N/A'} to {activity.planned_finish or 'N/A'}, "
            f"current baseline: {activity.status.value} ({activity.actual_progress or 0}%)."
        )

        factors: dict[str, Any] = {
            "source_reliability": source_rel_summary,
            "schedule_context": sched_context,
            "conflict_types": conflict_types,
            "conflict_details": conflict_details,
            "stale_evidence_superseded": stale_superseded,
        }
        if ai_rec and ai_rec.source_reliability_reasoning:
            factors["ai_reliability_reasoning"] = ai_rec.source_reliability_reasoning
        if ai_rec and ai_rec.schedule_context_reasoning:
            factors["ai_schedule_reasoning"] = ai_rec.schedule_context_reasoning
        return factors

    @staticmethod
    def _actual_dates(supporting: list[WeightedObservation], status: ActivityStatus) -> tuple[date | None, date | None]:
        starts = [item.observation.actual_start for item in supporting if item.observation.actual_start]
        ends = [item.observation.actual_end for item in supporting if item.observation.actual_end]
        return min(starts) if starts else None, max(ends) if status is ActivityStatus.COMPLETED and ends else None

    @staticmethod
    def _reference(item: WeightedObservation) -> EvidenceReference:
        evidence = item.observation.evidence
        return EvidenceReference(
            observation_id=item.observation.observation_id,
            evidence_id=evidence.evidence_id,
            source_name=evidence.source_name,
            source_type=evidence.source_type,
            source_timestamp=evidence.source_timestamp,
            status=item.observation.status,
            progress=item.observation.progress,
            weight=round(item.weight, 4),
            raw_text=item.observation.original_evidence or evidence.raw_text,
            reliability_score=round(item.reliability, 2),
            freshness_score=round(item.freshness, 2),
            is_stale=item.is_stale,
            is_duplicate=item.is_duplicate,
            contradiction_reason=item.contradiction_reason,
        )

    @staticmethod
    def _explanation(
        activity: Activity,
        status: ActivityStatus,
        progress: float | None,
        supporting: list[EvidenceReference],
        conflicting: list[EvidenceReference],
        confidence: float,
        conflict_types: list[str],
        reasoning_factors: dict[str, Any],
        ai_rec: AIReconciliationRecommendation | None = None,
        has_conflict: bool = False,
        stale_superseded: bool = False,
    ) -> str:
        if has_conflict:
            all_items = supporting + conflicting
            count = len(all_items)
            count_word = {1: "One source reports", 2: "Two sources report", 3: "Three sources report"}.get(
                count, f"{count} sources report"
            )
            prog_list = [
                f"{int(x.progress)}%"
                if x.progress is not None
                else ("ongoing" if x.status is ActivityStatus.IN_PROGRESS else x.status.value)
                for x in all_items
            ]
            has_supervisor = any("supervisor" in x.source_name.lower() for x in all_items)
            if has_supervisor:
                prefix = (
                    f"{count_word} conflicting progress ({', '.join(prog_list)}). "
                    f"Although the supervisor report indicates completion, independent contractor and diary evidence disagree. "
                    f"The evidence set does not meet the configured confidence threshold for automatic acceptance."
                )
            else:
                prefix = (
                    f"{count_word} conflicting progress ({', '.join(prog_list)}). "
                    f"Independent evidence sources disagree on progress or activity status. "
                    f"The evidence set does not meet the configured confidence threshold for automatic acceptance."
                )
            if ai_rec and ai_rec.reasoning:
                prefix += f" AI Assessment: {ai_rec.reasoning}."
            prefix += " Conflicting evidence retained for review: " + ", ".join(
                f"{item.source_name} reports {item.status.value}" for item in conflicting
            ) + "."
            if any(item.is_stale for item in conflicting):
                stale_sources = ", ".join(item.source_name for item in conflicting if item.is_stale)
                prefix += f" Note: older records from ({stale_sources}) are flagged as stale evidence."
            return prefix

        if stale_superseded:
            names = ", ".join(item.source_name for item in supporting)
            return (
                f"Activity {activity.external_activity_id} is reconciled as {status.value} at {progress:.1f}% "
                f"with confidence {confidence:.2f}. Newer direct field report ({names}) confirms completion, "
                f"superseding older secondary spreadsheet records treated as stale rather than an active contradiction."
            )

        names = ", ".join(item.source_name for item in supporting) or "no matched evidence"
        text = (
            f"Activity {activity.external_activity_id} is reconciled as {status.value} at {progress:.1f}% "
            f"with confidence {confidence:.2f}, based on {names}."
        ) if progress is not None else (
            f"Activity {activity.external_activity_id} has no defensible progress state because no matched evidence was available."
        )
        if conflicting:
            text += " Conflicting evidence retained for review: " + ", ".join(
                f"{item.source_name} reports {item.status.value}" for item in conflicting
            ) + "."
        if ai_rec and ai_rec.reasoning:
            text += f" AI Assessment: {ai_rec.reasoning}."
        return text

    @staticmethod
    def _recommended_action(decision: ReconciliationDecision, has_conflict: bool) -> str:
        if decision is ReconciliationDecision.AUTO_ACCEPT:
            return "Automatically update the internal prototype schedule from this evidence-backed recommendation."
        if decision is ReconciliationDecision.NO_DECISION:
            return "Collect additional independently sourced field evidence before updating the schedule."
        if decision is ReconciliationDecision.REJECT:
            return "Reject this evidence set for schedule updating because it does not state an interpretable progress condition."
        return (
            "Planner review required: verify conflicting evidence records and work-front scope."
            if has_conflict
            else "Planner review required before any schedule update."
        )

    def _create_conflicts(
        self,
        activity: Activity,
        conflicting: list[EvidenceReference],
        status: ActivityStatus,
        progress: float | None,
        conflict_types: list[str] | None = None,
    ) -> None:
        if conflicting:
            sources = ", ".join(f"{item.source_name} ({item.observation_id})" for item in conflicting)
            conflict_type = (
                ConflictType.STATUS
                if any(item.status != status for item in conflicting)
                else ConflictType.PROGRESS
            )
            type_label = f" [{', '.join(conflict_types)}]" if conflict_types else ""
            self.session.add(
                EvidenceConflict(
                    activity_id=activity.activity_id,
                    conflict_type=conflict_type,
                    severity=ConflictSeverity.HIGH,
                    description=(
                        f"Reconciliation selected {status.value} at {progress}% but conflicting observations remain{type_label}: {sources}."
                    ),
                )
            )

    def _record_no_decision(self, activity: Activity) -> ReconciliationResponse:
        reconciliation = Reconciliation(
            activity_id=activity.activity_id,
            reconciled_status=ActivityStatus.UNKNOWN,
            reconciled_progress=None,
            actual_start=None,
            actual_end=None,
            confidence=0.0,
            explanation=f"Activity {activity.external_activity_id} has no defensible progress state because no matched evidence was available.",
            decision=ReconciliationDecision.NO_DECISION,
            supporting_evidence=[],
            conflicting_evidence=[],
            recommended_action=self._recommended_action(ReconciliationDecision.NO_DECISION, False),
        )
        self.session.add(reconciliation)
        self.session.commit()
        return self._response(reconciliation)

    def _record_reject(
        self, activity: Activity, weighted: list[WeightedObservation], explanation: str
    ) -> ReconciliationResponse:
        supporting_refs = [self._reference(item) for item in weighted]
        reconciliation = Reconciliation(
            activity_id=activity.activity_id,
            reconciled_status=ActivityStatus.UNKNOWN,
            reconciled_progress=None,
            actual_start=None,
            actual_end=None,
            confidence=0.0,
            explanation=explanation,
            decision=ReconciliationDecision.REJECT,
            supporting_evidence=[item.model_dump(mode="json") for item in supporting_refs],
            conflicting_evidence=[],
            recommended_action=self._recommended_action(ReconciliationDecision.REJECT, False),
        )
        self.session.add(reconciliation)
        self.session.commit()
        return self._response(reconciliation)

    @staticmethod
    def _response(
        item: Reconciliation,
        ai_rec: AIReconciliationRecommendation | None = None,
        conflict_detected: bool = False,
        conflict_types: list[str] | None = None,
        reasoning_factors: dict[str, object] | None = None,
        temporal_result: TemporalValidationResult | None = None,
    ) -> ReconciliationResponse:
        has_conf = conflict_detected or bool(item.conflicting_evidence)
        dep_status = "VALID"
        dep_details: list[DependencyValidationDetailResponse] = []
        if temporal_result is not None:
            dep_status = temporal_result.dependency_status.value
            dep_details = [
                DependencyValidationDetailResponse(
                    predecessor_activity_id=d.predecessor_activity_id,
                    predecessor_activity_name=d.predecessor_activity_name,
                    successor_activity_id=d.successor_activity_id,
                    successor_activity_name=d.successor_activity_name,
                    relevant_actual_start=d.relevant_actual_start,
                    relevant_actual_end=d.relevant_actual_end,
                    rule=d.rule,
                    status=d.status.value,
                    reason=d.reason,
                )
                for d in temporal_result.details
            ]
        elif item.activity is not None:
            res = TemporalValidationEngine.validate(
                item.activity,
                proposed_status=item.reconciled_status,
                proposed_start=item.actual_start,
                proposed_end=item.actual_end,
                proposed_progress=item.reconciled_progress,
            )
            dep_status = res.dependency_status.value
            dep_details = [
                DependencyValidationDetailResponse(
                    predecessor_activity_id=d.predecessor_activity_id,
                    predecessor_activity_name=d.predecessor_activity_name,
                    successor_activity_id=d.successor_activity_id,
                    successor_activity_name=d.successor_activity_name,
                    relevant_actual_start=d.relevant_actual_start,
                    relevant_actual_end=d.relevant_actual_end,
                    rule=d.rule,
                    status=d.status.value,
                    reason=d.reason,
                )
                for d in res.details
            ]

        return ReconciliationResponse(
            reconciliation_id=item.reconciliation_id,
            activity_id=item.activity_id,
            reconciled_status=item.reconciled_status,
            reconciled_progress=item.reconciled_progress,
            actual_start=item.actual_start,
            actual_end=item.actual_end,
            confidence=item.confidence,
            decision=item.decision,
            explanation=item.explanation,
            supporting_evidence=[EvidenceReference.model_validate(x) for x in item.supporting_evidence],
            conflicting_evidence=[EvidenceReference.model_validate(x) for x in item.conflicting_evidence],
            recommended_action=item.recommended_action,
            created_at=item.created_at,
            ai_recommendation=ai_rec,
            conflict_detected=has_conf,
            conflict_types=conflict_types or [],
            reasoning_factors=reasoning_factors or {},
            dependency_status=dep_status,
            dependency_details=dep_details,
        )
