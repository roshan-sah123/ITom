"""The endpoint inventory uses canonical reporting sites, before pagination."""
import pytest
from app.models.location import Location
from tests.factories import make_ci


@pytest.fixture
async def endpoint_location_inventory(session):
    session.add_all([Location(id='pune', name='Pune', level='city'),
                     Location(id='noida', name='Noida', level='city')])
    await session.flush()
    session.add_all([
        make_ci('INTUNE', f'PUNE-{i:02}', 'Compliant' if i < 10 else 'NonCompliant', 'High',
                location='Different raw location', location_id='pune',
                location_resolution='mapped' if i < 10 else 'review') for i in range(13)
    ] + [
        make_ci('INTUNE', 'NOIDA-01', 'Compliant', 'High', location_id='noida', location_resolution='mapped'),
        make_ci('INTUNE', 'UNKNOWN-01', 'Unknown', 'Medium', location='Raw office without a mapping'),
        make_ci('INTUNE', 'UNKNOWN-02', 'Unknown', 'Medium'),
        make_ci('INTUNE', 'RETIRED-PUNE', 'Compliant', 'High', location_id='pune', is_active=False),
        make_ci('SOLARWINDS', 'PUNE-SERVER', 'Up', 'High', location_id='pune'),
    ])
    await session.commit()


async def test_reporting_location_filter_and_total_apply_before_pagination(api_client, endpoint_location_inventory):
    first = await api_client.get('/api/v1/intune/devices?location_id=pune&page_size=10')
    assert first.status_code == 200
    page = first.json()
    assert page['total'] == 13
    assert len(page['items']) == 10
    assert {ci['canonical_location'] for ci in page['items']} == {'Pune'}
    assert {ci['location'] for ci in page['items']} == {'Different raw location'}
    assert all(ci['source_system'] == 'INTUNE' for ci in page['items'])
    second = (await api_client.get('/api/v1/intune/devices?location_id=pune&page_size=10&page=2')).json()
    assert len(second['items']) == 3 and second['total'] == 13
    assert {ci['id'] for ci in page['items']}.isdisjoint(ci['id'] for ci in second['items'])
    assert all(ci['location_resolution'] == 'review' for ci in second['items'])


async def test_unassigned_uses_canonical_membership_instead_of_raw_source_value(api_client, endpoint_location_inventory):
    data = (await api_client.get('/api/v1/intune/devices?location_id=unassigned')).json()
    assert data['total'] == 2
    assert {ci['name'] for ci in data['items']} == {'UNKNOWN-01', 'UNKNOWN-02'}
    assert all(ci['canonical_location'] is None for ci in data['items'])


async def test_location_combines_with_existing_filters_and_unknown_ids_match_nothing(api_client, endpoint_location_inventory):
    data = (await api_client.get('/api/v1/intune/devices?location_id=pune&status=NonCompliant&vendor=Dell&search=PUNE')).json()
    assert data['total'] == 3
    assert all(ci['canonical_location'] == 'Pune' and ci['location_resolution'] == 'review' for ci in data['items'])
    unknown = (await api_client.get('/api/v1/intune/devices?location_id=no-such-site')).json()
    assert unknown['total'] == 0 and unknown['items'] == []


async def test_unfiltered_inventory_includes_reporting_name_and_assignment_state(api_client, endpoint_location_inventory):
    data = (await api_client.get('/api/v1/intune/devices')).json()
    assert data['total'] == 16
    assert all('canonical_location' in ci and 'location_resolution' in ci for ci in data['items'])
