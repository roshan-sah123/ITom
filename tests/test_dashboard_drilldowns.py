"""Dashboard drill-down populations match the summary's evidence policy."""
from tests.factories import make_ci


async def test_resource_pressure_filter_matches_summary_before_pagination(session, api_client):
    session.add_all([
        make_ci('SOLARWINDS', f'HOT-{i:02}', 'Up', 'Medium',
                attributes={'node_category':'Server', 'cpu_load':75, 'memory_used':None})
        for i in range(12)
    ] + [
        make_ci('SOLARWINDS', 'MEMORY-HOT', 'Up', 'Medium', attributes={'memory_used':80}),
        make_ci('SOLARWINDS', 'NORMAL', 'Up', 'High', attributes={'cpu_load':10, 'memory_used':20}),
        make_ci('SOLARWINDS', 'INVALID', 'Up', 'High', attributes={'cpu_load':101, 'memory_used':'80%'}),
        make_ci('SOLARWINDS', 'MISSING', 'Up', 'Medium', attributes={}),
        make_ci('SOLARWINDS', 'RETIRED', 'Up', 'Low', is_active=False, attributes={'cpu_load':99}),
        make_ci('INTUNE', 'OTHER-SOURCE', 'Compliant', 'High', attributes={'cpu_load':99}),
    ])
    await session.commit()
    summary=(await api_client.get('/api/v1/solarwinds/summary')).json()
    first=(await api_client.get('/api/v1/solarwinds/nodes?resource_pressure=true&page_size=10')).json()
    second=(await api_client.get('/api/v1/solarwinds/nodes?resource_pressure=true&page_size=10&page=2')).json()
    assert first['total'] == summary['decision_metrics']['resource_pressure']['numerator'] == 13
    assert len(first['items']) == 10 and len(second['items']) == 3
    assert {row['name'] for row in first['items']+second['items']} == {f'HOT-{i:02}' for i in range(12)} | {'MEMORY-HOT'}
    filtered=(await api_client.get('/api/v1/solarwinds/nodes?resource_pressure=true&category=Server&search=HOT-')).json()
    assert filtered['total'] == 12


async def test_intune_os_chart_filter_matches_os_distribution(session, api_client):
    session.add_all([
        make_ci('INTUNE', 'MAC', 'Compliant', 'High', ci_type='macOS'),
        make_ci('INTUNE', 'OTHER-MAC-FAMILY', 'Compliant', 'High', ci_type='macOS Other'),
        make_ci('INTUNE', 'WINDOWS', 'NonCompliant', 'Low', ci_type='Windows'),
        make_ci('SOLARWINDS', 'SERVER', 'Up', 'High', ci_type='macOS'),
    ])
    await session.commit()
    summary=(await api_client.get('/api/v1/intune/summary')).json()
    data=(await api_client.get('/api/v1/intune/devices?ci_type=macOS')).json()
    assert data['total'] == summary['os_distribution']['macOS'] == 1
    assert data['items'][0]['name']=='MAC'


async def test_source_breakdown_is_derived_from_active_records(session, api_client):
    session.add_all([
        make_ci('INTUNE', 'A', 'Compliant', 'High'),
        make_ci('SOLARWINDS', 'B', 'Up', 'High'),
        make_ci('OTHER', 'C', 'Unknown', 'Medium'),
        make_ci('RETIRED-SOURCE', 'D', 'Unknown', 'Medium', is_active=False),
    ])
    await session.commit()
    summary=(await api_client.get('/api/v1/cmdb/summary')).json()
    assert summary['source_breakdown'] == {'INTUNE':1,'SOLARWINDS':1,'OTHER':1}
    assert sum(summary['source_breakdown'].values())==summary['total_cis']==3
