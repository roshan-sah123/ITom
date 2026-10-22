"""Exact device names allow researched exceptions to a shared naming prefix."""
from app.services.location_service import LocationResolver, LocationService
import pytest


def rule(key, target, approval='PENDING'):
    return dict(id=key, source_system='INTUNE', match_key=key,
                location_id=target, revision='research-v1', approval_status=approval)


def test_exact_name_overrides_prefix_without_matching_another_device():
    resolver = LocationResolver([
        rule('LP-AZ-', 'default', 'APPROVED'),
        rule('NAME:LP-AZ-12345', 'chennai'),
    ], {})
    result = resolver.resolve('INTUNE', ' lp-az-12345 ')
    assert result['location_id'] == 'chennai'
    assert result['resolution'] == 'review'
    assert result['location_rule_id'] == 'NAME:LP-AZ-12345'
    assert resolver.resolve('INTUNE', 'LP-AZ-123456')['location_id'] == 'default'
    assert resolver.resolve('INTUNE', 'LP-AZ-1234')['location_id'] == 'default'


def test_rejected_exact_rule_does_not_fall_back_to_approved_prefix():
    resolver = LocationResolver([
        rule('LP-AZ-', 'default', 'APPROVED'),
        rule('NAME:LP-AZ-12345', 'chennai', 'REJECTED'),
    ], {})
    result = resolver.resolve('INTUNE', 'LP-AZ-12345')
    assert result['location_id'] is None
    assert result['resolution'] == 'unassigned'
    assert result['location_rule_id'] == 'NAME:LP-AZ-12345'


@pytest.mark.asyncio
async def test_empty_exact_name_rule_is_rejected(session):
    with pytest.raises(ValueError, match='exact device name'):
        await LocationService(session).install_rules([
            dict(source_system='INTUNE', match_key='NAME: ', location='Chennai')])


@pytest.mark.asyncio
async def test_backfill_keeps_exact_research_pending_and_other_devices_unassigned(session):
    from tests.factories import make_ci

    service = LocationService(session)
    await service.install_rules([
        dict(source_system='INTUNE', match_key='LP-AZ-', location=None),
        dict(source_system='INTUNE', match_key=' name: lp-az-12345 ', location='Chennai'),
    ])
    researched = make_ci('INTUNE', 'LP-AZ-12345', 'Compliant', 'High')
    unknown = make_ci('INTUNE', 'LP-AZ-123456', 'Compliant', 'High')
    session.add_all([researched, unknown])
    await session.flush()
    counts = await service.backfill(source_system='INTUNE', bootstrap=False)
    assert counts['INTUNE:review'] == 1
    assert counts['INTUNE:unassigned'] == 1
    assert researched.location_id is not None
    assert researched.location_resolution == 'review'
    assert unknown.location_id is None
    assert researched.status == unknown.status == 'Compliant'
    assert (await service.backfill(source_system='INTUNE', bootstrap=False)).get('changed_assignments', 0) == 0
