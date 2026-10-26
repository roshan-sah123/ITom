"""Batch location assessments using source membership and the existing score policy."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace

from app.repositories.solarwinds_categories import category_counts
from app.repositories.solarwinds_group_repository import SolarWindsGroupRepository
from app.services.location_service import LocationService


class GroupScoreService:
    def __init__(self, session):
        self.session = session
        self.locations = LocationService(session)
        self.repository = SolarWindsGroupRepository(session)

    async def token(self):
        return await self.locations.observation_token(), await self.repository.link_revisions()

    async def assess(self, score_mode='infrastructure', group_id=None):
        for _ in range(3):
            before = await self.token()
            result = await self._assess(score_mode, group_id)
            if before == await self.token():
                return result
        raise RuntimeError('Inventory changed during assessment')

    async def _assess(self, score_mode, group_id):
        groups, members, raw_nodes, links, location_names, endpoint_rows = await self.repository.assessment_inputs(score_mode)
        if group_id is not None and group_id not in groups:
            return None
        children = defaultdict(set); direct = defaultdict(set); nested = set()
        for parent, child, ci in members:
            if child is not None:
                children[parent].add(child); nested.add(child)
            elif ci is not None:
                direct[parent].add(ci)
        roots = set(groups)-nested
        nodes = {row.id: SimpleNamespace(source_system='SOLARWINDS', status=row.status, category=row.category,
                 location_resolution='mapped', location_revision=None, attributes={}) for row in raw_nodes}
        endpoint_groups = defaultdict(list)
        for row in endpoint_rows:
            endpoint_groups[row.location_id].append(SimpleNamespace(source_system='INTUNE', status=row.status,
                location_resolution=row.location_resolution, location_revision=row.location_revision,
                attributes={'last_sync_date_time':row.checkin}))
        fresh = await self.locations.freshness()
        evidence = await self.repository.evidence()
        # Group inventory and freshness describe the same completed group snapshot.
        fresh['sources']['SOLARWINDS'].update(evidence['freshness'])
        fresh['sources']['SOLARWINDS']['last_attempt_status'] = evidence['last_attempt_status']
        now = datetime.now(timezone.utc)
        grouped = set()

        def descendants(id):
            visited = set(); todo = [id]; ids = set()
            while todo:
                current = todo.pop()
                if current in visited:
                    continue
                visited.add(current); ids.update(direct[current]); todo.extend(children[current])
            return {ci for ci in ids if ci in nodes}

        selected = [group_id] if group_id is not None else sorted(roots, key=lambda id: (groups[id].name.casefold(), id))
        items = []
        for id in selected:
            ids = descendants(id); grouped.update(ids)
            population = [nodes[ci] for ci in ids]
            link = links.get(id)
            valid = id in roots and link is not None and link.approval_status == 'APPROVED' and link.location_id in location_names
            endpoints = endpoint_groups[link.location_id] if valid and score_mode == 'combined' else []
            assessment = LocationService.score(SimpleNamespace(id=f'group:{id}', name=groups[id].name, level='group'),
                population+endpoints, fresh, now)
            score = dict(assessment['scores'][score_mode], mode=score_mode)
            if score_mode == 'combined' and not valid:
                score.update(value=None, status='unavailable', reason='An explicit approved Intune location link is required')
            items.append(dict(group=self.repository.group_data(groups[id], bool(children[id] or direct[id])),
                **category_counts(population), site_score=score, intune_endpoints=len(endpoints),
                components=assessment['components'], status_breakdown=dict(Counter(n.status for n in population)),
                mapping=dict(status='APPROVED' if valid else link.approval_status if link else 'UNMAPPED',
                             location_id=link.location_id if link else None,
                             location_name=location_names.get(link.location_id) if link else None),
                source_freshness=fresh['sources'], policy_version=assessment['policy_version']))
        if group_id is not None:
            return dict(items[0], **evidence)
        return dict(items=items, fleet=dict(**category_counts(list(nodes.values())),
                    grouped_devices=len(grouped), ungrouped_devices=len(nodes)-len(grouped)), **evidence)
