"""API routes for project execution memory, historical knowledge, and auditability."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.routes.imports import get_session
from app.database.models import ExecutionRecord
from app.database.repositories import ProjectRepository
from app.modules.memory.schemas import (
    ActivityExecutionHistoryResponse,
    CrossProjectMemoryResponse,
    ExecutionRecordResponse,
    ProjectPerformanceSummary,
    SimilarExecutionSearchResponse,
)
from app.modules.memory.service import ExecutionMemoryService

router = APIRouter()


@router.get(
    "/projects/{project_id}/memory/summary",
    response_model=ProjectPerformanceSummary,
    tags=["execution-memory"],
)
def get_project_memory_summary(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectPerformanceSummary:
    """Retrieve deterministic project performance metrics, average durations, and delay causes."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionMemoryService(session)
    try:
        return service.get_project_summary(project_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get(
    "/projects/{project_id}/memory/activities/{activity_id}",
    response_model=ActivityExecutionHistoryResponse,
    tags=["execution-memory"],
)
def get_activity_execution_history(
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ActivityExecutionHistoryResponse:
    """Retrieve full execution history, baseline deviations, delay causes, and audit trace for an activity."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionMemoryService(session)
    try:
        return service.get_activity_history(project_id, activity_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.post(
    "/projects/{project_id}/memory/sync",
    response_model=list[ExecutionRecordResponse],
    tags=["execution-memory"],
)
def sync_project_execution_memory(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> list[ExecutionRecordResponse]:
    """Synchronize live verified actuals and reconciliations into the persistent execution memory layer."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionMemoryService(session)
    records = service.sync_project_memory(project_id)
    return [ExecutionRecordResponse.model_validate(r) for r in records]


@router.get(
    "/projects/{project_id}/memory/records",
    response_model=list[ExecutionRecordResponse],
    tags=["execution-memory"],
)
def list_project_execution_records(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    discipline: str | None = Query(default=None),
    deviation_type: str | None = Query(default=None),
    contractor: str | None = Query(default=None),
) -> list[ExecutionRecordResponse]:
    """List detailed execution records for a project, with optional filtering."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionMemoryService(session)
    service.sync_project_memory(project_id)

    stmt = (
        select(ExecutionRecord)
        .where(ExecutionRecord.project_id == project_id)
        .options(selectinload(ExecutionRecord.deviations))
    )
    if discipline:
        stmt = stmt.where(ExecutionRecord.discipline.ilike(f"%{discipline}%"))
    if deviation_type:
        stmt = stmt.where(ExecutionRecord.deviation_type == deviation_type.upper())
    if contractor:
        stmt = stmt.where(ExecutionRecord.contractor.ilike(f"%{contractor}%"))

    records = list(session.scalars(stmt))
    return [ExecutionRecordResponse.model_validate(r) for r in records]


@router.get(
    "/projects/{project_id}/memory/similar",
    response_model=SimilarExecutionSearchResponse,
    tags=["execution-memory"],
)
def find_similar_historical_executions(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    query: str | None = Query(default=None),
    discipline: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
) -> SimilarExecutionSearchResponse:
    """Retrieve similar historical completed activities as reference points. Clearly labeled as historical reference."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionMemoryService(session)
    return service.find_similar_executions(query=query, discipline=discipline, limit=limit)


@router.get(
    "/memory/cross-project/summary",
    response_model=CrossProjectMemoryResponse,
    tags=["execution-memory"],
)
def get_cross_project_memory_summary(
    session: Annotated[Session, Depends(get_session)],
    discipline: str | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
) -> CrossProjectMemoryResponse:
    """Query institutional knowledge across all projects in the memory layer."""
    service = ExecutionMemoryService(session)
    return service.query_cross_project(discipline=discipline, query=query, limit=limit)
