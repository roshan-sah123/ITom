"""Declarative base and core model mixins supporting PostgreSQL and SQLite."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import DateTime, JSON, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Cross-dialect JSON and UUID type definitions
JSONType = JSON().with_variant(JSONB, "postgresql")
UUIDType = Uuid(as_uuid=True).with_variant(PG_UUID(as_uuid=True), "postgresql")


class Base(DeclarativeBase):
    """Authoritative base class for all SQLAlchemy 2.0 declarative models."""
    pass


class UUIDPrimaryKeyMixin:
    """Mixin adding a standard UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin adding timezone-aware created_at and updated_at tracking columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=func.now(),
    )
