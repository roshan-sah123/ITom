"""Local-only mapping decisions; upstream source systems remain read-only."""
import ipaddress
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.api.v1.endpoints.locations import read, envelope
from app.services.location_review_service import LocationReviewService, ReviewConflict

router=APIRouter(prefix='/locations/reviews',tags=['Location reviews'])


def local_client(request):
    try:
        return bool(request.client and ipaddress.ip_address(request.client.host).is_loopback
                    and request.url.hostname in {'localhost','127.0.0.1','::1'})
    except ValueError:
        return False


def require_local_review(request: Request):
    if not local_client(request):
        raise HTTPException(403,'Mapping decisions are available only on the local portal until sign-in is configured')
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Submit mapping decisions from this portal origin')
    if request.headers.get('sec-fetch-site')=='cross-site':
        raise HTTPException(403,'Cross-site mapping decisions are forbidden')


class ReviewDecision(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,extra='forbid')
    status: Literal['PENDING','APPROVED','REJECTED']
    reviewer: str=Field(min_length=1,max_length=128)
    location_id: Optional[str]=Field(default=None,min_length=1,max_length=64)
    expected_revision: str=Field(min_length=1,max_length=64)
    comment: Optional[str]=Field(default=None,max_length=512)


@router.get('/rules')
async def rules(request: Request, status: Optional[Literal['PENDING','APPROVED','REJECTED']]=None,
                source: Optional[Literal['INTUNE','SOLARWINDS']]=None,
                search: str=Query('',max_length=255),page: int=Query(1,ge=1),
                page_size: int=Query(25,ge=1,le=100),session=Depends(get_db)):
    data=await read(LocationReviewService(session).queue(status,source,search,page,page_size))
    data['write_enabled']=local_client(request)
    return envelope(data)


@router.get('/rules/{rule_id}/history')
async def history(rule_id: str,session=Depends(get_db)):
    return envelope(await read(LocationReviewService(session).history(rule_id)))


@router.post('/rules/{rule_id}/decision',dependencies=[Depends(require_local_review)])
async def decision(rule_id: str,body: ReviewDecision,session=Depends(get_db)):
    try:
        data=await LocationReviewService(session).decide(rule_id,body.status,body.reviewer,body.location_id,
                                                       body.expected_revision,body.comment)
        return envelope(data)
    except ReviewConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except (SQLAlchemyError,RuntimeError) as exc:
        raise HTTPException(503,'Mapping decision could not be saved; no changes were applied') from exc
