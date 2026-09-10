"""Master API Router for v1 REST endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints import analytics, cmdb, health, intune, solarwinds, sync, system

api_router = APIRouter()

# Register domain routers
api_router.include_router(health.router)
api_router.include_router(cmdb.router)
api_router.include_router(intune.router)
api_router.include_router(solarwinds.router)
api_router.include_router(sync.router)
api_router.include_router(system.router)
api_router.include_router(analytics.router)
