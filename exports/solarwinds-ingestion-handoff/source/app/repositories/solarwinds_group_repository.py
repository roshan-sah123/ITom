"""Persist validated snapshots and query unique descendant devices in SQL."""
import uuid
from sqlalchemy import delete, exists, false, func, insert, literal, or_, select

from app.models.ci import ConfigurationItem
from app.models.solarwinds_group import SolarWindsGroup as Group, SolarWindsGroupMember as Member
from app.models.sync import SyncRun
from app.models.solarwinds_group import SolarWindsGroupLocation
from app.repositories.freshness_repository import classify
from app.core.config import settings


class SolarWindsGroupRepository:
    def __init__(self, session):
        self.session = session

    async def link_revisions(self):
        return tuple((await self.session.execute(select(SolarWindsGroupLocation.group_id,
            SolarWindsGroupLocation.revision).order_by(SolarWindsGroupLocation.group_id))).all())

    async def assessment_inputs(self, score_mode):
        """Minimal batched projections, independent of the number of locations."""
        from app.models.location import Location
        groups = {group.group_id: group for group in (await self.session.scalars(
            select(Group).where(Group.is_active.is_(True)))).all()}
        members = (await self.session.execute(select(Member.group_id, Member.child_group_id, Member.ci_id))).all()
        nodes = (await self.session.execute(select(ConfigurationItem.id, ConfigurationItem.status,
            ConfigurationItem.attributes['node_category'].as_string().label('category')).where(
                ConfigurationItem.source_system == 'SOLARWINDS'))).all()
        links = {link.group_id: link for link in (await self.session.scalars(select(SolarWindsGroupLocation))).all()}
        names = dict((await self.session.execute(select(Location.id, Location.name))).all())
        children = {row.child_group_id for row in members if row.child_group_id is not None}
        approved = {link.location_id for id, link in links.items() if id in groups and id not in children
                    and link.approval_status == 'APPROVED'}
        endpoints = []
        if approved and score_mode == 'combined':
            endpoints = (await self.session.execute(select(ConfigurationItem.location_id, ConfigurationItem.status,
                ConfigurationItem.location_resolution, ConfigurationItem.location_revision,
                ConfigurationItem.attributes['last_sync_date_time'].as_string().label('checkin')).where(
                ConfigurationItem.source_system == 'INTUNE', ConfigurationItem.location_id.in_(approved)))).all()
        return groups, members, nodes, links, names, endpoints

    async def replace(self, snapshot):
        nodes = (await self.session.execute(select(ConfigurationItem.source_id, ConfigurationItem.id)
                 .where(ConfigurationItem.source_system == 'SOLARWINDS'))).all()
        node_ids = dict(nodes)
        records = []
        for member in snapshot.members:
            row = dict(member)
            if row['member_entity_type'] == 'Orion.Groups':
                row['child_group_id'] = row['member_id']
                row['ci_id'] = None
            else:
                row['child_group_id'] = None
                row['ci_id'] = node_ids[f"SW-NODE-{row['member_id']}"]
            records.append(row)
        # Caller owns the transaction, including CI updates and the success audit.
        await self.session.execute(delete(Member))
        existing = {group.group_id: group for group in (await self.session.scalars(select(Group))).all()}
        current_ids = {group['group_id'] for group in snapshot.groups}
        for group in existing.values():
            group.is_active = group.group_id in current_ids
        for values in snapshot.groups:
            group = existing.get(values['group_id'])
            if group is None:
                group = Group(**values)
                self.session.add(group)
            else:
                for key, value in values.items():
                    setattr(group, key, value)
            group.is_active = True
        children = {member['member_id'] for member in snapshot.members if member['member_entity_type'] == 'Orion.Groups'}
        from app.services.group_location_service import link_data, record_link_decision
        links = (await self.session.scalars(select(SolarWindsGroupLocation))).all()
        for link in links:
            if link.approval_status == 'APPROVED' and (link.group_id not in current_ids or link.group_id in children):
                before = link_data(link)
                link.approval_status = 'REVIEW'; link.revision = str(uuid.uuid4())
                record_link_decision(self.session, link, before, 'SOURCE_SYNC', 'Group is no longer an active top-level location')
        await self.session.flush()
        if records:
            await self.session.execute(insert(Member), records)

    async def evidence(self):
        successful = await self.session.scalar(select(SyncRun).where(
            SyncRun.source_system == 'SOLARWINDS', SyncRun.status == 'SUCCESS',
            SyncRun.groups_extracted.is_not(None)).order_by(SyncRun.started_at.desc()).limit(1))
        latest = await self.session.scalar(select(SyncRun.status).where(
            SyncRun.source_system == 'SOLARWINDS').order_by(SyncRun.started_at.desc()).limit(1))
        completed = successful.completed_at if successful else None
        freshness = classify(completed, freshness_window_seconds=max(900, int(settings.SYNC_INTERVAL_SECONDS*2.5)))
        return dict(data_available=successful is not None,
                    as_of=freshness['last_synchronized_at'],
                    last_attempt_status=latest,
                    freshness=freshness,
                    snapshot_id=str(successful.id) if successful else None)

    @staticmethod
    def group_data(group, has_members):
        return dict(kind='group', group_id=group.group_id, name=group.name,
                    status_code=group.status_code, status=group.status, has_members=has_members)

    def group_query(self):
        return select(Group, exists().where(Member.group_id == Group.group_id).label('has_members')).where(Group.is_active.is_(True))

    @staticmethod
    def order_groups(items):
        return sorted(items, key=lambda item: (item['name'].casefold(), item['group_id']))

    async def roots(self):
        query = self.group_query().where(~exists().where(Member.child_group_id == Group.group_id))
        rows = (await self.session.execute(query)).all()
        return dict(items=self.order_groups([self.group_data(g, has) for g, has in rows]),
                    **await self.evidence())

    async def members(self, group_id):
        group = await self.session.get(Group, group_id)
        if group is None or not group.is_active:
            return None
        child_ids = select(Member.child_group_id).where(Member.group_id == group_id,
                                                       Member.child_group_id.is_not(None))
        children = (await self.session.execute(self.group_query().where(Group.group_id.in_(child_ids)))).all()
        device_ids = select(Member.ci_id).where(Member.group_id == group_id, Member.ci_id.is_not(None))
        nodes = (await self.session.scalars(select(ConfigurationItem).where(
            ConfigurationItem.source_system == 'SOLARWINDS', ConfigurationItem.id.in_(device_ids))
            .order_by(ConfigurationItem.name, ConfigurationItem.source_id))).all()
        items = self.order_groups([self.group_data(g, has) for g, has in children])
        items.extend(dict(kind='device', **node.to_dict()) for node in nodes)
        return dict(group=self.group_data(group, bool(items)), items=items, **await self.evidence())

    async def devices(self, group_id, page=1, page_size=25, search='', status=None, category=None, category_missing=False, source_type=None):
        group = None
        query = select(ConfigurationItem).where(ConfigurationItem.source_system == 'SOLARWINDS')
        if group_id is None:
            query = query.where(~exists().where(Member.ci_id == ConfigurationItem.id,
                Member.group_id == Group.group_id, Group.is_active.is_(True)))
        else:
            group = await self.session.get(Group, group_id)
            if group is None or not group.is_active:
                return None
            descendants = select(literal(group_id).label('group_id')).cte('descendant_groups', recursive=True)
            descendants = descendants.union(select(Member.child_group_id).join(
                descendants, Member.group_id == descendants.c.group_id).where(Member.child_group_id.is_not(None)))
            node_ids = select(Member.ci_id).where(Member.group_id.in_(select(descendants.c.group_id)),
                                                 Member.ci_id.is_not(None))
            query = query.where(ConfigurationItem.id.in_(node_ids))
        if '\x00' in search:
            query = query.where(false())
        elif search:
            # Search text is literal; SQL wildcards never broaden a device search.
            pattern = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            query = query.where(or_(ConfigurationItem.name.ilike(pattern, escape='\\'),
                                    ConfigurationItem.ip_address.ilike(pattern, escape='\\')))
        if status:
            query = query.where(func.lower(ConfigurationItem.status) == status.casefold())
        if category is not None:
            query = query.where(ConfigurationItem.attributes['node_category'].as_string() == category)
        if source_type is not None:
            query = query.where(ConfigurationItem.attributes['node_type'].as_string() == source_type)
        if category_missing:
            query = query.where(or_(ConfigurationItem.attributes['node_category'].as_string().is_(None),
                                    func.trim(ConfigurationItem.attributes['node_category'].as_string()) == ''))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        nodes = (await self.session.scalars(query.order_by(ConfigurationItem.name, ConfigurationItem.source_id)
                 .offset((page - 1) * page_size).limit(page_size))).all()
        return dict(group=self.group_data(group, bool(total)) if group is not None else None,
                scope='regular_group' if group is not None else 'outside_regular_groups',
                items=[node.to_dict() for node in nodes],
                    total=total, page=page, page_size=page_size,
                    total_pages=max(1, (total + page_size - 1) // page_size), **await self.evidence())
