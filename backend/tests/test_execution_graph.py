"""Tests for Phase 3: Execution Evidence Graph and Field Activity Decomposition."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider
from app.api.routes.imports import get_session
from app.database.models import (
    Activity,
    ActivityDependency,
    ActivityStatus,
    DependencyType,
    Evidence,
    EvidenceInterpretation,
    ObservationMatchCandidate,
    ObservationMatchOutcome,
    ObservationMatchResult,
    Project,
    Reconciliation,
    ReconciliationDecision,
    SourceType,
)
from app.main import app
from app.modules.extraction.service import ExtractionService
from app.modules.graph.service import ExecutionGraphService
from app.modules.matching.service import MatchingService
from app.modules.normalization.service import NormalizationService
from app.modules.reconciliation.service import ReconciliationService


def create_test_project(session) -> Project:
    project = Project(
        name=f"Execution Graph Project {uuid.uuid4().hex[:6]}",
        description="Graph and Decomposition Tests",
    )
    session.add(project)
    session.commit()
    return project


def test_graph_relationship_creation(session):
    """1. Graph relationship creation & Activity -> evidence/events lookup."""
    project = create_test_project(session)

    act_pred = Activity(
        project_id=project.project_id,
        external_activity_id="L6-121",
        description="Predecessor civil work",
        discipline="Civil",
        location="Unit 3",
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 5),
        actual_progress=100.0,
        level=6,
    )
    act_target = Activity(
        project_id=project.project_id,
        external_activity_id="L6-122",
        description="Install piping assembly for Unit 3",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 6),
        actual_end=date(2026, 9, 10),
        actual_progress=100.0,
        level=6,
    )
    act_succ = Activity(
        project_id=project.project_id,
        external_activity_id="L6-123",
        description="Hydrotest line in Unit 3",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=6,
    )
    session.add_all([act_pred, act_target, act_succ])
    session.flush()

    dep1 = ActivityDependency(
        project_id=project.project_id,
        predecessor_id=act_pred.activity_id,
        successor_id=act_target.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=0,
    )
    dep2 = ActivityDependency(
        project_id=project.project_id,
        predecessor_id=act_target.activity_id,
        successor_id=act_succ.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=0,
    )
    session.add_all([dep1, dep2])

    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-104.txt",
        source_timestamp=datetime(2026, 9, 10, 17, 0, tzinfo=UTC),
        raw_text="Piping crew completed valve assembly XV-203 and bolt-up in Unit 3.",
    )
    session.add(ev)
    session.flush()

    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Piping",
        location="Unit 3",
        contractor="Piping crew",
        activity_description="Installed valve XV-203 and completed bolt-up",
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 6),
        actual_end=date(2026, 9, 10),
        progress=100.0,
        confidence=0.95,
        provider_name="test_provider",
        raw_provider_response={},
    )
    session.add(obs)
    session.flush()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.94,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(match_res)
    session.flush()

    candidate = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act_target.activity_id,
        rank=1,
        similarity_score=0.92,
        contextual_score=0.96,
        final_score=0.94,
        explanation="Matched valve bolt-up to piping assembly package.",
    )
    session.add(candidate)

    rec = Reconciliation(
        activity_id=act_target.activity_id,
        reconciled_status=ActivityStatus.COMPLETED,
        reconciled_progress=100.0,
        actual_start=date(2026, 9, 6),
        actual_end=date(2026, 9, 10),
        confidence=0.94,
        explanation="Verified by daily supervisor report DPR-104.",
        decision=ReconciliationDecision.AUTO_ACCEPT,
        supporting_evidence=[{"observation_id": str(obs.observation_id), "source_name": ev.source_name}],
        conflicting_evidence=[],
    )
    session.add(rec)
    session.commit()

    # Query context
    service = ExecutionGraphService(session)
    ctx = service.get_activity_execution_context(project.project_id, act_target.activity_id)

    # Assertions
    assert ctx.activity.external_activity_id == "L6-122"
    assert len(ctx.predecessors) == 1
    assert ctx.predecessors[0].external_activity_id == "L6-121"
    assert len(ctx.successors) == 1
    assert ctx.successors[0].external_activity_id == "L6-123"

    assert len(ctx.execution_events) == 1
    event = ctx.execution_events[0]
    assert event.event_id == obs.observation_id
    assert event.contractor == "Piping crew"
    assert event.discipline == "Piping"
    assert event.location == "Unit 3"
    assert event.is_supporting is True
    assert event.reconciliation_decision == "auto_accept"
    assert event.match_score == 0.94

    # Provenance
    assert len(ctx.provenance) >= 2
    prov_start = next(p for p in ctx.provenance if p.field == "actual_start")
    assert prov_start.value == "2026-09-06"
    assert prov_start.contractor == "Piping crew"
    assert prov_start.source_name == "DPR-104.txt"

    prov_end = next(p for p in ctx.provenance if p.field == "actual_end")
    assert prov_end.value == "2026-09-10"
    assert prov_end.source_name == "DPR-104.txt"

    # Temporal validation
    assert ctx.temporal_validation.is_valid is True
    assert ctx.temporal_validation.status == "VALID"


def test_one_report_produces_multiple_independent_events(session):
    """4. One field report -> multiple distinct execution events with contractor & field description."""
    project = create_test_project(session)

    raw_dpr = (
        "Today the piping team completed erection of Line 24-XX, "
        "installed the associated valve assembly and started hydrotest preparation in Unit 3."
    )
    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR_Daily_Log.txt",
        source_timestamp=datetime(2026, 9, 12, 18, 0, tzinfo=UTC),
        raw_text=raw_dpr,
    )
    session.add(ev)
    session.commit()

    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)
    observations = extractor.extract_evidence(ev.evidence_id)

    # Must extract at least 3 distinct observations from the narrative
    assert len(observations) >= 3
    descriptions = [o.activity_description.lower() for o in observations]
    assert any("erection" in d or "24" in d for d in descriptions)
    assert any("valve" in d or "bolt-up" in d for d in descriptions)
    assert any("hydrotest" in d for d in descriptions)

    # All observations must link to the same evidence but have unique event/observation IDs
    obs_ids = {o.observation_id for o in observations}
    assert len(obs_ids) == len(observations)
    for o in observations:
        assert o.evidence_id == ev.evidence_id
        assert o.discipline == "Piping"
        assert o.contractor is not None or o.location is not None


def test_multiple_events_independent_reconciliation_and_safety_gate(session):
    """
    5. One DPR containing:
    - Event A = valid, high confidence
    - Event B = planner review (ambiguous match)
    - Event C = dependency conflict (safety gate hold)
    Expected: A remains valid, B remains in review, C enters safety gate.
    """
    project = create_test_project(session)

    # Activities:
    # Act A: Independent line erection
    act_a = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-001",
        description="24 inch line erection",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=5,
    )
    # Act B: Valve installation with duplicate candidate
    act_b1 = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-002A",
        description="Install valve assembly train A",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=6,
    )
    act_b2 = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-002B",
        description="Install valve assembly train B",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=6,
    )
    # Act C: Predecessor not completed, but successor claimed completed
    act_c_pred = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-003-PRED",
        description="Predecessor punchlist clearance",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.IN_PROGRESS,  # NOT completed!
        actual_progress=40.0,
        actual_end=date(2026, 9, 20),
        level=6,
    )
    act_c_succ = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-003-SUCC",
        description="Hydrotest preparation",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=6,
    )
    session.add_all([act_a, act_b1, act_b2, act_c_pred, act_c_succ])
    session.flush()

    dep_c = ActivityDependency(
        project_id=project.project_id,
        predecessor_id=act_c_pred.activity_id,
        successor_id=act_c_succ.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=0,
    )
    session.add(dep_c)
    session.flush()

    # Create Evidence (1 DPR)
    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR_Combined.txt",
        source_timestamp=datetime(2026, 9, 12, 17, 0, tzinfo=UTC),
        raw_text="Piping team report",
    )
    session.add(ev)
    session.flush()

    # Event A (High confidence, valid)
    obs_a = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Piping",
        location="Unit 3",
        contractor="Piping crew",
        activity_description="24 inch line erection completed",
        status=ActivityStatus.COMPLETED,
        actual_end=date(2026, 9, 12),
        progress=100.0,
        confidence=0.96,
        provider_name="test",
        raw_provider_response={},
    )
    # Event B (Low confidence -> planner review)
    obs_b = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Piping",
        location="Unit 3",
        contractor="Piping crew",
        activity_description="Installed valve assembly in Unit 3",
        status=ActivityStatus.COMPLETED,
        progress=100.0,
        confidence=0.50,
        provider_name="test",
        raw_provider_response={},
    )
    # Event C (High confidence completion, but predecessor incomplete -> dependency conflict)
    obs_c = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Piping",
        location="Unit 3",
        contractor="Testing crew",
        activity_description="Hydrotest preparation 100% finished",
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 12),
        actual_end=date(2026, 9, 12),
        progress=100.0,
        confidence=0.94,
        provider_name="test",
        raw_provider_response={},
    )
    session.add_all([obs_a, obs_b, obs_c])
    session.flush()

    # Match results:
    # A -> matched to act_a
    res_a = ObservationMatchResult(
        observation_id=obs_a.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.95,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(res_a)
    session.flush()
    cand_a = ObservationMatchCandidate(
        result_id=res_a.result_id,
        activity_id=act_a.activity_id,
        rank=1,
        similarity_score=0.95,
        contextual_score=0.95,
        final_score=0.95,
        explanation="Direct match to line erection",
    )
    session.add(cand_a)

    # B -> low confidence / needs review match
    res_b = ObservationMatchResult(
        observation_id=obs_b.observation_id,
        outcome=ObservationMatchOutcome.NEEDS_REVIEW,
        best_score=0.72,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(res_b)
    session.flush()
    cand_b1 = ObservationMatchCandidate(
        result_id=res_b.result_id,
        activity_id=act_b1.activity_id,
        rank=1,
        similarity_score=0.72,
        contextual_score=0.70,
        final_score=0.72,
        explanation="Low confidence candidate match requiring review",
    )
    cand_b2 = ObservationMatchCandidate(
        result_id=res_b.result_id,
        activity_id=act_b2.activity_id,
        rank=2,
        similarity_score=0.68,
        contextual_score=0.68,
        final_score=0.68,
        explanation="Alternative low confidence match",
    )
    session.add_all([cand_b1, cand_b2])

    # C -> matched to act_c_succ
    res_c = ObservationMatchResult(
        observation_id=obs_c.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.93,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(res_c)
    session.flush()
    cand_c = ObservationMatchCandidate(
        result_id=res_c.result_id,
        activity_id=act_c_succ.activity_id,
        rank=1,
        similarity_score=0.93,
        contextual_score=0.93,
        final_score=0.93,
        explanation="Matched to hydrotest preparation",
    )
    session.add(cand_c)
    session.commit()

    # Reconcile all 3 activities using deterministic mock provider
    mock_llm = DeterministicMockProvider()
    rec_service = ReconciliationService(session, llm_provider=mock_llm)
    rec_a = rec_service.reconcile_activity(act_a.activity_id)
    rec_b1 = rec_service.reconcile_activity(act_b1.activity_id)
    rec_c = rec_service.reconcile_activity(act_c_succ.activity_id)

    # Assertions:
    # 1. Event A is auto_accept / valid
    assert rec_a.decision == ReconciliationDecision.AUTO_ACCEPT

    # 2. Event B triggers planner review because match was ambiguous (candidates b1 and b2)
    assert rec_b1.decision == ReconciliationDecision.PLANNER_REVIEW

    # 3. Event C triggers planner review because safety gate detected dependency conflict with act_c_pred!
    assert rec_c.decision == ReconciliationDecision.PLANNER_REVIEW
    assert "predecessor" in rec_c.explanation.lower() or "conflict" in rec_c.explanation.lower() or "safety" in rec_c.explanation.lower()


def test_granularity_mismatch_and_multiple_candidates_preservation(session):
    """6 & 7: Granularity mismatch & multi-candidate preservation in Execution Context."""
    project = create_test_project(session)

    act_broad = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-500",
        description="Install piping assembly for Unit 3",  # Schedule Level
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.IN_PROGRESS,
        level=5,
    )
    act_alt = Activity(
        project_id=project.project_id,
        external_activity_id="PIP-501",
        description="Install secondary valve manifold for Unit 3",
        discipline="Piping",
        location="Unit 3",
        status=ActivityStatus.NOT_STARTED,
        level=6,
    )
    session.add_all([act_broad, act_alt])
    session.flush()

    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-2026-09-12.txt",
        source_timestamp=datetime(2026, 9, 12, 16, 30, tzinfo=UTC),
        raw_text="Installed valve XV-203 and completed bolt-up in Unit 3.",
    )
    session.add(ev)
    session.flush()

    # Detailed field description
    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Piping",
        location="Unit 3",
        contractor="Piping crew",
        activity_description="Installed valve XV-203 and completed bolt-up",  # Field Level Granularity
        status=ActivityStatus.COMPLETED,
        actual_start=date(2026, 9, 11),
        actual_end=date(2026, 9, 12),
        progress=100.0,
        confidence=0.95,
        provider_name="test",
        raw_provider_response={},
    )
    session.add(obs)
    session.flush()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.AMBIGUOUS,
        best_score=0.88,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(match_res)
    session.flush()

    cand1 = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act_broad.activity_id,
        rank=1,
        similarity_score=0.88,
        contextual_score=0.90,
        final_score=0.89,
        explanation="Valve XV-203 belongs to broader Unit 3 piping assembly.",
    )
    cand2 = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act_alt.activity_id,
        rank=2,
        similarity_score=0.82,
        contextual_score=0.84,
        final_score=0.83,
        explanation="Alternative candidate valve manifold.",
    )
    session.add_all([cand1, cand2])
    session.commit()

    service = ExecutionGraphService(session)
    ctx = service.get_activity_execution_context(project.project_id, act_broad.activity_id)

    # 1. Field-level description is preserved and distinct from schedule description
    assert ctx.activity.description == "Install piping assembly for Unit 3"
    assert len(ctx.execution_events) == 1
    event = ctx.execution_events[0]
    assert event.field_description == "Installed valve XV-203 and completed bolt-up"
    assert event.contractor == "Piping crew"
    assert event.location == "Unit 3"

    # 2. Both candidates preserved with scores and explanations
    assert len(event.candidates) == 2
    assert event.candidates[0].external_activity_id == "PIP-500"
    assert event.candidates[0].final_score == 0.89
    assert event.candidates[1].external_activity_id == "PIP-501"
    assert event.candidates[1].final_score == 0.83


def test_graph_query_api_endpoint(session):
    """12. Execution context REST API endpoint."""
    project = create_test_project(session)

    act = Activity(
        project_id=project.project_id,
        external_activity_id="API-001",
        description="Erect process column",
        discipline="Mechanical",
        location="Unit 1",
        status=ActivityStatus.NOT_STARTED,
        level=5,
    )
    session.add(act)
    session.commit()

    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/projects/{project.project_id}/activities/{act.activity_id}/execution-context"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["activity"]["external_activity_id"] == "API-001"
            assert data["activity"]["description"] == "Erect process column"
            assert "predecessors" in data
            assert "successors" in data
            assert "execution_events" in data
            assert "temporal_validation" in data
            assert "provenance" in data

            # 404 on missing activity
            bad_uuid = uuid.uuid4()
            resp_404 = client.get(
                f"/api/v1/projects/{project.project_id}/activities/{bad_uuid}/execution-context"
            )
            assert resp_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_predecessor_and_successor_lookups(session):
    """3, 4 & 5: Predecessor and successor execution relationships with lag and dependency type."""
    project = create_test_project(session)

    act_1 = Activity(
        project_id=project.project_id,
        external_activity_id="ACT-1",
        description="Site Clearing",
        discipline="Civil",
        status=ActivityStatus.COMPLETED,
        actual_end=date(2026, 9, 1),
        level=5,
    )
    act_2 = Activity(
        project_id=project.project_id,
        external_activity_id="ACT-2",
        description="Foundation Excavation",
        discipline="Civil",
        status=ActivityStatus.IN_PROGRESS,
        actual_start=date(2026, 9, 2),
        level=5,
    )
    act_3 = Activity(
        project_id=project.project_id,
        external_activity_id="ACT-3",
        description="Rebar Installation",
        discipline="Civil",
        status=ActivityStatus.NOT_STARTED,
        level=5,
    )
    session.add_all([act_1, act_2, act_3])
    session.flush()

    dep_1_2 = ActivityDependency(
        project_id=project.project_id,
        predecessor_id=act_1.activity_id,
        successor_id=act_2.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=1,
    )
    dep_2_3 = ActivityDependency(
        project_id=project.project_id,
        predecessor_id=act_2.activity_id,
        successor_id=act_3.activity_id,
        dependency_type=DependencyType.FINISH_TO_START,
        lag_days=0,
    )
    session.add_all([dep_1_2, dep_2_3])
    session.commit()

    service = ExecutionGraphService(session)
    ctx = service.get_activity_execution_context(project.project_id, act_2.activity_id)

    # Predecessor
    assert len(ctx.predecessors) == 1
    assert ctx.predecessors[0].external_activity_id == "ACT-1"
    assert ctx.predecessors[0].lag_days == 1
    assert ctx.predecessors[0].dependency_type == "finish_to_start"
    assert ctx.predecessors[0].status == "completed"

    # Successor
    assert len(ctx.successors) == 1
    assert ctx.successors[0].external_activity_id == "ACT-3"
    assert ctx.successors[0].lag_days == 0
    assert ctx.successors[0].status == "not_started"


def test_contractor_discipline_location_propagation(session):
    """7 & 11: Contractor, discipline, and location propagation from evidence to execution graph."""
    project = create_test_project(session)

    act = Activity(
        project_id=project.project_id,
        external_activity_id="ELEC-100",
        description="Cable pull to switchgear",
        discipline="Electrical",
        location="Substation B",
        status=ActivityStatus.IN_PROGRESS,
        level=6,
    )
    session.add(act)
    session.flush()

    ev = Evidence(
        project_id=project.project_id,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="VoltCorp_Weekly_Return.csv",
        source_timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        raw_text="Contractor: VoltCorp | Substation B cable pull 75% complete",
    )
    session.add(ev)
    session.flush()

    obs = EvidenceInterpretation(
        evidence_id=ev.evidence_id,
        original_evidence=ev.raw_text,
        discipline="Electrical",
        location="Substation B",
        contractor="VoltCorp Electrical Ltd",
        activity_description="Pulling 11kV cables to Substation B switchgear",
        status=ActivityStatus.IN_PROGRESS,
        progress=75.0,
        confidence=0.91,
        provider_name="test",
        raw_provider_response={},
    )
    session.add(obs)
    session.flush()

    match_res = ObservationMatchResult(
        observation_id=obs.observation_id,
        outcome=ObservationMatchOutcome.MATCHED,
        best_score=0.92,
        high_confidence_threshold=0.85,
        ambiguous_score_delta=0.08,
        no_match_threshold=0.50,
    )
    session.add(match_res)
    session.flush()

    cand = ObservationMatchCandidate(
        result_id=match_res.result_id,
        activity_id=act.activity_id,
        rank=1,
        similarity_score=0.92,
        contextual_score=0.92,
        final_score=0.92,
        explanation="Matched to switchgear cable pull",
    )
    session.add(cand)
    session.commit()

    service = ExecutionGraphService(session)
    ctx = service.get_activity_execution_context(project.project_id, act.activity_id)

    assert len(ctx.execution_events) == 1
    event = ctx.execution_events[0]
    assert event.contractor == "VoltCorp Electrical Ltd"
    assert event.discipline == "Electrical"
    assert event.location == "Substation B"
    assert event.source_name == "VoltCorp_Weekly_Return.csv"
    assert event.source_type == "contractor_spreadsheet"

