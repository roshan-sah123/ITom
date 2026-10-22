"""Validate source hierarchy snapshots and serve repository-backed drilldowns."""
from collections import defaultdict, deque
from dataclasses import dataclass

from app.repositories.solarwinds_group_repository import SolarWindsGroupRepository


@dataclass(frozen=True)
class GroupSnapshot:
    groups: list[dict]
    members: list[dict]


def source_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('Invalid SolarWinds identifier')
    if isinstance(value, str) and (not value.isascii() or not value.isdecimal()):
        raise ValueError('Invalid SolarWinds identifier')
    number = int(value)
    if number <= 0 or number > 2147483647:
        raise ValueError('Invalid SolarWinds identifier')
    return number


def validate_group_snapshot(raw_groups, raw_members, node_source_ids):
    """Keep Core names verbatim; reject ambiguous or incomplete relationships."""
    if not isinstance(raw_groups, list) or not isinstance(raw_members, list):
        raise ValueError('Invalid SolarWinds group snapshot')
    groups = {}
    all_group_ids = set()
    for row in raw_groups:
        if not isinstance(row, dict) or not isinstance(row.get('Owner'), str) or not isinstance(row.get('IsDeleted'), bool):
            raise ValueError('Malformed SolarWinds group')
        id = source_id(row.get('ContainerID'))
        if id in all_group_ids:
            raise ValueError('Duplicate group identifier')
        all_group_ids.add(id)
        if row['Owner'] != 'Core' or row['IsDeleted']:
            continue
        if id in groups or not isinstance(row.get('Name'), str) or not row['Name'].strip():
            raise ValueError('Missing group name or duplicate group identifier')
        status = row.get('Status')
        if not isinstance(status, int) or isinstance(status, bool):
            raise ValueError('Invalid SolarWinds group status')
        description = row.get('StatusDescription')
        if not isinstance(description, str) or not description:
            description = 'Unknown'
        groups[id] = dict(group_id=id, name=row['Name'], status_code=status, status=description)

    members = {}
    children = defaultdict(set)
    incoming = {id: 0 for id in groups}
    for row in raw_members:
        if not isinstance(row, dict):
            raise ValueError('Malformed SolarWinds membership')
        parent = source_id(row.get('ContainerID'))
        if parent not in all_group_ids:
            raise ValueError('Unresolved membership parent')
        if parent not in groups:
            continue
        entity = row.get('MemberEntityType')
        id = source_id(row.get('MemberPrimaryID'))
        if entity == 'Orion.Groups':
            if id not in groups:
                raise ValueError('Unresolved child group')
            if id not in children[parent]:
                children[parent].add(id)
                incoming[id] += 1
        elif entity == 'Orion.Nodes':
            if f'SW-NODE-{id}' not in node_source_ids:
                raise ValueError('Unresolved group device')
        else:
            raise ValueError('Unsupported regular group member type')
        key = (parent, entity, id)
        members[key] = dict(group_id=parent, member_entity_type=entity, member_id=id)

    # Iterative topological validation supports deep graphs and multiple parents.
    ready = deque(id for id, count in incoming.items() if not count)
    visited = 0
    while ready:
        parent = ready.popleft()
        visited += 1
        for child in children[parent]:
            incoming[child] -= 1
            if not incoming[child]:
                ready.append(child)
    if visited != len(groups):
        raise ValueError('Cyclic SolarWinds group hierarchy')
    return GroupSnapshot(list(groups.values()), list(members.values()))


class SolarWindsGroupService:
    def __init__(self, session):
        self.session = session
        self.repository = SolarWindsGroupRepository(session)

    async def overview(self, score_mode='infrastructure'):
        from app.services.group_score_service import GroupScoreService
        return await GroupScoreService(self.session).assess(score_mode)

    async def summary(self, group_id, score_mode='infrastructure'):
        from app.services.group_score_service import GroupScoreService
        return await GroupScoreService(self.session).assess(score_mode, group_id)

    async def roots(self):
        return await self.repository.roots()

    async def members(self, group_id):
        return await self.repository.members(group_id)

    async def devices(self, group_id, **filters):
        return await self.repository.devices(group_id, **filters)
