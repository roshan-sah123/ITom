"""Configuration Item and Relationship models for CMDB and multi-domain telemetry."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

if TYPE_CHECKING:
    from app.models.history import CIStatusHistory


class ConfigurationItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative relational representation of an IT Configuration Item (CI)."""

    __tablename__ = "configuration_items"

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)  # "SOLARWINDS" | "INTUNE"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ci_type: Mapped[str] = mapped_column(String(64), nullable=False)        # "Server", "Access Switch", "Windows", etc.
    status: Mapped[str] = mapped_column(String(32), nullable=False)         # "Up", "Down", "Compliant", etc.
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False)    # "High", "Medium", "Low"
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False, default="Other")
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    operating_system: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_sync_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    state_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    # Relationships
    status_history: Mapped[List["CIStatusHistory"]] = relationship(
        "CIStatusHistory",
        back_populates="ci",
        cascade="all, delete-orphan",
    )
    outgoing_relationships: Mapped[List["CIRelationship"]] = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.source_ci_id",
        back_populates="source_ci",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[List["CIRelationship"]] = relationship(
        "CIRelationship",
        foreign_keys="CIRelationship.target_ci_id",
        back_populates="target_ci",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_ci_source_active", "source_system", "is_active"),
        UniqueConstraint("source_system", "source_id", name="uq_ci_source_system_source_id"),
        Index("ix_ci_source_system_type_status", "source_system", "ci_type", "status"),
        Index("ix_ci_source_system_created", "source_system", "created_at"),
        Index("ix_ci_health_tier", "health_tier"),
        Index("ix_ci_ip_address", "ip_address"),
        Index("ix_ci_vendor", "vendor"),
        Index("ix_ci_serial_number", "serial_number"),
        Index("ix_ci_name", "name"),
        Index("ix_ci_source_id", "source_id"),
        Index("ix_ci_ci_type", "ci_type"),
        Index("ix_ci_status", "status"),
        Index("ix_ci_location", "location"),
        Index("ix_ci_last_sync_time", "last_sync_time"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict; ORM instances must never leak past the repository layer."""
        return {
            "id": str(self.id),
            "is_active": self.is_active,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "source_id": self.source_id,
            "source_system": self.source_system,
            "name": self.name,
            "ci_type": self.ci_type,
            "status": self.status,
            "health_tier": self.health_tier,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "vendor": self.vendor,
            "model": self.model,
            "serial_number": self.serial_number,
            "operating_system": self.operating_system,
            "location": self.location,
            "attributes": self.attributes or {},
            "last_sync_time": self.last_sync_time.isoformat() if self.last_sync_time else None,
            "state_hash": self.state_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CIRelationship(Base, UUIDPrimaryKeyMixin):
    """Directed dependency or topology edge between two Configuration Items."""

    __tablename__ = "ci_relationships"

    source_ci_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_ci_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)  # "located_at", "depends_on", etc.
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    source_ci: Mapped["ConfigurationItem"] = relationship(
        "ConfigurationItem",
        foreign_keys=[source_ci_id],
        back_populates="outgoing_relationships",
    )
    target_ci: Mapped["ConfigurationItem"] = relationship(
        "ConfigurationItem",
        foreign_keys=[target_ci_id],
        back_populates="incoming_relationships",
    )

    __table_args__ = (
        Index("ix_ci_rel_source_target", "source_ci_id", "target_ci_id"),
        Index("ix_ci_rel_type", "relationship_type"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict; ORM instances must never leak past the repository layer."""
        return {
            "id": str(self.id),
            "source_ci_id": str(self.source_ci_id),
            "target_ci_id": str(self.target_ci_id),
            "relationship_type": self.relationship_type,
            "attributes": self.attributes or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
