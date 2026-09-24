"""API routes for activity execution context and evidence graph."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.repositories import ProjectRepository
from app.modules.graph.schemas import ExecutionContextResponse
from app.modules.graph.service import ExecutionGraphService

router = APIRouter(prefix="/projects/{project_id}/activities")


@router.get("/{activity_id}/execution-context", response_model=ExecutionContextResponse)
def get_activity_execution_context(
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ExecutionContextResponse:
    """Retrieve the immediate execution evidence graph context for an activity."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ExecutionGraphService(session)
    try:
        return service.get_activity_execution_context(project_id, activity_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
