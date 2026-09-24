import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.models import Activity
from app.database.repositories import ProjectRepository
from app.modules.reconciliation.schemas import ReconciliationResponse
from app.modules.reconciliation.service import ReconciliationService


router = APIRouter(prefix="/projects/{project_id}/activities")


@router.post("/{activity_id}/reconcile", response_model=ReconciliationResponse)
def reconcile_activity(project_id: uuid.UUID, activity_id: uuid.UUID,
                       session: Annotated[Session, Depends(get_session)]) -> ReconciliationResponse:
    activity = session.get(Activity, activity_id)
    if activity is None or activity.project_id != project_id:
        raise HTTPException(status_code=404, detail="Activity not found in project.")
    return ReconciliationService(session).reconcile_activity(activity_id)


@router.get("/{activity_id}/reconciliations", response_model=list[ReconciliationResponse])
def list_reconciliations(project_id: uuid.UUID, activity_id: uuid.UUID,
                         session: Annotated[Session, Depends(get_session)]) -> list[ReconciliationResponse]:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    activity = session.get(Activity, activity_id)
    if activity is None or activity.project_id != project_id:
        raise HTTPException(status_code=404, detail="Activity not found in project.")
    return [ReconciliationService._response(item) for item in activity.reconciliations]
