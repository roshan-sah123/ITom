"""Native classifications, explicit cross-source links and shared score policy."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.ci import ConfigurationItem
from app.models.location import Location
from app.services.telemetry_sources import normalize_solarwinds_node
from tests.factories import make_ci, make_run
from tests.test_solarwinds_groups import GroupClient, group, member, ingest


def native_client():
    client = GroupClient()
    for node, category, type in zip(client.nodes, ['Server', 'Network', 'Telecom', None], ['Windows Server', 'Access Switch', 'WAN', None]):
        node.update(NodeCategory=category, NodeType=type)
    return client


def test_native_tags_are_preserved_without_replacing_hardware():
    row = normalize_solarwinds_node(dict(NodeID=1, Caption='n', MachineType='VMware ESX',
                                         NodeCategory=' Cloud ', NodeType='Virtual Machine', Status=1))
    assert row['attributes']['node_category'] == ' Cloud '
    assert row['attributes']['node_type'] == 'Virtual Machine'
    assert row['ci_type'] == 'VMware ESX'


async def test_source_server_triage_never_substitutes_hardware_guesses(session, api_client):
    client=native_client()
    client.nodes[0].update(CPULoad=90,MachineType='Unusual hardware')
    client.nodes[1].update(CPULoad=99,MachineType='Windows Server')
    await ingest(session,client)
    data=(await api_client.get('/api/v1/solarwinds/summary')).json()
    assert [row['name'] for row in data['top_source_servers']]==['Device 1']


async def test_source_category_charts_report_health_and_status_for_same_nodes(session, api_client):
    client = native_client()
    client.nodes[0]['Status'] = 2
    await ingest(session, client)
    data = (await api_client.get('/api/v1/solarwinds/summary')).json()
    server = next(row for row in data['source_categories'] if row['value'] == 'Server')
    assert sum(server['health_counts'].values()) == server['count'] == 1
    assert sum(server['status_counts'].values()) == 1


async def test_overview_reconciles_all_inventory_shared_nodes_and_unknowns(session, api_client):
    client = native_client()
    client.members += [member(13, 11, 'Orion.Groups')]
    await ingest(session, client)
    response = await api_client.get('/api/v1/solarwinds/groups/overview')
    assert response.status_code == 200
    data = response.json()['data']
    assert data['fleet']['total_devices'] == 4
    assert data['fleet']['grouped_devices'] == 2
    assert data['fleet']['ungrouped_devices'] == 2
    assert sum(c['count'] for c in data['fleet']['categories']) == 4
    assert {c['value'] for c in data['fleet']['categories']} == {'Server', 'Network', 'Telecom', None}
    root = next(item for item in data['items'] if item['group']['group_id'] == 10)
    assert root['total_devices'] == 2 and root['server_count'] == root['network_count'] == 1
    assert root['site_score']['value'] == 100 and root['site_score']['status'] == 'healthy'
    assert root['group']['status'] == 'Critical'  # source rollup is independent of the score
    devices = (await api_client.get('/api/v1/solarwinds/groups/10/devices?category=Network')).json()['data']
    assert devices['total'] == 1 and devices['items'][0]['source_category'] == 'Network'
    full = (await api_client.get('/api/v1/solarwinds/nodes?category=Telecom')).json()
    assert full['total'] == 1 and full['items'][0]['source_type'] == 'WAN'
    typed = (await api_client.get('/api/v1/solarwinds/nodes?source_type=Access+Switch')).json()
    assert typed['total'] == 1 and typed['items'][0]['source_category'] == 'Network'
    typed_group = (await api_client.get('/api/v1/solarwinds/groups/10/devices?source_type=Access+Switch')).json()['data']
    assert typed_group['total'] == 1


async def test_outside_regular_groups_reconciles_and_filters_without_assignments(session, api_client):
    client = native_client()
    client.members += [member(13, 11, 'Orion.Groups')]
    await ingest(session, client)
    base = '/api/v1/solarwinds/groups/ungrouped/devices'
    response = await api_client.get(base)
    assert response.status_code == 200
    data = response.json()['data']
    assert data['group'] is None
    assert data['scope'] == 'outside_regular_groups'
    assert data['total'] == 2
    assert {row['source_id'] for row in data['items']} == {'SW-NODE-3', 'SW-NODE-4'}
    overview = (await api_client.get('/api/v1/solarwinds/groups/overview')).json()['data']
    assert data['total'] == overview['fleet']['ungrouped_devices']
    assert data['snapshot_id'] == overview['snapshot_id']
    filtered = (await api_client.get(base + '?search=Device+3')).json()['data']
    assert filtered['total'] == 1 and filtered['items'][0]['name'] == 'Device 3'
    assert (await api_client.get(base + '?category=Telecom')).json()['data']['total'] == 1
    assert (await api_client.get(base + '?search=%25')).json()['data']['total'] == 0
    assert (await api_client.get(base + '?page_size=3')).status_code == 422
    assert (await api_client.get(base + '?page=0')).status_code == 422
    assert (await api_client.post(base)).status_code == 405
    assert (await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']['total_devices'] == 2
    client.nodes.extend(dict(NodeID=node_id, Caption=f'Device {node_id}', Status=1) for node_id in range(5, 17))
    await ingest(session, client)
    first = (await api_client.get(base + '?page_size=10')).json()['data']
    second = (await api_client.get(base + '?page_size=10&page=2')).json()['data']
    assert first['total'] == second['total'] == 14
    assert first['total_pages'] == second['total_pages'] == 2
    assert len(first['items']) == 10 and len(second['items']) == 4
    assert len({row['id'] for row in first['items'] + second['items']}) == 14


@pytest.mark.parametrize('up,other,state,score', [(90,3,'healthy',90), (89,3,'warning',89),
    (75,3,'warning',75),(74,3,'critical',74),(99,2,'warning',99),
    (99,9,'healthy',100),(95,0,'healthy',95),(94,0,'unavailable',None)])
async def test_native_group_score_boundaries_and_field_coverage(session, api_client, up, other, state, score):
    client=native_client()
    client.nodes=[dict(NodeID=i,Caption=f'Node {i}',Status=1 if i<=up else other) for i in range(1,101)]
    client.members=[member(10,i) for i in range(1,101)]
    await ingest(session,client)
    data=(await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']
    assert data['site_score']['value']==score and data['site_score']['status']==state


async def test_stale_failed_empty_and_batch_query_count(session, api_client, db_engine):
    from datetime import timedelta
    from sqlalchemy import event, update
    from app.models.sync import SyncRun
    await ingest(session,native_client())
    empty=(await api_client.get('/api/v1/solarwinds/groups/12/summary')).json()['data']
    assert empty['site_score']['status']=='unavailable'
    statements=[]
    def record(*args): statements.append(args[2])
    event.listen(db_engine.sync_engine,'before_cursor_execute',record)
    try:
        await api_client.get('/api/v1/solarwinds/groups/overview')
        before=len(statements)
        from app.models.solarwinds_group import SolarWindsGroup
        session.add_all([SolarWindsGroup(group_id=i,name=f'Group {i}',status_code=1,status='Up') for i in range(200,230)])
        await session.commit();statements.clear()
        await api_client.get('/api/v1/solarwinds/groups/overview')
        assert len(statements)==before  # constant SQL count as locations grow
    finally:
        event.remove(db_engine.sync_engine,'before_cursor_execute',record)
    session.add(make_run('SOLARWINDS','FAILED'));await session.commit()
    failed=(await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']
    assert failed['site_score']['status']=='warning' and failed['site_score']['value']==100
    await session.execute(update(SyncRun).where(SyncRun.status=='SUCCESS').values(completed_at=datetime.now(timezone.utc)-timedelta(days=7)))
    await session.commit()
    stale=(await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']
    assert stale['site_score']['status']=='unavailable' and 'stale' in stale['site_score']['reason']


async def test_combined_requires_explicit_approval_not_device_aliases(session, api_client):
    await ingest(session, native_client())
    data = (await api_client.get('/api/v1/solarwinds/groups/10/summary?score_mode=combined')).json()['data']
    assert data['site_score']['value'] is None
    assert data['mapping']['status'] == 'UNMAPPED'
    assert 'approved' in data['site_score']['reason'].lower()
    assert (await api_client.get('/api/v1/solarwinds/groups/10/summary?score_mode=bad')).status_code == 422


async def test_approved_combined_formula_survives_rename_but_not_removal(session, api_client):
    from app.services.group_location_service import GroupLocationService
    client = native_client(); await ingest(session, client)
    session.add(Location(id='approved-site', name='Approved site', level='city'))
    await session.flush()
    now = datetime.now(timezone.utc).isoformat()
    session.add_all([make_ci('INTUNE', 'e1', 'Compliant', 'High', location_id='approved-site',
                            location_resolution='mapped', attributes={'last_sync_date_time':now}),
                     make_ci('INTUNE', 'e2', 'NonCompliant', 'Low', location_id='approved-site',
                            location_resolution='mapped', attributes={'last_sync_date_time':now}), make_run('INTUNE')])
    await session.commit()
    await GroupLocationService(session).approve(10, 'approved-site', 'Test owner', 'Verified site identity')
    await session.commit()
    data = (await api_client.get('/api/v1/solarwinds/groups/10/summary?score_mode=combined')).json()['data']
    assert data['site_score']['value'] == 80  # .4*50 + .35*100 + .25*100
    assert data['site_score']['status'] == 'critical'  # component below 75 retains the existing guardrail
    assert data['intune_endpoints'] == 2
    child = (await api_client.get('/api/v1/solarwinds/groups/11/summary?score_mode=combined')).json()['data']
    assert child['mapping']['status'] == 'UNMAPPED'  # never inherit a parent's endpoint population
    client.groups[0]['Name'] = 'Renamed, same source ID'
    await ingest(session, client)
    data = (await api_client.get('/api/v1/solarwinds/groups/10/summary?score_mode=combined')).json()['data']
    assert data['mapping']['status'] == 'APPROVED' and data['site_score']['value'] == 80
    client.groups = [g for g in client.groups if g['ContainerID'] != 10]
    client.members = [m for m in client.members if m['ContainerID'] != 10]
    await ingest(session, client)
    assert (await api_client.get('/api/v1/solarwinds/groups/10/summary')).status_code == 404
    from app.models.solarwinds_group import SolarWindsGroupLocation
    assert (await session.get(SolarWindsGroupLocation, 10)).approval_status == 'REVIEW'
    client.groups.append(group(10, 'Returned'))
    await ingest(session, client)
    data = (await api_client.get('/api/v1/solarwinds/groups/10/summary?score_mode=combined')).json()['data']
    assert data['site_score']['value'] is None


async def test_link_validation_and_inventory_filters_do_not_change_site_score(session, api_client):
    from app.services.group_location_service import GroupLocationService
    await ingest(session, native_client())
    session.add(Location(id='site', name='Site', level='city')); await session.commit()
    service = GroupLocationService(session)
    for args in [(11,'site','Owner','Evidence'), (10,'missing','Owner','Evidence'), (10,'site','','')]:
        with pytest.raises(ValueError): await service.approve(*args)
    source = (await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']
    await api_client.get('/api/v1/solarwinds/groups/10/devices?category=Server&status=Down')
    assert (await api_client.get('/api/v1/solarwinds/groups/10/summary')).json()['data']['site_score'] == source['site_score']
