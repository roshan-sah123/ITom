"""Run actual Alembic upgrades against a new database, independently of ORM bootstrap."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models.base import Base

ROOT = Path(__file__).resolve().parents[1]


def migrate(path, *arguments):
    environment = dict(os.environ, DATABASE_URL=f"sqlite+aiosqlite:///{path.as_posix()}", SCHEDULER_ENABLED="false")
    return subprocess.run([sys.executable, "-m", "alembic", *arguments], cwd=ROOT, env=environment,
                          capture_output=True, text=True, timeout=30)


@pytest.fixture
def migrated_database(tmp_path):
    path = tmp_path / "migrated.db"
    result = migrate(path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return path


def test_clean_upgrade_creates_model_columns_and_current_revision(migrated_database):
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    with sqlite3.connect(migrated_database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == ScriptDirectory.from_config(config).get_current_head()
        for table in Base.metadata.sorted_tables:
            columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table.name}")')}
            assert columns == set(table.columns.keys()), f"Migration/ORM columns differ for {table.name}"
    assert migrate(migrated_database, "upgrade", "head").returncode == 0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Audit P2: revision 0004 has a no-op upgrade and omits three ORM indexes")
def test_clean_upgrade_creates_all_model_indexes(migrated_database):
    with sqlite3.connect(migrated_database) as db:
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    required = {index.name for table in Base.metadata.tables.values() for index in table.indexes}
    assert required <= indexes, f"Missing migration indexes: {sorted(required - indexes)}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Audit P2: revision 0004 downgrade drops indexes that its upgrade never created")
def test_fresh_database_can_downgrade_and_upgrade(migrated_database):
    result = migrate(migrated_database, "downgrade", "base")
    assert result.returncode == 0, result.stderr
    assert migrate(migrated_database, "upgrade", "head").returncode == 0
