"""System liveness, readiness, and diagnostic health check endpoints."""

from datetime import datetime, timezone
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
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
        root = Path(__file__).resolve().parents[4]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        expected = set(ScriptDirectory.from_config(config).get_heads())
        revisions = set((await session.execute(text("SELECT version_num FROM alembic_version"))).scalars())
        dialect = session.bind.dialect.name
        ready = revisions == expected and (settings.ENVIRONMENT.lower() != "production" or dialect == "postgresql")
        if not ready:
            response.status_code = 503
        return {
            "status": "ready" if ready else "not_ready",
            "database": "connected",
            "database_engine": dialect,
            "migration_head": revisions == expected,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "detail": f"Readiness check failed: {type(exc).__name__}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
