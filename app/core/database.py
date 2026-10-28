"""Async SQLAlchemy 2.0 Engine, Session Management, and Database Lifecycle."""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
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


SQLITE_DATABASE_PATH = Path(settings.SQLITE_DB_PATH).expanduser()
if not SQLITE_DATABASE_PATH.is_absolute():
    SQLITE_DATABASE_PATH = Path(PROJECT_ROOT) / SQLITE_DATABASE_PATH
SQLITE_DATABASE_PATH = SQLITE_DATABASE_PATH.resolve()
SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_DATABASE_PATH.as_posix()}"


def prepare_sqlite_storage(database_path: Path = SQLITE_DATABASE_PATH) -> Path:
    """Create storage safely and refuse a silent empty replacement when backups exist."""
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = database_path.parent / "backups"
    existing_backups = sorted(backup_dir.glob(f"{database_path.stem}-*.db")) if backup_dir.exists() else []
    if not database_path.exists() and existing_backups:
        raise RuntimeError(
            f"Database {database_path} is missing while backups exist in {backup_dir}. "
            "Restore a backup instead of starting with an empty database."
        )
    return database_path


def create_sqlite_backup(database_path: Path, label: str = "backup", keep: int = 5) -> Optional[Path]:
    """Create a consistent SQLite backup and retain only the newest copies for this database."""
    source_path = Path(database_path).resolve()
    if not source_path.is_file():
        return None
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "-", label).strip("-") or "backup"
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"{source_path.stem}-{safe_label}-{stamp}.db"
    temporary = destination.with_suffix(".tmp")
    try:
        with sqlite3.connect(source_path) as source, sqlite3.connect(temporary) as target:
            source.backup(target)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    backups = sorted(backup_dir.glob(f"{source_path.stem}-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    for stale in backups[max(1, keep):]:
        stale.unlink(missing_ok=True)
    return destination


if "sqlite" in settings.async_database_url:
    prepare_sqlite_storage()
    logger.info("Authoritative SQLite database: %s", SQLITE_DATABASE_PATH)


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
        if ":memory:" not in url:
            url = SQLITE_URL
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


async def _repair_legacy_sqlite_schema(connection) -> None:
    """Add columns that create_all cannot retrofit on an existing local SQLite DB."""
    if connection.dialect.name != "sqlite":
        return

    async def columns(table: str) -> set[str]:
        result = await connection.exec_driver_sql(f'PRAGMA table_info("{table}")')
        return {str(row[1]) for row in result.fetchall()}

    sync_columns = await columns("sync_runs")
    for name in ("records_retired", "records_failed", "items_normalized", "items_rejected"):
        if sync_columns and name not in sync_columns:
            await connection.exec_driver_sql(
                f'ALTER TABLE "sync_runs" ADD COLUMN "{name}" INTEGER NOT NULL DEFAULT 0'
            )

    ci_columns = await columns("configuration_items")
    if ci_columns and "is_active" not in ci_columns:
        await connection.exec_driver_sql(
            'ALTER TABLE "configuration_items" ADD COLUMN "is_active" BOOLEAN NOT NULL DEFAULT 1'
        )
    if ci_columns and "retired_at" not in ci_columns:
        await connection.exec_driver_sql(
            'ALTER TABLE "configuration_items" ADD COLUMN "retired_at" DATETIME'
        )
    if ci_columns:
        await connection.exec_driver_sql(
            'CREATE INDEX IF NOT EXISTS "ix_ci_source_active" '
            'ON "configuration_items" ("source_system", "is_active")'
        )

    inventory_columns = await columns("cmdb_inventory_records")
    inventory_repaired = False
    if inventory_columns and "source_order" not in inventory_columns:
        await connection.exec_driver_sql(
            'ALTER TABLE "cmdb_inventory_records" ADD COLUMN "source_order" INTEGER NOT NULL DEFAULT 0'
        )
        inventory_repaired = True
    if inventory_columns and "field_reviews" not in inventory_columns:
        await connection.exec_driver_sql(
            "ALTER TABLE \"cmdb_inventory_records\" ADD COLUMN \"field_reviews\" JSON NOT NULL DEFAULT '{}'"
        )
        inventory_repaired = True
    if inventory_columns and inventory_repaired:
        rows = (await connection.exec_driver_sql(
            'SELECT "id", "inventory_type", "source_file", "source_sheet", '
            '"source_row", "data" FROM "cmdb_inventory_records" '
            'ORDER BY "inventory_type", "source_file", "source_sheet", "source_row"'
        )).fetchall()
        counters = {}
        for record_id, inventory_type, _source_file, _source_sheet, _source_row, raw_data in rows:
            position = counters.get(inventory_type, 0)
            counters[inventory_type] = position + 1
            try:
                data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            except (TypeError, ValueError):
                data = raw_data
            if isinstance(data, dict):
                data = [
                    {"index": index, "header": header, "value": value}
                    for index, (header, value) in enumerate(data.items())
                ]
            await connection.exec_driver_sql(
                "UPDATE \"cmdb_inventory_records\" SET \"source_order\" = ?, \"data\" = ?, "
                "\"field_reviews\" = COALESCE(\"field_reviews\", '{}') WHERE \"id\" = ?",
                (position, json.dumps(data, ensure_ascii=True), record_id),
            )


async def create_db_and_tables(target_engine: Optional[AsyncEngine] = None) -> None:
    """Create new tables and safely repair known legacy SQLite columns."""
    eng = target_engine or engine
    if eng is None:
        return
    from app.models.base import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _repair_legacy_sqlite_schema(conn)
    logger.info("Database tables created and local SQLite compatibility checked.")


async def drop_db_and_tables(target_engine: Optional[AsyncEngine] = None) -> None:
    """Drop all declarative tables in the target database (testing only)."""
    eng = target_engine or engine
    if eng is None:
        return
    from app.models.base import Base

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables successfully dropped.")
