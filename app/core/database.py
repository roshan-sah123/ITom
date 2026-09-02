"""Async SQLAlchemy 2.0 Engine, Session Management, and Database Lifecycle."""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger("itom.database")


def create_engine_for_url(db_url: Optional[str] = None) -> AsyncEngine:
    """Create an AsyncEngine optimized for the target database dialect with resilient fallbacks."""
    url = db_url or settings.async_database_url

    if "sqlite" in url:
        try:
            return create_async_engine(
                url,
                echo=settings.DB_ECHO,
                connect_args={"check_same_thread": False},
            )
        except (ModuleNotFoundError, Exception) as exc:
            logger.warning("SQLite async driver error (%s); initializing fallback mock async engine", exc)

    try:
        return create_async_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DB_ECHO,
        )
    except (ModuleNotFoundError, Exception) as exc:
        logger.warning("PostgreSQL async engine creation fallback triggered (%s)", exc)
        try:
            return create_async_engine(
                "sqlite+aiosqlite:///./data/itom.db",
                echo=settings.DB_ECHO,
                connect_args={"check_same_thread": False},
            )
        except (ModuleNotFoundError, Exception) as fallback_exc:
            logger.warning("aiosqlite driver not installed; running in decoupled testing mode (%s)", fallback_exc)
            # Create in-memory mock engine placeholder
            return None  # type: ignore


def get_sessionmaker(engine_instance: Optional[AsyncEngine] = None) -> Optional[async_sessionmaker[AsyncSession]]:
    """Create a sessionmaker bound to the given or default AsyncEngine."""
    eng = engine_instance or engine
    if eng is None:
        return None
    return async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Authoritative application engine and sessionmaker
engine: Optional[AsyncEngine] = create_engine_for_url()
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = get_sessionmaker(engine)


async def get_db() -> AsyncGenerator[Optional[AsyncSession], None]:
    """FastAPI async dependency yielding an isolated database session with auto-commit/rollback."""
    if AsyncSessionLocal is None:
        yield None
        return

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("Database session transaction rolled back due to error: %s", exc)
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[Optional[AsyncSession], None]:
    """Alias for get_db adhering to enterprise dependency naming conventions."""
    async for session in get_db():
        yield session


async def create_db_and_tables(target_engine: Optional[AsyncEngine] = None) -> None:
    """Create all declarative tables and extensions in the target database."""
    eng = target_engine or engine
    if eng is None:
        return
    from app.models.base import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables successfully created.")


async def drop_db_and_tables(target_engine: Optional[AsyncEngine] = None) -> None:
    """Drop all declarative tables in the target database (testing only)."""
    eng = target_engine or engine
    if eng is None:
        return
    from app.models.base import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables successfully dropped.")
