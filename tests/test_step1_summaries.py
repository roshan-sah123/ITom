"""STEP 1 VERIFICATION - the /summary endpoints must be computed from the database.

What these tests prove
----------------------
1. The Intune and SolarWinds summaries reflect whatever rows are actually in
   ``configuration_items`` - not a constant baked into the source.
2. When the data changes, the summary changes. (This is the property that was
   completely missing before: the old service returned the same numbers forever.)
3. An empty dataset raises EmptyDatasetError -> HTTP 503, rather than returning
   plausible placeholder figures.
4. None of the previously hardcoded fleet literals can appear for a dataset that
   does not genuinely contain them.

Run:
    python -m pytest tests/test_step1_summaries.py -v
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import history as _history_models  # noqa: F401  (registers tables)
from app.models import sync as _sync_models  # noqa: F401  (registers tables)
from app.models.base import Base
from app.models.ci import ConfigurationItem
from app.repositories.summary_repository import EmptyDatasetError, SummaryRepository

# The exact figures that used to be hardcoded in ci_service.py. If any of these
# shows up for a dataset that does not contain that many rows, we have regressed.
FORBIDDEN_LITERALS = {
    25987, 21589, 4398, 83.08, 37.4,
    1548, 1543, 1357, 150, 41,
    14210, 6120, 3450, 1890, 317,
}


def _ci(
    source_system: str,
    name: str,
    status: str,
    health_tier: str,
    ci_type: str = "Server",
    vendor: str = "Dell",
) -> ConfigurationItem:
    """Build a minimal, valid ConfigurationItem row."""
    now = datetime.now(timezone.utc)
    return ConfigurationItem(
        id=uuid.uuid4(),
        source_id=f"{source_system}-{name}",
        source_system=source_system,
        name=name,
        ci_type=ci_type,
        status=status,
        health_tier=health_tier,
        vendor=vendor,
        last_sync_time=now,
        state_hash="deadbeef",
        attributes={},
        created_at=now,
        updated_at=now,
    )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Isolated in-memory SQLite session with the full schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s

    await engine.dispose()


def _flatten_numbers(payload) -> list:
    """Collect every numeric value found anywhere in a nested payload."""
    found = []
    if isinstance(payload, dict):
        for value in payload.values():
            found.extend(_flatten_numbers(value))
    elif isinstance(payload, list):
        for value in payload:
            found.extend(_flatten_numbers(value))
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        found.append(payload)
    return found


# --------------------------------------------------------------------------- #
# 1. Intune summary is computed, not constant
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_intune_summary_reflects_actual_rows(session: AsyncSession):
    session.add_all([
        _ci("INTUNE", "LAP-001", "compliant", "High", ci_type="Windows"),
        _ci("INTUNE", "LAP-002", "compliant", "High", ci_type="Windows"),
        _ci("INTUNE", "LAP-003", "compliant", "High", ci_type="macOS", vendor="Apple"),
        _ci("INTUNE", "LAP-004", "noncompliant", "Low", ci_type="Windows"),
        _ci("INTUNE", "LAP-005", "unknown", "Medium", ci_type="Linux"),
    ])
    await session.flush()

    summary = await SummaryRepository(session).get_intune_summary()
    metrics = summary["metrics"]

    assert summary["data_source"] == "DATABASE"
    assert metrics["total_managed_devices"] == 5
    assert metrics["compliant_devices"] == 3
    assert metrics["noncompliant_devices"] == 1
    assert metrics["other_compliance"] == 1
    assert metrics["compliance_rate_pct"] == 60.0

    # Every device is accounted for in exactly one compliance bucket.
    assert (
        metrics["compliant_devices"]
        + metrics["noncompliant_devices"]
        + metrics["other_compliance"]
        == metrics["total_managed_devices"]
    )

    # OS distribution is derived from ci_type and reconciles to the total.
    assert summary["os_distribution"] == {"Windows": 3, "macOS": 1, "Linux": 1}
    assert sum(summary["os_distribution"].values()) == metrics["total_managed_devices"]


# --------------------------------------------------------------------------- #
# 2. The summary MOVES when the data moves - the core freshness property
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_summary_changes_when_underlying_data_changes(session: AsyncSession):
    repo = SummaryRepository(session)

    session.add_all([
        _ci("INTUNE", "D-1", "compliant", "High", ci_type="Windows"),
        _ci("INTUNE", "D-2", "compliant", "High", ci_type="Windows"),
    ])
    await session.flush()
    before = await repo.get_intune_summary()
    assert before["metrics"]["compliance_rate_pct"] == 100.0

    session.add_all([
        _ci("INTUNE", "D-3", "noncompliant", "Low", ci_type="Windows"),
        _ci("INTUNE", "D-4", "noncompliant", "Low", ci_type="Windows"),
    ])
    await session.flush()
    after = await repo.get_intune_summary()

    assert after["metrics"]["total_managed_devices"] == 4
    assert after["metrics"]["compliance_rate_pct"] == 50.0
    assert after["metrics"]["low_health_count"] == 2
    assert before["metrics"]["compliance_rate_pct"] != after["metrics"]["compliance_rate_pct"]


# --------------------------------------------------------------------------- #
# 3. SolarWinds availability, including the Low tier that never existed before
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_solarwinds_summary_includes_every_status(session: AsyncSession):
    session.add_all([
        _ci("SOLARWINDS", "SRV-1", "Up", "High"),
        _ci("SOLARWINDS", "SRV-2", "Up", "High"),
        _ci("SOLARWINDS", "SRV-3", "Warning", "Medium"),
        _ci("SOLARWINDS", "SRV-4", "Critical", "Low"),
        _ci("SOLARWINDS", "SRV-5", "Unmanaged", "Medium"),
        _ci("SOLARWINDS", "SRV-6", "Down", "Low"),
    ])
    await session.flush()

    summary = await SummaryRepository(session).get_solarwinds_summary()
    metrics = summary["metrics"]

    assert metrics["total_server_nodes"] == 6
    assert metrics["available_nodes"] == 2
    assert metrics["unavailable_nodes"] == 4
    assert metrics["availability_pct"] == 33.33

    # Critical and Unmanaged must survive as distinct statuses - they used to be
    # collapsed into "Down" by the ingestion mapping.
    assert summary["status_breakdown"]["Critical"] == 1
    assert summary["status_breakdown"]["Unmanaged"] == 1
    assert summary["status_breakdown"]["Down"] == 1

    # Frontend contract: charts consume normalized, lowercase status keys from
    # metrics. Keep the source-labelled status_breakdown above for detail and
    # backward compatibility, but do not make the UI translate it itself.
    assert metrics["status_counts"] == {
        "up": 2,
        "warning": 1,
        "critical": 1,
        "down": 1,
        "unmanaged_unknown": 1,
    }

    # The Low health tier must be reachable.
    assert metrics["low_health_count"] == 2


# --------------------------------------------------------------------------- #
# 4. Empty dataset fails loudly instead of inventing numbers
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_empty_dataset_raises_instead_of_returning_placeholders(session: AsyncSession):
    repo = SummaryRepository(session)

    with pytest.raises(EmptyDatasetError) as excinfo:
        await repo.get_intune_summary()
    assert excinfo.value.source_system == "INTUNE"

    with pytest.raises(EmptyDatasetError):
        await repo.get_solarwinds_summary()


@pytest.mark.asyncio
async def test_domains_are_isolated_from_each_other(session: AsyncSession):
    """SolarWinds rows must not leak into the Intune summary, or vice versa."""
    session.add_all([
        _ci("SOLARWINDS", "SRV-1", "Up", "High"),
        _ci("SOLARWINDS", "SRV-2", "Up", "High"),
    ])
    await session.flush()

    repo = SummaryRepository(session)
    assert (await repo.get_solarwinds_summary())["metrics"]["total_server_nodes"] == 2

    with pytest.raises(EmptyDatasetError):
        await repo.get_intune_summary()


# --------------------------------------------------------------------------- #
# 5. Regression guard - no resurrected hardcoded constants
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_no_hardcoded_fleet_literals_in_response(session: AsyncSession):
    session.add_all([
        _ci("INTUNE", "D-1", "compliant", "High", ci_type="Windows"),
        _ci("INTUNE", "D-2", "noncompliant", "Low", ci_type="Windows"),
        _ci("SOLARWINDS", "SRV-1", "Up", "High"),
    ])
    await session.flush()

    repo = SummaryRepository(session)
    for payload in (await repo.get_intune_summary(), await repo.get_solarwinds_summary()):
        for number in _flatten_numbers(payload):
            assert number not in FORBIDDEN_LITERALS, (
                f"Hardcoded fleet literal {number} reappeared in the "
                f"{payload['source_system']} summary for a 3-row dataset."
            )


def test_service_module_contains_no_fleet_literals():
    """Static guard: the service layer must not carry baked-in fleet figures."""
    import inspect

    from app.services import ci_service

    source = inspect.getsource(ci_service)
    for literal in ("25987", "21589", "83.08", "1357", "14210"):
        assert literal not in source, (
            f"Hardcoded literal {literal} is still present in ci_service.py"
        )
