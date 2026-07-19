from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from datetime import datetime, timezone

from app.exceptions import BriefPersistenceError, BriefConflictError
from app.services.publish_gate import PublishGateService

logger = logging.getLogger(__name__)

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

    _noi_dung_ready: bool = False

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver

    async def _ensure_noi_dung_column(self, conn: Any) -> None:
        if BriefService._noi_dung_ready:
            return
        try:
            await conn.execute("ALTER TABLE briefs ADD COLUMN IF NOT EXISTS noi_dung TEXT")
            BriefService._noi_dung_ready = True
        except Exception:
            logger.warning("Could not ensure briefs.noi_dung column", exc_info=True)

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

    # ── Read operations: best-effort — log on failure, return empty ──

    async def list_briefs(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Liệt kê brief trực tiếp từ bảng Postgres `briefs`."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await self._ensure_noi_dung_column(conn)
                    if status:
                        rows = await conn.fetch(
                            "SELECT id, tieu_de, noi_dung, media_type, status, citations, created_by, created_at, published_at "
                            "FROM briefs WHERE status = $1::brief_status ORDER BY created_at DESC LIMIT $2",
                            status,
                            limit,
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT id, tieu_de, noi_dung, media_type, status, citations, created_by, created_at, published_at "
                            "FROM briefs ORDER BY created_at DESC LIMIT $1",
                            limit,
                        )
                    items = [self._row_to_dict(r) for r in rows]
            except Exception:
                # Nhóm 3 — best-effort read: log warning, return empty list
                logger.warning("Failed to list briefs from Postgres", exc_info=True, extra={"operation": "list_briefs"})
        return items

    async def get_brief(self, brief_id: str) -> dict[str, Any] | None:
        """Lấy 1 brief từ Postgres."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await self._ensure_noi_dung_column(conn)
                    row = await conn.fetchrow("SELECT * FROM briefs WHERE id = $1::uuid", brief_id)
                    if row:
                        return self._row_to_dict(row)
            except Exception:
                # Nhóm 3 — best-effort read
                logger.warning("Failed to get brief %s from Postgres", brief_id, exc_info=True, extra={"operation": "get_brief", "brief_id": brief_id})
        return None

    # ── Write operations: MUST propagate errors — no false success ──

    async def generate_brief(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """Tạo bản nháp brief mới và ghi vào Postgres (id = UUID, khớp uuid BaiTomTat của Neo4j)."""
        brief_id = str(uuid.uuid4())
        tieu_de = payload.get("tieu_de") or "Bài tóm tắt pháp lý"
        noi_dung = payload.get("noi_dung") or ""
        media_type = _resolve_media_type(payload.get("media_types"))
        citations = payload.get("citations", [])
        created_at = datetime.now(timezone.utc)

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await self._ensure_noi_dung_column(conn)
                    await conn.execute(
                        """
                        INSERT INTO briefs (id, tieu_de, noi_dung, media_type, status, citations, created_by)
                        VALUES ($1::uuid, $2, $3, $4::media_type, 'draft', $5::jsonb, $6::uuid)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        brief_id,
                        tieu_de,
                        noi_dung,
                        media_type,
                        json.dumps(citations, ensure_ascii=False),
                        user_id if _is_uuid(user_id) else None,
                    )
            except Exception as exc:
                logger.exception(
                    "Failed to INSERT brief into Postgres",
                    extra={"operation": "generate_brief", "brief_id": brief_id},
                )
                raise BriefPersistenceError(
                    "Không thể tạo bản tóm tắt. Vui lòng thử lại.",
                    details={"brief_id": brief_id},
                ) from exc
        else:
            raise BriefPersistenceError(
                "Không thể tạo bản tóm tắt: Postgres không khả dụng.",
                details={"brief_id": brief_id},
            )

        return {
            "id": brief_id,
            "tieu_de": tieu_de,
            "noi_dung": noi_dung,
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
        if updates.get("noi_dung") is not None:
            item["noi_dung"] = updates["noi_dung"]
        if updates.get("media_types") is not None:
            item["media_type"] = _resolve_media_type(updates["media_types"])
        if updates.get("citations") is not None:
            item["citations"] = updates["citations"]

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await self._ensure_noi_dung_column(conn)
                    await conn.execute(
                        """
                        UPDATE briefs
                           SET tieu_de = $1,
                               noi_dung = $2,
                               media_type = $3::media_type,
                               citations = $4::jsonb
                         WHERE id = $5::uuid
                        """,
                        item["tieu_de"],
                        item.get("noi_dung") or "",
                        item.get("media_type", "text"),
                        json.dumps(item["citations"], ensure_ascii=False),
                        brief_id,
                    )
            except Exception as exc:
                logger.exception(
                    "Failed to UPDATE brief in Postgres",
                    extra={"operation": "update_brief", "brief_id": brief_id},
                )
                raise BriefPersistenceError(
                    "Không thể cập nhật bản tóm tắt.",
                    details={"brief_id": brief_id},
                ) from exc
        else:
            raise BriefPersistenceError(
                "Không thể cập nhật bản tóm tắt: Postgres không khả dụng.",
                details={"brief_id": brief_id},
            )
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
            except Exception as exc:
                logger.exception(
                    "Failed to archive brief in Postgres",
                    extra={"operation": "archive_brief", "brief_id": brief_id},
                )
                raise BriefPersistenceError(
                    "Không thể lưu trữ bản tóm tắt.",
                    details={"brief_id": brief_id},
                ) from exc
        else:
            raise BriefPersistenceError(
                "Không thể lưu trữ bản tóm tắt: Postgres không khả dụng.",
                details={"brief_id": brief_id},
            )
        return item

    async def delete_brief(self, brief_id: str) -> dict[str, Any] | None:
        """Xóa hẳn brief khỏi Postgres."""
        item = await self.get_brief(brief_id)
        if not item:
            return None

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute("DELETE FROM briefs WHERE id = $1::uuid", brief_id)
            except Exception as exc:
                logger.exception(
                    "Failed to DELETE brief from Postgres",
                    extra={"operation": "delete_brief", "brief_id": brief_id},
                )
                raise BriefPersistenceError(
                    "Không thể xóa bản tóm tắt.",
                    details={"brief_id": brief_id},
                ) from exc
        else:
            raise BriefPersistenceError(
                "Không thể xóa bản tóm tắt: Postgres không khả dụng.",
                details={"brief_id": brief_id},
            )
        return item


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False
