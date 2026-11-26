"""Fail-closed configuration for the local experimental portal."""

from pathlib import Path
from typing import Mapping

from sqlalchemy.engine import make_url


def build_staging_environment(production: Mapping[str, str], staging_url: str, module_url: str, data_dir: Path) -> dict[str, str]:
    if not production.get("DATABASE_URL") or not production.get("DATABASE_URL_2"):
        raise ValueError("Both production database configurations are required for isolation checks")

    try:
        targets = [make_url(staging_url), make_url(module_url)]
        production_urls = [make_url(production[key]) for key in ("DATABASE_URL", "DATABASE_URL_2")]
    except Exception as exc:
        raise ValueError("Invalid database configuration") from exc

    for target, expected in zip(targets, ("itom_experimental", "itom_experimental_modules")):
        if (target.drivername != "postgresql+asyncpg" or target.host not in {"localhost", "127.0.0.1", "::1"}
                or target.port != 55432 or target.database != expected or target.query):
            raise ValueError("Experimental databases must use local PostgreSQL port 55432, the required names, and no URL options")
    if any(url.get_backend_name() == "postgresql" and url.database in {target.database for target in targets} for url in production_urls):
        raise ValueError("Experimental database name conflicts with production")
    if any(url.get_backend_name() == "postgresql" and url.host in {"localhost", "127.0.0.1", "::1"}
           and url.port == 55432 for url in production_urls):
        raise ValueError("Experimental database listener conflicts with production")

    return {
        "DATABASE_URL": staging_url,
        "DATABASE_URL_2": module_url,
        "ENVIRONMENT": "development",
        "ASSET_INVENTORY_DIR": str(data_dir / "asset_inventory"),
        "SCHEDULER_ENABLED": "false",
        "SYNC_EXECUTION_ENABLED": "false",
        "AUTH_ENABLED": "false",
        "MODULE_NETWORK_ACCESS": "false",
        "MODULE_SHARED_ORIGIN": "",
        "MODULE_SHARED_ACCESS_KEY": "",
        "AZURE_TENANT_ID": "",
        "AZURE_CLIENT_ID": "",
        "AZURE_CLIENT_SECRET": "",
        "SOLARWINDS_HOST": "",
        "SOLARWINDS_USERNAME": "",
        "SOLARWINDS_PASSWORD": "",
        "SPLUNK_ASSETS_ENABLED": "false",
    }