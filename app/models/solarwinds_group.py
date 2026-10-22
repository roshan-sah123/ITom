"""SolarWinds' source-owned groups and resolved, typed membership edges."""
import uuid
from typing import Optional

from datetime import datetime
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, UUIDPrimaryKeyMixin, UUIDType


class SolarWindsGroup(Base):
    __tablename__ = 'solarwinds_groups'

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='true')


class SolarWindsGroupLocation(Base):
    __tablename__ = 'solarwinds_group_locations'
    group_id: Mapped[int] = mapped_column(ForeignKey('solarwinds_groups.group_id'), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey('locations.id'), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[str] = mapped_column(String(36), nullable=False)
    __table_args__ = (CheckConstraint("approval_status IN ('APPROVED','REVIEW','REJECTED')", name='ck_sw_group_location_approval'),)


class SolarWindsGroupLocationReview(Base, UUIDPrimaryKeyMixin):
    __tablename__ = 'solarwinds_group_location_reviews'
    group_id: Mapped[int] = mapped_column(ForeignKey('solarwinds_groups.group_id'), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    before_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    after_data: Mapped[dict] = mapped_column(JSONType, nullable=False)


class SolarWindsGroupMember(Base):
    __tablename__ = 'solarwinds_group_members'

    group_id: Mapped[int] = mapped_column(ForeignKey('solarwinds_groups.group_id'), primary_key=True)
    member_entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    member_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    child_group_id: Mapped[Optional[int]] = mapped_column(ForeignKey('solarwinds_groups.group_id'))
    ci_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUIDType, ForeignKey('configuration_items.id'))

    __table_args__ = (
        CheckConstraint("(member_entity_type = 'Orion.Groups' AND child_group_id = member_id AND child_group_id IS NOT NULL AND ci_id IS NULL) OR "
                        "(member_entity_type = 'Orion.Nodes' AND ci_id IS NOT NULL AND child_group_id IS NULL)",
                        name='ck_sw_group_member_target'),
        Index('ix_sw_group_member_child', 'child_group_id'),
        Index('ix_sw_group_member_ci', 'ci_id'),
    )
