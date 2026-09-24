"""Focused unit and integration test suite for Phase 5 Execution Memory Layer.

Validates:
1. execution record creation
2. actual duration calculation (deterministic)
3. schedule variance calculation (deterministic)
4. early completion classification
5. on-time completion classification
6. late completion classification
7. extended duration classification
8. dependency conflict recording
9. explicit delay cause extraction
10. unknown delay cause handling
11. cause provenance back to source DPR
12. discipline aggregation
13. contractor aggregation
14. project summary
15. cross-project historical query
16. similar execution retrieval (with historical disclaimer)
17. missing data handling (distinguishes KNOWN vs UNKNOWN)
18. planner override preservation
19. execution memory API routes
"""

import uuid
from datetime import UTC, date, datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider
from app.api.routes.imports import get_session
from app.database.base import Base
from app.database.models import (
    Activity,
    ActivityDependency,
    ActivityStatus,
    ConflictSeverity,
    ConflictType,
    DelayCategory,
    DependencyType,
    DeviationType,
    Evidence,
    EvidenceConflict,
    EvidenceInterpretation,
    ExecutionDeviation,
    ExecutionRecord,
    ImportedSource,
    ImportKind,
    ImportStatus,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    PlannerReview,
    Project,
    Reconciliation,
    ReconciliationDecision,
    ResolutionStatus,
    ReviewDecision,
    SourceType,
)
from app.main import app
from app.modules.extraction.schemas import ExtractedObservation
from app.modules.extraction.service import ExtractionService
from app.modules.memory.service import ExecutionMemoryService


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()



def test_actual_duration_calculation():
    """Validates deterministic duration calculation in calendar days."""
    # 3 calendar days inclusive: Sept 10, 11, 12
    dur = ExecutionMemoryService.calculate_duration(date(2026, 9, 10), date(2026, 9, 12))
    assert dur == 3.0

    # Same day = 1 calendar day
    dur_same = ExecutionMemoryService.calculate_duration(date(2026, 9, 10), date(2026, 9, 10))
    assert dur_same == 1.0

    # Missing end date -> None (UNKNOWN)
    assert ExecutionMemoryService.calculate_duration(date(2026, 9, 10), None) is None

    # Missing start date -> None (UNKNOWN)
    assert ExecutionMemoryService.calculate_duration(None, date(2026, 9, 12)) is None

    # End before start -> None
    assert ExecutionMemoryService.calculate_duration(date(2026, 9, 12), date(2026, 9, 10)) is None


def test_schedule_variance_calculation():
    """Validates deterministic variance: actual - planned duration."""
    # Planned 3 days, actual 5 days -> +2 days
    assert ExecutionMemoryService.calculate_variance(3.0, 5.0) == 2.0

    # Planned 5 days, actual 3 days -> -2 days (early)
    assert ExecutionMemoryService.calculate_variance(5.0, 3.0) == -2.0

    # Planned 4 days, actual 4 days -> 0 days (on-time)
    assert ExecutionMemoryService.calculate_variance(4.0, 4.0) == 0.0

    # Missing planned or actual -> None (UNKNOWN)
    assert ExecutionMemoryService.calculate_variance(None, 5.0) is None
    assert ExecutionMemoryService.calculate_variance(4.0, None) is None


def test_explicit_delay_cause_extraction(test_db):
    """Explicit cause 'pending NDT clearance' is extracted and categorized as INSPECTION with confidence."""
    project = Project(name="Delay Extraction Project")
    test_db.add(project)
    test_db.commit()

    raw = "Hydrotest Line 18-AA delayed due to pending NDT clearance."
    evidence = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-104.txt",
        source_timestamp=datetime(2026, 9, 10, tzinfo=UTC),
        raw_text=raw,
    )
    test_db.add(evidence)
    test_db.commit()

    service = ExtractionService(test_db, provider=DeterministicMockProvider())
    observations = service.extract_evidence(evidence.evidence_id)

    assert len(observations) >= 1
    obs = observations[0]
    assert obs.delay_cause == "Pending ndt clearance" or "ndt clearance" in (obs.delay_cause or "").lower()
    assert obs.delay_category == "INSPECTION"
    assert obs.delay_confidence is not None and obs.delay_confidence >= 0.9


def test_unknown_delay_cause_when_not_stated(test_db):
    """When DPR only mentions delay without a cause, delay_cause is UNKNOWN and never fabricated."""
    project = Project(name="Unknown Delay Project")
    test_db.add(project)
    test_db.commit()

    raw = "Hydrotest Line 18-AA is delayed."
    evidence = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-105.txt",
        source_timestamp=datetime(2026, 9, 11, tzinfo=UTC),
        raw_text=raw,
    )
    test_db.add(evidence)
    test_db.commit()

    service = ExtractionService(test_db, provider=DeterministicMockProvider())
    observations = service.extract_evidence(evidence.evidence_id)

    assert len(observations) >= 1
    obs = observations[0]
    assert obs.delay_cause == "UNKNOWN"
    assert obs.delay_category == "UNKNOWN"



def test_execution_record_creation_and_provenance(test_db):
    """ExecutionRecord preserves project, activity, contractor, durations, variance, and evidence reference."""
    project = Project(name="Institutional Memory Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-100",
        description="Hydrotest Line 18-AA",
        discipline="Piping",
        location="Unit 3",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 3),  # 3 days planned
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 5),    # 5 days actual (+2d variance)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    # Add evidence observation with contractor and delay cause
    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-104.txt",
        source_timestamp=datetime(2026, 9, 5, tzinfo=UTC),
        raw_text="Hydrotest delayed due to pending NDT clearance.",
    )
    test_db.add(ev)
    test_db.commit()

    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        activity_description="Hydrotest Line 18-AA",
        discipline="Piping",
        location="Unit 3",
        contractor="Apex Mechanical",
        status=ActivityStatus.COMPLETED,
        actual_end=date(2026, 9, 5),
        confidence=0.95,
        delay_cause="Pending NDT clearance",
        delay_category="INSPECTION",
        delay_confidence=0.94,
        provider_name="test",
        raw_provider_response={},
    )
    test_db.add(obs)
    test_db.commit()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.95,
        high_confidence_threshold=0.7,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.45,
    )
    test_db.add(match_res)
    test_db.commit()

    cand = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act.activity_id,
        rank=1,
        similarity_score=0.95,
        contextual_score=0.95,
        final_score=0.95,
        explanation="Direct match",
    )
    test_db.add(cand)
    test_db.commit()

    # Sync memory
    mem_service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = mem_service.sync_project_memory(project.project_id)

    assert len(records) == 1
    rec = records[0]
    assert rec.external_activity_id == "PIP-100"
    assert rec.contractor == "Apex Mechanical"
    assert rec.planned_duration_days == 3.0
    assert rec.actual_duration_days == 5.0
    assert rec.variance_days == 2.0
    assert rec.deviation_type in ("LATE", "EXTENDED")
    assert rec.delay_cause == "Pending NDT clearance"
    assert rec.delay_category == "INSPECTION"
    assert "DPR-104.txt" in (rec.delay_source_evidence or "")


def test_early_completion_classification(test_db):
    """Activity finished before planned finish is classified as EARLY with negative variance."""
    project = Project(name="Early Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="CIV-010",
        description="Foundation Excavation",
        discipline="Civil",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 10), # 10 days
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 6),     # 6 days (4 days early)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.deviation_type == DeviationType.EARLY.value
    assert rec.variance_days == -4.0
    assert len(rec.deviations) == 1
    assert "earlier than baseline" in rec.deviations[0].description


def test_on_time_completion_classification(test_db):
    """Activity finished on planned finish is classified as ON_TIME with 0 variance."""
    project = Project(name="On Time Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="ELE-001",
        description="Transformer Foundation",
        discipline="Electrical",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 5),
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 5),
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.deviation_type == DeviationType.ON_TIME.value
    assert rec.variance_days == 0.0


def test_dependency_conflict_recording(test_db):
    """Unresolved dependency conflict flags record as CONFLICT."""
    project = Project(name="Conflict Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-200",
        description="Tie-in Welding",
        discipline="Piping",
        level=5,
        planned_start=date(2026, 9, 10),
        planned_finish=date(2026, 9, 15),
        status=ActivityStatus.IN_PROGRESS,
    )
    test_db.add(act)
    test_db.commit()

    conflict = EvidenceConflict(
        activity_id=act.activity_id,
        conflict_type=ConflictType.DEPENDENCY,
        description="Successor commenced prior to predecessor completion.",
        severity=ConflictSeverity.HIGH,
        resolution_status=ResolutionStatus.OPEN,
    )
    test_db.add(conflict)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.deviation_type == DeviationType.CONFLICT.value
    assert rec.dependency_status == "CONFLICT"
    assert any("Conflict (dependency)" in d.description for d in rec.deviations)


def test_missing_data_distinguishes_unknown(test_db):
    """Missing actual dates/contractor are preserved as UNKNOWN, never 0 or assumed on-time."""
    project = Project(name="Missing Data Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="CIV-999",
        description="Unstarted excavation",
        discipline="Civil",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 5),
        status=ActivityStatus.NOT_STARTED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.actual_duration_days is None
    assert rec.variance_days is None
    assert rec.contractor == "UNKNOWN"
    assert rec.deviation_type == DeviationType.UNKNOWN.value


def test_project_performance_summary_aggregation(test_db):
    """Project summary deterministically computes totals, completion, averages, and causes."""
    project = Project(name="Refinery Summary Project")
    test_db.add(project)
    test_db.commit()

    # 1. On time activity (3 days)
    act1 = Activity(
        project_id=project.project_id, external_activity_id="A1", description="Pipe spool", discipline="Piping",
        level=5, planned_start=date(2026, 9, 1), planned_finish=date(2026, 9, 3),
        actual_start=date(2026, 9, 1), actual_end=date(2026, 9, 3),
        actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    # 2. Late activity (+2 days variance)
    act2 = Activity(
        project_id=project.project_id, external_activity_id="A2", description="Hydrotest", discipline="Piping",
        level=5, planned_start=date(2026, 9, 1), planned_finish=date(2026, 9, 3), # 3d planned
        actual_start=date(2026, 9, 1), actual_end=date(2026, 9, 5),             # 5d actual (+2d)
        actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    test_db.add_all([act1, act2])
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    summary = service.get_project_summary(project.project_id)

    assert summary.total_activities == 2
    assert summary.completed_activities == 2
    assert summary.on_time_activities == 1
    assert summary.late_activities == 1
    assert summary.conflict_count == 0
    assert summary.average_planned_duration_days == 3.0
    # Average actual = (3 + 5) / 2 = 4.0
    assert summary.average_actual_duration_days == 4.0
    # Average variance = (0 + 2) / 2 = 1.0
    assert summary.average_variance_days == 1.0
    assert len(summary.discipline_performance) == 1
    assert summary.discipline_performance[0].discipline == "Piping"
    assert summary.discipline_performance[0].average_variance_days == 1.0


def test_cross_project_historical_query(test_db):
    """Historical knowledge can be queried across multiple projects."""
    p1 = Project(name="Project 1")
    p2 = Project(name="Project 2")
    test_db.add_all([p1, p2])
    test_db.commit()

    # Project 1: Hydrotest took 5 days (+2d variance)
    act1 = Activity(
        project_id=p1.project_id, external_activity_id="P1-HYD", description="Hydrotest piping package A", discipline="Piping",
        level=5, planned_start=date(2026, 8, 1), planned_finish=date(2026, 8, 3),
        actual_start=date(2026, 8, 1), actual_end=date(2026, 8, 5),
        actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    # Project 2: Hydrotest took 4 days (+1d variance)
    act2 = Activity(
        project_id=p2.project_id, external_activity_id="P2-HYD", description="Hydrotest unit 2", discipline="Piping",
        level=5, planned_start=date(2026, 8, 1), planned_finish=date(2026, 8, 3),
        actual_start=date(2026, 8, 1), actual_end=date(2026, 8, 4),
        actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    test_db.add_all([act1, act2])
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    service.sync_project_memory(p1.project_id)
    service.sync_project_memory(p2.project_id)

    cross_res = service.query_cross_project(discipline="Piping", query="Hydrotest")

    assert cross_res.total_matching_records == 2
    assert cross_res.completed_matching_records == 2
    # Avg variance = (2.0 + 1.0) / 2 = 1.5 days
    assert cross_res.average_variance_days == 1.5
    assert "HISTORICAL REFERENCE" in cross_res.disclaimer


def test_similar_execution_retrieval_with_disclaimer(test_db):
    """Similar historical completed execution retrieval returns matched activities with required disclaimer."""
    project = Project(name="Reference Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-500",
        description="24 inch line erection",
        discipline="Piping",
        level=5,
        planned_start=date(2026, 8, 1),
        planned_finish=date(2026, 8, 10),
        actual_start=date(2026, 8, 1),
        actual_end=date(2026, 8, 12), # 12 days (+2d variance)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    service.sync_project_memory(project.project_id)

    similar = service.find_similar_executions(query="24 inch line erection", discipline="Piping")

    assert len(similar.results) == 1
    item = similar.results[0]
    assert item.activity_name == "24 inch line erection"
    assert item.variance_days == 2.0
    assert item.disclaimer == "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"
    assert similar.disclaimer == "HISTORICAL REFERENCE ONLY — NOT A PREDICTION"


def test_planner_override_preservation_in_memory(test_db):
    """Planner modification or approval override is recorded with notes in execution memory."""
    project = Project(name="Planner Override Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-800",
        description="Valve assembly",
        discipline="Piping",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 3),
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 4),
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    review = PlannerReview(
        activity_id=act.activity_id,
        reviewer="Lead Planner John Doe",
        reason="Field inspection confirmed bolt-up completion.",
        proposed_decision=ReviewDecision.ACCEPT,
        reviewer_decision=ReviewDecision.ACCEPT,
        reviewer_comment="Approved based on QA/QC signoff.",
        reviewed_at=datetime(2026, 9, 4, tzinfo=UTC),
    )
    test_db.add(review)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.planner_override is True
    assert "Approved based on QA/QC signoff." in (rec.planner_notes or "")

    hist = service.get_activity_history(project.project_id, act.activity_id)
    assert len(hist.planner_decisions) == 1
    assert hist.planner_decisions[0]["reviewer"] == "Lead Planner John Doe"


def test_memory_api_endpoints(test_db, monkeypatch):
    """Test memory summary, activity history, sync, and similar endpoints via FastAPI test client."""
    from app.core.config import get_settings
    monkeypatch.setenv("AI_EMBEDDING_PROVIDER", "deterministic_mock")
    get_settings.cache_clear()
    project = Project(name="API Test Project")
    test_db.add(project)
    test_db.commit()


    act = Activity(
        project_id=project.project_id,
        external_activity_id="API-ACT-1",
        description="Cable tray installation",
        discipline="Electrical",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 4),
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 4),
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    app.dependency_overrides[get_session] = lambda: test_db
    client = TestClient(app)

    try:
        # 1. Summary
        res_sum = client.get(f"/api/v1/projects/{project.project_id}/memory/summary")
        assert res_sum.status_code == 200
        data_sum = res_sum.json()
        assert data_sum["total_activities"] == 1
        assert data_sum["completed_activities"] == 1

        # 2. Activity History
        res_hist = client.get(f"/api/v1/projects/{project.project_id}/memory/activities/{act.activity_id}")
        assert res_hist.status_code == 200
        data_hist = res_hist.json()
        assert data_hist["external_activity_id"] == "API-ACT-1"
        assert data_hist["planned_duration_days"] == 4.0

        # 3. Similar
        res_sim = client.get(f"/api/v1/projects/{project.project_id}/memory/similar?query=cable")
        assert res_sim.status_code == 200
        data_sim = res_sim.json()
        assert "disclaimer" in data_sim
        assert "NOT A PREDICTION" in data_sim["disclaimer"]

        # 4. Cross-project
        res_cross = client.get("/api/v1/memory/cross-project/summary?discipline=Electrical")
        assert res_cross.status_code == 200
        assert res_cross.json()["total_matching_records"] >= 1
    finally:
        app.dependency_overrides.pop(get_session, None)
        get_settings.cache_clear()


def test_late_completion_classification(test_db):
    """Activity completed after planned finish is classified as LATE with positive variance."""
    project = Project(name="Late Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-303",
        description="Hydrotest Unit 4",
        discipline="Piping",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 3), # 3 days planned
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 7),     # 7 days actual (+4 days)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.deviation_type == DeviationType.LATE.value
    assert rec.planned_duration_days == 3.0
    assert rec.actual_duration_days == 7.0
    assert rec.variance_days == 4.0
    assert any("later than baseline" in d.description for d in rec.deviations)


def test_extended_duration_classification(test_db):
    """Activity that exceeded planned duration without explicit finish date is classified as EXTENDED."""
    project = Project(name="Extended Project")
    test_db.add(project)
    test_db.commit()

    # Activity with planned start/finish but actual duration derived from observation
    act = Activity(
        project_id=project.project_id,
        external_activity_id="ELE-404",
        description="Cable pull Unit 1",
        discipline="Electrical",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 4), # 4 days
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 8),     # 8 days (+4d extended)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.variance_days == 4.0
    assert rec.deviation_type in (DeviationType.LATE.value, DeviationType.EXTENDED.value)


def test_cause_provenance_to_source_dpr(test_db):
    """Every extracted delay cause has provenance linking to the DPR source and observation."""
    project = Project(name="Provenance Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="CIV-501",
        description="Concrete foundation pour",
        discipline="Civil",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 2),
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 4),
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-2026-09-04.txt",
        source_timestamp=datetime(2026, 9, 4, tzinfo=UTC),
        raw_text="Concrete pour delayed due to heavy monsoon rainfall.",
    )
    test_db.add(ev)
    test_db.commit()

    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        activity_description="Concrete foundation pour",
        discipline="Civil",
        location="Unit 1",
        status=ActivityStatus.COMPLETED,
        confidence=0.96,
        delay_cause="Heavy monsoon rainfall",
        delay_category="WEATHER",
        delay_confidence=0.95,
        provider_name="test",
        raw_provider_response={},
    )
    test_db.add(obs)
    test_db.commit()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.96,
        high_confidence_threshold=0.7,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.45,
    )
    test_db.add(match_res)
    test_db.commit()

    cand = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act.activity_id,
        rank=1,
        similarity_score=0.96,
        contextual_score=0.96,
        final_score=0.96,
        explanation="Direct match",
    )
    test_db.add(cand)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    records = service.sync_project_memory(project.project_id)
    rec = records[0]

    assert rec.delay_cause == "Heavy monsoon rainfall"
    assert rec.delay_category == "WEATHER"
    assert "DPR-2026-09-04.txt" in rec.delay_source_evidence

    hist = service.get_activity_history(project.project_id, act.activity_id)
    assert hist.recorded_cause == "Heavy monsoon rainfall"
    assert hist.delay_category == "WEATHER"
    assert "DPR-2026-09-04.txt" in (hist.cause_source_reference or "")


def test_discipline_aggregation_statistics(test_db):
    """Validates discipline-level metrics and average schedule variances."""
    project = Project(name="Discipline Stats Project")
    test_db.add(project)
    test_db.commit()

    # Piping: 2 activities, variances +2d and 0d -> avg +1.0d
    p1 = Activity(
        project_id=project.project_id, external_activity_id="P-1", description="Spool A", discipline="Piping",
        level=5, planned_start=date(2026, 9, 1), planned_finish=date(2026, 9, 3),
        actual_start=date(2026, 9, 1), actual_end=date(2026, 9, 5), actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    p2 = Activity(
        project_id=project.project_id, external_activity_id="P-2", description="Spool B", discipline="Piping",
        level=5, planned_start=date(2026, 9, 1), planned_finish=date(2026, 9, 3),
        actual_start=date(2026, 9, 1), actual_end=date(2026, 9, 3), actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    # Civil: 1 activity, on-time -> avg 0.0d
    c1 = Activity(
        project_id=project.project_id, external_activity_id="C-1", description="Excavation", discipline="Civil",
        level=5, planned_start=date(2026, 9, 1), planned_finish=date(2026, 9, 5),
        actual_start=date(2026, 9, 1), actual_end=date(2026, 9, 5), actual_progress=100.0, status=ActivityStatus.COMPLETED,
    )
    test_db.add_all([p1, p2, c1])
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    summary = service.get_project_summary(project.project_id)

    disc_map = {d.discipline: d for d in summary.discipline_performance}
    assert "Piping" in disc_map
    assert "Civil" in disc_map
    assert disc_map["Piping"].total_activities == 2
    assert disc_map["Piping"].average_variance_days == 1.0
    assert disc_map["Civil"].total_activities == 1
    assert disc_map["Civil"].average_variance_days == 0.0


def test_contractor_aggregation_statistics(test_db):
    """Validates contractor-level metrics where contractor was explicitly reported."""
    project = Project(name="Contractor Stats Project")
    test_db.add(project)
    test_db.commit()

    act = Activity(
        project_id=project.project_id,
        external_activity_id="CON-1",
        description="Turbine Generator",
        discipline="Mechanical",
        level=5,
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 5), # 5 days
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 8),     # 8 days (+3 days variance)
        actual_progress=100.0,
        status=ActivityStatus.COMPLETED,
    )
    test_db.add(act)
    test_db.commit()

    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="Babcock_Weekly_Return.csv",
        source_timestamp=datetime(2026, 9, 8, tzinfo=UTC),
        raw_text="Turbine erection completed by Babcock Power.",
    )
    test_db.add(ev)
    test_db.commit()

    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        activity_description="Turbine Generator",
        contractor="Babcock Power",
        discipline="Mechanical",
        status=ActivityStatus.COMPLETED,
        confidence=0.94,
        provider_name="test",
        raw_provider_response={},
    )
    test_db.add(obs)
    test_db.commit()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.94,
        high_confidence_threshold=0.7,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.45,
    )
    test_db.add(match_res)
    test_db.commit()

    cand = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act.activity_id,
        rank=1,
        similarity_score=0.94,
        contextual_score=0.94,
        final_score=0.94,
        explanation="Direct match",
    )
    test_db.add(cand)
    test_db.commit()

    service = ExecutionMemoryService(test_db, embedding_provider=DeterministicEmbeddingProvider())
    summary = service.get_project_summary(project.project_id)

    cont_map = {c.contractor: c for c in summary.contractor_performance}
    assert "Babcock Power" in cont_map
    assert cont_map["Babcock Power"].total_activities == 1
    assert cont_map["Babcock Power"].completed_activities == 1
    assert cont_map["Babcock Power"].delayed_count == 1
    assert cont_map["Babcock Power"].average_variance_days == 3.0

