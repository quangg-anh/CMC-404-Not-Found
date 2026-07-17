from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query
from app.api.deps import get_neo4j_driver, require_admin
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.graph_query import GraphQueryService

router = APIRouter(tags=["Admin Graph"], dependencies=[Depends(require_admin())])


@router.get("/graph/neighborhood", summary="Khám phá láng giềng đồ thị (Graph Neighborhood Explorer)")
async def get_graph_neighborhood(
    seed_id: str = Query(..., description="ID nút gốc (khoan_id, vb_id, slug, bai_dang_id, hoặc internal neo4j id)"),
    depth: int = Query(default=1, ge=1, le=2, description="Bán kính mở rộng (tối đa 2 hops)"),
    limit: int = Query(default=100, ge=1, le=300, description="Số lượng nút tối đa trả về"),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    service = GraphQueryService(driver=driver)
    res = await service.get_neighborhood(seed_id=seed_id, depth=depth, limit=limit)
    return success_response(data=res, request_id=get_request_id())


@router.get("/graph/clarity-index", summary="Chỉ số Mù mờ Pháp lý (Legal Clarity Index)")
async def get_clarity_index(
    min_volume: int = Query(default=5, ge=1, le=1000, description="Ngưỡng số lượt đối chiếu tối thiểu để tính"),
    limit: int = Query(default=50, ge=1, le=200, description="Số Khoản trả về"),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    """Xếp hạng các Khoản đang bị hiểu sai nhiều nhất (mâu thuẫn/không rõ) dựa trên DOI_CHIEU."""
    service = GraphQueryService(driver=driver)
    res = await service.clarity_index(min_volume=min_volume, limit=limit)
    return success_response(data=res, request_id=get_request_id())
