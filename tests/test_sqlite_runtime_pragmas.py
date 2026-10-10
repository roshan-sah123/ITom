"""Local SQLite concurrency settings required by long-running sync writes."""
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import create_engine_for_url


@pytest.mark.asyncio
async def test_local_sqlite_uses_wal_and_busy_timeout(tmp_path):
    db_path = tmp_path / "runtime.db"
    engine = create_engine_for_url(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        async with engine.connect() as connection:
            journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
            foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
        assert journal_mode.lower() == "wal"
        assert busy_timeout >= 30_000
        assert foreign_keys == 1
    finally:
        await engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
