from __future__ import annotations

import json
import uuid
from typing import Any
from datetime import datetime, timezone


class SuggestService:
    """Service managing Suggestion (`DeXuatDinhChinh`) lifecycle (`draft -> ready -> exported`) without mock data."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver

    @staticmethod
    def _row_to_suggestion(row: dict[str, Any]) -> dict[str, Any]:
        def _json(val: Any) -> Any:
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return val
            return val

        created_at = row.get("created_at")
        return {
            "id": str(row.get("id")),
            "draft_text": row.get("draft_text"),
            "alert_ids": _json(row.get("alert_ids")) or [],
            "khoan_ids": _json(row.get("khoan_ids")) or [],
            "claim_labels": _json(row.get("claim_labels")) or [],
            "status": str(row.get("status")) if row.get("status") is not None else "draft",
            "created_by": str(row["created_by"]) if row.get("created_by") else None,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        }

    async def list_suggestions(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List suggestions directly from Postgres table suggestions."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    query = "SELECT id, draft_text, alert_ids, khoan_ids, claim_labels, status, created_by, created_at FROM suggestions ORDER BY created_at DESC LIMIT $1"
                    rows = await conn.fetch(query, limit)
                    for r in rows:
                        data = self._row_to_suggestion(dict(r))
                        if status and data["status"] != status:
                            continue
                        items.append(data)
            except Exception:
                pass
        return items

    async def get_suggestion(self, suggest_id: str) -> dict[str, Any] | None:
        """Get single suggestion details from Postgres."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT id, draft_text, alert_ids, khoan_ids, claim_labels, status, created_by, created_at FROM suggestions WHERE id = $1::uuid",
                        suggest_id,
                    )
                    if row:
                        return self._row_to_suggestion(dict(row))
            except Exception:
                pass
        return None

    async def generate_suggestion(self, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
        """Generate a new suggestion draft and insert into real Postgres (schema 003)."""
        suggest_id = str(uuid.uuid4())
        tieu_de = payload.get("tieu_de") or "Đề xuất đính chính tự động"
        noi_dung = payload.get("noi_dung_dinh_chinh") or "Nội dung đính chính chuẩn hóa dựa trên trích dẫn pháp lý chính thức."
        draft_text = f"{tieu_de}\n\n{noi_dung}".strip()
        khoan_ids = [payload["khoan_doi_chieu_id"]] if payload.get("khoan_doi_chieu_id") else []

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO suggestions (id, draft_text, alert_ids, khoan_ids, claim_labels, status, created_by, created_at)
                        VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, '[]'::jsonb, 'draft'::dexuat_status, NULL, $5)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        suggest_id,
                        draft_text,
                        json.dumps([]),
                        json.dumps(khoan_ids),
                        datetime.now(timezone.utc),
                    )
            except Exception:
                pass

        return {
            "id": suggest_id,
            "draft_text": draft_text,
            "alert_ids": [],
            "khoan_ids": khoan_ids,
            "claim_labels": [],
            "status": "draft",
            "created_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    async def update_suggestion(self, suggest_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update suggestion content or status (`draft -> ready -> exported`)."""
        suggest = await self.get_suggestion(suggest_id)
        if not suggest:
            return None

        # Guardrail: Suggestions can never be 'published' (not a valid dexuat_status either).
        if updates.get("status") == "published":
            raise ValueError("Guardrail Violation: Suggestions (DeXuatDinhChinh) cannot be published directly to Citizen Portal.")

        if updates.get("tieu_de") or updates.get("noi_dung_dinh_chinh"):
            tieu_de = updates.get("tieu_de") or ""
            noi_dung = updates.get("noi_dung_dinh_chinh") or ""
            suggest["draft_text"] = f"{tieu_de}\n\n{noi_dung}".strip() or suggest["draft_text"]
        if updates.get("khoan_doi_chieu_id"):
            suggest["khoan_ids"] = [updates["khoan_doi_chieu_id"]]
        if updates.get("status"):
            suggest["status"] = updates["status"]

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE suggestions SET draft_text = $1, khoan_ids = $2::jsonb, status = $3::dexuat_status WHERE id = $4::uuid",
                        suggest["draft_text"],
                        json.dumps(suggest["khoan_ids"]),
                        suggest["status"],
                        suggest_id,
                    )
            except Exception:
                pass

        return suggest
