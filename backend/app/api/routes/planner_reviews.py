import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.imports import get_session
from app.database.models import PlannerReview, ReviewDecision
from app.database.repositories import ProjectRepository
from app.modules.planner_review.schemas import PlannerActionRequest, PlannerReviewContext
from app.modules.planner_review.service import PlannerReviewService


router = APIRouter(prefix="/projects/{project_id}/planner-reviews")


def _review_for_project(session: Session, review_id: uuid.UUID, project_id: uuid.UUID) -> PlannerReview | None:
    return session.scalar(select(PlannerReview).join(PlannerReview.activity).where(
        PlannerReview.review_id == review_id, PlannerReview.activity.has(project_id=project_id)))


@router.get("", response_model=list[PlannerReviewContext])
def list_reviews(project_id: uuid.UUID, session: Annotated[Session, Depends(get_session)],
                 pending_only: bool = True) -> list[PlannerReviewContext]:
    if ProjectRepository(session).get(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    statement = select(PlannerReview).join(PlannerReview.activity).where(PlannerReview.activity.has(project_id=project_id))
    if pending_only:
        statement = statement.where(PlannerReview.reviewer_decision == ReviewDecision.PENDING)
    return [PlannerReviewService(session).context(review.review_id) for review in session.scalars(statement)]


@router.get("/{review_id}", response_model=PlannerReviewContext)
def get_review(project_id: uuid.UUID, review_id: uuid.UUID,
               session: Annotated[Session, Depends(get_session)]) -> PlannerReviewContext:
    if _review_for_project(session, review_id, project_id) is None:
        raise HTTPException(status_code=404, detail="Planner review not found.")
    return PlannerReviewService(session).context(review_id)


@router.post("/{review_id}/actions", response_model=PlannerReviewContext)
def act_on_review(project_id: uuid.UUID, review_id: uuid.UUID, request: PlannerActionRequest,
                  session: Annotated[Session, Depends(get_session)]) -> PlannerReviewContext:
    if _review_for_project(session, review_id, project_id) is None:
        raise HTTPException(status_code=404, detail="Planner review not found.")
    try:
        return PlannerReviewService(session).act(review_id, request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
