"""Explicit local approval decisions, immutable audit and assignment updates."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func, or_, text
from app.models.ci import ConfigurationItem
from app.models.location import Location, LocationMappingRule, LocationMappingReview
from app.services.location_service import LocationService
from app.services.sync_service import SyncService
from app.services.summary_cache import invalidate_summaries_for_sources

STATUSES = {'PENDING','APPROVED','REJECTED'}
logger=logging.getLogger('itom.location_review')


class ReviewConflict(RuntimeError):
    pass


def utc_iso(value):
    if value is None:
        return None
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()


def rule_data(rule, location=None, devices=0):
    return dict(id=rule.id,source_system=rule.source_system,match_key=rule.match_key,
                location_id=rule.location_id,location_name=location.name if location else None,
                approval_status=rule.approval_status,reviewed_by=rule.reviewed_by,
                reviewed_at=utc_iso(rule.reviewed_at),review_note=rule.review_note,
                revision=rule.revision,enabled=rule.enabled,devices=devices,
                legacy_approval=rule.approval_status=='APPROVED' and rule.reviewed_at is None)


class LocationReviewService:
    def __init__(self, session):
        self.session = session

    async def queue(self, status=None, source=None, search='', page=1, page_size=25):
        counts=dict((await self.session.execute(select(LocationMappingRule.approval_status,func.count())
                    .where(LocationMappingRule.enabled.is_(True)).group_by(LocationMappingRule.approval_status))).all())
        device_counts=select(ConfigurationItem.location_rule_id,func.count().label('devices')).where(
            ConfigurationItem.is_active.is_(True)).group_by(ConfigurationItem.location_rule_id).subquery()
        query=select(LocationMappingRule,Location,func.coalesce(device_counts.c.devices,0)).outerjoin(
            Location,LocationMappingRule.location_id==Location.id).outerjoin(
            device_counts,LocationMappingRule.id==device_counts.c.location_rule_id).where(LocationMappingRule.enabled.is_(True))
        if status:
            query=query.where(LocationMappingRule.approval_status==status)
        if source:
            query=query.where(LocationMappingRule.source_system==source)
        if search:
            term=search.strip().lower()
            query=query.where(or_(func.lower(LocationMappingRule.match_key).contains(term,autoescape=True),
                                  func.lower(Location.name).contains(term,autoescape=True)))
        total=await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows=(await self.session.execute(query.order_by(LocationMappingRule.source_system,LocationMappingRule.match_key)
                                        .offset((page-1)*page_size).limit(page_size))).all()
        locations=(await self.session.execute(select(Location.id,Location.name).order_by(Location.name))).all()
        return dict(items=[rule_data(rule,location,int(count)) for rule,location,count in rows],
                    total=total,page=page,page_size=page_size,total_pages=max(1,(total+page_size-1)//page_size),
                    counts={key:counts.get(key,0) for key in sorted(STATUSES)},
                    locations=[dict(id=r.id,name=r.name) for r in locations])

    async def history(self, rule_id):
        if await self.session.get(LocationMappingRule,rule_id) is None:
            return None
        rows=(await self.session.scalars(select(LocationMappingReview).where(LocationMappingReview.rule_id==rule_id)
                .order_by(LocationMappingReview.reviewed_at.desc()).limit(50))).all()
        return dict(items=[dict(id=str(r.id),reviewed_by=r.reviewed_by,reviewed_at=utc_iso(r.reviewed_at),
                               comment=r.comment,before=r.before_data,after=r.after_data) for r in rows])

    async def decide(self, rule_id, status, reviewer, location_id, expected_revision, comment=None):
        reviewer=reviewer.strip();comment=comment.strip() if comment else None
        if status not in STATUSES or not reviewer or len(reviewer)>128 or (comment and len(comment)>512):
            raise ValueError('A valid status and reviewer name are required')
        if status=='REJECTED' and not comment:
            raise ValueError('Explain why this mapping is rejected')
        sync=SyncService(self.session)
        if not await sync._acquire_lock():
            raise ReviewConflict('A sync or mapping review is running. Retry after it completes.')
        try:
            # The SQLite write lock also serializes other local processes. PG
            # uses the shared transaction advisory lock acquired above.
            if self.session.bind.dialect.name=='sqlite':
                await self.session.execute(text('BEGIN IMMEDIATE'))
            rule=await self.session.get(LocationMappingRule,rule_id,populate_existing=True)
            if rule is None:
                raise LookupError('Mapping rule not found')
            if not rule.enabled or rule.revision!=expected_revision:
                raise ReviewConflict('This rule changed. Reload it before saving a decision.')
            location=await self.session.get(Location,location_id) if location_id else None
            if location_id and location is None:
                raise ValueError('Choose an existing reporting location')
            if status=='APPROVED' and location is None:
                raise ValueError('Choose a location before approving this rule')
            old_location=await self.session.get(Location,rule.location_id) if rule.location_id else None
            before_count=await self.session.scalar(select(func.count()).select_from(ConfigurationItem)
                .where(ConfigurationItem.location_rule_id==rule.id,ConfigurationItem.is_active.is_(True)))
            before=rule_data(rule,old_location,before_count)
            now=datetime.now(timezone.utc)
            event_id=uuid.uuid4()
            rule.approval_status=status;rule.location_id=location_id
            rule.reviewed_by=reviewer;rule.reviewed_at=now
            rule.revision=hashlib.sha256((rule.revision+'|'+str(event_id)).encode()).hexdigest()
            await self.session.flush()
            assignments=await LocationService(self.session).backfill(source_system=rule.source_system,bootstrap=False)
            after_count=await self.session.scalar(select(func.count()).select_from(ConfigurationItem)
                .where(ConfigurationItem.location_rule_id==rule.id,ConfigurationItem.is_active.is_(True)))
            after=rule_data(rule,location,after_count)
            self.session.add(LocationMappingReview(id=event_id,rule_id=rule.id,reviewed_by=reviewer,
                reviewed_at=now,comment=comment,before_data=before,after_data=after))
            await self.session.commit()
            try:
                invalidate_summaries_for_sources([rule.source_system],session=self.session)
            except Exception:
                # Approval and its audit are already committed. A cache fault
                # must never report that the saved decision was rolled back.
                logger.warning('Mapping review saved, but summary invalidation failed for %s',rule.source_system)
            return dict(rule=after,changed_assignments=assignments.get('changed_assignments',0),assignments=assignments)
        except Exception:
            await self.session.rollback()
            raise
        finally:
            sync._release_in_memory_lock()
