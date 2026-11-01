from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin


class AssetInventoryBatch(Base, TimestampMixin):
    __tablename__ = "asset_inventory_batches"
    category: Mapped[str] = mapped_column(String(16), primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255))
    source_sheet: Mapped[str] = mapped_column(String(255))
    columns: Mapped[list] = mapped_column(JSONType)


class AssetInventoryRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_inventory_records"
    category: Mapped[str] = mapped_column(String(16))
    source_key: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(512))
    source_file: Mapped[str] = mapped_column(String(255))
    source_sheet: Mapped[str] = mapped_column(String(255))
    source_row: Mapped[int] = mapped_column(Integer)
    source_order: Mapped[int] = mapped_column(Integer)
    data: Mapped[list] = mapped_column(JSONType)
    field_reviews: Mapped[dict] = mapped_column(JSONType, default=dict)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validated_by: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("category", "source_key", name="uq_asset_inventory_source"),)


class AssetInventoryAudit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_inventory_audit"
    category: Mapped[str] = mapped_column(String(16))
    record_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSONType)
