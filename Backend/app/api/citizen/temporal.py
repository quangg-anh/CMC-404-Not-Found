from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_temporal_law_service
from app.config import BE2Config, get_config
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.temporal_law_service import TemporalLawService

router = APIRouter(tags=["Citizen Temporal Law"])


def _require_temporal_v2(config: BE2Config) -> None:
    if not (config.legal_provision_v2_read and config.temporal_law_v2):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporal legal API is disabled")


@router.get("/legal/provisions/compare", summary="Compare two public immutable versions")
async def compare_public_legal_versions(
    old_id: str = Query(..., min_length=1),
    new_id: str = Query(..., min_length=1),
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.compare_versions(old_id, new_id, audience="citizen")
    return success_response(data=result, request_id=get_request_id())


@router.get("/legal/provisions/{identifier:path}/timeline", summary="Read the public immutable timeline")
async def citizen_legal_provision_timeline(
    identifier: str,
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.timeline(identifier, audience="citizen")
    return success_response(data=result, request_id=get_request_id())


@router.get("/legal/provisions/{identifier:path}", summary="Read the public version effective on a date")
async def citizen_legal_provision(
    identifier: str,
    as_of: date | None = Query(default=None),
    config: BE2Config = Depends(get_config),
    service: TemporalLawService = Depends(get_temporal_law_service),
) -> dict[str, Any]:
    _require_temporal_v2(config)
    result = await service.get_provision(identifier, as_of=as_of, audience="citizen")
    return success_response(data=result, request_id=get_request_id())
