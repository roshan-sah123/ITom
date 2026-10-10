"""Small deterministic records for production models, not alternative implementations."""
from datetime import datetime, timezone
from app.models.ci import ConfigurationItem
from app.models.sync import SyncRun


def make_ci(source_system, name, status, health_tier, ci_type="Server", vendor="Dell", location=None, **kwargs):
    values = dict(source_system=source_system, source_id=f"{source_system}-{name}",
                  name=name, status=status, health_tier=health_tier, ci_type=ci_type,
                  vendor=vendor, location=location, attributes={},
                  last_sync_time=datetime.now(timezone.utc))
    values.update(kwargs)
    return ConfigurationItem(**values)


def make_run(source, status="SUCCESS", at=None, **kwargs):
    at = at or datetime.now(timezone.utc)
    values = dict(source_system=source, status=status, started_at=at, completed_at=at)
    values.update(kwargs)
    return SyncRun(**values)
