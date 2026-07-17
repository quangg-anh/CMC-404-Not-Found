from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid5, NAMESPACE_URL
from app.schemas import LinkCandidate, NliResult, SocialPost, TopicResult


class Neo4jSocialRepository:
    """BE2 Neo4j writes limited to labels/relationships in SYSTEM_DATA.md."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def upsert_post(self, post: SocialPost) -> str:
        bai_dang_id = f"{post.platform}:{post.external_id}"
        query = """
        MERGE (b:BaiDang {platform: $platform, external_id: $external_id})
        SET b.noi_dung = $noi_dung,
            b.tac_gia_hash = $tac_gia_hash,
            b.url = $url,
            b.thoi_gian = datetime($thoi_gian),
            b.ingested_at = datetime($ingested_at)
        RETURN b.platform + ':' + b.external_id AS bai_dang_id
        """
        params = {"platform": post.platform, "external_id": post.external_id, "noi_dung": post.noi_dung, "tac_gia_hash": post.tac_gia_hash, "url": post.url, "thoi_gian": post.thoi_gian.isoformat(), "ingested_at": post.ingested_at.isoformat()}
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
        return SocialPost(platform=data["platform"], external_id=data["external_id"], noi_dung=data["noi_dung"], tac_gia_hash=data.get("tac_gia_hash"), url=data.get("url"), thoi_gian=data.get("thoi_gian") or datetime.now(timezone.utc))

    async def save_topic(self, result: TopicResult) -> None:
        if not result.slug:
            return
        platform, external_id = result.bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})
        MERGE (c:ChuDe {slug: $slug})
        SET c.ten = coalesce(c.ten, $slug)
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

    async def save_nli(self, bai_dang_id: str, khoan_id: str, result: NliResult) -> None:
        platform, external_id = bai_dang_id.split(":", 1)
        query = """
        MATCH (b:BaiDang {platform: $platform, external_id: $external_id})
        MATCH (k:Khoan {khoan_id: $khoan_id})
        MERGE (y:YKien {uuid: $uuid})
        SET y.bai_dang_id = $bai_dang_id,
            y.claim_hash = $claim_hash,
            y.claim_text = $claim_text,
            y.stance = $label,
            y.confidence = $score
        MERGE (b)-[:LIEN_QUAN]->(y)
        MERGE (y)-[r:DOI_CHIEU]->(k)
        SET r.label = $label, r.score = $score
        """
        claim_hash = f"{bai_dang_id}:{khoan_id}:{result.label}"
        ykien_uuid = str(uuid5(NAMESPACE_URL, f"be2:ykien:{claim_hash}"))
        async with self.driver.session() as session:
            result_cursor = await session.run(query, platform=platform, external_id=external_id, khoan_id=khoan_id, bai_dang_id=bai_dang_id, uuid=ykien_uuid, claim_hash=claim_hash, claim_text=claim_hash, label=result.label.value, score=result.score)
            await result_cursor.consume()

    async def save_alert(self, alert: dict[str, Any]) -> str:
        alert_uuid = alert.get("uuid") or alert.get("alert_id") or str(uuid5(NAMESPACE_URL, f"be2:alert:{alert.get('dedupe_key') or alert}"))
        query = """
        MERGE (a:AlertMeta {uuid: $uuid})
        SET a.chu_de = $chu_de, a.khoan_ids = $khoan_ids, a.severity = $severity,
            a.volume = $volume, a.status = $status, a.created_at = coalesce(a.created_at, datetime($created_at))
        RETURN a.uuid AS uuid
        """
        async with self.driver.session() as session:
            result = await session.run(query, uuid=alert_uuid, chu_de=alert.get("chu_de"), khoan_ids=alert.get("khoan_ids", []), severity=alert.get("severity"), volume=alert.get("volume"), status=alert.get("status", "open"), created_at=datetime.now(timezone.utc).isoformat())
            record = await result.single()
        return record["uuid"] if record else str(alert_uuid)

    async def find_recent_alert(self, key: str, cooldown_s: int) -> dict[str, Any] | None:
        query = "MATCH (a:AlertMeta {uuid: $key}) RETURN a LIMIT 1"
        async with self.driver.session() as session:
            result = await session.run(query, key=key)
            record = await result.single()
        return dict(record["a"]) if record else None
