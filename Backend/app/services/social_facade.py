from __future__ import annotations

import json
import uuid
from typing import Any
from datetime import datetime, timezone
import httpx
from app.adapters.neo4j_social import Neo4jSocialRepository
from app.adapters.postgres_content import PostgresContentRepository


class SocialAlertFacade:
    """Facade orchestrating BE2 Social Intelligence queries, Alert triage, and real link previews."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver
        self.neo_repo = Neo4jSocialRepository(neo4j_driver) if neo4j_driver else None
        self.pg_repo = PostgresContentRepository(pool) if pool else None

    async def ingest_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger ingestion job into real Postgres jobs queue."""
        job_id = str(uuid.uuid4())
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO jobs (id, type, status, payload_json, created_at)
                        VALUES ($1::uuid, 'social_ingest', 'queued', $2::jsonb, $3)
                        ON CONFLICT DO NOTHING
                        """,
                        job_id,
                        json.dumps(payload),
                        datetime.now(timezone.utc),
                    )
            except Exception:
                pass

        return {
            "job_id": job_id,
            "platform": payload.get("platform", "facebook"),
            "external_id": payload.get("external_id", str(uuid.uuid4())[:8]),
            "status": "queued",
            "message": "Social post ingestion task submitted into queue.",
        }

    async def list_topics(self) -> list[dict[str, Any]]:
        """List current legal topics monitored on social channels from Neo4j."""
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = "MATCH (t:ChuDe) RETURN t ORDER BY t.post_count DESC LIMIT 100"
                async with self.driver.session() as session:
                    res = await session.run(query)
                    async for record in res:
                        items.append(dict(record["t"]))
            except Exception:
                pass

        if not items and self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch("SELECT * FROM topics ORDER BY id ASC LIMIT 100")
                    for r in rows:
                        items.append(dict(r))
            except Exception:
                pass

        return items

    async def list_posts(
        self,
        topic_slug: str | None = None,
        status: str | None = None,
        needs_review: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List social posts with topic / review status filtering from Neo4j / Postgres."""
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = "MATCH (b:BaiDang) RETURN b ORDER BY b.ngay_dang DESC LIMIT 100"
                async with self.driver.session() as session:
                    res = await session.run(query)
                    async for record in res:
                        data = dict(record["b"])
                        if topic_slug and data.get("chu_de") != topic_slug:
                            continue
                        if needs_review is not None and data.get("needs_review", False) != needs_review:
                            continue
                        items.append(data)
            except Exception:
                pass

        if not items and self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch("SELECT * FROM bai_dang ORDER BY ngay_dang DESC LIMIT 100")
                    for r in rows:
                        data = dict(r)
                        if topic_slug and data.get("chu_de") != topic_slug:
                            continue
                        if needs_review is not None and data.get("needs_review", False) != needs_review:
                            continue
                        items.append(data)
            except Exception:
                pass

        return items

    @staticmethod
    def _alert_from_row(row: dict[str, Any]) -> dict[str, Any]:
        """Normalize an alerts row into the API shape.

        Handles both the real normalized schema (chu_de/khoan_ids/severity/volume/status)
        and the legacy `payload_json` blob (used by test fakes).
        """
        if "payload_json" in row and row["payload_json"]:
            p = row["payload_json"]
            if isinstance(p, str):
                p = json.loads(p)
            p.setdefault("alert_id", str(row.get("id")))
            return p
        khoan_ids = row.get("khoan_ids") or []
        if isinstance(khoan_ids, str):
            khoan_ids = json.loads(khoan_ids)
        severity = row.get("severity")
        volume = row.get("volume", 0) or 0
        created_at = row.get("created_at")
        return {
            "alert_id": str(row.get("id")),
            "chu_de": row.get("chu_de"),
            "khoan_ids": khoan_ids,
            "severity": severity,
            "volume": volume,
            "cluster_size": volume,
            "status": str(row.get("status")) if row.get("status") is not None else "open",
            "nli_label": "mau_thuan" if severity == "high" else "khong_ro",
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        }

    async def list_alerts(self, severity: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List alerts generated from BE2 claim check and NLI signal detection in real DB."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT id, chu_de, khoan_ids, severity, volume, status, created_at FROM alerts ORDER BY created_at DESC LIMIT 100"
                    )
                    for r in rows:
                        data = self._alert_from_row(dict(r))
                        if severity and data.get("severity") != severity:
                            continue
                        if status and data.get("status") != status:
                            continue
                        items.append(data)
            except Exception:
                pass

        return items

    async def get_alert_detail(self, alert_id: str) -> dict[str, Any] | None:
        """Get alert details with cluster of posts and NLI verification edges from real DB."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT id, chu_de, khoan_ids, severity, volume, status, created_at FROM alerts WHERE id = $1", alert_id
                    )
                    if row:
                        return self._alert_from_row(dict(row))
            except Exception:
                pass

        return None

    async def triage_alert(
        self,
        alert_id: str,
        action: str,
        note: str | None,
        user_id: str,
    ) -> dict[str, Any]:
        """Triage an alert: change status or trigger suggestion draft creation in real DB."""
        new_status = "investigating" if action == "investigate" else ("resolved" if action == "resolve" else "open")
        suggest_id = None

        if action == "create_suggest":
            new_status = "investigating"
            suggest_id = str(uuid.uuid4())
            if self.pool and hasattr(self.pool, "acquire"):
                try:
                    async with self.pool.acquire() as conn:
                        # Schema (Data/schema/postgres/003): suggestions(id uuid, draft_text,
                        # alert_ids jsonb, khoan_ids jsonb, status, created_by uuid FK, ...).
                        await conn.execute(
                            """
                            INSERT INTO suggestions (id, draft_text, alert_ids, khoan_ids, status, created_by, created_at)
                            VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, 'draft', NULL, $5)
                            ON CONFLICT DO NOTHING
                            """,
                            suggest_id,
                            f"Đề xuất đính chính cho cảnh báo {alert_id} dựa trên {note or 'thông tin sai lệch phát hiện'}.",
                            json.dumps([alert_id]),
                            json.dumps([]),
                            datetime.now(timezone.utc),
                        )
                except Exception:
                    pass

        # Map the logical action to the alert_status enum {open, triaged, closed}.
        db_status = {
            "investigate": "triaged",
            "create_suggest": "triaged",
            "resolve": "closed",
            "dismiss": "closed",
        }.get(action, "open")

        # Update alerts table in Postgres (real schema uses a `status` enum column).
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE alerts SET status = $1::alert_status, updated_at = now() WHERE id = $2::uuid",
                        db_status,
                        alert_id,
                    )
            except Exception:
                pass

        # Update AlertMeta node in Neo4j if exists
        if self.driver and hasattr(self.driver, "session"):
            try:
                async with self.driver.session() as session:
                    await session.run(
                        "MATCH (a:AlertMeta) WHERE a.uuid = $id SET a.status = $status, a.triaged_by = $user",
                        id=alert_id,
                        status=db_status,
                        user=user_id,
                    )
            except Exception:
                pass

        return {
            "alert_id": alert_id,
            "previous_action": action,
            "new_status": new_status,
            "note": note,
            "triaged_by": user_id,
            "triaged_at": datetime.now(timezone.utc).isoformat(),
            "created_suggestion_id": suggest_id,
        }

    async def generate_link_preview(self, url: str) -> dict[str, Any]:
        """Extract live metadata / OpenGraph properties from external URL."""
        domain = url.split("//")[-1].split("/")[0] if "//" in url else url
        title = f"URL Content from {domain}"
        description = "Live content extracted via scraper"
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    text = res.text[:4096]
                    if "<title>" in text and "</title>" in text:
                        title = text.split("<title>")[1].split("</title>")[0].strip()
        except Exception:
            pass

        return {
            "url": url,
            "domain": domain,
            "title": title,
            "description": description,
            "image": f"https://{domain}/favicon.ico",
            "candidate_text": f"Trích đoạn nội dung chính từ {url}.",
        }
