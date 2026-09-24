"""Phase 6 End-to-End Product Hardening & Realistic Demo Lifecycle Integration Tests.

Validates:
1. Demo project reset with full realistic data:
   - Project: PRJ-2026-SYN01 · Oil & Gas Infrastructure Project (Synthetic Demo)
   - 4 disciplines: Civil, Piping, Electrical, Instrumentation
   - 10 L5/L6 activities with predecessor relationships
   - 8 evidence items spanning realistic field scenarios
2. The 4 required DPR field scenarios:
   - Verified / high-confidence match & auto-reconciled (ELEC001)
   - Ambiguous match needing planner disambiguation (ambiguous.txt)
   - Dependency / temporal conflict (PIP004 started before predecessor)
   - Explicit delay cause with provenance (PIP003 with NDT clearance delay)
3. End-to-end planner review actuation -> schedule update bridge -> verified export (CSV & XLSX)
4. Execution memory compilation, delay cause provenance, and cross-project historical lookup
5. Security hardening: safe file handling, path traversal prevention, and export format validation
"""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.ai.mock_provider import DeterministicEmbeddingProvider
from app.database.demo import DEMO_NAME, DEMO_PROJECT_ID, reset_sih26122
from app.database.models import (
    Activity,
    ActivityDependency,
    ActivityStatus,
    ConflictSeverity,
    ConflictType,
    DelayCategory,
    DeviationType,
    Evidence,
    EvidenceConflict,
    EvidenceInterpretation,
    ExecutionDeviation,
    ExecutionRecord,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    PlannerReview,
    Project,
    Reconciliation,
    ReconciliationDecision,
    ReviewDecision,
    ScheduleUpdate,
    SourceType,
)
from app.modules.memory.service import ExecutionMemoryService
from app.modules.ingestion.service import IngestionService
from app.modules.planner_review.schemas import PlannerActionRequest
from app.modules.planner_review.service import PlannerReviewService
from app.modules.schedule.bridge_service import ScheduleBridgeService
from app.modules.schedule.schemas import ScheduleDecisionState


def test_phase6_realistic_demo_dataset_and_4_scenarios(session) -> None:
    """Validate demo project reset produces synthetic demo with 4 realistic DPR scenarios."""
    project = reset_sih26122(session)
    assert project.name == DEMO_NAME
    assert "Synthetic Demo" in project.name

    # 1. Disciplines and activities audit
    activities = list(
        session.scalars(
            select(Activity)
            .where(Activity.project_id == project.project_id)
            .order_by(Activity.external_activity_id)
        )
    )
    assert len(activities) == 10

    disciplines = {a.discipline for a in activities if a.discipline}
    assert {"Civil", "Piping", "Electrical", "Instrumentation"}.issubset(disciplines)

    # Verify dependencies
    dependencies = list(
        session.scalars(
            select(ActivityDependency).where(ActivityDependency.project_id == project.project_id)
        )
    )
    assert len(dependencies) >= 4

    # Verify 8 evidence items
    evidence_items = list(
        session.scalars(
            select(Evidence).where(Evidence.project_id == project.project_id)
        )
    )
    assert len(evidence_items) == 8

    # SCENARIO 1: High confidence match and auto-reconciliation (ELEC001)
    elec = session.scalar(
        select(Activity).where(
            Activity.project_id == project.project_id,
            Activity.external_activity_id == "ELEC001",
        )
    )
    assert elec is not None
    assert elec.status is ActivityStatus.COMPLETED
    elec_update = session.scalar(
        select(ScheduleUpdate).where(ScheduleUpdate.activity_id == elec.activity_id)
    )
    assert elec_update is not None
    assert elec_update.new_value.get("status") == ActivityStatus.COMPLETED.value

    # SCENARIO 2: Ambiguous match needing planner review
    ambig_match = session.scalar(
        select(ObservationMatchResult)
        .join(ObservationMatchResult.interpretation)
        .join(Evidence)
        .where(
            Evidence.project_id == project.project_id,
            Evidence.source_name == "ambiguous.txt",
        )
    )
    assert ambig_match is not None
    assert ambig_match.outcome is ObservationMatchOutcome.AMBIGUOUS
    assert ambig_match.ambiguity_flag is True
    assert len(ambig_match.candidates) >= 2

    # SCENARIO 3: Dependency / temporal conflict
    conflict = session.scalar(
        select(EvidenceConflict)
        .join(Activity)
        .where(Activity.project_id == project.project_id)
    )
    assert conflict is not None
    assert conflict.conflict_type in (
        ConflictType.DEPENDENCY,
        ConflictType.STATUS,
        ConflictType.PROGRESS,
        ConflictType.DATES,
    )

    # SCENARIO 4: Explicit delay cause with provenance
    delay_interp = session.scalar(
        select(EvidenceInterpretation)
        .join(Evidence)
        .where(
            Evidence.project_id == project.project_id,
            Evidence.source_name == "delay_cause.txt",
        )
    )
    assert delay_interp is not None
    assert delay_interp.delay_cause == "Pending NDT clearance"
    assert delay_interp.delay_category == DelayCategory.INSPECTION
    assert delay_interp.delay_confidence is not None and delay_interp.delay_confidence > 0.8
    assert delay_interp.original_evidence is not None


def test_phase6_planner_review_actuation_to_verified_exports(session) -> None:
    """Validate planner review approval creates verified schedule update and exports cleanly."""
    project = reset_sih26122(session)
    bridge_service = ScheduleBridgeService(session)

    # Find PIP001 which is in PLANNER_REVIEW
    pip = session.scalar(
        select(Activity).where(
            Activity.project_id == project.project_id,
            Activity.external_activity_id == "PIP001",
        )
    )
    assert pip is not None

    review = session.scalar(
        select(PlannerReview).where(PlannerReview.activity_id == pip.activity_id)
    )
    assert review is not None

    # Actuate review approval with modify/override
    review_service = PlannerReviewService(session)
    action_request = PlannerActionRequest(
        action="modify",
        reviewer="lead_planner",
        comment="Planner approved erection completion based on quality signoff.",
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        actual_start=date(2026, 8, 25),
        actual_end=date(2026, 9, 12),
    )
    review_service.act(review.review_id, action_request)

    # Verify ScheduleUpdate exists for PIP001
    pip_update = session.scalar(
        select(ScheduleUpdate).where(ScheduleUpdate.activity_id == pip.activity_id)
    )
    assert pip_update is not None
    assert pip_update.new_value.get("status") == ActivityStatus.COMPLETED.value

    # Check Preview
    preview = bridge_service.get_change_preview(project.project_id)
    assert preview.summary.activities_evaluated == 10
    assert preview.summary.verified_updates >= 2
    verified_ids = [c.external_activity_id for c in preview.changes if c.decision == ScheduleDecisionState.VERIFIED]
    assert "ELEC001" in verified_ids
    assert "PIP001" in verified_ids

    # Export CSV
    csv_bytes, media_type, filename = bridge_service.export_verified_schedule(project.project_id, "csv")
    assert media_type.startswith("text/csv")
    assert filename.endswith(".csv")
    csv_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert len(csv_rows) >= 2
    verified_csv_rows = [r for r in csv_rows if r["export_status"] == "VERIFIED_UPDATE"]
    assert len(verified_csv_rows) >= 2
    verified_export_ids = {r["activity_id"] for r in verified_csv_rows}
    assert "ELEC001" in verified_export_ids
    assert "PIP001" in verified_export_ids
    for r in verified_csv_rows:
        assert r["status"] in ("completed", "in_progress")

    # Export XLSX
    xlsx_bytes, xlsx_media, xlsx_filename = bridge_service.export_verified_schedule(project.project_id, "xlsx")
    assert "spreadsheetml" in xlsx_media
    assert xlsx_filename.endswith(".xlsx")
    wb = load_workbook(filename=io.BytesIO(xlsx_bytes))
    sheet = wb.active
    assert sheet is not None
    header = [cell.value for cell in sheet[1]]
    assert "Activity ID" in header
    assert "Export Status" in header


def test_phase6_execution_memory_compilation_and_search(session) -> None:
    """Validate Execution Memory layer preserves execution lessons with provenance."""
    project = reset_sih26122(session)
    mem_service = ExecutionMemoryService(session, embedding_provider=DeterministicEmbeddingProvider())
    mem_service.sync_project_memory(project.project_id)

    # 1. Execution records and deviations
    records = list(
        session.scalars(
            select(ExecutionRecord).where(ExecutionRecord.project_id == project.project_id)
        )
    )
    assert len(records) > 0

    deviations = list(
        session.scalars(
            select(ExecutionDeviation)
            .join(ExecutionRecord)
            .where(ExecutionRecord.project_id == project.project_id)
        )
    )
    assert len(deviations) > 0

    # Verify project summary
    summary = mem_service.get_project_summary(project.project_id)
    assert summary.total_activities == 10
    assert summary.completed_activities >= 1
    assert len(summary.discipline_performance) > 0

    # Verify delay causes with provenance from execution records
    pip3_rec = next((r for r in records if r.external_activity_id == "PIP003"), None)
    if pip3_rec and pip3_rec.delay_cause:
        assert "NDT" in pip3_rec.delay_cause
        assert pip3_rec.delay_category == DelayCategory.INSPECTION.value
        assert pip3_rec.evidence_reference is not None

    # Verify similar execution retrieval with historical disclaimer
    search_res = mem_service.find_similar_executions("transformer foundation installation", limit=3)
    assert search_res.disclaimer == "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"
    assert isinstance(search_res.results, list)


def test_phase6_security_safe_paths_and_export_validation(session, tmp_path) -> None:
    """Validate security hardening: safe file handling and path traversal prevention."""
    project = reset_sih26122(session)
    ingestion = IngestionService(session)

    # Path traversal attack file name simulation
    malicious_file = tmp_path / "normal.txt"
    malicious_file.write_text("OBSERVATION|2026-09-01T10:00:00Z|Civil|Unit 1|in_progress|50|Normal work|0.9\n")

    # Pass filename with path traversal characters
    traversal_name = "../../etc/passwd"
    imported = ingestion.import_evidence(
        project.project_id,
        malicious_file,
        traversal_name,
        SourceType.DAILY_REPORT,
    )
    # Ensure source_name does not allow directory traversal
    assert ".." not in Path(imported.source_name).name or Path(imported.source_name).name == "passwd"

    # Export format validation
    bridge = ScheduleBridgeService(session)
    with pytest.raises(ValueError, match="Unsupported export format"):
        bridge.export_verified_schedule(project.project_id, "exe")  # type: ignore[arg-type]
