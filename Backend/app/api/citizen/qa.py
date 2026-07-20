from __future__ import annotations

from datetime import date
from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.deps import get_neo4j_driver, get_qdrant_client, get_llm_router, get_embedder, get_redis
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.qa_factory import build_qa_service

router = APIRouter(tags=["Citizen QA"])


class CitizenQARequest(BaseModel):
    question: str = Field(..., min_length=2, description="Câu hỏi pháp lý đời thường")
    as_of: date | None = Field(
        default=None,
        description="Thời điểm áp dụng luật (YYYY-MM-DD). Mặc định: hôm nay. Dùng cho hành vi xảy ra trong quá khứ.",
    )


@router.post("/qa/ask", summary="Trợ lý ảo hỏi đáp pháp lý cho người dân (có trích dẫn)")
async def ask_citizen_qa(
    request: CitizenQARequest,
    driver: Any = Depends(get_neo4j_driver),
    qdrant: Any = Depends(get_qdrant_client),
    router_llm: Any = Depends(get_llm_router),
    embedder: Any = Depends(get_embedder),
    redis_pool: Any = Depends(get_redis),
) -> dict[str, Any]:
    service = build_qa_service(
        qdrant_client=qdrant,
        neo4j_driver=driver,
        llm_router=router_llm,
        embedder=embedder,
        redis_pool=redis_pool,
    )
    res = await service.answer(
        question=request.question,
        audience="citizen",
        graph_paths_enabled=False,
        as_of=request.as_of.isoformat() if request.as_of else None,
    )
    return success_response(data=res, request_id=get_request_id())
