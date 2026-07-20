from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid5, NAMESPACE_URL
from app.schemas import LinkCandidate, NliResult, SocialPost, TopicResult
from app.pipelines.social.ingest import content_item_from_social_post


class Neo4jSocialRepository:
    """BE2 Neo4j writes limited to labels/relationships in SYSTEM_DATA.md."""

    def __init__(self, driver: Any, pool: Any | None = None) -> None:
        self.driver = driver
        self.pool = pool

    async def upsert_post(self, post: SocialPost) -> str:
        bai_dang_id = f"{post.platform}:{post.external_id}"
        content_item = content_item_from_social_post(post)
        query = """
        MERGE (b:BaiDang:NoiDungNguon {platform: $platform, external_id: $external_id})
        SET b.content_id = $content_id,
            b.source_type = $source_type,
            b.provider = $provider,
            b.canonical_url = $canonical_url,
            b.content_hash = $content_hash,
            b.title = $title,
            b.engagement_json = $engagement_json,
            b.noi_dung = $noi_dung,
            b.tac_gia_hash = $tac_gia_hash,
            b.tac_gia = $tac_gia,
            b.url = $url,
            b.chu_de = $chu_de,
            b.source_query = $source_query,
            b.youtube_kind = $youtube_kind,
            b.comment_id = $comment_id,
            b.comment_author_name = $comment_author_name,
            b.comment_text = $comment_text,
            b.comment_url = $comment_url,
            b.video_title = $video_title,
            b.video_url = $video_url,
            b.thoi_gian = datetime($thoi_gian),
            b.ngay_dang = datetime($thoi_gian),
            b.ingested_at = datetime($ingested_at),
            b.source_metadata_json = $source_metadata_json
        RETURN b.platform + ':' + b.external_id AS bai_dang_id
        """
        meta = post.source_metadata or {}
        comment_text = None
        if meta.get("youtube_kind") == "comment":
            parts = [part.strip() for part in post.noi_dung.split("\n\n", 1)]
            comment_text = parts[1] if len(parts) == 2 else post.noi_dung
        params = {
            "platform": post.platform,
            "external_id": post.external_id,
            "content_id": content_item.content_id,
            "source_type": content_item.source_type.value,
            "provider": content_item.provider,
            "canonical_url": content_item.canonical_url,
            "content_hash": content_item.content_hash,
            "title": content_item.title,
            "engagement_json": json.dumps(content_item.engagement, ensure_ascii=False, default=str),
            "noi_dung": post.noi_dung,
            "tac_gia_hash": post.tac_gia_hash,
            "tac_gia": meta.get("comment_author_name") or meta.get("author_name") or meta.get("video_channel_title"),
            "url": post.url,
            "chu_de": meta.get("source_topic"),
            "source_query": meta.get("source_query"),
            "youtube_kind": meta.get("youtube_kind"),
            "comment_id": meta.get("comment_id"),
            "comment_author_name": meta.get("comment_author_name"),
            "comment_text": comment_text,
            "comment_url": meta.get("comment_url"),
            "video_title": meta.get("video_title"),
            "video_url": meta.get("video_url"),
            "source_metadata_json": json.dumps(meta, ensure_ascii=False, default=str),
            "thoi_gian": post.thoi_gian.isoformat(),
            "ingested_at": post.ingested_at.isoformat(),
        }
        async with self.driver.session() as session:
            result = await session.run(query, **params)
            record = await result.single()
        return record["bai_dang_id"] if record else bai_dang_id

    async def get_post(self, bai_dang_id: str) -> SocialPost | None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = "MATCH (b:BaiDang {platform: $platform, external_id: $external_id}) RETURN b"
        async with self.driver.session() as session:
            result = await session.run(query, platform=platform, external_id=external_id)
            record = await result.single()
        if not record:
            return None
        data = dict(record["b"])
        source_metadata = data.get("source_metadata_json") or {}
        if isinstance(source_metadata, str):
            try:
                source_metadata = json.loads(source_metadata)
            except json.JSONDecodeError:
                source_metadata = {}
        if not isinstance(source_metadata, dict):
            source_metadata = {}
        source_metadata.setdefault("source_type", data.get("source_type"))
        source_metadata.setdefault("provider", data.get("provider"))
        return SocialPost(
            platform=data["platform"],
            external_id=data["external_id"],
            noi_dung=data["noi_dung"],
            tac_gia_hash=data.get("tac_gia_hash"),
            url=data.get("url"),
            thoi_gian=data.get("thoi_gian") or datetime.now(timezone.utc),
            source_metadata=source_metadata,
            ingested_at=data.get("ingested_at") or datetime.now(timezone.utc),
        )

    async def save_topic(self, result: TopicResult) -> None:
        if not result.slug:
            return
        platform, external_id = result.bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})
        MERGE (c:ChuDe {slug: $slug})
        SET c.ten = coalesce(c.ten, $slug)
        SET b.chu_de = coalesce(b.chu_de, $slug)
        MERGE (b)-[r:THAO_LUAN_VE]->(c)
        SET r.score = $score, r.model = $model, r.status = $status
        """
        async with self.driver.session() as session:
            result_cursor = await session.run(query, platform=platform, external_id=external_id, slug=result.slug, score=result.score, model=result.model, status=result.status)
            await result_cursor.consume()

    async def get_topic(self, bai_dang_id: str) -> TopicResult | None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})-[r:THAO_LUAN_VE]->(c:ChuDe)
        RETURN c.slug AS slug, r.score AS score, r.status AS status, r.model AS model
        ORDER BY r.score DESC LIMIT 1
        """
        async with self.driver.session() as session:
            result = await session.run(query, platform=platform, external_id=external_id)
            record = await result.single()
        if not record:
            return None
        return TopicResult(bai_dang_id=bai_dang_id, slug=record["slug"], score=float(record["score"]), status=record["status"], model=record["model"])

    async def create_link_edge(self, bai_dang_id: str, candidate: LinkCandidate, *, method: str) -> None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})
        MATCH (k:Khoan {khoan_id: $khoan_id})
        MATCH (b)-[:THAO_LUAN_VE]->(:ChuDe)-[:LIEN_QUAN]->(k)
        MERGE (b)-[r:GAN_CO_CAN_KIEM_CHUNG]->(k)
        SET r.score = $score, r.method = $method, r.updated_at = datetime($updated_at)
        """
        async with self.driver.session() as session:
            result = await session.run(query, platform=platform, external_id=external_id, khoan_id=candidate.khoan_id, score=candidate.score, method=method, updated_at=datetime.now(timezone.utc).isoformat())
            await result.consume()

    async def save_nli(self, bai_dang_id: str, khoan_id: str, result: NliResult, *, claim_text: str, evidence_span: str) -> str:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})
        MATCH (k:Khoan {khoan_id: $khoan_id})
        MERGE (y:YKien {uuid: $uuid})
        SET y.bai_dang_id = $bai_dang_id,
            y.claim_hash = $claim_hash,
            y.claim_text = $claim_text,
            y.evidence_span = $evidence_span,
            y.stance = $label,
            y.confidence = $score,
            y.created_at = coalesce(y.created_at, datetime($now)),
            y.updated_at = datetime($now)
        MERGE (b)-[:CO_YKIEN]->(y)
        MERGE (y)-[r:DOI_CHIEU]->(k)
        SET r.label = $label, r.score = $score, r.updated_at = datetime($now)
        """
        claim_hash = str(uuid5(NAMESPACE_URL, f"{bai_dang_id}:{khoan_id}:{claim_text}:{evidence_span}"))
        ykien_uuid = str(uuid5(NAMESPACE_URL, f"be2:ykien:{claim_hash}"))
        now = datetime.now(timezone.utc).isoformat()
        async with self.driver.session() as session:
            result_cursor = await session.run(
                query,
                platform=platform,
                external_id=external_id,
                khoan_id=khoan_id,
                bai_dang_id=bai_dang_id,
                uuid=ykien_uuid,
                claim_hash=claim_hash,
                claim_text=claim_text,
                evidence_span=evidence_span,
                label=result.label.value,
                score=result.score,
                now=now,
            )
            await result_cursor.consume()
        return ykien_uuid

    async def save_alert(self, alert: dict[str, Any]) -> str:
        alert_uuid = alert.get("uuid") or alert.get("alert_id") or str(uuid5(NAMESPACE_URL, f"be2:alert:{alert.get('dedupe_key') or alert}"))
        now = datetime.now(timezone.utc).isoformat()
        query = """
        MERGE (a:AlertMeta {uuid: $uuid})
        SET a.chu_de = $chu_de, a.khoan_ids = $khoan_ids, a.severity = $severity,
            a.volume = $volume, a.status = $status, a.provenance_status = $provenance_status,
            a.dedupe_key = $dedupe_key,
            a.signals_json = $signals_json,
            a.created_at = coalesce(a.created_at, datetime($now)),
            a.updated_at = datetime($now),
            a.last_seen_at = datetime($now)
        WITH a
        UNWIND $signal_ids AS signal_id
        OPTIONAL MATCH (y:YKien {uuid: signal_id})
        FOREACH (_ IN CASE WHEN y IS NULL THEN [] ELSE [1] END | MERGE (a)-[:BAO_GOM_TIN_HIEU]->(y))
        RETURN a.uuid AS uuid
        """
        async with self.driver.session() as session:
            signals = alert.get("signals", [])
            result = await session.run(
                query,
                uuid=alert_uuid,
                dedupe_key=alert.get("dedupe_key"),
                chu_de=alert.get("chu_de"),
                khoan_ids=alert.get("khoan_ids", []),
                severity=alert.get("severity"),
                volume=alert.get("volume"),
                status=alert.get("status", "open"),
                provenance_status=alert.get("provenance_status", "missing"),
                signals_json=json.dumps(signals, ensure_ascii=False, default=str),
                signal_ids=[s.get("ykien_id") for s in signals if s.get("ykien_id")],
                now=now,
            )
            record = await result.single()
        if self.pool and hasattr(self.pool, "acquire"):
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO alerts (id, chu_de, khoan_ids, severity, volume, status, signals, provenance_status)
                    VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6::alert_status, $7::jsonb, $8)
                    ON CONFLICT (id) DO UPDATE SET
                      chu_de = EXCLUDED.chu_de,
                      khoan_ids = EXCLUDED.khoan_ids,
                      severity = EXCLUDED.severity,
                      volume = EXCLUDED.volume,
                      status = EXCLUDED.status,
                      signals = EXCLUDED.signals,
                      provenance_status = EXCLUDED.provenance_status
                    """,
                    str(alert_uuid),
                    alert.get("chu_de"),
                    json.dumps(alert.get("khoan_ids", []), ensure_ascii=False),
                    alert.get("severity"),
                    alert.get("volume", 0),
                    alert.get("status", "open"),
                    json.dumps(alert.get("signals", []), ensure_ascii=False, default=str),
                    alert.get("provenance_status", "missing"),
                )
        return record["uuid"] if record else str(alert_uuid)

    async def find_recent_alert(self, key: str, cooldown_s: int) -> dict[str, Any] | None:
        query = """
        MATCH (a:AlertMeta {dedupe_key: $key})
        WHERE coalesce(a.last_seen_at, a.updated_at, a.created_at)
              >= datetime() - duration({seconds: $cooldown_s})
        RETURN a LIMIT 1
        """
        async with self.driver.session() as session:
            result = await session.run(query, key=key, cooldown_s=max(0, int(cooldown_s)))
            record = await result.single()
        return dict(record["a"]) if record else None

    async def get_recent_alert_signals(
        self,
        *,
        chu_de: str | None,
        khoan_ids: list[str],
        window_s: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        """Load persisted, source-grounded contradictions for one alert aggregation window."""
        if not self.driver or not hasattr(self.driver, "session"):
            return []
        query = """
        MATCH (b:BaiDang)-[:CO_YKIEN]->(y:YKien)-[d:DOI_CHIEU]->(k:Khoan)
        OPTIONAL MATCH (b)-[:THAO_LUAN_VE]->(c:ChuDe)
        WHERE d.label = 'mau_thuan'
          AND d.score >= $min_score
          AND y.created_at >= datetime() - duration({seconds: $window_s})
          AND ($chu_de IS NULL OR coalesce(c.slug, b.chu_de) = $chu_de)
          AND (size($khoan_ids) = 0 OR k.khoan_id IN $khoan_ids)
        RETURN y.uuid AS ykien_id, y.claim_text AS claim_text,
               y.evidence_span AS evidence_span, d.label AS label, d.score AS score,
               b.platform + ':' + b.external_id AS bai_dang_id,
               b.noi_dung AS post_content, b.url AS post_url,
               coalesce(c.slug, b.chu_de) AS chu_de,
               b.source_type AS source_type, b.provider AS provider,
               k.khoan_id AS khoan_id, k.noi_dung AS legal_text,
               k.van_ban_id AS van_ban_id
        ORDER BY y.created_at DESC
        LIMIT 500
        """
        signals: list[dict[str, Any]] = []
        async with self.driver.session() as session:
            result = await session.run(
                query,
                chu_de=chu_de,
                khoan_ids=khoan_ids,
                window_s=max(1, int(window_s)),
                min_score=float(min_score),
            )
            async for record in result:
                signals.append({
                    "bai_dang_id": record.get("bai_dang_id"),
                    "ykien_id": record.get("ykien_id"),
                    "claim_text": record.get("claim_text"),
                    "evidence_span": record.get("evidence_span"),
                    "post_content": record.get("post_content"),
                    "post_url": record.get("post_url"),
                    "chu_de": record.get("chu_de"),
                    "khoan_id": record.get("khoan_id"),
                    "label": record.get("label"),
                    "score": float(record.get("score") or 0.0),
                    "source_type": record.get("source_type"),
                    "provider": record.get("provider"),
                    "legal_evidence": {
                        "khoan_id": record.get("khoan_id"),
                        "van_ban": record.get("van_ban_id"),
                        "quote": record.get("legal_text"),
                    },
                })
        return signals
