"""Configuration management using Pydantic Settings and environment variables."""

import os
from typing import Any, List, Optional, Union
from pydantic import Field, model_validator
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
    DEBUG: bool = False

    # Server Runtime
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    SECRET_KEY: Optional[str] = None

    # Database Persistence
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/itom.db"
    SQLITE_DB_PATH: str = "./data/itom.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_ECHO: bool = False

    # Source-specific HTTP transport. Inheritance follows requests' standard
    # environment proxy handling unless explicitly disabled here.
    SOURCE_PROXY_INHERIT: bool = True
    SOURCE_ALLOW_DIRECT: bool = False
    SOURCE_PROXY_MODE: str = "inherit"  # inherit | explicit | direct
    SOURCE_HTTP_PROXY: Optional[str] = None
    SOURCE_HTTPS_PROXY: Optional[str] = None
    SOURCE_NO_PROXY: str = ""
    SOLARWINDS_VERIFY_SSL: bool = True

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
    # Keep periodic ingestion enabled by default for the deployed VM. Set this
    # false only for local API development or read-only endpoint verification.
    SCHEDULER_ENABLED: bool = True
    ADVISORY_LOCK_ID: int = 1048576  # PostgreSQL advisory lock ID for ITOM telemetry ETL

    # Local VM Deployment Configuration
    LOCAL_SERVER_IP: Optional[str] = None
    LOCAL_SERVER_USER: Optional[str] = None
    LOCAL_SERVER_PORT: int = 22

    # CORS Configuration
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081,http://localhost:8000,http://127.0.0.1:8000"
    CORS_ALLOW_CREDENTIALS: bool = True
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    @staticmethod
    def _clean_origin(origin_val: Any) -> str:
        if origin_val is None:
            return ""
        s = str(origin_val).strip()
        while s and (s[0] in ("'", '"', '[', ' ') or s[-1] in ("'", '"', ']', ' ')):
            prev = s
            s = s.strip("'\"[] ")
            if s == prev:
                break
        if s != "*" and s != "/" and s.endswith("/"):
            s = s.rstrip("/")
        return s

    @classmethod
    def _parse_origin_input(cls, target: Any) -> List[str]:
        """Parse raw origin input (str, JSON list, or list) into cleaned origins."""
        if target is None:
            return []
        if isinstance(target, str):
            raw_str = target.strip()
            if raw_str.startswith("[") and raw_str.endswith("]"):
                import ast
                import json
                try:
                    parsed = json.loads(raw_str)
                    if isinstance(parsed, list):
                        target = parsed
                    else:
                        target = [raw_str]
                except Exception:
                    try:
                        parsed = ast.literal_eval(raw_str)
                        if isinstance(parsed, (list, tuple, set)):
                            target = list(parsed)
                        else:
                            target = [str(parsed)]
                    except Exception:
                        inner = raw_str[1:-1].strip()
                        target = [item.strip() for item in inner.split(",") if item.strip()]
            else:
                target = [item for item in raw_str.split(",") if item.strip()]

        if isinstance(target, (list, tuple, set)):
            origins = [cls._clean_origin(item) for item in target if item is not None and str(item).strip()]
        else:
            cleaned = cls._clean_origin(target)
            origins = [cleaned] if cleaned else []

        return [o for o in origins if o]

    @model_validator(mode="before")
    @classmethod
    def assemble_cors_origins(cls, values: Any) -> Any:
        if isinstance(values, dict):
            cors_raw = values.get("CORS_ORIGINS")
            backend_cors = values.get("BACKEND_CORS_ORIGINS")

            if backend_cors is not None and cors_raw is not None:
                parsed_backend = cls._parse_origin_input(backend_cors)
                parsed_cors = cls._parse_origin_input(cors_raw)
                # If either contains wildcard '*', make sure it's not bypassed
                if "*" in parsed_backend or "*" in parsed_cors:
                    origins = ["*"]
                else:
                    origins = parsed_backend if parsed_backend else parsed_cors
                values["BACKEND_CORS_ORIGINS"] = origins
                values["CORS_ORIGINS"] = origins
            elif backend_cors is not None:
                parsed_backend = cls._parse_origin_input(backend_cors)
                origins = parsed_backend if parsed_backend else ["http://localhost:8080"]
                values["BACKEND_CORS_ORIGINS"] = origins
                values["CORS_ORIGINS"] = origins
            elif cors_raw is not None:
                parsed_cors = cls._parse_origin_input(cors_raw)
                origins = parsed_cors if parsed_cors else ["http://localhost:8080"]
                values["BACKEND_CORS_ORIGINS"] = origins
                values["CORS_ORIGINS"] = origins
            else:
                # Local supervisor may serve the UI on either hostname and on
                # 8080/8081 depending on which portal instance is open.
                origins = [
                    "http://localhost:8080", "http://127.0.0.1:8080",
                    "http://localhost:8081", "http://127.0.0.1:8081",
                ]
                values["BACKEND_CORS_ORIGINS"] = origins
                values["CORS_ORIGINS"] = origins

        return values

    @model_validator(mode="after")
    def validate_app_configuration(self) -> "Settings":
        env = (self.ENVIRONMENT or "development").strip().lower()

        # 1. CORS Validation (R2)
        allow_creds = getattr(self, "CORS_ALLOW_CREDENTIALS", True)
        if allow_creds:
            has_wildcard = any(
                self._clean_origin(o) == "*" for o in (self.BACKEND_CORS_ORIGINS or [])
            )
            if not has_wildcard and isinstance(self.CORS_ORIGINS, str):
                has_wildcard = any(
                    self._clean_origin(s) == "*"
                    for s in self._parse_origin_input(self.CORS_ORIGINS)
                )
            elif not has_wildcard and isinstance(self.CORS_ORIGINS, list):
                has_wildcard = any(
                    self._clean_origin(o) == "*" for o in self.CORS_ORIGINS
                )

            if has_wildcard:
                raise ValueError(
                    "Insecure CORS configuration: Wildcard origin '*' cannot be used when allow_credentials=True."
                )

        # 2. DEBUG Validation (R4)
        if self.DEBUG:
            if env == "production":
                raise ValueError("DEBUG mode is strictly prohibited in production environment.")
            if env != "development":
                raise ValueError(
                    f"DEBUG mode is only permitted in development environment, not in '{self.ENVIRONMENT}'."
                )

        # 3. SECRET_KEY Validation (R3)
        if env != "development":
            if not self.SECRET_KEY or not str(self.SECRET_KEY).strip():
                raise ValueError(
                    f"SECRET_KEY must be configured in non-development environment '{self.ENVIRONMENT}'."
                )
            insecure_placeholders = {
                "itom-secret-key-change-in-production-0987654321",
                "your-secret-key-here",
                "your-secret-key",
                "secret",
                "changeme",
                "password",
                "admin",
                "default",
                "test",
                "dummy",
                "123456",
                "12345678",
                "secretkey",
                "placeholder",
                "demo",
            }
            clean_secret = str(self.SECRET_KEY).strip()
            if clean_secret.lower() in insecure_placeholders:
                raise ValueError(
                    f"Insecure placeholder SECRET_KEY is strictly forbidden in '{self.ENVIRONMENT}'. "
                    "Generate a cryptographically secure key via 'openssl rand -hex 32'."
                )
            if len(clean_secret) < 16:
                raise ValueError(
                    f"SECRET_KEY in non-development environment '{self.ENVIRONMENT}' must be at least 16 characters long. "
                    "Generate a cryptographically secure key via 'openssl rand -hex 32'."
                )

        return self


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

    @property
    def database_engine(self) -> str:
        return "sqlite" if self.async_database_url.startswith("sqlite") else "postgresql"


settings = Settings()
