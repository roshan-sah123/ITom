from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.services.location_service import LocationResolver, LocationService
from app.models.location import Location, LocationMappingRule
from app.models.ci import ConfigurationItem
from tests.factories import make_ci, make_run
from app.services.sync_service import SyncService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.models.sync import SyncRun
from app.models.location import LocationScoreSnapshot
from sqlalchemy import func


@pytest.mark.parametrize('mode', ['endpoints', 'infrastructure', 'combined'])
@pytest.mark.parametrize('numerator,denominator,expected_status,display', [
    (2249,2500,'warning',90.0),
    (22499,30000,'critical',75.0),
    (9,10,'healthy',90.0),
    (3,4,'warning',75.0),
])
def test_score_thresholds_use_exact_ratios(mode,numerator,denominator,expected_status,display):
    now=datetime.now(timezone.utc)
    def record(source,status,recent=True):
        return SimpleNamespace(source_system=source,status=status,location_resolution='mapped',
                               location_revision=None,attributes={'last_sync_date_time':
                               (now-timedelta(days=0 if recent else 8)).isoformat()})
    records=[]
    if mode != 'infrastructure':
        records += [record('INTUNE','Compliant')]*numerator
        records += [record('INTUNE','NonCompliant',False)]*(denominator-numerator)
    if mode != 'endpoints':
        records += [record('SOLARWINDS','Up')]*numerator
        records += [record('SOLARWINDS','Warning')]*(denominator-numerator)
    fresh={'sources':{source:dict(status='FRESH',last_attempt_status='SUCCESS')
                      for source in ['INTUNE','SOLARWINDS']}}
    result=LocationService.score(SimpleNamespace(id='office',name='Office',level='office'),records,fresh,now)
    assert result['scores'][mode]['value']==display
    assert result['scores'][mode]['status']==expected_status


def test_low_component_cannot_be_rounded_above_red_floor():
    now=datetime.now(timezone.utc)
    fresh={'sources':{source:dict(status='FRESH',last_attempt_status='SUCCESS')
                      for source in ['INTUNE','SOLARWINDS']}}
    def record(status):
        return SimpleNamespace(source_system='SOLARWINDS',status=status,location_resolution='mapped',
                               location_revision=None,attributes={})
    endpoint=SimpleNamespace(source_system='INTUNE',status='Compliant',location_resolution='mapped',
                             location_revision=None,attributes={'last_sync_date_time':now.isoformat()})
    records=[endpoint]+[record('Up')]*22499+[record('Warning')]*7501
    result=LocationService.score(SimpleNamespace(id='office',name='Office',level='office'),records,fresh,now)
    assert result['components']['node_status']['value']==75.0
    assert result['scores']['combined']['value']==91.2
    assert result['scores']['combined']['status']=='critical'
    assert result['scores']['combined']['reason']=='A component is below 75%'


def test_longest_prefix_and_unknown():
    resolver = LocationResolver([
        dict(id='a', source_system='INTUNE', match_key='LPMNL', location_id='city', revision='v1'),
        dict(id='b', source_system='INTUNE', match_key='LPMNL-', location_id='office', revision='v1'),
    ], {})
    assert resolver.resolve('INTUNE', ' lpmnl-123 ')['location_id'] == 'office'
    assert resolver.resolve('INTUNE', 'LPMNL-')['location_id'] is None
    assert resolver.resolve('INTUNE', 'anything')['resolution'] == 'unassigned'


def test_conflicting_solarwinds_fields():
    resolver = LocationResolver([
        dict(id='a', source_system='SOLARWINDS', match_key='Bangalore-Encora', location_id='blr', revision='v1'),
        dict(id='b', source_system='SOLARWINDS', match_key='Encora-Pune', location_id='pun', revision='v1'),
    ], {'blr': 'Bengaluru / Encora', 'pun': 'Pune / Encora'})
    result = resolver.resolve('SOLARWINDS', 'node', 'Bangalore-Encora', {'city':'Bangalore-Encora', 'itsm_location':'Encora-Pune'})
    assert result['resolution'] == 'conflict'
    assert result['location_id'] is None


def test_solarwinds_placeholder_fallback_and_broad_country_agreement():
    resolver=LocationResolver([
        dict(id='empty',source_system='SOLARWINDS',match_key='NA',location_id=None,revision='v1',approval_status='PENDING'),
        dict(id='country',source_system='SOLARWINDS',match_key='Mexico',location_id='mx',revision='v1',approval_status='APPROVED'),
        dict(id='office',source_system='SOLARWINDS',match_key='Hermosillo',location_id='office',revision='v1',approval_status='APPROVED'),
    ],{'mx':'Mexico / Site unspecified','office':'Mexico / Hermosillo / Encora'})
    assert resolver.resolve('SOLARWINDS','node','NA',{'city':'NA','itsm_location':'Hermosillo'})['location_id']=='office'
    assert resolver.resolve('SOLARWINDS','node','Hermosillo',{'city':'Hermosillo','itsm_location':'Mexico'})['resolution']=='mapped'
    assert resolver.resolve('SOLARWINDS','node','Mexico',{'city':'Mexico','itsm_location':'Hermosillo'})['location_id']=='office'


@pytest.mark.asyncio
async def test_periodic_history_contains_observed_scores(api_client,session):
    session.add(Location(id='observed',name='Observed office',level='office'));await session.flush()
    session.add(make_ci('INTUNE','observed-device','Compliant','High',location_id='observed',location_resolution='mapped',attributes={'last_sync_date_time':datetime.now(timezone.utc).isoformat()}))
    run=make_run('INTUNE');session.add(run);await session.flush()
    await LocationService(session).capture(run.id);await session.commit()
    history=(await api_client.get('/api/v1/locations/observed/history')).json()['data']
    assert history['data_available'] and len(history['items'])==1
    assert history['items'][0]['data']['scores']['endpoints']['value']==100
    assert history['items'][0]['data']['scores']['combined']['value'] is None


@pytest.mark.asyncio
async def test_backfill_idempotent_preserves_telemetry(session):
    service = LocationService(session)
    await service.install_seed()
    ci = make_ci(source_system='INTUNE', name='LP-TZD-123', status='NonCompliant', health_tier='Low')
    session.add(ci)
    await session.flush()
    original_time = ci.last_sync_time
    await service.backfill()
    first = ci.location_id
    assert first and ci.status == 'NonCompliant' and ci.last_sync_time == original_time
    await service.backfill()
    assert ci.location_id == first


@pytest.mark.asyncio
async def test_score_counts_and_issue_selection(api_client, session):
    session.add(Location(id='test-office', name='Test office', level='office'))
    await session.flush()
    now = datetime.now(timezone.utc)
    for name, status, age in [('a','Compliant',1),('b','NonCompliant',8)]:
        ci = make_ci(source_system='INTUNE', name=name, status=status, health_tier='High',
                     attributes={'last_sync_date_time': (now-timedelta(days=age)).isoformat()})
        ci.location_id='test-office'; ci.location_resolution='mapped'
        session.add(ci)
    for name,status in [('up','Up'),('unmanaged','Unmanaged')]:
        ci=make_ci(source_system='SOLARWINDS',name=name,status=status,health_tier='High')
        ci.location_id='test-office';ci.location_resolution='mapped';session.add(ci)
    session.add_all([make_run('INTUNE',completed_at=now),make_run('SOLARWINDS',completed_at=now)])
    await session.commit()
    response=await api_client.get('/api/v1/locations/test-office/score')
    assert response.status_code==200
    score=response.json()['data']
    assert score['components']['compliance']['value']==50
    assert score['components']['node_status']['value']==100
    assert score['components']['recent_checkins']['value']==50
    assert score['scores']['combined']['value']==67.5
    response=await api_client.get('/api/v1/locations/test-office/devices?issue=noncompliant')
    assert response.json()['data']['total']==score['issues']['noncompliant']==1
    response=await api_client.get('/api/v1/locations/test-office/devices?issue=old_checkins')
    assert response.json()['data']['total']==score['issues']['old_checkins']==1


@pytest.mark.asyncio
async def test_missing_and_stale_are_not_healthy(api_client, session):
    session.add(Location(id='empty', name='Empty office', level='office'))
    await session.commit()
    response=await api_client.get('/api/v1/locations/empty/score')
    assert response.json()['data']['scores']['combined']['value'] is None
    assert response.json()['data']['scores']['combined']['status']=='unavailable'
    assert (await api_client.get('/api/v1/locations/missing/score')).status_code==404


@pytest.mark.asyncio
async def test_normalization_survives_unchanged_sync_and_mapping_revision(session):
    sync=SyncService(session)
    item=dict(external_id='source-one',name='LP-TZD-123',status='Compliant',health_tier='High',ci_type='Windows')
    await sync.ingest_telemetry_batch([item],'INTUNE')
    ci=(await session.scalars(select(ConfigurationItem))).one()
    first=ci.location_id
    assert first and ci.location_resolution=='mapped' and ci.location is None
    await sync.ingest_telemetry_batch([item],'INTUNE')
    assert ci.location_id==first
    await LocationService(session).install_rules([dict(source_system='INTUNE',match_key='LP-TZD-',location='Replacement office')])
    await sync.ingest_telemetry_batch([item],'INTUNE')
    assert ci.location_id!=first and ci.status=='Compliant'


@pytest.mark.asyncio
async def test_invalid_revision_does_not_remove_existing_rules(session):
    service=LocationService(session);await service.install_seed()
    before=(await session.scalars(select(LocationMappingRule))).all()
    with pytest.raises(ValueError):
        await service.install_rules([dict(source_system='INTUNE',match_key='LP-',location='One'),dict(source_system='INTUNE',match_key='lp-',location='Two')])
    after=(await session.scalars(select(LocationMappingRule))).all()
    assert len(after)==len(before) and all(r.enabled for r in after)


@pytest.mark.asyncio
async def test_stale_source_unmanaged_and_unknown_timestamp(api_client,session):
    session.add(Location(id='stale',name='Stale',level='city'));await session.flush()
    session.add(make_ci('INTUNE','old','Compliant','High',location_id='stale',attributes={}))
    session.add(make_ci('SOLARWINDS','unmanaged','Unmanaged','High',location_id='stale'))
    session.add_all([make_run('INTUNE',at=datetime.now(timezone.utc)-timedelta(hours=1)),make_run('SOLARWINDS')])
    await session.commit()
    data=(await api_client.get('/api/v1/locations/stale/score')).json()['data']
    assert data['scores']['endpoints']['value'] is None
    assert data['components']['node_status']['denominator']==0
    assert data['scores']['infrastructure']['value'] is None
    assert data['issues']['invalid_checkins']==1


@pytest.mark.asyncio
async def test_fresh_but_missing_required_fields_are_unavailable(api_client,session):
    session.add(Location(id='missing-fields',name='Missing fields',level='city'));await session.flush()
    session.add(make_ci('INTUNE','missing-date','Unknown','Medium',location_id='missing-fields',attributes={}))
    session.add(make_ci('SOLARWINDS','unknown-state','Unknown','Medium',location_id='missing-fields'))
    session.add_all([make_run('INTUNE'),make_run('SOLARWINDS')]);await session.commit()
    data=(await api_client.get('/api/v1/locations/missing-fields/score')).json()['data']
    assert all(c['value'] is None and c['coverage_pct']==0 for c in data['components'].values())
    assert all(score['value'] is None for score in data['scores'].values())


@pytest.mark.asyncio
async def test_failed_refresh_retains_fresh_snapshot_but_warns(api_client,session):
    now=datetime.now(timezone.utc)
    session.add(Location(id='degraded',name='Degraded refresh',level='city'));await session.flush()
    session.add(make_ci('INTUNE','fresh-before-failure','Compliant','High',location_id='degraded',attributes={'last_sync_date_time':now.isoformat()}))
    session.add_all([make_run('INTUNE',at=now-timedelta(minutes=1)),make_run('INTUNE',status='FAILED',at=now)])
    await session.commit()
    data=(await api_client.get('/api/v1/locations/degraded/score')).json()['data']
    assert data['scores']['endpoints']['value']==100
    assert data['scores']['endpoints']['status']=='warning'
    assert data['freshness']['INTUNE']['last_attempt_status']=='FAILED'


async def test_history_failure_rolls_back_updates_retirement_and_observations(session, monkeypatch):
    service = LocationService(session)
    await service.install_rules([dict(source_system='INTUNE',match_key='LP-',location='Test office')])
    kept = make_ci('INTUNE','LP-kept','Compliant','High')
    retired = make_ci('INTUNE','LP-retired','Compliant','High')
    session.add_all([kept,retired]); await session.commit()
    original = LocationService.capture

    async def failing_capture(self, run_id):
        await original(self,run_id)
        await self.session.flush()
        raise RuntimeError('History capture failed after writing observations')

    monkeypatch.setattr(LocationService,'capture',failing_capture)
    source = SimpleNamespace(name='INTUNE',snapshot_complete=True)
    monkeypatch.setattr('app.services.sync_service.build_sources',lambda *args,**kwargs: [source])
    sync = SyncService(session)
    monkeypatch.setattr(sync,'_fetch_source',AsyncMock(return_value=[dict(external_id=kept.source_id,name=kept.name,status='NonCompliant',health_tier='Low',ci_type='Windows')]))
    result = await sync.execute_sync_with_lock(source_system='INTUNE')
    await session.refresh(kept); await session.refresh(retired)
    assert result['status'] == 'FAILED'
    assert kept.status == 'Compliant' and kept.location_id is None
    assert retired.is_active and retired.retired_at is None
    assert (await session.scalar(select(func.count()).select_from(LocationScoreSnapshot))) == 0
    run = (await session.scalars(select(SyncRun))).one()
    assert run.status == 'FAILED' and run.records_retired == 0 and run.records_updated == 0


@pytest.mark.parametrize('method',['catalogue','one_score'])
async def test_score_retries_when_inventory_and_source_epoch_change(session, db_session_factory, monkeypatch, method):
    now = datetime.now(timezone.utc)
    session.add(Location(id='coherent',name='Coherent office',level='office')); await session.flush()
    session.add(make_ci('INTUNE','coherent-device','Compliant','High',location_id='coherent',attributes={'last_sync_date_time':now.isoformat()}))
    session.add(make_run('INTUNE',at=now-timedelta(hours=1))); await session.commit()
    service = LocationService(session)
    original = service.score_records
    changed = False

    async def interleave(*args):
        nonlocal changed
        records = await original(*args)
        if not changed:
            changed = True
            async with db_session_factory() as writer:
                ci = (await writer.scalars(select(ConfigurationItem))).one()
                ci.status = 'NonCompliant'
                writer.add(make_run('INTUNE',at=now))
                await writer.commit()
        return records

    monkeypatch.setattr(service,'score_records',interleave)
    result = await service.catalogue() if method == 'catalogue' else await service.one_score('coherent')
    data = next(l for l in result['items'] if l['id']=='coherent') if method=='catalogue' else result
    assert data['components']['compliance']['value'] == 0
    assert data['scores']['endpoints']['status'] == 'critical'
    assert data['freshness']['INTUNE']['status'] == 'FRESH'


async def test_mapping_identity_is_reloaded_after_concurrent_rename(session, db_session_factory, monkeypatch):
    session.add(Location(id='renamed',name='Original name',level='city')); await session.flush()
    session.add(make_ci('INTUNE','renamed-device','Compliant','High',location_id='renamed',attributes={'last_sync_date_time':datetime.now(timezone.utc).isoformat()}))
    session.add(make_run('INTUNE')); await session.commit()
    # Populate the reader's ORM identity map before a different session renames it.
    original_location = await session.get(Location,'renamed')
    service = LocationService(session)
    original = service.score_records
    changed = False

    async def interleave(*args):
        nonlocal changed
        records = await original(*args)
        if not changed:
            changed = True
            async with db_session_factory() as writer:
                location = await writer.get(Location,'renamed')
                location.name = 'Updated name'
                await writer.commit()
        return records

    monkeypatch.setattr(service,'score_records',interleave)
    data = await service.one_score('renamed')
    assert data['name'] == 'Updated name'
    assert original_location is not None


@pytest.mark.parametrize('path',['/api/v1/locations','/api/v1/locations/churning/score'])
async def test_continuous_changes_fail_closed_with_503(api_client, session, db_session_factory, monkeypatch, path):
    session.add(Location(id='churning',name='Changing source',level='city')); await session.flush()
    session.add(make_ci('INTUNE','changing-device','Compliant','High',location_id='churning',attributes={'last_sync_date_time':datetime.now(timezone.utc).isoformat()}))
    session.add(make_run('INTUNE')); await session.commit()
    original = LocationService.score_records
    attempts = 0

    async def interleave(self, *args):
        nonlocal attempts
        records = await original(self,*args)
        async with db_session_factory() as writer:
            writer.add(make_run('INTUNE'))
            await writer.commit()
        attempts += 1
        return records

    monkeypatch.setattr(LocationService,'score_records',interleave)
    response = await api_client.get(path)
    assert response.status_code == 503 and attempts == 3
    assert response.json()['detail'].startswith('Location data unavailable')
