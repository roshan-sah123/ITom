"""FastAPI dependency injection providers for database sessions and services."""

from collections.abc import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories.ci_repository import CIRepository
from app.repositories.sync_repository import SyncRepository
from app.services.ci_service import CIService
from app.services.sync_service import SyncService


async def get_ci_repository(session: AsyncSession = Depends(get_db)) -> CIRepository:
    """Dependency yielding a CIRepository bound to the request session."""
    return CIRepository(session)


async def get_sync_repository(session: AsyncSession = Depends(get_db)) -> SyncRepository:
    """Dependency yielding a SyncRepository bound to the request session."""
    return SyncRepository(session)


async def get_ci_service(ci_repo: CIRepository = Depends(get_ci_repository)) -> CIService:
    """Dependency yielding a CIService instance."""
    return CIService(ci_repo)


async def get_sync_service(session: AsyncSession = Depends(get_db)) -> SyncService:
    """Dependency yielding a SyncService instance."""
    return SyncService(session)
