import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.engine import create_session_factory
from app.database.models import Evidence, ImportKind, ImportStatus, ImportedSource, SourceType
from app.database.repositories import ImportedSourceRepository, ProjectRepository
from app.modules.ingestion.errors import IngestionError
from app.modules.ingestion.service import IngestionService
from app.modules.ingestion.storage import persist_upload


router = APIRouter(prefix="/projects/{project_id}/imports")


class ImportStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_id: uuid.UUID
    project_id: uuid.UUID
    import_kind: ImportKind
    source_type: SourceType | None
    source_name: str
    stored_reference: str
    status: ImportStatus
    records_imported: int
    validation_errors: list[dict[str, str]] | None
    error_message: str | None
    completed_at: datetime | None
    created_at: datetime


def get_session():
    session_factory = create_session_factory()
    with session_factory() as session:
        yield session


async def _persist_and_import(
    project_id: uuid.UUID,
    upload: UploadFile,
    session: Session,
    import_source: Callable[[Path, str], ImportedSource],
) -> ImportStatusResponse:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    try:
        stored_path = await persist_upload(upload, Path(get_settings().ingestion_storage_path))
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    try:
        source_name = Path(upload.filename).name if upload.filename else stored_path.name
        source = import_source(stored_path, source_name)
    except IngestionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ImportStatusResponse.model_validate(source)


class ExtractedObservationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_id: uuid.UUID
    evidence_id: uuid.UUID
    activity_description: str
    discipline: str | None
    location: str | None
    status: str
    progress: float | None
    actual_start: str | None
    actual_end: str | None
    confidence: float
    notes: str | None = None
    contractor: str | None = None
    equipment_or_tag: str | None = None


class PasteDprRequest(BaseModel):
    raw_text: str
    source_name: str = "pasted_field_report.txt"
    source_type: SourceType = SourceType.DAILY_REPORT
    report_date: str | None = None
    auto_extract: bool = True


class PipelineProgressResponse(BaseModel):
    status: str
    evidence_count: int
    observations_extracted: int
    matched_count: int
    reconciled_count: int
    extracted_events: list[ExtractedObservationItem]


@router.post("/schedule", response_model=ImportStatusResponse)
async def import_schedule(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="L5/L6 schedule in CSV or XLSX format")],
    version: Annotated[str, Form(min_length=1, max_length=100)],
    session: Annotated[Session, Depends(get_session)],
) -> ImportStatusResponse:
    service = IngestionService(session)
    return await _persist_and_import(
        project_id,
        file,
        session,
        lambda path, name: service.import_schedule(project_id, path, name, version),
    )


@router.post("/evidence", response_model=ImportStatusResponse)
async def import_evidence(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Evidence in CSV, XLSX, TXT, or text-based PDF format")],
    source_type: Annotated[SourceType, Form()],
    session: Annotated[Session, Depends(get_session)],
    auto_extract: Annotated[bool, Form()] = True,
) -> ImportStatusResponse:
    service = IngestionService(session)
    response = await _persist_and_import(
        project_id,
        file,
        session,
        lambda path, name: service.import_evidence(project_id, path, name, source_type),
    )
    if auto_extract and response.status == ImportStatus.COMPLETED:
        _extract_pending_evidence(project_id, session)
    return response


@router.post("/paste", response_model=PipelineProgressResponse)
def paste_dpr(
    project_id: uuid.UUID,
    payload: PasteDprRequest,
    session: Annotated[Session, Depends(get_session)],
) -> PipelineProgressResponse:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not payload.raw_text or not payload.raw_text.strip():
        raise HTTPException(status_code=422, detail="Field report is empty.")

    service = IngestionService(session)
    source, evidence = service.import_text_evidence(
        project_id=project_id,
        raw_text=payload.raw_text,
        source_name=payload.source_name,
        source_type=payload.source_type,
    )
    if source.status == ImportStatus.FAILED:
        raise HTTPException(status_code=422, detail=source.error_message or "Text ingestion failed.")

    extracted_items: list[ExtractedObservationItem] = []
    if payload.auto_extract and evidence:
        observations = _extract_single_evidence(evidence, session)
        for obs in observations:
            extracted_items.append(
                ExtractedObservationItem(
                    observation_id=obs.observation_id,
                    evidence_id=obs.evidence_id,
                    activity_description=obs.activity_description,
                    discipline=obs.discipline,
                    location=obs.location,
                    status=obs.status.value,
                    progress=obs.progress,
                    actual_start=obs.actual_start.isoformat() if obs.actual_start else None,
                    actual_end=obs.actual_end.isoformat() if obs.actual_end else None,
                    confidence=obs.confidence,
                    notes=obs.additional_context,
                    contractor=obs.contractor,
                    equipment_or_tag=getattr(obs, "equipment_or_tag", None),
                )
            )

    return PipelineProgressResponse(
        status="completed",
        evidence_count=1,
        observations_extracted=len(extracted_items),
        matched_count=0,
        reconciled_count=0,
        extracted_events=extracted_items,
    )


@router.post("/process-pipeline", response_model=PipelineProgressResponse)
def process_pipeline(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> PipelineProgressResponse:
    """Extracts, normalizes, matches, and reconciles all pending evidence for the project."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    from sqlalchemy import select
    from app.ai.mock_provider import DeterministicEmbeddingProvider
    from app.database.models import Activity, Evidence, EvidenceInterpretation
    from app.modules.extraction.service import ExtractionService
    from app.modules.matching.service import MatchingService
    from app.modules.normalization.service import NormalizationService
    from app.modules.reconciliation.service import ReconciliationService

    evidence_rows = list(
        session.scalars(select(Evidence).where(Evidence.project_id == project_id))
    )
    extraction_service = ExtractionService(session)
    normalization_service = NormalizationService(session)
    matching_service = MatchingService(session, embedding_provider=DeterministicEmbeddingProvider())
    reconciliation_service = ReconciliationService(session)

    extracted_items: list[ExtractedObservationItem] = []
    observations: list[EvidenceInterpretation] = []

    for ev in evidence_rows:
        if not ev.interpretations:
            if ev.raw_text:
                obs_list = extraction_service.extract_evidence(ev.evidence_id)
                observations.extend(obs_list)
        else:
            observations.extend(ev.interpretations)

    matched_count = 0
    for obs in observations:
        if not obs.match_results:
            normalization_service.normalize_observation(obs.observation_id)
            matching_service.match_observation(obs.observation_id)
            matched_count += 1
        extracted_items.append(
            ExtractedObservationItem(
                observation_id=obs.observation_id,
                evidence_id=obs.evidence_id,
                activity_description=obs.activity_description,
                discipline=obs.discipline,
                location=obs.location,
                status=obs.status.value,
                progress=obs.progress,
                actual_start=obs.actual_start.isoformat() if obs.actual_start else None,
                actual_end=obs.actual_end.isoformat() if obs.actual_end else None,
                confidence=obs.confidence,
                notes=obs.additional_context,
            )
        )

    activities = list(session.scalars(select(Activity).where(Activity.project_id == project_id)))
    reconciled_count = 0
    for act in activities:
        reconciliation_service.reconcile_activity(act.activity_id)
        reconciled_count += 1

    session.commit()

    return PipelineProgressResponse(
        status="completed",
        evidence_count=len(evidence_rows),
        observations_extracted=len(extracted_items),
        matched_count=matched_count,
        reconciled_count=reconciled_count,
        extracted_events=extracted_items,
    )


def _extract_single_evidence(evidence: Evidence, session: Session) -> list:
    from app.modules.extraction.service import ExtractionService
    try:
        service = ExtractionService(session)
        return service.extract_evidence(evidence.evidence_id)
    except Exception:
        return []


def _extract_pending_evidence(project_id: uuid.UUID, session: Session) -> None:
    from sqlalchemy import select
    from app.database.models import Evidence
    from app.modules.extraction.service import ExtractionService
    evidence_rows = list(
        session.scalars(
            select(Evidence)
            .where(Evidence.project_id == project_id)
        )
    )
    service = ExtractionService(session)
    for ev in evidence_rows:
        if not ev.interpretations and ev.raw_text:
            try:
                service.extract_evidence(ev.evidence_id)
            except Exception:
                pass


@router.get("", response_model=list[ImportStatusResponse])
def list_imported_sources(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[ImportStatusResponse]:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return [
        ImportStatusResponse.model_validate(source)
        for source in ImportedSourceRepository(session).for_project(project_id)
    ]


@router.get("/{import_id}", response_model=ImportStatusResponse)
def get_import_status(
    project_id: uuid.UUID,
    import_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ImportStatusResponse:
    source = ImportedSourceRepository(session).get(import_id)
    if source is None or source.project_id != project_id:
        raise HTTPException(status_code=404, detail="Import not found.")
    return ImportStatusResponse.model_validate(source)

