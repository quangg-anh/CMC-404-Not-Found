from __future__ import annotations

import json
import uuid
from typing import Any
from datetime import datetime, timezone
from app.services.publish_gate import PublishGateService


_VALID_MEDIA = {"text", "image", "audio", "video"}
# Map các nhãn nghiệp vụ (article/qa/infographic/video_script) sang enum media_type của DB.
_MEDIA_ALIAS = {
    "article": "text",
    "qa": "text",
    "infographic": "image",
    "video_script": "video",
}


def _resolve_media_type(media_types: list[str] | None) -> str:
    if not media_types:
        return "text"
    first = str(media_types[0]).lower()
    if first in _VALID_MEDIA:
        return first
    return _MEDIA_ALIAS.get(first, "text")


class BriefService:
    """Service quản lý vòng đời Content Brief (`BaiTomTat`) khớp schema Data/schema/postgres/003."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        data = dict(row)
        if "id" in data and data["id"] is not None:
            data["id"] = str(data["id"])
        cits = data.get("citations")
        if isinstance(cits, str):
            try:
                cits = json.loads(cits)
            except json.JSONDecodeError:
                cits = []
        data["citations"] = cits or []
        for ts in ("created_at", "published_at", "updated_at", "archived_at"):
            if data.get(ts) is not None and hasattr(data[ts], "isoformat"):
                data[ts] = data[ts].isoformat()
        if data.get("created_by") is not None:
            data["created_by"] = str(data["created_by"])
        return data

    async def list_briefs(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Liệt kê brief trực tiếp từ bảng Postgres `briefs`."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    if status:
                        rows = await conn.fetch(
                            "SELECT id, tieu_de, media_type, status, citations, created_by, created_at, published_at "
                            "FROM briefs WHERE status = $1::brief_status ORDER BY created_at DESC LIMIT $2",
                            status,
                            limit,
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT id, tieu_de, media_type, status, citations, created_by, created_at, published_at "
                            "FROM briefs ORDER BY created_at DESC LIMIT $1",
                            limit,
                        )
                    items = [self._row_to_dict(r) for r in rows]
            except Exception:
                pass
        return items

    async def get_brief(self, brief_id: str) -> dict[str, Any] | None:
        """Lấy 1 brief từ Postgres."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM briefs WHERE id = $1::uuid", brief_id)
                    if row:
                        return self._row_to_dict(row)
            except Exception:
                pass
        return None

    async def generate_brief(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """Tạo bản nháp brief mới và ghi vào Postgres (id = UUID, khớp uuid BaiTomTat của Neo4j)."""
        brief_id = str(uuid.uuid4())
        tieu_de = payload.get("tieu_de") or "Bài tóm tắt pháp lý"
        media_type = _resolve_media_type(payload.get("media_types"))
        citations = payload.get("citations", [])
        created_at = datetime.now(timezone.utc)

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO briefs (id, tieu_de, media_type, status, citations, created_by)
                        VALUES ($1::uuid, $2, $3::media_type, 'draft', $4::jsonb, $5::uuid)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        brief_id,
                        tieu_de,
                        media_type,
                        json.dumps(citations, ensure_ascii=False),
                        user_id if _is_uuid(user_id) else None,
                    )
            except Exception:
                pass

        return {
            "id": brief_id,
            "tieu_de": tieu_de,
            "media_type": media_type,
            "status": "draft",
            "citations": citations,
            "created_by": user_id,
            "created_at": created_at.isoformat(),
        }

    async def update_brief(self, brief_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Cập nhật metadata bản nháp. KHÔNG cho đổi status ở đây — publish phải qua PublishGate."""
        item = await self.get_brief(brief_id)
        if not item:
            return None

        if updates.get("tieu_de") is not None:
            item["tieu_de"] = updates["tieu_de"]
        if updates.get("media_types") is not None:
            item["media_type"] = _resolve_media_type(updates["media_types"])
        if updates.get("citations") is not None:
            item["citations"] = updates["citations"]

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE briefs SET tieu_de = $1, media_type = $2::media_type, citations = $3::jsonb WHERE id = $4::uuid",
                        item["tieu_de"],
                        item.get("media_type", "text"),
                        json.dumps(item["citations"], ensure_ascii=False),
                        brief_id,
                    )
            except Exception:
                pass
        return item

    async def publish_brief(self, brief_id: str, actor: Any) -> tuple[bool, dict[str, Any], list[str]]:
        """Xuất bản brief qua guardrail PublishGate. Trả về (ok, data, errors)."""
        item = await self.get_brief(brief_id)
        if not item:
            return False, {}, [f"Brief {brief_id} không tồn tại."]

        gate = PublishGateService(self.pool, self.driver)
        ok, updated_brief, errors = await gate.verify_and_publish_brief(brief_id, actor, item)
        if ok:
            item.update(updated_brief)
        return ok, item, errors

    async def archive_brief(self, brief_id: str, actor: Any = None) -> dict[str, Any] | None:
        """Lưu trữ/ẩn brief."""
        item = await self.get_brief(brief_id)
        if not item:
            return None

        item["status"] = "archived"
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE briefs SET status = 'archived' WHERE id = $1::uuid", brief_id
                    )
            except Exception:
                pass
        return item


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False
