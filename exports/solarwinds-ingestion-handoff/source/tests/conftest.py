"""Isolated application fixtures; no developer credentials or live source calls."""
import os
from pathlib import Path

# Set before importing application modules: neither Settings nor load_dotenv may
# select the developer's database, credentials, or transport policy during tests.
for key, value in {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "SCHEDULER_ENABLED": "false", "ENVIRONMENT": "development", "DEBUG": "false",
    "AZURE_TENANT_ID": "", "AZURE_CLIENT_ID": "", "AZURE_CLIENT_SECRET": "",
    "SOLARWINDS_HOST": "", "SOLARWINDS_USERNAME": "", "SOLARWINDS_PASSWORD": "",
    "SOURCE_PROXY_MODE": "inherit", "SOURCE_ALLOW_DIRECT": "false",
    "SOURCE_PROXY_INHERIT": "true", "SOURCE_HTTP_PROXY": "", "SOURCE_HTTPS_PROXY": "",
    "SOURCE_NO_PROXY": "", "SOLARWINDS_VERIFY_SSL": "true",
    "SECRET_KEY": "", "CORS_ALLOW_CREDENTIALS": "true",
    "CORS_ORIGINS": "http://localhost:8080,http://127.0.0.1:8080",
    "BACKEND_CORS_ORIGINS": '["http://localhost:8080","http://127.0.0.1:8080"]',
}.items():
    os.environ[key] = value

import pytest
import pytest_asyncio
import requests
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_engine_for_url, get_db
from app.models.base import Base
from app.models import ci, history, sync  # register all persistence tables

ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser):
    parser.addoption("--run-browser", action="store_true", help="Run isolated browser journeys")


def pytest_ignore_collect(collection_path, config):
    if "browser" in collection_path.parts and not config.getoption("--run-browser"):
        return True


@pytest.fixture(autouse=True)
def block_live_source_requests(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected live source request; mock the source transport")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    engine = create_engine_for_url(f"sqlite+aiosqlite:///{(tmp_path / 'itom-test.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def session(db_session_factory):
    async with db_session_factory() as db:
        yield db


@pytest_asyncio.fixture
async def api_environment(db_engine, db_session_factory, monkeypatch):
    from app.main import app
    from app import main
    from app.core import database, middleware
    from app.api.v1.endpoints import health, sync as sync_routes
    from app.services.summary_cache import summary_cache

    async def isolated_db():
        async with db_session_factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    head = ScriptDirectory.from_config(config).get_current_head()
    async with db_engine.begin() as conn:
        # API fixtures use ORM schema; actual Alembic execution is tested separately.
        await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
        await conn.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": head})
    for module in (main, database, health):
        monkeypatch.setattr(module, "engine", db_engine)
    for module in (database, middleware, sync_routes):
        monkeypatch.setattr(module, "AsyncSessionLocal", db_session_factory)
    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = isolated_db
    summary_cache.invalidate()
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        summary_cache.invalidate()


@pytest_asyncio.fixture
async def api_client(api_environment):
    async with AsyncClient(transport=ASGITransport(app=api_environment), base_url="http://test") as client:
        yield client
