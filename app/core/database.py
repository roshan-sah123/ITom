"""Async SQLAlchemy 2.0 Engine, Session Management, and Database Lifecycle."""

import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Optional
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger("itom.database")


@event.listens_for(Session, "do_orm_execute")
def active_inventory_scope(execute_state):
    """Inventory reads exclude retired assets; ingestion opts in explicitly."""
    if execute_state.is_select and not execute_state.execution_options.get("include_retired"):
        from app.models.ci import ConfigurationItem
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(ConfigurationItem, lambda ci: ci.is_active.is_(True), include_aliases=True)
        )


def _find_project_root() -> str:
    cur = os.path.abspath(__file__)
    while cur and os.path.dirname(cur) != cur:
        cur = os.path.dirname(cur)
        if os.path.exists(os.path.join(cur, "data", "itom.db")):
            return cur
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = _find_project_root()


def _sqlite_url(project_root: Optional[str] = None) -> str:
    """Resolve the explicitly configured SQLite database path."""
    configured_path = Path(settings.SQLITE_DB_PATH).expanduser()
    if not configured_path.is_absolute():
        configured_path = Path(project_root or PROJECT_ROOT) / configured_path
    return f"sqlite+aiosqlite:///{configured_path.resolve().as_posix()}"


SQLITE_URL = _sqlite_url()


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


def _create_sqlite_engine(url: str) -> AsyncEngine:
    """Create a local engine that lets portal reads coexist with sync writes."""
    sqlite_engine = create_async_engine(
        url,
        echo=settings.DB_ECHO,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(sqlite_engine.sync_engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return sqlite_engine


def create_engine_for_url(db_url: Optional[str] = None) -> AsyncEngine:
    """Create an AsyncEngine for the configured datastore without engine fallback."""
    url = db_url or settings.async_database_url
    if "sqlite" in url:
        url = SQLITE_URL if ("./data/itom.db" in url or "data/itom.db" in url) else url
        return _create_sqlite_engine(url)
    return create_async_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DB_ECHO,
        )


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
        raise RuntimeError("Configured database session is unavailable")

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
