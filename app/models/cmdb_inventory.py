"""Separate persistence for reviewed spreadsheet-owned CMDB inventory."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class CMDBInventoryRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cmdb_inventory_records"

    inventory_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[List[Dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    field_reviews: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    is_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("inventory_type", "source_key", name="uq_cmdb_inventory_source_key"),
        Index("ix_cmdb_inventory_type_name", "inventory_type", "name"),
        Index("ix_cmdb_inventory_validation", "inventory_type", "is_validated"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "inventory_type": self.inventory_type,
            "name": self.name,
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "data": self.data or [],
            "field_reviews": self.field_reviews or {},
            "is_validated": self.is_validated,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
            "validated_by": self.validated_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CMDBInventoryImport(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cmdb_inventory_imports"

    inventory_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    headers: Mapped[list] = mapped_column(JSONType, nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_by: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now(),
    )


class CMDBInventoryAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "cmdb_inventory_audit"

    inventory_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    record_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=func.now(),
    )