"""Schedule bridge service: verified actuals update model, change preview, and safe export."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import (
    Activity,
    ActivityStatus,
    ConflictType,
    EvidenceConflict,
    ObservationMatchCandidate,
    ObservationMatchResult,
    PlannerReview,
    Project,
    Reconciliation,
    ReconciliationDecision,
    ReviewDecision,
    ScheduleUpdate,
)
from app.modules.schedule.schemas import (
    ScheduleChangeItem,
    ScheduleChangePreviewResponse,
    ScheduleDecisionState,
    ScheduleExportSummary,
)
from app.modules.schedule.temporal_validation import (
    DependencyStatus,
    TemporalValidationEngine,
)


class ScheduleBridgeService:
    """Bridges evidence reconciliation with downstream schedule export.
    
    CRITICAL INVARIANT: Only VERIFIED / APPROVED actuals may appear in the
    verified schedule export. Planner Review, Conflict, Unknown, and Rejected
    decisions must not silently become verified schedule updates.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_change_preview(self, project_id: uuid.UUID) -> ScheduleChangePreviewResponse:
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError("Project not found.")

        activities = list(
            self.session.scalars(
                select(Activity)
                .where(Activity.project_id == project_id)
                .options(
                    selectinload(Activity.schedule_updates),
                    selectinload(Activity.reconciliations),
                    selectinload(Activity.reviews),
                    selectinload(Activity.conflicts),
                    selectinload(Activity.predecessors),
                    selectinload(Activity.successors),
                )
                .order_by(Activity.external_activity_id)
            )
        )

        changes: list[ScheduleChangeItem] = []
        counts = {
            ScheduleDecisionState.VERIFIED: 0,
            ScheduleDecisionState.PLANNER_REVIEW: 0,
            ScheduleDecisionState.CONFLICT: 0,
            ScheduleDecisionState.REJECTED: 0,
            ScheduleDecisionState.UNCHANGED: 0,
        }

        for activity in activities:
            state, act_changes = self._evaluate_activity(activity)
            counts[state] += 1
            changes.extend(act_changes)

        summary = ScheduleExportSummary(
            activities_evaluated=len(activities),
            verified_updates=counts[ScheduleDecisionState.VERIFIED],
            planner_review=counts[ScheduleDecisionState.PLANNER_REVIEW],
            conflicts=counts[ScheduleDecisionState.CONFLICT],
            rejected=counts[ScheduleDecisionState.REJECTED],
            unchanged=counts[ScheduleDecisionState.UNCHANGED],
        )

        return ScheduleChangePreviewResponse(
            project_id=project_id,
            summary=summary,
            changes=changes,
        )

    def export_verified_schedule(
        self, project_id: uuid.UUID, export_format: str = "csv"
    ) -> tuple[bytes, str, str]:
        """Export verified schedule.
        
        Returns (file_bytes, media_type, filename).
        Enforces export safety: Unverified records are strictly excluded from actual fields.
        """
        project = self.session.get(Project, project_id)
        if project is None:
            raise ValueError("Project not found.")

        activities = list(
            self.session.scalars(
                select(Activity)
                .where(Activity.project_id == project_id)
                .options(
                    selectinload(Activity.schedule_updates),
                    selectinload(Activity.reconciliations),
                    selectinload(Activity.reviews),
                    selectinload(Activity.conflicts),
                    selectinload(Activity.predecessors),
                )
                .order_by(Activity.external_activity_id)
            )
        )

        rows: list[dict[str, Any]] = []
        excluded_rows: list[dict[str, Any]] = []

        for activity in activities:
            state, _ = self._evaluate_activity(activity)
            latest_update = self._latest_verified_update(activity)

            if state == ScheduleDecisionState.VERIFIED and latest_update is not None:
                new_val = latest_update.new_value
                act_start = new_val.get("actual_start") or (
                    activity.actual_start.isoformat() if activity.actual_start else ""
                )
                act_end = new_val.get("actual_end") or (
                    activity.actual_end.isoformat() if activity.actual_end else ""
                )
                progress = new_val.get("actual_progress")
                if progress is None and activity.actual_progress is not None:
                    progress = activity.actual_progress
                progress_str = f"{progress:.1f}" if progress is not None else ""
                status_str = new_val.get("status") or activity.status.value
                export_status = "VERIFIED_UPDATE"
                source_ver = latest_update.decision_source
                evidence_ref = self._format_evidence_sources(latest_update.evidence)
                audit_time = latest_update.created_at.isoformat()
            elif state in {
                ScheduleDecisionState.PLANNER_REVIEW,
                ScheduleDecisionState.CONFLICT,
                ScheduleDecisionState.REJECTED,
            }:
                # SAFETY GATE: Exclude unverified actual dates from verified schedule!
                # Baseline pre-existing dates are preserved if they were already part of the baseline import,
                # but unverified proposed values from reconciliations are strictly withheld.
                prev_val = latest_update.new_value if latest_update else {}
                act_start = prev_val.get("actual_start") or ""
                act_end = prev_val.get("actual_end") or ""
                progress_str = f"{prev_val.get('actual_progress', ''):.1f}" if prev_val.get("actual_progress") is not None else ""
                status_str = prev_val.get("status") or ActivityStatus.NOT_STARTED.value
                export_status = f"EXCLUDED_{state.value}"
                source_ver = "SAFETY_GATE_WITHHELD"
                evidence_ref = f"Withheld: {state.value} unverified"
                audit_time = ""

                # Add to excluded audit sheet
                rec = self._latest_reconciliation(activity)
                excluded_rows.append({
                    "activity_id": activity.external_activity_id,
                    "activity_name": activity.description,
                    "state": state.value,
                    "reason": rec.explanation if rec else "Unresolved schedule condition",
                    "proposed_actual_start": rec.actual_start.isoformat() if rec and rec.actual_start else "—",
                    "proposed_actual_end": rec.actual_end.isoformat() if rec and rec.actual_end else "—",
                    "proposed_progress": f"{rec.reconciled_progress:.1f}%" if rec and rec.reconciled_progress is not None else "—",
                    "proposed_status": rec.reconciled_status.value if rec else "—",
                    "confidence": f"{rec.confidence * 100:.1f}%" if rec else "—",
                })
            else:
                # UNCHANGED
                act_start = activity.actual_start.isoformat() if activity.actual_start else ""
                act_end = activity.actual_end.isoformat() if activity.actual_end else ""
                progress_str = f"{activity.actual_progress:.1f}" if activity.actual_progress is not None else ""
                status_str = activity.status.value
                export_status = "UNCHANGED"
                source_ver = "baseline"
                evidence_ref = "Baseline Schedule"
                audit_time = ""

            rows.append({
                "activity_id": activity.external_activity_id,
                "activity_name": activity.description,
                "wbs": activity.parent_activity.external_activity_id if activity.parent_activity else "",
                "discipline": activity.discipline or "",
                "location": activity.location or "",
                "level": activity.level,
                "planned_start": activity.planned_start.isoformat() if activity.planned_start else "",
                "planned_finish": activity.planned_finish.isoformat() if activity.planned_finish else "",
                "actual_start": act_start,
                "actual_end": act_end,
                "percent_complete": progress_str,
                "status": status_str,
                "export_status": export_status,
                "verification_source": source_ver,
                "source_evidence": evidence_ref,
                "audit_timestamp": audit_time,
            })

        clean_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.name).strip("_")
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M")

        fmt = export_format.lower()
        if fmt == "xlsx":
            return self._build_xlsx(rows, excluded_rows, clean_name, timestamp_str)
        elif fmt == "csv":
            return self._build_csv(rows, clean_name, timestamp_str)
        else:
            raise ValueError(f"Unsupported export format: {export_format}. Expected 'csv' or 'xlsx'.")

    def _evaluate_activity(
        self, activity: Activity
    ) -> tuple[ScheduleDecisionState, list[ScheduleChangeItem]]:
        """Evaluate activity and return its decision state and detailed change items."""
        latest_update = self._latest_verified_update(activity)
        latest_rec = self._latest_reconciliation(activity)
        pending_review = self._pending_review(activity)
        temporal_result = TemporalValidationEngine.validate(activity)
        has_dependency_conflict = (
            temporal_result.dependency_status == DependencyStatus.CONFLICT
        )
        has_open_conflicts = any(
            c.conflict_type == ConflictType.DEPENDENCY or c.resolution_status.value == "open"
            for c in activity.conflicts
        )

        temp_status = (
            "CONFLICT"
            if has_dependency_conflict
            else ("WARNING" if temporal_result.dependency_status == DependencyStatus.WARNING else "VALID")
        )

        # 1. Check if there is a VERIFIED update
        if latest_update is not None:
            items = self._build_change_items_from_update(
                activity, latest_update, latest_rec, temp_status
            )
            return ScheduleDecisionState.VERIFIED, items

        # 2. Check for REJECTED
        if (
            (latest_rec and latest_rec.decision in {ReconciliationDecision.REJECT, ReconciliationDecision.PLANNER_REJECTED})
            or (activity.reviews and any(r.reviewer_decision == ReviewDecision.REJECT for r in activity.reviews))
        ):
            items = self._build_unverified_change_items(
                activity,
                latest_rec,
                ScheduleDecisionState.REJECTED,
                "Reconciliation or review was rejected; changes excluded from schedule.",
                temp_status,
            )
            return ScheduleDecisionState.REJECTED, items

        # 3. Check for CONFLICT
        if has_dependency_conflict or has_open_conflicts:
            reason = (
                f"Schedule dependency violation: {temporal_result.reason}"
                if has_dependency_conflict
                else "Unresolved evidence conflicts detected."
            )
            items = self._build_unverified_change_items(
                activity,
                latest_rec,
                ScheduleDecisionState.CONFLICT,
                reason,
                "CONFLICT",
            )
            return ScheduleDecisionState.CONFLICT, items

        # 4. Check for PLANNER_REVIEW
        if pending_review or (
            latest_rec
            and latest_rec.decision
            in {
                ReconciliationDecision.PLANNER_REVIEW,
                ReconciliationDecision.PLANNER_REVIEW_REQUIRED,
            }
        ):
            reason = (
                pending_review.reason
                if pending_review
                else (latest_rec.explanation if latest_rec else "Pending planner review")
            )
            items = self._build_unverified_change_items(
                activity,
                latest_rec,
                ScheduleDecisionState.PLANNER_REVIEW,
                reason,
                temp_status,
            )
            return ScheduleDecisionState.PLANNER_REVIEW, items

        # 5. UNCHANGED
        item = ScheduleChangeItem(
            activity_id=activity.activity_id,
            external_activity_id=activity.external_activity_id,
            activity_name=activity.description,
            discipline=activity.discipline,
            location=activity.location,
            field="Status / Dates",
            old_value=activity.status.value,
            new_value=activity.status.value,
            source_evidence="Baseline Schedule",
            match_confidence=None,
            reconciliation_confidence=None,
            temporal_status=temp_status,
            decision=ScheduleDecisionState.UNCHANGED,
            decision_source="baseline",
            rationale="No execution updates or reconciliation applied; baseline intact.",
            updated_at=None,
        )
        return ScheduleDecisionState.UNCHANGED, [item]

    def _build_change_items_from_update(
        self,
        activity: Activity,
        update: ScheduleUpdate,
        reconciliation: Reconciliation | None,
        temporal_status: str,
    ) -> list[ScheduleChangeItem]:
        items: list[ScheduleChangeItem] = []
        prev = update.previous_value
        new = update.new_value
        evidence_str = self._format_evidence_sources(update.evidence)
        rec_conf = reconciliation.confidence if reconciliation else 1.0
        match_conf = self._get_match_confidence(activity, reconciliation)

        # Actual End
        if new.get("actual_end") or prev.get("actual_end"):
            if new.get("actual_end") != prev.get("actual_end"):
                items.append(
                    ScheduleChangeItem(
                        activity_id=activity.activity_id,
                        external_activity_id=activity.external_activity_id,
                        activity_name=activity.description,
                        discipline=activity.discipline,
                        location=activity.location,
                        field="Actual End",
                        old_value=prev.get("actual_end") or "—",
                        new_value=new.get("actual_end") or "—",
                        source_evidence=evidence_str,
                        match_confidence=match_conf,
                        reconciliation_confidence=rec_conf,
                        temporal_status=temporal_status,
                        decision=ScheduleDecisionState.VERIFIED,
                        decision_source=update.decision_source,
                        rationale=update.reason,
                        updated_at=update.created_at,
                    )
                )

        # Actual Start
        if new.get("actual_start") or prev.get("actual_start"):
            if new.get("actual_start") != prev.get("actual_start"):
                items.append(
                    ScheduleChangeItem(
                        activity_id=activity.activity_id,
                        external_activity_id=activity.external_activity_id,
                        activity_name=activity.description,
                        discipline=activity.discipline,
                        location=activity.location,
                        field="Actual Start",
                        old_value=prev.get("actual_start") or "—",
                        new_value=new.get("actual_start") or "—",
                        source_evidence=evidence_str,
                        match_confidence=match_conf,
                        reconciliation_confidence=rec_conf,
                        temporal_status=temporal_status,
                        decision=ScheduleDecisionState.VERIFIED,
                        decision_source=update.decision_source,
                        rationale=update.reason,
                        updated_at=update.created_at,
                    )
                )

        # Status
        if new.get("status") != prev.get("status"):
            items.append(
                ScheduleChangeItem(
                    activity_id=activity.activity_id,
                    external_activity_id=activity.external_activity_id,
                    activity_name=activity.description,
                    discipline=activity.discipline,
                    location=activity.location,
                    field="Status",
                    old_value=prev.get("status") or "—",
                    new_value=new.get("status") or "—",
                    source_evidence=evidence_str,
                    match_confidence=match_conf,
                    reconciliation_confidence=rec_conf,
                    temporal_status=temporal_status,
                    decision=ScheduleDecisionState.VERIFIED,
                    decision_source=update.decision_source,
                    rationale=update.reason,
                    updated_at=update.created_at,
                )
            )

        # Progress
        prev_prog = prev.get("actual_progress")
        new_prog = new.get("actual_progress")
        if prev_prog != new_prog and new_prog is not None:
            items.append(
                ScheduleChangeItem(
                    activity_id=activity.activity_id,
                    external_activity_id=activity.external_activity_id,
                    activity_name=activity.description,
                    discipline=activity.discipline,
                    location=activity.location,
                    field="Progress",
                    old_value=f"{prev_prog:.1f}%" if prev_prog is not None else "0%",
                    new_value=f"{new_prog:.1f}%",
                    source_evidence=evidence_str,
                    match_confidence=match_conf,
                    reconciliation_confidence=rec_conf,
                    temporal_status=temporal_status,
                    decision=ScheduleDecisionState.VERIFIED,
                    decision_source=update.decision_source,
                    rationale=update.reason,
                    updated_at=update.created_at,
                )
            )

        if not items:
            # Emitted if fields had minor or internal change
            items.append(
                ScheduleChangeItem(
                    activity_id=activity.activity_id,
                    external_activity_id=activity.external_activity_id,
                    activity_name=activity.description,
                    discipline=activity.discipline,
                    location=activity.location,
                    field="Actual Dates",
                    old_value=prev.get("actual_end") or prev.get("actual_start") or "—",
                    new_value=new.get("actual_end") or new.get("actual_start") or "—",
                    source_evidence=evidence_str,
                    match_confidence=match_conf,
                    reconciliation_confidence=rec_conf,
                    temporal_status=temporal_status,
                    decision=ScheduleDecisionState.VERIFIED,
                    decision_source=update.decision_source,
                    rationale=update.reason,
                    updated_at=update.created_at,
                )
            )

        return items

    def _build_unverified_change_items(
        self,
        activity: Activity,
        reconciliation: Reconciliation | None,
        decision: ScheduleDecisionState,
        rationale: str,
        temporal_status: str,
    ) -> list[ScheduleChangeItem]:
        items: list[ScheduleChangeItem] = []
        rec_conf = reconciliation.confidence if reconciliation else None
        match_conf = self._get_match_confidence(activity, reconciliation)
        evidence_str = (
            self._format_evidence_sources(
                (reconciliation.supporting_evidence + reconciliation.conflicting_evidence)
                if reconciliation
                else []
            )
            or "Field DPR"
        )

        field_name = "Proposed Actual End" if (reconciliation and reconciliation.actual_end) else "Proposed Actual Start"
        new_val = (
            reconciliation.actual_end.isoformat()
            if (reconciliation and reconciliation.actual_end)
            else (
                reconciliation.actual_start.isoformat()
                if (reconciliation and reconciliation.actual_start)
                else (reconciliation.reconciled_status.value if reconciliation else "—")
            )
        )
        old_val = (
            activity.actual_end.isoformat()
            if activity.actual_end
            else (activity.actual_start.isoformat() if activity.actual_start else "—")
        )

        items.append(
            ScheduleChangeItem(
                activity_id=activity.activity_id,
                external_activity_id=activity.external_activity_id,
                activity_name=activity.description,
                discipline=activity.discipline,
                location=activity.location,
                field=field_name,
                old_value=old_val,
                new_value=new_val,
                source_evidence=evidence_str,
                match_confidence=match_conf,
                reconciliation_confidence=rec_conf,
                temporal_status=temporal_status,
                decision=decision,
                decision_source="reconciliation:unverified",
                rationale=rationale,
                updated_at=reconciliation.created_at if reconciliation else None,
            )
        )
        return items

    def _latest_verified_update(self, activity: Activity) -> ScheduleUpdate | None:
        if not activity.schedule_updates:
            return None
        return sorted(activity.schedule_updates, key=lambda u: u.created_at)[-1]

    def _latest_reconciliation(self, activity: Activity) -> Reconciliation | None:
        if not activity.reconciliations:
            return None
        return sorted(activity.reconciliations, key=lambda r: r.created_at)[-1]

    def _pending_review(self, activity: Activity) -> PlannerReview | None:
        if not activity.reviews:
            return None
        for review in activity.reviews:
            if review.reviewer_decision == ReviewDecision.PENDING:
                return review
        return None

    def _get_match_confidence(
        self, activity: Activity, reconciliation: Reconciliation | None
    ) -> float | None:
        if not reconciliation:
            return None
        all_ev = reconciliation.supporting_evidence + reconciliation.conflicting_evidence
        obs_ids: list[uuid.UUID] = []
        for item in all_ev:
            oid = item.get("observation_id")
            if oid:
                try:
                    obs_ids.append(uuid.UUID(str(oid)))
                except ValueError:
                    pass
        if not obs_ids:
            return None

        # Look up candidate score
        candidate = self.session.scalar(
            select(ObservationMatchCandidate)
            .join(ObservationMatchCandidate.result)
            .where(
                ObservationMatchCandidate.activity_id == activity.activity_id,
                ObservationMatchResult.observation_id.in_(obs_ids),
            )
            .order_by(ObservationMatchCandidate.final_score.desc())
        )
        if candidate is not None:
            return candidate.final_score
        return None

    @staticmethod
    def _format_evidence_sources(evidence_items: list[dict[str, Any]]) -> str:
        if not evidence_items:
            return "—"
        sources: list[str] = []
        for item in evidence_items:
            s_name = item.get("source_name") or item.get("source_type") or "Evidence"
            if s_name not in sources:
                sources.append(s_name)
        return ", ".join(sources) if sources else "—"

    def _build_csv(
        self, rows: list[dict[str, Any]], project_name: str, timestamp_str: str
    ) -> tuple[bytes, str, str]:
        headers = [
            "activity_id",
            "activity_name",
            "wbs",
            "discipline",
            "location",
            "level",
            "planned_start",
            "planned_finish",
            "actual_start",
            "actual_end",
            "percent_complete",
            "status",
            "export_status",
            "verification_source",
            "source_evidence",
            "audit_timestamp",
        ]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})

        csv_bytes = output.getvalue().encode("utf-8-sig")
        filename = f"{project_name}_verified_schedule_{timestamp_str}.csv"
        return csv_bytes, "text/csv; charset=utf-8", filename

    def _build_xlsx(
        self,
        rows: list[dict[str, Any]],
        excluded_rows: list[dict[str, Any]],
        project_name: str,
        timestamp_str: str,
    ) -> tuple[bytes, str, str]:
        wb = Workbook()
        ws_verified = wb.active
        ws_verified.title = "Verified Schedule"

        headers = [
            "Activity ID",
            "Activity Name",
            "WBS",
            "Discipline",
            "Location",
            "Level",
            "Planned Start",
            "Planned Finish",
            "Actual Start",
            "Actual End",
            "% Complete",
            "Status",
            "Export Status",
            "Verification Source",
            "Source Evidence",
            "Audit Timestamp",
        ]

        row_keys = [
            "activity_id",
            "activity_name",
            "wbs",
            "discipline",
            "location",
            "level",
            "planned_start",
            "planned_finish",
            "actual_start",
            "actual_end",
            "percent_complete",
            "status",
            "export_status",
            "verification_source",
            "source_evidence",
            "audit_timestamp",
        ]

        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        border_thin = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )
        align_left = Alignment(horizontal="left", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")

        ws_verified.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws_verified.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = align_center

        for row_data in rows:
            row_vals = [row_data.get(k, "") for k in row_keys]
            ws_verified.append(row_vals)
            curr_row = ws_verified.max_row
            is_verified = row_data.get("export_status") == "VERIFIED_UPDATE"
            is_excluded = "EXCLUDED" in str(row_data.get("export_status", ""))

            for col_idx in range(1, len(headers) + 1):
                cell = ws_verified.cell(row=curr_row, column=col_idx)
                cell.border = border_thin
                cell.alignment = align_left if col_idx in {1, 2, 4, 5, 14, 15} else align_center
                if is_verified:
                    cell.fill = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid")
                elif is_excluded:
                    cell.fill = PatternFill(start_color="FFF1F2", end_color="FFF1F2", fill_type="solid")

        # Auto-adjust column widths
        for col in ws_verified.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws_verified.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # Sheet 2: Review & Conflicts Audit
        ws_audit = wb.create_sheet(title="Review & Conflicts Audit")
        audit_headers = [
            "Activity ID",
            "Activity Name",
            "Safety Gate Status",
            "Reason / Violation",
            "Withheld Actual Start",
            "Withheld Actual End",
            "Withheld Progress",
            "Withheld Status",
            "Reconciliation Confidence",
        ]
        audit_keys = [
            "activity_id",
            "activity_name",
            "state",
            "reason",
            "proposed_actual_start",
            "proposed_actual_end",
            "proposed_progress",
            "proposed_status",
            "confidence",
        ]
        ws_audit.append(audit_headers)
        audit_header_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
        for col_idx in range(1, len(audit_headers) + 1):
            cell = ws_audit.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = audit_header_fill
            cell.alignment = align_center

        for row_data in excluded_rows:
            ws_audit.append([row_data.get(k, "") for k in audit_keys])
            curr_row = ws_audit.max_row
            for col_idx in range(1, len(audit_headers) + 1):
                cell = ws_audit.cell(row=curr_row, column=col_idx)
                cell.border = border_thin
                cell.alignment = align_left if col_idx in {1, 2, 4} else align_center

        for col in ws_audit.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = col[0].column_letter
            ws_audit.column_dimensions[col_letter].width = max(max_len + 3, 14)

        output = io.BytesIO()
        wb.save(output)
        xlsx_bytes = output.getvalue()
        filename = f"{project_name}_verified_schedule_{timestamp_str}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return xlsx_bytes, media_type, filename
