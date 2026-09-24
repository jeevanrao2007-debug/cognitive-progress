"""Deterministic project baseline scenario for refinery expansion."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.ai.mock_provider import DeterministicEmbeddingProvider
from app.database.models import (Activity, ActivityDependency, ActivityMatch, ActivityNormalization, AuditEvent,
    Evidence, EvidenceConflict, EvidenceInterpretation, ExecutionDeviation, ExecutionRecord,
    ImportedSource, ObservationMatchCandidate, ObservationMatchResult, PlannerReview, Project,
    Reconciliation, Schedule, ScheduleUpdate)
from app.modules.extraction.service import ExtractionService
from app.modules.ingestion.service import IngestionService
from app.modules.matching.service import MatchingService
from app.modules.memory.service import ExecutionMemoryService
from app.modules.normalization.service import NormalizationService
from app.modules.reconciliation.service import ReconciliationService

DEMO_NAME = "PRJ-2026-SYN01 · Oil & Gas Infrastructure Project (Synthetic Demo)"
DEMO_PROJECT_ID = uuid.UUID("26122000-0000-0000-0000-000000000001")
ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = ROOT / "data" / "demo_sih26122"


class DemoProvider:
    """Stable provider used only for the presentation scenario."""

    provider_name = "benchmark_provider"
    model_name = "reconciliation-engine-v1"

    def extract_progress(self, prompt: str) -> str:
        match = re.search(r'"raw_text":\s*"(.*?)"', prompt, flags=re.DOTALL)
        raw = json.loads(f'"{match.group(1)}"') if match else prompt
        lowered = raw.lower()

        delay_cause = None
        delay_category = None
        delay_confidence = None
        actual_start = None
        actual_end = None

        if "pending ndt clearance" in lowered or "ndt clearance" in lowered:
            status, progress = "in_progress", 40
            delay_cause = "Pending NDT clearance"
            delay_category = "INSPECTION"
            delay_confidence = 0.95
        elif "started at" in lowered or "hydrotest started" in lowered:
            status, progress = "in_progress", 20
            actual_start = "2026-09-12"
        elif "completed" in lowered or "complete" in lowered:
            status, progress = "completed", 100
            actual_end = "2026-09-03"
        elif "80%" in lowered:
            status, progress = "in_progress", 80
        elif "ongoing" in lowered:
            status, progress = "in_progress", 55
        else:
            status, progress = "in_progress", 35

        if "pending ndt clearance" in lowered or "hydrotest prep" in lowered:
            description, discipline, location = "Hydrotest preparation", "Piping", "Unit 3"
        elif "hydrotest line 18-aa" in lowered or "hydrotest started" in lowered or "line 18-aa" in lowered:
            description, discipline, location = "Hydrotest Line 18-AA", "Piping", "Unit 3"
        elif "valve" in lowered:
            description, discipline, location = "Valve installation", "Piping", "Unit 3"
        elif "24 inch" in lowered or "line 24" in lowered or "erection" in lowered:
            description, discipline, location = "24 inch line erection", "Piping", "Unit 3"
        elif "transformer" in lowered:
            description, discipline, location = "Install transformer foundation", "Electrical", "Substation"
        elif "cable tray" in lowered:
            description, discipline, location = "Cable tray installation", "Electrical", "Unit 2"
        elif "foundation" in lowered or "excavation" in lowered:
            description, discipline, location = "Foundation excavation", "Civil", "Unit 1"
        else:
            description, discipline, location = "Temporary fencing outside workfront", "Site Services", "Laydown"

        obs: dict[str, object] = {
            "discipline": discipline,
            "location": location,
            "activity_description": description,
            "status": status,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "progress": progress,
            "additional_context": raw,
            "confidence": 0.98,
            "delay_cause": delay_cause,
            "delay_category": delay_category,
            "delay_confidence": delay_confidence,
            "constraint": delay_cause,
            "impact_description": f"Activity delayed due to {delay_cause}" if delay_cause else None,
        }
        return json.dumps({"observations": [obs]})

    def normalize_activity(self, prompt: str) -> str:
        payload = prompt.split("INPUT_JSON:")[-1].lower() if "INPUT_JSON:" in prompt else prompt.lower()
        if "pending ndt clearance" in payload or "hydrotest prep" in payload:
            description, discipline, location = "Hydrotest preparation", "Piping", "Unit 3"
        elif "hydrotest line 18-aa" in payload or "hydrotest started" in payload or "line 18-aa" in payload:
            description, discipline, location = "Hydrotest Line 18-AA", "Piping", "Unit 3"
        elif "valve" in payload:
            description, discipline, location = "Valve installation", "Piping", "Unit 3"
        elif "24 inch" in payload or "line 24" in payload or "erection" in payload:
            description, discipline, location = "24 inch line erection", "Piping", "Unit 3"
        elif "transformer" in payload:
            description, discipline, location = "Install transformer foundation", "Electrical", "Substation"
        elif "cable tray" in payload:
            description, discipline, location = "Cable tray installation", "Electrical", "Unit 2"
        elif "foundation" in payload or "excavation" in payload:
            description, discipline, location = "Foundation excavation", "Civil", "Unit 1"
        else:
            description, discipline, location = "Temporary fencing outside workfront", "Site Services", "Laydown"
        return json.dumps({
            "normalized_activity_description": description,
            "normalized_discipline": discipline,
            "normalized_location": location,
            "confidence": 0.98,
        })

    def explain_reconciliation(self, prompt: str) -> str:
        return json.dumps({"explanation": "Multi-source evidence reconciliation based on source reliability, timestamps, and activity scope."})


def _delete_demo(session: Session, project: Project) -> None:
    ids = list(session.scalars(select(Activity.activity_id).where(Activity.project_id == project.project_id)))
    evidence_ids = list(session.scalars(select(Evidence.evidence_id).where(Evidence.project_id == project.project_id)))
    observation_ids = list(session.scalars(select(EvidenceInterpretation.observation_id).where(EvidenceInterpretation.evidence_id.in_(evidence_ids)))) if evidence_ids else []
    result_ids = list(session.scalars(select(ObservationMatchResult.result_id).where(ObservationMatchResult.observation_id.in_(observation_ids)))) if observation_ids else []
    rec_ids = list(session.scalars(select(Reconciliation.reconciliation_id).where(Reconciliation.activity_id.in_(ids)))) if ids else []
    review_ids = list(session.scalars(select(PlannerReview.review_id).where(PlannerReview.activity_id.in_(ids)))) if ids else []
    update_ids = list(session.scalars(select(ScheduleUpdate.update_id).where(ScheduleUpdate.activity_id.in_(ids)))) if ids else []
    record_ids = list(session.scalars(select(ExecutionRecord.record_id).where(ExecutionRecord.project_id == project.project_id)))
    # Break the self-referencing schedule hierarchy before bulk deletion.
    if ids:
        session.execute(update(Activity).where(Activity.activity_id.in_(ids)).values(parent_activity_id=None))
    for model, column, values in ((ExecutionDeviation, ExecutionDeviation.record_id, record_ids),
        (ExecutionRecord, ExecutionRecord.record_id, record_ids),
        (AuditEvent, AuditEvent.entity_id, ids + observation_ids + result_ids + rec_ids + review_ids + update_ids + record_ids),
        (ActivityMatch, ActivityMatch.activity_id, ids), (ActivityNormalization, ActivityNormalization.observation_id, observation_ids),
        (ObservationMatchCandidate, ObservationMatchCandidate.result_id, result_ids), (ObservationMatchResult, ObservationMatchResult.result_id, result_ids),
        (PlannerReview, PlannerReview.review_id, review_ids), (ScheduleUpdate, ScheduleUpdate.update_id, update_ids),
        (Reconciliation, Reconciliation.reconciliation_id, rec_ids), (EvidenceInterpretation, EvidenceInterpretation.observation_id, observation_ids),
        (EvidenceConflict, EvidenceConflict.activity_id, ids), (ImportedSource, ImportedSource.project_id, [project.project_id]),
        (Evidence, Evidence.evidence_id, evidence_ids), (ActivityDependency, ActivityDependency.project_id, [project.project_id]),
        (Activity, Activity.activity_id, ids), (Schedule, Schedule.project_id, [project.project_id])):
        if values:
            session.execute(delete(model).where(column.in_(values)))
    session.delete(project)
    session.flush()



def reset_sih26122(session: Session, project_id: uuid.UUID | None = None) -> Project:
    target_id = project_id or DEMO_PROJECT_ID
    existing = session.scalar(select(Project).where((Project.name == DEMO_NAME) | (Project.project_id == target_id)))
    if existing is not None:
        _delete_demo(session, existing)
    project = Project(
        project_id=target_id,
        name=DEMO_NAME,
        description="Synthetic Demonstration Project · Multi-Discipline Piping, Civil, Electrical & Instrumentation Package.",
    )
    session.add(project); session.flush()
    ingestion = IngestionService(session)
    ingestion.import_schedule(project.project_id, DEMO_DIR / "schedule.csv", "schedule_rev_04.csv", "baseline-v1")
    for filename, source_type in (
        ("supervisor.txt", "daily_report"),
        ("contractor.csv", "contractor_spreadsheet"),
        ("site_diary.txt", "site_diary"),
        ("high_confidence.txt", "daily_report"),
        ("ambiguous.txt", "site_diary"),
        ("unmatched.txt", "site_diary"),
        ("dependency_conflict.txt", "daily_report"),
        ("delay_cause.txt", "daily_report"),
    ):
        from app.database.models import SourceType
        ingestion.import_evidence(project.project_id, DEMO_DIR / filename, filename, SourceType(source_type))
    provider = DemoProvider()
    evidence_rows = list(session.scalars(select(Evidence).where(Evidence.project_id == project.project_id)))
    for evidence in evidence_rows:
        observations = ExtractionService(session, provider=provider).extract_evidence(evidence.evidence_id)
        for observation in observations:
            NormalizationService(session, provider=provider).normalize_observation(observation.observation_id)
            MatchingService(session, embedding_provider=DeterministicEmbeddingProvider()).match_observation(observation.observation_id)
    pip = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "PIP001"))
    if pip is not None:
        ReconciliationService(session).reconcile_activity(pip.activity_id)
    auto = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "ELEC001"))
    if auto is not None:
        ReconciliationService(session).reconcile_activity(auto.activity_id)
    pip3 = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "PIP003"))
    if pip3 is not None:
        ReconciliationService(session).reconcile_activity(pip3.activity_id)
    pip4 = session.scalar(select(Activity).where(Activity.project_id == project.project_id, Activity.external_activity_id == "PIP004"))
    if pip4 is not None:
        ReconciliationService(session).reconcile_activity(pip4.activity_id)
    ExecutionMemoryService(session, embedding_provider=DeterministicEmbeddingProvider()).sync_project_memory(project.project_id)
    session.commit()
    return project
