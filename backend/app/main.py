from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


def create_application() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        description=(
            "CognitiveProgress project controls API. "
            "Provides evidence-backed reconciliation, planner review, and internal schedule provenance."
        ),
    )
    allowed_origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    if settings.frontend_origin and settings.frontend_origin not in allowed_origins:
        allowed_origins.append(settings.frontend_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_application()
