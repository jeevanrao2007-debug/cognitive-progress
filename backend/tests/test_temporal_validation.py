"""Tests for CognitiveProgress Phase 2: Schedule-Aware Temporal & Dependency Intelligence."""

import uuid
from datetime import date, datetime, UTC
from pathlib import Path
import pytest
from sqlalchemy import select

from app.database.models import (
    Activity,
    ActivityDependency,
    ActivityStatus,
    AuditEvent,
    DependencyType,
    EvidenceConflict,
    ImportStatus,
    Project,
    ReconciliationDecision,
)
from app.modules.ingestion.service import IngestionService
from app.modules.reconciliation.service import ReconciliationService, WeightedObservation
from app.modules.schedule.temporal_validation import (
    DependencyStatus,
    TemporalValidationEngine,
    TemporalValidationResult,
)


@pytest.fixture
def test_project(session) -> Project:
    proj = Project(name="Phase 2 Schedule Dependency Test Project")
    session.add(proj)
    session.commit()
    return proj


def test_dependency_creation_and_persistence(session, test_project):
    """Test manual creation and relationship navigation of ActivityDependency."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 10),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest Line 24-XX",
        level=6,
        status=ActivityStatus.NOT_STARTED,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=0,
    )
    session.add(dep)
    session.commit()

    reloaded_b = session.get(Activity, act_b.activity_id)
    assert len(reloaded_b.predecessors) == 1
    assert reloaded_b.predecessors[0].predecessor.external_activity_id == "PIP001"

    reloaded_a = session.get(Activity, act_a.activity_id)
    assert len(reloaded_a.successors) == 1
    assert reloaded_a.successors[0].successor.external_activity_id == "HT001"


def test_scenario_1_valid_sequence(session, test_project):
    """Scenario 1: Valid sequence (PIP001 ends 2026-09-10, HT001 starts 2026-09-11 -> VALID)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 10),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 11),
        actual_end=None,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add(dep)
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.VALID
    assert "consistent" in result.reason.lower()


def test_scenario_2_exact_boundary(session, test_project):
    """Scenario 2: Exact boundary (PIP001 ends 2026-09-10, HT001 starts 2026-09-10 -> VALID)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 10),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 10),
        actual_end=None,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add(dep)
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.VALID
    assert "exact boundary" in result.reason.lower()


def test_scenario_3_invalid_sequence_conflict(session, test_project):
    """Scenario 3: Invalid sequence (PIP001 ends 2026-09-14, HT001 starts 2026-09-10 -> CONFLICT)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 14),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 10),
        actual_end=None,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add(dep)
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.CONFLICT
    assert result.rule == "RULE_2_FINISH_TO_START"
    assert "occurs 4 days before predecessor PIP001 actual completion" in result.reason


def test_scenario_4_missing_predecessor_dates_unknown(session, test_project):
    """Scenario 4: Missing dates (PIP001 actual_end=null, HT001 starts 2026-09-10 -> UNKNOWN)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 1),
        actual_end=None,
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 10),
        actual_end=None,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add(dep)
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.UNKNOWN
    assert result.rule == "RULE_4_MISSING_DATES"
    assert "unavailable" in result.reason.lower()


def test_scenario_5_no_dependency_overlap_is_valid(session, test_project):
    """Scenario 5: No dependency (A and B overlap, neither constrained -> VALID)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="CIV001",
        description="Civil foundation",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 20),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Piping installation",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 5),
        actual_end=date(2026, 9, 25),
    )
    session.add_all([act_a, act_b])
    session.commit()

    # Neither activity has explicit dependencies
    res_a = TemporalValidationEngine.validate(act_a)
    res_b = TemporalValidationEngine.validate(act_b)

    assert res_a.dependency_status == DependencyStatus.VALID
    assert res_b.dependency_status == DependencyStatus.VALID
    assert "no dependency constraints" in res_a.reason.lower()


def test_scenario_6_multiple_predecessors(session, test_project):
    """Scenario 6: Multiple predecessors (B depends on A and C. One conflict, one valid -> CONFLICT)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="CIV001",
        description="Foundation",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 5),
    )
    act_c = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Piping",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 15),  # Finishes on the 15th
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 10),  # Starts on 10th (after CIV001, but before PIP001 finishes!)
        actual_end=None,
    )
    session.add_all([act_a, act_c, act_b])
    session.flush()

    dep1 = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    dep2 = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_c.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add_all([dep1, dep2])
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.CONFLICT
    assert len(result.details) == 2
    statuses = {d.predecessor_activity_id: d.status for d in result.details}
    assert statuses["CIV001"] == DependencyStatus.VALID
    assert statuses["PIP001"] == DependencyStatus.CONFLICT


def test_scenario_7_multiple_successors(session, test_project):
    """Scenario 7: Multiple successors (A precedes B and C. Evaluated independently)."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="CIV001",
        description="Foundation",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 10),
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Piping Unit 1",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 12),  # Valid: starts after CIV001 completion
        actual_end=None,
    )
    act_c = Activity(
        project_id=test_project.project_id,
        external_activity_id="ELEC001",
        description="Electrical Substation",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 5),   # Conflict: starts before CIV001 completion
        actual_end=None,
    )
    session.add_all([act_a, act_b, act_c])
    session.flush()

    dep1 = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    dep2 = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_c.activity_id,
    )
    session.add_all([dep1, dep2])
    session.commit()

    res_b = TemporalValidationEngine.validate(act_b)
    res_c = TemporalValidationEngine.validate(act_c)

    assert res_b.dependency_status == DependencyStatus.VALID
    assert res_c.dependency_status == DependencyStatus.CONFLICT


def test_rule_1_date_sanity(session, test_project):
    """Rule 1: Date sanity check (actual_end < actual_start -> CONFLICT)."""
    act = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Erect Line 24-XX",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 15),
        actual_end=date(2026, 9, 10),  # End before start
    )
    session.add(act)
    session.commit()

    result = TemporalValidationEngine.validate(act)
    assert result.dependency_status == DependencyStatus.CONFLICT
    assert result.rule == "RULE_1_DATE_SANITY"
    assert "occurs before actual start" in result.reason


def test_rule_3_completion_dependency_conflict(session, test_project):
    """Rule 3: Successor claimed COMPLETED while predecessor actively IN_PROGRESS (30%) -> CONFLICT."""
    act_a = Activity(
        project_id=test_project.project_id,
        external_activity_id="PIP001",
        description="Piping line erection",
        level=6,
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 1),
        actual_end=None,
        actual_progress=30.0,
    )
    act_b = Activity(
        project_id=test_project.project_id,
        external_activity_id="HT001",
        description="Hydrotest",
        level=6,
        status=ActivityStatus.COMPLETED,
        actual_start=None,
        actual_end=date(2026, 9, 12),
        actual_progress=100.0,
    )
    session.add_all([act_a, act_b])
    session.flush()

    dep = ActivityDependency(
        project_id=test_project.project_id,
        predecessor_id=act_a.activity_id,
        successor_id=act_b.activity_id,
    )
    session.add(dep)
    session.commit()

    result = TemporalValidationEngine.validate(act_b)
    assert result.dependency_status == DependencyStatus.CONFLICT
    assert result.rule == "RULE_3_COMPLETION_DEPENDENCY"
    assert "actively in_progress (30.0% complete)" in result.reason


def test_schedule_import_with_predecessors_csv(session, test_project, tmp_path):
    """Schedule import parses predecessors column and links ActivityDependency."""
    schedule_csv = tmp_path / "schedule_with_preds.csv"
    schedule_csv.write_text(
        "external_activity_id,discipline,description,location,planned_start,planned_finish,parent_activity_id,level,status,predecessors\n"
        "PIP001,Piping,Erect Line 24-XX,Unit 3,2026-08-25,2026-09-20,,6,not_started,\n"
        "HT001,Piping,Hydrotest Line 24-XX,Unit 3,2026-09-21,2026-09-25,,6,not_started,PIP001\n",
        encoding="utf-8",
    )
    service = IngestionService(session)
    source = service.import_schedule(test_project.project_id, schedule_csv, "sched.csv", "v1")

    assert source.status == ImportStatus.COMPLETED
    assert source.records_imported == 2

    ht = session.scalar(
        select(Activity).where(
            Activity.project_id == test_project.project_id,
            Activity.external_activity_id == "HT001",
        )
    )
    assert ht is not None
    assert len(ht.predecessors) == 1
    assert ht.predecessors[0].predecessor.external_activity_id == "PIP001"


def test_schedule_import_without_predecessors_remains_unconstrained(session, test_project, tmp_path):
    """Schedule import without predecessors column imports cleanly and leaves activities unconstrained."""
    schedule_csv = tmp_path / "schedule_no_preds.csv"
    schedule_csv.write_text(
        "external_activity_id,discipline,description,location,planned_start,planned_finish,parent_activity_id,level,status\n"
        "ACT001,Civil,Site clearing,Unit 1,2026-08-01,2026-08-10,,6,not_started\n",
        encoding="utf-8",
    )
    service = IngestionService(session)
    source = service.import_schedule(test_project.project_id, schedule_csv, "sched.csv", "v1")

    assert source.status == ImportStatus.COMPLETED
    act = session.scalar(
        select(Activity).where(
            Activity.project_id == test_project.project_id,
            Activity.external_activity_id == "ACT001",
        )
    )
    assert act is not None
    assert len(act.predecessors) == 0


def test_schedule_import_3_column_representation(session, test_project, tmp_path):
    """Support common representation: Activity ID | Activity Name | Predecessors."""
    csv_file = tmp_path / "three_column_schedule.csv"
    csv_file.write_text(
        "activity_id,activity_name,predecessors\n"
        "PIP001,Erect Line 24-XX,\n"
        "HT001,Hydrotest,PIP001\n",
        encoding="utf-8",
    )
    service = IngestionService(session)
    source = service.import_schedule(test_project.project_id, csv_file, "simple.csv", "v1")

    assert source.status == ImportStatus.COMPLETED
    assert source.records_imported == 2

    ht = session.scalar(
        select(Activity).where(
            Activity.project_id == test_project.project_id,
            Activity.external_activity_id == "HT001",
        )
    )
    assert ht is not None
    assert len(ht.predecessors) == 1
    assert ht.predecessors[0].predecessor.external_activity_id == "PIP001"


def test_safety_gate_blocks_auto_accept_on_dependency_conflict(session, test_project, tmp_path):
    """Hard dependency conflict strictly blocks AUTO_ACCEPT and routes to PLANNER_REVIEW."""
    import json
    from app.ai.mock_provider import DeterministicEmbeddingProvider
    from app.modules.extraction.service import ExtractionService
    from app.modules.matching.service import MatchingService
    from app.modules.normalization.service import NormalizationService
    from app.database.models import SourceType

    class MockHTProvider:
        provider_name = "test_provider"
        model_name = "test-v1"

        def extract_progress(self, prompt: str) -> str:
            return json.dumps({
                "observations": [{
                    "discipline": "Piping",
                    "location": "Unit 3",
                    "activity_description": "Hydrotest Line 24-XX",
                    "status": "in_progress",
                    "actual_start": "2026-09-10",
                    "actual_end": None,
                    "progress": 40.0,
                    "additional_context": "Hydrotest Line 24-XX commenced",
                    "confidence": 0.98,
                }]
            })

        def normalize_activity(self, prompt: str) -> str:
            return json.dumps({
                "normalized_activity_description": "Hydrotest Line 24-XX",
                "normalized_discipline": "Piping",
                "normalized_location": "Unit 3",
                "confidence": 0.98,
            })

        def explain_reconciliation(self, prompt: str) -> str:
            return json.dumps({
                "explanation": "Hydrotest reported active start on 2026-09-10.",
                "confidence": 0.95,
                "recommended_status": "in_progress",
                "recommended_progress": 40.0,
                "recommended_actual_start": "2026-09-10",
            })

    provider = MockHTProvider()
    ingestion = IngestionService(session)

    # 1. Schedule with PIP001 -> HT001
    sched_csv = tmp_path / "conflict_sched.csv"
    sched_csv.write_text(
        "external_activity_id,discipline,description,location,planned_start,planned_finish,parent_activity_id,level,status,predecessors\n"
        "PIP001,Piping,Erect Line 24-XX,Unit 3,2026-08-25,2026-09-20,,6,not_started,\n"
        "HT001,Piping,Hydrotest Line 24-XX,Unit 3,2026-09-21,2026-09-25,,6,not_started,PIP001\n",
        encoding="utf-8",
    )
    ingestion.import_schedule(test_project.project_id, sched_csv, "sched.csv", "v1")

    # Set PIP001 as completed on 2026-09-15
    pip = session.scalar(
        select(Activity).where(
            Activity.project_id == test_project.project_id,
            Activity.external_activity_id == "PIP001",
        )
    )
    pip.status = ActivityStatus.COMPLETED
    pip.actual_start = date(2026, 9, 1)
    pip.actual_end = date(2026, 9, 15)
    pip.actual_progress = 100.0
    session.commit()

    # Evidence for HT001 reporting actual start on 2026-09-10 (before PIP001 completes!)
    evidence_text = (
        "OBSERVATION|2026-09-10T10:00:00Z|Piping|Unit 3|in_progress|40%|Hydrotest Line 24-XX commenced|0.98\n"
    )
    ev_file = tmp_path / "ht_evidence.txt"
    ev_file.write_text(evidence_text, encoding="utf-8")
    ingestion.import_evidence(test_project.project_id, ev_file, "ht.txt", SourceType.DAILY_REPORT)

    # Extract, normalize, match
    from app.database.models import Evidence
    ev = session.scalar(select(Evidence).where(Evidence.project_id == test_project.project_id))
    obs = ExtractionService(session, provider=provider).extract_evidence(ev.evidence_id)
    for o in obs:
        NormalizationService(session, provider=provider).normalize_observation(o.observation_id)
        MatchingService(session, embedding_provider=DeterministicEmbeddingProvider()).match_observation(o.observation_id)

    ht = session.scalar(
        select(Activity).where(
            Activity.project_id == test_project.project_id,
            Activity.external_activity_id == "HT001",
        )
    )

    # Reconcile HT001
    rec_service = ReconciliationService(session, llm_provider=provider)
    response = rec_service.reconcile_activity(ht.activity_id)

    # Verify that AUTO_ACCEPT was BLOCKED and routed to PLANNER_REVIEW
    assert response.decision == ReconciliationDecision.PLANNER_REVIEW
    assert response.dependency_status == "CONFLICT"
    assert len(response.dependency_details) == 1
    assert "occurs 5 days before predecessor PIP001 actual completion" in response.dependency_details[0].reason

    # Verify conflict persisted in EvidenceConflict
    conflicts = list(session.scalars(select(EvidenceConflict).where(EvidenceConflict.activity_id == ht.activity_id)))
    assert len(conflicts) >= 1
    assert any("Schedule dependency violation" in c.description for c in conflicts)

    # Verify Audit Trail recorded dependency details
    audits = list(session.scalars(select(AuditEvent).where(AuditEvent.entity_id == response.reconciliation_id)))
    assert len(audits) >= 1
    dep_audit = audits[0].after_value.get("dependency_validation")
    assert dep_audit is not None
    assert dep_audit["result"] == "CONFLICT"
    assert dep_audit["rule_evaluated"] == "RULE_2_FINISH_TO_START"
    assert dep_audit["details"][0]["predecessor_activity_id"] == "PIP001"
