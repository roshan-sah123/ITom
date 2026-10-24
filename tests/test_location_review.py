"""Local mapping approval, immutable decisions and assignment contracts."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.location import LocationMappingRule
from app.models.ci import ConfigurationItem
from app.services.location_service import LocationService, LocationResolver
from app.services.location_review_service import LocationReviewService, ReviewConflict
from tests.factories import make_ci, make_run
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.models.location import LocationMappingReview
from app.services.sync_service import SyncService


@pytest_asyncio.fixture
async def api_client(api_environment):
    async with AsyncClient(transport=ASGITransport(app=api_environment),base_url='http://localhost') as client:
        yield client


async def setup_rule(session, location='Review office'):
    service = LocationService(session)
    await service.install_rules([dict(source_system='INTUNE',match_key='LP-REVIEW-',location=location,
                                     review_note='No conflict; source owner verified this note.')])
    session.add(make_ci('INTUNE','LP-REVIEW-001','Compliant','High',attributes={'last_sync_date_time':datetime.now(timezone.utc).isoformat()}))
    session.add(make_run('INTUNE'))
    await session.flush()
    await service.backfill(); await session.commit()
    return (await session.scalars(select(LocationMappingRule))).one()


def test_explicit_approval_replaces_note_keywords():
    rule = dict(id='rule',source_system='INTUNE',match_key='LP-',location_id='office',revision='v1',
                approval_status='APPROVED',review_note='No conflict; verified.')
    resolver = LocationResolver([rule],{'office':'Office'})
    assert resolver.resolve('INTUNE','LP-001')['resolution']=='mapped'
    rule['approval_status']='PENDING'
    assert LocationResolver([rule],{}).resolve('INTUNE','LP-001')['resolution']=='review'
    rule['approval_status']='REJECTED'
    result = LocationResolver([rule],{}).resolve('INTUNE','LP-001')
    assert result['location_id'] is None and result['resolution']=='unassigned'


async def test_approve_records_reviewer_date_history_and_assignments(api_client,session):
    rule = await setup_rule(session)
    assert rule.approval_status=='PENDING'
    before=(await api_client.get('/api/v1/locations/'+rule.location_id+'/score')).json()['data']
    assert before['scores']['endpoints']['value'] is None
    response = await api_client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
        'status':'APPROVED','reviewer':'Roshan Sah','location_id':rule.location_id,'expected_revision':rule.revision,'comment':'Checked with site owner'})
    assert response.status_code==200,response.text
    result=response.json()['data']
    assert result['rule']['approval_status']=='APPROVED'
    assert result['rule']['reviewed_by']=='Roshan Sah' and result['rule']['reviewed_at']
    assert result['changed_assignments']==1
    session.expire_all()
    ci=(await session.scalars(select(ConfigurationItem))).one()
    assert ci.location_resolution=='mapped' and ci.status=='Compliant'
    history=(await api_client.get(f'/api/v1/locations/reviews/rules/{result["rule"]["id"]}/history')).json()['data']['items']
    assert len(history)==1 and history[0]['before']['approval_status']=='PENDING'
    assert history[0]['after']['approval_status']=='APPROVED'
    after=(await api_client.get('/api/v1/locations/'+ci.location_id+'/score')).json()['data']
    assert after['scores']['endpoints']['value']==100


async def test_bulk_approve_records_each_rule_and_refreshes_assignments_once(session):
    locations=LocationService(session)
    await locations.install_rules([
        dict(source_system='INTUNE',match_key='BULK-A-',location='Bulk office'),
        dict(source_system='INTUNE',match_key='BULK-B-',location='Bulk office'),
    ])
    session.add_all([
        make_ci('INTUNE','BULK-A-001','Compliant','High'),
        make_ci('INTUNE','BULK-B-001','Compliant','High'),
    ])
    await session.flush();await locations.backfill();await session.commit()
    rules=(await session.scalars(select(LocationMappingRule).order_by(LocationMappingRule.match_key))).all()
    expected_revisions={rule.id:rule.revision for rule in rules}
    await session.rollback()

    result=await LocationReviewService(session).approve_many(
        expected_revisions,'Local portal operator')

    assert result['reviewed_rules']==2
    rules=(await session.scalars(select(LocationMappingRule).order_by(LocationMappingRule.match_key))).all()
    assert all(rule.approval_status=='APPROVED' and rule.reviewed_by=='Local portal operator' for rule in rules)
    assert len((await session.scalars(select(LocationMappingReview))).all())==2
    devices=(await session.scalars(select(ConfigurationItem).order_by(ConfigurationItem.name))).all()
    assert all(device.location_resolution=='mapped' for device in devices)


async def test_bulk_approve_rolls_back_all_rules_when_one_revision_changed(session):
    locations=LocationService(session)
    await locations.install_rules([
        dict(source_system='INTUNE',match_key='BULK-A-',location='Bulk office'),
        dict(source_system='INTUNE',match_key='BULK-B-',location='Bulk office'),
    ])
    await session.commit()
    rules=(await session.scalars(select(LocationMappingRule).order_by(LocationMappingRule.match_key))).all()
    expected_revisions={rule.id:rule.revision for rule in rules}
    expected_revisions[rules[-1].id]='stale-revision'
    await session.rollback()

    with pytest.raises(ReviewConflict):
        await LocationReviewService(session).approve_many(expected_revisions,'Local portal operator')

    rules=(await session.scalars(select(LocationMappingRule))).all()
    assert all(rule.approval_status=='PENDING' and rule.reviewed_by is None for rule in rules)
    assert (await session.scalars(select(LocationMappingReview))).all()==[]


async def test_reject_removes_assignment_and_stale_decision_is_conflict(api_client,session):
    rule=await setup_rule(session)
    body=dict(status='REJECTED',reviewer='Site owner',location_id=rule.location_id,expected_revision=rule.revision,comment='Prefix belongs to another site')
    url=f'/api/v1/locations/reviews/rules/{rule.id}/decision'
    assert (await api_client.post(url,json=body)).status_code==200
    assert (await api_client.post(url,json=body)).status_code==409
    session.expire_all()
    ci=(await session.scalars(select(ConfigurationItem))).one()
    assert ci.location_id is None and ci.location_rule_id and ci.location_resolution=='unassigned'


async def test_review_validation_and_cross_origin_guard(api_client,session):
    rule=await setup_rule(session,location=None)
    url=f'/api/v1/locations/reviews/rules/{rule.id}/decision'
    body=dict(status='APPROVED',reviewer='Site owner',location_id=None,expected_revision=rule.revision)
    assert (await api_client.post(url,json=body)).status_code==422
    body['reviewer']=' '
    assert (await api_client.post(url,json=body)).status_code==422
    body['reviewer']='Site owner';body['status']='REJECTED';body['comment']='Not a valid site'
    assert (await api_client.post(url,json=body,headers={'Origin':'https://outside.example'})).status_code==403
    assert (await api_client.post(url,json=body)).status_code==200


async def test_reimport_preserves_same_target_approval_but_resets_changed_target(api_client,session):
    rule=await setup_rule(session)
    body=dict(status='APPROVED',reviewer='Site owner',location_id=rule.location_id,expected_revision=rule.revision)
    response=await api_client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json=body)
    assert response.status_code==200
    session.expire_all()
    service=LocationService(session)
    await service.install_rules([dict(source_system='INTUNE',match_key='LP-REVIEW-',location='Review office')])
    rule=(await session.scalars(select(LocationMappingRule))).one()
    assert rule.approval_status=='APPROVED' and rule.reviewed_by=='Site owner'
    await service.install_rules([dict(source_system='INTUNE',match_key='LP-REVIEW-',location='Changed office')])
    assert rule.approval_status=='PENDING' and rule.reviewed_by is None and rule.reviewed_at is None


async def test_queue_filters_counts_and_literal_search(api_client,session):
    rule = await setup_rule(session)
    ci = (await session.scalars(select(ConfigurationItem))).one()
    assert ci.location_rule_id == rule.id
    response=await api_client.get('/api/v1/locations/reviews/rules?status=PENDING&source=INTUNE&search=LP-REVIEW')
    assert response.status_code==200
    data=response.json()['data']
    assert data['total']==1 and data['items'][0]['devices']==1 and data['counts']['PENDING']==1
    assert (await api_client.get('/api/v1/locations/reviews/rules?search=%25')).json()['data']['total']==0


async def test_failed_assignment_update_rolls_back_decision_and_audit(api_client,session,monkeypatch):
    rule=await setup_rule(session)
    rule_id=rule.id;revision=rule.revision;target=rule.location_id
    async def failing_backfill(*args,**kwargs):
        raise RuntimeError('Injected assignment failure')
    monkeypatch.setattr(LocationService,'backfill',failing_backfill)
    response=await api_client.post(f'/api/v1/locations/reviews/rules/{rule_id}/decision',json={
        'status':'APPROVED','reviewer':'Site owner','location_id':target,'expected_revision':revision})
    assert response.status_code==503
    session.expire_all()
    persisted=await session.get(LocationMappingRule,rule_id)
    assert persisted.approval_status=='PENDING' and persisted.reviewed_by is None
    assert (await session.scalars(select(LocationMappingReview))).all()==[]


async def test_busy_ingestion_prevents_review_without_releasing_peer_lock(api_client,session):
    rule=await setup_rule(session)
    sync=SyncService(session)
    assert await sync._acquire_lock()
    try:
        response=await api_client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
            'status':'APPROVED','reviewer':'Site owner','location_id':rule.location_id,'expected_revision':rule.revision})
        assert response.status_code==409
        assert not await SyncService(session)._acquire_lock()
    finally:
        sync._release_in_memory_lock()


async def test_remote_clients_can_read_but_cannot_review(api_environment,session):
    rule=await setup_rule(session)
    async with AsyncClient(transport=ASGITransport(app=api_environment,client=('10.0.0.2',3000)),base_url='http://test') as client:
        response=await client.get('/api/v1/locations/reviews/rules')
        assert response.json()['data']['write_enabled'] is False
        response=await client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
            'status':'APPROVED','reviewer':'Remote name','location_id':rule.location_id,'expected_revision':rule.revision})
        assert response.status_code==403


async def test_loopback_connection_with_untrusted_host_cannot_review(api_environment,session):
    rule=await setup_rule(session)
    async with AsyncClient(transport=ASGITransport(app=api_environment),base_url='http://outside.example') as client:
        queue=(await client.get('/api/v1/locations/reviews/rules')).json()['data']
        assert queue['write_enabled'] is False
        response=await client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
            'status':'APPROVED','reviewer':'Untrusted host','location_id':rule.location_id,'expected_revision':rule.revision})
        assert response.status_code==403


async def test_approved_rule_survives_periodic_sync_and_note_does_not_control_it(api_client,session):
    rule=await setup_rule(session)
    response=await api_client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
        'status':'APPROVED','reviewer':'Site owner','location_id':rule.location_id,'expected_revision':rule.revision})
    assert response.status_code==200
    session.expire_all()
    ci=(await session.scalars(select(ConfigurationItem))).one()
    await SyncService(session).ingest_telemetry_batch([dict(external_id=ci.source_id,name=ci.name,status='Compliant',health_tier='High')],'INTUNE')
    assert ci.location_resolution=='mapped'


def test_rejected_solarwinds_alias_preserves_provenance_without_assignment():
    rule=dict(id='rejected',source_system='SOLARWINDS',match_key='Office',location_id='office',revision='v1',approval_status='REJECTED')
    result=LocationResolver([rule],{}).resolve('SOLARWINDS','node','Office',{'city':'Office'})
    assert result['location_id'] is None and result['location_rule_id']=='rejected'


async def test_cache_failure_does_not_claim_committed_review_was_rolled_back(api_client,session,monkeypatch):
    rule=await setup_rule(session)
    def failing_cache(*args,**kwargs):
        raise RuntimeError('Cache fault')
    monkeypatch.setattr('app.services.location_review_service.invalidate_summaries_for_sources',failing_cache)
    response=await api_client.post(f'/api/v1/locations/reviews/rules/{rule.id}/decision',json={
        'status':'APPROVED','reviewer':'Site owner','location_id':rule.location_id,'expected_revision':rule.revision})
    assert response.status_code==200
    session.expire_all()
    persisted=(await session.scalars(select(LocationMappingRule))).one()
    assert persisted.approval_status=='APPROVED'
    assert len((await session.scalars(select(LocationMappingReview))).all())==1
