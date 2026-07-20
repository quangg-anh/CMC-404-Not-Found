from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_temporal_law_service, require_admin
from app.config import BE2Config, get_config
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.temporal_law_service import TemporalLawService

router = APIRouter(tags=["Admin Temporal Law"], dependencies=[Depends(require_admin())])


def _require_temporal_v2(config: BE2Config) -> None:
    if not (config.legal_provision_v2_read and config.temporal_law_v2):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporal legal API is disabled")


@router.get("/legal/provisions/compare", summary="Compare two immutable versions of one provision")
async def compare_legal_versions(
    old_id: str = Query(..., min_length=1),
    new_id: str = Query(..., min_length=1),
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.compare_versions(old_id, new_id, audience="admin")
    return success_response(data=result, request_id=get_request_id())


@router.get("/legal/documents/{document_id:path}/as-of", summary="Read the deepest effective provisions on a date")
async def legal_document_as_of(
    document_id: str,
    as_of: date = Query(..., alias="date"),
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.law_as_of(as_of, logical_vb_id=document_id, audience="admin")
    return success_response(data=result, request_id=get_request_id())


@router.get("/legal/provisions/{identifier:path}/timeline", summary="Read the immutable timeline of a provision")
async def legal_provision_timeline(
    identifier: str,
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.timeline(identifier, audience="admin")
    return success_response(data=result, request_id=get_request_id())
