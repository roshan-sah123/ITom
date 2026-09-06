"""Append-only time-series history model for CI status and metric changes."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, UUIDPrimaryKeyMixin, UUIDType

if TYPE_CHECKING:
    from app.models.ci import ConfigurationItem


class CIStatusHistory(Base, UUIDPrimaryKeyMixin):
    """Append-only historical status, health, and performance telemetry record."""

    __tablename__ = "ci_status_history"

    ci_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("configuration_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    previous_health_tier: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    cpu_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    storage_used_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    changed_attributes: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    ci: Mapped["ConfigurationItem"] = relationship(
        "ConfigurationItem",
        back_populates="status_history",
    )

    __table_args__ = (
        Index("ix_status_history_ci_recorded", "ci_id", "recorded_at"),
        Index("ix_status_history_recorded_at", "recorded_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-safe dict; ORM instances must never leak past the repository layer."""
        return {
            "id": str(self.id),
            "ci_id": str(self.ci_id),
            "status": self.status,
            "health_tier": self.health_tier,
            "previous_status": self.previous_status,
            "previous_health_tier": self.previous_health_tier,
            "cpu_utilization": self.cpu_utilization,
            "memory_utilization": self.memory_utilization,
            "storage_used_pct": self.storage_used_pct,
            "latency_ms": self.latency_ms,
            "changed_attributes": self.changed_attributes or {},
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }

