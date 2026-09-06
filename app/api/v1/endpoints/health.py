"""System liveness, readiness, and diagnostic health check endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["System Probes"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict:
    """Kubernetes liveness probe returning process health and UTC timestamp."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_probe(
    response: Response, session: AsyncSession = Depends(get_db)
) -> dict:
    """Readiness probe validating relational database connectivity."""
    try:
        await session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "migration_head": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
