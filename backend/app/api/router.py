from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.matching import router as matching_router
from app.api.routes.reconciliation import router as reconciliation_router
from app.api.routes.planner_reviews import router as planner_reviews_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.demo import router as demo_router
from app.api.routes.activities import router as activities_router
from app.api.routes.schedule import router as schedule_router
from app.api.routes.memory import router as memory_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(imports_router, tags=["imports"])
api_router.include_router(matching_router, tags=["matching"])
api_router.include_router(reconciliation_router, tags=["reconciliation"])
api_router.include_router(activities_router, tags=["activities"])
api_router.include_router(schedule_router, tags=["schedule"])
api_router.include_router(memory_router, tags=["execution-memory"])
api_router.include_router(planner_reviews_router, tags=["planner-review"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(demo_router, tags=["demo"])

