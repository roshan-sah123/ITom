"""Master API Router for v1 REST endpoints."""

from fastapi import APIRouter

from app.api.v1.endpoints import analytics, assets, cmdb, health, intune, solarwinds, sync, system, locations, location_reviews
from app.api.v1.endpoints import vendors, knowledge

api_router = APIRouter()

# Register domain routers
api_router.include_router(health.router)
api_router.include_router(cmdb.router)
api_router.include_router(assets.router)
api_router.include_router(vendors.router)
api_router.include_router(knowledge.router)
api_router.include_router(intune.router)
api_router.include_router(solarwinds.router)
api_router.include_router(sync.router)
api_router.include_router(system.router)
api_router.include_router(analytics.router)
api_router.include_router(location_reviews.router)
api_router.include_router(locations.router)
