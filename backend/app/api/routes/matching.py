import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.models import EvidenceInterpretation, ObservationMatchOutcome
from app.database.repositories import ProjectRepository
from app.modules.extraction.errors import AIInterpretationError
from app.modules.matching.schemas import ObservationMatchResponse
from app.modules.matching.service import MatchingService


router = APIRouter(prefix="/projects/{project_id}/matches")


@router.post("/observations/{observation_id}", response_model=ObservationMatchResponse)
def match_observation(project_id: uuid.UUID, observation_id: uuid.UUID,
                      session: Annotated[Session, Depends(get_session)]) -> ObservationMatchResponse:
    observation = session.get(EvidenceInterpretation, observation_id)
    if observation is None or observation.evidence.project_id != project_id:
        raise HTTPException(status_code=404, detail="Observation not found in project.")
    try:
        return MatchingService(session).match_observation(observation_id)
    except AIInterpretationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("", response_model=list[ObservationMatchResponse])
def list_matches(project_id: uuid.UUID, session: Annotated[Session, Depends(get_session)],
                 outcome: ObservationMatchOutcome | None = None) -> list[ObservationMatchResponse]:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return MatchingService(session).list_results(project_id, outcome)
