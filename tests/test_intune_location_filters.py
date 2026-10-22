"""Intune tiles use exact source populations and the existing score policy."""
from datetime import datetime, timedelta, timezone
import pytest
from app.models.location import Location
from tests.factories import make_ci, make_run


@pytest.fixture
async def intune_location_inventory(session):
    session.add(Location(id='site',name='Site',level='city'));await session.flush()
    now=datetime.now(timezone.utc)
    for i in range(25):
        session.add(make_ci('INTUNE',f'Device {i:02}','Compliant' if i<20 else 'NonCompliant' if i<24 else 'Unknown','High',
            location_id='site',location_resolution='mapped',attributes={'last_sync_date_time':
                (now-timedelta(days=0 if i<22 else 10)).isoformat()} if i<24 else {}))
    session.add(make_ci('SOLARWINDS','Not an endpoint','Up','High',location_id='site',location_resolution='mapped'))
    session.add(make_run('INTUNE'));await session.commit()


@pytest.mark.parametrize('issue,count',[('compliant',20),('noncompliant',4),('recent_checkins',22),('old_checkins',2),('invalid_checkins',1)])
async def test_tile_filters_reconcile_before_pagination(api_client,intune_location_inventory,issue,count):
    before=(await api_client.get('/api/v1/locations/site/score')).json()['data']
    response=await api_client.get(f'/api/v1/locations/site/devices?source=INTUNE&issue={issue}&page_size=10')
    assert response.status_code==200
    data=response.json()['data']
    assert data['total']==count and len(data['items'])==min(10,count)
    assert all(ci['source_system']=='INTUNE' for ci in data['items'])
    assert before['issues'][issue]==count
    after=(await api_client.get('/api/v1/locations/site/score')).json()['data']
    assert after['scores']['endpoints']==before['scores']['endpoints']
    assert before['scores']['endpoints']['value']==83.1
    if issue=='compliant':
        second=(await api_client.get('/api/v1/locations/site/devices?source=INTUNE&issue=compliant&page_size=10&page=2')).json()['data']
        assert len(second['items'])==10
        assert {ci['id'] for ci in second['items']}.isdisjoint(ci['id'] for ci in data['items'])
