"""Source hierarchy contracts, isolated from live telemetry and developer data."""
from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.models.ci import ConfigurationItem
from app.models.sync import SyncRun
from app.services.sync_service import SyncService
from app.services.telemetry_sources import SolarWindsSource


def group(id, name, owner='Core'):
    return dict(ContainerID=id, Name=name, Owner=owner, IsDeleted=False,
                Status=14, StatusDescription='Critical')


def member(parent, id, entity='Orion.Nodes'):
    return dict(ContainerID=parent, MemberPrimaryID=id, MemberEntityType=entity,
                Name=f'member-{id}', Status=1)


class GroupClient:
    def __init__(self):
        self.nodes = [dict(NodeID=i, Caption=f'Device {i}', Status=1,
                           City='Conflicting city') for i in range(1, 5)]
        self.groups = [group(10, 'BOCBA(Bolivia,Cochabamba-Encora)'),
                       group(11, 'BOCBANWK (Network Devices)'),
                       group(12, 'Empty  (Kraków, Poland)'),
                       group(13, 'BOCBANWK (Network Devices)'),
                       group(99, 'MAPS-private', 'Maps')]
        self.members = [member(10, 11, 'Orion.Groups'), member(10, 1),
                        member(11, 1), member(11, 2), member(99, 4)]

    def fetch_nodes(self):
        return deepcopy(self.nodes)

    def fetch_groups(self):
        return deepcopy(self.groups)

    def fetch_group_members(self):
        return deepcopy(self.members)


async def ingest(session, client):
    result = await SyncService(session).sync_single_source(SolarWindsSource(client))
    await session.commit()
    return result


async def test_group_api_exact_names_recursive_unique_nodes_and_empty_groups(session, api_client):
    assert (await ingest(session, GroupClient()))['status'] == 'SUCCESS'
    response = await api_client.get('/api/v1/solarwinds/groups')
    assert response.status_code == 200
    roots = response.json()['data']
    assert roots['data_available'] is True
    assert {x['group_id'] for x in roots['items']} == {10, 12, 13}
    assert next(x['name'] for x in roots['items'] if x['group_id'] == 12) == 'Empty  (Kraków, Poland)'
    root = next(x for x in roots['items'] if x['group_id'] == 10)
    assert root['status'] == 'Critical' and root['status_code'] == 14
    direct = (await api_client.get('/api/v1/solarwinds/groups/10/members')).json()['data']
    assert {x['kind'] for x in direct['items']} == {'group', 'device'}
    devices = (await api_client.get('/api/v1/solarwinds/groups/10/devices?page_size=10')).json()['data']
    assert devices['total'] == 2
    assert {x['source_id'] for x in devices['items']} == {'SW-NODE-1', 'SW-NODE-2'}
    assert (await api_client.get('/api/v1/solarwinds/groups/12/devices')).json()['data']['total'] == 0
    assert (await api_client.get('/api/v1/solarwinds/groups/999/devices')).status_code == 404
    assert await session.scalar(select(func.count()).select_from(ConfigurationItem)) == 4


async def test_filters_before_pagination_and_unknown_status(session, api_client):
    client = GroupClient()
    client.nodes[1]['Status'] = 14
    await ingest(session, client)
    base = '/api/v1/solarwinds/groups/10/devices'
    for query in ['search=Device+2', 'status=Critical']:
        data = (await api_client.get(f'{base}?{query}&page_size=10')).json()['data']
        assert data['total'] == 1 and data['items'][0]['name'] == 'Device 2'
    assert (await api_client.get(base + '?search=%00')).json()['data']['total'] == 0
    assert (await api_client.get(base + '?page_size=3')).status_code == 422
    assert (await api_client.get(base + '?page=0')).status_code == 422


@pytest.mark.parametrize('failure', ['cycle', 'missing_group', 'missing_node', 'missing_parent', 'fetch_error', 'bad_id'])
async def test_invalid_group_snapshot_preserves_inventory_groups_and_success(session, api_client, failure):
    client = GroupClient()
    await ingest(session, client)
    client.nodes[0]['Caption'] = 'Must roll back'
    if failure == 'cycle':
        client.members.append(member(11, 10, 'Orion.Groups'))
    elif failure == 'missing_group':
        client.members.append(member(10, 999, 'Orion.Groups'))
    elif failure == 'missing_node':
        client.members.append(member(10, 999))
    elif failure == 'missing_parent':
        client.members.append(member(999, 1))
    elif failure == 'bad_id':
        client.groups[0]['ContainerID'] = True
    else:
        def fail():
            raise RuntimeError('offline')
        client.fetch_group_members = fail
    result = await ingest(session, client)
    assert result['status'] == 'FAILED'
    ci = await session.scalar(select(ConfigurationItem).where(ConfigurationItem.source_id == 'SW-NODE-1'))
    assert ci.name == 'Device 1'
    data = (await api_client.get('/api/v1/solarwinds/groups/10/devices')).json()['data']
    assert data['total'] == 2
    assert await session.scalar(select(func.count()).select_from(SyncRun).where(SyncRun.status == 'SUCCESS')) == 1


async def test_rename_removal_duplicate_edges_and_shared_descendants(session, api_client):
    client = GroupClient()
    client.members += [member(13, 11, 'Orion.Groups'), member(11, 2)]
    await ingest(session, client)
    assert (await api_client.get('/api/v1/solarwinds/groups/13/devices')).json()['data']['total'] == 2
    client.groups[0]['Name'] = ' Renamed  <exact> '
    client.members = [member(10, 2)]
    client.groups = [client.groups[0]]
    assert (await ingest(session, client))['status'] == 'SUCCESS'
    data = (await api_client.get('/api/v1/solarwinds/groups')).json()['data']
    assert [x['name'] for x in data['items']] == [' Renamed  <exact> ']
    assert (await api_client.get('/api/v1/solarwinds/groups/10/devices')).json()['data']['total'] == 1
    assert (await api_client.get('/api/v1/solarwinds/groups/11/members')).status_code == 404


async def test_no_snapshot_is_unavailable_but_successful_empty_snapshot_is_empty(session, api_client):
    assert (await api_client.get('/api/v1/solarwinds/groups')).json()['data']['data_available'] is False
    client = GroupClient()
    client.groups = []; client.members = []
    assert (await ingest(session, client))['status'] == 'SUCCESS'
    data = (await api_client.get('/api/v1/solarwinds/groups')).json()['data']
    assert data['data_available'] is True and data['items'] == []


def test_validation_handles_deep_groups_without_python_recursion_limit():
    from app.services.solarwinds_group_service import validate_group_snapshot
    groups = [group(i, f'Deep {i}') for i in range(1, 1501)]
    members = [member(i, i + 1, 'Orion.Groups') for i in range(1, 1500)]
    members.append(member(1500, 1))
    snapshot = validate_group_snapshot(groups, members, {'SW-NODE-1'})
    assert len(snapshot.groups) == 1500


def test_paged_source_rejects_truncation_and_count_change(monkeypatch):
    from src.sync.solarwinds_client import SolarWindsClient, SolarWindsApiError
    client = SolarWindsClient()
    monkeypatch.setattr(client, 'query', lambda query: [{'Total': 2}] if 'COUNT(' in query else [group(1, 'A')])
    with pytest.raises(SolarWindsApiError):
        client.fetch_groups()


async def test_late_transaction_failure_rolls_back_groups_nodes_and_audit(session, api_client, monkeypatch):
    from app.services.location_service import LocationService
    client = GroupClient()
    await ingest(session, client)
    before = (await api_client.get('/api/v1/solarwinds/groups')).json()['data']
    client.groups[0]['Name'] = 'Must roll back'
    client.nodes[0]['Caption'] = 'Must roll back'
    client.members = []
    async def fail(*args):
        raise RuntimeError('Late failure after group persistence')
    monkeypatch.setattr(LocationService, 'capture', fail)
    assert (await ingest(session, client))['status'] == 'FAILED'
    after = (await api_client.get('/api/v1/solarwinds/groups')).json()['data']
    assert after['items'] == before['items']
    assert after['snapshot_id'] == before['snapshot_id']
    assert after['as_of'] == before['as_of']
    assert after['last_attempt_status'] == 'FAILED'
    ci = await session.scalar(select(ConfigurationItem).where(ConfigurationItem.source_id == 'SW-NODE-1'))
    assert ci.name == 'Device 1'


def test_paged_source_reconciles_ordered_pages_and_changing_counts(monkeypatch):
    from src.sync.solarwinds_client import SolarWindsClient, SolarWindsApiError
    client = SolarWindsClient()
    responses = iter([[{'Total': 3}], [{'NodeID': 1}, {'NodeID': 2}], [{'NodeID': 3}], [{'Total': 3}]])
    monkeypatch.setattr(client, 'query', lambda query: next(responses))
    assert client._fetch_complete_pages('NodeID', 'Orion.Nodes', ['NodeID'], page_size=2) == [
        {'NodeID': 1}, {'NodeID': 2}, {'NodeID': 3}]
    for responses in [iter([[{'Total': 1}], [{'NodeID': 1}], [{'Total': 2}]]),
                      iter([[{'Total': 2}], [{'NodeID': 2}, {'NodeID': 1}]])]:
        monkeypatch.setattr(client, 'query', lambda query: next(responses))
        with pytest.raises(SolarWindsApiError):
            client._fetch_complete_pages('NodeID', 'Orion.Nodes', ['NodeID'])


async def test_recursive_query_handles_deep_groups_and_filters_before_page(session, api_client):
    client = GroupClient()
    client.nodes = [dict(NodeID=i, Caption=f'Device {i:02}', Status=14 if i == 31 else 1) for i in range(1, 32)]
    client.groups = [group(i, f'Deep {i}') for i in range(1, 1201)]
    client.members = [member(i, i + 1, 'Orion.Groups') for i in range(1, 1200)]
    client.members += [member(1200, i) for i in range(1, 32)]
    assert (await ingest(session, client))['status'] == 'SUCCESS'
    base = '/api/v1/solarwinds/groups/1/devices'
    data = (await api_client.get(base + '?page_size=10&page=2')).json()['data']
    assert data['total'] == 31 and len(data['items']) == 10 and data['total_pages'] == 4
    data = (await api_client.get(base + '?page_size=10&status=Critical')).json()['data']
    assert data['total'] == 1 and data['items'][0]['name'] == 'Device 31'


async def test_database_outage_returns_safe_503(api_client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from app.repositories.solarwinds_group_repository import SolarWindsGroupRepository
    async def fail(*args):
        raise SQLAlchemyError('private database diagnostics')
    monkeypatch.setattr(SolarWindsGroupRepository, 'roots', fail)
    response = await api_client.get('/api/v1/solarwinds/groups')
    assert response.status_code == 503
    assert 'private' not in response.text
