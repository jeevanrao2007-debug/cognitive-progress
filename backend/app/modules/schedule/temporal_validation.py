"""Deterministic temporal and schedule dependency validation engine.

Validates execution order relationships between activities without relying on LLMs.
Enforces:
- Rule 1: Date sanity (actual_start <= actual_end)
- Rule 2: Finish-to-start dependencies (successor start >= predecessor completion)
- Rule 3: Completion dependencies (successor cannot be complete if predecessor strongly known incomplete)
- Rule 4: Missing dates handling (UNKNOWN without manufacturing dates)
- Rule 5: Legitimate overlap preservation (unconstrained activities may overlap)
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from app.database.models import Activity, ActivityDependency, ActivityStatus, DependencyType


class DependencyStatus(str, enum.Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


@dataclass
class DependencyValidationDetail:
    predecessor_activity_id: str | None
    predecessor_activity_name: str | None
    successor_activity_id: str | None
    successor_activity_name: str | None
    relevant_actual_start: date | None
    relevant_actual_end: date | None
    rule: str
    status: DependencyStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "predecessor_activity_id": self.predecessor_activity_id,
            "predecessor_activity_name": self.predecessor_activity_name,
            "successor_activity_id": self.successor_activity_id,
            "successor_activity_name": self.successor_activity_name,
            "relevant_actual_start": self.relevant_actual_start.isoformat() if self.relevant_actual_start else None,
            "relevant_actual_end": self.relevant_actual_end.isoformat() if self.relevant_actual_end else None,
            "rule": self.rule,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclass
class TemporalValidationResult:
    dependency_status: DependencyStatus
    details: list[DependencyValidationDetail] = field(default_factory=list)
    rule: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency_status": self.dependency_status.value,
            "rule": self.rule,
            "reason": self.reason,
            "details": [d.to_dict() for d in self.details],
        }


class TemporalValidationEngine:
    """Deterministic validation of schedule dependencies and temporal execution constraints."""

    @classmethod
    def validate(
        cls,
        activity: Activity,
        proposed_status: ActivityStatus | None = None,
        proposed_start: date | None = None,
        proposed_end: date | None = None,
        proposed_progress: float | None = None,
    ) -> TemporalValidationResult:
        effective_status = proposed_status or activity.status
        effective_start = proposed_start or activity.actual_start
        effective_end = proposed_end or activity.actual_end
        effective_progress = proposed_progress if proposed_progress is not None else activity.actual_progress

        details: list[DependencyValidationDetail] = []

        # RULE 1: Date sanity on the activity itself
        if effective_start and effective_end and effective_end < effective_start:
            sanity_detail = DependencyValidationDetail(
                predecessor_activity_id=None,
                predecessor_activity_name=None,
                successor_activity_id=activity.external_activity_id,
                successor_activity_name=activity.description,
                relevant_actual_start=effective_start,
                relevant_actual_end=effective_end,
                rule="RULE_1_DATE_SANITY",
                status=DependencyStatus.CONFLICT,
                reason=(
                    f"Invalid temporal sequence: reported actual end for {activity.external_activity_id} ({effective_end}) "
                    f"occurs before actual start ({effective_start})."
                ),
            )
            return TemporalValidationResult(
                dependency_status=DependencyStatus.CONFLICT,
                details=[sanity_detail],
                rule="RULE_1_DATE_SANITY",
                reason=sanity_detail.reason,
            )

        predecessor_deps = list(activity.predecessors or [])

        # RULE 5: Overlap permitted if no explicit dependencies exist
        if not predecessor_deps:
            return TemporalValidationResult(
                dependency_status=DependencyStatus.VALID,
                details=[],
                rule="RULE_5_NO_DEPENDENCY",
                reason="No dependency constraints; sequence is consistent.",
            )

        # Validate each predecessor relationship
        for dep in predecessor_deps:
            pred = dep.predecessor
            if pred is None:
                continue

            detail = cls._validate_dependency_pair(
                pred=pred,
                successor=activity,
                dep=dep,
                successor_status=effective_status,
                successor_start=effective_start,
                successor_end=effective_end,
                successor_progress=effective_progress,
            )
            details.append(detail)

        # Aggregate overall status
        # Priority: CONFLICT > WARNING > UNKNOWN > VALID
        has_conflict = any(d.status == DependencyStatus.CONFLICT for d in details)
        has_warning = any(d.status == DependencyStatus.WARNING for d in details)
        has_unknown = any(d.status == DependencyStatus.UNKNOWN for d in details)

        if has_conflict:
            primary = next(d for d in details if d.status == DependencyStatus.CONFLICT)
            return TemporalValidationResult(
                dependency_status=DependencyStatus.CONFLICT,
                details=details,
                rule=primary.rule,
                reason=primary.reason,
            )
        elif has_warning:
            primary = next(d for d in details if d.status == DependencyStatus.WARNING)
            return TemporalValidationResult(
                dependency_status=DependencyStatus.WARNING,
                details=details,
                rule=primary.rule,
                reason=primary.reason,
            )
        elif has_unknown:
            primary = next(d for d in details if d.status == DependencyStatus.UNKNOWN)
            return TemporalValidationResult(
                dependency_status=DependencyStatus.UNKNOWN,
                details=details,
                rule=primary.rule,
                reason=primary.reason,
            )
        else:
            primary = details[0] if details else None
            return TemporalValidationResult(
                dependency_status=DependencyStatus.VALID,
                details=details,
                rule="RULE_2_FINISH_TO_START",
                reason=primary.reason if primary else "Dependency sequence is consistent.",
            )

    @classmethod
    def _validate_dependency_pair(
        cls,
        pred: Activity,
        successor: Activity,
        dep: ActivityDependency,
        successor_status: ActivityStatus,
        successor_start: date | None,
        successor_end: date | None,
        successor_progress: float | None,
    ) -> DependencyValidationDetail:
        pred_id = pred.external_activity_id
        succ_id = successor.external_activity_id

        # RULE 2: Finish-to-Start dependency check
        # If successor actual_start exists and predecessor actual_end exists
        if successor_start is not None and pred.actual_end is not None:
            if successor_start < pred.actual_end:
                days_early = (pred.actual_end - successor_start).days
                return DependencyValidationDetail(
                    predecessor_activity_id=pred_id,
                    predecessor_activity_name=pred.description,
                    successor_activity_id=succ_id,
                    successor_activity_name=successor.description,
                    relevant_actual_start=successor_start,
                    relevant_actual_end=pred.actual_end,
                    rule="RULE_2_FINISH_TO_START",
                    status=DependencyStatus.CONFLICT,
                    reason=(
                        f"Reported actual start for {succ_id} ({successor_start}) occurs {days_early} "
                        f"day{'s' if days_early != 1 else ''} before predecessor {pred_id} actual completion ({pred.actual_end})."
                    ),
                )
            elif successor_start == pred.actual_end:
                return DependencyValidationDetail(
                    predecessor_activity_id=pred_id,
                    predecessor_activity_name=pred.description,
                    successor_activity_id=succ_id,
                    successor_activity_name=successor.description,
                    relevant_actual_start=successor_start,
                    relevant_actual_end=pred.actual_end,
                    rule="RULE_2_FINISH_TO_START",
                    status=DependencyStatus.VALID,
                    reason=f"Exact boundary sequence satisfied with predecessor {pred_id} on {successor_start}.",
                )
            else:
                return DependencyValidationDetail(
                    predecessor_activity_id=pred_id,
                    predecessor_activity_name=pred.description,
                    successor_activity_id=succ_id,
                    successor_activity_name=successor.description,
                    relevant_actual_start=successor_start,
                    relevant_actual_end=pred.actual_end,
                    rule="RULE_2_FINISH_TO_START",
                    status=DependencyStatus.VALID,
                    reason=f"Finish-to-start sequence with predecessor {pred_id} is consistent.",
                )

        # RULE 3: Completion dependency check
        # If successor is reported COMPLETED (or 100%), but predecessor is explicitly known incomplete
        is_succ_completed = (
            successor_status == ActivityStatus.COMPLETED or (successor_progress is not None and successor_progress >= 100.0)
        )
        if is_succ_completed:
            # Check if predecessor is strongly incomplete
            pred_is_completed = (
                pred.status == ActivityStatus.COMPLETED or (pred.actual_progress is not None and pred.actual_progress >= 100.0)
            )
            pred_is_active = pred.status in (ActivityStatus.IN_PROGRESS, ActivityStatus.NOT_STARTED) and (
                pred.actual_progress is not None and pred.actual_progress < 100.0
            )

            if pred_is_active and not pred_is_completed:
                return DependencyValidationDetail(
                    predecessor_activity_id=pred_id,
                    predecessor_activity_name=pred.description,
                    successor_activity_id=succ_id,
                    successor_activity_name=successor.description,
                    relevant_actual_start=successor_start,
                    relevant_actual_end=pred.actual_end,
                    rule="RULE_3_COMPLETION_DEPENDENCY",
                    status=DependencyStatus.CONFLICT,
                    reason=(
                        f"Activity {succ_id} is reported COMPLETED, but predecessor {pred_id} "
                        f"is actively {pred.status.value} ({pred.actual_progress or 0}% complete)."
                    ),
                )
            elif pred_is_completed:
                return DependencyValidationDetail(
                    predecessor_activity_id=pred_id,
                    predecessor_activity_name=pred.description,
                    successor_activity_id=succ_id,
                    successor_activity_name=successor.description,
                    relevant_actual_start=successor_start,
                    relevant_actual_end=pred.actual_end,
                    rule="RULE_3_COMPLETION_DEPENDENCY",
                    status=DependencyStatus.VALID,
                    reason=f"Predecessor {pred_id} completion verified.",
                )

        # RULE 4: Missing dates
        # Dates are unavailable to fully evaluate finish-to-start ordering
        return DependencyValidationDetail(
            predecessor_activity_id=pred_id,
            predecessor_activity_name=pred.description,
            successor_activity_id=succ_id,
            successor_activity_name=successor.description,
            relevant_actual_start=successor_start,
            relevant_actual_end=pred.actual_end,
            rule="RULE_4_MISSING_DATES",
            status=DependencyStatus.UNKNOWN,
            reason=f"Dependency exists with predecessor {pred_id}, but required actual dates are unavailable.",
        )
