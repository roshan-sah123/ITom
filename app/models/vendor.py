"""Portal-owned vendor submissions, separate from telemetry and legacy vendor data."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin


class VendorSubmission(Base, TimestampMixin):
    __tablename__ = "vendor_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sop_name: Mapped[str | None] = mapped_column(String(150))
    document: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, deferred=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validated_by: Mapped[str | None] = mapped_column(String(128))
    validated_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
