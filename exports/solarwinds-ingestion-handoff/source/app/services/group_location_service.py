"""Local operator approvals; never infer group identities or expose a write API."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import exists, select
from app.models.location import Location
from app.models.solarwinds_group import SolarWindsGroup, SolarWindsGroupMember, SolarWindsGroupLocation, SolarWindsGroupLocationReview


def link_data(link):
    if link is None:
        return {}
    return dict(location_id=link.location_id, approval_status=link.approval_status,
                reviewed_by=link.reviewed_by, reviewed_at=link.reviewed_at.isoformat() if link.reviewed_at else None,
                evidence=link.evidence, revision=link.revision)


def record_link_decision(session, link, before, actor, evidence):
    session.add(SolarWindsGroupLocationReview(group_id=link.group_id, actor=actor,
                recorded_at=datetime.now(timezone.utc), evidence=evidence,
                before_data=before, after_data=link_data(link)))


class GroupLocationService:
    def __init__(self, session):
        self.session = session

    async def approve(self, group_id, location_id, reviewer, evidence):
        if not reviewer.strip() or len(reviewer) > 128 or not evidence.strip():
            raise ValueError('Reviewer and approval evidence are required')
        group = await self.session.get(SolarWindsGroup, group_id)
        child = await self.session.scalar(select(exists().where(SolarWindsGroupMember.child_group_id == group_id)))
        if group is None or not group.is_active or child:
            raise ValueError('Only active top-level SolarWinds groups can be linked')
        if await self.session.get(Location, location_id) is None or location_id == 'unassigned':
            raise ValueError('Select an existing canonical location')
        link = await self.session.get(SolarWindsGroupLocation, group_id)
        before = link_data(link)
        if link is None:
            link = SolarWindsGroupLocation(group_id=group_id)
            self.session.add(link)
        link.location_id = location_id
        link.approval_status = 'APPROVED'
        link.reviewed_by = reviewer.strip()
        link.reviewed_at = datetime.now(timezone.utc)
        link.evidence = evidence
        link.revision = str(uuid.uuid4())
        record_link_decision(self.session, link, before, link.reviewed_by, evidence)
        await self.session.flush()
        return link_data(link)

    async def revoke(self, group_id, reviewer, evidence):
        if not reviewer.strip() or len(reviewer) > 128 or not evidence.strip():
            raise ValueError('Reviewer and evidence are required')
        link = await self.session.get(SolarWindsGroupLocation, group_id)
        if link is None:
            raise ValueError('No group link exists')
        before = link_data(link)
        link.approval_status = 'REJECTED'; link.reviewed_by = reviewer.strip()
        link.reviewed_at = datetime.now(timezone.utc); link.evidence = evidence
        link.revision = str(uuid.uuid4())
        record_link_decision(self.session, link, before, reviewer, evidence)
        await self.session.flush()
        return link_data(link)
