"""Configuration management using Pydantic Settings and environment variables."""

import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Authoritative enterprise application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Metadata
    PROJECT_NAME: str = "ITOM Portal"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server Runtime
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = "itom-secret-key-change-in-production-0987654321"

    # Database Persistence
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/itom_db"
    SQLITE_DB_PATH: str = "./data/itom.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    # Microsoft Intune / Microsoft Graph API Configuration
    AZURE_TENANT_ID: Optional[str] = None
    AZURE_CLIENT_ID: Optional[str] = None
    AZURE_CLIENT_SECRET: Optional[str] = None
    AZURE_SECRET_ID: Optional[str] = None

    # SolarWinds Orion SWIS API Configuration
    SOLARWINDS_HOST: Optional[str] = None
    SOLARWINDS_PORT: int = 17774
    SOLARWINDS_USERNAME: Optional[str] = None
    SOLARWINDS_PASSWORD: Optional[str] = None

    # Sync Engine & Schedulers
    SYNC_INTERVAL_SECONDS: int = 600
    ADVISORY_LOCK_ID: int = 1048576  # PostgreSQL advisory lock ID for ITOM telemetry ETL

    # Local VM Deployment Configuration
    LOCAL_SERVER_IP: Optional[str] = None
    LOCAL_SERVER_USER: Optional[str] = None
    LOCAL_SERVER_PORT: int = 22

    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    @property
    def async_database_url(self) -> str:
        """Normalize database URL for async drivers (asyncpg / aiosqlite)."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return url


settings = Settings()
