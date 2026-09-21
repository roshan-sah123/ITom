"""Persisted cache for Intune compliance-reason remediation worklists."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin


class IntuneComplianceReasonCache(Base, TimestampMixin):
    """One Intune setting summary and its optional cached affected-device worklist."""

    __tablename__ = "intune_compliance_reason_cache"

    summary_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    setting_name: Mapped[str] = mapped_column(String(512), nullable=False)
    platform: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    noncompliant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    devices: Mapped[List[Dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    catalog_refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    worklist_refreshed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def to_reason(self) -> Dict[str, Any]:
        """Return the cache entry in the remediation worklist contract."""
        return {
            "id": self.summary_id,
            "setting_name": self.setting_name,
            "platform": self.platform,
            "noncompliant_count": self.noncompliant_count,
            "error_count": self.error_count,
            "conflict_count": self.conflict_count,
            "affected_count": self.affected_count,
            "catalog_refreshed_at": self.catalog_refreshed_at.isoformat(),
            "worklist_cached": self.worklist_refreshed_at is not None,
            "cached_device_count": (
                len(self.devices or []) if self.worklist_refreshed_at else None
            ),
            "worklist_refreshed_at": (
                self.worklist_refreshed_at.isoformat()
                if self.worklist_refreshed_at
                else None
            ),
        }
