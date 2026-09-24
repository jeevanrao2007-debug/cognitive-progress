from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.registry import AIProviderStatus, get_ai_status
from app.core.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    ai_status: AIProviderStatus


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        ai_status=get_ai_status(),
    )
