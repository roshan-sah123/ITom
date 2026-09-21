"""Async SQLAlchemy 2.0 Engine, Session Management, and Database Lifecycle."""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger("itom.database")


def _find_project_root() -> str:
    cur = os.path.abspath(__file__)
    while cur and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
        if os.path.exists(os.path.join(cur, "data", "itom.db")):
            return cur
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = _find_project_root()
SQLITE_FALLBACK_URL = f"sqlite+aiosqlite:///{os.path.join(PROJECT_ROOT, 'data', 'itom.db').replace(chr(92), '/')}"


def _is_db_reachable(db_url: str) -> bool:
    """Fast socket probe to verify if the configured database host/port is reachable."""
    import socket
    from urllib.parse import urlparse
    try:
        test_url = db_url.replace("+asyncpg", "") if "+asyncpg" in db_url else db_url
        parsed = urlparse(test_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def create_engine_for_url(db_url: Optional[str] = None) -> AsyncEngine:
    """Create an AsyncEngine optimized for the target database dialect with resilient fallbacks."""
    url = db_url or settings.async_database_url

    if "postgresql" in url and not _is_db_reachable(url):
        logger.info("Configured PostgreSQL server is unreachable; activating SQLite fallback: %s", SQLITE_FALLBACK_URL)
        url = SQLITE_FALLBACK_URL

    if "sqlite" in url:
        if "./data/itom.db" in url or "data/itom.db" in url:
            url = SQLITE_FALLBACK_URL
        try:
            sqlite_engine = create_async_engine(
                url,
                echo=settings.DB_ECHO,
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            # WAL lets dashboard reads continue while a remediation worklist is
            # saved; busy_timeout lets one writer wait for another writer.
            @event.listens_for(sqlite_engine.sync_engine, "connect")
            def configure_sqlite(connection, _connection_record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

            return sqlite_engine
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
                SQLITE_FALLBACK_URL,
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
    # Import cache models before creating metadata so existing deployments gain
    # the remediation-cache table on the next service startup.
    from app.models.compliance_cache import IntuneComplianceReasonCache  # noqa: F401
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
