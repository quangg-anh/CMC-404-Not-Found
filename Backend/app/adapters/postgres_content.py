from __future__ import annotations

import json
from typing import Any
from uuid import uuid4
from app.schemas import BriefDraft, SuggestDraft


class PostgresContentRepository:
    """Async SQL adapter for BE2 draft metadata. Uses existing tables from Data/SYSTEM_DATA.md."""

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def save_brief(self, draft: BriefDraft) -> str:
        brief_id = str(draft.audit.get("uuid") or draft.audit.get("brief_id") or uuid4())
        query = """
        INSERT INTO briefs (id, tieu_de, media_type, status, citations)
        VALUES ($1::uuid, $2, $3::media_type, $4::brief_status, $5::jsonb)
        ON CONFLICT (id) DO UPDATE SET
          tieu_de = EXCLUDED.tieu_de,
          media_type = EXCLUDED.media_type,
          status = EXCLUDED.status,
          citations = EXCLUDED.citations
        RETURNING id
        """
        citations = json.dumps([citation.model_dump(mode="json") for citation in draft.citations], ensure_ascii=False)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, brief_id, draft.title, "text", _brief_status(draft.status.value), citations)
        return str(row["id"]) if row else brief_id

    async def save_suggestion(self, draft: SuggestDraft) -> str:
        suggestion_id = str(draft.audit.get("uuid") or draft.audit.get("suggestion_id") or uuid4())
        query = """
        INSERT INTO suggestions (id, draft_text, alert_ids, khoan_ids, claim_labels, status)
        VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6::dexuat_status)
        ON CONFLICT (id) DO UPDATE SET
          draft_text = EXCLUDED.draft_text,
          alert_ids = EXCLUDED.alert_ids,
          khoan_ids = EXCLUDED.khoan_ids,
          claim_labels = EXCLUDED.claim_labels,
          status = EXCLUDED.status
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, suggestion_id, draft.draft_content, json.dumps(draft.related_alert_ids, ensure_ascii=False), json.dumps(draft.related_khoan_ids, ensure_ascii=False), json.dumps([citation.model_dump(mode="json") for citation in draft.citations], ensure_ascii=False), _suggestion_status(draft.status.value))
        return str(row["id"]) if row else suggestion_id

    async def load_alerts(self, alert_ids: list[str]) -> list[dict[str, Any]]:
        query = "SELECT id, chu_de, khoan_ids, severity, volume, status, created_at FROM alerts WHERE id = ANY($1::uuid[])"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, alert_ids)
        alerts: list[dict[str, Any]] = []
        for row in rows:
            khoan_ids = row["khoan_ids"] or []
            if isinstance(khoan_ids, str):
                khoan_ids = json.loads(khoan_ids)
            alerts.append({
                "alert_id": str(row["id"]),
                "chu_de": row["chu_de"],
                "khoan_ids": khoan_ids,
                "severity": row["severity"],
                "volume": row["volume"],
                "status": row["status"],
                "created_at": row["created_at"],
            })
        return alerts

def _brief_status(status: str) -> str:
    return "review" if status == "needs_review" else status

def _suggestion_status(status: str) -> str:
    return "draft" if status == "needs_review" else status
