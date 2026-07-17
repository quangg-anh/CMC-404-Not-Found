from __future__ import annotations

import json
import uuid
from typing import Any
from datetime import datetime, timezone
from app.services.publish_gate import PublishGateService


class BriefService:
    """Service managing Content Briefs (`BaiTomTat`) lifecycle without mock data."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver

    async def list_briefs(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List content briefs directly from Postgres table briefs."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    query = "SELECT id, tieu_de, tuc_danh, status, citations_json, created_by, created_at, published_at FROM briefs ORDER BY created_at DESC LIMIT $1"
                    rows = await conn.fetch(query, limit)
                    for r in rows:
                        data = {
                            "id": str(r["id"]),
                            "tieu_de": r["tieu_de"],
                            "tuc_danh": r["tuc_danh"],
                            "status": r["status"],
                            "created_by": r["created_by"],
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                        }
                        cits = r["citations_json"]
                        if isinstance(cits, str):
                            cits = json.loads(cits)
                        data["citations"] = cits or []
                        if status and data["status"] != status:
                            continue
                        items.append(data)
            except Exception:
                pass
        return items

    async def get_brief(self, brief_id: str) -> dict[str, Any] | None:
        """Fetch single brief from Postgres."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow("SELECT * FROM briefs WHERE id = $1", brief_id)
                    if row:
                        data = dict(row)
                        cits = data.pop("citations_json", None)
                        if isinstance(cits, str):
                            cits = json.loads(cits)
                        data["citations"] = cits or []
                        if data.get("created_at"):
                            data["created_at"] = data["created_at"].isoformat()
                        if data.get("published_at"):
                            data["published_at"] = data["published_at"].isoformat()
                        return data
            except Exception:
                pass
        return None

    async def generate_brief(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """Generate a new draft brief and insert into Postgres table briefs."""
        brief_id = f"brief-{uuid.uuid4().hex[:8]}"
        tieu_de = payload.get("tieu_de", "Bài tóm tắt pháp lý")
        tuc_danh = payload.get("tuc_danh", "Tóm tắt điểm mới và lưu ý quan trọng.")
        citations = payload.get("citations", [])

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO briefs (id, tieu_de, tuc_danh, status, citations_json, created_by, created_at)
                        VALUES ($1, $2, $3, 'draft', $4, $5, $6)
                        ON CONFLICT DO NOTHING
                        """,
                        brief_id,
                        tieu_de,
                        tuc_danh,
                        json.dumps(citations),
                        user_id,
                        datetime.now(timezone.utc),
                    )
            except Exception:
                pass

        return {
            "id": brief_id,
            "tieu_de": tieu_de,
            "tuc_danh": tuc_danh,
            "status": "draft",
            "citations": citations,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def update_brief(self, brief_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update brief metadata or draft status."""
        item = await self.get_brief(brief_id)
        if not item:
            return None

        for k in ["tieu_de", "tuc_danh", "status"]:
            if k in updates and updates[k] is not None:
                item[k] = updates[k]
        if "citations" in updates and updates["citations"] is not None:
            item["citations"] = updates["citations"]

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE briefs SET tieu_de = $1, tuc_danh = $2, status = $3, citations_json = $4 WHERE id = $5",
                        item["tieu_de"],
                        item["tuc_danh"],
                        item["status"],
                        json.dumps(item["citations"]),
                        brief_id,
                    )
            except Exception:
                pass
        return item

    async def publish_brief(self, brief_id: str, user_token: Any) -> dict[str, Any]:
        """Publish a brief via PublishGate guardrail."""
        item = await self.get_brief(brief_id)
        if not item:
            raise ValueError(f"Brief {brief_id} không tồn tại.")

        gate = PublishGateService(self.pool, self.driver)
        ok, updated_brief, errors = await gate.verify_and_publish_brief(brief_id, user_token, item)
        if not ok:
            raise ValueError("; ".join(errors) or f"Không thể xuất bản Brief {brief_id}.")

        item.update(updated_brief)
        return item

    async def archive_brief(self, brief_id: str) -> dict[str, Any] | None:
        """Archive a brief."""
        item = await self.get_brief(brief_id)
        if not item:
            return None

        item["status"] = "archived"
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE briefs SET status = 'archived' WHERE id = $1", brief_id)
            except Exception:
                pass
        return item
