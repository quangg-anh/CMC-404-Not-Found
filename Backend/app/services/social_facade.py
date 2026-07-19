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
        # Pass Postgres pool so save_alert mirrors AlertMeta → alerts table (UI reads PG).
        self.neo_repo = Neo4jSocialRepository(neo4j_driver, pool) if neo4j_driver else None
        self.pg_repo = PostgresContentRepository(pool) if pool else None

    async def _build_review_ctx(self, cfg: Any) -> dict[str, Any] | None:
        """Build worker-compatible ctx for claim/NLI/alert after admin crawl."""
        if not self.neo_repo:
            return None
        from app.intelligence.embedder import Embedder
        from app.intelligence.llm_router import LLMRouter
        from app.intelligence.nli import NLIService
        from app.pipelines.social.alert_signal import AlertSignalService
        from app.pipelines.social.claim_check import ClaimChecker
        from app.pipelines.social.entity_link import EntityLinker
        from app.pipelines.social.topic_classify import TopicClassifier

        ctx: dict[str, Any] = {
            "config": cfg,
            "social_repo": self.neo_repo,
            "alert_signal_service": AlertSignalService(self.neo_repo, cfg),
            "claim_checker": ClaimChecker(None, NLIService(cfg)),
            "topic_classifier": None,
            "entity_linker": None,
        }
        try:
            from app.api.deps import get_qdrant_client

            qdrant = await get_qdrant_client()
            embedder = Embedder(cfg)
            ctx["topic_classifier"] = TopicClassifier(qdrant, embedder, cfg)
            ctx["entity_linker"] = EntityLinker(qdrant, self.neo_repo, embedder, None, cfg)
        except Exception:  # noqa: BLE001
            logger.warning("Review ctx without Qdrant/entity linker — Neo4j khoan fallback only", exc_info=True)
        try:
            from app.api.deps import RealLLMClient, normalize_service_url
            import os

            router = LLMRouter(
                config=cfg,
                client=RealLLMClient(
                    base_url=normalize_service_url(
                        os.getenv("BE2_INTELLIGENCE_URL"),
                        default="http://localhost:8002",
                    )
                ),
            )
            ctx["claim_checker"] = ClaimChecker(router, NLIService(cfg))
            ctx["llm_router"] = router
        except Exception:  # noqa: BLE001
            logger.warning("Review ctx using heuristic NLI only (no LLM router)", exc_info=True)
        return ctx

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
        chain_results: list[dict[str, Any]] = []
        if not dry_run and self.neo_repo:
            ingest_service = SocialIngestService(self.neo_repo, cfg)
            for payload in collected:
                try:
                    post = await ingest_service.ingest(payload)
                    ingested_items.append(post.model_dump())
                except Exception as exc:  # noqa: BLE001
                    errors.append({"platform": payload.get("platform"), "external_id": payload.get("external_id"), "message": str(exc)})
            # Ensure monitored ChuDe nodes exist even if a topic had zero collected posts.
            try:
                await self.neo_repo.ensure_monitored_topics(active_topics)
                await self.neo_repo.ensure_topics_from_posts()
            except Exception:  # noqa: BLE001
                logger.warning("Failed to ensure ChuDe topics after crawl", exc_info=True)

            # Topic → link → claim/NLI → alert (fills Alerts UI + Graph clarity DOI_CHIEU).
            try:
                review_ctx = await self._build_review_ctx(cfg)
                if review_ctx:
                    from app.workers.social_jobs import _chain_social_review

                    for item in ingested_items:
                        platform = item.get("platform")
                        external_id = item.get("external_id")
                        if not platform or not external_id:
                            continue
                        try:
                            chain_results.append(
                                await _chain_social_review(
                                    review_ctx,
                                    bai_dang_id=f"{platform}:{external_id}",
                                    dry_run=False,
                                )
                            )
                        except Exception as exc:  # noqa: BLE001
                            errors.append(
                                {
                                    "platform": platform,
                                    "external_id": external_id,
                                    "message": f"review chain: {exc}",
                                }
                            )
            except Exception:  # noqa: BLE001
                logger.warning("Social review chain unavailable after crawl", exc_info=True)

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

        alerts_made = sum(1 for c in chain_results if c.get("alert"))
        if chain_results and not message:
            message = (
                f"Đã lưu {len(ingested_items)} bài, chạy pipeline claim/NLI; "
                f"tạo {alerts_made} cảnh báo."
            )

        return {
            "status": status,
            "message": message,
            "topics": active_topics,
            "platforms": sorted(active_platforms),
            "dry_run": dry_run,
            "collected": len(collected),
            "ingested": len(ingested_items),
            "chain": chain_results,
            "alerts_created": alerts_made,
            "items": ingested_items if ingested_items else collected[:100],
            "errors": errors,
        }

    async def reprocess_existing_posts(
        self,
        *,
        limit: int = 100,
        only_missing_doi_chieu: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run claim/NLI/alert on BaiDang already in Neo4j (pre-fix crawl data).

        Default: only posts that still lack DOI_CHIEU. Set only_missing_doi_chieu=False to redo all.
        """
        if not self.neo_repo or not self.driver:
            return {
                "status": "failed",
                "message": "Neo4j không khả dụng — không thể đọc bài cũ.",
                "processed": 0,
                "alerts_created": 0,
                "items": [],
            }

        cfg = get_config()
        bounded = max(1, min(int(limit), 500))
        ids: list[str] = []
        try:
            if only_missing_doi_chieu:
                query = """
                MATCH (b:BaiDang)
                WHERE b.platform IS NOT NULL AND b.external_id IS NOT NULL
                  AND b.noi_dung IS NOT NULL AND size(toString(b.noi_dung)) >= 20
                OPTIONAL MATCH (b)-[:CO_YKIEN]->(:YKien)-[d:DOI_CHIEU]->(:Khoan)
                WITH b, count(d) AS doi
                WHERE doi = 0
                RETURN b.platform AS platform, b.external_id AS external_id
                ORDER BY coalesce(b.ngay_dang, b.thoi_gian, b.ingested_at) DESC
                LIMIT $limit
                """
            else:
                query = """
                MATCH (b:BaiDang)
                WHERE b.platform IS NOT NULL AND b.external_id IS NOT NULL
                  AND b.noi_dung IS NOT NULL AND size(toString(b.noi_dung)) >= 20
                RETURN b.platform AS platform, b.external_id AS external_id
                ORDER BY coalesce(b.ngay_dang, b.thoi_gian, b.ingested_at) DESC
                LIMIT $limit
                """
            async with self.driver.session() as session:
                res = await session.run(query, limit=bounded)
                async for record in res:
                    platform = record.get("platform")
                    external_id = record.get("external_id")
                    if platform and external_id:
                        ids.append(f"{platform}:{external_id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed listing BaiDang for reprocess", exc_info=True)
            return {
                "status": "failed",
                "message": f"Không đọc được bài cũ từ Neo4j: {exc}",
                "processed": 0,
                "alerts_created": 0,
                "items": [],
            }

        if not ids:
            return {
                "status": "success",
                "message": (
                    "Không còn bài cũ thiếu DOI_CHIEU."
                    if only_missing_doi_chieu
                    else "Không có BaiDang đủ dài để xử lý."
                ),
                "processed": 0,
                "alerts_created": 0,
                "skipped": 0,
                "items": [],
            }

        if dry_run:
            return {
                "status": "success",
                "message": f"Dry-run: sẽ xử lý {len(ids)} bài cũ.",
                "processed": 0,
                "alerts_created": 0,
                "planned": len(ids),
                "items": [{"bai_dang_id": i} for i in ids[:50]],
            }

        try:
            await self.neo_repo.ensure_topics_from_posts()
        except Exception:  # noqa: BLE001
            logger.warning("ensure_topics_from_posts failed before reprocess", exc_info=True)

        review_ctx = await self._build_review_ctx(cfg)
        if not review_ctx:
            return {
                "status": "failed",
                "message": "Không khởi tạo được pipeline claim/NLI.",
                "processed": 0,
                "alerts_created": 0,
                "items": [],
            }

        from app.workers.social_jobs import _chain_social_review

        chain_results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for bai_dang_id in ids:
            try:
                chain_results.append(
                    await _chain_social_review(review_ctx, bai_dang_id=bai_dang_id, dry_run=False)
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"bai_dang_id": bai_dang_id, "message": str(exc)})

        alerts_made = sum(1 for c in chain_results if c.get("alert"))
        claims = sum(int(c.get("claims") or 0) for c in chain_results)
        stage_errs = [
            e
            for c in chain_results
            for e in (c.get("errors") or [])
        ]
        sample_err = None
        if errors:
            sample_err = errors[0].get("message")
        elif stage_errs:
            sample_err = stage_errs[0].get("message") or stage_errs[0].get("code") or str(stage_errs[0])
        status = "success" if chain_results and not errors else ("partial" if chain_results else "failed")
        msg = (
            f"Đã xử lý {len(chain_results)}/{len(ids)} bài cũ: "
            f"{claims} đối chiếu DOI_CHIEU, {alerts_made} cảnh báo mới."
        )
        if sample_err and claims == 0:
            msg += f" Lỗi mẫu: {sample_err}"
        return {
            "status": status,
            "message": msg,
            "processed": len(chain_results),
            "planned": len(ids),
            "claims": claims,
            "alerts_created": alerts_made,
            "errors": errors[:20] + [{"stage_errors_sample": stage_errs[:5]}] if stage_errs else errors[:20],
            "items": chain_results[:50],
        }

    async def list_topics(self) -> list[dict[str, Any]]:
        """List legal topics monitored on social channels (Neo4j ChuDe).

        Also backfills ChuDe from BaiDang.chu_de / source_topic so crawl data shows up
        in bubble charts without waiting for the async topic-classifier worker.
        """
        from app.adapters.neo4j_social import topic_slug

        items: list[dict[str, Any]] = []
        cfg = get_config()
        if self.neo_repo and hasattr(self.neo_repo, "ensure_topics_from_posts"):
            try:
                await self.neo_repo.ensure_monitored_topics(cfg.social_monitor_topics or [])
                await self.neo_repo.ensure_topics_from_posts()
            except Exception:
                logger.warning("Failed to backfill ChuDe topics", exc_info=True)

        if self.driver and hasattr(self.driver, "session"):
            try:
                # Prefer relationship counts; fall back to BaiDang.chu_de when edges are missing.
                query = """
                MATCH (t:ChuDe)
                OPTIONAL MATCH (t)<-[:THAO_LUAN_VE]-(b:BaiDang)
                WITH t, count(b) AS linked
                OPTIONAL MATCH (b2:BaiDang)
                WHERE linked = 0
                  AND toLower(trim(toString(coalesce(b2.chu_de, b2.source_topic, '')))) = t.slug
                WITH t, linked, count(b2) AS prop_count
                WITH t, CASE WHEN linked > 0 THEN linked ELSE prop_count END AS post_count
                RETURN t {
                  .*,
                  post_count: post_count,
                  so_bai: post_count,
                  ten: coalesce(t.ten, t.name, t.slug)
                } AS topic
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
                        data["ten"] = data.get("ten") or data.get("name") or data.get("slug")
                        items.append(self._json_safe(data))
            except Exception:
                logger.warning("Failed to list topics from Neo4j", exc_info=True)

        # Seed configured monitor topics when Neo4j is empty / offline so the UI is not blank.
        seen = {(str(it.get("slug") or "").casefold()) for it in items}
        for name in cfg.social_monitor_topics or []:
            slug = topic_slug(name)
            if not slug or slug in seen:
                continue
            seen.add(slug)
            items.append(
                {
                    "slug": slug,
                    "ten": name.strip(),
                    "name": name.strip(),
                    "post_count": 0,
                    "so_bai": 0,
                    "monitored": True,
                }
            )
        return items

    async def clarity_index_by_topic(self, min_volume: int = 1, limit: int = 50) -> dict[str, Any]:
        """Topic-level legal clarity risk from social radar data.

        Primary: share of DOI_CHIEU labels mau_thuan/khong_ro under each ChuDe.
        Fallback: needs_review / ambiguous stance on BaiDang when no DOI_CHIEU yet.
        """
        bounded_min = max(1, min(min_volume, 1000))
        bounded_limit = max(1, min(limit, 200))
        items: list[dict[str, Any]] = []

        if self.neo_repo and hasattr(self.neo_repo, "ensure_topics_from_posts"):
            try:
                await self.neo_repo.ensure_topics_from_posts()
            except Exception:
                logger.warning("clarity backfill topics failed", exc_info=True)

        if self.driver and hasattr(self.driver, "session"):
            try:
                query = """
                MATCH (c:ChuDe)
                OPTIONAL MATCH (b:BaiDang)-[:THAO_LUAN_VE]->(c)
                OPTIONAL MATCH (b)-[:CO_YKIEN]->(y:YKien)-[d:DOI_CHIEU]->(:Khoan)
                WITH c,
                     count(DISTINCT b) AS volume,
                     count(d) AS doi_chieu,
                     count(CASE WHEN d.label IN ['mau_thuan', 'khong_ro'] THEN 1 END) AS fuzzy,
                     count(CASE WHEN d.label = 'mau_thuan' THEN 1 END) AS mau_thuan,
                     count(CASE WHEN d.label = 'khong_ro' THEN 1 END) AS khong_ro,
                     count(CASE WHEN coalesce(b.needs_review, false) = true THEN 1 END) AS needs_review
                WHERE volume >= $min_volume
                WITH c, volume, doi_chieu, fuzzy, mau_thuan, khong_ro, needs_review,
                     CASE
                       WHEN doi_chieu > 0 THEN toFloat(fuzzy) / doi_chieu
                       WHEN volume > 0 THEN toFloat(needs_review) / volume
                       ELSE 0.0
                     END AS clarity_risk
                RETURN coalesce(c.ten, c.name, c.slug) AS ten,
                       c.slug AS slug,
                       volume,
                       doi_chieu,
                       mau_thuan,
                       khong_ro,
                       needs_review,
                       clarity_risk
                ORDER BY clarity_risk * log(volume + 1) DESC
                LIMIT $limit
                """
                async with self.driver.session() as session:
                    res = await session.run(query, min_volume=bounded_min, limit=bounded_limit)
                    async for r in res:
                        items.append(
                            {
                                "slug": r.get("slug"),
                                "ten": r.get("ten"),
                                "volume": int(r.get("volume") or 0),
                                "doi_chieu": int(r.get("doi_chieu") or 0),
                                "mau_thuan": int(r.get("mau_thuan") or 0),
                                "khong_ro": int(r.get("khong_ro") or 0),
                                "needs_review": int(r.get("needs_review") or 0),
                                "clarity_risk": round(float(r.get("clarity_risk") or 0.0), 3),
                            }
                        )
            except Exception:
                logger.warning("Failed to compute social clarity index", exc_info=True)

        return {"min_volume": bounded_min, "items": items, "total": len(items)}

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
        """List alerts from Postgres; fall back to Neo4j AlertMeta if PG empty/unavailable."""
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

        if items:
            return items

        if self.driver and hasattr(self.driver, "session"):
            try:
                async with self.driver.session() as session:
                    res = await session.run(
                        """
                        MATCH (a:AlertMeta)
                        RETURN a
                        ORDER BY coalesce(a.created_at, datetime('1970-01-01')) DESC
                        LIMIT 100
                        """
                    )
                    async for record in res:
                        node = dict(record["a"])
                        data = {
                            "id": node.get("uuid") or node.get("id"),
                            "chu_de": node.get("chu_de"),
                            "khoan_ids": node.get("khoan_ids") or [],
                            "severity": node.get("severity"),
                            "volume": node.get("volume") or 0,
                            "status": node.get("status") or "open",
                            "provenance_status": node.get("provenance_status"),
                            "signals": json.loads(node["signals_json"])
                            if isinstance(node.get("signals_json"), str)
                            else (node.get("signals") or []),
                            "created_at": str(node.get("created_at") or ""),
                        }
                        if severity and data.get("severity") != severity:
                            continue
                        if status and data.get("status") != status:
                            continue
                        items.append(data)
            except Exception:
                logger.warning("Failed to list alerts from Neo4j AlertMeta", exc_info=True)

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
