"""Read-only canonical location scorecards and exact issue drilldowns."""
import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.services.location_service import LocationService, ISSUES, SOURCES
from app.models.location import LocationScoreSnapshot

router=APIRouter(prefix='/locations',tags=['Locations'])


def envelope(data):
    if data is None:
        raise HTTPException(404,'Location not found')
    return {'status':'success','data':data}


def scope(source,issue):
    source=source.upper() if source else None
    if source and source not in SOURCES or issue not in ISSUES:
        raise HTTPException(422,'Unsupported source or issue filter')
    return source


async def read(operation):
    try:
        return await operation
    except (SQLAlchemyError,RuntimeError) as exc:
        raise HTTPException(503,'Location data unavailable; retry after database recovery') from exc


@router.get('')
async def catalogue(session=Depends(get_db)):
    return envelope(await read(LocationService(session).catalogue()))


@router.get('/matches')
async def geographic_matches(session=Depends(get_db)):
    return envelope(await read(LocationService(session).geographic_matches()))


@router.get('/{location_id}/score')
async def score(location_id: str,session=Depends(get_db)):
    return envelope(await read(LocationService(session).one_score(location_id)))


@router.get('/{location_id}/devices')
async def devices(location_id: str, source: Optional[str]=None, issue: str='all',
                  page: int=Query(1,ge=1),page_size: int=Query(25,ge=1,le=100),
                  search: str=Query('',max_length=255),session=Depends(get_db)):
    source=scope(source,issue)
    return envelope(await read(LocationService(session).devices(location_id,source,issue,page,page_size,search)))


@router.get('/{location_id}/export')
async def export(location_id: str,source: Optional[str]=None,issue: str='all',
                 search: str=Query('',max_length=255),session=Depends(get_db)):
    source=scope(source,issue)
    data=await read(LocationService(session).devices(location_id,source,issue,1,1000000,search))
    if data is None:
        raise HTTPException(404,'Location not found')
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['Source ID','Name','Source','Status','Raw source location','Canonical location ID','Mapping state'])
    def cell(value):
        value=str(value or '')
        return "'"+value if value.startswith(('=','+','-','@','\t','\r','\n')) else value
    for ci in data['items']:
        writer.writerow([cell(ci.get(key)) for key in ['source_id','name','source_system','status','location','location_id','location_resolution']])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="location-inventory.csv"','X-Record-Count':str(data['total']),'X-Observed-At':data['as_of']})


@router.get('/{location_id}/history')
async def history(location_id: str, limit: int=Query(48,ge=1,le=144),session=Depends(get_db)):
    service=LocationService(session)
    if await read(service.one_score(location_id)) is None:
        raise HTTPException(404,'Location not found')
    rows=(await read(session.scalars(select(LocationScoreSnapshot).where(LocationScoreSnapshot.location_id==location_id)
                                   .order_by(LocationScoreSnapshot.recorded_at.desc()).limit(limit)))).all()
    return envelope({'items':[dict(recorded_at=r.recorded_at.isoformat(),policy_version=r.policy_version,
                                   mapping_revision=r.mapping_revision,data=r.data) for r in rows],
                     'data_available':bool(rows),'reason':None if rows else 'No observed score snapshots yet'})
