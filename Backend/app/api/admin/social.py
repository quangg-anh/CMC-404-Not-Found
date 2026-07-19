from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.api.deps import get_db_pool, get_neo4j_driver, require_admin, UserToken
from app.core.envelope import success_response
from app.core.logging import get_request_id
from app.services.social_facade import SocialAlertFacade

router = APIRouter(tags=["Admin Social"], dependencies=[Depends(require_admin())])


class IngestSocialRequest(BaseModel):
    platform: str = Field(..., description="Nền tảng MXH hoặc báo chí: facebook, tiktok, news, forum")
    url: str = Field(..., description="Đường dẫn bài đăng")
    noi_dung: str = Field(..., description="Nội dung bài đăng/video description")
    tac_gia: str | None = Field(default=None, description="Tên tài khoản/Tác giả")
    external_id: str | None = Field(default=None, description="ID bài viết trên nền tảng gốc")


class LinkPreviewRequest(BaseModel):
    url: str = Field(..., description="Đường dẫn URL cần trích xuất preview metadata")

class CrawlSocialRequest(BaseModel):
    topics: list[str] | None = Field(default=None, description="Chủ đề cần crawl. Bỏ trống sẽ dùng BE2_SOCIAL_MONITOR_TOPICS")
    platforms: list[str] = Field(default_factory=lambda: ["youtube"], description="Nguồn crawl: youtube, facebook, forum")
    limit_per_topic: int | None = Field(default=None, ge=1, le=50, description="Số video/bài tối đa mỗi chủ đề")
    dry_run: bool = Field(default=False, description="Chỉ thu thập thử, không ghi DB")


class ReprocessSocialRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500, description="Số BaiDang cũ tối đa cần chạy lại claim/NLI")
    only_missing_doi_chieu: bool = Field(
        default=True,
        description="Chỉ xử lý bài chưa có DOI_CHIEU (dữ liệu crawl trước khi pipeline được nối)",
    )
    dry_run: bool = Field(default=False, description="Chỉ liệt kê bài sẽ xử lý, không ghi")


@router.post("/ingest/social", summary="Đẩy bài đăng MXH vào pipeline BE2")
async def ingest_social(
    request: IngestSocialRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
    user: UserToken = Depends(require_admin()),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    res = await facade.ingest_post(request.model_dump())
    return success_response(data=res, request_id=get_request_id())


@router.get("/social/topics", summary="Danh sách chủ đề pháp lý đang giám sát trên MXH")
async def list_social_topics(
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    items = await facade.list_topics()
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.get("/social/clarity-index", summary="Chỉ số mù mờ pháp lý theo chủ đề (từ radar MXH)")
async def social_clarity_index(
    min_volume: int = 1,
    limit: int = 50,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    data = await facade.clarity_index_by_topic(min_volume=min_volume, limit=limit)
    return success_response(data=data, request_id=get_request_id())


@router.get("/social/posts", summary="Danh sách bài đăng MXH đã thu thập")
async def list_social_posts(
    topic: str | None = None,
    status: str | None = None,
    needs_review: bool | None = None,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    items = await facade.list_posts(topic_slug=topic, status=status, needs_review=needs_review)
    return success_response(data={"items": items, "total": len(items)}, request_id=get_request_id())


@router.post("/social/crawl", summary="Crawl MXH thật từ token đã cấu hình")
async def crawl_social(
    request: CrawlSocialRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    data = await facade.crawl_social(
        topics=request.topics,
        platforms=request.platforms,
        limit_per_topic=request.limit_per_topic,
        dry_run=request.dry_run,
    )
    return success_response(data=data, request_id=get_request_id())


@router.post(
    "/social/reprocess",
    summary="Chạy lại claim/NLI/alert trên BaiDang đã có trong Neo4j (dữ liệu crawl cũ)",
)
async def reprocess_social(
    request: ReprocessSocialRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    data = await facade.reprocess_existing_posts(
        limit=request.limit,
        only_missing_doi_chieu=request.only_missing_doi_chieu,
        dry_run=request.dry_run,
    )
    return success_response(data=data, request_id=get_request_id())


@router.post("/social/link-preview", summary="Trích xuất metadata & xem trước nội dung URL")
@router.post("/link/preview", summary="Trích xuất metadata & xem trước nội dung URL (Alias khớp bảng §5.2)")
async def link_preview(
    request: LinkPreviewRequest,
    pool: Any = Depends(get_db_pool),
    driver: Any = Depends(get_neo4j_driver),
) -> dict[str, Any]:
    facade = SocialAlertFacade(pool=pool, neo4j_driver=driver)
    data = await facade.generate_link_preview(request.url)
    return success_response(data=data, request_id=get_request_id())
