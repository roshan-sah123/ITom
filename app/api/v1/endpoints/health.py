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
from app.core.database import engine

router = APIRouter(tags=["System Probes"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
@router.get("/health", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict:
    """Kubernetes liveness probe returning process health and UTC timestamp."""
    return {
        "status": "ok",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "configured_database_engine": settings.database_engine,
        "active_database_engine": engine.dialect.name if engine is not None else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_probe(
    response: Response, session: AsyncSession = Depends(get_db)
) -> dict:
    """Readiness probe validating relational database connectivity."""
    configured_engine = settings.database_engine
    active_engine = engine.dialect.name if engine is not None else None
    database_path = None
    if configured_engine == "sqlite":
        from app.core.database import SQLITE_URL
        database_path = SQLITE_URL.rsplit("/", 1)[-1]
    try:
        if session is None:
            raise RuntimeError("Database session unavailable")
        await session.execute(text("SELECT 1"))
        await session.execute(text("SELECT 1"))
        root = Path(__file__).resolve().parents[4]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "alembic"))
        expected = set(ScriptDirectory.from_config(config).get_heads())
        revisions = set((await session.execute(text("SELECT version_num FROM alembic_version"))).scalars())
        dialect = session.bind.dialect.name
        # Readiness checks query and perform a harmless transactional write.
        await session.execute(text("SAVEPOINT readiness_write"))
        await session.execute(text("RELEASE SAVEPOINT readiness_write"))
        ready = revisions == expected and dialect == configured_engine
        if not ready:
            response.status_code = 503
        return {
            "status": "ready" if ready else "not_ready",
            "database": "connected",
            "database_engine": dialect,
            "configured_database_engine": configured_engine,
            "active_database_engine": dialect,
            "database_status": "connected" if ready else "migration_mismatch",
            "database_path": database_path,
            "connection_verified": True,
            "migration_head": revisions == expected,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "configured_database_engine": configured_engine,
            "active_database_engine": active_engine,
            "database_status": "unavailable",
            "database_path": database_path,
            "connection_verified": False,
            "detail": f"Readiness check failed: {type(exc).__name__}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
