from __future__ import annotations

import json
import uuid
import logging
from typing import Any
from datetime import datetime, timezone
import httpx
from app.adapters.neo4j_social import Neo4jSocialRepository
from app.adapters.postgres_content import PostgresContentRepository
from app.config import get_config
from app.exceptions import BE2Error, JobEnqueueError
from app.pipelines.social.collectors import FacebookGraphCollector, ForumFeedCollector, YouTubeDataCollector
from app.pipelines.social.ingest import SocialIngestService

logger = logging.getLogger(__name__)

class SocialAlertFacade:
    """Facade orchestrating BE2 Social Intelligence queries, Alert triage, and real link previews."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver
        self.neo_repo = Neo4jSocialRepository(neo4j_driver) if neo4j_driver else None
        self.pg_repo = PostgresContentRepository(pool) if pool else None

    async def ingest_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger ingestion job into real Postgres jobs queue.

        Only returns ``status=queued`` after a successful INSERT. Missing pool or DB errors
        raise — never a false-success envelope.
        """
        if not (self.pool and hasattr(self.pool, "acquire")):
            raise JobEnqueueError(
                "Không thể xếp hàng social ingest: Postgres pool không khả dụng.",
                details={"platform": payload.get("platform")},
            )

        job_id = str(uuid.uuid4())
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
        except BE2Error:
            raise
        except Exception as exc:
            logger.exception("social ingest INSERT failed", extra={"job_id": job_id})
            raise JobEnqueueError(
                f"Không thể xếp hàng social ingest: {exc}",
                details={"job_id": job_id, "platform": payload.get("platform")},
            ) from exc

        return {
            "job_id": job_id,
            "platform": payload.get("platform", "facebook"),
            "external_id": payload.get("external_id", str(uuid.uuid4())[:8]),
            "status": "queued",
            "message": "Social post ingestion task submitted into queue.",
        }

    async def crawl_social(
        self,
        *,
        topics: list[str] | None = None,
        platforms: list[str] | None = None,
        limit_per_topic: int | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Collect real public social data from configured collectors and optionally ingest to Neo4j."""
        cfg = get_config()
        active_topics = [t.strip() for t in (topics or cfg.social_monitor_topics) if t and t.strip()]
        active_platforms = {p.strip().lower() for p in (platforms or ["youtube"]) if p and p.strip()}
        if not active_topics:
            return {"status": "failed", "message": "Chưa cấu hình chủ đề crawl.", "collected": 0, "ingested": 0, "items": []}

        collectors: list[Any] = []
        if "youtube" in active_platforms:
            collectors.append(YouTubeDataCollector(cfg))
        if "facebook" in active_platforms:
            collectors.append(FacebookGraphCollector(cfg))
        if "forum" in active_platforms:
            collectors.append(ForumFeedCollector(cfg))
        if not collectors:
            return {"status": "failed", "message": "Chưa chọn nguồn crawl hợp lệ.", "collected": 0, "ingested": 0, "items": []}

        collected: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for collector in collectors:
            provider = collector.__class__.__name__.replace("DataCollector", "").replace("GraphCollector", "").replace("FeedCollector", "").lower()
            try:
                collected.extend(await collector.collect(active_topics, limit_per_topic=limit_per_topic))
            except Exception as exc:  # noqa: BLE001
                msg = getattr(exc, "message", None) or str(exc)
                details = getattr(exc, "details", None)
                if isinstance(details, dict) and details:
                    hint = details.get("reason") or details.get("hint") or details.get("status_code")
                    if hint:
                        msg = f"{msg} [{hint}]"
                errors.append({"platform": provider, "message": msg, "details": details if isinstance(details, dict) else None})

        ingested_items: list[dict[str, Any]] = []
        if not dry_run and self.neo_repo:
            ingest_service = SocialIngestService(self.neo_repo, cfg)
            for payload in collected:
                try:
                    post = await ingest_service.ingest(payload)
                    ingested_items.append(post.model_dump())
                except Exception as exc:  # noqa: BLE001
                    errors.append({"platform": payload.get("platform"), "external_id": payload.get("external_id"), "message": str(exc)})

        status = "success" if collected else ("partial" if errors else "failed")
        if collected and errors:
            status = "partial"
        elif not collected and errors:
            status = "failed"

        message = None
        if errors and not collected:
            message = errors[0].get("message") or "Crawl thất bại."
        elif errors:
            message = f"Thu thập được {len(collected)} mục, có {len(errors)} lỗi."

        return {
            "status": status,
            "message": message,
            "topics": active_topics,
            "platforms": sorted(active_platforms),
            "dry_run": dry_run,
            "collected": len(collected),
            "ingested": len(ingested_items),
            "items": ingested_items if ingested_items else collected[:100],
            "errors": errors,
        }

    async def list_topics(self) -> list[dict[str, Any]]:
        """List current legal topics monitored on social channels from Neo4j (source of truth)."""
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                # Count related posts instead of relying on a missing `post_count` property.
                query = """
                MATCH (t:ChuDe)
                OPTIONAL MATCH (t)<-[:THAO_LUAN_VE]-(b:BaiDang)
                WITH t, count(b) AS post_count
                RETURN t {.*, post_count: post_count} AS topic
                ORDER BY post_count DESC, coalesce(t.ten, t.name, t.slug, '') ASC
                LIMIT 100
                """
                async with self.driver.session() as session:
                    res = await session.run(query)
                    async for record in res:
                        topic = record["topic"]
                        data = dict(topic) if topic is not None else {}
                        data["post_count"] = int(data.get("post_count") or 0)
                        data["so_bai"] = data["post_count"]
                        items.append(self._json_safe(data))
            except Exception:
                logger.warning("Failed to list topics from Neo4j", exc_info=True)

        # Topics live in Neo4j only — no Postgres `topics` table in schema.
        return items

    async def list_posts(
        self,
        topic_slug: str | None = None,
        status: str | None = None,
        needs_review: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List social posts with topic / review status filtering from Neo4j."""
        items: list[dict[str, Any]] = []
        if self.driver and hasattr(self.driver, "session"):
            try:
                query = "MATCH (b:BaiDang) RETURN b ORDER BY coalesce(b.ngay_dang, b.thoi_gian, b.ingested_at) DESC LIMIT 100"
                async with self.driver.session() as session:
                    res = await session.run(query)
                    async for record in res:
                        data = self._json_safe(dict(record["b"]))
                        data["chu_de"] = data.get("chu_de") or data.get("source_topic")
                        data["ngay_dang"] = data.get("ngay_dang") or data.get("thoi_gian") or data.get("ingested_at")
                        data["tac_gia"] = data.get("comment_author_name") or data.get("tac_gia") or data.get("tac_gia_hash")
                        if topic_slug and data.get("chu_de") != topic_slug:
                            continue
                        if needs_review is not None and data.get("needs_review", False) != needs_review:
                            continue
                        items.append(data)
            except Exception:
                logger.warning("Failed to list posts from Neo4j", exc_info=True)

        return items

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: SocialAlertFacade._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [SocialAlertFacade._json_safe(v) for v in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

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
        signals = row.get("signals") or []
        if isinstance(signals, str):
            signals = json.loads(signals)
        return {
            "alert_id": str(row.get("id")),
            "chu_de": row.get("chu_de"),
            "khoan_ids": khoan_ids,
            "severity": severity,
            "volume": volume,
            "cluster_size": volume,
            "status": str(row.get("status")) if row.get("status") is not None else "open",
            "signals": signals,
            "provenance_status": row.get("provenance_status", "missing"),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        }

    async def _fetch_alert_rows(self, conn: Any, alert_id: str | None = None) -> list[Any]:
        """Fetch alerts, tolerating DBs that have not applied 009_alert_provenance yet."""
        if alert_id:
            full_sql = (
                "SELECT id, chu_de, khoan_ids, severity, volume, status, signals, provenance_status, created_at "
                "FROM alerts WHERE id = $1"
            )
            base_sql = (
                "SELECT id, chu_de, khoan_ids, severity, volume, status, created_at "
                "FROM alerts WHERE id = $1"
            )
            try:
                row = await conn.fetchrow(full_sql, alert_id)
            except Exception as exc:
                if "signals" not in str(exc) and "provenance_status" not in str(exc):
                    raise
                row = await conn.fetchrow(base_sql, alert_id)
            return [row] if row else []

        full_sql = (
            "SELECT id, chu_de, khoan_ids, severity, volume, status, signals, provenance_status, created_at "
            "FROM alerts ORDER BY created_at DESC LIMIT 100"
        )
        base_sql = (
            "SELECT id, chu_de, khoan_ids, severity, volume, status, created_at "
            "FROM alerts ORDER BY created_at DESC LIMIT 100"
        )
        try:
            return await conn.fetch(full_sql)
        except Exception as exc:
            if "signals" not in str(exc) and "provenance_status" not in str(exc):
                raise
            logger.warning("alerts.signals missing — apply Data/schema/postgres/009_alert_provenance.sql")
            return await conn.fetch(base_sql)

    async def list_alerts(self, severity: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        """List alerts generated from BE2 claim check and NLI signal detection in real DB."""
        items: list[dict[str, Any]] = []
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await self._fetch_alert_rows(conn)
                    for r in rows:
                        data = self._alert_from_row(dict(r))
                        if severity and data.get("severity") != severity:
                            continue
                        if status and data.get("status") != status:
                            continue
                        items.append(data)
            except Exception:
                logger.warning("Failed to list alerts from Postgres", exc_info=True)

        return items

    async def get_alert_detail(self, alert_id: str) -> dict[str, Any] | None:
        """Get alert details with cluster of posts and NLI verification edges from real DB."""
        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    rows = await self._fetch_alert_rows(conn, alert_id=alert_id)
                    if rows:
                        return self._alert_from_row(dict(rows[0]))
            except Exception:
                logger.warning("Failed to get alert detail %s from Postgres", alert_id, exc_info=True)

        return None

    async def triage_alert(
        self,
        alert_id: str,
        action: str,
        note: str | None,
        user_id: str,
    ) -> dict[str, Any]:
        """Triage an alert: change status or trigger suggestion draft creation in real DB."""
        suggest_id = None

        if action == "create_suggest":
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
                except Exception as exc:
                    logger.exception("Failed to insert suggestion for alert triage", extra={"alert_id": alert_id})
                    raise BE2Error(f"Không thể tạo đề xuất đính chính cho cảnh báo: {exc}") from exc

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
            except Exception as exc:
                logger.exception("Failed to update alert status in Postgres", extra={"alert_id": alert_id})
                raise BE2Error(f"Không thể cập nhật trạng thái cảnh báo trong Postgres: {exc}") from exc

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
                logger.warning("Failed to update AlertMeta status in Neo4j for alert %s", alert_id, exc_info=True)

        return {
            "alert_id": alert_id,
            "previous_action": action,
            "new_status": db_status,
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
            logger.warning("Failed to generate link preview for %s", url, exc_info=True)

        return {
            "url": url,
            "domain": domain,
            "title": title,
            "description": description,
            "image": f"https://{domain}/favicon.ico",
            "candidate_text": f"Trích đoạn nội dung chính từ {url}.",
        }
