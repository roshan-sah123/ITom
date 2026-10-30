"""Canonical reporting locations, database rules and observed score snapshots."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, Boolean, DateTime, Index, UniqueConstraint, CheckConstraint
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
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING', server_default='PENDING')
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('source_system', 'match_key', name='uq_location_source_key'),
                     CheckConstraint("approval_status IN ('PENDING','APPROVED','REJECTED')",name='ck_location_rule_approval'),
                     CheckConstraint("approval_status != 'APPROVED' OR location_id IS NOT NULL",name='ck_location_approved_target'),
                     Index('ix_location_rule_review_queue','approval_status','source_system'))


class LocationMappingReview(Base, UUIDPrimaryKeyMixin):
    """Append-only decisions with a copy of the rule before and after review."""
    __tablename__ = 'location_mapping_reviews'
    rule_id: Mapped[str] = mapped_column(ForeignKey('location_mapping_rules.id'), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    before_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    after_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    __table_args__ = (Index('ix_location_review_rule_time','rule_id','reviewed_at'),)


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


class GeographicScoreSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'geographic_score_snapshots'
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'), nullable=False)
    sync_run_id: Mapped[object] = mapped_column(UUIDType, ForeignKey('sync_runs.id'), nullable=False)
    location_name: Mapped[str] = mapped_column(String(128), nullable=False)
    match_level: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    __table_args__ = (UniqueConstraint('location_id', 'sync_run_id', name='uq_geographic_location_run'),
                      Index('ix_geographic_snapshot_time', 'location_id', 'recorded_at'))


class GeographicScoreInventory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'geographic_score_inventory'
    snapshot_id: Mapped[object] = mapped_column(UUIDType, ForeignKey('geographic_score_snapshots.id', ondelete='CASCADE'), nullable=False)
    ci_id: Mapped[object] = mapped_column(UUIDType, ForeignKey('configuration_items.id'), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ci_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checkin_at_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_sync_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint('snapshot_id', 'ci_id', name='uq_geographic_snapshot_ci'),
                      Index('ix_geographic_inventory_snapshot', 'snapshot_id'))
