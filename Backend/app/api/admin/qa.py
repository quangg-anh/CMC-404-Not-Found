from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.deps import get_neo4j_driver, get_qdrant_client, get_llm_router, get_embedder, get_redis, require_admin, UserToken
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.qa_factory import build_qa_service

router = APIRouter(tags=["Admin QA"], dependencies=[Depends(require_admin())])


class QARequest(BaseModel):
    question: str = Field(..., min_length=2, description="Câu hỏi pháp lý/nghiệp vụ")
    graph_paths_enabled: bool = Field(default=True, description="Cho phép trả về đường dẫn đồ thị quan hệ")
    audience: str = Field(default="admin", description="Đối tượng nhận câu trả lời")
    as_of: str | None = Field(default=None, description="Thời điểm áp dụng luật (YYYY-MM-DD). Mặc định: hôm nay.")


@router.post("/qa/ask", summary="Hỏi đáp thông minh (RAG QA) cho Admin với citation và đồ thị")
async def ask_admin_qa(
    request: QARequest,
    driver: Any = Depends(get_neo4j_driver),
    qdrant: Any = Depends(get_qdrant_client),
    router_llm: Any = Depends(get_llm_router),
    embedder: Any = Depends(get_embedder),
    redis_pool: Any = Depends(get_redis),
    user: UserToken = Depends(require_admin()),
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
        audience="admin",
        graph_paths_enabled=request.graph_paths_enabled,
        as_of=request.as_of,
    )
    return success_response(data=res, request_id=get_request_id())
