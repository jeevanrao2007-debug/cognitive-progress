import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.demo import reset_sih26122

router = APIRouter(prefix="/demo")
logger = logging.getLogger(__name__)

class DemoResetResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    message: str

@router.post("/reset", response_model=DemoResetResponse)
def reset_demo(session: Annotated[Session, Depends(get_session)]) -> DemoResetResponse:
    try:
        project = reset_sih26122(session)
    except Exception as error:
        session.rollback()
        logger.exception("Benchmark project baseline reset failed")
        raise HTTPException(status_code=500, detail="Unable to reset benchmark project baseline.") from error
    return DemoResetResponse(project_id=project.project_id, project_name=project.name, message="Project baseline initialized and synchronized across ingestion, extraction, matching, reconciliation, and audit services.")
