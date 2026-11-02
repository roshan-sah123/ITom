import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.api.v1.endpoints.module_access import require_local_module, require_inventory_key
from app.api.v1.endpoints.vendors import file_response, operation
from app.core.database import get_module_db
from app.services.knowledge_service import KnowledgeInput, KnowledgeService
from frontend.vendor_management_server import reject_constant, unique_object


def local_knowledge(request: Request):
    require_local_module(request, "Knowledge Centre")


def knowledge_validator(request: Request):
    require_inventory_key(request, "Knowledge Centre")


router = APIRouter(prefix="/knowledge/content", tags=["Knowledge content"], dependencies=[Depends(local_knowledge)])


class KnowledgeReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reviewer: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1, strict=True)


async def json_body(request: Request, schema, limit):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "Send application/json.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            raise HTTPException(413, f"Knowledge request exceeds {limit // 1024} KiB.")
    try:
        return schema.model_validate(json.loads(raw.decode("utf-8"), parse_constant=reject_constant,
                                                        object_pairs_hook=unique_object))
    except (ValidationError, ValueError, UnicodeError, RecursionError) as error:
        raise HTTPException(422, "Provide valid content/reviewer details, revision and a non-empty file up to 5 MiB.") from error


async def content_body(request: Request):
    return await json_body(request, KnowledgeInput, 7 * 1024 * 1024)


async def review_body(request: Request):
    return await json_body(request, KnowledgeReview, 16 * 1024)


@router.get("")
async def list_content(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100), session=Depends(get_module_db)):
    return await operation(KnowledgeService(session).list(page, page_size), session, label="Knowledge")


@router.post("", status_code=201)
async def create_content(body=Depends(content_body), session=Depends(get_module_db)):
    return await operation(KnowledgeService(session).create(body), session, write=True, label="Knowledge")


@router.put("/{identifier}", dependencies=[Depends(knowledge_validator)])
async def edit_content(identifier: int, body=Depends(content_body), session=Depends(get_module_db)):
    return await operation(KnowledgeService(session).edit(identifier, body), session, write=True, label="Knowledge")


@router.post("/{identifier}/validate", dependencies=[Depends(knowledge_validator)])
async def validate_content(identifier: int, body=Depends(review_body), session=Depends(get_module_db)):
    return await operation(KnowledgeService(session).validate(identifier, body), session, write=True, label="Knowledge")


@router.delete("/{identifier}", status_code=204, dependencies=[Depends(knowledge_validator)])
async def delete_content(identifier: int, expected_revision: int = Query(..., ge=1), session=Depends(get_module_db)):
    await operation(KnowledgeService(session).delete(identifier, expected_revision), session, write=True, label="Knowledge")
    return Response(status_code=204)


@router.get("/{identifier}/file")
async def download_content(identifier: int, session=Depends(get_module_db)):
    row = await operation(KnowledgeService(session).get(identifier, file=True), session, label="Knowledge")
    return file_response({"name": row.file_name, "mime": row.file_type}, raw=row.file_data, download_only=True)
