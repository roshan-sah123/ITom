import pytest

from scripts.staging_config import build_staging_environment


PRODUCTION = {
    "DATABASE_URL": "postgresql+asyncpg://user:password@localhost/itom_db",
    "DATABASE_URL_2": "postgresql+asyncpg://user:password@localhost/itom_modules",
}
STAGING_URL = "postgresql+asyncpg://user:password@127.0.0.1/itom_experimental"


def test_staging_environment_isolated_from_sources_and_auth(tmp_path):
    env = build_staging_environment(PRODUCTION, STAGING_URL, tmp_path)
    assert env["DATABASE_URL"] == env["DATABASE_URL_2"] == STAGING_URL
    assert env["SYNC_EXECUTION_ENABLED"] == env["SCHEDULER_ENABLED"] == "false"
    assert env["AUTH_ENABLED"] == "false"
    assert env["AZURE_CLIENT_SECRET"] == env["SOLARWINDS_PASSWORD"] == ""
    assert env["ASSET_INVENTORY_DIR"] == str(tmp_path / "asset_inventory")


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://user:password@localhost/itom_db",
    "postgresql+asyncpg://user:password@remote.example/itom_experimental",
    "postgresql+asyncpg://user:password@localhost/itom_experimental?host=remote.example",
    "sqlite+aiosqlite:///data/itom.db",
])
def test_staging_rejects_unsafe_database_urls(url, tmp_path):
    with pytest.raises(ValueError):
        build_staging_environment(PRODUCTION, url, tmp_path)


def test_staging_rejects_production_with_same_database_name(tmp_path):
    production = {**PRODUCTION, "DATABASE_URL": STAGING_URL}
    with pytest.raises(ValueError):
        build_staging_environment(production, STAGING_URL, tmp_path)