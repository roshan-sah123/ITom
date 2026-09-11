from dotenv import load_dotenv
load_dotenv()

"""Main FastAPI Application initialization, lifespan events, middleware, and route mounting."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import create_db_and_tables, engine
from app.core.middleware import FreshnessHeadersMiddleware, get_last_sync_timestamp
from app.core.security import SolarWindsSecurityError
from app.repositories.summary_repository import EmptyDatasetError
from app.workers.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger("itom.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management handling database migrations and scheduler worker."""
    logger.info("Starting ITOM Portal FastAPI Backend v%s (%s)...", settings.VERSION, settings.ENVIRONMENT)

    # Auto-create tables in development/local mode
    try:
        await create_db_and_tables(engine)
    except Exception as exc:
        logger.warning("Auto table creation encountered notice: %s", exc)

    # Start APScheduler background sync worker if not running tests
    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("Background scheduler startup notice: %s", exc)

    yield

    # Graceful shutdown
    logger.info("Shutting down ITOM Portal FastAPI Backend...")
    try:
        stop_scheduler()
    except Exception as exc:
        logger.warning("Scheduler shutdown notice: %s", exc)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise IT Operations Management & CMDB Telemetry Async REST API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Configuration
if settings.CORS_ALLOW_CREDENTIALS and any(
    settings._clean_origin(o) == "*" for o in settings.BACKEND_CORS_ORIGINS
):
    raise ValueError("Insecure CORS configuration: Wildcard origin '*' is forbidden when allow_credentials=True.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authoritative Freshness & Read-Only Guard Middleware
app.add_middleware(FreshnessHeadersMiddleware)


# Custom Exception Handlers
@app.exception_handler(EmptyDatasetError)
async def empty_dataset_exception_handler(request: Request, exc: EmptyDatasetError):
    """Return HTTP 503 when a telemetry domain has no ingested data."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Telemetry dataset unavailable",
            "detail": str(exc),
            "source_system": exc.source_system,
            "data_source": "NONE",
        },
    )


# Custom Exception Handlers
@app.exception_handler(SolarWindsSecurityError)
async def solarwinds_security_exception_handler(request: Request, exc: SolarWindsSecurityError):
    """Handle forbidden mutating queries or operations."""
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "Security Violation", "detail": str(exc)},
    )


@app.exception_handler(405)
async def method_not_allowed_exception_handler(request: Request, exc: Exception):
    """Enforce strict read-only error envelope for HTTP 405 Method Not Allowed."""
    now = datetime.now(timezone.utc)
    last_sync = get_last_sync_timestamp()
    age_seconds = max(0, int((now - last_sync).total_seconds()))
    sync_status = "FRESH" if age_seconds <= 900 else "STALE"

    headers = {
        "Allow": "GET, HEAD, OPTIONS",
        "X-Last-Synchronized-At": last_sync.isoformat(),
        "X-Data-Age-Seconds": str(age_seconds),
        "X-Sync-Status": sync_status,
    }
    return JSONResponse(
        status_code=405,
        content={
            "error": "Forbidden: SolarWinds/Intune Telemetry API is strictly READ-ONLY.",
            "allowed_methods": ["GET"],
        },
        headers=headers,
    )


# Mount Root and API v1 Health Probes
app.include_router(health.router)
app.include_router(health.router, prefix=settings.API_V1_STR)

# Mount API v1 Routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root metadata probe."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "operational",
        "docs": "/docs",
        "api_v1": settings.API_V1_STR,
    }
