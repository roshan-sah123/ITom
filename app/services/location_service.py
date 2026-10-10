"""Database-owned canonical membership, scoring, and issue predicates.

The JSON catalogue is bootstrap knowledge only. Excel is never read at runtime.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select, func, and_
from app.core.config import settings
from app.models.ci import ConfigurationItem
from app.models.location import Location, LocationMappingRule, LocationScoreSnapshot
from app.models.sync import SyncRun
from app.repositories.freshness_repository import FreshnessRepository
from app.services.telemetry_sources import ORION_STATUS_MAP

POLICY_VERSION = 'location-v1'
RESOLVER_VERSION = 'assignment-v1'
MIN_FIELD_COVERAGE = 0.95
ISSUES = {'all','noncompliant','other_compliance','old_checkins','old_30d','invalid_checkins',
          'up','down','critical','warning','unmanaged','conflict'}
SOURCES = {'INTUNE','SOLARWINDS'}


def normalized(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).upper()


def stable_id(kind, value):
    return kind + '_' + hashlib.sha256(value.encode()).hexdigest()[:24]


def checkin_age(ci, now):
    raw = (ci.attributes or {}).get('last_sync_date_time')
    try:
        value = datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        age = now - value
        return None if age < -timedelta(minutes=5) else age
    except (ValueError, TypeError):
        return None


def matches_issue(ci, issue, now):
    """One predicate shared by headline issue counts and paginated drilldowns."""
    status = (ci.status or '').casefold()
    if issue == 'all':
        return True
    if issue == 'conflict':
        return ci.location_resolution in {'conflict','review'}
    if issue in {'noncompliant','other_compliance','old_checkins','old_30d','invalid_checkins'}:
        if ci.source_system != 'INTUNE':
            return False
        if issue == 'noncompliant':
            return status == 'noncompliant'
        if issue == 'other_compliance':
            return status not in {'compliant','noncompliant'}
        age = checkin_age(ci, now)
        if issue == 'invalid_checkins':
            return age is None
        return age is not None and age > timedelta(days=30 if issue == 'old_30d' else 7)
    return ci.source_system == 'SOLARWINDS' and status == issue


class LocationResolver:
    def __init__(self, rules, names):
        self.rules = sorted(rules, key=lambda r: -len(normalized(r['match_key'])))
        self.prefixes = [(normalized(r['match_key']),r) for r in self.rules if r['source_system']=='INTUNE']
        self.names = names
        self.aliases = {normalized(r['match_key']):r for r in rules if r['source_system']=='SOLARWINDS'}

    def resolve(self, source, name, raw=None, attributes=None):
        source = source.upper()
        rule = None
        if source == 'INTUNE':
            value = normalized(name)
            # Select the longest recognized rule even if unresolved. A missing
            # identifier must never fall through to a shorter overlapping rule.
            for key,candidate in self.prefixes:
                if value.startswith(key):
                    if len(value)>len(key):
                        rule = candidate
                    break
        elif source == 'SOLARWINDS':
            attrs = attributes or {}
            city = self.aliases.get(normalized(attrs.get('city')))
            itsm = self.aliases.get(normalized(attrs.get('itsm_location')))
            if city and itsm and city['location_id'] and itsm['location_id'] and city['location_id']!=itsm['location_id']:
                a = self.names.get(city['location_id'],'').removesuffix(' / Site unspecified')
                b = self.names.get(itsm['location_id'],'').removesuffix(' / Site unspecified')
                # A broader city agrees with an office in that city. Different
                # offices or cities remain conflicts, never silently preferred.
                if not (a.startswith(b+' / ') or b.startswith(a+' / ')):
                    return dict(location_id=None,location_rule_id=city['id'],
                                location_resolution='conflict',resolution='conflict',location_revision=self.assignment_revision(city['revision']))
                if b.startswith(a+' / '):
                    city=itsm  # Both agree geographically; use the more precise known rule.
            raw_rule=self.aliases.get(normalized(raw))
            rule = next((r for r in [city,raw_rule,itsm] if r and r['location_id']),city or raw_rule or itsm)
        target = rule.get('location_id') if rule else None
        note = (rule.get('review_note') or '').casefold() if rule else ''
        state = 'review' if target and any(word in note for word in ['conflict','versus']) else 'mapped' if target else 'unassigned'
        return dict(location_id=target, location_rule_id=rule['id'] if rule else None,
                    location_resolution=state, resolution=state, location_revision=self.assignment_revision(rule['revision']) if rule else None)

    @staticmethod
    def assignment_revision(revision):
        return hashlib.sha256((revision+'|'+RESOLVER_VERSION).encode()).hexdigest()


class LocationService:
    def __init__(self, session):
        self.session = session

    async def install_seed(self):
        """Bootstrap once; never overwrite database decisions on a later sync."""
        if await self.session.scalar(select(func.count()).select_from(LocationMappingRule)):
            return False
        payload = json.loads((Path(__file__).parents[1]/'data'/'location_seed.json').read_text(encoding='utf-8'))
        await self.install_rules(payload['rules'])
        return True

    async def install_rules(self, rules):
        """Validate a complete revision before changing rules in the transaction."""
        prepared, names, keys = [], {}, set()
        for r in rules:
            src, key = normalized(r['source_system']), normalized(r['match_key'])
            name = str(r.get('location') or '').strip()
            if src not in SOURCES or not key or len(key)>255 or len(name)>128:
                raise ValueError('Invalid location rule')
            if (src,key) in keys:
                raise ValueError('Duplicate or conflicting source location rule')
            keys.add((src,key))
            target = stable_id('loc',normalized(name)) if name and normalized(name)!='UNASSIGNED' else None
            if target:
                if target in names and names[target]!=name:
                    raise ValueError('Inconsistent canonical spelling')
                names[target]=name
            prepared.append(dict(id=stable_id('rule',src+'|'+key),source_system=src,match_key=key,
                                 location_id=target,review_note=r.get('review_note')))
        revision = hashlib.sha256(json.dumps(prepared,sort_keys=True).encode()).hexdigest()
        existing_locations = {r.id:r for r in (await self.session.scalars(select(Location))).all()}
        countries = {'Costa Rica','Brazil','Mexico','United States','United Kingdom','Poland','Australia'}
        for id,name in names.items():
            level = 'country' if name in countries else 'region' if name=='Europe' else 'cloud' if name.startswith('Cloud /') else 'office' if any(t in name for t in ['Tower','Office','Data Center']) else 'group' if ' / ' in name else 'city'
            if id not in existing_locations:
                self.session.add(Location(id=id,name=name,level=level))
        await self.session.flush()
        existing = {r.id:r for r in (await self.session.scalars(select(LocationMappingRule))).all()}
        for rule in existing.values():
            rule.enabled=False
        for values in prepared:
            rule=existing.get(values['id'])
            if rule is None:
                rule=LocationMappingRule(**values,revision=revision,enabled=True)
                self.session.add(rule)
            else:
                for field,value in values.items():
                    setattr(rule,field,value)
                rule.revision=revision;rule.enabled=True
        await self.session.flush()
        return revision

    async def resolver(self, bootstrap=False):
        if bootstrap:
            await self.install_seed()
        rules=(await self.session.scalars(select(LocationMappingRule).where(LocationMappingRule.enabled.is_(True)))).all()
        names={r.id:r.name for r in (await self.session.scalars(select(Location))).all()}
        return LocationResolver([dict(id=r.id,source_system=r.source_system,match_key=r.match_key,location_id=r.location_id,revision=r.revision,review_note=r.review_note) for r in rules], names)

    @staticmethod
    def assign(ci, result):
        for field in ['location_id','location_rule_id','location_resolution','location_revision']:
            setattr(ci,field,result[field])

    async def backfill(self):
        resolver=await self.resolver(bootstrap=True)
        counts=Counter()
        for ci in (await self.session.scalars(select(ConfigurationItem))).all():
            result=resolver.resolve(ci.source_system,ci.name,ci.location,ci.attributes)
            self.assign(ci,result)
            counts[ci.source_system+':'+result['resolution']]+=1
        await self.session.flush()
        return dict(counts)

    async def freshness(self):
        report=await FreshnessRepository(self.session,max(900,int(settings.SYNC_INTERVAL_SECONDS*2.5))).get_freshness()
        latest=select(SyncRun.source_system,func.max(SyncRun.started_at).label('started')).where(SyncRun.source_system.in_(SOURCES)).group_by(SyncRun.source_system).subquery()
        attempts=(await self.session.execute(select(SyncRun.source_system,SyncRun.status).join(latest,and_(SyncRun.source_system==latest.c.source_system,SyncRun.started_at==latest.c.started)))).all()
        for src,status in attempts:
            report['sources'][src]['last_attempt_status']=status
        return report

    async def score_records(self, location_id=None):
        # Aggregate cards need only status, assignment and check-in evidence.
        # Extract the JSON timestamp in SQL instead of loading all personal and
        # hardware attributes for tens of thousands of ORM objects.
        ci=ConfigurationItem
        query=select(ci.source_system,ci.status,ci.location_id,ci.location_resolution,ci.location_revision,
                     ci.attributes['last_sync_date_time'].as_string().label('checkin')).where(ci.is_active.is_(True))
        if location_id is not None:
            query=query.where(ci.location_id.is_(None) if location_id=='unassigned' else ci.location_id==location_id)
        rows=(await self.session.execute(query)).all()
        return [SimpleNamespace(source_system=r.source_system,status=r.status,location_id=r.location_id,
                                location_resolution=r.location_resolution,location_revision=r.location_revision,
                                attributes={'last_sync_date_time':r.checkin}) for r in rows]

    async def observation_token(self):
        """Revision evidence for supported sync, backfill and mapping writers.

        Read committed/SQLite readers can see a new commit between statements.
        Bracket score inputs with these markers and retry rather than attaching
        a newer source timestamp to older counts. No read transaction is reset,
        so capture can also use this inside the ingestion savepoint.
        """
        runs=(await self.session.execute(
            select(SyncRun.source_system,SyncRun.status,func.count(),func.max(SyncRun.started_at),func.max(SyncRun.completed_at))
            .group_by(SyncRun.source_system,SyncRun.status).order_by(SyncRun.source_system,SyncRun.status))).all()
        inventory=(await self.session.execute(
            select(ConfigurationItem.source_system,func.count(),func.max(ConfigurationItem.updated_at))
            .group_by(ConfigurationItem.source_system).order_by(ConfigurationItem.source_system)
            .execution_options(include_retired=True))).all()
        rules=(await self.session.execute(select(LocationMappingRule.id,LocationMappingRule.revision,
                LocationMappingRule.enabled,LocationMappingRule.location_id).order_by(LocationMappingRule.id))).all()
        locations=(await self.session.execute(select(Location.id,Location.name,Location.level).order_by(Location.id))).all()
        return tuple(runs),tuple(inventory),tuple(rules),tuple(locations)

    async def score_inputs(self, location_id=None):
        for _ in range(3):
            before=await self.observation_token()
            now=datetime.now(timezone.utc)
            query=select(Location.id,Location.name,Location.level).order_by(Location.name)
            if location_id is not None:
                query=query.where(Location.id==location_id)
            locations=[SimpleNamespace(id=r.id,name=r.name,level=r.level) for r in (await self.session.execute(query)).all()]
            cis=await self.score_records(location_id)
            fresh=await self.freshness()
            if before==await self.observation_token():
                return now,locations,cis,fresh
        raise RuntimeError('Location inventory changed during assessment; retry the request')

    async def catalogue(self):
        now,locations,cis,fresh=await self.score_inputs()
        groups=defaultdict(list)
        for ci in cis:
            groups[ci.location_id or 'unassigned'].append(ci)
        items=[self.score(loc,groups.get(loc.id,[]),fresh,now) for loc in locations]
        items.append(self.score(Location(id='unassigned',name='Unassigned',level='unassigned'),groups['unassigned'],fresh,now))
        counts={src:sum(ci.source_system==src for g in groups.values() for ci in g) for src in SOURCES}
        unmapped={src:sum(ci.source_system==src for ci in groups['unassigned']) for src in SOURCES}
        return dict(items=items,coverage={src:dict(total=counts[src],unassigned=unmapped[src],assigned=counts[src]-unmapped[src]) for src in SOURCES},freshness=fresh,as_of=now.isoformat(),policy_version=POLICY_VERSION)

    @staticmethod
    def score(loc, cis, fresh, now):
        endpoints=[c for c in cis if c.source_system=='INTUNE']
        nodes=[c for c in cis if c.source_system=='SOLARWINDS']
        statuses={src:dict(Counter(c.status for c in cis if c.source_system==src)) for src in SOURCES}
        issues={issue:sum(matches_issue(c,issue,now) for c in cis) for issue in ISSUES-{'all'}}
        ages=[checkin_age(c,now) for c in endpoints]
        recent=sum(age is not None and age<=timedelta(days=7) for age in ages)
        compliant=sum(c.status.casefold()=='compliant' for c in endpoints)
        monitored=[c for c in nodes if c.status.casefold()!='unmanaged']
        up=sum(c.status.casefold()=='up' for c in monitored)
        def component(n,d,src,known):
            complete=d>0 and known/d>=MIN_FIELD_COVERAGE
            current=fresh['sources'][src]['status']=='FRESH'
            usable=current and complete
            reason=None if usable else 'No eligible records' if not d else 'Source data is stale or unavailable' if not current else 'Required field coverage is below 95%'
            return dict(numerator=n,denominator=d,known_records=known,coverage_pct=round(100*known/d,2) if d else None,
                        value=round(100*n/d,2) if complete else None,usable=usable,reason=reason,source_system=src)
        compliance_states={'compliant','noncompliant','configmanager','ingraceperiod','error','conflict'}
        node_states={state.casefold() for state in ORION_STATUS_MAP.values()}-{'unknown'}
        components=dict(compliance=component(compliant,len(endpoints),'INTUNE',sum(ci.status.casefold() in compliance_states for ci in endpoints)),
                        node_status=component(up,len(monitored),'SOLARWINDS',sum(ci.status.casefold() in node_states for ci in monitored)),
                        recent_checkins=component(recent,len(endpoints),'INTUNE',sum(age is not None for age in ages)))
        c,h,r=[components[k] for k in ['compliance','node_status','recent_checkins']]
        mapped=loc.id!='unassigned'
        review=issues['conflict']
        def scored(value, required, allow, infrastructure=False):
            if not mapped or not allow or not all(v['usable'] for v in required):
                return dict(value=None,status='unavailable',reason='Unassigned location' if not mapped else 'Location identity needs review' if not allow else next((v['reason'] for v in required if not v['usable']),'Insufficient data'))
            value=round(value,1)
            severe=any(v['value']<75 for v in required)
            attention=infrastructure and bool(issues['down']+issues['critical'])
            degraded=any(fresh['sources'][v['source_system']].get('last_attempt_status') in {'FAILED','PARTIAL'} for v in required)
            status='critical' if value<75 or severe else 'warning' if value<90 or attention or degraded else 'healthy'
            return dict(value=value,status=status,reason='A component is below 75%' if severe else 'Down or Critical nodes need attention' if attention else 'Latest refresh failed; showing the last successful snapshot' if degraded else None)
        cv,hv,rv=[v['value'] or 0 for v in [c,h,r]]
        scores=dict(endpoints=scored((40*cv+25*rv)/65,[c,r],True),infrastructure=scored(hv,[h],True,True),
                    combined=scored(.4*cv+.35*hv+.25*rv,[c,h,r],not review,True))
        revisions=sorted({ci.location_revision for ci in cis if ci.location_revision})
        return dict(id=loc.id,name=loc.name,level=loc.level,endpoints=len(endpoints),nodes=len(nodes),
                    components=components,scores=scores,issues=issues,status_breakdown=statuses,
                    mapping_revision=stable_id('rev','|'.join(revisions)) if revisions else None,
                    freshness=fresh['sources'],as_of=now.isoformat(),policy_version=POLICY_VERSION)

    async def one_score(self, id):
        now,locations,cis,fresh=await self.score_inputs(id)
        loc=Location(id='unassigned',name='Unassigned',level='unassigned') if id=='unassigned' else next(iter(locations),None)
        if loc is None:
            return None
        return self.score(loc,cis,fresh,now)

    async def devices(self, id, source=None, issue='all', page=1, page_size=25, search=''):
        if id!='unassigned' and await self.session.get(Location,id) is None:
            return None
        query=select(ConfigurationItem).where(ConfigurationItem.location_id.is_(None) if id=='unassigned' else ConfigurationItem.location_id==id).order_by(ConfigurationItem.name,ConfigurationItem.id)
        if source:
            query=query.where(ConfigurationItem.source_system==source)
        now=datetime.now(timezone.utc)
        selected=[ci for ci in (await self.session.scalars(query)).all() if matches_issue(ci,issue,now) and (not search or search.casefold() in ci.name.casefold())]
        total=len(selected);start=(page-1)*page_size
        return dict(items=[ci.to_dict() for ci in selected[start:start+page_size]],total=total,page=page,page_size=page_size,
                    total_pages=max(1,(total+page_size-1)//page_size),location_id=id,source=source,issue=issue,
                    as_of=now.isoformat(),policy_version=POLICY_VERSION)

    async def capture(self, sync_run_id):
        await self.session.flush()
        now=datetime.now(timezone.utc)
        for data in (await self.catalogue())['items']:
            if data['id']=='unassigned' or not data['endpoints']+data['nodes']:
                continue
            # Retain the observed measures and provenance, not a repeated card
            # presentation or entire device inventory at every sync.
            observed={key:data[key] for key in ['scores','components','endpoints','nodes','freshness','issues']}
            self.session.add(LocationScoreSnapshot(location_id=data['id'],sync_run_id=sync_run_id,recorded_at=now,
                                                   policy_version=POLICY_VERSION,mapping_revision=data['mapping_revision'] or 'none',data=observed))
