"""Exercise real CMDB constraints, retired scope, JSON and history persistence."""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.models.ci import ConfigurationItem
from app.models.history import CIStatusHistory
from app.repositories.ci_repository import CIRepository
from tests.factories import make_ci


async def test_same_source_identity_cannot_be_duplicated(session):
    session.add(make_ci("INTUNE", "same", "Compliant", "High"))
    await session.commit()
    session.add(make_ci("INTUNE", "same", "Noncompliant", "Low"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    assert (await session.execute(select(func.count()).select_from(ConfigurationItem))).scalar_one() == 1


async def test_source_identity_is_namespaced_and_json_roundtrips(session):
    ci = make_ci("INTUNE", "first", "Compliant", "High", source_id="42", attributes={"nested": {"serial": "A&B"}, "measurements": [None, 25.5]})
    session.add_all([ci, make_ci("SOLARWINDS", "second", "Up", "High", source_id="42")])
    await session.commit()
    session.expire_all()
    rows = (await session.execute(select(ConfigurationItem))).scalars().all()
    assert len(rows) == 2
    assert next(row for row in rows if row.source_system == "INTUNE").attributes == {"nested": {"serial": "A&B"}, "measurements": [None, 25.5]}


async def test_retired_scope_only_ingestion_can_find_retired_identity(session):
    session.add(make_ci("INTUNE", "retired", "Compliant", "High", is_active=False))
    await session.commit()
    assert (await session.execute(select(ConfigurationItem))).scalars().all() == []
    found = await CIRepository(session).get_by_source_key("INTUNE", "INTUNE-retired")
    assert found is not None and found.is_active is False


async def test_orphan_history_is_rejected_and_delete_cascades(session):
    session.add(CIStatusHistory(ci_id=uuid.uuid4(), status="Up", health_tier="High"))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
    ci = make_ci("SOLARWINDS", "node", "Up", "High")
    session.add(ci)
    await session.flush()
    session.add(CIStatusHistory(ci_id=ci.id, status="Up", health_tier="High"))
    await session.commit()
    await session.execute(delete(ConfigurationItem).where(ConfigurationItem.id == ci.id))
    await session.commit()
    assert (await session.execute(select(func.count()).select_from(CIStatusHistory))).scalar_one() == 0


async def test_inventory_database_failure_is_not_reported_as_zero_results():
    failing_session = AsyncMock()
    failing_session.execute.side_effect = RuntimeError("datastore unavailable")
    # An exception must propagate, so the API can report an unavailable datastore.
    with pytest.raises(RuntimeError, match="datastore unavailable"):
        await CIRepository(failing_session).get_cis_paginated()
