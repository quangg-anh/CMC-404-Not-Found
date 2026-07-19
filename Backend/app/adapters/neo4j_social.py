from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid5, NAMESPACE_URL
from app.schemas import LinkCandidate, NliResult, SocialPost, TopicResult


def topic_slug(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    if not cleaned:
        return None
    return cleaned.casefold()


def _coerce_datetime(value: Any) -> datetime:
    """Neo4j DateTime / ISO string / native datetime → aware datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        if isinstance(native, datetime):
            return native if native.tzinfo else native.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class Neo4jSocialRepository:
    """BE2 Neo4j writes limited to labels/relationships in SYSTEM_DATA.md."""

    def __init__(self, driver: Any, pool: Any | None = None) -> None:
        self.driver = driver
        self.pool = pool

    async def upsert_post(self, post: SocialPost) -> str:
        bai_dang_id = f"{post.platform}:{post.external_id}"
        meta = post.source_metadata or {}
        chu_de = topic_slug(meta.get("source_topic") or meta.get("chu_de"))
        query = """
        MERGE (b:BaiDang {platform: $platform, external_id: $external_id})
        SET b.noi_dung = $noi_dung,
            b.tac_gia_hash = $tac_gia_hash,
            b.tac_gia = $tac_gia,
            b.url = $url,
            b.chu_de = $chu_de,
            b.source_topic = $chu_de,
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
        WITH b
        FOREACH (_ IN CASE WHEN $chu_de IS NULL THEN [] ELSE [1] END |
            MERGE (c:ChuDe {slug: $chu_de})
            SET c.ten = coalesce(c.ten, $chu_de_ten, $chu_de)
            MERGE (b)-[r:THAO_LUAN_VE]->(c)
            SET r.score = coalesce(r.score, 1.0),
                r.model = coalesce(r.model, 'crawl_source_topic'),
                r.status = coalesce(r.status, 'classified')
        )
        RETURN b.platform + ':' + b.external_id AS bai_dang_id
        """
        comment_text = None
        if meta.get("youtube_kind") == "comment":
            parts = [part.strip() for part in post.noi_dung.split("\n\n", 1)]
            comment_text = parts[1] if len(parts) == 2 else post.noi_dung
        chu_de_ten = str(meta.get("source_topic") or meta.get("chu_de") or chu_de or "").strip() or None
        params = {
            "platform": post.platform,
            "external_id": post.external_id,
            "noi_dung": post.noi_dung,
            "tac_gia_hash": post.tac_gia_hash,
            "tac_gia": meta.get("comment_author_name") or meta.get("author_name") or meta.get("video_channel_title"),
            "url": post.url,
            "chu_de": chu_de,
            "chu_de_ten": chu_de_ten,
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

    async def ensure_topics_from_posts(self) -> int:
        """Backfill ChuDe + THAO_LUAN_VE for posts that only have chu_de / source_topic props."""
        query = """
        MATCH (b:BaiDang)
        WHERE coalesce(b.chu_de, b.source_topic) IS NOT NULL
          AND trim(toString(coalesce(b.chu_de, b.source_topic))) <> ''
        WITH b, toLower(trim(toString(coalesce(b.chu_de, b.source_topic)))) AS slug
        MERGE (c:ChuDe {slug: slug})
        SET c.ten = coalesce(c.ten, trim(toString(coalesce(b.chu_de, b.source_topic))))
        SET b.chu_de = slug
        MERGE (b)-[r:THAO_LUAN_VE]->(c)
        SET r.score = coalesce(r.score, 1.0),
            r.model = coalesce(r.model, 'backfill_source_topic'),
            r.status = coalesce(r.status, 'classified')
        RETURN count(DISTINCT c) AS topics
        """
        async with self.driver.session() as session:
            result = await session.run(query)
            record = await result.single()
        return int(record["topics"]) if record else 0

    async def ensure_monitored_topics(self, topics: list[str]) -> int:
        """Seed ChuDe nodes for configured monitor topics (even before crawl has posts)."""
        created = 0
        async with self.driver.session() as session:
            for name in topics:
                slug = topic_slug(name)
                if not slug:
                    continue
                result = await session.run(
                    """
                    MERGE (c:ChuDe {slug: $slug})
                    SET c.ten = coalesce(c.ten, $ten),
                        c.monitored = true
                    RETURN c.slug AS slug
                    """,
                    slug=slug,
                    ten=name.strip(),
                )
                if await result.single():
                    created += 1
        return created

    async def get_post(self, bai_dang_id: str) -> SocialPost | None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform})
        WHERE toString(b.external_id) = $external_id
        RETURN b LIMIT 1
        """
        async with self.driver.session() as session:
            result = await session.run(query, platform=platform, external_id=str(external_id))
            record = await result.single()
        if not record:
            return None
        data = dict(record["b"])
        noi = str(data.get("noi_dung") or data.get("comment_text") or "").strip()
        if not noi:
            return None
        return SocialPost(
            platform=str(data.get("platform") or platform),
            external_id=str(data.get("external_id") or external_id),
            noi_dung=noi,
            tac_gia_hash=str(data["tac_gia_hash"]) if data.get("tac_gia_hash") is not None else None,
            url=str(data["url"]) if data.get("url") else None,
            thoi_gian=_coerce_datetime(
                data.get("thoi_gian") or data.get("ngay_dang") or data.get("ingested_at")
            ),
            source_metadata={
                "chu_de": data.get("chu_de"),
                "source_topic": data.get("source_topic") or data.get("chu_de"),
            },
        )

    async def save_topic(self, result: TopicResult) -> None:
        if not result.slug:
            return
        platform, external_id = result.bai_dang_id.split(":", 1)
        slug = topic_slug(result.slug) or result.slug
        query = """
        MATCH (b:BaiDang {platform: $platform})
        WHERE toString(b.external_id) = $external_id
        MERGE (c:ChuDe {slug: $slug})
        SET c.ten = coalesce(c.ten, $slug)
        SET b.chu_de = coalesce(b.chu_de, $slug)
        MERGE (b)-[r:THAO_LUAN_VE]->(c)
        SET r.score = $score, r.model = $model, r.status = $status
        """
        async with self.driver.session() as session:
            result_cursor = await session.run(
                query,
                platform=platform,
                external_id=str(external_id),
                slug=slug,
                score=result.score,
                model=result.model,
                status=result.status,
            )
            await result_cursor.consume()

    async def get_topic(self, bai_dang_id: str) -> TopicResult | None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang)
        WHERE b.platform = $platform AND toString(b.external_id) = $external_id
        OPTIONAL MATCH (b)-[r:THAO_LUAN_VE]->(c:ChuDe)
        WITH b, c, r
        ORDER BY coalesce(r.score, 0) DESC
        LIMIT 1
        RETURN coalesce(c.slug, b.chu_de, b.source_topic) AS slug,
               coalesce(r.score, 1.0) AS score,
               coalesce(r.status, 'classified') AS status,
               coalesce(r.model, 'bai_dang_chu_de') AS model
        """
        async with self.driver.session() as session:
            result = await session.run(query, platform=platform, external_id=str(external_id))
            record = await result.single()
        if not record or not record.get("slug"):
            return None
        slug = topic_slug(str(record["slug"])) or str(record["slug"])
        status = record.get("status")
        if status not in {"classified", "needs_review", "unknown"}:
            status = "classified"
        return TopicResult(
            bai_dang_id=bai_dang_id,
            slug=slug,
            score=min(1.0, max(0.0, float(record.get("score") or 1.0))),
            status=status,
            model=str(record.get("model") or "bai_dang_chu_de"),
        )

    async def create_link_edge(self, bai_dang_id: str, candidate: LinkCandidate, *, method: str) -> None:
        platform, external_id = bai_dang_id.split(":", 1)
        # Do not require ChuDe-[:LIEN_QUAN]->Khoan beforehand — MERGE it when ChuDe exists.
        query = """
        MATCH (b:BaiDang {platform: $platform})
        WHERE toString(b.external_id) = $external_id
        MATCH (k:Khoan {khoan_id: $khoan_id})
        OPTIONAL MATCH (b)-[:THAO_LUAN_VE]->(c:ChuDe)
        FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
          MERGE (c)-[:LIEN_QUAN]->(k)
        )
        MERGE (b)-[r:GAN_CO_CAN_KIEM_CHUNG]->(k)
        SET r.score = $score, r.method = $method, r.updated_at = datetime($updated_at)
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                platform=platform,
                external_id=str(external_id),
                khoan_id=candidate.khoan_id,
                score=candidate.score,
                method=method,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            await result.consume()

    async def fetch_khoan_text(self, khoan_id: str) -> str | None:
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (k:Khoan {khoan_id: $khoan_id}) RETURN k.noi_dung AS noi_dung LIMIT 1",
                khoan_id=khoan_id,
            )
            record = await result.single()
        return str(record["noi_dung"]) if record and record.get("noi_dung") else None

    async def save_nli(self, bai_dang_id: str, khoan_id: str, result: NliResult, *, claim_text: str, evidence_span: str) -> str:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform})
        WHERE toString(b.external_id) = $external_id
        MATCH (k:Khoan {khoan_id: $khoan_id})
        MERGE (y:YKien {uuid: $uuid})
        SET y.bai_dang_id = $bai_dang_id,
            y.claim_hash = $claim_hash,
            y.claim_text = $claim_text,
            y.evidence_span = $evidence_span,
            y.stance = $label,
            y.confidence = $score
        MERGE (b)-[:CO_YKIEN]->(y)
        MERGE (y)-[r:DOI_CHIEU]->(k)
        SET r.label = $label, r.score = $score
        """
        claim_hash = str(uuid5(NAMESPACE_URL, f"{bai_dang_id}:{khoan_id}:{claim_text}:{evidence_span}"))
        ykien_uuid = str(uuid5(NAMESPACE_URL, f"be2:ykien:{claim_hash}"))
        async with self.driver.session() as session:
            result_cursor = await session.run(
                query,
                platform=platform,
                external_id=str(external_id),
                khoan_id=khoan_id,
                bai_dang_id=bai_dang_id,
                uuid=ykien_uuid,
                claim_hash=claim_hash,
                claim_text=claim_text,
                evidence_span=evidence_span,
                label=result.label.value,
                score=result.score,
            )
            await result_cursor.consume()
        return ykien_uuid

    async def save_alert(self, alert: dict[str, Any]) -> str:
        alert_uuid = alert.get("uuid") or alert.get("alert_id") or str(uuid5(NAMESPACE_URL, f"be2:alert:{alert.get('dedupe_key') or alert}"))
        query = """
        MERGE (a:AlertMeta {uuid: $uuid})
        SET a.chu_de = $chu_de, a.khoan_ids = $khoan_ids, a.severity = $severity,
            a.volume = $volume, a.status = $status, a.provenance_status = $provenance_status,
            a.dedupe_key = $dedupe_key,
            a.signals_json = $signals_json,
            a.created_at = coalesce(a.created_at, datetime($created_at))
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
                chu_de=alert.get("chu_de"),
                khoan_ids=alert.get("khoan_ids", []),
                severity=alert.get("severity"),
                volume=alert.get("volume"),
                status=alert.get("status", "open"),
                provenance_status=alert.get("provenance_status", "missing"),
                dedupe_key=alert.get("dedupe_key"),
                signals_json=json.dumps(signals, ensure_ascii=False, default=str),
                signal_ids=[s.get("ykien_id") for s in signals if s.get("ykien_id")],
                created_at=datetime.now(timezone.utc).isoformat(),
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
        alert_uuid = str(uuid5(NAMESPACE_URL, f"be2:alert:{key}"))
        query = """
        MATCH (a:AlertMeta)
        WHERE a.uuid = $uuid OR a.dedupe_key = $key
        RETURN a
        LIMIT 1
        """
        async with self.driver.session() as session:
            result = await session.run(query, uuid=alert_uuid, key=key)
            record = await result.single()
        return dict(record["a"]) if record else None
