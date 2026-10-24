"""Business categories must agree across summaries and filtered inventory."""
from types import SimpleNamespace

from tests.factories import make_ci


async def test_source_categories_override_vendor_models_and_reconcile_all_views(session, api_client):
    records = [
        make_ci('SOLARWINDS', 'server-on-cisco', 'Critical', 'Low', vendor='Cisco', ci_type='Switch',
                attributes={'node_category':'Server','node_type':'Virtual Machine','cpu_load':90}),
        make_ci('SOLARWINDS', 'network-on-other', 'Up', 'High', vendor='Other', ci_type='Unknown',
                attributes={'node_category':'Network','node_type':'Firewall','cpu_load':0,'memory_used':0}),
        make_ci('SOLARWINDS', 'cloud-server', 'Unmanaged', 'Medium',
                attributes={'node_category':'Cloud','node_type':'Server'}),
        make_ci('SOLARWINDS', 'new-domain', 'Unknown', 'Medium',
                attributes={'node_category':'New <domain>','node_type':'New type'}),
        make_ci('SOLARWINDS', 'no-category', 'Down', 'Low', attributes={}),
        make_ci('SOLARWINDS', 'blank-category', 'Shutdown', 'Medium', attributes={'node_category':'  '}),
        make_ci('SOLARWINDS', 'retired-network', 'Up', 'High', is_active=False,
                attributes={'node_category':'Network'}),
        make_ci('INTUNE', 'endpoint', 'Compliant', 'High', attributes={'node_category':'Network'}),
    ]
    session.add_all(records)
    await session.commit()
    summary = (await api_client.get('/api/v1/solarwinds/summary')).json()
    metrics = summary['metrics']
    assert metrics['server_nodes_count'] == 1
    assert metrics['network_devices_count'] == 1
    assert metrics['unclassified_nodes_count'] == 2
    assert metrics['other_category_nodes_count'] == 2
    categories = summary['source_categories']
    assert sum(row['count'] for row in categories) == metrics['total_nodes'] == 6
    for row in categories:
        params = {'category':row['value']} if row['value'] is not None else {'category_missing':True}
        data = (await api_client.get('/api/v1/solarwinds/nodes',params=params)).json()
        assert data['total'] == row['count']
        assert sum(row['status_counts'].values()) == row['count']
    assert next(row for row in categories if row['value'] is None)['status_counts'] == {'Down':1,'Shutdown':1}
    assert (await api_client.get('/api/v1/solarwinds/network-devices')).json()['total'] == 1
    cmdb = (await api_client.get('/api/v1/cmdb/summary')).json()
    assert (cmdb['total_servers'],cmdb['total_network_devices'],cmdb['total_unclassified'],cmdb['total_other_categories']) == (1,1,2,2)
    server = next(row for row in categories if row['value']=='Server')
    assert server['cpu_count'] == 1 and server['memory_count'] == 0
    assert server['resource_pressure_count'] == 1
    network = next(row for row in categories if row['value']=='Network')
    assert network['cpu_count'] == network['memory_count'] == network['both_resources_count'] == 1
    assert network['resource_pressure_count'] == 0  # Real zero readings remain evidence.
    assert summary['source_types'] == ['Firewall','New type','Server','Virtual Machine']
    assert summary['top_source_servers'][0]['name'] == 'server-on-cisco'
    assert summary['top_saturated_servers'] == summary['top_source_servers']


async def test_category_type_status_filters_apply_before_pagination(session, api_client):
    for index in range(13):
        session.add(make_ci('SOLARWINDS',f'wan-{index:02}', 'Down' if index<11 else 'Up','Low',
                           location='Pune', attributes={'node_category':'Telecom','node_type':'MPLS'}))
    session.add(make_ci('SOLARWINDS','other','Down','Low',attributes={'node_category':'Server','node_type':'MPLS'}))
    await session.commit()
    params=dict(category='Telecom', source_type='MPLS', status='Down',location='Pune',page_size=10,page=2)
    data=(await api_client.get('/api/v1/solarwinds/nodes',params=params)).json()
    assert data['total']==11 and len(data['items'])==1
    assert data['items'][0]['source_category']=='Telecom'


def test_group_and_summary_share_source_category_buckets():
    from app.repositories.solarwinds_categories import category_counts, category_evidence
    rows=[SimpleNamespace(category='Telecom',status='Up',attributes={}),
          SimpleNamespace(category=None,status='Unknown',attributes={}),
          SimpleNamespace(category=' ',status='Down',attributes={})]
    assert category_counts(rows)['categories'] == [
        {'value':'Telecom','name':'Telecom','count':1},
        {'value':None,'name':'Unclassified','count':2}]
    assert [(r['value'],r['count']) for r in category_evidence(rows)] == [('Telecom',1),(None,2)]
