"""Canonical reporting locations, database rules and observed score snapshots."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, JSONType, UUIDPrimaryKeyMixin, UUIDType


class Location(Base, TimestampMixin):
    __tablename__ = 'locations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default='group')


class LocationMappingRule(Base):
    __tablename__ = 'location_mapping_rules'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    match_key: Mapped[str] = mapped_column(String(255), nullable=False)
    location_id: Mapped[Optional[str]] = mapped_column(ForeignKey('locations.id'), nullable=True)
    revision: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    __table_args__ = (UniqueConstraint('source_system', 'match_key', name='uq_location_source_key'),)


class LocationScoreSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'location_score_snapshots'
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'), nullable=False)
    sync_run_id: Mapped[object] = mapped_column(UUIDType, ForeignKey('sync_runs.id'), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    __table_args__ = (Index('ix_location_snapshot_time', 'location_id', 'recorded_at'),
                     UniqueConstraint('location_id','sync_run_id',name='uq_location_run_snapshot'))
