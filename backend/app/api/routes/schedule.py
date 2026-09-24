"""API routes for schedule change preview and verified schedule export."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.repositories import ProjectRepository
from app.modules.schedule.bridge_service import ScheduleBridgeService
from app.modules.schedule.schemas import ScheduleChangePreviewResponse

router = APIRouter(prefix="/projects/{project_id}/schedule")


@router.get("/preview", response_model=ScheduleChangePreviewResponse)
def get_schedule_preview(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleChangePreviewResponse:
    """Provide a deterministic preview of schedule actuals, categorizing verified vs excluded items."""
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    service = ScheduleBridgeService(session)
    try:
        return service.get_change_preview(project_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get("/export")
def export_verified_schedule(
    project_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    format: Annotated[str, Query(description="Export format: 'csv' or 'xlsx'")] = "csv",
) -> Response:
    """Export verified schedule with verified actual dates.
    
    CRITICAL EXPORT SAFETY: Unverified, planner review, conflict, or rejected updates
    are strictly excluded from verified actual fields.
    """
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    fmt = format.lower().strip()
    if fmt not in {"csv", "xlsx"}:
        raise HTTPException(status_code=400, detail="Supported export formats are 'csv' and 'xlsx'.")

    service = ScheduleBridgeService(session)
    try:
        content, media_type, filename = service.export_verified_schedule(project_id, export_format=fmt)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
